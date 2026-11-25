import requests
import re
import json
import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlsplit
from datetime import datetime
from core import db
from core import notifier

BASE_URL = "https://congvan.drvn.gov.vn"
LOGIN_URL = f"{BASE_URL}/login?returnurl=%2fdoc"

URLS = {
    "incoming_personal": f"{BASE_URL}/doc/view/doc-progress",
    "incoming_history": f"{BASE_URL}/doc/view/doc-send",
    "incoming_department": f"{BASE_URL}/doc/view/doc-provin",
    "outgoing_department": f"{BASE_URL}/doc/view/shipdoc-provin",
    "outgoing_personal": f"{BASE_URL}/doc/view/shipdoc-send",
    "outgoing_processing": f"{BASE_URL}/doc/view/shipdoc-progress"
}


class PortalSyncError(RuntimeError):
    """The requested list could not be synchronized completely."""


class _PortalSession(requests.Session):
    def get_adapter(self, url):
        if not url.lower().startswith("https://"):
            raise requests.exceptions.InvalidURL("Cổng công văn yêu cầu HTTPS.")
        return super().get_adapter(url)


def parse_personnel(td_element):
    """Tách chuyên viên xử lý chính và chuyên viên phối hợp từ thẻ TD cột 7"""
    if td_element is None:
        return "", ""
    divs = [d.get_text(strip=True) for d in td_element.find_all('div') if d.get_text(strip=True)]
    if not divs:
        text = td_element.get_text(strip=True)
        return text, ""
    names = []
    dept = ""
    for item in divs:
        if any(item.lower().startswith(p) for p in ['phòng', 'văn phòng', 'ban ', 'chi cục', 'cục ']):
            dept = item
        else:
            names.append(item)
    if not names:
        return dept, ""
    xu_ly_chinh = names[0]
    phoi_hop = ', '.join(names[1:]) if len(names) > 1 else ""
    return xu_ly_chinh, phoi_hop

