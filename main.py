import sys
import os

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import ctypes
import traceback
from ctypes import wintypes
from datetime import datetime

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from logger import log
from update_transaction import recover_interrupted_update


def wait_for_restart_parent(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    parent = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not parent:
        return ctypes.get_last_error() == 87  # The parent already exited.
    try:
        return kernel.WaitForSingleObject(parent, 60_000) == 0
    finally:
        kernel.CloseHandle(parent)


def handle_global_exception(exc_type, exc_value, exc_traceback):
    """Bắt lỗi toàn cục để đảm bảo phần mềm không bao giờ bị văng/thoát đột ngột."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    err_str = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    try:
        log.critical("Lỗi nghiêm trọng chưa được xử lý:\n%s", err_str)
        log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "error.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR:\n{err_str}\n")
    except Exception:
        pass
    if QApplication.instance():
        QMessageBox.critical(
            None,
            "Thông báo lỗi",
            f"Đã xảy ra lỗi:\n{exc_value}\n\n(Chi tiết đã được ghi vào app.log và error.log)",
        )


sys.excepthook = handle_global_exception


class SingleInstanceManager:
    """Đảm bảo chỉ có duy nhất một phiên bản ứng dụng chạy tại một thời điểm."""

    def __init__(self, server_name="TroLyCongVan_DRVN_SingleInstance_IPC"):
        self.server_name = server_name
        self.server = None
        self.mutex = None
        self.window = None

    def is_another_instance_running(self):
        """Kiểm tra tức thì (0ms) xem ứng dụng đã chạy hay chưa qua Windows Named Mutex."""
        try:
            self.mutex = ctypes.windll.kernel32.CreateMutexW(
                None, False, "Global\\TroLyCongVan_DRVN_App_Mutex"
            )
            if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
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
    if len(sys.argv) == 3 and sys.argv[1] == "--restart-after":
        if not wait_for_restart_parent(int(sys.argv[2])):
            sys.exit(1)
        del sys.argv[1:]
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    instance_mgr = SingleInstanceManager()
    if instance_mgr.is_another_instance_running():
        sys.exit(0)

    try:
        if recover_interrupted_update(os.path.dirname(os.path.abspath(__file__))):
            log.warning("Đã khôi phục bản cũ sau khi quá trình cập nhật bị gián đoạn.")
    except (OSError, ValueError) as error:
        log.exception("Không thể khôi phục bản cập nhật.")
        QMessageBox.critical(None, "Khôi phục bản cập nhật", str(error))
        sys.exit(1)

    from ui.main_window import MainWindow

    log.info("Khởi động Trợ lý Công văn DRVN...")

    window = MainWindow()
    instance_mgr.register_window(window)

    window.show()
    window.raise_()
    window.activateWindow()
    sys.exit(app.exec())
