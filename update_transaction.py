"""Validate update contents and restore the prior files if installation fails."""

import json
import os
import re
import shutil
import stat
import zipfile
from pathlib import Path


RECOVERY_DIR = ".update-recovery"
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
_MAX_EXTRACTED_BYTES = 128 * 1024 * 1024
_MAX_FILES = 512
_ROOT_FILES = {
    "main.py", "logger.py", "admin_update_tool.py", "setup_env.py", "update_transaction.py",
    "requirements.txt", "version.json", "README.md", "Huong_Dan_Su_Dung.txt",
    "Cai_Dat_Moi_Truong.bat", "Chay_Tro_Ly_Cong_Van.bat", "Khoi_Dong_Cung_Windows.bat",
    "Khoi_Dong_Tro_Ly_Cong_Van.vbs", "Mo_Bang_Dieu_Khien.bat", "Quan_Tri_Cap_Nhat.bat",
    "icon.png", "icon.ico",
}
_MODULE_PATH = re.compile(r"(?:core|ui)/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\.py")
_DEVICE = re.compile(r"(?:CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])", re.I)


def is_managed_file(name):
    if name in _ROOT_FILES:
        return True
    return bool(_MODULE_PATH.fullmatch(name)) and not any(
        part == "__pycache__" or _DEVICE.fullmatch(part.split(".")[0])
        for part in name.split("/")
    )


def _checked_path(root, name):
    path = root
    for part in name.split("/"):
        path = path / part
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise OSError(f"Đường dẫn chứa liên kết hoặc điểm nối: {name}")
    return path


def _stage_package(archive, stage, expected_version):
    names = set()
    paths = []
    with zipfile.ZipFile(archive) as package:
        entries = package.infolist()
        if len(entries) > _MAX_FILES or sum(entry.file_size for entry in entries) > _MAX_EXTRACTED_BYTES:
            raise ValueError("Gói cập nhật vượt giới hạn số lượng hoặc dung lượng tệp.")
        for entry in entries:
            name = entry.filename
            if (
                entry.orig_filename != name
                or not is_managed_file(name)
                or name.casefold() in names
                or stat.S_ISLNK(entry.external_attr >> 16)
            ):
                raise ValueError(f"Tệp không hợp lệ trong gói cập nhật: {name}")
            names.add(name.casefold())
            paths.append(name)
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(entry) as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
            if target.suffix == ".py":
                compile(target.read_bytes(), name, "exec")
    if not {"main.py", "version.json"} <= set(paths):
        raise ValueError("Gói cập nhật thiếu tệp ứng dụng hoặc version.json.")
    metadata = json.loads((stage / "version.json").read_text(encoding="utf-8"))
    if metadata["version"] != expected_version:
        raise ValueError("Phiên bản bên trong gói đã ký không khớp phiên bản được công bố.")
    return paths


def _rollback(app_dir, recovery, records):
    for name, existed in reversed(records):
        # A file still in staging was never swapped in. Its old copy may be locked.
        if (recovery / "stage" / name).exists():
            continue
        target = _checked_path(app_dir, name)
        if existed:
            backup = _checked_path(recovery, f"backup/{name}")
            restore = recovery / "restore.tmp"
            shutil.copy2(backup, restore)
            os.replace(restore, target)
        else:
            target.unlink(missing_ok=True)
    (recovery / "journal.json").unlink()


def recover_interrupted_update(app_dir):
    app_dir = Path(app_dir)
    recovery = _checked_path(app_dir, RECOVERY_DIR)
    if not recovery.exists():
        return False
    journal = _checked_path(recovery, "journal.json")
    if journal.exists():
        records = json.loads(journal.read_text(encoding="utf-8"))
        if not isinstance(records, list) or any(
            not isinstance(record, list) or len(record) != 2
            or not isinstance(record[0], str) or not is_managed_file(record[0])
            or type(record[1]) is not bool
            for record in records
        ):
            raise ValueError("Nhật ký khôi phục bản cập nhật bị hỏng.")
        _rollback(app_dir, recovery, records)
        shutil.rmtree(recovery, ignore_errors=True)
        return True
    shutil.rmtree(recovery, ignore_errors=True)
    return False


def install_package(app_dir, archive, expected_version):
    """Install a previously authenticated ZIP using on-disk backups and atomic file swaps."""
    app_dir = Path(app_dir)
    recovery = app_dir / RECOVERY_DIR
    recovery.mkdir()
    journal = recovery / "journal.json"
    try:
        stage = recovery / "stage"
        paths = _stage_package(archive, stage, expected_version)
        records = []
        for name in paths:
            target = _checked_path(app_dir, name)
            existed = target.exists()
            if existed:
                backup = recovery / "backup" / name
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
            records.append([name, existed])

        pending = recovery / "journal.tmp"
        with pending.open("x", encoding="utf-8") as stream:
            json.dump(records, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, journal)

        try:
            for name, _ in records:
                target = _checked_path(app_dir, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage / name, target)
            journal.unlink()
        except Exception:
            try:
                _rollback(app_dir, recovery, records)
            except Exception as error:
                raise RuntimeError(
                    "Chưa khôi phục được toàn bộ bản cũ. Ứng dụng sẽ thử lại ở lần mở tiếp theo."
                ) from error
            raise
    finally:
        if not journal.exists():
            shutil.rmtree(recovery, ignore_errors=True)
