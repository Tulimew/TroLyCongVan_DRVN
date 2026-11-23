import os
import sys
import json
import zipfile
import shutil
import re
import requests

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")

def clean_input(prompt):
    try:
        return input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\nĐã hủy.")
        sys.exit(0)

def convert_gdrive_url(url):
    """Trích xuất file_id từ Google Drive và tạo link tải trực tiếp"""
    if not url:
        return ""
    url = url.strip()
    match = re.search(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)', url)
    if not match:
        match = re.search(r'drive\.google\.com/(?:open|uc)\?(?:.*&)?id=([a-zA-Z0-9_-]+)', url)
    if not match:
        match = re.search(r'id=([a-zA-Z0-9_-]+)', url)
    if match:
        fid = match.group(1)
        return f"https://drive.google.com/uc?export=download&id={fid}"
    return url

def test_gdrive_url(url):
    """Kiểm tra quyền truy cập của file Google Drive"""
    direct_url = convert_gdrive_url(url)
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    try:
        r = session.get(direct_url, timeout=10, allow_redirects=True)
        if "accounts.google.com" in r.url:
            return False, "❌ File đang ở chế độ Riêng tư (Private). Bạn cần đổi quyền chia sẻ sang 'Bất kỳ ai có đường liên kết'."
        if r.status_code == 200:
            return True, "✅ Link Google Drive hợp lệ và công khai (Public)."
        else:
            return False, f"⚠️ Google trả về mã HTTP {r.status_code}."
    except Exception as e:
        return False, f"❌ Lỗi kết nối: {str(e)}"

def action_create_package():
    """Đóng gói phiên bản mới sạch 100% ra Desktop"""
    print("\n" + "="*70)
    print("📦 ĐÓNG GÓI PHIÊN BẢN CẬP NHẬT MỚI (CHO QUẢN TRỊ VIÊN)")
    print("="*70)
    
    # Đọc version hiện tại
    v_path = os.path.join(APP_DIR, "version.json")
    cur_ver = "1.0.0"
    if os.path.exists(v_path):
        try:
            with open(v_path, "r", encoding="utf-8") as f:
                cur_ver = json.load(f).get("version", "1.0.0")
        except Exception:
            pass
            
    print(f"Phiên bản hiện tại trong hệ thống: v{cur_ver}")
    new_ver = clean_input(f"Nhập số phiên bản mới cần phát hành (VD: 1.0.1) [Enter để giữ {cur_ver}]: ")
    if not new_ver:
        new_ver = cur_ver
    new_ver = new_ver.lstrip('vV').strip()
    
    print("\nNhập các nội dung nâng cấp chính (Enter sau mỗi dòng, gõ 'xong' để kết thúc):")
    changelog = []
    while True:
        line = clean_input(f" - Nội dung #{len(changelog)+1} (hoặc 'xong'): ")
        if not line or line.lower() == "xong":
            break
        changelog.append(line)
        
    if not changelog:
        changelog = [f"Bản cập nhật nâng cấp và tối ưu hóa hệ thống v{new_ver}"]

    # Cập nhật version.json
    from datetime import date
    v_data = {
        "version": new_ver,
        "name": "Trợ lý Quản lý và Theo dõi Công văn DRVN",
        "release_date": date.today().isoformat(),
        "description": f"Phiên bản cập nhật v{new_ver} dành cho cán bộ Cục Đường bộ Việt Nam.",
        "changelog": changelog,
        "download_url": ""
    }
    with open(v_path, "w", encoding="utf-8") as f:
        json.dump(v_data, f, ensure_ascii=False, indent=2)
        
    print(f"\n✅ Đã cập nhật file: {v_path}")

    # Tạo file ZIP ra Desktop
    zip_name = f"TroLyCongVan_DRVN_v{new_ver}.zip"
    zip_desktop_path = os.path.join(DESKTOP, zip_name)
    
    exclude_items = {
        "drvn_data.db", "__pycache__", ".git", "error.log",
        "debug_crawler.py", "convert_ico.py", "generate_icon.py",
        "doc_progress_page.html", "logged_in_page.html"
    }

    print(f"\n⏳ Đang nén file mã nguồn sạch...")
    with zipfile.ZipFile(zip_desktop_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(APP_DIR):
            # Lọc bỏ thư mục tạm
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
            for file in files:
                if file in exclude_items or file.endswith(".pyc") or file.endswith(".zip"):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, APP_DIR)
                zf.write(full_path, rel_path)

    file_size_kb = os.path.getsize(zip_desktop_path) / 1024
    print("="*70)
    print(f"🎉 ĐÓNG GÓI THÀNH CÔNG GÓI CẬP NHẬT!")
    print(f"📁 Đường dẫn file ZIP: {zip_desktop_path}")
    print(f"📊 Kích thước siêu nhẹ: {file_size_kb:.1f} KB")
    print("="*70)
    print("👉 TIẾP THEO:")
    print("1. Tải file ZIP này lên Google Drive.")
    print("2. Lấy link chia sẻ Google Drive ('Bất kỳ ai có đường liên kết').")
    print("3. Chọn chức năng số [2] dưới menu để tự động điền link vào file version.json.")

