import unittest
import os
import sys
from datetime import date, timedelta

# Thêm thư mục gốc vào path để import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db

class TestDatabase(unittest.TestCase):
    def setUp(self):
        # Đảm bảo CSDL được khởi tạo
        db.init_db()

    def test_parse_date_vietnam(self):
        d1 = db.parse_date_vietnam("20/11/2026")
        self.assertEqual(d1, date(2026, 11, 20))

        d2 = db.parse_date_vietnam("1/5/2026")
        self.assertEqual(d2, date(2026, 5, 1))

        d_invalid = db.parse_date_vietnam("không hợp lệ")
        self.assertIsNone(d_invalid)

    def test_calculate_days_remaining(self):
        today = date.today()
        future_str = (today + timedelta(days=5)).strftime("%d/%m/%Y")
        days = db.calculate_days_remaining(future_str)
        self.assertEqual(days, 5)

        past_str = (today - timedelta(days=3)).strftime("%d/%m/%Y")
        days_past = db.calculate_days_remaining(past_str)
        self.assertEqual(days_past, -3)

        empty_days = db.calculate_days_remaining("")
        self.assertEqual(empty_days, 999)

    def test_parse_leaders(self):
        cuc, phong = db.parse_leaders("Phó Cục trưởng Phan Thị Thu Hiền; Trưởng phòng Lương Duyên Thống")
        self.assertIn("Phan Thị Thu Hiền", cuc)
        self.assertIn("Lương Duyên Thống", phong)

    def test_settings_get_set(self):
        db.set_setting("test_key_xyz", "value_123")
        val = db.get_setting("test_key_xyz")
        self.assertEqual(val, "value_123")

    def test_upsert_and_filter_incoming_doc(self):
        doc = {
            "id": "test_unit_001",
            "so_den": "99999",
            "so_ky_hieu": "TEST/CV-2026",
            "ngay_ban_hanh": "20/11/2026",
            "trich_yeu": "Văn bản kiểm thử tự động",
            "ngay_den": "20/11/2026",
            "han_xu_ly": "30/11/2026",
            "chi_dao": "Lãnh đạo chỉ đạo",
            "xu_ly_chinh": "Tăng Tuấn Linh",
            "phoi_hop": "",
            "thoi_han": "",
            "phan_loai_xu_ly": "Công văn đến phải xử lý",
            "scope": "personal",
            "download_url": "",
            "view_url": "",
            "detail_url": "",
            "attachments": []
        }
        db.upsert_incoming_doc(doc)

        docs = db.get_incoming_docs_filtered(scope="personal")
        ids = [d["id"] for d in docs]
        self.assertIn("test_unit_001", ids)

if __name__ == "__main__":
    unittest.main()
