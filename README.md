================================================================================
   HỆ THỐNG TRỢ LÝ QUẢN LÝ VÀ THEO DÕI CÔNG VĂN - CỤC ĐƯỜNG BỘ VIỆT NAM (DRVN)
                 PHIÊN BẢN SẠCH v1.0.0 (DÀNH CHO TRIỂN KHAI MÁY MỚI)
================================================================================

1. TỔNG QUAN TÍNH NĂNG ĐÃ TRIỂN KHAI
------------------------------------
- BẢNG ĐIỀU KHIỂN CHUYÊN NGHIỆP:
  + Thanh điều hướng dọc (Sidebar): 
    * ⚡ Thông báo nhanh
    * 📥 Công văn đến
    * 📤 Công văn đi
    * 🎯 Theo dõi nhiệm vụ (MỚI)
    * ⚙️ Cấu hình
    * 🛠️ Quản trị viên ⭐ (Chỉ hiển thị khi đăng nhập tài khoản Admin)
- HỆ THỐNG THEO DÕI & ĐÔN ĐỐC NHIỆM VỤ (nhiemvu.drvn.gov.vn):
  + Đồng bộ dữ liệu giám sát tiến độ theo thời gian thực từ Supabase API.
  + Tab 1 - "📊 Tổng quan (Dashboard)":
    * 5 Thẻ chỉ số KPI: Tổng nhiệm vụ, Đang thực hiện, Đã hoàn thành, Quá hạn, Sắp đến hạn.
    * Thanh tiến độ Tỷ lệ hoàn thành toàn Cục.
    * Bảng phân bổ nhiệm vụ theo từng Đơn vị / Phòng ban.
    * Bảng nhiệm vụ trọng tâm cần đôn đốc gấp (nhấp đúp để tra cứu chi tiết tức thì).
  + Tab 2 - "📋 Danh sách nhiệm vụ":
    * Bộ lọc nâng cao: Tìm kiếm từ khóa, Đơn vị chủ trì, Trạng thái, Mức độ ưu tiên.
    * Bảng chi tiết 9 cột với huy hiệu trực quan (Đang thực hiện, Đã hoàn thành, Quá hạn, Hỏa tốc/Khẩn).
    * Khung hiển thị chi tiết tiến độ, người thực hiện, nguồn giao và báo cáo gần nhất.
- THÔNG BÁO NHANH & HUY HIỆU TRỰC QUAN:
  + Tự động phân loại 3 nhóm văn bản:
    * ⚡ Phải xử lý (Có thời hạn giải quyết cụ thể)
    * 👁️ Để biết & lưu (Công văn thông báo, báo cáo, chỉ đạo phối hợp)
    * 📂 Lưu chung (Công văn lưu chung đơn vị)
  + Bóc tách độc lập: Chuyên viên xử lý chính & Chuyên viên phối hợp.
- XEM TRỰC TIẾP TỆP ĐÍNH KÈM & CHỮ KÝ SỐ:
  + Tích hợp bộ đọc PDF siêu tốc nội bộ: hiển thị 100% chữ ký số, ngày ký và con dấu đỏ.
  + Liệt kê danh sách đầy đủ tất cả các tệp đính kèm; chỉ mở đọc khi nhấp vào tệp.
  + Hỗ trợ lưu nhanh tệp về máy tính hoặc mở đọc bằng trình duyệt Chrome/Edge.
- ĐA DẠNG HÌNH THỨC CẢNH BÁO:
  + Cảnh báo qua âm thanh chuông Windows.
  + Cửa sổ thông báo nổi (Toast Notification) ở góc dưới màn hình.
  + Tùy chọn ghim thông báo nổi cho đến khi người dùng quay lại máy tính và xác nhận.
  + Đẩy thông báo tức thì về điện thoại qua Bot Telegram cá nhân.
- TRUNG TÂM QUẢN TRỊ VIÊN & CẬP NHẬT GOOGLE DRIVE TỰ ĐỘNG:
  + Tích hợp tab Quản trị viên trực tiếp trong giao diện: đóng gói code sạch 1-click ra Desktop và đồng bộ liên kết Google Drive trong vài giây.

================================================================================
2. HƯỚNG DẪN TRIỂN KHAI TRÊN MÁY TÍNH CÁ NHÂN KHÁC (TỪNG BƯỚC)
================================================================================

BƯỚC 1: SAO CHÉP THƯ MỤC SANG MÁY TÍNH MỚI
------------------------------------------
- Bạn có thể sao chép thư mục "TroLyCongVan_DRVN" hoặc file "TroLyCongVan_DRVN_v1.0.0.zip"
  sang máy tính mới qua USB, Zalo, Google Drive,...
- Nếu là file ZIP, hãy giải nén ra một thư mục cố định trên máy (khuyến nghị để tại 
  ổ D:\TroLyCongVan_DRVN hoặc C:\TroLyCongVan_DRVN để tránh bị xóa nhầm).

BƯỚC 2: YÊU CẦU TIÊN QUYẾT - CÀI ĐẶT PYTHON
--------------------------------------------
- Ứng dụng yêu cầu máy tính có cài đặt Python (phiên bản 3.10 trở lên).
- Nếu máy tính mới chưa có Python:
  1. Vào trang chính thức: https://www.python.org/downloads/
  2. Tải và chạy file cài đặt Python.
  3. ⚠️ QUAN TRỌNG NHẤT: Ở màn hình cài đặt đầu tiên, bạn PHẢI TÍCH CHỌN ô:
     [x] "Add Python to PATH" (ở dưới cùng cửa sổ).
  4. Bấm "Install Now" và đợi cài xong.

