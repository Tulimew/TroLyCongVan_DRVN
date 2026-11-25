import sys
import subprocess
import importlib.util

REQUIRED_PACKAGES = [
    ("PyQt6", "PyQt6>=6.4.0", "Giao diện đồ họa người dùng (GUI)"),
    ("pymupdf", "pymupdf>=1.23.0", "Trình đọc PDF siêu tốc & con dấu/chữ ký số"),
    ("requests", "requests>=2.28.0", "Giao thức kết nối & đồng bộ dữ liệu mạng"),
    ("bs4", "beautifulsoup4>=4.11.0", "Bộ phân tích bóc tách công văn"),
    ("cryptography", "cryptography>=44,<49", "Xác minh chữ ký gói cập nhật"),
]

def check_package(module_name):
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False

def install_package(pip_name, desc):
    print(f"\n👉 [ĐANG TẢI & CÀI ĐẶT] {pip_name} ({desc})...")
    cmd = [sys.executable, "-m", "pip", "install", pip_name, "--progress-bar", "on"]
    try:
        res = subprocess.run(cmd)
        return res.returncode == 0
    except Exception as e:
        print(f"Lỗi: {e}")
        return False

def main():
    print("=" * 72)
    print("   KIỂM TRA & CÀI ĐẶT MÔI TRƯỜNG - TRỢ LÝ CÔNG VĂN CỤC ĐƯỜNG BỘ VN")
    print("=" * 72)
    print(f"• Đường dẫn Python : {sys.executable}")
    print(f"• Phiên bản Python : {sys.version.split()[0]}\n")

    print("--- 1. Kiểm tra các thư viện trên máy tính ---")
    missing = []
    for mod, pkg, desc in REQUIRED_PACKAGES:
        if check_package(mod):
            print(f"  ✅ [ĐÃ CÓ SẴN] {pkg:<24} - {desc}")
        else:
            print(f"  ⏳ [CHƯA CÓ]   {pkg:<24} - {desc}")
            missing.append((mod, pkg, desc))

    if not missing:
        print("\n" + "=" * 72)
        print("  🎉 MÁY TÍNH ĐÃ CÓ ĐẦY ĐỦ TẤT CẢ THƯ VIỆN CẦN THIẾT (100%)!")
        print("  👉 Bạn có thể nhấp đúp 'Chay_Tro_Ly_Cong_Van.bat' để mở ứng dụng ngay.")
        print("=" * 72)
        input("\nNhấn phím Enter để đóng...")
        return

    print(f"\n--- 2. Đang tiến hành tải và cài đặt {len(missing)} thư viện còn thiếu ---")
    print("Vui lòng đợi trong giây lát, tiến trình tải và phần trăm (%) sẽ hiển thị trực tiếp bên dưới:")
    
    success = True
    for mod, pkg, desc in missing:
        ok = install_package(pkg, desc)
        if not ok:
            print(f"\n❌ Cài đặt thất bại gói: {pkg}")
            success = False
        else:
            print(f"✅ Hoàn tất cài đặt gói: {pkg}")

    print("\n" + "=" * 72)
    if success:
        print("  🎉 HOÀN TẤT CÀI ĐẶT 100%! TẤT CẢ THƯ VIỆN ĐÃ SẴN SÀNG.")
        print("  👉 Bây giờ bạn có thể nhấp đúp 'Chay_Tro_Ly_Cong_Van.bat' để làm việc.")
    else:
        print("  ⚠️ Có thư viện chưa thể cài đặt do lỗi kết nối mạng.")
        print("  Vui lòng kiểm tra lại đường truyền Internet và chạy lại file này.")
    print("=" * 72)
    input("\nNhấn phím Enter để hoàn tất và đóng cửa sổ...")

if __name__ == "__main__":
    main()
