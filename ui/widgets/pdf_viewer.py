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


class PdfViewerMixin:
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

    def action_pdf_force_reload(self):
        """Buộc tải lại tệp đính kèm gốc từ máy chủ DRVN (xóa đệm và làm mới)"""
        if hasattr(self, "current_reading_attach") and self.current_reading_attach:
            self.load_attachment_into_reader(self.current_reading_attach, force_reload=True)

    def load_attachment_into_reader(self, attach, force_reload=False):
        self.current_reading_attach = attach
        raw_name = attach.get("name", "van_ban.pdf")
        self.lbl_pdf_title.setText(f"📖 {raw_name}")

        url = attach.get("download_url") or attach.get("view_url")
        if not url:
            self.unload_pdf_reader("Tệp đính kèm này không có liên kết tải xuống.")
            return

        doc = getattr(self, "selected_doc_for_detail", {}) or {}
        so_den = str(doc.get("so_den") or doc.get("so_di") or doc.get("id") or "CV")
        clean_so_den = re.sub(r'[\\/*?:"<>|]', '_', so_den)
        clean_raw_name = re.sub(r'[\\/*?:"<>|]', '_', raw_name)

        # Trích xuất GUID tệp duy nhất từ link (đảm bảo 100% không bị trùng file giữa các công văn)
        url_match = re.search(r'/(?:id|itemid)/([a-zA-Z0-9\-]+)', url)
        att_id = url_match.group(1)[:12] if url_match else "att"
        safe_file_name = f"DRVN_{clean_so_den}_{att_id}_{clean_raw_name}"
        temp_dir = tempfile.gettempdir()
        dest = os.path.join(temp_dir, safe_file_name)

        # Mở tức thì nếu file đã được tải trước đó và không yêu cầu tải lại
        if force_reload or not (os.path.exists(dest) and os.path.getsize(dest) > 0):
            if os.path.exists(dest):
                try:
                    os.remove(dest)
                except Exception:
                    pass
            self.status_bar.showMessage(f"Đang tải {raw_name} từ cổng DRVN...")
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

    def action_view_quick_file(self):
        self.action_read_selected_attachment()

    def action_save_quick_file(self):
        self.action_save_selected_attachment()

    def action_save_custom_file(self):
        self.action_save_selected_attachment()

