import os
import tempfile
import unittest
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QMessageBox

from core import db, windows_credentials
from ui.main_window import MainWindow


class TaskDepartmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        db_path = patch.object(db, "DB_PATH", str(Path(temporary.name) / "tasks.db"))
        db_path.start()
        self.addCleanup(db_path.stop)
        db.init_db()
        with closing(db.get_connection()) as conn, conn:
            conn.execute("DELETE FROM drvn_tasks")
        due = (date.today() + timedelta(days=2)).strftime("%d/%m/%Y")
        for code, department, status in (
            ("A1", "Phòng Kế hoạch", "dang_xu_ly"),
            ("A2", " PHÒNG   KẾ HOẠCH ", "hoan_thanh"),
            ("B1", "Phòng Kế hoạch và Đầu tư", "qua_han"),
        ):
            db.upsert_task({
                "id": code, "code": code, "title": code, "status": status,
                "department": department, "due_date": due, "priority": "binh_thuong",
            })

    def test_statistics_use_same_exact_normalized_scope_as_list(self):
        department = "phòng kế hoạch"
        self.assertEqual(db.get_task_stats(department), {
            "total": 2, "in_progress": 1, "completed": 1, "overdue": 0,
            "near_due": 1, "completion_rate": 50,
        })
        self.assertEqual([t["code"] for t in db.get_tasks_filtered(department, status="Đã hoàn thành")], ["A2"])
        self.assertEqual(len(db.get_tasks_by_department(department)), 1)
        self.assertEqual(db.get_task_stats()["total"], 3)

    def test_saving_switching_and_clearing_the_configured_room(self):
        with (
            patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}),
            patch.object(windows_credentials, "read", side_effect=lambda path, key, default: default),
            patch.object(windows_credentials, "write"),
            patch.object(MainWindow, "start_background_scan"),
            patch.object(MainWindow, "set_autostart_enabled"),
            patch.object(QMessageBox, "information"),
        ):
            app = QApplication.instance() or QApplication([])
            window = MainWindow()
            try:
                self.assertFalse(window.chk_task_department.isEnabled())
                form = window.txt_officer_name.parentWidget().layout()
                officer_row, _ = form.getWidgetPosition(window.txt_officer_name)
                department_row, _ = form.getWidgetPosition(window.txt_task_department)
                self.assertEqual(department_row, officer_row + 1)

                window.txt_task_department.setText("Phòng Kế hoạch")
                window.action_save_all_config()
                self.assertEqual(db.get_setting("task_department"), "Phòng Kế hoạch")
                self.assertTrue(window.chk_task_department.isChecked())
                self.assertEqual(window.card_total.lbl_count.text(), "2")
                self.assertEqual(window.progress_tasks.value(), 50)
                self.assertEqual(window.table_tasks.rowCount(), 2)
                self.assertEqual(window.table_urgent_tasks.rowCount(), 1)
                self.assertEqual(window.table_tasks_by_dept.rowCount(), 1)

                window.chk_task_department.setChecked(False)
                self.assertEqual(window.table_tasks.rowCount(), 3)
                self.assertEqual(window.card_total.lbl_count.text(), "3")

                window.txt_task_department.setText("Phòng chưa đồng bộ")
                window.action_save_all_config()
                self.assertEqual(window.table_tasks.rowCount(), 0)
                self.assertIn("Chưa có nhiệm vụ", window.lbl_task_department_scope.text())

                window.txt_task_department.clear()
                window.action_save_all_config()
                self.assertFalse(window.chk_task_department.isEnabled())
                self.assertEqual(window.table_tasks.rowCount(), 3)
            finally:
                window.timer.stop()
                window.deleteLater()
                app.processEvents()
