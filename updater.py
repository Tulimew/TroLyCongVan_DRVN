import os
import sys
import json
import zipfile
import shutil
import tempfile
import subprocess
import re
import requests

APP_VERSION = "1.0.0"

def parse_version_tuple(ver_str):
    """Chuyển đổi chuỗi version (ví dụ: '1.0.1' hoặc 'v1.0.1') thành tuple số để so sánh chính xác"""
    if not ver_str:
        return (0, 0, 0)
    cleaned = ver_str.strip().lstrip('vV')
    parts = []
    for item in cleaned.split('.'):
        digits = ''.join(c for c in item if c.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)

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
    
    session = requests.Session()
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
        
        current_tuple = parse_version_tuple(APP_VERSION)
        remote_tuple = parse_version_tuple(remote_ver_str)
        
        if remote_tuple > current_tuple:
            return {
                "status": "update_available",
                "current_version": APP_VERSION,
                "remote_version": remote_ver_str,
                "release_date": data.get("release_date", ""),
                "description": data.get("description", "Bản cập nhật nâng cấp tính năng mới."),
                "changelog": data.get("changelog", []),
                "download_url": data.get("download_url", ""),
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

def download_and_install_update(download_url, progress_callback=None):
    """
    Tải file zip cập nhật từ download_url (hỗ trợ Google Drive, direct link),
    giải nén và ghi đè an toàn vào ứng dụng hiện tại.
    BẢO VỆ DỮ LIỆU: Tuyệt đối không ghi đè file drvn_data.db để giữ nguyên cấu hình và văn bản đã lưu.
    """
    if not download_url:
        return False, "Không tìm thấy đường link tải bản cập nhật."
    
    direct_url = normalize_download_url(download_url)
    temp_dir = tempfile.mkdtemp(prefix="drvn_update_")
    zip_file_path = os.path.join(temp_dir, "package.zip")
    app_dir = os.path.dirname(os.path.abspath(__file__))

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })

    try:
        # 1. Tải bản cập nhật
        r = session.get(direct_url, stream=True, timeout=60)
        token = _get_gdrive_confirm_token(r)
        if token:
            r = session.get(direct_url, params={'confirm': token}, stream=True, timeout=60)
            
        if r.status_code != 200:
            return False, f"Máy chủ tải file báo lỗi HTTP {r.status_code}."
        
        # Nếu Google Drive bị khóa quyền
        if "accounts.google.com" in r.url:
            return False, "File zip cập nhật trên Google Drive đang bị khóa Riêng tư (Private). Quản trị viên cần đặt quyền chia sẻ: 'Bất kỳ ai có đường liên kết'."
            
        total_size = int(r.headers.get('content-length', 0))
        downloaded = 0
        with open(zip_file_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=16384):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        progress_callback(int((downloaded / total_size) * 100))
        
        # Kiểm tra tính hợp lệ của file ZIP
        if not zipfile.is_zipfile(zip_file_path):
            with open(zip_file_path, "r", encoding="utf-8", errors="ignore") as f:
                sample = f.read(500)
            if "accounts.google.com" in sample or "Sign in" in sample or "Đăng nhập" in sample:
                return False, "File cập nhật trên Google Drive đang yêu cầu đăng nhập. Quản trị viên cần đặt quyền: 'Bất kỳ ai có đường liên kết đều có thể xem'."
            return False, "File tải về không đúng định dạng ZIP chuẩn (có thể do link tải bị lỗi)."

        # 2. Giải nén vào thư mục tạm
        extract_folder = os.path.join(temp_dir, "extracted")
        with zipfile.ZipFile(zip_file_path, "r") as zf:
            zf.extractall(extract_folder)
        
        # Kiểm tra xem zip có chứa 1 thư mục gốc bao ngoài hay không
        target_src = extract_folder
        sub_items = os.listdir(extract_folder)
        if len(sub_items) == 1 and os.path.isdir(os.path.join(extract_folder, sub_items[0])):
            target_src = os.path.join(extract_folder, sub_items[0])
            
        # 3. Ghi đè vào thư mục app
        protected_files = ["drvn_data.db", "__pycache__", ".git", "error.log"]
        for root, dirs, files in os.walk(target_src):
            rel_path = os.path.relpath(root, target_src)
            dest_dir = os.path.join(app_dir, rel_path) if rel_path != "." else app_dir
            os.makedirs(dest_dir, exist_ok=True)
            
            for file in files:
                if file in protected_files:
                    continue
                src_file = os.path.join(root, file)
                dest_file = os.path.join(dest_dir, file)
                try:
                    shutil.copy2(src_file, dest_file)
                except Exception as e:
                    print(f"[Updater] Không thể ghi đè {file}: {e}")

        # Dọn dẹp thư mục tạm
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
            
        return True, "Cập nhật ứng dụng thành công!"
    except Exception as e:
        return False, f"Quá trình tải và cài đặt cập nhật gặp sự cố: {str(e)}"

