"""Release administration for the Windows application."""

import sys

from core import updater
from core.update_signing import initialize_signing_key


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
    }
    while True:
        try:
            print("\n1. Đóng gói và ký bản phát hành")
            print("2. Lưu liên kết tải xuống")
            print("3. Kiểm tra đường dẫn version.json")
            print("0. Thoát")
            choice = input("Chọn chức năng: ").strip()
            if choice == "0":
                return 0
            if choice in actions:
                actions[choice]()
            else:
                print("Vui lòng chọn từ 0 đến 3.")
        except (KeyboardInterrupt, EOFError):
            return 0
        except (OSError, ValueError) as error:
            print(f"Không thể hoàn tất thao tác: {error}")


if __name__ == "__main__":
    sys.exit(main())
