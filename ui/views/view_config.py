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
    QProgressBar, QComboBox, QCompleter
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QDate, QPointF, QStringListModel
from PyQt6.QtGui import QIcon, QColor, QFont, QAction, QPixmap, QImage
import pymupdf

from core import db, notifier, updater, nhiemvu
from core.crawler import DRVNCrawler
from logger import log

APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ICON_PATH = os.path.join(APP_DIR, "icon.png")

class ConfigViewMixin:
    def init_view_config(self):
        root = QVBoxLayout(self.view_config)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 14, 14, 24)
        layout.setSpacing(14)

        # 1. KHAI BÁO TÀI KHOẢN & ĐĂNG NHẬP
        grp_auth = QGroupBox("1. KHAI BÁO TÀI KHOẢN & TRẠNG THÁI ĐĂNG NHẬP (congvan.drvn.gov.vn)")
        grp_auth.setStyleSheet("QGroupBox { font-weight: bold; color: #0284c7; }")
        form_auth = QFormLayout(grp_auth)

        # Thẻ trạng thái kết nối
        u_saved = db.get_setting("username", "")
        if u_saved:
            self.lbl_auth_status = QLabel(f"🟢 ĐÃ LƯU TÀI KHOẢN ({u_saved})")
            self.lbl_auth_status.setStyleSheet("color: #16a34a; font-size: 13px; font-weight: bold;")
            self.lbl_auth_msg = QLabel("Hệ thống đã lưu thông tin. Bấm Đăng nhập để kiểm tra hoặc làm mới phiên.")
        else:
            self.lbl_auth_status = QLabel("⚪ CHƯA KẾT NỐI")
            self.lbl_auth_status.setStyleSheet("color: #dc2626; font-size: 13px; font-weight: bold;")
            self.lbl_auth_msg = QLabel("Vui lòng nhập tài khoản và mật khẩu hệ thống Quản lý công văn DRVN.")
        self.lbl_auth_msg.setStyleSheet("color: #64748b; font-size: 12px;")

        self.txt_username = QLineEdit(u_saved)
        self.txt_password = QLineEdit(db.get_setting("password", ""))
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)

        self.chk_show_pass = QCheckBox("Hiển thị mật khẩu (kiểm tra Unikey)")
        self.chk_show_pass.stateChanged.connect(lambda: self.txt_password.setEchoMode(
            QLineEdit.EchoMode.Normal if self.chk_show_pass.isChecked() else QLineEdit.EchoMode.Password
        ))

        self.txt_officer_name = QLineEdit(db.get_officer_name())
        self.txt_officer_name.setPlaceholderText("VD: Tăng Tuấn Linh (dùng để lọc công văn cá nhân)")

        self.txt_task_department = QLineEdit(db.get_setting("task_department"))
        self.txt_task_department.setPlaceholderText("Chọn hoặc nhập tên đơn vị chủ trì")
        self.task_department_model = QStringListModel(self)
        completer = QCompleter(self.task_department_model, self.txt_task_department)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.txt_task_department.setCompleter(completer)

        btn_login = QPushButton("🔑 ĐĂNG NHẬP & KIỂM TRA KẾT NỐI")
        btn_login.setStyleSheet("background: #0284c7; color: white; padding: 8px 18px; border-radius: 4px; font-weight: bold;")
        btn_login.clicked.connect(self.action_login)

        form_auth.addRow("Trạng thái:", self.lbl_auth_status)
        form_auth.addRow("", self.lbl_auth_msg)
        form_auth.addRow("Tên đăng nhập:", self.txt_username)
        form_auth.addRow("Mật khẩu:", self.txt_password)
        form_auth.addRow("", self.chk_show_pass)
        form_auth.addRow("Họ và tên cán bộ:", self.txt_officer_name)
        form_auth.addRow("Tên phòng:", self.txt_task_department)
        form_auth.addRow("", btn_login)
        layout.addWidget(grp_auth)

        # 2. KHỞI ĐỘNG CÙNG WINDOWS & THƯ MỤC LƯU NHANH
        grp_system = QGroupBox("2. KHỞI ĐỘNG CÙNG WINDOWS & THƯ MỤC TỆP ĐÍNH KÈM")
        grp_system.setStyleSheet("QGroupBox { font-weight: bold; color: #16a34a; }")
        form_system = QFormLayout(grp_system)

        self.chk_autostart = QCheckBox("Tự động khởi động cùng Windows khi bật máy tính (chạy ngầm dưới khay đồng hồ)")
        self.chk_autostart.setStyleSheet("font-size: 13px; font-weight: bold; color: #0284c7;")
        self.chk_autostart.setChecked(self.is_autostart_enabled())
        self.chk_autostart.setToolTip("Khi bật máy tính, Trợ lý Công văn sẽ tự động khởi động ẩn để luôn sẵn sàng theo dõi và cảnh báo công văn kịp thời.")

        default_fld = db.get_setting("save_folder", db.DEFAULT_SAVE_FOLDER)
        self.txt_save_folder = QLineEdit(default_fld)

        btn_browse_fld = QPushButton("📁 Chọn thư mục...")
        btn_browse_fld.clicked.connect(self.action_browse_save_folder)
        btn_open_fld = QPushButton("📂 Mở thư mục")
        btn_open_fld.clicked.connect(self.action_open_save_folder)

        fld_box = QHBoxLayout()
        fld_box.addWidget(self.txt_save_folder)
        fld_box.addWidget(btn_browse_fld)
        fld_box.addWidget(btn_open_fld)

        form_system.addRow("Khởi động hệ thống:", self.chk_autostart)
        form_system.addRow("Thư mục lưu tệp:", fld_box)
        layout.addWidget(grp_system)

        # 3. CẤU HÌNH TÀI KHOẢN HỆ THỐNG THEO DÕI NHIỆM VỤ (nhiemvu.drvn.gov.vn)
        grp_nhiemvu = QGroupBox("3. CẤU HÌNH TÀI KHOẢN HỆ THỐNG THEO DÕI NHIỆM VỤ (nhiemvu.drvn.gov.vn)")
        grp_nhiemvu.setStyleSheet("QGroupBox { font-weight: bold; color: #0284c7; }")
        form_nv = QFormLayout(grp_nhiemvu)

        nv_email_saved = db.get_setting("nhiemvu_email", "")
        if nv_email_saved:
            self.lbl_nv_auth_status = QLabel(f"🟢 ĐÃ LƯU TÀI KHOẢN NHIỆM VỤ ({nv_email_saved})")
            self.lbl_nv_auth_status.setStyleSheet("color: #16a34a; font-size: 13px; font-weight: bold;")
        else:
            self.lbl_nv_auth_status = QLabel("⚪ CHƯA KẾT NỐI HỆ THỐNG NHIỆM VỤ")
            self.lbl_nv_auth_status.setStyleSheet("color: #dc2626; font-size: 13px; font-weight: bold;")

        self.txt_nhiemvu_email = QLineEdit(nv_email_saved)
        self.txt_nhiemvu_email.setPlaceholderText("Nhập email tài khoản tại nhiemvu.drvn.gov.vn (VD: email@gttm.vn)")

        self.txt_nhiemvu_password = QLineEdit(db.get_setting("nhiemvu_password", ""))
        self.txt_nhiemvu_password.setEchoMode(QLineEdit.EchoMode.Password)

        self.chk_show_nv_pass = QCheckBox("Hiển thị mật khẩu nhiệm vụ")
        self.chk_show_nv_pass.toggled.connect(
            lambda checked: self.txt_nhiemvu_password.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)
        )

        box_nv_actions = QHBoxLayout()
        btn_login_nv = QPushButton("🔑 ĐĂNG NHẬP & KẾT NỐI HỆ THỐNG NHIỆM VỤ")
        btn_login_nv.setStyleSheet("background: #0284c7; color: white; padding: 8px 18px; border-radius: 4px; font-weight: bold;")
        btn_login_nv.clicked.connect(self.action_login_nhiemvu)

        btn_open_nv_web = QPushButton("🌐 MỞ TRANG WEB (nhiemvu.drvn.gov.vn)")
        btn_open_nv_web.setStyleSheet("background: #0369a1; color: white; padding: 8px 18px; border-radius: 4px; font-weight: bold;")
        btn_open_nv_web.clicked.connect(lambda: webbrowser.open("https://nhiemvu.drvn.gov.vn/dashboard"))

        box_nv_actions.addWidget(btn_login_nv)
        box_nv_actions.addWidget(btn_open_nv_web)
        box_nv_actions.addStretch()

        form_nv.addRow("Trạng thái:", self.lbl_nv_auth_status)
        form_nv.addRow("Email đăng nhập:", self.txt_nhiemvu_email)
        form_nv.addRow("Mật khẩu:", self.txt_nhiemvu_password)
        form_nv.addRow("", self.chk_show_nv_pass)
        form_nv.addRow("", box_nv_actions)
        layout.addWidget(grp_nhiemvu)

        # 4. TẦN SUẤT QUÉT, CẢNH BÁO & TELEGRAM
        grp_tele = QGroupBox("4. CẤU HÌNH CẢNH BÁO, TẦN SUẤT QUÉT & TELEGRAM")
        grp_tele.setStyleSheet("QGroupBox { font-weight: bold; color: #d97706; }")
        form_tele = QFormLayout(grp_tele)

        self.spin_warning_days = QSpinBox()
        self.spin_warning_days.setRange(1, 30)
        self.spin_warning_days.setValue(db.get_warning_days())
        self.spin_warning_days.setSuffix(" ngày")

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 60)
        self.spin_interval.setValue(int(db.get_setting("interval_min", "2")))
        self.spin_interval.setSuffix(" phút")

        self.txt_tg_token = QLineEdit(db.get_setting("telegram_token", ""))
        self.txt_tg_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_tg_chatid = QLineEdit(db.get_setting("telegram_chat_id", ""))

        self.chk_enable_tg = QCheckBox("Gửi cảnh báo công văn mới về Telegram")
        self.chk_enable_tg.setChecked(db.get_setting("enable_telegram", "1") == "1")

        self.chk_enable_sound = QCheckBox("Phát âm thanh chuông báo trên máy tính")
        self.chk_enable_sound.setChecked(db.get_setting("enable_sound", "1") == "1")

        self.chk_enable_toast = QCheckBox("Hiện thông báo nổi góc màn hình Windows")
        self.chk_enable_toast.setChecked(db.get_setting("enable_toast", "1") == "1")

        self.chk_keep_toast = QCheckBox("Ghim thông báo trên màn hình cho đến khi xem (Không tự tắt khi vắng mặt)")
        self.chk_keep_toast.setChecked(db.get_setting("keep_toast", "1") == "1")

        btn_test_tg = QPushButton("🧪 Thử nghiệm gửi thông báo ngay")
        btn_test_tg.clicked.connect(self.action_test_notification)

        btn_save_all_cfg = QPushButton("💾 LƯU TOÀN BỘ CẤU HÌNH")
        btn_save_all_cfg.setStyleSheet("background: #16a34a; color: white; padding: 10px 24px; font-weight: bold; border-radius: 6px;")
        btn_save_all_cfg.clicked.connect(self.action_save_all_config)

        form_tele.addRow("Cảnh báo trước khi hết hạn:", self.spin_warning_days)
        form_tele.addRow("Tần suất quét ngầm:", self.spin_interval)
        form_tele.addRow("Bot Token Telegram:", self.txt_tg_token)
        form_tele.addRow("Chat ID Telegram:", self.txt_tg_chatid)
        form_tele.addRow("", self.chk_enable_tg)
        form_tele.addRow("", self.chk_enable_sound)
        form_tele.addRow("", self.chk_enable_toast)
        form_tele.addRow("", self.chk_keep_toast)
        form_tele.addRow("", btn_test_tg)
        form_tele.addRow("", btn_save_all_cfg)
        layout.addWidget(grp_tele)

        # 5. CẬP NHẬT PHẦN MỀM TỪ XA
        grp_update = QGroupBox("5. CẬP NHẬT PHẦN MỀM TỪ XA (REMOTE UPDATE)")
        grp_update.setStyleSheet("QGroupBox { font-weight: bold; color: #7c3aed; }")
        form_update = QFormLayout(grp_update)

        self.lbl_current_ver = QLabel(f"Phiên bản đang cài đặt: v{updater.APP_VERSION}")
        self.lbl_current_ver.setStyleSheet("font-weight: bold; color: #0284c7; font-size: 13px;")

        self.txt_update_url = QLineEdit(db.get_setting("update_url", ""))
        self.txt_update_url.setPlaceholderText("Dán link Google Drive hoặc web server chứa file version.json")

        btn_check_update = QPushButton("🔄 KIỂM TRA BẢN CẬP NHẬT MỚI")
        btn_check_update.setStyleSheet("background: #7c3aed; color: white; padding: 8px 18px; border-radius: 4px; font-weight: bold;")
        btn_check_update.clicked.connect(self.action_check_remote_update)

        form_update.addRow("Phiên bản hiện tại:", self.lbl_current_ver)
        form_update.addRow("URL máy chủ cập nhật:", self.txt_update_url)
        form_update.addRow("", btn_check_update)
        layout.addWidget(grp_update)

        # 6. DÀNH CHO QUẢN TRỊ VIÊN
        grp_admin_unlock = QGroupBox("6. DÀNH CHO QUẢN TRỊ VIÊN HỆ THỐNG")
        grp_admin_unlock.setStyleSheet("QGroupBox { font-weight: bold; color: #a855f7; }")
        layout_adm_btn = QHBoxLayout(grp_admin_unlock)
        self.btn_toggle_admin = QPushButton("🔐 Đăng nhập chế độ Quản trị viên (Admin Mode)")
        self.btn_toggle_admin.setStyleSheet("background: #6b21a8; color: white; padding: 7px 15px; border-radius: 4px; font-weight: bold;")
        self.btn_toggle_admin.clicked.connect(self.action_unlock_admin)
        layout_adm_btn.addWidget(self.btn_toggle_admin)
        layout_adm_btn.addStretch()
        layout.addWidget(grp_admin_unlock)

        layout.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll)

    def action_login(self):
        u = self.txt_username.text().strip()
        p = self.txt_password.text().strip()
        if not u or not p:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập Tên đăng nhập và Mật khẩu!")
            return

        db.set_setting("username", u)
        db.set_setting("password", p)
        if hasattr(self, "txt_officer_name"):
            db.set_setting("officer_name", self.txt_officer_name.text().strip())

        self.lbl_auth_status.setText("🟡 ĐANG KẾT NỐI VÀ ĐĂNG NHẬP VÀO DRVN...")
        self.lbl_auth_status.setStyleSheet("color: #d97706; font-size: 13px; font-weight: bold;")
        self.lbl_auth_msg.setText("Đang gửi yêu cầu xác thực tới hệ thống...")
        QApplication.processEvents()

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        ok = self.crawler.login(u, p)
        QApplication.restoreOverrideCursor()

        if ok:
            self.lbl_auth_status.setText(f"🟢 ĐÃ ĐĂNG NHẬP THÀNH CÔNG (Tài khoản: {u})")
            self.lbl_auth_status.setStyleSheet("color: #16a34a; font-size: 13px; font-weight: bold;")
            self.lbl_auth_msg.setText("Kết nối thông suốt! Đang đồng bộ toàn bộ dữ liệu công văn...")
            self.update_user_header()
            self.check_and_update_admin_status(u)
            role_note = " (Quyền Quản trị viên - Admin)" if self.is_admin else ""
            QMessageBox.information(self, "Thành công", f"✅ ĐĂNG NHẬP THÀNH CÔNG!\n\nTài khoản: {u}{role_note}\nPhần mềm sẽ tự động quét và tải dữ liệu mới nhất.")
            self.start_background_scan()
        else:
            self.lbl_auth_status.setText("🔴 ĐĂNG NHẬP THẤT BẠI")
            self.lbl_auth_status.setStyleSheet("color: #dc2626; font-size: 13px; font-weight: bold;")
            self.lbl_auth_msg.setText(f"Phản hồi từ máy chủ: {self.crawler.last_error}")
            self.check_and_update_admin_status(u)
            QMessageBox.warning(self, "Thất bại", f"❌ Không thể đăng nhập.\nLý do: {self.crawler.last_error}")

    def action_browse_save_folder(self):
        current = self.txt_save_folder.text().strip()
        fld = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu nhanh công văn", current)
        if fld:
            self.txt_save_folder.setText(fld)
            db.set_setting("save_folder", fld)

    def action_open_save_folder(self):
        fld = self.txt_save_folder.text().strip()
        if os.path.exists(fld):
            os.startfile(fld)
        else:
            os.makedirs(fld, exist_ok=True)
            os.startfile(fld)

    def action_test_notification(self):
        if self.chk_enable_sound.isChecked():
            notifier.play_alert_chime()

        sample_doc = {
            "id": "sample_test_doc",
            "so_den": "30488",
            "so_ky_hieu": "18699/BXD-KHTC",
            "ngay_ban_hanh": "20/11/2026",
            "trich_yeu": "V/v phối hợp rà soát tiến độ xử lý văn bản và dự thảo thông tư hướng dẫn công tác vận tải đường bộ",
            "ngay_den": "20/11/2026",
            "han_xu_ly": "24/11/2026",
            "chi_dao": "Lãnh đạo Cục chỉ đạo khẩn trương xử lý",
            "lanh_dao_cuc": "Lãnh đạo Cục",
            "lanh_dao_phong": "Lãnh đạo Phòng",
            "xu_ly_chinh": "Chuyên viên thụ lý",
            "phoi_hop": "",
            "scope": "personal"
        }

        # Hiển thị cửa sổ thông báo nổi góc màn hình
        if self.chk_enable_toast.isChecked():
            self.show_floating_incoming_alert(sample_doc)

        if self.chk_enable_tg.isChecked():
            token = self.txt_tg_token.text().strip()
            chat_id = self.txt_tg_chatid.text().strip()
            db.set_setting("telegram_token", token)
            db.set_setting("telegram_chat_id", chat_id)
            notifier.send_telegram_alert("🧪 *THỬ NGHIỆM THÀNH CÔNG!*\n\nCảnh báo công văn Cục Đường bộ Việt Nam đã kết nối với Telegram của bạn!")
            QMessageBox.information(self, "Thông báo", "Đã gửi thử nghiệm qua Chuông loa, Cửa sổ thông báo nổi trên màn hình và Telegram! Hãy kiểm tra màn hình và điện thoại của bạn.")

    def is_autostart_enabled(self):
        """Kiểm tra xem ứng dụng đã được đăng ký khởi động cùng Windows hay chưa"""
        try:
            startup_dir = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
            lnk_path = os.path.join(startup_dir, "TroLyCongVan_DRVN.lnk")
            return os.path.exists(lnk_path)
        except Exception:
            return False

    def set_autostart_enabled(self, enable=True):
        """Bật/tắt tự động khởi động cùng Windows thông qua thư mục Startup"""
        try:
            startup_dir = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
            lnk_path = os.path.join(startup_dir, "TroLyCongVan_DRVN.lnk")
            if enable:
                app_dir = APP_DIR
                bat_path = os.path.join(app_dir, "Chay_Tro_Ly_Cong_Van.bat")
                ico_path = os.path.join(app_dir, "icon.ico")
                vbs_code = (
                    f'Set ws = CreateObject("WScript.Shell")\n'
                    f'Set s = ws.CreateShortcut("{lnk_path}")\n'
                    f's.TargetPath = "{bat_path}"\n'
                    f's.WorkingDirectory = "{app_dir}"\n'
                    f's.IconLocation = "{ico_path}"\n'
                    f's.Save\n'
                )
                vbs_tmp = os.path.join(tempfile.gettempdir(), "_create_lnk.vbs")
                with open(vbs_tmp, "w", encoding="utf-8") as f:
                    f.write(vbs_code)
                subprocess.run(["wscript.exe", vbs_tmp], capture_output=True)
                if os.path.exists(vbs_tmp):
                    try:
                        os.remove(vbs_tmp)
                    except Exception:
                        pass
                return os.path.exists(lnk_path)
            else:
                if os.path.exists(lnk_path):
                    try:
                        os.remove(lnk_path)
                    except Exception:
                        pass
                return not os.path.exists(lnk_path)
        except Exception:
            return False

    def action_save_all_config(self):
        db.set_setting("save_folder", self.txt_save_folder.text().strip())
        db.set_setting("interval_min", str(self.spin_interval.value()))
        db.set_setting("warning_days", str(self.spin_warning_days.value()))
        db.set_setting("telegram_token", self.txt_tg_token.text().strip())
        db.set_setting("telegram_chat_id", self.txt_tg_chatid.text().strip())
        db.set_setting("enable_telegram", "1" if self.chk_enable_tg.isChecked() else "0")
        db.set_setting("enable_sound", "1" if self.chk_enable_sound.isChecked() else "0")
        db.set_setting("enable_toast", "1" if self.chk_enable_toast.isChecked() else "0")
        db.set_setting("keep_toast", "1" if self.chk_keep_toast.isChecked() else "0")
        if hasattr(self, "txt_officer_name"):
            db.set_setting("officer_name", self.txt_officer_name.text().strip())
            self.update_user_header()
        department = self.txt_task_department.text().strip()
        if department != db.get_setting("task_department"):
            db.set_setting("task_department", department)
            self.chk_task_department.blockSignals(True)
            self.chk_task_department.setChecked(bool(department))
            self.chk_task_department.blockSignals(False)
        if hasattr(self, "txt_update_url"):
            db.set_setting("update_url", self.txt_update_url.text().strip())
        if hasattr(self, "txt_nhiemvu_email"):
            db.set_setting("nhiemvu_email", self.txt_nhiemvu_email.text().strip())
        if hasattr(self, "txt_nhiemvu_password"):
            db.set_setting("nhiemvu_password", self.txt_nhiemvu_password.text().strip())

        # Cập nhật cấu hình khởi động cùng Windows
        autostart_msg = ""
        if hasattr(self, "chk_autostart"):
            want_autostart = self.chk_autostart.isChecked()
            self.set_autostart_enabled(want_autostart)
            db.set_setting("autostart", "1" if want_autostart else "0")
            autostart_msg = f"• Khởi động cùng Windows: {'BẬT (Tự chạy ẩn khi mở máy)' if want_autostart else 'TẮT'}\n"

        self.timer.setInterval(self.spin_interval.value() * 60 * 1000)
        db.recalculate_urgency()
        self.refresh_all_data()
        QMessageBox.information(
            self, "Thành công",
            f"✅ Đã lưu toàn bộ cấu hình hệ thống!\n\n"
            f"{autostart_msg}"
            f"• Cảnh báo sắp quá hạn: ≤ {self.spin_warning_days.value()} ngày\n"
            f"• Tần suất quét ngầm: {self.spin_interval.value()} phút\n"
            f"• Thư mục lưu file: {self.txt_save_folder.text().strip()}"
        )

    def action_check_remote_update(self):
        url = self.txt_update_url.text().strip()
        db.set_setting("update_url", url)
        if not url:
            QMessageBox.information(
                self, "Cập nhật phần mềm từ xa",
                "ℹ️ CHƯA THIẾT LẬP ĐƯỜNG DẪN CẬP NHẬT TỪ XA\n\n"
                "Để sử dụng tính năng cập nhật tự động:\n"
                "1. Quản trị viên tải file 'version.json' và file zip bản cập nhật lên Google Drive (hoặc GitHub, máy chủ nội bộ).\n"
                "2. Sao chép liên kết chia sẻ của file 'version.json' trên Google Drive (quyền 'Bất kỳ ai có đường liên kết').\n"
                "3. Dán link vào ô 'URL máy chủ cập nhật' ở trên và bấm 'Lưu cấu hình'.\n"
                "Khi có phiên bản mới, phần mềm sẽ tự động phát hiện và nâng cấp chỉ với 1 click!"
            )
            return

        self.status_bar.showMessage("Đang kiểm tra bản cập nhật mới từ xa...")
        res = updater.check_for_updates(url)
        if res.get("status") == "update_available":
            changelog_lines = res.get("changelog", [])
            ch_str = "\n".join(f"• {c}" for c in changelog_lines) if changelog_lines else res.get("description", "")
            msg = f"🎉 ĐÃ CÓ BẢN CẬP NHẬT MỚI: v{res['remote_version']}!\n" \
                  f"(Phiên bản đang cài đặt: v{res['current_version']})\n\n" \
                  f"📋 Nội dung cập nhật:\n{ch_str}\n\n" \
                  f"Bạn có muốn tải xuống và cài đặt tự động ngay bây giờ không?\n" \
                  f"(Lưu ý: Dữ liệu công văn và tài khoản của bạn sẽ được bảo lưu an toàn 100%)"
            reply = QMessageBox.question(self, "Bản cập nhật mới", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                d_url = res.get("download_url", "").strip()
                if not d_url:
                    QMessageBox.warning(self, "Thông báo", "Bản cập nhật này chưa kèm link tải file tự động. Vui lòng liên hệ quản trị viên.")
                    return
                self.status_bar.showMessage("Đang tải và tiến hành nâng cấp...")
                ok, up_msg = updater.download_and_install_update(
                    d_url, res["remote_version"], res.get("package_signature", "")
                )
                if ok:
                    QMessageBox.information(self, "Cập nhật hoàn tất", "✅ Nâng cấp thành công! Ứng dụng sẽ khởi động lại ngay bây giờ.")
                    updater.restart_app()
                else:
                    QMessageBox.critical(self, "Lỗi cập nhật", f"❌ Không thể hoàn tất cập nhật:\n{up_msg}")
        elif res.get("status") == "up_to_date":
            QMessageBox.information(self, "Kiểm tra cập nhật", f"✅ {res['message']}")
        else:
            QMessageBox.warning(self, "Thông báo cập nhật", res.get("message", "Không thể kiểm tra."))
        self.status_bar.showMessage("Sẵn sàng hoạt động.")