def restart_app():
    """Khởi động lại ứng dụng sau khi cập nhật"""
    try:
        app_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
        subprocess.Popen([sys.executable, app_file])
        sys.exit(0)
    except Exception as e:
        print("[Updater] Lỗi khởi động lại ứng dụng:", e)

# =============================================================================
# CÁC HÀM TIỆN ÍCH DÀNH CHO QUẢN TRỊ VIÊN (ADMIN CONSOLE)
# =============================================================================

def update_version_manifest(new_ver=None, changelog_list=None, download_url=None):
    """Cập nhật nội dung file version.json"""
    app_dir = os.path.dirname(os.path.abspath(__file__))
    v_path = os.path.join(app_dir, "version.json")
    data = {
        "version": APP_VERSION,
        "name": "Trợ lý Quản lý và Theo dõi Công văn DRVN",
        "release_date": "",
        "description": "Phiên bản phát hành chính thức dành cho cán bộ Cục Đường bộ Việt Nam.",
        "changelog": [],
        "download_url": ""
    }
    if os.path.exists(v_path):
        try:
            with open(v_path, "r", encoding="utf-8") as f:
                data.update(json.load(f))
        except Exception:
            pass

    if new_ver:
        data["version"] = str(new_ver).lstrip('vV').strip()
    if changelog_list is not None:
        data["changelog"] = changelog_list
    if download_url is not None:
        data["download_url"] = normalize_download_url(download_url)
    
    from datetime import date
    data["release_date"] = date.today().isoformat()
    
    with open(v_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    rel_dir = os.path.join(os.path.expanduser("~"), "Downloads", "TroLyCongVan_DRVN_Release")
    if os.path.exists(rel_dir):
        try:
            with open(os.path.join(rel_dir, "version.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
            
    return data

def create_release_package(new_ver, changelog_list=None, download_url=None):
    """
    Đóng gói toàn bộ mã nguồn sạch ra Desktop cho Quản trị viên.
    Tuyệt đối không kèm database, thông tin tài khoản cá nhân hoặc file rác.
    """
    app_dir = os.path.dirname(os.path.abspath(__file__))
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.exists(desktop):
        desktop = app_dir
        
    new_ver = str(new_ver).lstrip('vV').strip()
    
    # 1. Cập nhật version.json trước khi nén
    update_version_manifest(new_ver=new_ver, changelog_list=changelog_list, download_url=download_url)
    
    # 2. Tạo file ZIP
    zip_name = f"TroLyCongVan_DRVN_v{new_ver}.zip"
    zip_path = os.path.join(desktop, zip_name)
    
    exclude_files = {
        "drvn_data.db", "error.log", "debug_crawler.py",
        "convert_ico.py", "generate_icon.py",
        "doc_progress_page.html", "logged_in_page.html"
    }
    exclude_dirs = {"__pycache__", ".git", ".idea", ".vscode", "scratch"}

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(app_dir):
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                for file in files:
                    if file in exclude_files or file.endswith(".pyc") or file.endswith(".zip") or file.endswith(".log"):
                        continue
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, app_dir)
                    zf.write(full_path, rel_path)

        size_kb = os.path.getsize(zip_path) / 1024
        
        down_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.exists(down_dir):
            try:
                shutil.copy2(zip_path, os.path.join(down_dir, zip_name))
            except Exception:
                pass
                
        return {
            "ok": True,
            "zip_path": zip_path,
            "zip_name": zip_name,
            "size_kb": size_kb,
            "version": new_ver,
            "message": f"Đã đóng gói thành công bản phát hành v{new_ver} ({size_kb:.1f} KB) ra Desktop!"
        }
    except Exception as e:
        return {
            "ok": False,
            "zip_path": "",
            "zip_name": "",
            "size_kb": 0,
            "version": new_ver,
            "message": f"Lỗi đóng gói: {str(e)}"
        }

def test_remote_url(url, is_manifest=True):
    """
    Kiểm tra link Google Drive hoặc web server từ xa.
    Trả về: (ok: bool, message: str, data: dict)
    """
    if not url or not url.strip():
        return False, "Chưa nhập đường link kiểm tra.", None
        
    direct_url = normalize_download_url(url.strip())
    session = requests.Session()
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
