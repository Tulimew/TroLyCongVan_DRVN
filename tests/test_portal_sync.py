import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core import db, notifier
from core.crawler import DRVNCrawler, PortalSyncError, URLS
from ui.main_window import BackgroundWorker, MainWindow


DEPARTMENT = ("Số đến", "Số/Ký hiệu", "Ngày ban hành", "Trích yếu", "Ngày đến", "Hạn xử lý",
              "Chỉ đạo giải quyết", "Xử lý chính", "Số đi", "Xem")
PENDING = (*DEPARTMENT[:8], "Thời hạn", *DEPARTMENT[8:])
HISTORY = ("Số đến", "Số/Ký hiệu", "Trích yếu", "Hạn xử lý", "Báo cáo thực hiện",
           "Chỉ đạo giải quyết", "Xử lý chính", "Số đi", "Xem")
OUTGOING = ("Số trình ký", "Số đi", "Ngày ban hành", "Trích yếu", "Người ký",
            "Đơn vị / người soạn thảo", "CV đến trả lời", "Xem")
START, END = date(2026, 10, 25), date(2026, 11, 26)
RANGE = "/from/25-10-2026/to/26-11-2026"


def page(columns, rows=(), links=(), total=None):
    headings = "".join(f"<th>{v}</th>" for v in columns)
    body = "".join("<tr>" + "".join(f"<td>{v}</td>" for v in row) + "</tr>" for row in rows)
    pager = "".join(f'<a href="{link}">Trang</a>' for link in links)
    count = len(rows) if total is None else total
    return f'<h3>Danh sách công văn đến ({count})</h3><table id="dnn_grdData"><tr>{headings}</tr>{body}</table>{pager}'


def incoming(number, *, pending=False):
    record = (str(number), f"TEST/{number}", "25/11/2026", "Trích yếu mẫu", "25/11/2026",
              "30/11/2026", "", "", "456", f'<a href="/doc/detail/itemid/{number}">Xem</a>')
    return (*record[:8], "3 ngày", *record[8:]) if pending else record


def history(number):
    return (str(number), f"TEST/{number}", "Trích yếu mẫu", "", "Báo cáo mẫu", "", "", "",
            f'<a href="/doc/history/itemid/{number}">Xem</a>')


class PortalSyncTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        db_path = patch.object(db, "DB_PATH", str(Path(temporary.name) / "test.db"))
        db_path.start()
        self.addCleanup(db_path.stop)
        db.init_db()
        self.crawler = DRVNCrawler()
        auth = patch.object(self.crawler, "ensure_logged_in", return_value=True)
        self.auth = auth.start()
        self.addCleanup(auth.stop)
        self.sound = self.start_patch("core.notifier.play_alert_chime")
        self.telegram = self.start_patch("core.notifier.send_telegram_alert")

    def start_patch(self, target):
        active = patch(target)
        self.addCleanup(active.stop)
        return active.start()

    def configure_portal(self, pages):
        def get(url, **kwargs):
            value = pages[url]
            if isinstance(value, str):
                return SimpleNamespace(url=url, status_code=200, text=value)
            return value
        self.crawler.session.get = Mock(side_effect=get)

    def test_full_range_follows_next_page_and_maps_columns(self):
        url = URLS["incoming_department"] + RANGE
        page_two = url + "/p/2"
        self.configure_portal({
            url: page(DEPARTMENT, [incoming(1)], [page_two], total=2),
            page_two: page(DEPARTMENT, [incoming(2)], [url + "/p/1"], total=2),
        })
        docs = self.crawler.fetch_incoming_docs_department(START, END)
        self.assertEqual([d["so_den"] for d in docs], ["1", "2"])
        self.assertTrue(all(not d["thoi_han"] for d in docs))
        self.assertEqual(len(db.get_incoming_docs_filtered(scope="department")), 2)

    def test_recent_scan_reads_only_one_department_page(self):
        url = self.crawler._dated_url("incoming_department", None, None)
        self.configure_portal({url: page(DEPARTMENT, [incoming(1)], [url + "/p/2"], total=2)})
        self.crawler.fetch_incoming_docs_department(max_pages=1)
        self.crawler.session.get.assert_called_once()

    def test_missing_next_page_is_not_a_success(self):
        url = URLS["incoming_department"] + RANGE
        self.configure_portal({url: page(DEPARTMENT, [incoming(1)], total=2)})
        with self.assertRaisesRegex(PortalSyncError, "Thiếu trang"):
            self.crawler.fetch_incoming_docs_department(START, END)

    def test_history_reuses_identity_preserves_dates_and_excludes_alerts(self):
        current = URLS["incoming_personal"]
        completed = URLS["incoming_history"] + RANGE
        self.configure_portal({
            current: page(PENDING, [incoming(1, pending=True)]),
            completed: page(HISTORY, [history(1), history(2)]),
        })
        self.crawler.fetch_incoming_docs_personal()
        self.sound.reset_mock()
        self.telegram.reset_mock()
        self.crawler.fetch_incoming_history(START, END)
        docs = {d["so_den"]: d for d in db.get_incoming_docs_filtered(scope="personal", from_date=START, to_date=END)}
        self.assertEqual(set(docs), {"1", "2"})
        self.assertEqual(docs["1"]["ngay_den"], "25/11/2026")
        self.assertTrue(all(d["is_read"] and d["is_processed"] for d in docs.values()))
        self.assertFalse(db.get_incoming_docs_filtered(scope="personal", unread_only=True))
        self.assertFalse(db.get_urgent_docs(scope="personal"))
        self.assertFalse(db.get_incoming_docs_filtered(scope="personal", from_date=date(2026, 1, 1),
                                                       to_date=date(2026, 1, 31)))
        self.sound.assert_not_called()
        self.telegram.assert_not_called()

    def test_empty_pending_snapshot_removes_badge_without_deleting_records(self):
        url = URLS["incoming_personal"]
        self.configure_portal({url: page(PENDING, [incoming(1, pending=True)])})
        self.crawler.fetch_incoming_docs_personal()
        self.configure_portal({url: page(PENDING)})
        self.assertEqual(self.crawler.fetch_incoming_docs_personal(), [])
        self.assertFalse(db.get_incoming_docs_filtered(scope="personal", unread_only=True))
        self.assertEqual(len(db.get_incoming_docs_filtered(scope="personal")), 1)

    def test_authoritative_outgoing_queue_replaces_only_after_complete_fetch(self):
        url = URLS["outgoing_processing"]
        row = ("7", "", "", "Mẫu", "", "", "", '<a href="/doc/detail/itemid/7">Xem</a>')
        db.upsert_outgoing_doc({"id": "ship_7", "so_trinh_ky": "7", "trich_yeu": "Mẫu",
                                "trang_thai": "Đã xử lý", "scope": "personal"})
        self.assertFalse(db.get_outgoing_docs_filtered(scope="processing"))
        self.configure_portal({url: page(OUTGOING, [row])})
        self.crawler.fetch_outgoing_docs_processing()
        self.assertEqual(db.get_outgoing_docs_filtered(scope="processing")[0]["trang_thai"], "Chờ xử lý / Trình ký")
        self.configure_portal({url: page(OUTGOING, [row], [url + "/p/2"], total=2),
                               url + "/p/2": SimpleNamespace(url=url + "/p/2", status_code=503, text="")})
        with self.assertRaisesRegex(PortalSyncError, "HTTP 503"):
            self.crawler.fetch_outgoing_docs_processing()
        self.assertEqual(len(db.get_outgoing_docs_filtered(scope="processing")), 1)
        self.configure_portal({url: page(OUTGOING)})
        self.crawler.fetch_outgoing_docs_processing()
        self.assertFalse(db.get_outgoing_docs_filtered(scope="processing"))
        self.assertEqual(len(db.get_outgoing_docs_filtered(scope="personal")), 1)

    def test_redirected_filter_and_missing_table_fail(self):
        url = URLS["incoming_department"] + RANGE
        self.configure_portal({url: SimpleNamespace(url=URLS["incoming_department"], status_code=200, text="")})
        with self.assertRaisesRegex(PortalSyncError, "bỏ qua bộ lọc"):
            self.crawler.fetch_incoming_docs_department(START, END)
        self.configure_portal({url: "<html>Trang lỗi</html>"})
        with self.assertRaisesRegex(PortalSyncError, "Không tìm thấy bảng"):
            self.crawler.fetch_incoming_docs_department(START, END)

    def test_publication_after_pending_is_an_outgoing_status_change(self):
        pending = {"id": "ship_new", "so_trinh_ky": "8", "trich_yeu": "Mẫu",
                   "scope": "processing", "trang_thai": "Chờ xử lý / Trình ký"}
        db.replace_outgoing_processing([pending])
        db.replace_outgoing_processing([])
        archived = {**pending, "scope": "personal", "trang_thai": "Đã ban hành", "so_di": "42"}
        self.assertTrue(db.upsert_outgoing_doc(archived))
        self.assertFalse(db.upsert_outgoing_doc(archived))

    def test_failed_read_confirmation_keeps_local_unread(self):
        window = Mock()
        window.read_in_progress = {"one"}
        with patch.object(db, "mark_as_read") as mark:
            MainWindow.complete_doc_read(window, "one", False)
            mark.assert_not_called()
            MainWindow.complete_doc_read(window, "one", True)
            mark.assert_called_once_with("one")

    def test_worker_reports_failed_auth_and_partial_scan(self):
        crawler = Mock()
        crawler.ensure_logged_in.return_value = False
        worker = BackgroundWorker(crawler)
        messages = []
        worker.finished_signal.connect(messages.append)
        worker.run()
        self.assertIn("thất bại", messages[-1])
        crawler.fetch_outgoing_docs_processing.assert_not_called()
        crawler.ensure_logged_in.return_value = True
        for fetch in ("fetch_incoming_docs_personal", "fetch_outgoing_docs_processing",
                      "fetch_outgoing_docs_department", "fetch_outgoing_docs_personal"):
            getattr(crawler, fetch).return_value = []
        crawler.fetch_incoming_docs_department.side_effect = PortalSyncError("HTTP 503")
        worker.run()
        self.assertIn("chưa hoàn tất", messages[-1])
        self.assertIn("HTTP 503", messages[-1])

    def test_sound_respects_disabled_setting(self):
        db.set_setting("enable_sound", "0")
        # Use the original function because the crawler fixture patches the entry point.
        with patch("core.notifier.winsound.MessageBeep") as beep:
            play_alert_chime()
        beep.assert_not_called()


play_alert_chime = notifier.play_alert_chime
