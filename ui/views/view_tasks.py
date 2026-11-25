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

class TasksViewMixin:
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
            current_dept = self.cbo_task_dept.currentText()
            dept_names = sorted([str(d.get("department", "")).strip() for d in dept_rows if d.get("department")])
            self.cbo_task_dept.blockSignals(True)
            self.cbo_task_dept.clear()
            self.cbo_task_dept.addItem("Tất cả đơn vị")
            self.cbo_task_dept.addItems(dept_names)
            idx_dept = self.cbo_task_dept.findText(current_dept)
            if idx_dept >= 0:
                self.cbo_task_dept.setCurrentIndex(idx_dept)
            self.cbo_task_dept.blockSignals(False)

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