BƯỚC 3: CÀI ĐẶT MÔI TRƯỜNG & THƯ VIỆN TỰ ĐỘNG
---------------------------------------------
- Trong thư mục ứng dụng, hãy nhấp đúp chuột vào file:
  👉 "Cai_Dat_Moi_Truong.bat"
- Cửa sổ màu đen sẽ xuất hiện và tự động kiểm tra, tải các thư viện cần thiết:
  + PyQt6 (Giao diện ứng dụng)
  + pymupdf (Bộ đọc PDF & giải mã con dấu/chữ ký số)
  + requests (Kết nối mạng & API)
  + beautifulsoup4 (Bóc tách dữ liệu công văn)
- Tiến trình tải và cài đặt sẽ hiển thị trực tiếp. Khi hoàn tất, cửa sổ sẽ thông báo
  "🎉 HOÀN TẤT CÀI ĐẶT 100%! TẤT CẢ THƯ VIỆN ĐÃ SẴN SÀNG."
- Nhấn Enter để đóng cửa sổ.

BƯỚC 4: KHỞI ĐỘNG ỨNG DỤNG
---------------------------
- Nhấp đúp vào file:
  👉 "Chay_Tro_Ly_Cong_Van.bat"
- Giao diện Trợ lý Công văn DRVN sẽ khởi động và sẵn sàng làm việc!

BƯỚC 5: THIẾT LẬP KHỞI ĐỘNG CÙNG WINDOWS (TÙY CHỌN)
----------------------------------------------------
- Nếu bạn muốn ứng dụng tự động chạy ngầm mỗi khi bật máy tính:
  Nhấp đúp vào file:
  👉 "Khoi_Dong_Cung_Windows.bat"
- Ứng dụng sẽ tự động thu nhỏ xuống khay đồng hồ ở góc phải màn hình và âm thầm
  canh công văn mới cho bạn.

================================================================================
3. CẤU HÌNH TÀI KHOẢN KHI BẮT ĐẦU SỬ DỤNG
================================================================================
- Vào tab "⚙️ Cấu hình" (bên thanh điều hướng trái):
  1. Mục 1: Nhập Tên đăng nhập & Mật khẩu hệ thống Quản lý công văn (congvan.drvn.gov.vn).
     Bấm "🔑 ĐĂNG NHẬP & KIỂM TRA KẾT NỐI".
  2. Mục 2: Chọn thư mục lưu nhanh tệp PDF đính kèm (mặc định là thư mục Downloads của máy).
  3. Mục 3: Nhập Email & Mật khẩu Hệ thống theo dõi nhiệm vụ (nhiemvu.drvn.gov.vn).
     Bấm "🔑 ĐĂNG NHẬP & KẾT NỐI HỆ THỐNG NHIỆM VỤ".
  4. Mục 4: (Tùy chọn) Bật âm thanh thông báo, thông báo nổi hoặc cài đặt Telegram Bot.
  5. Bấm nút "💾 LƯU TOÀN BỘ CẤU HÌNH".
- Ngay sau đó, ứng dụng sẽ quét dữ liệu và hiển thị đầy đủ công văn, nhiệm vụ của bạn!

================================================================================
4. DANH MỤC CÁC TỆP TRONG BỘ SẢN PHẨM
================================================================================
1.  main.py                    : Mã nguồn chính của giao diện ứng dụng.
2.  db.py                      : Quản lý CSDL SQLite nội bộ & dữ liệu mẫu nhiệm vụ.
3.  nhiemvu.py                 : Module kết nối API Supabase của nhiemvu.drvn.gov.vn.
4.  crawler.py                 : Module đăng nhập & bóc tách dữ liệu congvan.drvn.gov.vn.
5.  notifier.py                : Module phát âm thanh, thông báo nổi & Telegram bot.
6.  updater.py                 : Module cập nhật phần mềm từ xa qua Google Drive.
7.  admin_update_tool.py       : Công cụ dành cho Quản trị viên quản lý bản phát hành.
8.  requirements.txt           : Danh sách thư viện Python cần thiết.
9.  setup_env.py               : Trình kiểm tra & cài đặt môi trường trực quan.
10. Cai_Dat_Moi_Truong.bat     : Phím tắt 1-click cài đặt môi trường.
11. Chay_Tro_Ly_Cong_Van.bat   : Phím tắt 1-click khởi động ứng dụng.
12. Khoi_Dong_Cung_Windows.bat : Phím tắt đăng ký tự khởi động cùng máy tính.
13. Quan_Tri_Cap_Nhat.bat      : Phím tắt mở công cụ Quản trị viên.
14. icon.ico, icon.png         : Bộ biểu tượng ứng dụng DRVN.
15. version.json               : Tệp thông tin phiên bản & nhật ký cập nhật.
16. Huong_Dan_Su_Dung.txt      : Hướng dẫn sử dụng & triển khai máy mới.
17. README.md                  : Tài liệu hướng dẫn định dạng Markdown.
================================================================================