def action_configure_gdrive_links():
    """Hỗ trợ cấu hình link Google Drive vào version.json"""
    print("\n" + "="*70)
    print("🔗 CẤU HÌNH LINK GOOGLE DRIVE VÀO FILE version.json")
    print("="*70)
    
    v_path = os.path.join(APP_DIR, "version.json")
    if not os.path.exists(v_path):
        print("❌ Không tìm thấy file version.json!")
        return

    with open(v_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Phiên bản đang quản lý: v{data.get('version', '1.0.0')}")
    print(f"Link tải hiện tại: {data.get('download_url', '(Chưa có)')}")
    print("\nHãy dán link chia sẻ Google Drive của file ZIP (ví dụ: https://drive.google.com/file/d/.../view?usp=sharing)")
    raw_zip_link = clean_input("Dán link file ZIP tại đây: ")
    
    if raw_zip_link:
        direct_zip = convert_gdrive_url(raw_zip_link)
        print(f"\n🔍 Đang kiểm tra quyền truy cập file trên Google Drive...")
        ok, msg = test_gdrive_url(direct_zip)
        print(msg)
        
        data["download_url"] = direct_zip
        with open(v_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ ĐÃ CẬP NHẬT THÀNH CÔNG VÀO version.json!")
        print(f"Đường dẫn tải trực tiếp: {direct_zip}")
        print("\n👉 BƯỚC CUỐI CÙNG:")
        print("Bây giờ bạn chỉ cần tải file 'version.json' này lên thư mục Google Drive của bạn.")
        print("Sau đó lấy link chia sẻ của file 'version.json' để gửi cho đồng nghiệp (hoặc dán vào phần mềm)!")

def action_test_version_json_link():
    """Kiểm tra link Google Drive của version.json"""
    print("\n" + "="*70)
    print("🔍 KIỂM TRA ĐƯỜNG DẪN CẬP NHẬT TỪ XA CỦA version.json")
    print("="*70)
    raw_v_link = clean_input("Dán link chia sẻ Google Drive của file 'version.json' tại đây: ")
    if not raw_v_link:
        return
        
    direct_v = convert_gdrive_url(raw_v_link)
    print(f"Link trực tiếp: {direct_v}")
    print("Đang kiểm tra kết nối...")
    
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    try:
        r = session.get(direct_v, timeout=12)
        if "accounts.google.com" in r.url:
            print("❌ File 'version.json' đang bị khóa quyền riêng tư!")
            print("👉 Hãy vào Google Drive -> Nhấp chuột phải vào version.json -> Chia sẻ -> Đổi thành 'Bất kỳ ai có đường liên kết'.")
            return
            
        data = r.json()
        print("\n🎉 KẾT NỐI VÀ ĐỌC DỮ LIỆU THÀNH CÔNG!")
        print(f"• Phiên bản remote: v{data.get('version')}")
        print(f"• Ngày phát hành: {data.get('release_date')}")
        print(f"• Link tải zip: {data.get('download_url')}")
        print("\n📋 Nội dung cập nhật:")
        for c in data.get('changelog', []):
            print(f"  + {c}")
        print("\n✅ Link này hoạt động hoàn hảo! Đồng nghiệp có thể dán link này vào phần mềm.")
    except Exception as e:
        print(f"❌ Lỗi đọc file version.json: {e}")

def main():
    while True:
        print("\n" + "="*70)
        print("   QUẢN TRỊ VIÊN - QUẢN LÝ PHÁT HÀNH & CẬP NHẬT TỪ XA QUA GOOGLE DRIVE")
        print("="*70)
        print(" [1] Đóng gói mã nguồn phiên bản mới sạch ra Desktop (ZIP)")
        print(" [2] Cấu hình link Google Drive của file ZIP vào version.json")
        print(" [3] Kiểm tra thử nghiệm link chia sẻ Google Drive của version.json")
        print(" [0] Thoát")
        print("="*70)
        choice = clean_input("Chọn chức năng (0-3): ")
        if choice == "1":
            action_create_package()
        elif choice == "2":
            action_configure_gdrive_links()
        elif choice == "3":
            action_test_version_json_link()
        elif choice == "0":
            print("Tạm biệt!")
            break
        else:
            print("Lựa chọn không hợp lệ. Vui lòng nhập từ 0 đến 3.")

if __name__ == "__main__":
    main()
