import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import nhiemvu

class TestNhiemVu(unittest.TestCase):
    def test_get_supabase_config(self):
        url, key = nhiemvu.get_supabase_config()
        self.assertTrue(url.startswith("http"))
        self.assertIsInstance(key, str)

if __name__ == "__main__":
    unittest.main()
