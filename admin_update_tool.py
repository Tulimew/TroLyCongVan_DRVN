"""Release administration for the Windows application."""

import argparse
import os
import sys
import webbrowser
from getpass import getpass
from pathlib import Path
from zipfile import BadZipFile

import requests

from core import updater, windows_credentials
from core.github_release import GitHubRelease, prepare_draft
from core.update_signing import PUBLIC_KEY_NAME, initialize_signing_key


def action_create_github_draft(ref=None, version=None, notes_file=None, open_draft=False):
    app_dir = Path(updater.APP_DIR)
    ref = ref or input("Nhánh hoặc commit GitHub để phát hành [main]: ").strip() or "main"
    if not (app_dir / PUBLIC_KEY_NAME).exists():
        answer = input("Máy này chưa có khóa ký. Khởi tạo khóa ký phát hành trên máy này? [c/K]: ")
        if answer.strip().casefold() not in ("c", "có", "y", "yes"):
            raise ValueError("Cần khóa ký của nhóm phát hành trước khi tạo bản nháp.")
        path = initialize_signing_key(app_dir)
        print(f"Đã tạo khóa công khai để phân phối qua kênh tin cậy: {path}")

    db_path = app_dir / "drvn_data.db"
    token = os.getenv("GH_TOKEN", "").strip() or windows_credentials.read(db_path, "github_release_token")
    entered_token = not token
    if entered_token:
        token = getpass("Nhập token GitHub của repo này (Contents: Read and write): ").strip()
        if not token:
            raise ValueError("Cần token GitHub để tạo bản nháp và tải tệp.")
    notes = Path(notes_file).read_text(encoding="utf-8") if notes_file else None
    output_dir = updater.release_manifest_path().parent / "GitHub"
    with requests.Session() as session:
        url = prepare_draft(GitHubRelease(session, token), app_dir, output_dir, ref,
                            version=version, notes=notes)
    print(f"Đã xác minh ZIP và version.json trên Release nháp. Mở để duyệt: {url}")
    if open_draft:
        webbrowser.open(url)
    if entered_token:
        answer = input("Lưu token vào Windows Credential Manager cho lần sau? [c/K]: ")
        if answer.strip().casefold() in ("c", "có", "y", "yes"):
            windows_credentials.write(db_path, "github_release_token", token)


def action_create_package():
    print(f"Phiên bản đang cài: v{updater.APP_VERSION}")
    version = input("Phiên bản cần phát hành (x.y.z): ").strip()
    if not version:
        return
    print("Nhập nội dung cập nhật, mỗi mục một dòng. Dòng trống để kết thúc.")
    changelog = []
    while line := input(" - ").strip():
        changelog.append(line)
    result = updater.create_release_package(version, changelog)
    print(result["message"])
    if result["ok"]:
        print(f"Gói đã ký: {result['zip_path']}")
        print(f"Tệp thông tin phát hành: {result['manifest_path']}")
        print("Tải ZIP lên máy chủ HTTPS, điền liên kết ở mục 2 rồi tải version.json lên.")


def action_configure_gdrive_links():
    url = input("Liên kết HTTPS của gói cập nhật đã ký: ").strip()
    if not url:
        return
    updater.update_version_manifest(download_url=url)
    print(f"Đã lưu liên kết vào {updater.release_manifest_path()}")


def action_test_version_json_link():
    url = input("Liên kết HTTPS của version.json: ").strip()
    if url:
        _, message, _ = updater.test_remote_url(url)
        print(message)


def main():
    if "--create-draft" in sys.argv[1:]:
        parser = argparse.ArgumentParser(description="Tạo bản cập nhật và tải lên GitHub Release nháp.")
        parser.add_argument("--create-draft", action="store_true")
        parser.add_argument("--ref", help="Nhánh hoặc commit GitHub chứa phiên bản phát hành.")
        parser.add_argument("--version", help="Đối chiếu với số phiên bản trong commit đã chọn.")
        parser.add_argument("--notes-file", help="Đường dẫn tệp ghi chú phát hành UTF-8.")
        parser.add_argument("--open", action="store_true", help="Mở bản nháp trong trình duyệt sau khi xác minh.")
        args = parser.parse_args()
        try:
            action_create_github_draft(args.ref, args.version, args.notes_file, args.open)
        except (OSError, ValueError, BadZipFile, requests.RequestException) as error:
            print(f"Không thể hoàn tất bản nháp: {error}", file=sys.stderr)
            return 1
        except (KeyboardInterrupt, EOFError):
            return 1
        return 0

    if sys.argv[1:] == ["--init-signing-key"]:
        try:
            path = initialize_signing_key(updater.APP_DIR)
        except (OSError, ValueError) as error:
            print(f"Không thể khởi tạo khóa ký: {error}", file=sys.stderr)
            return 1
        print(f"Khóa công khai để phân phối: {path}")
        return 0

    actions = {
        "1": action_create_package,
        "2": action_configure_gdrive_links,
        "3": action_test_version_json_link,
        "4": action_create_github_draft,
    }
    while True:
        try:
            print("\n1. Đóng gói và ký bản phát hành")
            print("2. Lưu liên kết tải xuống")
            print("3. Kiểm tra đường dẫn version.json")
            print("4. Tạo bản cập nhật và tải lên GitHub Release nháp")
            print("0. Thoát")
            choice = input("Chọn chức năng: ").strip()
            if choice == "0":
                return 0
            if choice in actions:
                actions[choice]()
            else:
                print("Vui lòng chọn từ 0 đến 4.")
        except (KeyboardInterrupt, EOFError):
            return 0
        except (OSError, ValueError, BadZipFile, requests.RequestException) as error:
            print(f"Không thể hoàn tất thao tác: {error}")


if __name__ == "__main__":
    sys.exit(main())
