import os
import re
import webbrowser
import tempfile
import subprocess
from datetime import datetime, date, timedelta

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QLineEdit, QCheckBox, QSpinBox, QFormLayout, QGroupBox,
    QHeaderView, QMessageBox, QSystemTrayIcon, QMenu, QAbstractItemView,
    QStatusBar, QFrame, QListWidget, QListWidgetItem, QStackedWidget,
    QDateEdit, QFileDialog, QSplitter, QScrollArea, QTextEdit, QInputDialog,
    QProgressBar, QComboBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QDate, QPointF
from PyQt6.QtGui import QIcon, QColor, QFont, QAction, QPixmap, QImage
import pymupdf

from core import db, notifier, updater, nhiemvu
from core.crawler import DRVNCrawler
from logger import log

APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ICON_PATH = os.path.join(APP_DIR, "icon.png")

class AdminViewMixin:
    def init_view_admin(self):
        root = QVBoxLayout(self.view_admin)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(14)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header banner
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4c1d95, stop:1 #1e1b4b);
                border-radius: 8px;
                padding: 12px 18px;
            }
        """)
        hdr_layout = QVBoxLayout(header_frame)
        lbl_adm_title = QLabel("🛠️ TRUNG TÂM QUẢN TRỊ HỆ THỐNG & PHÁT HÀNH CẬP NHẬT (ADMIN CONSOLE)")
        lbl_adm_title.setStyleSheet("color: #e9d5ff; font-size: 15px; font-weight: bold;")
        lbl_adm_sub = QLabel("Chức năng dành riêng cho Quản trị viên: Đóng gói bản phát hành sạch 1-click & Quản lý đồng bộ Google Drive.")
        lbl_adm_sub.setStyleSheet("color: #c4b5fd; font-size: 12px;")
        hdr_layout.addWidget(lbl_adm_title)
        hdr_layout.addWidget(lbl_adm_sub)
        layout.addWidget(header_frame)

        # 1. ĐÓNG GÓI & PHÁT HÀNH BẢN MỚI
        grp_package = QGroupBox("1. ĐÓNG GÓI BẢN PHÁT HÀNH MỚI (1-CLICK PACKAGING)")
        grp_package.setStyleSheet("QGroupBox { font-weight: bold; color: #7c3aed; }")
        form_pack = QFormLayout(grp_package)

        self.lbl_adm_cur_ver = QLabel(f"v{updater.APP_VERSION}")
        self.lbl_adm_cur_ver.setStyleSheet("font-weight: bold; color: #0284c7; font-size: 13px;")

        cur_tuple = updater.parse_version_tuple(updater.APP_VERSION)
        next_ver_suggest = f"{cur_tuple[0]}.{cur_tuple[1]}.{cur_tuple[2] + 1}"
        self.txt_admin_new_ver = QLineEdit(next_ver_suggest)
        self.txt_admin_new_ver.setPlaceholderText("VD: 1.0.1")

        self.txt_admin_changelog = QTextEdit()
        self.txt_admin_changelog.setPlaceholderText(
            "- Tối ưu hóa giao diện và tốc độ tải dữ liệu\n"
            "- Nâng cấp khả năng bóc tách tệp đính kèm và chữ ký số\n"
            "- Cải thiện độ ổn định và bảo mật"
        )
        self.txt_admin_changelog.setMaximumHeight(90)

        btn_pack_release = QPushButton("📦 1-CLICK: ĐÓNG GÓI BẢN PHÁT HÀNH MỚI RA DESKTOP")
        btn_pack_release.setStyleSheet("""
            QPushButton {
                background: #7c3aed; color: white; padding: 10px 20px;
                border-radius: 6px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background: #6d28d9; }
        """)
        btn_pack_release.clicked.connect(self.action_admin_package_release)

        form_pack.addRow("Phiên bản hiện tại:", self.lbl_adm_cur_ver)
        form_pack.addRow("Phiên bản mới phát hành:", self.txt_admin_new_ver)
        form_pack.addRow("Nội dung cập nhật (Changelog):", self.txt_admin_changelog)
        form_pack.addRow("", btn_pack_release)
        layout.addWidget(grp_package)

        # 2. ĐỒNG BỘ GOOGLE DRIVE
        grp_gdrive = QGroupBox("2. ĐỒNG BỘ GOOGLE DRIVE & LIÊN KẾT TẢI VỀ")
        grp_gdrive.setStyleSheet("QGroupBox { font-weight: bold; color: #0284c7; }")
        form_gdrive = QFormLayout(grp_gdrive)

        btn_open_gdrive = QPushButton("🌐 MỞ GOOGLE DRIVE TRÊN TRÌNH DUYỆT (drive.google.com)")
        btn_open_gdrive.setStyleSheet("background: #0284c7; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        btn_open_gdrive.clicked.connect(lambda: webbrowser.open("https://drive.google.com"))

        self.txt_admin_zip_url = QLineEdit()
        self.txt_admin_zip_url.setPlaceholderText("Dán link chia sẻ file ZIP trên Google Drive (quyền 'Bất kỳ ai có đường liên kết')")

        btn_save_zip_url = QPushButton("⚡ Nhận diện & Cập nhật link tải ZIP vào version.json")
        btn_save_zip_url.setStyleSheet("background: #0ea5e9; color: white; padding: 7px 15px; border-radius: 4px; font-weight: bold;")
        btn_save_zip_url.clicked.connect(self.action_admin_save_zip_url)

        self.txt_admin_manifest_url = QLineEdit(db.get_setting("update_url", ""))
        self.txt_admin_manifest_url.setPlaceholderText("Dán link chia sẻ file version.json trên Google Drive")

        box_gdrive_actions = QHBoxLayout()
        btn_test_manifest = QPushButton("🧪 Kiểm tra thử nghiệm link version.json")
        btn_test_manifest.setStyleSheet("background: #10b981; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        btn_test_manifest.clicked.connect(self.action_admin_test_manifest_url)

        btn_save_default_url = QPushButton("💾 LƯU LÀM MÁY CHỦ MẶC ĐỊNH CHO MỌI NGƯỜI DÙNG")
        btn_save_default_url.setStyleSheet("background: #16a34a; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold;")
        btn_save_default_url.clicked.connect(self.action_admin_save_default_url)

        box_gdrive_actions.addWidget(btn_test_manifest)
        box_gdrive_actions.addWidget(btn_save_default_url)
        box_gdrive_actions.addStretch()

        form_gdrive.addRow("Thao tác nhanh:", btn_open_gdrive)
        form_gdrive.addRow("Link Google Drive của file ZIP:", self.txt_admin_zip_url)
        form_gdrive.addRow("", btn_save_zip_url)
        form_gdrive.addRow("Link Google Drive của version.json:", self.txt_admin_manifest_url)
        form_gdrive.addRow("", box_gdrive_actions)
        layout.addWidget(grp_gdrive)

        # 3. QUẢN LÝ PHÂN QUYỀN VÀ BẢO MẬT ADMIN
        grp_security = QGroupBox("3. QUẢN LÝ PHÂN QUYỀN ADMIN & BẢO MẬT")
        grp_security.setStyleSheet("QGroupBox { font-weight: bold; color: #ea580c; }")
        form_sec = QFormLayout(grp_security)

        self.txt_admin_users = QLineEdit(db.get_setting("admin_usernames", "tcdb.linhtt,admin"))
        self.txt_admin_users.setPlaceholderText("Danh sách tài khoản có quyền Admin, cách nhau bởi dấu phẩy")

        self.txt_admin_pin = QLineEdit(db.get_setting("admin_pin", "admin@drvn"))
        self.txt_admin_pin.setEchoMode(QLineEdit.EchoMode.Password)

        box_sec_actions = QHBoxLayout()
        btn_save_sec = QPushButton("💾 Lưu cấu hình bảo mật")
        btn_save_sec.setStyleSheet("background: #ea580c; color: white; padding: 7px 16px; border-radius: 4px; font-weight: bold;")
        btn_save_sec.clicked.connect(self.action_admin_save_security_settings)

        btn_lock_session = QPushButton("🔒 Khóa phiên Quản trị (Ẩn tab Quản trị)")
        btn_lock_session.setStyleSheet("background: #64748b; color: white; padding: 7px 16px; border-radius: 4px; font-weight: bold;")
        btn_lock_session.clicked.connect(self.action_lock_admin)

        box_sec_actions.addWidget(btn_save_sec)
        box_sec_actions.addWidget(btn_lock_session)
        box_sec_actions.addStretch()

        form_sec.addRow("Tài khoản có quyền Quản trị:", self.txt_admin_users)
        form_sec.addRow("Mã PIN bảo mật Quản trị viên:", self.txt_admin_pin)
        form_sec.addRow("", box_sec_actions)
        layout.addWidget(grp_security)

        layout.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll)

    def refresh_admin_view(self):
        """Làm mới dữ liệu trên giao diện Quản trị viên"""
        if hasattr(self, "lbl_adm_cur_ver"):
            self.lbl_adm_cur_ver.setText(f"v{updater.APP_VERSION}")
        if hasattr(self, "txt_admin_manifest_url"):
            self.txt_admin_manifest_url.setText(db.get_setting("update_url", ""))
        v_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.json")
        if os.path.exists(v_path):
            try:
                import json
                with open(v_path, "r", encoding="utf-8") as f:
                    v_data = json.load(f)
                    d_url = v_data.get("download_url", "")
                    if hasattr(self, "txt_admin_zip_url") and d_url and not self.txt_admin_zip_url.text().strip():
                        self.txt_admin_zip_url.setText(d_url)
                    ch = v_data.get("changelog", [])
                    if hasattr(self, "txt_admin_changelog") and not self.txt_admin_changelog.toPlainText().strip():
                        if isinstance(ch, list) and ch:
                            self.txt_admin_changelog.setPlainText("\n".join(f"- {c}" for c in ch))
            except Exception:
                pass

    def action_admin_package_release(self):
        """Thực hiện đóng gói phiên bản mới ra Desktop sạch 100%"""
        new_ver = self.txt_admin_new_ver.text().strip()
        if not new_ver:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập số phiên bản mới (ví dụ: 1.0.1)!")
            return

        raw_ch = self.txt_admin_changelog.toPlainText().strip()
        changelog_list = []
        for line in raw_ch.split("\n"):
            line = line.strip().lstrip("-*• ")
            if line:
                changelog_list.append(line)

        if not changelog_list:
            changelog_list = [f"Bản cập nhật nâng cấp tính năng và tối ưu hóa hệ thống v{new_ver}"]

        zip_url = self.txt_admin_zip_url.text().strip()

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.status_bar.showMessage("Đang đóng gói mã nguồn sạch ra Desktop...")
        res = updater.create_release_package(new_ver, changelog_list, download_url=zip_url)
        QApplication.restoreOverrideCursor()

        if res.get("ok"):
            zip_path = res.get("zip_path")
            size_kb = res.get("size_kb", 0)
            msg = (
                f"🎉 ĐÃ ĐÓNG GÓI THÀNH CÔNG BẢN PHÁT HÀNH v{new_ver}!\n\n"
                f"• Vị trí file: {zip_path}\n"
                f"• Dung lượng siêu nhẹ: {size_kb:.1f} KB\n"
                f"• Đảm bảo sạch 100%: Đã loại trừ toàn bộ dữ liệu cá nhân, log và database.\n\n"
                f"Bạn có muốn MỞ NGAY file ZIP trên Desktop và Google Drive trên trình duyệt để tải lên không?"
            )
            reply = QMessageBox.question(self, "Đóng gói thành công", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                webbrowser.open("https://drive.google.com")
                desktop_fld = os.path.dirname(zip_path)
                try:
                    import subprocess
                    subprocess.Popen(f'explorer /select,"{zip_path}"')
                except Exception:
                    os.startfile(desktop_fld)
            self.refresh_admin_view()
        else:
            QMessageBox.critical(self, "Lỗi đóng gói", f"❌ Không thể đóng gói:\n{res.get('message')}")
        self.status_bar.showMessage("Sẵn sàng hoạt động.")

    def action_admin_save_zip_url(self):
        """Chuẩn hóa và ghi đè link tải ZIP vào version.json"""
        raw_url = self.txt_admin_zip_url.text().strip()
        if not raw_url:
            QMessageBox.warning(self, "Thiếu liên kết", "Vui lòng dán link Google Drive của file ZIP!")
            return

        direct_url = updater.normalize_download_url(raw_url)
        self.status_bar.showMessage("Đang kiểm tra kết nối Google Drive...")
        ok, msg, data = updater.test_remote_url(direct_url, is_manifest=False)
        self.status_bar.showMessage("Sẵn sàng hoạt động.")

        if not ok:
            QMessageBox.warning(self, "Cảnh báo Google Drive", f"⚠️ Kiểm tra kết nối phát hiện sự cố:\n\n{msg}\n\nBạn hãy đảm bảo file ZIP đã được bật quyền 'Bất kỳ ai có đường liên kết'.")
            return

        updater.update_version_manifest(download_url=direct_url)
        self.txt_admin_zip_url.setText(direct_url)
        QMessageBox.information(
            self, "Cập nhật thành công",
            f"✅ ĐÃ LƯU LINK TẢI ZIP VÀO version.json!\n\n"
            f"• Link trực tiếp: {direct_url}\n\n"
            f"👉 BƯỚC TIẾP THEO:\n"
            f"Tải file 'version.json' lên cùng thư mục Google Drive của bạn, sau đó lấy link chia sẻ của file 'version.json' dán vào ô bên dưới."
        )

    def action_admin_test_manifest_url(self):
        """Kiểm tra link version.json trên Google Drive"""
        raw_url = self.txt_admin_manifest_url.text().strip()
        if not raw_url:
            QMessageBox.warning(self, "Thiếu liên kết", "Vui lòng dán link Google Drive của file 'version.json'!")
            return

        self.status_bar.showMessage("Đang kiểm tra file version.json trên Google Drive...")
        ok, msg, data = updater.test_remote_url(raw_url, is_manifest=True)
        self.status_bar.showMessage("Sẵn sàng hoạt động.")

        if ok:
            QMessageBox.information(self, "Kiểm tra thành công", msg)
        else:
            QMessageBox.warning(self, "Kiểm tra thất bại", msg)

    def action_admin_save_default_url(self):
        """Lưu URL máy chủ cập nhật làm mặc định cho toàn bộ người dùng"""
        raw_url = self.txt_admin_manifest_url.text().strip()
        if not raw_url:
            QMessageBox.warning(self, "Thiếu liên kết", "Vui lòng dán link Google Drive của file 'version.json'!")
            return

        direct_url = updater.normalize_download_url(raw_url)
        db.set_setting("update_url", direct_url)
        if hasattr(self, "txt_update_url"):
            self.txt_update_url.setText(direct_url)

        QMessageBox.information(
            self, "Đã lưu làm mặc định",
            f"✅ ĐÃ THIẾT LẬP MÁY CHỦ CẬP NHẬT MẶC ĐỊNH!\n\n"
            f"URL: {direct_url}\n\n"
            f"Từ nay, mọi bản xuất bản phát hành cho đồng nghiệp sẽ tự động kết nối đến máy chủ này mà đồng nghiệp không cần phải cấu hình thêm bất cứ điều gì!"
        )

    def action_admin_save_security_settings(self):
        """Lưu danh sách tài khoản Admin và mã PIN"""
        u_list = self.txt_admin_users.text().strip()
        pin = self.txt_admin_pin.text().strip()
        if not u_list:
            QMessageBox.warning(self, "Cảnh báo", "Danh sách tài khoản Admin không được để trống!")
            return
        if not pin:
            QMessageBox.warning(self, "Cảnh báo", "Mã PIN Quản trị viên không được để trống!")
            return

        db.set_setting("admin_usernames", u_list)
        db.set_setting("admin_pin", pin)
        QMessageBox.information(self, "Thành công", "✅ Đã lưu cấu hình phân quyền Admin và mã PIN bảo mật thành công!")

    def check_and_update_admin_status(self, custom_user=None):
        """Xác định tài khoản hiện tại có quyền Quản trị viên hay không"""
        u = custom_user if custom_user is not None else db.get_setting("username", "")
        u_clean = u.strip().lower()
        admin_raw = db.get_setting("admin_usernames", "tcdb.linhtt,admin")
        admin_list = [x.strip().lower() for x in admin_raw.split(",") if x.strip()]

        is_admin = bool(u_clean and u_clean in admin_list)
        self.set_admin_role(is_admin)

    def set_admin_role(self, is_admin):
        """Bật/tắt chế độ Quản trị viên trên thanh Sidebar"""
        self.is_admin = is_admin
        if hasattr(self, "item_admin"):
            self.item_admin.setHidden(not is_admin)
            if is_admin:
                self.item_admin.setText("🛠️ Quản trị viên ⭐")
                self.item_admin.setForeground(QColor("#a855f7"))
                if hasattr(self, "btn_toggle_admin"):
                    self.btn_toggle_admin.setText("🔓 Đang hoạt động ở chế độ Quản trị viên (Admin)")
                    self.btn_toggle_admin.setStyleSheet("background: #15803d; color: white; padding: 7px 15px; border-radius: 4px; font-weight: bold;")
            else:
                if hasattr(self, "btn_toggle_admin"):
                    self.btn_toggle_admin.setText("🔐 Đăng nhập chế độ Quản trị viên (Admin Mode)")
                    self.btn_toggle_admin.setStyleSheet("background: #6b21a8; color: white; padding: 7px 15px; border-radius: 4px; font-weight: bold;")
                if self.sidebar.currentRow() == 5:
                    self.sidebar.setCurrentRow(0)

    def action_unlock_admin(self):
        """Mở khóa chế độ Quản trị viên bằng mã PIN"""
        if getattr(self, "is_admin", False):
            self.sidebar.setCurrentRow(5)
            return

        pin, ok = QInputDialog.getText(
            self, "Xác thực Quản trị viên",
            "Nhập mã PIN bảo mật của Quản trị viên:\n(Mặc định ban đầu: admin@drvn)",
            QLineEdit.EchoMode.Password
        )
        if ok and pin:
            saved_pin = db.get_setting("admin_pin", "admin@drvn")
            if pin.strip() == saved_pin.strip():
                self.set_admin_role(True)
                self.sidebar.setCurrentRow(5)
                QMessageBox.information(
                    self, "Thành công",
                    "✅ ĐÃ MỞ KHÓA VAI TRÒ QUẢN TRỊ VIÊN!\n\n"
                    "Tab '🛠️ Quản trị viên' đã xuất hiện trên thanh điều hướng bên trái."
                )
            else:
                QMessageBox.warning(self, "Thất bại", "❌ Mã PIN Quản trị viên không chính xác!")

    def action_lock_admin(self):
        """Khóa phiên Quản trị viên"""
        self.set_admin_role(False)
        self.sidebar.setCurrentRow(0)
        QMessageBox.information(self, "Thông báo", "🔒 Đã khóa phiên Quản trị viên. Giao diện trở về chế độ người dùng bình thường.")