class DRVNCrawler:
    def __init__(self):
        self.session = _PortalSession()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
        })
        self.is_logged_in = False
        self.last_login_time = None
        self.last_error = ""

    def ensure_logged_in(self, force=False):
        """Đảm bảo luôn có phiên làm việc hợp lệ. Tự động đăng nhập lại định kỳ hoặc khi hết phiên."""
        now = datetime.now()
        if not force and self.is_logged_in:
            if self.last_login_time and (now - self.last_login_time).total_seconds() < 900:  # 15 phút
                return True

        u = db.get_setting("username", "")
        p = db.get_setting("password", "")
        if not u or not p:
            if not self.is_logged_in:
                self.load_saved_cookies()
            return self.is_logged_in

        # Thử nạp cookie nếu còn mới và không bị ép buộc
        if not force and not self.is_logged_in:
            if self.load_saved_cookies():
                return True

        ok = self.login(u, p)
        if ok:
            self.last_login_time = datetime.now()
        return ok

    def _get_input_value(self, name, html):
        m = re.search(r'name=["\']' + re.escape(name) + r'["\'][^>]*value=["\']([^"\']*)["\']', html)
        if not m:
            m = re.search(r'value=["\']([^"\']*)["\'][^>]*name=["\']' + re.escape(name) + r'["\']', html)
        return m.group(1) if m else ""

    def login(self, username, password):
        try:
            self.session.cookies.clear()
            self.is_logged_in = False
            r = self.session.get(LOGIN_URL, timeout=15)
            if r.status_code != 200:
                self.last_error = f"Không thể kết nối máy chủ (Mã lỗi {r.status_code})"
                return False

            html = r.text
            viewstate = self._get_input_value("__VIEWSTATE", html)
            cachekey = self._get_input_value("__VIEWSTATE_CACHEKEY", html)
            eventvalidation = self._get_input_value("__EVENTVALIDATION", html)
            dnn_var = self._get_input_value("__dnnVariable", html)

            payload = {
                'StylesheetManager_TSSM': '',
                'ScriptManager_TSM': '',
                '__EVENTTARGET': 'dnn$ctr$Login$Login_DNN$AdminLogin$cmdLogin',
                '__EVENTARGUMENT': '',
                '__VIEWSTATE_CACHEKEY': cachekey,
                '__VIEWSTATE': viewstate,
                '__VIEWSTATEENCRYPTED': '',
                '__EVENTVALIDATION': eventvalidation,
                'dnn$ctr$Login$Login_DNN$AdminLogin$txtUsername': username,
                'dnn$ctr$Login$Login_DNN$AdminLogin$txtPassword': password,
                'ScrollTop': '',
                '__dnnVariable': dnn_var or '`{`__scdoff`:`1`}'
            }

            r_post = self.session.post(LOGIN_URL, data=payload, allow_redirects=False, timeout=20)

            cookies = self.session.cookies.get_dict()
            if r_post.status_code in (301, 302) or ".DOTNETNUKE" in cookies:
                db.set_setting("session_cookies", json.dumps(cookies) if ".DOTNETNUKE" in cookies else "")
                self.is_logged_in = True
                self.last_login_time = datetime.now()
                return True

            soup = BeautifulSoup(r_post.text, "html.parser")
            err_elem = soup.find(class_=re.compile(r"dnnFormMessage|alert|error", re.I))
            if err_elem:
                self.last_error = err_elem.get_text(strip=True)
            else:
                self.last_error = "Tài khoản hoặc mật khẩu không chính xác."

            self.is_logged_in = False
            return False
        except Exception as e:
            self.last_error = f"Lỗi kết nối: {str(e)}"
            self.is_logged_in = False
            return False

    def load_saved_cookies(self):
        cookies_json = db.get_setting("session_cookies", "")
        if cookies_json:
            try:
                cookies = json.loads(cookies_json)
                if ".DOTNETNUKE" in cookies:
                    for name, value in cookies.items():
                        self.session.cookies.set(name, value, domain="congvan.drvn.gov.vn", secure=True)
                    self.is_logged_in = True
                    self.last_login_time = datetime.now()
                    return True
            except:
                pass
        return False

    def fetch_doc_details_and_attachments(self, detail_url, han_xu_ly=""):
        """Trích xuất toàn bộ danh sách tệp đính kèm và phân loại xử lý từ trang chi tiết của công văn"""
        try:
            full_url = urljoin(BASE_URL, detail_url)
            if not re.search(r"/itemid/[^/]+", urlsplit(full_url).path, re.I):
                return [], ""
            r = self._portal_response(full_url)

            soup = BeautifulSoup(r.text, "html.parser")
            
            # Phân loại xử lý: ưu tiên radio đã chọn trên hệ thống
            phan_loai = ""
            for r_id, label in [
                ('rdLuuChung', 'Lưu chung đơn vị'),
                ('rdLuuChungFake', 'Lưu chung đơn vị'),
                ('rdPhaiXuLy', 'Công văn đến phải xử lý'),
                ('rdNhanDeBiet', 'Nhận để biết và lưu')
            ]:
                inp = soup.find('input', {'id': r_id})
                if inp and 'checked' in inp.attrs:
                    phan_loai = label
                    break
            if not phan_loai:
                phan_loai = 'Công văn đến phải xử lý' if (han_xu_ly and han_xu_ly.strip()) else 'Nhận để biết và lưu'

            divs = soup.find_all("div", class_="download")
            attachments = []
            for d in divs:
                a_d = d.find("a", href=lambda x: x and "/download/" in x)
                a_v = d.find("a", href=lambda x: x and ("/pdfeditor/" in x or "view.aspx" in x))
                info_elem = d.find("span", class_="dname")

                file_name = a_d.get_text(strip=True) if a_d else ""
                d_href = urljoin(BASE_URL, a_d["href"]) if a_d and a_d.get("href") else ""
                v_href = urljoin(BASE_URL, a_v["href"]) if a_v and a_v.get("href") else d_href
                info_text = info_elem.get_text(strip=True) if info_elem else ""

                if d_href or file_name:
                    attachments.append({
                        "name": file_name or "Tệp đính kèm.pdf",
                        "download_url": d_href,
                        "view_url": v_href,
                        "info": info_text
                    })
            return attachments, phan_loai
        except Exception as e:
            print(f"[Crawler] Lỗi lấy tệp đính kèm: {e}")
            return [], ""

    def fetch_doc_attachments(self, detail_url):
        """Trích xuất toàn bộ danh sách tệp đính kèm từ trang chi tiết của công văn (tương thích ngược)"""
        att, _ = self.fetch_doc_details_and_attachments(detail_url)
        return att

    def mark_doc_read_on_web(self, detail_url):
        """Gửi yêu cầu mở trang chi tiết lên cổng DRVN để hệ thống web ghi nhận đã đọc."""
        if not detail_url:
            return False
        _, classification = self.fetch_doc_details_and_attachments(detail_url)
        return bool(classification)

    def _extract_links(self, cell):
        """Trích xuất link download file và link xem nhanh"""
        download_url = ""
        view_url = ""
        for a in cell.find_all("a"):
            href = a.get("href", "")
            if not href:
                continue
            if not href.startswith("http"):
                href = urljoin(BASE_URL, href)
            if "/download/" in href:
                download_url = href
            elif "pdfeditor" in href or "view.aspx" in href:
                view_url = href
        return download_url, view_url

    def _dated_url(self, feed, from_date, to_date):
        year = datetime.now().year
        start = from_date.strftime("%d-%m-%Y") if from_date else f"01-01-{year}"
        end = to_date.strftime("%d-%m-%Y") if to_date else f"31-12-{year}"
        if from_date and to_date and from_date > to_date:
            raise PortalSyncError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
        return f"{URLS[feed]}/from/{start}/to/{end}"

    def _portal_response(self, url):
        allowed = urlsplit(BASE_URL)
        target = urlsplit(url)
        if (target.scheme, target.netloc) != (allowed.scheme, allowed.netloc):
            raise PortalSyncError("Đường dẫn không thuộc cổng công văn DRVN.")
        if not self.ensure_logged_in():
            raise PortalSyncError("Chưa xác thực được phiên đăng nhập DRVN.")
        response = self.session.get(url, timeout=20)
        if "/login" in urlsplit(response.url).path.lower() or response.status_code in (401, 403):
            self.is_logged_in = False
            if not self.ensure_logged_in(force=True):
                raise PortalSyncError("Phiên đăng nhập DRVN đã hết hạn.")
            response = self.session.get(url, timeout=20)
        if response.status_code != 200:
            raise PortalSyncError(f"Cổng DRVN trả HTTP {response.status_code}.")
        expected, actual = urlsplit(url), urlsplit(response.url)
        if (actual.scheme, actual.netloc, actual.path.rstrip("/").lower()) != (
            expected.scheme, expected.netloc, expected.path.rstrip("/").lower()
        ):
            raise PortalSyncError("Cổng DRVN chuyển sang trang khác hoặc bỏ qua bộ lọc đã chọn.")
        return response

    def _list_pages(self, url, required, max_pages=None):
        start_path = urlsplit(url).path.rstrip("/")
        feed_path = start_path.split("/from/")[0]
        page = 1
        seen_rows = 0
        seen_pages = set()
        reported_total = None
        while True:
            response = self._portal_response(url)
            soup = BeautifulSoup(response.text, "html.parser")
            table = soup.find("table", id=re.compile("grdData", re.I))
            if table is None:
                raise PortalSyncError(f"Không tìm thấy bảng công văn ở trang {page}.")
            rows = [row for row in table.find_all("tr") if row.find_parent("table") is table]
            if not rows:
                raise PortalSyncError(f"Bảng công văn thiếu tiêu đề ở trang {page}.")
            labels = [" ".join(cell.get_text(" ", strip=True).split()).casefold()
                      for cell in rows[0].find_all(["th", "td"], recursive=False)]
            columns = {label: index for index, label in enumerate(labels)}
            if not required.issubset(columns):
                raise PortalSyncError(f"Cấu trúc bảng công văn đã thay đổi ở trang {page}.")
            records = [row for row in rows[1:]
                       if len(row.find_all("td", recursive=False)) == len(labels)]
            if reported_total is None:
                for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
                    match = re.search(r"Danh sách công văn.+?\(([\d., ]+)\)", heading.get_text(" ", strip=True), re.I)
                    if match:
                        reported_total = int(re.sub(r"\D", "", match.group(1)))
                        break
            if (page > 1 or reported_total) and not records:
                raise PortalSyncError(f"Trang {page} trống nhưng cổng vẫn báo có dữ liệu.")
            if records:
                page_key = tuple(row.get_text(" ", strip=True) for row in records)
                if page_key in seen_pages:
                    raise PortalSyncError(f"Cổng DRVN trả dữ liệu trùng nguyên trang ở trang {page}.")
                seen_pages.add(page_key)
            seen_rows += len(records)
            yield columns, records
            if on_page := getattr(self, "on_list_page", None):
                on_page(page, seen_rows)
            if max_pages is not None and page >= max_pages:
                return

            next_urls = set()
            higher_page = False
            for link in soup.select("a[href]"):
                target = urlsplit(urljoin(response.url, link["href"]))
                match = re.fullmatch(r"(.+)/p/([1-9][0-9]*)/?", target.path)
                if (target.scheme, target.netloc) != ("https", urlsplit(BASE_URL).netloc) or not match:
                    continue
                prefix, number = match.group(1), int(match.group(2))
                if prefix.split("/from/")[0] != feed_path or (start_path != feed_path and prefix != start_path):
                    continue
                higher_page |= number > page
                if number == page + 1:
                    next_urls.add(target.geturl())
            if len(next_urls) > 1:
                raise PortalSyncError(f"Có nhiều liên kết khác nhau cho trang {page + 1}.")
            if not next_urls:
                if higher_page or (reported_total is not None and seen_rows < reported_total):
                    raise PortalSyncError(f"Thiếu trang công văn sau trang {page} ({seen_rows}/{reported_total or '?'} mục).")
                return
            if not records:
                raise PortalSyncError(f"Trang {page} trống nhưng cổng vẫn báo còn dữ liệu.")
            url = next_urls.pop()
            page += 1

    def fetch_incoming_docs_personal(self):
        return self._fetch_incoming_table(URLS["incoming_personal"], scope="personal")

    def fetch_incoming_history(self, from_date, to_date):
        return self._fetch_incoming_table(
            self._dated_url("incoming_history", from_date, to_date), scope="personal",
            history_range=(from_date.isoformat(), to_date.isoformat())
        )

    def fetch_incoming_docs_department(self, from_date=None, to_date=None, *, max_pages=None):
        return self._fetch_incoming_table(
            self._dated_url("incoming_department", from_date, to_date), scope="department", max_pages=max_pages
        )

    def _fetch_incoming_table(self, url, scope="personal", *, history_range=None, max_pages=None):
        processed = history_range is not None
        parsed_docs = []
        required = {"số đến", "số/ký hiệu", "trích yếu", "hạn xử lý", "xem"}
        for columns, rows in self._list_pages(url, required, max_pages):
            page_docs = []
            for row in rows:
                tds = row.find_all("td", recursive=False)

                def value(label):
                    return tds[columns[label]].get_text(" ", strip=True) if label in columns else ""

                so_den = value("số đến")
                so_ky_hieu = value("số/ký hiệu")
                ngay_ban_hanh = value("ngày ban hành")
                trich_yeu = value("trích yếu")
                if not so_ky_hieu and not trich_yeu:
                    raise PortalSyncError("Có dòng công văn đến thiếu số ký hiệu và trích yếu.")
                ngay_den = value("ngày đến")
                han_xu_ly = value("hạn xử lý")
                chi_dao = value("chỉ đạo giải quyết")
                xu_ly_chinh, phoi_hop = (parse_personnel(tds[columns["xử lý chính"]])
                                         if "xử lý chính" in columns else ("", ""))
                thoi_han = value("thời hạn")

                # Tìm link trang chi tiết của công văn
                detail_url = ""
                for a in row.find_all("a"):
                    h = a.get("href", "")
                    if "/itemid/" in h:
                        detail_url = urljoin(BASE_URL, h)
                        break

                # Tạo ID định danh duy nhất (ưu tiên GUID itemid trên web để đảm bảo 100% không trùng)
                item_match = re.search(r'/itemid/([a-zA-Z0-9\-]+)', detail_url)
                if item_match:
                    doc_id = f"item_{item_match.group(1)}_{scope}"
                elif so_den and re.search(r'\d+', so_den):
                    doc_id = f"{so_den}_{so_ky_hieu}_{scope}"
                else:
                    clean_skh = re.sub(r'[^a-zA-Z0-9]', '_', so_ky_hieu)
                    doc_id = f"doc_{clean_skh}_{ngay_ban_hanh}_{scope}"

                # Phân loại xử lý mặc định
                phan_loai_xu_ly = "Công văn đến phải xử lý" if (han_xu_ly and han_xu_ly.strip()) else "Nhận để biết và lưu"

                # Trích xuất liên kết tệp đính kèm trực tiếp từ dòng bảng
                # KHÔNG tự ý gửi GET detail_url vì cổng DRVN sẽ tự động chuyển văn bản 'Nhận để biết và lưu' sang 'Đã xử lý'
                download_url, view_url = self._extract_links(tds[columns["xem"]])
                if not download_url:
                    d2, v2 = self._extract_links(tds[columns["trích yếu"]])
                    download_url = download_url or d2
                    view_url = view_url or v2

                doc = {
                    "id": doc_id,
                    "so_den": so_den,
                    "so_ky_hieu": so_ky_hieu,
                    "ngay_ban_hanh": ngay_ban_hanh,
                    "trich_yeu": trich_yeu,
                    "ngay_den": ngay_den,
                    "han_xu_ly": han_xu_ly,
                    "chi_dao": chi_dao,
                    "xu_ly_chinh": xu_ly_chinh,
                    "phoi_hop": phoi_hop,
                    "thoi_han": thoi_han,
                    "phan_loai_xu_ly": phan_loai_xu_ly,
                    "scope": scope,
                    "is_processed": processed,
                    "history_range": history_range,
                    "download_url": download_url,
                    "view_url": view_url,
                    "detail_url": detail_url
                }

                page_docs.append(doc)
            if scope == "department" or processed:
                db.save_incoming_docs(page_docs)
            parsed_docs.extend(page_docs)

        if scope == "personal" and not processed:
            for doc in db.save_incoming_docs(parsed_docs, replace_pending=True):
                notifier.play_alert_chime()
                so_den_txt = doc['so_den'] if doc['so_den'] else "Văn bản nội bộ"
                msg = f"🔔 *CÓ CÔNG VĂN ĐẾN MỚI ĐƯỢC GIAO!*\n\n" \
                      f"📌 *Số đến:* `{so_den_txt}`\n" \
                      f"🏷️ *Phân loại:* {doc['phan_loai_xu_ly']}\n" \
                      f"📋 *Số/Ký hiệu:* {doc['so_ky_hieu']}\n" \
                      f"📅 *Ngày đến:* {doc['ngay_den'] or doc['ngay_ban_hanh']}\n" \
                      f"📝 *Trích yếu:* {doc['trich_yeu']}\n" \
                      f"👤 *Xử lý chính:* {doc['xu_ly_chinh']}\n"
                if doc.get("phoi_hop"):
                    msg += f"👥 *Phối hợp:* {doc['phoi_hop']}\n"
                msg += f"⏳ *Hạn xử lý:* {doc['han_xu_ly'] or 'Không ghi hạn'}\n\n" \
                       f"🔗 [Mở Hệ Thống DRVN]({url})"
                notifier.send_telegram_alert(msg)
                if hasattr(self, "on_new_personal_doc") and callable(self.on_new_personal_doc):
                    self.on_new_personal_doc(doc)
        return parsed_docs

    def fetch_outgoing_docs_department(self, from_date=None, to_date=None, *, max_pages=None):
        return self._fetch_outgoing_table(
            self._dated_url("outgoing_department", from_date, to_date), scope="department", max_pages=max_pages
        )

    def fetch_outgoing_docs_personal(self, from_date=None, to_date=None, *, max_pages=None):
        url = (self._dated_url("outgoing_personal", from_date, to_date)
               if from_date or to_date else URLS["outgoing_personal"])
        return self._fetch_outgoing_table(url, scope="personal", max_pages=max_pages)

    def fetch_outgoing_docs_processing(self):
        docs = self._fetch_outgoing_table(URLS["outgoing_processing"], scope="processing")
        db.replace_outgoing_processing(docs)
        return docs

    def _fetch_outgoing_table(self, url, scope="department", *, max_pages=None):
        parsed_docs = []
        required = {"số trình ký", "số đi", "ngày ban hành", "trích yếu", "người ký",
                    "đơn vị / người soạn thảo", "cv đến trả lời", "xem"}
        officer_name = db.get_officer_name() if max_pages else ""
        for columns, rows in self._list_pages(url, required, max_pages):
            page_docs = []
            for row in rows:
                tds = row.find_all("td", recursive=False)

                def value(label):
                    return tds[columns[label]].get_text(" ", strip=True)

                so_trinh_ky = value("số trình ký")
                so_di = value("số đi")
                ngay_ban_hanh = value("ngày ban hành")
                trich_yeu = value("trích yếu")
                nguoi_ky = value("người ký")
                soan_thao = value("đơn vị / người soạn thảo")
                cv_tra_loi = value("cv đến trả lời")
                if not so_trinh_ky and not so_di and not trich_yeu:
                    raise PortalSyncError("Có dòng công văn đi thiếu thông tin định danh.")
                if "không phải trả lời cho công văn đến" in trich_yeu.lower():
                    continue

                itemid = next((match.group(1) for link in row.find_all("a", href=True)
                               if (match := re.search(r"/itemid/([a-zA-Z0-9-]+)", link["href"]))), "")
                doc_id = f"ship_{itemid}" if itemid else f"out_{so_trinh_ky}_{so_di}_{soan_thao}"
                if scope == "processing":
                    trang_thai = "Chờ duyệt" if "chờ duyệt" in trich_yeu.lower() else "Chờ xử lý / Trình ký"
                elif so_di:
                    trang_thai = "Đã ban hành"
                elif "đã ký" in nguoi_ky.lower():
                    trang_thai = "Đã ký số"
                else:
                    trang_thai = "Đã xử lý"

                download_url, view_url = self._extract_links(tds[columns["xem"]])
                if not download_url:
                    d2, v2 = self._extract_links(tds[columns["trích yếu"]])
                    download_url = download_url or d2
                    view_url = view_url or v2
                doc = {
                    "id": doc_id, "so_trinh_ky": so_trinh_ky, "so_di": so_di,
                    "so_ky_hieu": so_di or so_trinh_ky, "trich_yeu": trich_yeu,
                    "ngay_ban_hanh": ngay_ban_hanh, "ngay_tao": ngay_ban_hanh,
                    "trang_thai": trang_thai, "nguoi_ky": nguoi_ky, "soan_thao": soan_thao,
                    "cv_tra_loi": cv_tra_loi, "scope": scope,
                    "download_url": download_url, "view_url": view_url,
                }
                page_docs.append(doc)
            parsed_docs.extend(page_docs)
            if scope == "processing":
                continue
            updates = db.save_outgoing_docs(page_docs)
            if max_pages is None:
                continue
            for doc in updates:
                is_officer = bool(officer_name and officer_name.casefold() in doc["soan_thao"].casefold())
                if scope == "personal" or is_officer:
                    notifier.play_alert_chime()
                    notifier.send_telegram_alert(
                        f"📤 *CÔNG VĂN ĐI CÓ CẬP NHẬT TRẠNG THÁI!*\n\n"
                        f"📌 *Số đi / Trình ký:* {doc['so_di'] or doc['so_trinh_ky']}\n"
                        f"📝 *Trích yếu:* {doc['trich_yeu']}\n"
                        f"🚀 *Trạng thái mới:* {doc['trang_thai']}\n"
                        f"👤 *Người ký:* {doc['nguoi_ky']}"
                    )
                    if hasattr(self, "on_outgoing_status_updated"):
                        self.on_outgoing_status_updated(doc)
        return parsed_docs

    def download_file(self, file_url, target_path, retry=True):
        """Tải file đính kèm với phiên làm việc đã xác thực về máy"""
        try:
            self.ensure_logged_in()
            full_url = file_url if file_url.startswith("http") else urljoin(BASE_URL, file_url)
            r = self.session.get(full_url, stream=True, timeout=30)
            if "login" in r.url.lower() or r.status_code in (301, 302, 401, 403):
                self.is_logged_in = False
                if retry and self.ensure_logged_in(force=True):
                    return self.download_file(file_url, target_path, retry=False)
                return False, "Phiên đăng nhập đã hết hạn. Vui lòng kiểm tra lại tài khoản."

            if r.status_code == 200:
                content_type = r.headers.get("Content-Type", "")
                if "text/html" in content_type.lower():
                    if retry and self.ensure_logged_in(force=True):
                        return self.download_file(file_url, target_path, retry=False)
                    return False, "Máy chủ phản hồi trang web thay vì file đính kèm."

                os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
                with open(target_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return True, target_path
            return False, f"Máy chủ báo mã lỗi {r.status_code}"
        except Exception as e:
            return False, str(e)
