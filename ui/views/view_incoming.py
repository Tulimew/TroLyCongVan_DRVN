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

from ui.widgets.pdf_viewer import PDFScrollArea

class IncomingViewMixin:
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

        self.btn_pdf_reload = QPushButton("🔄 Tải lại tệp")
        self.btn_pdf_reload.setToolTip("Tải lại tệp đính kèm gốc từ cổng DRVN (làm mới bộ đệm)")
        self.btn_pdf_reload.clicked.connect(self.action_pdf_force_reload)

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
        bar_layout.addWidget(self.btn_pdf_reload)
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

