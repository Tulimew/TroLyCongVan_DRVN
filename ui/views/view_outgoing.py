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

class OutgoingViewMixin:
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
        self.add_history_button(filter_bar, "outgoing_department", self.dt_from_out_dept, self.dt_to_out_dept)
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
        self.add_history_button(filter_bar, "outgoing_personal", self.dt_from_out_pers, self.dt_to_out_pers)
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

    def apply_outgoing_filter_dept(self):
        d_from = self.dt_from_out_dept.date().toPyDate()
        d_to = self.dt_to_out_dept.date().toPyDate()
        docs = db.get_outgoing_docs_filtered(scope="department", from_date=d_from, to_date=d_to)
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
        docs = db.get_outgoing_docs_filtered(scope="personal", from_date=d_from, to_date=d_to)
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

