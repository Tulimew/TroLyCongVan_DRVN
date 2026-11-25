import os
import sys
import json
import zipfile
import tempfile
import subprocess
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import requests

from core.update_signing import parse_release_version, sign_package, verify_package
from update_transaction import MAX_PACKAGE_BYTES, install_package, is_managed_file

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_VERSION = json.loads((Path(APP_DIR) / "version.json").read_text(encoding="utf-8"))["version"]


class _UpdateSession(requests.Session):
    def get_adapter(self, url):
        if urlsplit(url).scheme != "https":
            raise requests.exceptions.InvalidURL("Máy chủ cập nhật yêu cầu HTTPS.")
        return super().get_adapter(url)

def normalize_download_url(url):
    """
    Tự động chuẩn hóa link cập nhật/tải về.
    Nếu người dùng hoặc quản trị viên dán link Google Drive chia sẻ (dạng view, preview, share),
    hàm sẽ tự động bóc tách File ID và chuyển đổi thành URL tải file trực tiếp (direct stream).
    """
    if not url:
        return ""
    url = url.strip()
    
    # Kiểm tra link Google Drive
    match = re.search(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)', url)
    if not match:
        match = re.search(r'drive\.google\.com/(?:open|uc)\?(?:.*&)?id=([a-zA-Z0-9_-]+)', url)
    if not match:
        match = re.search(r'drive\.usercontent\.google\.com/download\?(?:.*&)?id=([a-zA-Z0-9_-]+)', url)
        
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=download&id={file_id}"
        
    return url

def _get_gdrive_confirm_token(response):
    """Lấy token xác nhận tải về nếu Google Drive yêu cầu xác thực virus hoặc dung lượng"""
    for key, value in response.cookies.items():
        if key.startswith('download_warning'):
            return value
    if 'text/html' in response.headers.get('Content-Type', '').lower():
        match = re.search(r'confirm=([0-9A-Za-z_-]+)', response.text)
        if match:
            return match.group(1)
    return None

def check_for_updates(update_url):
    """
    Kiểm tra phiên bản mới từ máy chủ cập nhật từ xa.
    URL có thể là link Google Drive, GitHub Raw, Gist, web server nội bộ.
    """
    if not update_url or not update_url.strip():
        return {
            "status": "no_url",
            "message": "Chưa thiết lập URL máy chủ cập nhật từ xa. Bạn có thể dán link Google Drive hoặc URL khác trong tab Cấu hình."
        }
    
    raw_url = update_url.strip()
    direct_url = normalize_download_url(raw_url)
    
    session = _UpdateSession()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    try:
        r = session.get(direct_url, timeout=15)
        
        # Nếu Google Drive yêu cầu confirm token
        token = _get_gdrive_confirm_token(r)
        if token:
            r = session.get(direct_url, params={'confirm': token}, timeout=15)
            
        if r.status_code != 200:
            return {
                "status": "error",
                "message": f"Không thể kết nối máy chủ cập nhật (Mã HTTP: {r.status_code})."
            }
        
        # Kiểm tra nếu link Google Drive bị khóa quyền riêng tư (Private)
        if "accounts.google.com" in r.url or ("accounts.google.com" in r.text and "<html" in r.text.lower()):
            return {
                "status": "error",
                "message": "File 'version.json' trên Google Drive đang bị khóa Riêng tư (Private).\n\n"
                           "👉 Quản trị viên cần cài đặt quyền chia sẻ: 'Bất kỳ ai có đường liên kết' -> 'Người xem'."
            }
            
        try:
            data = r.json()
        except Exception:
            return {
                "status": "error",
                "message": "Máy chủ phản hồi nhưng không đúng định dạng version.json hợp lệ.\n"
                           "Nếu dùng Google Drive, hãy đảm bảo tải lên file dạng .json và đặt quyền 'Bất kỳ ai có liên kết'."
            }
            
        remote_ver_str = data.get("version", "").strip()
        if not remote_ver_str:
            return {
                "status": "error",
                "message": "Máy chủ phản hồi nhưng không tìm thấy thông tin phiên bản hợp lệ."
            }
        
        current_tuple = parse_release_version(APP_VERSION)
        remote_tuple = parse_release_version(remote_ver_str)
        
        if remote_tuple > current_tuple:
            return {
                "status": "update_available",
                "current_version": APP_VERSION,
                "remote_version": remote_ver_str,
                "release_date": data.get("release_date", ""),
                "description": data.get("description", "Bản cập nhật nâng cấp tính năng mới."),
                "changelog": data.get("changelog", []),
                "download_url": data.get("download_url", ""),
                "package_signature": data.get("package_signature", ""),
                "message": f"Đã có phiên bản mới: v{remote_ver_str} (Phiên bản bạn đang dùng: v{APP_VERSION})"
            }
        else:
            return {
                "status": "up_to_date",
                "current_version": APP_VERSION,
                "remote_version": remote_ver_str,
                "message": f"Bạn đang sử dụng phiên bản mới nhất (v{APP_VERSION})."
            }
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "message": "Hết thời gian chờ kết nối máy chủ cập nhật (Timeout)."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Lỗi kiểm tra cập nhật: {str(e)}"
        }

