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

from ui.widgets.toast import ToastNotification

class DashboardViewMixin:
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
                self.request_doc_read(doc)

    def open_detail_from_quick_new(self):
        row = self.table_quick_new.currentRow()
        if row >= 0:
            doc = self.get_doc_from_table_row(self.table_quick_new, row)
            if doc:
                self.display_doc_detail(doc)

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

