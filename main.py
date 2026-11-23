import sys
import os
import re

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import webbrowser
import ctypes
import tempfile
import traceback
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
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
import pymupdf

import db
from crawler import DRVNCrawler
import notifier
import updater
import nhiemvu

# Bắt lỗi toàn cục để đảm bảo phần mềm không bao giờ bị văng/thoát đột ngột
def handle_global_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    err_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    try:
        log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR:\n{err_str}\n")
    except Exception:
        pass
    if QApplication.instance():
        QMessageBox.critical(None, "Thông báo lỗi", f"Đã xảy ra lỗi:\n{exc_value}\n\n(Chi tiết đã được ghi vào error.log)")

sys.excepthook = handle_global_exception

ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")

# Cửa sổ thông báo nổi (Floating Toast Popup) Always-on-top trên màn hình Windows
class ToastNotification(QWidget):
    def __init__(self, title, message, doc=None, on_click=None, parent=None, is_outgoing=False):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.doc = doc
        self.on_click = on_click
        self.is_outgoing = is_outgoing

        self.setFixedWidth(400)
        border_color = "#16a34a" if is_outgoing else "#0284c7"
        bg_color = "#0f172a"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        container = QFrame(self)
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 2px solid {border_color};
                border-radius: 10px;
            }}
        """)
        root.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # Header bar
        header_box = QHBoxLayout()
        icon_str = "📤" if is_outgoing else "🔔"
        lbl_icon = QLabel(icon_str)
        lbl_icon.setStyleSheet("font-size: 20px; border: none;")

        lbl_title = QLabel(title)
        title_color = "#4ade80" if is_outgoing else "#38bdf8"
        lbl_title.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {title_color}; border: none;")

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(22, 22)
        btn_close.setStyleSheet("""
            QPushButton { background: transparent; color: #94a3b8; font-weight: bold; border: none; font-size: 14px; }
            QPushButton:hover { color: #f43f5e; }
        """)
        btn_close.clicked.connect(self.close)

        header_box.addWidget(lbl_icon)
        header_box.addWidget(lbl_title, 1)
        header_box.addWidget(btn_close)
        layout.addLayout(header_box)

        # Message body
        lbl_msg = QLabel(message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("color: #f8fafc; font-size: 12px; line-height: 1.4; border: none;")
        layout.addWidget(lbl_msg)

        # Buttons
        btn_box = QHBoxLayout()
        btn_text = "📋 Xem chi tiết công văn" if is_outgoing else "📋 Xem chi tiết & Tệp đính kèm"
        btn_view = QPushButton(btn_text)
        btn_style = "#16a34a" if is_outgoing else "#0284c7"
        btn_view.setStyleSheet(f"""
            QPushButton {{
                background: {btn_style}; color: white; font-weight: bold;
                padding: 6px 14px; border-radius: 4px; font-size: 11px; border: none;
            }}
            QPushButton:hover {{ opacity: 0.9; }}
        """)
        btn_view.clicked.connect(self.handle_click)
        btn_box.addWidget(btn_view)
        btn_box.addStretch()
        layout.addLayout(btn_box)

        # Căn góc dưới bên phải màn hình desktop (trên khay taskbar)
        screen = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        x = screen.right() - self.width() - 24
        y = screen.bottom() - self.height() - 24
        self.move(x, y)

        # Tự động ẩn sau 15 giây nếu không bật chế độ Ghim thông báo khi vắng mặt
        keep_toast = (db.get_setting("keep_toast", "1") == "1")
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.close)
        if not keep_toast:
            self.timer.start(15000)

    def handle_click(self):
        self.timer.stop()
        self.close()
        if self.on_click:
            self.on_click(self.doc, self.is_outgoing)

    def enterEvent(self, event):
        self.timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        keep_toast = (db.get_setting("keep_toast", "1") == "1")
        if not keep_toast:
            self.timer.start(4000)
        super().leaveEvent(event)


# Khung cuộn văn bản PDF hỗ trợ cuộn chuột và phóng to/thu nhỏ bằng Ctrl + cuộn chuột
class PDFScrollArea(QScrollArea):
    def __init__(self, zoom_in_callback, zoom_out_callback, parent=None):
        super().__init__(parent)
        self.zoom_in_callback = zoom_in_callback
        self.zoom_out_callback = zoom_out_callback

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0 and self.zoom_in_callback:
                self.zoom_in_callback()
            elif delta < 0 and self.zoom_out_callback:
                self.zoom_out_callback()
            event.accept()
        else:
            super().wheelEvent(event)


# Worker quét dữ liệu chạy nền
class BackgroundWorker(QThread):
    finished_signal = pyqtSignal(str)
    new_doc_signal = pyqtSignal(dict)
    out_update_signal = pyqtSignal(dict)

    def __init__(self, crawler):
        super().__init__()
        self.crawler = crawler
        self.crawler.on_new_personal_doc = self.new_doc_signal.emit
        self.crawler.on_outgoing_status_updated = self.out_update_signal.emit

    def run(self):
        try:
            # Tự động duy trì phiên đăng nhập (tự re-login nếu phiên web hết hạn)
            self.crawler.ensure_logged_in()

            # Quét tất cả các danh mục
            self.crawler.fetch_incoming_docs_personal()
            self.crawler.fetch_incoming_docs_department()
            self.crawler.fetch_outgoing_docs_department()
            self.crawler.fetch_outgoing_docs_personal()
            self.crawler.fetch_outgoing_docs_processing()

            self.finished_signal.emit(f"Cập nhật thành công lúc: {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            self.finished_signal.emit(f"Lỗi quét dữ liệu: {str(e)}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.crawler = DRVNCrawler()
        self.worker = None
        self.selected_doc_for_detail = None
        self.is_admin = False

        self.setWindowTitle("Hệ thống Quản lý & Cảnh báo Công văn - Cục Đường bộ Việt Nam")
        self.resize(1280, 800)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))

        self.init_ui()
        self.check_and_update_admin_status()
        self.init_tray()
        self.init_timer()

        self.center_window()
        self.refresh_all_data()

        # Quét ngầm sau 2 giây
        QTimer.singleShot(2000, self.start_background_scan)

    def center_window(self):
        screen = self.screen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def update_user_header(self):
        u = db.get_setting("username", "")
        officer = db.get_officer_name()
        if hasattr(self, "lbl_sub"):
            if officer and u:
                self.lbl_sub.setText(f"👤 Cán bộ: {officer} ({u})")
            elif u:
                self.lbl_sub.setText(f"👤 Tài khoản: {u}")
            else:
                self.lbl_sub.setText("Hệ thống hỗ trợ quản lý & theo dõi văn bản")

    # =========================================================================
    # GIAO DIỆN CHÍNH (SIDEBAR DỌC TRÁI + NỘI DUNG PHẢI)
    # =========================================================================
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        # 1. TOP HEADER BAR
        top_header = QFrame()
        top_header.setStyleSheet("""
            QFrame {
                background: #0f172a;
                border-radius: 8px;
                padding: 10px 16px;
            }
        """)
        top_layout = QHBoxLayout(top_header)

        title_box = QVBoxLayout()
        lbl_title = QLabel(f"🏛️ HỆ THỐNG QUẢN LÝ VÀ THEO DÕI CÔNG VĂN - CỤC ĐƯỜNG BỘ VIỆT NAM (v{updater.APP_VERSION})")
        lbl_title.setStyleSheet("color: #38bdf8; font-size: 15px; font-weight: bold;")
        self.lbl_sub = QLabel("")
        self.lbl_sub.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.update_user_header()
        title_box.addWidget(lbl_title)
        title_box.addWidget(self.lbl_sub)
        top_layout.addLayout(title_box)

        top_layout.addStretch()

        self.badge_unread = QLabel("📥 Mới chưa đọc: 0")
        self.badge_unread.setStyleSheet("background: #dc2626; color: white; padding: 6px 14px; border-radius: 6px; font-weight: bold;")

        self.badge_urgent = QLabel("⏳ Sắp hết hạn: 0")
        self.badge_urgent.setStyleSheet("background: #d97706; color: white; padding: 6px 14px; border-radius: 6px; font-weight: bold;")

        self.btn_quick_scan = QPushButton("🔄 Quét dữ liệu ngay")
        self.btn_quick_scan.setStyleSheet("""
            QPushButton {
                background: #0284c7; color: white; padding: 7px 18px;
                border-radius: 6px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background: #0369a1; }
        """)
        self.btn_quick_scan.clicked.connect(self.start_background_scan)

        top_layout.addWidget(self.badge_unread)
        top_layout.addWidget(self.badge_urgent)
        top_layout.addWidget(self.btn_quick_scan)
        root_layout.addWidget(top_header)

        # 2. KHUNG NỘI DUNG: SIDEBAR DỌC TRÁI + CONTENT PHẢI
        body_layout = QHBoxLayout()
        body_layout.setSpacing(10)

        # SIDEBAR DỌC BÊN TRÁI
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(210)
        self.sidebar.setStyleSheet("""
            QListWidget {
                background: #1e293b;
                border-radius: 8px;
                padding: 8px;
                border: 1px solid #334155;
            }
            QListWidget::item {
                color: #e2e8f0;
                font-size: 14px;
                font-weight: bold;
                padding: 14px 12px;
                margin-bottom: 6px;
                border-radius: 6px;
            }
            QListWidget::item:hover {
                background: #334155;
            }
            QListWidget::item:selected {
                background: #0284c7;
                color: #ffffff;
            }
        """)

        item1 = QListWidgetItem("⚡ Thông báo nhanh")
        item2 = QListWidgetItem("📥 Công văn đến")
        item3 = QListWidgetItem("📤 Công văn đi")
        item4 = QListWidgetItem("🎯 Theo dõi nhiệm vụ")
        item5 = QListWidgetItem("⚙️ Cấu hình")
        self.item_admin = QListWidgetItem("🛠️ Quản trị viên ⭐")
        self.item_admin.setToolTip("Trung tâm đóng gói bản cập nhật và cấu hình Google Drive dành riêng cho Quản trị viên")

        self.sidebar.addItem(item1)
        self.sidebar.addItem(item2)
        self.sidebar.addItem(item3)
        self.sidebar.addItem(item4)
        self.sidebar.addItem(item5)
        self.sidebar.addItem(self.item_admin)
        self.item_admin.setHidden(True)  # Mặc định ẩn, chỉ hiện khi đăng nhập tài khoản admin!
        self.sidebar.currentRowChanged.connect(self.on_sidebar_changed)
        body_layout.addWidget(self.sidebar)

        # STACKED WIDGET BÊN PHẢI (CHỨA 6 VIEW CHÍNH)
        self.stack = QStackedWidget()

        # View 1: Thông báo nhanh (index 0)
        self.view_quick_alert = QWidget()
        self.init_view_quick_alert()
        self.stack.addWidget(self.view_quick_alert)

        # View 2: Công văn đến (index 1)
        self.view_incoming = QWidget()
        self.init_view_incoming()
        self.stack.addWidget(self.view_incoming)

        # View 3: Công văn đi (index 2)
        self.view_outgoing = QWidget()
        self.init_view_outgoing()
        self.stack.addWidget(self.view_outgoing)

        # View 4: Theo dõi nhiệm vụ (index 3)
        self.view_tasks = QWidget()
        self.init_view_tasks()
        self.stack.addWidget(self.view_tasks)

        # View 5: Cấu hình (index 4)
        self.view_config = QWidget()
        self.init_view_config()
        self.stack.addWidget(self.view_config)

        # View 6: Quản trị viên (index 5)
        self.view_admin = QWidget()
        self.init_view_admin()
        self.stack.addWidget(self.view_admin)

        body_layout.addWidget(self.stack, 1)
        root_layout.addLayout(body_layout)

        # 3. STATUS BAR
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Sẵn sàng hoạt động.")

        # Chọn tab Thông báo nhanh đầu tiên
        self.sidebar.setCurrentRow(0)

    def on_sidebar_changed(self, row):
        if row < 0:
            return
        self.stack.setCurrentIndex(row)
        if row == 0:
            self.refresh_quick_alerts()
        elif row == 1:
            self.apply_incoming_filter_dept()
            self.apply_incoming_filter_personal()
        elif row == 2:
            self.apply_outgoing_filter_dept()
            self.apply_outgoing_filter_personal()
        elif row == 3:
            self.refresh_tasks_view()
        elif row == 5:
            self.refresh_admin_view()

    # =========================================================================
    # VIEW 1: THÔNG BÁO NHANH (KHÔNG CHIA TAB PHỤ - HIỂN THỊ TỔNG QUAN)
    # =========================================================================
    def init_view_quick_alert(self):
        layout = QVBoxLayout(self.view_quick_alert)
        layout.setContentsMargins(4, 0, 4, 4)
        layout.setSpacing(10)

        # KHỐI 1: CÔNG VĂN ĐẾN MỚI CHƯA ĐỌC
        self.grp_new = QGroupBox("📥 1. CẬP NHẬT CÔNG VĂN ĐẾN CÁ NHÂN MỚI (CHƯA ĐỌC)")
        self.grp_new.setStyleSheet("QGroupBox { font-weight: bold; color: #0284c7; }")
        layout_new = QVBoxLayout(self.grp_new)

        self.table_quick_new = QTableWidget()
        self.table_quick_new.setColumnCount(9)
        self.table_quick_new.setHorizontalHeaderLabels([
            "Trạng thái", "Phân loại xử lý", "Số đến", "Số/Ký hiệu", "Ngày đến", "Trích yếu", "Xử lý chính", "Phối hợp", "Hạn xử lý"
        ])
        self.table_quick_new.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table_quick_new.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_quick_new.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_quick_new.doubleClicked.connect(self.on_double_click_quick_new)

        btn_box_new = QHBoxLayout()
        btn_mark_read = QPushButton("✔️ Đánh dấu đã đọc")
        btn_mark_read.clicked.connect(self.mark_quick_new_as_read)
        btn_detail = QPushButton("📋 Xem chi tiết & Tải file")
        btn_detail.clicked.connect(self.open_detail_from_quick_new)
        btn_box_new.addWidget(btn_mark_read)
        btn_box_new.addWidget(btn_detail)
        btn_box_new.addStretch()

        layout_new.addWidget(self.table_quick_new)
        layout_new.addLayout(btn_box_new)
        layout.addWidget(self.grp_new, 2)

        # KHỐI 2: CẢNH BÁO TIẾN ĐỘ & CÔNG VĂN ĐI MỚI (CHIA ĐÔI)
        bottom_split = QHBoxLayout()

        # Khối công văn gần hạn
        self.grp_urgent = QGroupBox(f"⏳ 2. CẢNH BÁO CÔNG VĂN CÁ NHÂN GẦN ĐẾN HẠN (≤ {db.get_warning_days()} NGÀY) & QUÁ HẠN")
        self.grp_urgent.setStyleSheet("QGroupBox { font-weight: bold; color: #d97706; }")
        layout_urgent = QVBoxLayout(self.grp_urgent)

        self.table_quick_urgent = QTableWidget()
        self.table_quick_urgent.setColumnCount(8)
        self.table_quick_urgent.setHorizontalHeaderLabels([
            "Mức độ khẩn", "Phân loại", "Số ngày", "Hạn", "Số đến - Ký hiệu", "Trích yếu", "Xử lý chính", "Phối hợp"
        ])
        self.table_quick_urgent.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table_quick_urgent.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_quick_urgent.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_quick_urgent.doubleClicked.connect(self.on_double_click_quick_urgent)
        layout_urgent.addWidget(self.table_quick_urgent)
        bottom_split.addWidget(self.grp_urgent, 1)

        # Khối công văn đi có cập nhật
        self.grp_out_update = QGroupBox("📤 3. CÔNG VĂN ĐI CÁ NHÂN CÓ CẬP NHẬT (CHUYỂN TRẠNG THÁI)")
        self.grp_out_update.setStyleSheet("QGroupBox { font-weight: bold; color: #16a34a; }")
        layout_out_update = QVBoxLayout(self.grp_out_update)

        self.table_quick_out = QTableWidget()
        self.table_quick_out.setColumnCount(4)
        self.table_quick_out.setHorizontalHeaderLabels([
            "Số đi / TK", "Trích yếu", "Ngày tạo", "Trạng thái"
        ])
        self.table_quick_out.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_quick_out.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_quick_out.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_quick_out.doubleClicked.connect(self.on_double_click_quick_out)
        layout_out_update.addWidget(self.table_quick_out)
        bottom_split.addWidget(self.grp_out_update, 1)

        layout.addLayout(bottom_split, 2)

    # =========================================================================
    # VIEW 2: CÔNG VĂN ĐẾN (3 TAB PHỤ NGANG)
    # =========================================================================
    def init_view_incoming(self):
        layout = QVBoxLayout(self.view_incoming)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs_incoming = QTabWidget()
        self.tabs_incoming.setStyleSheet("""
            QTabBar::tab {
                font-size: 13px; font-weight: bold; padding: 8px 16px; margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #0284c7; color: white; border-radius: 4px;
            }
        """)

        # Tab phụ 1: Toàn bộ công văn đến của Phòng
        self.tab_inc_dept = QWidget()
        self.init_tab_incoming_dept()
        self.tabs_incoming.addTab(self.tab_inc_dept, "🏢 Toàn bộ công văn đến của Phòng")

        # Tab phụ 2: Toàn bộ công văn đến cá nhân
        self.tab_inc_personal = QWidget()
        self.init_tab_incoming_personal()
        self.tabs_incoming.addTab(self.tab_inc_personal, "👤 Toàn bộ công văn đến cá nhân")

        # Tab phụ 3: Chi tiết thông tin & Tệp đính kèm
        self.tab_inc_detail = QWidget()
        self.init_tab_incoming_detail()
        self.tabs_incoming.addTab(self.tab_inc_detail, "📋 Chi tiết thông tin & Tệp đính kèm")

        layout.addWidget(self.tabs_incoming)

    def init_tab_incoming_dept(self):
        layout = QVBoxLayout(self.tab_inc_dept)

        # Bộ lọc Từ ngày - Đến ngày (mặc định cả năm hiện tại để xem đầy đủ công văn)
        curr_year = QDate.currentDate().year()
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Từ ngày:"))
        self.dt_from_inc_dept = QDateEdit()
        self.dt_from_inc_dept.setCalendarPopup(True)
        self.dt_from_inc_dept.setDate(QDate(curr_year, 1, 1))
        filter_bar.addWidget(self.dt_from_inc_dept)

        filter_bar.addWidget(QLabel("Đến ngày:"))
        self.dt_to_inc_dept = QDateEdit()
        self.dt_to_inc_dept.setCalendarPopup(True)
        self.dt_to_inc_dept.setDate(QDate(curr_year, 12, 31))
        filter_bar.addWidget(self.dt_to_inc_dept)

        btn_today = QPushButton("Hôm nay")
        btn_today.clicked.connect(lambda: self.set_dates_today(self.dt_from_inc_dept, self.dt_to_inc_dept, self.apply_incoming_filter_dept))
        btn_7days = QPushButton("7 ngày qua")
        btn_7days.clicked.connect(lambda: self.set_dates_ndays(self.dt_from_inc_dept, self.dt_to_inc_dept, 7, self.apply_incoming_filter_dept))
        btn_all = QPushButton("Tất cả")
        btn_all.clicked.connect(lambda: self.set_dates_all(self.dt_from_inc_dept, self.dt_to_inc_dept, self.apply_incoming_filter_dept))
        btn_filter = QPushButton("🔍 Lọc")
        btn_filter.setStyleSheet("background:#0284c7; color:#fff; font-weight:bold;")
        btn_filter.clicked.connect(self.apply_incoming_filter_dept)

        filter_bar.addWidget(btn_today)
        filter_bar.addWidget(btn_7days)
        filter_bar.addWidget(btn_all)
        filter_bar.addWidget(btn_filter)
        filter_bar.addStretch()

        btn_view_det = QPushButton("📋 Xem chi tiết & File đã chọn")
        btn_view_det.clicked.connect(self.open_detail_from_dept)
        filter_bar.addWidget(btn_view_det)

        layout.addLayout(filter_bar)

        self.table_inc_dept = QTableWidget()
        self.table_inc_dept.setColumnCount(10)
        self.table_inc_dept.setHorizontalHeaderLabels([
            "Số đến", "Phân loại", "Số/Ký hiệu", "Ngày ban hành", "Trích yếu", "Ngày đến", "Hạn xử lý", "Xử lý chính", "Phối hợp", "Chỉ đạo"
        ])
        self.table_inc_dept.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table_inc_dept.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_inc_dept.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_inc_dept.doubleClicked.connect(self.open_detail_from_dept)
        layout.addWidget(self.table_inc_dept)

    def init_tab_incoming_personal(self):
        layout = QVBoxLayout(self.tab_inc_personal)

        curr_year = QDate.currentDate().year()
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Từ ngày:"))
        self.dt_from_inc_pers = QDateEdit()
        self.dt_from_inc_pers.setCalendarPopup(True)
        self.dt_from_inc_pers.setDate(QDate(curr_year, 1, 1))
        filter_bar.addWidget(self.dt_from_inc_pers)

        filter_bar.addWidget(QLabel("Đến ngày:"))
        self.dt_to_inc_pers = QDateEdit()
        self.dt_to_inc_pers.setCalendarPopup(True)
        self.dt_to_inc_pers.setDate(QDate(curr_year, 12, 31))
        filter_bar.addWidget(self.dt_to_inc_pers)

        btn_today = QPushButton("Hôm nay")
        btn_today.clicked.connect(lambda: self.set_dates_today(self.dt_from_inc_pers, self.dt_to_inc_pers, self.apply_incoming_filter_personal))
        btn_7days = QPushButton("7 ngày qua")
        btn_7days.clicked.connect(lambda: self.set_dates_ndays(self.dt_from_inc_pers, self.dt_to_inc_pers, 7, self.apply_incoming_filter_personal))
        btn_all = QPushButton("Tất cả")
        btn_all.clicked.connect(lambda: self.set_dates_all(self.dt_from_inc_pers, self.dt_to_inc_pers, self.apply_incoming_filter_personal))
        btn_filter = QPushButton("🔍 Lọc")
        btn_filter.setStyleSheet("background:#0284c7; color:#fff; font-weight:bold;")
        btn_filter.clicked.connect(self.apply_incoming_filter_personal)

        filter_bar.addWidget(btn_today)
        filter_bar.addWidget(btn_7days)
        filter_bar.addWidget(btn_all)
        filter_bar.addWidget(btn_filter)
        filter_bar.addStretch()

        btn_view_det = QPushButton("📋 Xem chi tiết & File đã chọn")
        btn_view_det.clicked.connect(self.open_detail_from_personal)
        filter_bar.addWidget(btn_view_det)

        layout.addLayout(filter_bar)

        self.table_inc_pers = QTableWidget()
        self.table_inc_pers.setColumnCount(11)
        self.table_inc_pers.setHorizontalHeaderLabels([
            "Trạng thái", "Phân loại", "Số đến", "Số/Ký hiệu", "Ngày ban hành", "Trích yếu", "Ngày đến", "Hạn xử lý", "Xử lý chính", "Phối hợp", "Chỉ đạo"
        ])
        self.table_inc_pers.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table_inc_pers.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_inc_pers.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_inc_pers.doubleClicked.connect(self.open_detail_from_personal)
        layout.addWidget(self.table_inc_pers)

    def init_tab_incoming_detail(self):
        main_layout = QVBoxLayout(self.tab_inc_detail)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #cbd5e1;
                width: 4px;
            }
            QSplitter::handle:hover {
                background-color: #0284c7;
            }
        """)

        # ==========================================
        # KHUNG BÊN TRÁI: THÔNG TIN VĂN BẢN & CÁC TỆP
        # ==========================================
        left_widget = QWidget()
        layout_left = QVBoxLayout(left_widget)
        layout_left.setContentsMargins(4, 4, 4, 4)
        layout_left.setSpacing(8)

        # 1. THÔNG TIN CHỈ ĐẠO & XỬ LÝ
        grp_leaders = QGroupBox("🏛️ THÔNG TIN PHÂN CÔNG CHỈ ĐẠO & XỬ LÝ")
        grp_leaders.setStyleSheet("QGroupBox { font-weight: bold; color: #0284c7; }")
        grid_leaders = QFormLayout(grp_leaders)
        grid_leaders.setSpacing(6)

        self.lbl_det_cuc = QLabel("---")
        self.lbl_det_cuc.setStyleSheet("font-weight: bold; color: #1e293b;")
        self.lbl_det_phong = QLabel("---")
        self.lbl_det_phong.setStyleSheet("font-weight: bold; color: #1e293b;")
        self.lbl_det_main = QLabel("---")
        self.lbl_det_main.setStyleSheet("font-weight: bold; color: #0284c7;")
        self.lbl_det_sub = QLabel("---")
        self.lbl_det_sub.setStyleSheet("color: #475569;")

        grid_leaders.addRow("Lãnh đạo Cục chỉ đạo:", self.lbl_det_cuc)
        grid_leaders.addRow("Lãnh đạo Phòng chỉ đạo:", self.lbl_det_phong)
        grid_leaders.addRow("Chuyên viên xử lý chính:", self.lbl_det_main)
        grid_leaders.addRow("Chuyên viên phối hợp:", self.lbl_det_sub)
        layout_left.addWidget(grp_leaders)

        # 2. THÔNG TIN CÔNG VĂN
        grp_meta = QGroupBox("📄 THÔNG TIN TRÍCH YẾU VĂN BẢN")
        grid_meta = QFormLayout(grp_meta)
        grid_meta.setSpacing(6)

        self.lbl_det_meta_code = QLabel("---")
        self.lbl_det_meta_code.setStyleSheet("font-weight: bold;")
        self.lbl_det_meta_dates = QLabel("---")
        self.lbl_det_meta_phanloai = QLabel("---")
        self.lbl_det_meta_phanloai.setStyleSheet("font-weight: bold;")
        self.lbl_det_meta_trichyeu = QLabel("Vui lòng chọn một công văn ở Tab 1 hoặc Tab 2 để xem thông tin chi tiết.")
        self.lbl_det_meta_trichyeu.setWordWrap(True)
        self.lbl_det_meta_trichyeu.setStyleSheet("color: #334155; line-height: 1.4;")

        grid_meta.addRow("Số đến / Ký hiệu:", self.lbl_det_meta_code)
        grid_meta.addRow("Phân loại xử lý:", self.lbl_det_meta_phanloai)
        grid_meta.addRow("Ngày đến / Hạn xử lý:", self.lbl_det_meta_dates)
        grid_meta.addRow("Trích yếu nội dung:", self.lbl_det_meta_trichyeu)
        layout_left.addWidget(grp_meta)

        # 3. DANH SÁCH TẤT CẢ TỆP ĐÍNH KÈM & THAO TÁC
        grp_files = QGroupBox("📎 TOÀN BỘ TỆP ĐÍNH KÈM (BẤM ĐỂ ĐỌC TRỰC TIẾP)")
        grp_files.setStyleSheet("QGroupBox { font-weight: bold; color: #16a34a; }")
        layout_files = QVBoxLayout(grp_files)
        layout_files.setSpacing(6)

        self.table_attachments = QTableWidget()
        self.table_attachments.setColumnCount(2)
        self.table_attachments.setHorizontalHeaderLabels(["Tên tệp đính kèm", "Phiên bản / Thông tin"])
        self.table_attachments.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_attachments.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_attachments.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_attachments.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_attachments.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_attachments.setStyleSheet("""
            QTableWidget {
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                background-color: white;
            }
            QTableWidget::item:selected {
                background-color: #e0f2fe;
                color: #0369a1;
                font-weight: bold;
            }
        """)
        self.table_attachments.itemClicked.connect(self.on_attachment_item_clicked)
        self.table_attachments.doubleClicked.connect(self.on_attachment_double_clicked)
        self.table_attachments.setMinimumHeight(130)
        self.table_attachments.setMaximumHeight(220)
        layout_files.addWidget(self.table_attachments)

        # Nút thao tác tệp
        file_btn_row1 = QHBoxLayout()
        self.btn_attach_read = QPushButton("👁️ Đọc file đã chọn")
        self.btn_attach_read.setStyleSheet("background: #0f172a; color: white; padding: 7px 12px; border-radius: 4px; font-weight: bold;")
        self.btn_attach_read.clicked.connect(self.action_read_selected_attachment)

        self.btn_attach_web = QPushButton("🌐 Mở xem trên Web (Chrome)")
        self.btn_attach_web.setStyleSheet("background: #0284c7; color: white; padding: 7px 12px; border-radius: 4px; font-weight: bold;")
        self.btn_attach_web.setToolTip("Mở tài liệu trực tiếp trên trình duyệt bằng trình xem trực tuyến của DRVN (tốc độ cao)")
        self.btn_attach_web.clicked.connect(self.action_open_web_selected_attachment)

        file_btn_row1.addWidget(self.btn_attach_read)
        file_btn_row1.addWidget(self.btn_attach_web)
        layout_files.addLayout(file_btn_row1)

        file_btn_row2 = QHBoxLayout()
        self.btn_attach_save = QPushButton("💾 Lưu tệp đã chọn")
        self.btn_attach_save.setStyleSheet("background: #16a34a; color: white; padding: 7px 12px; border-radius: 4px; font-weight: bold;")
        self.btn_attach_save.clicked.connect(self.action_save_selected_attachment)

        self.btn_attach_save_all = QPushButton("📦 Tải về tất cả tệp (.pdf)")
        self.btn_attach_save_all.setStyleSheet("background: #475569; color: white; padding: 7px 12px; border-radius: 4px; font-weight: bold;")
        self.btn_attach_save_all.setToolTip("Tải toàn bộ các tệp đính kèm của công văn này vào một thư mục riêng")
        self.btn_attach_save_all.clicked.connect(self.action_save_all_attachments)

        file_btn_row2.addWidget(self.btn_attach_save)
        file_btn_row2.addWidget(self.btn_attach_save_all)
        layout_files.addLayout(file_btn_row2)

        lbl_hint = QLabel("💡 Bấm vào một tệp trong bảng để đọc ngay nội dung văn bản (đầy đủ chữ ký số & dấu đỏ), hoặc bấm 'Mở trên Web' để xem bằng Chrome/Edge.")
        lbl_hint.setStyleSheet("font-size: 11px; color: #64748b; font-style: italic;")
        lbl_hint.setWordWrap(True)
        layout_files.addWidget(lbl_hint)

        layout_left.addWidget(grp_files)
        layout_left.addStretch()

        # ==========================================
        # KHUNG BÊN PHẢI: TRÌNH ĐỌC PDF TỐC ĐỘ CAO (HỖ TRỢ 100% CHỮ KÝ SỐ & DẤU ĐỎ)
        # ==========================================
        right_widget = QWidget()
        layout_right = QVBoxLayout(right_widget)
        layout_right.setContentsMargins(4, 4, 4, 4)
        layout_right.setSpacing(6)

        # Thanh điều hướng Reader Toolbar
        pdf_bar = QFrame()
        pdf_bar.setStyleSheet("""
            QFrame {
                background: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 4px;
            }
            QPushButton {
                background: white;
                border: 1px solid #94a3b8;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #e2e8f0;
                border-color: #0284c7;
            }
        """)
        bar_layout = QHBoxLayout(pdf_bar)
        bar_layout.setContentsMargins(6, 4, 6, 4)
        bar_layout.setSpacing(6)

        self.lbl_pdf_title = QLabel("📖 Trình đọc văn bản nhanh (PDF)")
        self.lbl_pdf_title.setStyleSheet("font-weight: bold; color: #0f172a;")

        self.btn_pdf_prev = QPushButton("◀")
        self.btn_pdf_prev.setToolTip("Trang trước")
        self.btn_pdf_prev.clicked.connect(self.action_pdf_prev_page)

        self.lbl_pdf_page = QLabel("Trang --/--")
        self.lbl_pdf_page.setStyleSheet("font-weight: bold; color: #334155; min-width: 80px; text-align: center;")

        self.btn_pdf_next = QPushButton("▶")
        self.btn_pdf_next.setToolTip("Trang sau")
        self.btn_pdf_next.clicked.connect(self.action_pdf_next_page)

        self.btn_pdf_zoom_out = QPushButton("➖")
        self.btn_pdf_zoom_out.setToolTip("Thu nhỏ (Ctrl + Cuộn chuột)")
        self.btn_pdf_zoom_out.clicked.connect(self.action_pdf_zoom_out)

        self.lbl_pdf_zoom = QLabel("100%")
        self.lbl_pdf_zoom.setStyleSheet("font-weight: bold; color: #475569; min-width: 45px; text-align: center;")

        self.btn_pdf_zoom_in = QPushButton("➕")
        self.btn_pdf_zoom_in.setToolTip("Phóng to (Ctrl + Cuộn chuột)")
        self.btn_pdf_zoom_in.clicked.connect(self.action_pdf_zoom_in)

        self.btn_pdf_fit_width = QPushButton("↔ Vừa khung")
        self.btn_pdf_fit_width.setToolTip("Tự động vừa chiều rộng màn hình")
        self.btn_pdf_fit_width.clicked.connect(self.action_pdf_fit_width)

        self.btn_pdf_open_browser = QPushButton("↗ Mở ngoài")
        self.btn_pdf_open_browser.setToolTip("Mở tệp này bằng ứng dụng hoặc trình duyệt bên ngoài")
        self.btn_pdf_open_browser.clicked.connect(self.action_pdf_open_external)

        bar_layout.addWidget(self.lbl_pdf_title)
        bar_layout.addStretch()
        bar_layout.addWidget(self.btn_pdf_prev)
        bar_layout.addWidget(self.lbl_pdf_page)
        bar_layout.addWidget(self.btn_pdf_next)
        bar_layout.addWidget(self.btn_pdf_zoom_out)
        bar_layout.addWidget(self.lbl_pdf_zoom)
        bar_layout.addWidget(self.btn_pdf_zoom_in)
        bar_layout.addWidget(self.btn_pdf_fit_width)
        bar_layout.addWidget(self.btn_pdf_open_browser)

        layout_right.addWidget(pdf_bar)

        # Viewer & Placeholder Stack
        self.stack_pdf = QStackedWidget()
        self.stack_pdf.setStyleSheet("border: 1px solid #cbd5e1; background: white; border-radius: 4px;")

        # Page 0: Placeholder khi chưa chọn file
        self.lbl_pdf_placeholder = QLabel("📄 Chưa chọn tệp đính kèm nào để xem.\n\nVui lòng bấm vào một tệp trong danh sách bên trái để mở đọc nội dung.")
        self.lbl_pdf_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_pdf_placeholder.setStyleSheet("color: #64748b; font-size: 13px; font-weight: bold; background: #fafafa; line-height: 1.6;")
        self.stack_pdf.addWidget(self.lbl_pdf_placeholder)

        # Page 1: PDF Viewer bằng PyMuPDF - Hiển thị 100% chữ ký số, con dấu đỏ
        self.scroll_pdf_viewer = PDFScrollArea(self.action_pdf_zoom_in, self.action_pdf_zoom_out)
        self.scroll_pdf_viewer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_pdf_viewer.setStyleSheet("background-color: #525659; border: none;")
        self.scroll_pdf_viewer.setWidgetResizable(True)

        self.lbl_pdf_page_render = QLabel()
        self.lbl_pdf_page_render.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_pdf_page_render.setStyleSheet("background: transparent; margin: 12px auto;")
        self.scroll_pdf_viewer.setWidget(self.lbl_pdf_page_render)

        self.stack_pdf.addWidget(self.scroll_pdf_viewer)
        layout_right.addWidget(self.stack_pdf)

        # Đưa vào Splitter với tỷ lệ 42% - 58%
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([450, 650])
        main_layout.addWidget(splitter)

    # =========================================================================
    # VIEW 3: CÔNG VĂN ĐI (3 TAB PHỤ NGANG)
    # =========================================================================
    def init_view_outgoing(self):
        layout = QVBoxLayout(self.view_outgoing)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs_outgoing = QTabWidget()
        self.tabs_outgoing.setStyleSheet("""
            QTabBar::tab {
                font-size: 13px; font-weight: bold; padding: 8px 16px; margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #0284c7; color: white; border-radius: 4px;
            }
        """)

        # Tab phụ 1: Toàn bộ công văn đi của Phòng
        self.tab_out_dept = QWidget()
        self.init_tab_outgoing_dept()
        self.tabs_outgoing.addTab(self.tab_out_dept, "🏢 Toàn bộ công văn đi của Phòng")

        # Tab phụ 2: Toàn bộ công văn đi cá nhân
        self.tab_out_personal = QWidget()
        self.init_tab_outgoing_personal()
        self.tabs_outgoing.addTab(self.tab_out_personal, "👤 Toàn bộ công văn đi cá nhân")

        # Tab phụ 3: Toàn bộ công văn đi đang xử lý (trạng thái)
        self.tab_out_processing = QWidget()
        self.init_tab_outgoing_processing()
        self.tabs_outgoing.addTab(self.tab_out_processing, "⏳ Các công văn đi đang xử lý (Trạng thái)")

        layout.addWidget(self.tabs_outgoing)

    def init_tab_outgoing_dept(self):
        layout = QVBoxLayout(self.tab_out_dept)

        curr_year = QDate.currentDate().year()
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Từ ngày:"))
        self.dt_from_out_dept = QDateEdit()
        self.dt_from_out_dept.setCalendarPopup(True)
        self.dt_from_out_dept.setDate(QDate(curr_year, 1, 1))
        filter_bar.addWidget(self.dt_from_out_dept)

        filter_bar.addWidget(QLabel("Đến ngày:"))
        self.dt_to_out_dept = QDateEdit()
        self.dt_to_out_dept.setCalendarPopup(True)
        self.dt_to_out_dept.setDate(QDate(curr_year, 12, 31))
        filter_bar.addWidget(self.dt_to_out_dept)

        btn_today = QPushButton("Hôm nay")
        btn_today.clicked.connect(lambda: self.set_dates_today(self.dt_from_out_dept, self.dt_to_out_dept, self.apply_outgoing_filter_dept))
        btn_7days = QPushButton("7 ngày qua")
        btn_7days.clicked.connect(lambda: self.set_dates_ndays(self.dt_from_out_dept, self.dt_to_out_dept, 7, self.apply_outgoing_filter_dept))
        btn_all = QPushButton("Tất cả")
        btn_all.clicked.connect(lambda: self.set_dates_all(self.dt_from_out_dept, self.dt_to_out_dept, self.apply_outgoing_filter_dept))
        btn_filter = QPushButton("🔍 Lọc")
        btn_filter.setStyleSheet("background:#0284c7; color:#fff; font-weight:bold;")
        btn_filter.clicked.connect(self.apply_outgoing_filter_dept)

        filter_bar.addWidget(btn_today)
        filter_bar.addWidget(btn_7days)
        filter_bar.addWidget(btn_all)
        filter_bar.addWidget(btn_filter)
        filter_bar.addStretch()

        layout.addLayout(filter_bar)

        self.table_out_dept = QTableWidget()
        self.table_out_dept.setColumnCount(7)
        self.table_out_dept.setHorizontalHeaderLabels([
            "Số trình ký", "Số đi", "Ngày ban hành", "Trích yếu", "Người ký", "Người soạn thảo", "CV trả lời"
        ])
        self.table_out_dept.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table_out_dept.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_out_dept.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table_out_dept)

    def init_tab_outgoing_personal(self):
        layout = QVBoxLayout(self.tab_out_personal)

        curr_year = QDate.currentDate().year()
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Từ ngày:"))
        self.dt_from_out_pers = QDateEdit()
        self.dt_from_out_pers.setCalendarPopup(True)
        self.dt_from_out_pers.setDate(QDate(curr_year, 1, 1))
        filter_bar.addWidget(self.dt_from_out_pers)

        filter_bar.addWidget(QLabel("Đến ngày:"))
        self.dt_to_out_pers = QDateEdit()
        self.dt_to_out_pers.setCalendarPopup(True)
        self.dt_to_out_pers.setDate(QDate(curr_year, 12, 31))
        filter_bar.addWidget(self.dt_to_out_pers)

        btn_today = QPushButton("Hôm nay")
        btn_today.clicked.connect(lambda: self.set_dates_today(self.dt_from_out_pers, self.dt_to_out_pers, self.apply_outgoing_filter_personal))
        btn_7days = QPushButton("7 ngày qua")
        btn_7days.clicked.connect(lambda: self.set_dates_ndays(self.dt_from_out_pers, self.dt_to_out_pers, 7, self.apply_outgoing_filter_personal))
        btn_all = QPushButton("Tất cả")
        btn_all.clicked.connect(lambda: self.set_dates_all(self.dt_from_out_pers, self.dt_to_out_pers, self.apply_outgoing_filter_personal))
        btn_filter = QPushButton("🔍 Lọc")
        btn_filter.setStyleSheet("background:#0284c7; color:#fff; font-weight:bold;")
        btn_filter.clicked.connect(self.apply_outgoing_filter_personal)

        filter_bar.addWidget(btn_today)
        filter_bar.addWidget(btn_7days)
        filter_bar.addWidget(btn_all)
        filter_bar.addWidget(btn_filter)
        filter_bar.addStretch()

        layout.addLayout(filter_bar)

        self.table_out_pers = QTableWidget()
        self.table_out_pers.setColumnCount(8)
        self.table_out_pers.setHorizontalHeaderLabels([
            "Số đi", "Số trình ký", "Trích yếu", "Ngày ban hành", "Trạng thái", "Người ký", "Người soạn thảo", "CV trả lời"
        ])
        self.table_out_pers.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_out_pers.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_out_pers.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_out_pers.doubleClicked.connect(self.on_double_click_outgoing_personal)
        layout.addWidget(self.table_out_pers)

    def init_tab_outgoing_processing(self):
        layout = QVBoxLayout(self.tab_out_processing)

        tip_label = QLabel("⏳ Danh sách các văn bản đi đang trong luồng phê duyệt (Đã trình Lãnh đạo Phòng, Lãnh đạo Cục đã ký số, Đang phát hành...).")
        tip_label.setStyleSheet("color: #b45309; font-weight: bold; margin-bottom: 6px;")
        layout.addWidget(tip_label)

        self.table_out_proc = QTableWidget()
        self.table_out_proc.setColumnCount(6)
        self.table_out_proc.setHorizontalHeaderLabels([
            "Số trình ký", "Số đi", "Trích yếu", "Người ký", "Người soạn thảo", "Trạng thái xử lý"
        ])
        self.table_out_proc.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_out_proc.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_out_proc.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table_out_proc)

    # =========================================================================
    # VIEW 4: HỆ THỐNG THEO DÕI NHIỆM VỤ (nhiemvu.drvn.gov.vn)
    # =========================================================================
    def init_view_tasks(self):
        layout = QVBoxLayout(self.view_tasks)
        layout.setContentsMargins(4, 0, 4, 4)
        layout.setSpacing(8)

        # Header bar
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: #0f172a;
                border-radius: 8px;
                padding: 8px 16px;
                border: 1px solid #1e293b;
            }
        """)
        hdr_layout = QHBoxLayout(header_frame)

        title_box = QVBoxLayout()
        lbl_title = QLabel("🎯 HỆ THỐNG THEO DÕI VÀ ĐÔN ĐỐC NHIỆM VỤ - CỤC ĐƯỜNG BỘ VIỆT NAM")
        lbl_title.setStyleSheet("color: #38bdf8; font-size: 15px; font-weight: bold;")
        lbl_sub = QLabel("Giám sát tiến độ & đôn đốc nhiệm vụ theo thời gian thực (nhiemvu.drvn.gov.vn/dashboard)")
        lbl_sub.setStyleSheet("color: #94a3b8; font-size: 12px;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)
        hdr_layout.addLayout(title_box)

        hdr_layout.addStretch()

        btn_open_web = QPushButton("🌐 Mở trên Web (Chrome)")
        btn_open_web.setStyleSheet("background: #0284c7; color: white; padding: 7px 15px; border-radius: 6px; font-weight: bold; font-size: 12px;")
        btn_open_web.clicked.connect(lambda: webbrowser.open("https://nhiemvu.drvn.gov.vn/dashboard"))

        btn_sync = QPushButton("🔄 Đồng bộ dữ liệu")
        btn_sync.setStyleSheet("background: #0d9488; color: white; padding: 7px 15px; border-radius: 6px; font-weight: bold; font-size: 12px;")
        btn_sync.clicked.connect(self.action_sync_nhiemvu)

        hdr_layout.addWidget(btn_open_web)
        hdr_layout.addWidget(btn_sync)
        layout.addWidget(header_frame)

        # 2 Main Tabs: Tổng quan & Nhiệm vụ
        self.tabs_tasks = QTabWidget()
        self.tabs_tasks.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #334155;
                border-radius: 6px;
                background: #0f172a;
            }
            QTabBar::tab {
                background: #1e293b;
                color: #94a3b8;
                font-weight: bold;
                font-size: 13px;
                padding: 9px 22px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #0284c7;
                color: #ffffff;
            }
        """)

        # Tab 1: Tổng quan
        self.tab_task_overview = QWidget()
        self.init_tab_task_overview()
        self.tabs_tasks.addTab(self.tab_task_overview, "📊 Tổng quan (Dashboard)")

        # Tab 2: Nhiệm vụ
        self.tab_task_list = QWidget()
        self.init_tab_task_list()
        self.tabs_tasks.addTab(self.tab_task_list, "📋 Danh sách nhiệm vụ")

        layout.addWidget(self.tabs_tasks)

    def init_tab_task_overview(self):
        layout = QVBoxLayout(self.tab_task_overview)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 1. 5 Thẻ chỉ số KPI (Stat Cards)
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(10)

        self.card_total = self.create_stat_card("📌 TỔNG NHIỆM VỤ", "0", "Toàn Cục Đường bộ VN", "#0284c7", "#38bdf8")
        self.card_inprogress = self.create_stat_card("⏳ ĐANG THỰC HIỆN", "0", "Trong hạn giải quyết", "#3b82f6", "#60a5fa")
        self.card_completed = self.create_stat_card("✅ ĐÃ HOÀN THÀNH", "0", "Đúng và trước hạn", "#10b981", "#34d399")
        self.card_overdue = self.create_stat_card("🚨 QUÁ HẠN XỬ LÝ", "0", "Cần đôn đốc khẩn", "#ef4444", "#f87171")
        self.card_neardue = self.create_stat_card("⚠️ SẮP ĐẾN HẠN (≤ 3 ngày)", "0", "Ưu tiên hoàn thiện", "#f59e0b", "#fbbf24")

        cards_layout.addWidget(self.card_total)
        cards_layout.addWidget(self.card_inprogress)
        cards_layout.addWidget(self.card_completed)
        cards_layout.addWidget(self.card_overdue)
        cards_layout.addWidget(self.card_neardue)
        layout.addLayout(cards_layout)

        # 2. Thanh tiến độ hoàn thành chung
        prog_box = QFrame()
        prog_box.setStyleSheet("background: #1e293b; border-radius: 8px; padding: 10px 14px; border: 1px solid #334155;")
        prog_layout = QHBoxLayout(prog_box)
        self.lbl_task_rate_title = QLabel("TỶ LỆ HOÀN THÀNH NHIỆM VỤ TOÀN CỤC: 0%")
        self.lbl_task_rate_title.setStyleSheet("color: #e2e8f0; font-weight: bold; font-size: 13px; min-width: 320px;")

        self.progress_tasks = QProgressBar()
        self.progress_tasks.setStyleSheet("""
            QProgressBar {
                border: 1px solid #475569;
                border-radius: 6px;
                text-align: center;
                color: white;
                font-weight: bold;
                height: 22px;
                background: #0f172a;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #059669);
                border-radius: 5px;
            }
        """)
        self.progress_tasks.setValue(0)
        prog_layout.addWidget(self.lbl_task_rate_title)
        prog_layout.addWidget(self.progress_tasks, 1)
        layout.addWidget(prog_box)

        # 3. Hai bảng song song (Splitter): Phân bổ phòng ban + Nhiệm vụ cần đôn đốc gấp
        tables_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Bảng trái: Phân bổ theo phòng ban
        box_left = QFrame()
        box_left.setStyleSheet("background: #1e293b; border-radius: 8px; padding: 10px; border: 1px solid #334155;")
        layout_left = QVBoxLayout(box_left)
        lbl_left = QLabel("🏢 PHÂN BỔ NHIỆM VỤ THEO ĐƠN VỊ / PHÒNG BAN")
        lbl_left.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px; margin-bottom: 4px;")

        self.table_tasks_by_dept = QTableWidget()
        self.table_tasks_by_dept.setColumnCount(5)
        self.table_tasks_by_dept.setHorizontalHeaderLabels(["Đơn vị / Phòng ban", "Tổng số", "Đang xử lý", "Đã xong", "Quá hạn"])
        self.table_tasks_by_dept.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_tasks_by_dept.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks_by_dept.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks_by_dept.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks_by_dept.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks_by_dept.verticalHeader().setVisible(False)
        self.table_tasks_by_dept.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_tasks_by_dept.setStyleSheet(self.get_task_table_style())
        layout_left.addWidget(lbl_left)
        layout_left.addWidget(self.table_tasks_by_dept)
        tables_splitter.addWidget(box_left)

        # Bảng phải: Nhiệm vụ trọng tâm cần đôn đốc gấp
        box_right = QFrame()
        box_right.setStyleSheet("background: #1e293b; border-radius: 8px; padding: 10px; border: 1px solid #334155;")
        layout_right = QVBoxLayout(box_right)
        lbl_right = QLabel("🚨 NHIỆM VỤ CẦN ĐÔN ĐỐC GẤP (QUÁ HẠN & SẮP ĐẾN HẠN)")
        lbl_right.setStyleSheet("color: #f87171; font-weight: bold; font-size: 13px; margin-bottom: 4px;")

        self.table_urgent_tasks = QTableWidget()
        self.table_urgent_tasks.setColumnCount(4)
        self.table_urgent_tasks.setHorizontalHeaderLabels(["Mã NV", "Nội dung nhiệm vụ", "Hạn xử lý", "Đơn vị chủ trì"])
        self.table_urgent_tasks.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_urgent_tasks.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_urgent_tasks.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_urgent_tasks.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_urgent_tasks.verticalHeader().setVisible(False)
        self.table_urgent_tasks.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_urgent_tasks.setStyleSheet(self.get_task_table_style())
        self.table_urgent_tasks.doubleClicked.connect(self.on_double_click_urgent_task)

        layout_right.addWidget(lbl_right)
        layout_right.addWidget(self.table_urgent_tasks)
        tables_splitter.addWidget(box_right)

        tables_splitter.setSizes([550, 550])
        layout.addWidget(tables_splitter, 1)

    def create_stat_card(self, title, count_text, subtitle, border_color, text_color):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: #1e293b;
                border-radius: 8px;
                border: 2px solid {border_color};
                padding: 8px 10px;
            }}
        """)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(4, 4, 4, 4)
        c_layout.setSpacing(3)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold;")

        lbl_c = QLabel(count_text)
        lbl_c.setStyleSheet(f"color: {text_color}; font-size: 26px; font-weight: bold;")
        lbl_c.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.lbl_count = lbl_c

        lbl_s = QLabel(subtitle)
        lbl_s.setStyleSheet("color: #64748b; font-size: 11px;")
        lbl_s.setAlignment(Qt.AlignmentFlag.AlignCenter)

        c_layout.addWidget(lbl_t)
        c_layout.addWidget(lbl_c)
        c_layout.addWidget(lbl_s)
        return card

    def init_tab_task_list(self):
        layout = QVBoxLayout(self.tab_task_list)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 1. Khung lọc dữ liệu
        filter_box = QFrame()
        filter_box.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 6px 12px; border: 1px solid #334155;")
        f_layout = QHBoxLayout(filter_box)
        f_layout.setSpacing(8)

        self.txt_task_search = QLineEdit()
        self.txt_task_search.setPlaceholderText("🔍 Tìm theo tên nhiệm vụ, mã NV, người chủ trì...")
        self.txt_task_search.textChanged.connect(self.apply_tasks_filter)

        self.cbo_task_dept = QComboBox()
        self.cbo_task_dept.addItems([
            "Tất cả đơn vị",
            "Phòng Quản lý vận tải",
            "Phòng Kế hoạch - Đầu tư",
            "Phòng Quản lý bảo trì kết cấu hạ tầng",
            "Phòng Pháp chế - Thanh tra",
            "Phòng KHCN, Môi trường và HTQT",
            "Văn phòng Cục"
        ])
        self.cbo_task_dept.currentIndexChanged.connect(self.apply_tasks_filter)

        self.cbo_task_status = QComboBox()
        self.cbo_task_status.addItems([
            "Tất cả trạng thái",
            "Đang thực hiện",
            "Đã hoàn thành",
            "Quá hạn"
        ])
        self.cbo_task_status.currentIndexChanged.connect(self.apply_tasks_filter)

        self.cbo_task_priority = QComboBox()
        self.cbo_task_priority.addItems([
            "Tất cả ưu tiên",
            "Hỏa tốc / Khẩn",
            "Quan trọng",
            "Bình thường"
        ])
        self.cbo_task_priority.currentIndexChanged.connect(self.apply_tasks_filter)

        btn_reset_filter = QPushButton("🔄 Đặt lại")
        btn_reset_filter.setStyleSheet("background: #475569; color: white; padding: 6px 14px; border-radius: 4px; font-weight: bold;")
        btn_reset_filter.clicked.connect(self.reset_tasks_filter)

        f_layout.addWidget(self.txt_task_search, 2)
        f_layout.addWidget(self.cbo_task_dept, 1)
        f_layout.addWidget(self.cbo_task_status, 1)
        f_layout.addWidget(self.cbo_task_priority, 1)
        f_layout.addWidget(btn_reset_filter)
        layout.addWidget(filter_box)

        # 2. Splitter: Bảng danh sách nhiệm vụ + Khung xem chi tiết
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Bảng nhiệm vụ
        self.table_tasks = QTableWidget()
        self.table_tasks.setColumnCount(9)
        self.table_tasks.setHorizontalHeaderLabels([
            "Mã NV", "Tên / Nội dung nhiệm vụ", "Nguồn giao / Căn cứ",
            "Đơn vị chủ trì", "Người thực hiện", "Thời hạn",
            "Tiến độ", "Trạng thái", "Ưu tiên"
        ])
        self.table_tasks.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_tasks.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        self.table_tasks.verticalHeader().setVisible(False)
        self.table_tasks.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_tasks.setStyleSheet(self.get_task_table_style())
        self.table_tasks.itemSelectionChanged.connect(self.on_task_row_selected)
        splitter.addWidget(self.table_tasks)

        # Khung xem chi tiết nhiệm vụ
        self.frame_task_detail = QFrame()
        self.frame_task_detail.setStyleSheet("background: #0f172a; border-radius: 8px; border: 1px solid #334155; padding: 12px;")
        det_layout = QVBoxLayout(self.frame_task_detail)
        det_layout.setContentsMargins(10, 8, 10, 8)
        det_layout.setSpacing(6)

        self.lbl_task_det_code = QLabel("MÃ NHIỆM VỤ: --")
        self.lbl_task_det_code.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px;")

        self.lbl_task_det_title = QLabel("Chọn một nhiệm vụ ở bảng trên để xem chi tiết đầy đủ")
        self.lbl_task_det_title.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        self.lbl_task_det_title.setWordWrap(True)

        self.lbl_task_det_info = QLabel("")
        self.lbl_task_det_info.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.lbl_task_det_info.setWordWrap(True)

        self.lbl_task_det_report = QLabel("")
        self.lbl_task_det_report.setStyleSheet("color: #a7f3d0; font-size: 12px; background: #064e3b; padding: 8px; border-radius: 4px;")
        self.lbl_task_det_report.setWordWrap(True)
        self.lbl_task_det_report.setVisible(False)

        det_layout.addWidget(self.lbl_task_det_code)
        det_layout.addWidget(self.lbl_task_det_title)
        det_layout.addWidget(self.lbl_task_det_info)
        det_layout.addWidget(self.lbl_task_det_report)

        splitter.addWidget(self.frame_task_detail)
        splitter.setSizes([450, 160])

        layout.addWidget(splitter, 1)

    def get_task_table_style(self):
        return """
            QTableWidget {
                background: #0f172a;
                color: #e2e8f0;
                gridline-color: #334155;
                border: 1px solid #334155;
                border-radius: 6px;
                selection-background-color: #0284c7;
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #38bdf8;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #334155;
            }
        """

    def refresh_tasks_view(self):
        """Làm mới toàn bộ dữ liệu giao diện Hệ thống theo dõi nhiệm vụ"""
        try:
            stats = db.get_task_stats()
            self.card_total.lbl_count.setText(str(stats.get("total", 0)))
            self.card_inprogress.lbl_count.setText(str(stats.get("in_progress", 0)))
            self.card_completed.lbl_count.setText(str(stats.get("completed", 0)))
            self.card_overdue.lbl_count.setText(str(stats.get("overdue", 0)))
            self.card_neardue.lbl_count.setText(str(stats.get("near_due", 0)))

            rate = stats.get("completion_rate", 0)
            self.progress_tasks.setValue(int(rate))
            self.lbl_task_rate_title.setText(
                f"📈 TỶ LỆ HOÀN THÀNH TOÀN CỤC: {rate}% ({stats.get('completed', 0)}/{stats.get('total', 0)} nhiệm vụ)"
            )

            # 1. Bảng phân bổ nhiệm vụ theo đơn vị / phòng ban
            dept_rows = db.get_tasks_by_department()
            self.table_tasks_by_dept.setRowCount(len(dept_rows))
            for row, d in enumerate(dept_rows):
                item_d = QTableWidgetItem(str(d.get("department", "")))
                item_d.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                item_d.setForeground(QColor("#38bdf8"))

                item_tot = QTableWidgetItem(str(d.get("total", 0)))
                item_tot.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                item_inp = QTableWidgetItem(str(d.get("in_progress", 0)))
                item_inp.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_inp.setForeground(QColor("#60a5fa"))

                item_cmp = QTableWidgetItem(str(d.get("completed", 0)))
                item_cmp.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_cmp.setForeground(QColor("#34d399"))

                item_ovd = QTableWidgetItem(str(d.get("overdue", 0)))
                item_ovd.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                ovd_val = int(d.get("overdue", 0))
                if ovd_val > 0:
                    item_ovd.setForeground(QColor("#f87171"))
                    item_ovd.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                else:
                    item_ovd.setForeground(QColor("#94a3b8"))

                self.table_tasks_by_dept.setItem(row, 0, item_d)
                self.table_tasks_by_dept.setItem(row, 1, item_tot)
                self.table_tasks_by_dept.setItem(row, 2, item_inp)
                self.table_tasks_by_dept.setItem(row, 3, item_cmp)
                self.table_tasks_by_dept.setItem(row, 4, item_ovd)

            # 2. Bảng nhiệm vụ trọng tâm cần đôn đốc gấp (Quá hạn & sắp đến hạn)
            all_tasks = db.get_tasks_filtered()
            urgent_list = []
            today = date.today()
            for t in all_tasks:
                st = t.get("status", "")
                prio = t.get("priority", "")
                d_str = t.get("due_date", "")
                is_urgent = (st == "qua_han") or (prio == "khan")
                if not is_urgent and st == "dang_xu_ly" and d_str:
                    d_parsed = db.parse_date_vietnam(d_str)
                    if d_parsed:
                        delta = (d_parsed - today).days
                        if 0 <= delta <= 3:
                            is_urgent = True
                if is_urgent and st != "hoan_thanh":
                    urgent_list.append(t)

            self.table_urgent_tasks.setRowCount(len(urgent_list))
            for row, t in enumerate(urgent_list):
                code_str = str(t.get("code") or t.get("task_code") or "")
                item_code = QTableWidgetItem(code_str)
                item_code.setForeground(QColor("#f87171" if t.get("status") == "qua_han" else "#fbbf24"))
                item_code.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                item_code.setData(Qt.ItemDataRole.UserRole, t)

                item_title = QTableWidgetItem(str(t.get("title", "")))
                item_title.setToolTip(str(t.get("title", "")))
                item_title.setData(Qt.ItemDataRole.UserRole, t)

                due_text = str(t.get("due_date", ""))
                if t.get("status") == "qua_han":
                    due_text += " (QUÁ HẠN)"
                item_due = QTableWidgetItem(due_text)
                item_due.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_due.setForeground(QColor("#f87171" if t.get("status") == "qua_han" else "#fbbf24"))
                item_due.setData(Qt.ItemDataRole.UserRole, t)

                item_dept = QTableWidgetItem(str(t.get("department", "")))
                item_dept.setData(Qt.ItemDataRole.UserRole, t)

                self.table_urgent_tasks.setItem(row, 0, item_code)
                self.table_urgent_tasks.setItem(row, 1, item_title)
                self.table_urgent_tasks.setItem(row, 2, item_due)
                self.table_urgent_tasks.setItem(row, 3, item_dept)

            # 3. Làm mới bảng Tab 2
            self.apply_tasks_filter()
        except Exception as e:
            print(f"Error in refresh_tasks_view: {e}")

    def apply_tasks_filter(self):
        """Lọc và hiển thị danh sách nhiệm vụ chi tiết theo điều kiện"""
        try:
            kw = self.txt_task_search.text().strip() if hasattr(self, "txt_task_search") else ""
            dept = self.cbo_task_dept.currentText() if hasattr(self, "cbo_task_dept") else None
            status = self.cbo_task_status.currentText() if hasattr(self, "cbo_task_status") else None
            priority = self.cbo_task_priority.currentText() if hasattr(self, "cbo_task_priority") else None

            tasks = db.get_tasks_filtered(department=dept, status=status, priority=priority, keyword=kw)
            self.current_filtered_tasks = tasks
            self.table_tasks.setRowCount(len(tasks))

            for row, t in enumerate(tasks):
                # 0: Mã NV
                code_str = str(t.get("code") or t.get("task_code") or "")
                item_code = QTableWidgetItem(code_str)
                item_code.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                item_code.setForeground(QColor("#38bdf8"))
                item_code.setData(Qt.ItemDataRole.UserRole, t)

                # 1: Tên nhiệm vụ
                item_title = QTableWidgetItem(str(t.get("title", "")))
                item_title.setToolTip(str(t.get("title", "")))
                item_title.setData(Qt.ItemDataRole.UserRole, t)

                # 2: Căn cứ / Nguồn giao
                item_src = QTableWidgetItem(str(t.get("source", "")))
                item_src.setToolTip(str(t.get("source", "")))
                item_src.setData(Qt.ItemDataRole.UserRole, t)

                # 3: Đơn vị chủ trì
                item_dept = QTableWidgetItem(str(t.get("department", "")))
                item_dept.setData(Qt.ItemDataRole.UserRole, t)

                # 4: Chuyên viên xử lý
                item_asg = QTableWidgetItem(str(t.get("assignee", "")))
                item_asg.setData(Qt.ItemDataRole.UserRole, t)

                # 5: Thời hạn
                item_due = QTableWidgetItem(str(t.get("due_date", "")))
                item_due.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_due.setData(Qt.ItemDataRole.UserRole, t)

                # 6: Tiến độ
                prog = int(t.get("progress", 0))
                item_prog = QTableWidgetItem(f"{prog}%")
                item_prog.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if prog == 100:
                    item_prog.setForeground(QColor("#10b981"))
                elif prog > 50:
                    item_prog.setForeground(QColor("#38bdf8"))
                else:
                    item_prog.setForeground(QColor("#f59e0b"))
                item_prog.setData(Qt.ItemDataRole.UserRole, t)

                # 7: Trạng thái badge
                st_code = t.get("status", "")
                if st_code == "hoan_thanh":
                    st_text = "✅ Đã hoàn thành"
                    st_color = QColor("#10b981")
                elif st_code == "qua_han":
                    st_text = "🚨 Quá hạn"
                    st_color = QColor("#ef4444")
                else:
                    st_text = "⏳ Đang thực hiện"
                    st_color = QColor("#3b82f6")
                item_st = QTableWidgetItem(st_text)
                item_st.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_st.setForeground(st_color)
                item_st.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                item_st.setData(Qt.ItemDataRole.UserRole, t)

                # 8: Ưu tiên badge
                prio_code = t.get("priority", "")
                if prio_code == "khan":
                    pr_text = "🔥 Hỏa tốc/Khẩn"
                    pr_color = QColor("#ef4444")
                elif prio_code == "quan_trong":
                    pr_text = "⚡ Quan trọng"
                    pr_color = QColor("#f59e0b")
                else:
                    pr_text = "Tiêu chuẩn"
                    pr_color = QColor("#94a3b8")
                item_pr = QTableWidgetItem(pr_text)
                item_pr.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_pr.setForeground(pr_color)
                item_pr.setData(Qt.ItemDataRole.UserRole, t)

                self.table_tasks.setItem(row, 0, item_code)
                self.table_tasks.setItem(row, 1, item_title)
                self.table_tasks.setItem(row, 2, item_src)
                self.table_tasks.setItem(row, 3, item_dept)
                self.table_tasks.setItem(row, 4, item_asg)
                self.table_tasks.setItem(row, 5, item_due)
                self.table_tasks.setItem(row, 6, item_prog)
                self.table_tasks.setItem(row, 7, item_st)
                self.table_tasks.setItem(row, 8, item_pr)

            if len(tasks) > 0:
                self.table_tasks.selectRow(0)
                self.display_task_detail(tasks[0])
            else:
                self.lbl_task_det_code.setText("MÃ NHIỆM VỤ: --")
                self.lbl_task_det_title.setText("Không tìm thấy nhiệm vụ phù hợp với điều kiện lọc.")
                self.lbl_task_det_info.setText("")
                self.lbl_task_det_report.setVisible(False)
        except Exception as e:
            print(f"Error in apply_tasks_filter: {e}")

    def reset_tasks_filter(self):
        """Đặt lại bộ lọc tìm kiếm nhiệm vụ về mặc định"""
        self.txt_task_search.blockSignals(True)
        self.cbo_task_dept.blockSignals(True)
        self.cbo_task_status.blockSignals(True)
        self.cbo_task_priority.blockSignals(True)

        self.txt_task_search.clear()
        self.cbo_task_dept.setCurrentIndex(0)
        self.cbo_task_status.setCurrentIndex(0)
        self.cbo_task_priority.setCurrentIndex(0)

        self.txt_task_search.blockSignals(False)
        self.cbo_task_dept.blockSignals(False)
        self.cbo_task_status.blockSignals(False)
        self.cbo_task_priority.blockSignals(False)

        self.apply_tasks_filter()

    def on_task_row_selected(self):
        """Xử lý khi người dùng chọn một hàng trong bảng nhiệm vụ"""
        row = self.table_tasks.currentRow()
        if row >= 0:
            item = self.table_tasks.item(row, 0)
            if item:
                task = item.data(Qt.ItemDataRole.UserRole)
                if task:
                    self.display_task_detail(task)

    def display_task_detail(self, task):
        """Hiển thị thông tin chi tiết nhiệm vụ tại khung bên dưới"""
        code = task.get("code") or task.get("task_code") or "--"
        title = task.get("title") or "Nhiệm vụ không tên"
        dept = task.get("department") or "---"
        asg = task.get("assignee") or "---"
        coord = task.get("coordinators") or "(Không phân công phối hợp)"
        due = task.get("due_date") or "---"
        prog = task.get("progress", 0)
        source = task.get("source") or "---"
        st = task.get("status", "")
        prio = task.get("priority", "")
        report = task.get("report_content") or task.get("latest_report") or ""

        st_vn = "✅ ĐÃ HOÀN THÀNH" if st == "hoan_thanh" else ("🚨 QUÁ HẠN" if st == "qua_han" else "⏳ ĐANG THỰC HIỆN")
        prio_vn = "🔥 HỎA TỐC/KHẨN" if prio == "khan" else ("⚡ QUAN TRỌNG" if prio == "quan_trong" else "TIÊU CHUẨN")

        self.lbl_task_det_code.setText(f"MÃ NHIỆM VỤ: {code}  |  TRẠNG THÁI: {st_vn}  |  ƯU TIÊN: {prio_vn}")
        self.lbl_task_det_title.setText(title)

        info_text = (
            f"🏢 Đơn vị chủ trì: {dept}   |   👤 Người thực hiện: {asg}   |   🤝 Phối hợp: {coord}\n"
            f"📅 Thời hạn giải quyết: {due}   |   📊 Tiến độ hiện tại: {prog}%\n"
            f"📜 Văn bản căn cứ / Nguồn giao nhiệm vụ: {source}"
        )
        self.lbl_task_det_info.setText(info_text)

        if report:
            self.lbl_task_det_report.setText(f"📝 BÁO CÁO TIẾN ĐỘ GẦN NHẤT:\n{report}")
            self.lbl_task_det_report.setVisible(True)
        else:
            self.lbl_task_det_report.setVisible(False)

    def on_double_click_urgent_task(self, index):
        """Nhấp đúp chuột vào nhiệm vụ đôn đốc gấp để chuyển sang Tab Danh sách và tìm nhiệm vụ đó"""
        row = self.table_urgent_tasks.currentRow()
        if row < 0:
            return
        item = self.table_urgent_tasks.item(row, 0)
        if not item:
            return
        t = item.data(Qt.ItemDataRole.UserRole)
        if not t:
            return
        target_code = t.get("code") or t.get("task_code") or ""
        self.tabs_tasks.setCurrentIndex(1)
        self.txt_task_search.setText(target_code)

    def action_login_nhiemvu(self):
        """Xử lý đăng nhập tài khoản Hệ thống theo dõi nhiệm vụ qua Supabase"""
        email = self.txt_nhiemvu_email.text().strip()
        pwd = self.txt_nhiemvu_password.text().strip()

        if not email or not pwd:
            QMessageBox.warning(
                self, "Thiếu thông tin",
                "Vui lòng nhập Email và Mật khẩu tài khoản Hệ thống theo dõi nhiệm vụ!"
            )
            return

        self.status_bar.showMessage("Đang kết nối và xác thực với máy chủ nhiemvu.drvn.gov.vn...")
        ok, msg = nhiemvu.login_nhiemvu(email, pwd)
        if ok:
            self.lbl_nv_auth_status.setText(f"🟢 ĐÃ LƯU TÀI KHOẢN NHIỆM VỤ ({email})")
            self.lbl_nv_auth_status.setStyleSheet("color: #16a34a; font-size: 13px; font-weight: bold;")
            self.status_bar.showMessage("Đăng nhập Hệ thống nhiệm vụ thành công!")
            QMessageBox.information(
                self, "Đăng nhập thành công",
                f"✅ {msg}\n\nHệ thống sẽ bắt đầu đồng bộ danh mục nhiệm vụ từ máy chủ trực tuyến."
            )
            self.action_sync_nhiemvu()
        else:
            self.status_bar.showMessage("Đăng nhập Hệ thống nhiệm vụ thất bại.")
            QMessageBox.warning(self, "Đăng nhập thất bại", f"❌ {msg}")

    def action_sync_nhiemvu(self):
        """Đồng bộ dữ liệu nhiệm vụ trực tuyến"""
        self.status_bar.showMessage("Đang đồng bộ dữ liệu từ hệ thống theo dõi nhiệm vụ...")
        ok, msg = nhiemvu.sync_tasks_from_remote()
        self.refresh_tasks_view()
        self.status_bar.showMessage(msg)
        if ok:
            QMessageBox.information(self, "Đồng bộ nhiệm vụ", f"✅ {msg}")
        else:
            QMessageBox.information(
                self, "Thông tin đồng bộ",
                f"ℹ️ {msg}\n\nHiện tại ứng dụng đang hiển thị cơ sở dữ liệu nhiệm vụ nội bộ được lưu trong máy."
            )

    # =========================================================================
    # VIEW 5: CẤU HÌNH
    # =========================================================================
    def init_view_config(self):
        layout = QVBoxLayout(self.view_config)
        layout.setSpacing(12)

        # 1. KHAI BÁO TÀI KHOẢN & ĐĂNG NHẬP
        grp_auth = QGroupBox("1. KHAI BÁO TÀI KHOẢN & TRẠNG THÁI ĐĂNG NHẬP")
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

        btn_login = QPushButton("🔑 ĐĂNG NHẬP & KIỂM TRA KẾT NỐI")
        btn_login.setStyleSheet("background: #0284c7; color: white; padding: 8px 18px; border-radius: 4px; font-weight: bold;")
        btn_login.clicked.connect(self.action_login)

        form_auth.addRow("Trạng thái:", self.lbl_auth_status)
        form_auth.addRow("", self.lbl_auth_msg)
        form_auth.addRow("Tên đăng nhập:", self.txt_username)
        form_auth.addRow("Mật khẩu:", self.txt_password)
        form_auth.addRow("", self.chk_show_pass)
        form_auth.addRow("Họ và tên cán bộ:", self.txt_officer_name)
        form_auth.addRow("", btn_login)
        layout.addWidget(grp_auth)

        # 2. CẤU HÌNH THƯ MỤC LƯU NHANH
        grp_folder = QGroupBox("2. CẤU HÌNH THƯ MỤC LƯU NHANH TỆP ĐÍNH KÈM")
        grp_folder.setStyleSheet("QGroupBox { font-weight: bold; color: #16a34a; }")
        form_folder = QFormLayout(grp_folder)

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

        form_folder.addRow("Thư mục lưu:", fld_box)
        layout.addWidget(grp_folder)

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

    # =========================================================================
    # VIEW 6: QUẢN TRỊ VIÊN (CHỈ HIỂN THỊ KHI ĐĂNG NHẬP VỚI TÀI KHOẢN ADMIN)
    # =========================================================================
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

    # =========================================================================
    # HÀNH ĐỘNG DỮ LIỆU & LỌC NGÀY
    # =========================================================================
    def set_dates_today(self, dt_from, dt_to, callback):
        today = QDate.currentDate()
        dt_from.setDate(today)
        dt_to.setDate(today)
        callback()

    def set_dates_ndays(self, dt_from, dt_to, n, callback):
        today = QDate.currentDate()
        dt_from.setDate(today.addDays(-n))
        dt_to.setDate(today)
        callback()

    def set_dates_all(self, dt_from, dt_to, callback):
        dt_from.setDate(QDate(2020, 1, 1))
        dt_to.setDate(QDate(2030, 12, 31))
        callback()

    def apply_incoming_filter_dept(self):
        d_from = self.dt_from_inc_dept.date().toPyDate()
        d_to = self.dt_to_inc_dept.date().toPyDate()
        docs = db.get_incoming_docs_filtered(scope="department", from_date=d_from, to_date=d_to)
        if not docs:
            try:
                self.status_bar.showMessage(f"Đang đồng bộ công văn đến của Phòng từ {d_from.strftime('%d/%m/%Y')} đến {d_to.strftime('%d/%m/%Y')}...")
                self.crawler.fetch_incoming_docs_department(d_from, d_to)
                docs = db.get_incoming_docs_filtered(scope="department", from_date=d_from, to_date=d_to)
                self.status_bar.showMessage("Đã đồng bộ xong dữ liệu công văn đến của Phòng.")
            except Exception:
                pass
        self.render_incoming_table(self.table_inc_dept, docs, is_dept=True)

    def apply_incoming_filter_personal(self):
        d_from = self.dt_from_inc_pers.date().toPyDate()
        d_to = self.dt_to_inc_pers.date().toPyDate()
        docs = db.get_incoming_docs_filtered(scope="personal", from_date=d_from, to_date=d_to)
        if not docs:
            try:
                self.status_bar.showMessage("Đang đồng bộ công văn đến cá nhân...")
                self.crawler.fetch_incoming_docs_personal(d_from, d_to)
                docs = db.get_incoming_docs_filtered(scope="personal", from_date=d_from, to_date=d_to)
                self.status_bar.showMessage("Đã đồng bộ xong dữ liệu công văn đến cá nhân.")
            except Exception:
                pass
        self.render_incoming_table(self.table_inc_pers, docs, is_dept=False)

    def create_phan_loai_item(self, phan_loai_text):
        pl = (phan_loai_text or "").strip()
        item = QTableWidgetItem()
        f = item.font()
        f.setBold(True)
        item.setFont(f)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if "phải xử lý" in pl.lower():
            item.setText("⚡ Phải xử lý")
            item.setForeground(QColor("#b91c1c"))
            item.setBackground(QColor("#fef2f2"))
            item.setToolTip("Công văn đến phải xử lý (Có thời hạn giải quyết)")
        elif "lưu chung" in pl.lower():
            item.setText("📂 Lưu chung")
            item.setForeground(QColor("#6d28d9"))
            item.setBackground(QColor("#f5f3ff"))
            item.setToolTip("Lưu chung đơn vị")
        else:
            item.setText("👁️ Để biết & lưu")
            item.setForeground(QColor("#0369a1"))
            item.setBackground(QColor("#f0f9ff"))
            item.setToolTip("Nhận để biết và lưu (Không phát sinh hạn)")
        return item

    def get_doc_from_table_row(self, table, row):
        if row < 0 or row >= table.rowCount():
            return None
        for col in range(table.columnCount()):
            item = table.item(row, col)
            if item:
                d = item.data(Qt.ItemDataRole.UserRole)
                if d and isinstance(d, dict):
                    return d
        return None

    def render_incoming_table(self, table, docs, is_dept=False):
        table.setRowCount(len(docs))
        warning_days = db.get_warning_days()
        for row, doc in enumerate(docs):
            col = 0
            if not is_dept:
                is_un = (doc.get("is_read") == 0)
                item_st = QTableWidgetItem("🔵 Mới" if is_un else "⚪ Đã xem")
                if is_un:
                    item_st.setForeground(QColor("#0284c7"))
                    f = item_st.font()
                    f.setBold(True)
                    item_st.setFont(f)
                item_st.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item_st.setData(Qt.ItemDataRole.UserRole, doc)
                table.setItem(row, col, item_st)
                col += 1

            # Phân loại
            item_pl = self.create_phan_loai_item(doc.get("phan_loai_xu_ly", ""))
            item_pl.setData(Qt.ItemDataRole.UserRole, doc)
            table.setItem(row, col, item_pl)
            col += 1

            # Số đến
            sd_val = str(doc.get("so_den", "") or "").strip()
            item_sd = QTableWidgetItem(sd_val if sd_val else "-")
            item_sd.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_sd.setData(Qt.ItemDataRole.UserRole, doc)
            table.setItem(row, col, item_sd)
            col += 1

            # Số/Ký hiệu
            item_skh = QTableWidgetItem(doc.get("so_ky_hieu", ""))
            item_skh.setData(Qt.ItemDataRole.UserRole, doc)
            table.setItem(row, col, item_skh)
            col += 1

            # Ngày ban hành
            item_nbh = QTableWidgetItem(doc.get("ngay_ban_hanh", ""))
            item_nbh.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_nbh.setData(Qt.ItemDataRole.UserRole, doc)
            table.setItem(row, col, item_nbh)
            col += 1

            # Trích yếu
            item_ty = QTableWidgetItem(doc.get("trich_yeu", ""))
            item_ty.setData(Qt.ItemDataRole.UserRole, doc)
            table.setItem(row, col, item_ty)
            col += 1

            # Ngày đến
            item_nd = QTableWidgetItem(doc.get("ngay_den", ""))
            item_nd.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_nd.setData(Qt.ItemDataRole.UserRole, doc)
            table.setItem(row, col, item_nd)
            col += 1

            # Hạn xử lý
            han_str = doc.get("han_xu_ly", "")
            item_han = QTableWidgetItem(han_str)
            item_han.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            days = doc.get("days_remaining", 999)
            if days != 999 and han_str:
                if days < 0:
                    item_han.setBackground(QColor("#fee2e2"))
                    item_han.setForeground(QColor("#b91c1c"))
                    item_han.setText(f"{han_str} (Quá hạn {abs(days)}d)")
                    f = item_han.font(); f.setBold(True); item_han.setFont(f)
                elif days == 0:
                    item_han.setBackground(QColor("#fee2e2"))
                    item_han.setForeground(QColor("#b91c1c"))
                    item_han.setText(f"{han_str} (Hôm nay)")
                    f = item_han.font(); f.setBold(True); item_han.setFont(f)
                elif days <= warning_days:
                    item_han.setBackground(QColor("#fef3c7"))
                    item_han.setForeground(QColor("#b45309"))
                    item_han.setText(f"{han_str} (Còn {days}d)")
                    f = item_han.font(); f.setBold(True); item_han.setFont(f)
            item_han.setData(Qt.ItemDataRole.UserRole, doc)
            table.setItem(row, col, item_han)
            col += 1

            # Xử lý chính
            xlc_name = doc.get("xu_ly_chinh", "").strip() or "---"
            item_main = QTableWidgetItem(xlc_name)
            f_main = item_main.font(); f_main.setBold(True); item_main.setFont(f_main)
            item_main.setForeground(QColor("#0f172a"))
            item_main.setData(Qt.ItemDataRole.UserRole, doc)
            table.setItem(row, col, item_main)
            col += 1

            # Phối hợp
            ph_name = doc.get("phoi_hop", "").strip()
            item_sub = QTableWidgetItem(ph_name if ph_name else "---")
            if not ph_name:
                item_sub.setForeground(QColor("#94a3b8"))
            else:
                item_sub.setForeground(QColor("#334155"))
            item_sub.setData(Qt.ItemDataRole.UserRole, doc)
            table.setItem(row, col, item_sub)
            col += 1

            # Chỉ đạo
            item_cd = QTableWidgetItem(doc.get("chi_dao", ""))
            item_cd.setData(Qt.ItemDataRole.UserRole, doc)
            table.setItem(row, col, item_cd)
            col += 1

    def apply_outgoing_filter_dept(self):
        d_from = self.dt_from_out_dept.date().toPyDate()
        d_to = self.dt_to_out_dept.date().toPyDate()
        docs = db.get_outgoing_docs_filtered(scope="department", from_date=d_from, to_date=d_to)
        if not docs:
            try:
                self.status_bar.showMessage(f"Đang đồng bộ công văn đi của Phòng từ {d_from.strftime('%d/%m/%Y')} đến {d_to.strftime('%d/%m/%Y')}...")
                self.crawler.fetch_outgoing_docs_department(d_from, d_to)
                docs = db.get_outgoing_docs_filtered(scope="department", from_date=d_from, to_date=d_to)
                self.status_bar.showMessage("Đã đồng bộ xong dữ liệu công văn đi của Phòng.")
            except Exception:
                pass
        self.table_out_dept.setRowCount(len(docs))
        for row, doc in enumerate(docs):
            self.table_out_dept.setItem(row, 0, QTableWidgetItem(doc.get("so_trinh_ky", "")))
            self.table_out_dept.setItem(row, 1, QTableWidgetItem(doc.get("so_di", "")))
            self.table_out_dept.setItem(row, 2, QTableWidgetItem(doc.get("ngay_ban_hanh", "")))
            self.table_out_dept.setItem(row, 3, QTableWidgetItem(doc.get("trich_yeu", "")))
            self.table_out_dept.setItem(row, 4, QTableWidgetItem(doc.get("nguoi_ky", "")))
            self.table_out_dept.setItem(row, 5, QTableWidgetItem(doc.get("soan_thao", "")))
            self.table_out_dept.setItem(row, 6, QTableWidgetItem(doc.get("cv_tra_loi", "")))

    def apply_outgoing_filter_personal(self):
        d_from = self.dt_from_out_pers.date().toPyDate()
        d_to = self.dt_to_out_pers.date().toPyDate()
        officer = db.get_officer_name()
        docs = db.get_outgoing_docs_filtered(scope="personal", from_date=d_from, to_date=d_to, officer_name=officer)
        if not docs:
            try:
                self.status_bar.showMessage(f"Đang đồng bộ công văn đi cá nhân từ {d_from.strftime('%d/%m/%Y')} đến {d_to.strftime('%d/%m/%Y')}...")
                self.crawler.fetch_outgoing_docs_personal(d_from, d_to)
                docs = db.get_outgoing_docs_filtered(scope="personal", from_date=d_from, to_date=d_to, officer_name=officer)
                self.status_bar.showMessage("Đã đồng bộ xong dữ liệu công văn đi cá nhân.")
            except Exception:
                pass
        self.table_out_pers.setRowCount(len(docs))
        for row, doc in enumerate(docs):
            self.table_out_pers.setItem(row, 0, QTableWidgetItem(doc.get("so_di", "")))
            self.table_out_pers.setItem(row, 1, QTableWidgetItem(doc.get("so_trinh_ky", "")))

            item_ty = QTableWidgetItem(doc.get("trich_yeu", ""))
            item_ty.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_out_pers.setItem(row, 2, item_ty)

            self.table_out_pers.setItem(row, 3, QTableWidgetItem(doc.get("ngay_ban_hanh") or doc.get("ngay_tao", "")))

            st = doc.get("trang_thai", "Đã xử lý")
            item_st = QTableWidgetItem(st)
            if "ban hành" in st.lower() or "phát hành" in st.lower():
                item_st.setBackground(QColor("#f0fdf4"))
                item_st.setForeground(QColor("#16a34a"))
            elif "chờ" in st.lower() or "trình ký" in st.lower():
                item_st.setBackground(QColor("#fffbeb"))
                item_st.setForeground(QColor("#ea580c"))
            else:
                item_st.setBackground(QColor("#f0f9ff"))
                item_st.setForeground(QColor("#0284c7"))
            font = item_st.font()
            font.setBold(True)
            item_st.setFont(font)
            self.table_out_pers.setItem(row, 4, item_st)

            self.table_out_pers.setItem(row, 5, QTableWidgetItem(doc.get("nguoi_ky", "")))
            self.table_out_pers.setItem(row, 6, QTableWidgetItem(doc.get("soan_thao", "")))
            self.table_out_pers.setItem(row, 7, QTableWidgetItem(doc.get("cv_tra_loi", "")))

    def on_double_click_outgoing_personal(self, index):
        row = index.row()
        if row >= 0:
            item = self.table_out_pers.item(row, 2)
            if item:
                doc = item.data(Qt.ItemDataRole.UserRole)
                if doc:
                    target_url = doc.get("view_url") or doc.get("download_url")
                    if target_url:
                        webbrowser.open(target_url)
                    else:
                        webbrowser.open("https://congvan.drvn.gov.vn/doc/view/shipdoc-send")

    def refresh_outgoing_processing_table(self):
        docs = db.get_outgoing_docs_filtered(scope="processing")
        if not docs:
            docs = db.get_outgoing_docs_filtered(scope="department")
        self.table_out_proc.setRowCount(len(docs))
        for row, doc in enumerate(docs):
            self.table_out_proc.setItem(row, 0, QTableWidgetItem(doc.get("so_trinh_ky", "")))
            self.table_out_proc.setItem(row, 1, QTableWidgetItem(doc.get("so_di", "")))
            self.table_out_proc.setItem(row, 2, QTableWidgetItem(doc.get("trich_yeu", "")))
            self.table_out_proc.setItem(row, 3, QTableWidgetItem(doc.get("nguoi_ky", "")))
            self.table_out_proc.setItem(row, 4, QTableWidgetItem(doc.get("soan_thao", "")))

            # Trạng thái xử lý nổi bật
            status = doc.get("trang_thai", "Đang xử lý")
            item_st = QTableWidgetItem(status)
            if "phát hành" in status.lower():
                item_st.setBackground(QColor("#f0fdf4"))
                item_st.setForeground(QColor("#16a34a"))
            else:
                item_st.setBackground(QColor("#fffbeb"))
                item_st.setForeground(QColor("#b45309"))
            f = item_st.font()
            f.setBold(True)
            item_st.setFont(f)
            self.table_out_proc.setItem(row, 5, item_st)

    def refresh_quick_alerts(self):
        # 1. Cập nhật công văn đến CÁ NHÂN mới chưa đọc
        new_docs = db.get_incoming_docs_filtered(scope="personal", unread_only=True)
        self.table_quick_new.setRowCount(len(new_docs))
        for row, doc in enumerate(new_docs):
            item_st = QTableWidgetItem("🔵 Mới")
            item_st.setForeground(QColor("#0284c7"))
            f = item_st.font(); f.setBold(True); item_st.setFont(f)
            item_st.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_st.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_new.setItem(row, 0, item_st)

            item_pl = self.create_phan_loai_item(doc.get("phan_loai_xu_ly", ""))
            item_pl.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_new.setItem(row, 1, item_pl)

            item_sd = QTableWidgetItem(str(doc.get("so_den", "")))
            item_sd.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_sd.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_new.setItem(row, 2, item_sd)

            item_skh = QTableWidgetItem(doc.get("so_ky_hieu", ""))
            item_skh.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_new.setItem(row, 3, item_skh)

            item_nd = QTableWidgetItem(doc.get("ngay_den", ""))
            item_nd.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_nd.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_new.setItem(row, 4, item_nd)

            item_ty = QTableWidgetItem(doc.get("trich_yeu", ""))
            item_ty.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_new.setItem(row, 5, item_ty)

            # Chuyên viên xử lý chính
            xlc_name = doc.get("xu_ly_chinh", "").strip() or "---"
            item_main = QTableWidgetItem(xlc_name)
            f_main = item_main.font(); f_main.setBold(True); item_main.setFont(f_main)
            item_main.setForeground(QColor("#0f172a"))
            item_main.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_new.setItem(row, 6, item_main)

            # Chuyên viên phối hợp
            ph_name = doc.get("phoi_hop", "").strip()
            item_sub = QTableWidgetItem(ph_name if ph_name else "---")
            if not ph_name:
                item_sub.setForeground(QColor("#94a3b8"))
            else:
                item_sub.setForeground(QColor("#334155"))
            item_sub.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_new.setItem(row, 7, item_sub)

            # Hạn xử lý
            han_txt = doc.get("han_xu_ly", "").strip() or "---"
            item_han = QTableWidgetItem(han_txt)
            item_han.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if han_txt != "---":
                f_h = item_han.font(); f_h.setBold(True); item_han.setFont(f_h)
                item_han.setForeground(QColor("#dc2626"))
            item_han.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_new.setItem(row, 8, item_han)

        # 2. Cảnh báo CÁ NHÂN gần đến hạn & quá hạn theo cấu hình số ngày
        warning_days = db.get_warning_days()
        if hasattr(self, "grp_urgent"):
            self.grp_urgent.setTitle(f"⏳ 2. CẢNH BÁO CÔNG VĂN CÁ NHÂN GẦN ĐẾN HẠN (≤ {warning_days} NGÀY) & QUÁ HẠN")

        urgent_docs = db.get_urgent_docs(scope="personal")
        self.table_quick_urgent.setRowCount(len(urgent_docs))
        for row, doc in enumerate(urgent_docs):
            days = doc.get("days_remaining", 999)
            if days < 0:
                lvl = f"🔴 Quá hạn ({abs(days)}d)"
                bg = QColor("#fee2e2")
                fg = QColor("#b91c1c")
            elif days == 0:
                lvl = "🔴 Hết hạn HÔM NAY"
                bg = QColor("#fef2f2")
                fg = QColor("#dc2626")
            else:
                lvl = f"🟡 Khẩn ({days}d)"
                bg = QColor("#fef3c7")
                fg = QColor("#b45309")

            itm_lvl = QTableWidgetItem(lvl)
            itm_lvl.setBackground(bg)
            itm_lvl.setForeground(fg)
            f_l = itm_lvl.font(); f_l.setBold(True); itm_lvl.setFont(f_l)
            itm_lvl.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            itm_lvl.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_urgent.setItem(row, 0, itm_lvl)

            itm_pl = self.create_phan_loai_item(doc.get("phan_loai_xu_ly", ""))
            itm_pl.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_urgent.setItem(row, 1, itm_pl)

            itm_days = QTableWidgetItem(f"{days} ngày" if days != 999 else "---")
            itm_days.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            itm_days.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_urgent.setItem(row, 2, itm_days)

            itm_han = QTableWidgetItem(doc.get("han_xu_ly", ""))
            itm_han.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            itm_han.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_urgent.setItem(row, 3, itm_han)

            itm_code = QTableWidgetItem(f"{doc.get('so_den')} - {doc.get('so_ky_hieu')}")
            itm_code.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_urgent.setItem(row, 4, item_code if 'item_code' in locals() else itm_code)

            itm_ty = QTableWidgetItem(doc.get("trich_yeu", ""))
            itm_ty.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_urgent.setItem(row, 5, itm_ty)

            # Xử lý chính
            xlc_name = doc.get("xu_ly_chinh", "").strip() or "---"
            itm_main = QTableWidgetItem(xlc_name)
            f_m = itm_main.font(); f_m.setBold(True); itm_main.setFont(f_m)
            itm_main.setForeground(QColor("#0f172a"))
            itm_main.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_urgent.setItem(row, 6, itm_main)

            # Phối hợp
            ph_name = doc.get("phoi_hop", "").strip()
            itm_sub = QTableWidgetItem(ph_name if ph_name else "---")
            if not ph_name:
                itm_sub.setForeground(QColor("#94a3b8"))
            else:
                itm_sub.setForeground(QColor("#334155"))
            itm_sub.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_urgent.setItem(row, 7, itm_sub)

        # 3. Cập nhật công văn đi CÁ NHÂN
        out_docs = db.get_outgoing_status_updates(scope="personal")
        self.table_quick_out.setRowCount(len(out_docs))
        for row, doc in enumerate(out_docs):
            item_out = QTableWidgetItem(doc.get("so_di") or doc.get("so_trinh_ky", ""))
            item_out.setData(Qt.ItemDataRole.UserRole, doc)
            self.table_quick_out.setItem(row, 0, item_out)
            self.table_quick_out.setItem(row, 1, QTableWidgetItem(doc.get("trich_yeu", "")))
            self.table_quick_out.setItem(row, 2, QTableWidgetItem(doc.get("ngay_ban_hanh") or doc.get("ngay_tao", "")))
            st_item = QTableWidgetItem(doc.get("trang_thai", ""))
            st_item.setForeground(QColor("#0284c7"))
            self.table_quick_out.setItem(row, 3, st_item)

    def refresh_all_data(self):
        self.refresh_quick_alerts()
        self.apply_incoming_filter_dept()
        self.apply_incoming_filter_personal()
        self.apply_outgoing_filter_dept()
        self.apply_outgoing_filter_personal()
        self.refresh_outgoing_processing_table()
        if hasattr(self, "table_tasks"):
            self.refresh_tasks_view()
        self.update_badges()

    def update_badges(self):
        counts = db.get_counts()
        self.badge_unread.setText(f"📥 Mới chưa đọc: {counts['unread']}")
        self.badge_urgent.setText(f"⏳ Sắp hết hạn: {counts['urgent']}")
        if hasattr(self, "tray_icon"):
            self.tray_icon.setToolTip(f"Trợ lý Công văn DRVN\nChưa đọc: {counts['unread']} | Sắp đến hạn: {counts['urgent']}")

    # =========================================================================
    # XEM CHI TIẾT & TỆP ĐÍNH KÈM (TOÀN BỘ CÁC TỆP & TRÌNH ĐỌC PDF SIÊU TỐC)
    # =========================================================================
    def display_doc_detail(self, doc):
        self.selected_doc_for_detail = doc
        self.lbl_det_cuc.setText(doc.get("lanh_dao_cuc") or "---")
        self.lbl_det_phong.setText(doc.get("lanh_dao_phong") or "---")
        self.lbl_det_main.setText(doc.get("xu_ly_chinh") or "---")
        self.lbl_det_sub.setText(doc.get("phoi_hop") or "(Không phân công phối hợp)")

        pl = doc.get("phan_loai_xu_ly", "").strip()
        if not pl:
            pl = "Công văn đến phải xử lý" if doc.get("han_xu_ly") else "Nhận để biết và lưu"
        if "phải xử lý" in pl.lower():
            self.lbl_det_meta_phanloai.setText("⚡ Công văn đến phải xử lý (Có hạn giải quyết)")
            self.lbl_det_meta_phanloai.setStyleSheet("color: #dc2626; font-weight: bold; font-size: 13px;")
        elif "lưu chung" in pl.lower():
            self.lbl_det_meta_phanloai.setText("📂 Lưu chung đơn vị")
            self.lbl_det_meta_phanloai.setStyleSheet("color: #7c3aed; font-weight: bold; font-size: 13px;")
        else:
            self.lbl_det_meta_phanloai.setText("👁️ Nhận để biết và lưu")
            self.lbl_det_meta_phanloai.setStyleSheet("color: #0284c7; font-weight: bold; font-size: 13px;")

        self.lbl_det_meta_code.setText(f"Số đến: {doc.get('so_den')} | Số/Ký hiệu: {doc.get('so_ky_hieu')}")
        self.lbl_det_meta_dates.setText(f"Ngày đến: {doc.get('ngay_den') or doc.get('ngay_ban_hanh')} | Hạn xử lý: {doc.get('han_xu_ly') or 'Không ghi hạn'}")
        self.lbl_det_meta_trichyeu.setText(doc.get("trich_yeu", "---"))

        # 1. Trích xuất tất cả các tệp đính kèm thực tế
        attachments = db.get_doc_attachments_raw(doc)

        # Nếu trong DB chưa có danh sách tệp đầy đủ mà có link chi tiết, cào bổ sung ngay
        if not attachments and doc.get("detail_url"):
            try:
                self.status_bar.showMessage("Đang lấy danh sách toàn bộ tệp đính kèm và phân loại...")
                attachments, pl_from_detail = self.crawler.fetch_doc_details_and_attachments(doc["detail_url"], doc.get("han_xu_ly", ""))
                if attachments and doc.get("id"):
                    db.update_doc_attachments(doc["id"], attachments)
                if pl_from_detail and doc.get("id"):
                    db.update_doc_phan_loai(doc["id"], pl_from_detail)
                    doc["phan_loai_xu_ly"] = pl_from_detail
                    if "phải xử lý" in pl_from_detail.lower():
                        self.lbl_det_meta_phanloai.setText("⚡ Công văn đến phải xử lý (Có hạn giải quyết)")
                        self.lbl_det_meta_phanloai.setStyleSheet("color: #dc2626; font-weight: bold; font-size: 13px;")
                    elif "lưu chung" in pl_from_detail.lower():
                        self.lbl_det_meta_phanloai.setText("📂 Lưu chung đơn vị")
                        self.lbl_det_meta_phanloai.setStyleSheet("color: #7c3aed; font-weight: bold; font-size: 13px;")
                    else:
                        self.lbl_det_meta_phanloai.setText("👁️ Nhận để biết và lưu")
                        self.lbl_det_meta_phanloai.setStyleSheet("color: #0284c7; font-weight: bold; font-size: 13px;")
            except Exception:
                pass

        if not attachments:
            attachments = db.get_doc_attachments(doc)

        # 2. Hiển thị toàn bộ danh sách tệp lên bảng table_attachments
        self.table_attachments.blockSignals(True)
        self.table_attachments.setRowCount(len(attachments))
        for row, att in enumerate(attachments):
            f_name = att.get("name") or f"Tệp đính kèm {row + 1}.pdf"
            f_info = att.get("info") or "Tệp đính kèm"
            item_name = QTableWidgetItem(f"📎 {f_name}")
            item_name.setData(Qt.ItemDataRole.UserRole, att)
            item_info = QTableWidgetItem(f_info)
            self.table_attachments.setItem(row, 0, item_name)
            self.table_attachments.setItem(row, 1, item_info)
        self.table_attachments.clearSelection()
        self.table_attachments.blockSignals(False)

        # 3. Yêu cầu 1: Khi mở công văn, KHÔNG tự động mở file ngay.
        # Chỉ hiển thị danh sách và hướng dẫn, chỉ mở khi người dùng bấm vào một file cụ thể
        self.current_reading_attach = None
        self.btn_attach_read.setEnabled(False)
        self.btn_attach_web.setEnabled(False)
        self.btn_attach_save.setEnabled(False)
        self.btn_attach_save_all.setEnabled(len(attachments) > 0)

        if attachments:
            self.unload_pdf_reader(f"📄 Công văn này có {len(attachments)} tệp đính kèm.\n\n👉 Vui lòng nhấp đúp hoặc bấm chọn một tệp trong bảng bên trái để mở đọc nội dung.")
        else:
            self.unload_pdf_reader("Công văn này không có tệp đính kèm trực tiếp.")

        # Chuyển sang Tab Chi tiết
        self.sidebar.setCurrentRow(1)
        self.tabs_incoming.setCurrentIndex(2)

    def on_double_click_quick_new(self, index):
        row = index.row()
        doc = self.get_doc_from_table_row(self.table_quick_new, row)
        if doc:
            self.display_doc_detail(doc)

    def on_double_click_quick_urgent(self, index):
        row = index.row()
        doc = self.get_doc_from_table_row(self.table_quick_urgent, row)
        if doc:
            self.display_doc_detail(doc)

    def on_double_click_quick_out(self, index):
        self.sidebar.setCurrentRow(2)
        self.tabs_outgoing.setCurrentIndex(1)

    def mark_quick_new_as_read(self):
        row = self.table_quick_new.currentRow()
        if row >= 0:
            doc = self.get_doc_from_table_row(self.table_quick_new, row)
            if doc:
                db.mark_as_read(doc["id"])
                self.refresh_all_data()

    def open_detail_from_quick_new(self):
        row = self.table_quick_new.currentRow()
        if row >= 0:
            doc = self.get_doc_from_table_row(self.table_quick_new, row)
            if doc:
                self.display_doc_detail(doc)

    def open_detail_from_dept(self):
        row = self.table_inc_dept.currentRow()
        if row >= 0:
            doc = self.get_doc_from_table_row(self.table_inc_dept, row)
            if doc:
                self.display_doc_detail(doc)

    def open_detail_from_personal(self):
        row = self.table_inc_pers.currentRow()
        if row >= 0:
            doc = self.get_doc_from_table_row(self.table_inc_pers, row)
            if doc:
                self.display_doc_detail(doc)

    def on_attachment_item_clicked(self, item):
        row = item.row()
        item0 = self.table_attachments.item(row, 0)
        if item0:
            att = item0.data(Qt.ItemDataRole.UserRole)
            if att:
                self.btn_attach_read.setEnabled(True)
                self.btn_attach_web.setEnabled(True)
                self.btn_attach_save.setEnabled(True)
                if att != getattr(self, "current_reading_attach", None):
                    self.load_attachment_into_reader(att)

    def on_attachment_selection_changed(self):
        row = self.table_attachments.currentRow()
        if row >= 0:
            item = self.table_attachments.item(row, 0)
            if item:
                att = item.data(Qt.ItemDataRole.UserRole)
                if att:
                    self.btn_attach_read.setEnabled(True)
                    self.btn_attach_web.setEnabled(True)
                    self.btn_attach_save.setEnabled(True)
                    if att != getattr(self, "current_reading_attach", None):
                        self.load_attachment_into_reader(att)

    def on_attachment_double_clicked(self, index):
        row = index.row()
        item = self.table_attachments.item(row, 0)
        if item:
            att = item.data(Qt.ItemDataRole.UserRole)
            if att:
                self.btn_attach_read.setEnabled(True)
                self.btn_attach_web.setEnabled(True)
                self.btn_attach_save.setEnabled(True)
                self.load_attachment_into_reader(att)

    def load_attachment_into_reader(self, attach):
        self.current_reading_attach = attach
        raw_name = attach.get("name", "van_ban.pdf")
        self.lbl_pdf_title.setText(f"📖 {raw_name}")

        url = attach.get("download_url") or attach.get("view_url")
        if not url:
            self.unload_pdf_reader("Tệp đính kèm này không có liên kết tải xuống.")
            return

        doc = getattr(self, "selected_doc_for_detail", {}) or {}
        so_den = str(doc.get("so_den", "CV"))
        safe_file_name = re.sub(r'[\\/*?:"<>|]', '_', f"CV_{so_den}_{raw_name}")
        temp_dir = tempfile.gettempdir()
        dest = os.path.join(temp_dir, safe_file_name)

        # Mở tức thì nếu file đã được tải trước đó
        if not (os.path.exists(dest) and os.path.getsize(dest) > 0):
            self.status_bar.showMessage(f"Đang tải {raw_name} để xem nhanh...")
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                ok, err = self.crawler.download_file(url, dest)
            except Exception as e:
                ok, err = False, str(e)
            finally:
                QApplication.restoreOverrideCursor()

            if not (ok and os.path.exists(dest)):
                self.status_bar.showMessage("Không thể tải tệp để đọc trực tiếp.")
                self.unload_pdf_reader(f"Không thể tải tệp để đọc trực tiếp:\n{err}\n\nBạn có thể bấm 'Mở xem trên Web (Chrome)' để xem trực tiếp.")
                return

        self.current_pdf_local_path = dest
        try:
            # Mở bằng PyMuPDF - hỗ trợ 100% chữ ký số, con dấu đỏ và số hiệu
            if hasattr(self, "pdf_doc") and self.pdf_doc:
                try:
                    self.pdf_doc.close()
                except Exception:
                    pass

            self.pdf_doc = pymupdf.open(dest)
            self.pdf_total_pages = len(self.pdf_doc)
            self.pdf_current_page = 0
            self.pdf_zoom = 1.0
            self.stack_pdf.setCurrentIndex(1)
            self.action_pdf_fit_width()
            self.status_bar.showMessage(f"Đang xem: {raw_name} ({self.pdf_total_pages} trang)")
        except Exception as e:
            self.unload_pdf_reader(f"Lỗi khi đọc file PDF:\n{str(e)}")

    def render_current_pdf_page(self):
        if not hasattr(self, "pdf_doc") or not self.pdf_doc:
            return
        if self.pdf_current_page < 0 or self.pdf_current_page >= self.pdf_total_pages:
            return

        try:
            page = self.pdf_doc[self.pdf_current_page]
            dpi = max(72, int(144 * self.pdf_zoom))
            pix = page.get_pixmap(dpi=dpi)
            qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
            self.lbl_pdf_page_render.setPixmap(pixmap)
            self.lbl_pdf_page_render.adjustSize()

            self.lbl_pdf_page.setText(f"Trang {self.pdf_current_page + 1} / {self.pdf_total_pages}")
            self.lbl_pdf_zoom.setText(f"{int(self.pdf_zoom * 100)}%")
            self.btn_pdf_prev.setEnabled(self.pdf_current_page > 0)
            self.btn_pdf_next.setEnabled(self.pdf_current_page < self.pdf_total_pages - 1)
        except Exception as e:
            self.status_bar.showMessage(f"Lỗi hiển thị trang: {str(e)}")

    def unload_pdf_reader(self, message):
        if hasattr(self, "pdf_doc") and self.pdf_doc:
            try:
                self.pdf_doc.close()
            except Exception:
                pass
            self.pdf_doc = None
        self.pdf_total_pages = 0
        self.pdf_current_page = 0
        self.stack_pdf.setCurrentIndex(0)
        self.lbl_pdf_placeholder.setText(message)
        self.lbl_pdf_title.setText("📖 Trình đọc văn bản nhanh (PDF)")
        self.lbl_pdf_page.setText("Trang --/--")
        self.lbl_pdf_zoom.setText("100%")
        self.btn_pdf_prev.setEnabled(False)
        self.btn_pdf_next.setEnabled(False)
        self.current_reading_attach = None
        self.current_pdf_local_path = None

    def action_pdf_prev_page(self):
        if hasattr(self, "pdf_doc") and self.pdf_doc and self.pdf_current_page > 0:
            self.pdf_current_page -= 1
            self.render_current_pdf_page()
            if hasattr(self, "scroll_pdf_viewer"):
                self.scroll_pdf_viewer.verticalScrollBar().setValue(0)

    def action_pdf_next_page(self):
        if hasattr(self, "pdf_doc") and self.pdf_doc and self.pdf_current_page < self.pdf_total_pages - 1:
            self.pdf_current_page += 1
            self.render_current_pdf_page()
            if hasattr(self, "scroll_pdf_viewer"):
                self.scroll_pdf_viewer.verticalScrollBar().setValue(0)

    def action_pdf_zoom_in(self):
        if hasattr(self, "pdf_doc") and self.pdf_doc:
            self.pdf_zoom = min(3.5, self.pdf_zoom * 1.25)
            self.render_current_pdf_page()

    def action_pdf_zoom_out(self):
        if hasattr(self, "pdf_doc") and self.pdf_doc:
            self.pdf_zoom = max(0.4, self.pdf_zoom / 1.25)
            self.render_current_pdf_page()

    def action_pdf_fit_width(self):
        if hasattr(self, "pdf_doc") and self.pdf_doc and hasattr(self, "scroll_pdf_viewer"):
            viewport_w = self.scroll_pdf_viewer.viewport().width() - 40
            if viewport_w > 100:
                page = self.pdf_doc[self.pdf_current_page]
                base_w = page.rect.width * 2  # 144 DPI
                if base_w > 0:
                    self.pdf_zoom = max(0.4, min(3.0, viewport_w / base_w))
            self.render_current_pdf_page()

    def action_pdf_open_external(self):
        if hasattr(self, "current_pdf_local_path") and self.current_pdf_local_path and os.path.exists(self.current_pdf_local_path):
            try:
                os.startfile(self.current_pdf_local_path)
            except Exception:
                webbrowser.open(self.current_pdf_local_path)
        elif hasattr(self, "current_reading_attach") and self.current_reading_attach:
            url = self.current_reading_attach.get("view_url") or self.current_reading_attach.get("download_url")
            if url:
                webbrowser.open(url)

    def action_read_selected_attachment(self):
        row = self.table_attachments.currentRow()
        if row < 0:
            QMessageBox.information(self, "Thông báo", "Vui lòng chọn một tệp trong danh sách để đọc!")
            return
        item = self.table_attachments.item(row, 0)
        if item:
            att = item.data(Qt.ItemDataRole.UserRole)
            if att:
                self.load_attachment_into_reader(att)

    def action_open_web_selected_attachment(self):
        row = self.table_attachments.currentRow()
        if row < 0:
            QMessageBox.information(self, "Thông báo", "Vui lòng chọn một tệp trong danh sách để mở trên web!")
            return
        item = self.table_attachments.item(row, 0)
        if item:
            att = item.data(Qt.ItemDataRole.UserRole)
            url = att.get("view_url") or att.get("download_url")
            if url:
                self.status_bar.showMessage("Đang mở tệp trên trình duyệt web...")
                webbrowser.open(url)
            else:
                QMessageBox.warning(self, "Không có liên kết", "Tệp này không có đường dẫn xem trực tuyến!")

    def action_save_selected_attachment(self):
        row = self.table_attachments.currentRow()
        if row < 0:
            QMessageBox.information(self, "Thông báo", "Vui lòng chọn một tệp trong danh sách để tải về!")
            return
        item = self.table_attachments.item(row, 0)
        if not item:
            return
        att = item.data(Qt.ItemDataRole.UserRole)
        url = att.get("download_url") or att.get("view_url")
        if not url:
            QMessageBox.warning(self, "Không có file", "Không tìm thấy đường dẫn tải về của tệp này!")
            return

        folder = db.get_setting("save_folder", db.DEFAULT_SAVE_FOLDER)
        os.makedirs(folder, exist_ok=True)
        doc = getattr(self, "selected_doc_for_detail", {}) or {}
        so_den = str(doc.get("so_den", "CV"))
        raw_name = att.get("name", "document.pdf")
        safe_name = re.sub(r'[\\/*?:"<>|]', '_', f"CV_{so_den}_{raw_name}")
        dest = os.path.join(folder, safe_name)

        self.status_bar.showMessage(f"Đang lưu {raw_name}...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            ok, res = self.crawler.download_file(url, dest)
        except Exception as e:
            ok, res = False, str(e)
        finally:
            QApplication.restoreOverrideCursor()

        if ok and os.path.exists(dest):
            ans = QMessageBox.question(
                self, "Đã lưu thành công",
                f"✅ Đã lưu tệp thành công vào thư mục cấu hình:\n{dest}\n\nBạn có muốn mở thư mục ngay không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ans == QMessageBox.StandardButton.Yes:
                try:
                    os.startfile(folder)
                except Exception:
                    pass
        else:
            QMessageBox.critical(self, "Lỗi tải file", f"Không thể tải file: {res}")

    def action_save_all_attachments(self):
        if not self.selected_doc_for_detail:
            QMessageBox.information(self, "Thông báo", "Vui lòng chọn công văn trước!")
            return
        attachments = db.get_doc_attachments(self.selected_doc_for_detail)
        if not attachments:
            QMessageBox.warning(self, "Không có tệp", "Công văn này không có tệp đính kèm nào để tải về!")
            return

        base_folder = db.get_setting("save_folder", db.DEFAULT_SAVE_FOLDER)
        so_den = str(self.selected_doc_for_detail.get("so_den", "CV"))
        so_kh = str(self.selected_doc_for_detail.get("so_ky_hieu", ""))
        folder_name = re.sub(r'[\\/*?:"<>|]', '_', f"CV_{so_den}_{so_kh}")
        target_dir = os.path.join(base_folder, folder_name)
        os.makedirs(target_dir, exist_ok=True)

        self.status_bar.showMessage(f"Đang tải {len(attachments)} tệp đính kèm...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        success_count = 0
        try:
            for att in attachments:
                url = att.get("download_url") or att.get("view_url")
                if not url:
                    continue
                file_name = re.sub(r'[\\/*?:"<>|]', '_', att.get("name", "file.pdf"))
                dest = os.path.join(target_dir, file_name)
                ok, _ = self.crawler.download_file(url, dest)
                if ok:
                    success_count += 1
        finally:
            QApplication.restoreOverrideCursor()

        self.status_bar.showMessage(f"Đã tải thành công {success_count}/{len(attachments)} tệp.")
        ans = QMessageBox.question(
            self, "Tải về hoàn tất",
            f"✅ Đã tải về thành công {success_count}/{len(attachments)} tệp đính kèm vào thư mục:\n{target_dir}\n\nBạn có muốn mở thư mục ngay không?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ans == QMessageBox.StandardButton.Yes:
            try:
                os.startfile(target_dir)
            except Exception:
                pass

    # Tương thích ngược
    def action_view_quick_file(self):
        self.action_read_selected_attachment()

    def action_save_quick_file(self):
        self.action_save_selected_attachment()

    def action_save_custom_file(self):
        self.action_save_selected_attachment()

    # =========================================================================
    # HÀNH ĐỘNG CẤU HÌNH & ĐĂNG NHẬP
    # =========================================================================
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

    def show_floating_incoming_alert(self, doc):
        enable_toast = (db.get_setting("enable_toast", "1") == "1")
        if not enable_toast:
            return

        title = "CÓ CÔNG VĂN ĐẾN MỚI ĐƯỢC GIAO!"
        so_den = doc.get("so_den", "")
        so_kh = doc.get("so_ky_hieu", "")
        trich_yeu = doc.get("trich_yeu", "")
        if len(trich_yeu) > 90:
            trich_yeu = trich_yeu[:90] + "..."
        han = doc.get("han_xu_ly", "Không ghi hạn")

        msg = f"📌 Số đến: {so_den} | Số hiệu: {so_kh}\n⏳ Hạn xử lý: {han}\n📝 {trich_yeu}"

        # Cửa sổ thông báo nổi thiết kế riêng của ứng dụng (rõ ràng, trực quan, không hiển thị biểu tượng/tên Python)
        self.toast = ToastNotification(title, msg, doc=doc, on_click=self.on_toast_clicked, is_outgoing=False)
        self.toast.show()

        # Nhấp nháy icon trên thanh taskbar Windows để gây chú ý khi người dùng quay lại bàn làm việc
        try:
            QApplication.alert(self, 0)
        except Exception:
            pass

    def show_floating_outgoing_alert(self, doc):
        enable_toast = (db.get_setting("enable_toast", "1") == "1")
        if not enable_toast:
            return

        title = "CÔNG VĂN ĐI CÓ CẬP NHẬT TRẠNG THÁI!"
        so_di = doc.get("so_di") or doc.get("so_trinh_ky", "")
        trang_thai = doc.get("trang_thai", "")
        trich_yeu = doc.get("trich_yeu", "")
        if len(trich_yeu) > 90:
            trich_yeu = trich_yeu[:90] + "..."

        msg = f"📌 Số văn bản: {so_di}\n🚀 Trạng thái mới: {trang_thai}\n📝 {trich_yeu}"

        # Cửa sổ thông báo nổi thiết kế riêng của ứng dụng
        self.toast = ToastNotification(title, msg, doc=doc, on_click=self.on_toast_clicked, is_outgoing=True)
        self.toast.show()

        # Nhấp nháy icon trên thanh taskbar Windows để gây chú ý
        try:
            QApplication.alert(self, 0)
        except Exception:
            pass

    def on_toast_clicked(self, doc, is_outgoing=False):
        self.show_and_activate()
        if is_outgoing:
            self.sidebar.setCurrentRow(2)
            self.tabs_outgoing.setCurrentIndex(1)
        else:
            if doc:
                self.display_doc_detail(doc)

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
        if hasattr(self, "txt_update_url"):
            db.set_setting("update_url", self.txt_update_url.text().strip())
        if hasattr(self, "txt_nhiemvu_email"):
            db.set_setting("nhiemvu_email", self.txt_nhiemvu_email.text().strip())
        if hasattr(self, "txt_nhiemvu_password"):
            db.set_setting("nhiemvu_password", self.txt_nhiemvu_password.text().strip())

        self.timer.setInterval(self.spin_interval.value() * 60 * 1000)
        db.recalculate_urgency()
        self.refresh_all_data()
        QMessageBox.information(
            self, "Thành công",
            f"✅ Đã lưu toàn bộ cấu hình hệ thống!\n\n"
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
                ok, up_msg = updater.download_and_install_update(d_url)
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

    # =========================================================================
    # HÀNH ĐỘNG DÀNH CHO QUẢN TRỊ VIÊN (ADMIN CONSOLE ACTIONS)
    # =========================================================================
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

    # =========================================================================
    # QUÉT DỮ LIỆU NỀN & TIMER
    # =========================================================================
    def init_timer(self):
        interval_min = int(db.get_setting("interval_min", "2"))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.start_background_scan)
        self.timer.start(interval_min * 60 * 1000)

    def start_background_scan(self):
        self.status_bar.showMessage("Đang đồng bộ dữ liệu từ congvan.drvn.gov.vn...")
        self.btn_quick_scan.setEnabled(False)

        self.worker = BackgroundWorker(self.crawler)
        self.worker.finished_signal.connect(self.on_background_scan_finished)
        self.worker.new_doc_signal.connect(self.show_floating_incoming_alert)
        self.worker.out_update_signal.connect(self.show_floating_outgoing_alert)
        self.worker.start()

    def on_background_scan_finished(self, msg):
        self.btn_quick_scan.setEnabled(True)
        self.status_bar.showMessage(msg)
        self.refresh_all_data()

    # =========================================================================
    # SYSTEM TRAY (KHAY HỆ THỐNG WINDOWS)
    # =========================================================================
    def init_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray_icon = QSystemTrayIcon(self)
        if os.path.exists(ICON_PATH):
            self.tray_icon.setIcon(QIcon(ICON_PATH))
        else:
            self.tray_icon.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))

        self.tray_menu = QMenu(self)
        self.act_open = QAction("📂 Mở Bảng điều khiển", self)
        self.act_open.triggered.connect(self.show_and_activate)

        self.act_refresh = QAction("🔄 Quét dữ liệu ngay", self)
        self.act_refresh.triggered.connect(self.start_background_scan)

        self.act_exit = QAction("❌ Thoát ứng dụng hoàn toàn", self)
        self.act_exit.triggered.connect(self.quit_app)

        self.tray_menu.addAction(self.act_open)
        self.tray_menu.addAction(self.act_refresh)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.act_exit)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_and_activate()

    def show_and_activate(self):
        self.setWindowState(Qt.WindowState.WindowNoState)
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()

        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            user32.ShowWindow(hwnd, 9)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def quit_app(self):
        QApplication.instance().quit()


class SingleInstanceManager:
    def __init__(self, server_name="TroLyCongVan_DRVN_SingleInstance_IPC"):
        self.server_name = server_name
        self.server = None
        self.mutex = None
        self.window = None

    def is_another_instance_running(self):
        """Kiểm tra tức thì (0ms) xem ứng dụng đã chạy hay chưa qua Windows Named Mutex"""
        try:
            self.mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\TroLyCongVan_DRVN_App_Mutex")
            if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                # Đã có phiên bản đang chạy -> gửi tín hiệu IPC để phục hồi cửa sổ cũ lên trên cùng
                try:
                    sock = QLocalSocket()
                    sock.connectToServer(self.server_name)
                    if sock.waitForConnected(800):
                        sock.write(b"ACTIVATE\n")
                        sock.flush()
                        sock.waitForBytesWritten(1000)
                        sock.close()
                except Exception:
                    pass
                return True
        except Exception:
            pass

        # Đây là tiến trình duy nhất đầu tiên -> Khởi động ngay server IPC để lắng nghe
        try:
            QLocalServer.removeServer(self.server_name)
        except Exception:
            pass
        self.server = QLocalServer()
        self.server.newConnection.connect(self._handle_client)
        self.server.listen(self.server_name)
        return False

    def register_window(self, window):
        self.window = window

    def _handle_client(self):
        sock = self.server.nextPendingConnection()
        if not sock:
            return
        def on_read():
            try:
                data = sock.readAll().data().decode("utf-8", errors="ignore")
                if "ACTIVATE" in data and self.window:
                    self.window.show_and_activate()
            except Exception:
                pass
            sock.close()
        sock.readyRead.connect(on_read)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 1. Cơ chế Single Instance: Chỉ cho phép duy nhất 1 phiên bản chạy cùng lúc
    instance_mgr = SingleInstanceManager()
    if instance_mgr.is_another_instance_running():
        # Đã có phiên bản đang chạy -> kích hoạt cửa sổ cũ và thoát tiến trình mới ngay lập tức
        sys.exit(0)

    # 2. Khởi tạo cửa sổ chính và liên kết với trình quản lý IPC
    window = MainWindow()
    instance_mgr.register_window(window)

    window.show()
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec())