def download_and_install_update(download_url, expected_version, package_signature, progress_callback=None):
    """Authenticate the exact archive before staging or touching installed files."""
    try:
        if parse_release_version(expected_version) <= parse_release_version(APP_VERSION):
            raise ValueError("Gói cập nhật phải mới hơn phiên bản cài đặt.")
        if not package_signature:
            raise ValueError("Bản phát hành chưa có chữ ký gói cập nhật.")
        if not download_url:
            raise ValueError("Không tìm thấy đường link tải bản cập nhật.")
        direct_url = normalize_download_url(download_url)
        with tempfile.TemporaryDirectory(prefix="drvn_update_", dir=APP_DIR, ignore_cleanup_errors=True) as temp_dir:
            archive = Path(temp_dir) / "package.zip"
            with _UpdateSession() as session:
                with session.get(direct_url, stream=True, timeout=60) as response:
                    token = _get_gdrive_confirm_token(response)
                    if not token:
                        _download_archive(response, archive, progress_callback)
                if token:
                    with session.get(direct_url, params={"confirm": token}, stream=True, timeout=60) as response:
                        _download_archive(response, archive, progress_callback)
            verify_package(APP_DIR, archive, package_signature)
            install_package(APP_DIR, archive, expected_version)
        return True, "Cập nhật ứng dụng thành công!"
    except Exception as error:
        return False, f"Không thể cài bản cập nhật: {error}"


