import unittest
import os
import sys
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.crawler import parse_personnel, DRVNCrawler

class TestCrawlerHelpers(unittest.TestCase):
    def test_parse_personnel_separated(self):
        html = """
        <td>
            <div>Phòng Quản lý vận tải</div>
            <div>Tăng Tuấn Linh</div>
            <div>Nguyễn Văn A</div>
        </td>
        """
        soup = BeautifulSoup(html, "html.parser")
        td = soup.find("td")
        xu_ly_chinh, phoi_hop = parse_personnel(td)

        self.assertEqual(xu_ly_chinh, "Tăng Tuấn Linh")
        self.assertEqual(phoi_hop, "Nguyễn Văn A")

    def test_parse_personnel_single_officer(self):
        html = """
        <td>
            <div>Văn phòng Cục</div>
            <div>Nguyễn Văn B</div>
        </td>
        """
        soup = BeautifulSoup(html, "html.parser")
        td = soup.find("td")
        xu_ly_chinh, phoi_hop = parse_personnel(td)

        self.assertEqual(xu_ly_chinh, "Nguyễn Văn B")
        self.assertEqual(phoi_hop, "")

    def test_extract_links(self):
        crawler = DRVNCrawler()
        html = """
        <td>
            <a href="/download/id/12345-abcde">Tải về</a>
            <a href="/pdfeditor/view.aspx?itemid=12345-abcde">Xem</a>
        </td>
        """
        soup = BeautifulSoup(html, "html.parser")
        td = soup.find("td")
        dl_url, view_url = crawler._extract_links(td)

        self.assertIn("/download/id/12345-abcde", dl_url)
        self.assertIn("/pdfeditor/view.aspx", view_url)

if __name__ == "__main__":
    unittest.main()
