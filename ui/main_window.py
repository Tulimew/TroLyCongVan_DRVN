import os
import re
import webbrowser
import tempfile
import threading
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

from ui.views.view_dashboard import DashboardViewMixin
from ui.views.view_incoming import IncomingViewMixin
from ui.views.view_outgoing import OutgoingViewMixin
from ui.views.view_tasks import TasksViewMixin
from ui.views.view_config import ConfigViewMixin
from ui.views.view_admin import AdminViewMixin
from ui.widgets.pdf_viewer import PdfViewerMixin
from ui.widgets.system_tray import SystemTrayMixin

class BackgroundWorker(QThread):
    finished_signal = pyqtSignal(str)
    new_doc_signal = pyqtSignal(dict)
    out_update_signal = pyqtSignal(dict)
    progress_signal = pyqtSignal(str)

    def __init__(self, crawler, history=None):
        super().__init__()
        self.crawler = crawler
        self.history = history
        self.crawler.on_new_personal_doc = self.new_doc_signal.emit
        self.crawler.on_outgoing_status_updated = self.out_update_signal.emit

    def run(self):
        try:
            if not self.crawler.ensure_logged_in():
                self.finished_signal.emit("Đồng bộ thất bại: Chưa xác thực được phiên đăng nhập DRVN.")
                return
        except Exception as error:
            self.finished_signal.emit(f"Đồng bộ thất bại: {error}")
            return

        if self.history is None:
            jobs = [
                ("Công văn đi đang xử lý", self.crawler.fetch_outgoing_docs_processing, (), {}),
                ("Công văn đến chờ xử lý", self.crawler.fetch_incoming_docs_personal, (), {}),
                ("Công văn đến đơn vị", self.crawler.fetch_incoming_docs_department, (), {"max_pages": 1}),
                ("Công văn đi đơn vị", self.crawler.fetch_outgoing_docs_department, (), {"max_pages": 1}),
                ("Công văn đi cá nhân", self.crawler.fetch_outgoing_docs_personal, (), {"max_pages": 1}),
            ]
        else:
            feed, start, end = self.history
            history_jobs = {
                "incoming_personal": ("Công văn đến cá nhân đã xử lý", self.crawler.fetch_incoming_history),
                "incoming_department": ("Công văn đến đơn vị", self.crawler.fetch_incoming_docs_department),
                "outgoing_personal": ("Công văn đi cá nhân", self.crawler.fetch_outgoing_docs_personal),
                "outgoing_department": ("Công văn đi đơn vị", self.crawler.fetch_outgoing_docs_department),
            }
            label, fetch = history_jobs[feed]
            jobs = [(label, fetch, (start, end), {})]
            if feed == "incoming_personal":
                jobs.append(("Công văn đến chờ xử lý", self.crawler.fetch_incoming_docs_personal, (), {}))

        errors = []
        successes = []
        for label, fetch, args, kwargs in jobs:
            self.progress_signal.emit(f"Đang đồng bộ {label}…")
            self.crawler.on_list_page = lambda page, count, label=label: self.progress_signal.emit(
                f"Đang đồng bộ {label} · Trang {page} · Đã nhận {count} mục"
            )
            try:
                docs = fetch(*args, **kwargs)
                successes.append(f"{label}: {len(docs)}")
            except Exception as error:
                errors.append(f"{label}: {error}")
        self.crawler.on_list_page = None
        if errors:
            status = "Đồng bộ chưa hoàn tất" if successes else "Đồng bộ thất bại"
            self.finished_signal.emit(f"{status}: {' | '.join(errors)}")
        else:
            title = "Đã đồng bộ khoảng ngày đã chọn" if self.history else "Đã quét danh sách chờ và trang mới nhất"
            self.finished_signal.emit(f"{title} lúc {datetime.now():%H:%M:%S} · {' | '.join(successes)}")


class MainWindow(
    QMainWindow,
    DashboardViewMixin,
    IncomingViewMixin,
    OutgoingViewMixin,
    TasksViewMixin,
    ConfigViewMixin,
    AdminViewMixin,
    PdfViewerMixin,
    SystemTrayMixin,
):
    read_finished = pyqtSignal(str, bool)

    def __init__(self):
        super().__init__()
        self.read_in_progress = set()
        self.read_finished.connect(self.complete_doc_read)
        self.crawler = DRVNCrawler()
        self.detail_crawler = DRVNCrawler()
        self.worker = None
        self.history_buttons = []
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

    def init_timer(self):
        interval_min = int(db.get_setting("interval_min", "2"))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.start_background_scan)
        self.timer.start(interval_min * 60 * 1000)

    def start_background_scan(self):
        self._start_scan()

    def add_history_button(self, layout, feed, from_date, to_date):
        button = QPushButton("Đồng bộ khoảng ngày")
        button.clicked.connect(lambda: self.sync_history(feed, from_date.date().toPyDate(), to_date.date().toPyDate()))
        self.history_buttons.append(button)
        layout.addWidget(button)

    def sync_history(self, feed, start, end):
        if start > end:
            self.status_bar.showMessage("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
            return
        self._start_scan((feed, start, end))

    def _start_scan(self, history=None):
        if self.worker is not None and self.worker.isRunning():
            return
        self.status_bar.showMessage("Đang đồng bộ dữ liệu từ congvan.drvn.gov.vn…")
        for button in [self.btn_quick_scan, *self.history_buttons]:
            button.setEnabled(False)

        self.worker = BackgroundWorker(self.crawler, history)
        self.worker.finished_signal.connect(self.on_background_scan_finished)
        self.worker.progress_signal.connect(self.status_bar.showMessage)
        self.worker.new_doc_signal.connect(self.show_floating_incoming_alert)
        self.worker.out_update_signal.connect(self.show_floating_outgoing_alert)
        self.worker.start()

    def request_doc_read(self, doc):
        doc_id = doc["id"]
        if doc_id in self.read_in_progress:
            return
        self.read_in_progress.add(doc_id)
        self.status_bar.showMessage("Đang xác nhận trạng thái đã đọc với cổng DRVN…")

        def confirm():
            confirmed = DRVNCrawler().mark_doc_read_on_web(doc.get("detail_url", ""))
            self.read_finished.emit(doc_id, confirmed)

        threading.Thread(target=confirm, daemon=True).start()

    def complete_doc_read(self, doc_id, confirmed):
        self.read_in_progress.discard(doc_id)
        if confirmed:
            db.mark_as_read(doc_id)
            self.update_badges()
            self.refresh_quick_alerts()
            self.status_bar.showMessage("Cổng DRVN đã trả trang chi tiết. Đã cập nhật trạng thái đã đọc.")
        else:
            self.status_bar.showMessage("Chưa xác nhận được trạng thái đã đọc từ cổng DRVN. Có thể thử lại.")

    def on_background_scan_finished(self, msg):
        for button in [self.btn_quick_scan, *self.history_buttons]:
            button.setEnabled(True)
        self.status_bar.showMessage(msg)
        self.refresh_all_data()