def _download_archive(response, archive, progress_callback):
    response.raise_for_status()
    total = int(response.headers.get("content-length", 0))
    if total > MAX_PACKAGE_BYTES:
        raise ValueError("Gói cập nhật vượt giới hạn 64 MiB.")
    downloaded = 0
    with archive.open("xb") as stream:
        for chunk in response.iter_content(chunk_size=65536):
            downloaded += len(chunk)
            if downloaded > MAX_PACKAGE_BYTES:
                raise ValueError("Gói cập nhật vượt giới hạn 64 MiB.")
            stream.write(chunk)
            if progress_callback and total > 0:
                progress_callback(min(100, downloaded * 100 // total))


def restart_app():
    """Khởi động lại ứng dụng sau khi cập nhật"""
    try:
        app_file = os.path.join(APP_DIR, "main.py")
        subprocess.Popen([sys.executable, app_file, "--restart-after", str(os.getpid())])
        sys.exit(0)
    except Exception as e:
        print("[Updater] Lỗi khởi động lại ứng dụng:", e)

# =============================================================================
# CÁC HÀM TIỆN ÍCH DÀNH CHO QUẢN TRỊ VIÊN (ADMIN CONSOLE)
# =============================================================================

def release_manifest_path():
    desktop = Path.home() / "Desktop"
    release_dir = desktop / "TroLyCongVan_DRVN_Release" if desktop.is_dir() else Path(APP_DIR) / "dist"
    return release_dir / "version.json"


def _write_manifest(path, data):
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def update_version_manifest(download_url):
    """Update the download link for a separately built release manifest."""
    path = release_manifest_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("package_signature"):
        raise ValueError("Chưa có gói đã ký. Hãy đóng gói bản phát hành trước.")
    data["download_url"] = normalize_download_url(download_url)
    _write_manifest(path, data)
    return data


def write_signed_release(signing_dir, manifest_path, metadata, files):
    """Write a reproducible ZIP and a separate manifest for either release workflow."""
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {key: value for key, value in metadata.items() if key != "package_signature"}
    version = metadata["version"]
    parse_release_version(version)
    zip_path = manifest_path.with_name(f"TroLyCongVan_DRVN_v{version}.zip")
    with tempfile.TemporaryDirectory(dir=manifest_path.parent) as temporary:
        archive = Path(temporary) / zip_path.name
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
            entries = {"version.json": json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")}
            for name, data in files:
                if not is_managed_file(name) or name in entries:
                    raise ValueError(f"Tệp phát hành không hợp lệ: {name}")
                if name.endswith(".py"):
                    compile(data, name, "exec")
                entries[name] = data
            if "main.py" not in entries:
                raise ValueError("Gói phát hành thiếu main.py.")
            for name, data in sorted(entries.items()):
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_DEFLATED
                package.writestr(info, data)
        signature = sign_package(signing_dir, archive)
        verify_package(signing_dir, archive, signature)
        archive.replace(zip_path)
    _write_manifest(manifest_path, {**metadata, "package_signature": signature})
    return zip_path, manifest_path


def create_release_package(new_ver, changelog_list=None, download_url=None):
    """Create an allowlisted ZIP and a separate manifest carrying its signature."""
    try:
        version = new_ver.strip().removeprefix("v").removeprefix("V")
        parse_release_version(version)
        source_dir = Path(APP_DIR)
        manifest = release_manifest_path()
        installed = json.loads((source_dir / "version.json").read_text(encoding="utf-8"))
        installed.update({
            "version": version,
            "release_date": date.today().isoformat(),
            "changelog": changelog_list or installed.get("changelog", []),
            "download_url": normalize_download_url(download_url),
        })
        files = list(source_dir.iterdir())
        for directory in ("core", "ui"):
            files.extend((source_dir / directory).rglob("*.py"))
        payload = ((name, path.read_bytes()) for path in files
                   if (name := path.relative_to(source_dir).as_posix()) != "version.json"
                   and is_managed_file(name) and path.is_file() and not path.is_symlink())
        zip_path, manifest = write_signed_release(source_dir, manifest, installed, payload)
        return {
            "ok": True,
            "zip_path": str(zip_path),
            "zip_name": zip_path.name,
            "manifest_path": str(manifest),
            "size_kb": zip_path.stat().st_size / 1024,
            "message": "Đã tạo ZIP và manifest có chữ ký.",
        }
    except Exception as error:
        return {"ok": False, "message": f"Không thể tạo bản phát hành đã ký: {error}"}


def test_remote_url(url, is_manifest=True):
    """
    Kiểm tra link Google Drive hoặc web server từ xa.
    Trả về: (ok: bool, message: str, data: dict)
    """
    if not url or not url.strip():
        return False, "Chưa nhập đường link kiểm tra.", None
        
    direct_url = normalize_download_url(url.strip())
    session = _UpdateSession()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    try:
        r = session.get(direct_url, timeout=12, stream=not is_manifest)
        token = _get_gdrive_confirm_token(r)
        if token:
            r = session.get(direct_url, params={'confirm': token}, timeout=12, stream=not is_manifest)
            
        if "accounts.google.com" in r.url:
            return False, "❌ File trên Google Drive đang bị khóa Riêng tư (Private)!\n\n👉 Hãy đổi quyền chia sẻ sang: 'Bất kỳ ai có đường liên kết' -> 'Người xem'.", None
            
        if r.status_code != 200:
            return False, f"Máy chủ trả về mã HTTP {r.status_code}.", None
            
        if is_manifest:
            try:
                data = r.json()
                ver = data.get("version", "N/A")
                d_url = data.get("download_url", "")
                ch = data.get("changelog", [])
                ch_count = len(ch) if isinstance(ch, list) else 0
                msg = f"✅ KẾT NỐI THÀNH CÔNG VỚI GOOGLE DRIVE!\n\n" \
                      f"• Phiên bản từ xa: v{ver}\n" \
                      f"• Ngày phát hành: {data.get('release_date', '')}\n" \
                      f"• Link tải zip đính kèm: {'Đã có' if d_url else 'Chưa có link tải'}\n" \
                      f"• Số mục nội dung cập nhật: {ch_count} mục"
                return True, msg, data
            except Exception:
                return False, "❌ Máy chủ phản hồi nhưng không phải định dạng JSON hợp lệ. Đảm bảo bạn tải file 'version.json' lên và giữ nguyên định dạng file.", None
        else:
            size = int(r.headers.get("content-length", 0))
            size_kb = size / 1024 if size > 0 else 0
            return True, f"✅ Link tải file ZIP hợp lệ!\nKích thước file: {size_kb:.1f} KB.", {"size_kb": size_kb}
    except Exception as e:
        return False, f"❌ Lỗi kết nối Google Drive: {str(e)}", None
