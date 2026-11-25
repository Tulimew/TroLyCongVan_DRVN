from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication, QFrame
from PyQt6.QtCore import Qt, QTimer
from core import db

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

