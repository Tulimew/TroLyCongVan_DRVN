import requests
import re
import urllib3
import json
import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
import db
import notifier

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://congvan.drvn.gov.vn"
LOGIN_URL = f"{BASE_URL}/login?returnurl=%2fdoc"

URLS = {
    "incoming_personal": f"{BASE_URL}/doc/view/doc-progress",
    "incoming_department": f"{BASE_URL}/doc/view/doc-provin",
    "outgoing_department": f"{BASE_URL}/doc/view/shipdoc-provin",
    "outgoing_personal": f"{BASE_URL}/doc/view/shipdoc-send",
    "outgoing_processing": f"{BASE_URL}/doc/view/shipdoc-progress"
}

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
        self.session = requests.Session()
        self.session.verify = False
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
                self.is_logged_in = True
                self.last_login_time = datetime.now()
                db.set_setting("session_cookies", json.dumps(cookies))
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
                    self.session.cookies.update(cookies)
                    self.is_logged_in = True
                    return True
            except:
                pass
        return False

    def fetch_doc_details_and_attachments(self, detail_url, han_xu_ly=""):
        """Trích xuất toàn bộ danh sách tệp đính kèm và phân loại xử lý từ trang chi tiết của công văn"""
        try:
            self.ensure_logged_in()
            full_url = detail_url if detail_url.startswith("http") else urljoin(BASE_URL, detail_url)
            r = self.session.get(full_url, timeout=20)
            if r.status_code != 200 or "login" in r.url.lower():
                return [], ""

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

    def fetch_incoming_docs_personal(self, from_date=None, to_date=None):
        """1. Công văn đến cá nhân (Chờ xử lý & hàng đợi phân công)"""
        return self._fetch_incoming_table(URLS["incoming_personal"], scope="personal")

    def fetch_incoming_docs_department(self, from_date=None, to_date=None):
        """2. Công văn đến của toàn Phòng / Đơn vị (có hỗ trợ mốc thời gian lọc)"""
        curr_year = datetime.now().year
        f_str = from_date.strftime("%d-%m-%Y") if hasattr(from_date, "strftime") else (from_date or f"01-01-{curr_year}")
        t_str = to_date.strftime("%d-%m-%Y") if hasattr(to_date, "strftime") else (to_date or f"31-12-{curr_year}")

        url_filtered = f"{BASE_URL}/doc/view/doc-provin/from/{f_str}/to/{t_str}"
        docs = self._fetch_incoming_table(url_filtered, scope="department")
        if not docs:
            docs = self._fetch_incoming_table(URLS["incoming_department"], scope="department")
        return docs

    def _fetch_incoming_table(self, url, scope="personal", retry=True):
        try:
            self.ensure_logged_in()
            r = self.session.get(url, timeout=20)
            if "login" in r.url.lower() or r.status_code in (301, 302, 401, 403):
                self.is_logged_in = False
                if retry and self.ensure_logged_in(force=True):
                    return self._fetch_incoming_table(url, scope=scope, retry=False)
                return []

            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.find('table', {'id': lambda x: x and 'grdData' in x}) or soup.find('table')
            if not table:
                return []

            rows = table.find_all("tr")
            parsed_docs = []

            for row in rows:
                tds = row.find_all("td")
                if len(tds) < 5:
                    continue

                so_den = tds[0].get_text(strip=True) if len(tds) > 0 else ""
                so_ky_hieu = tds[1].get_text(separator=' ', strip=True) if len(tds) > 1 else ""
                ngay_ban_hanh = tds[2].get_text(strip=True) if len(tds) > 2 else ""
                trich_yeu = tds[3].get_text(separator=' ', strip=True) if len(tds) > 3 else ""

                # Bỏ qua dòng tiêu đề bảng hoặc dòng phân trang, dòng trống
                if not so_ky_hieu and not trich_yeu:
                    continue
                if "số/ký hiệu" in so_ky_hieu.lower() or "trích yếu" in trich_yeu.lower():
                    continue

                ngay_den = tds[4].get_text(strip=True) if len(tds) > 4 else ""
                han_xu_ly = tds[5].get_text(strip=True) if len(tds) > 5 else ""
                chi_dao = tds[6].get_text(separator=' ', strip=True) if len(tds) > 6 else ""
                
                # Tách riêng chuyên viên xử lý chính và chuyên viên phối hợp
                xu_ly_chinh, phoi_hop = parse_personnel(tds[7]) if len(tds) > 7 else ("", "")
                thoi_han = tds[8].get_text(strip=True) if len(tds) > 8 else ""

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
                download_url, view_url = self._extract_links(tds[-1])
                if not download_url:
                    d2, v2 = self._extract_links(tds[3])
                    download_url = download_url or d2
                    view_url = view_url or v2

                attachments = db.get_doc_attachments_by_id(doc_id)
                if not attachments and (download_url or view_url):
                    fname = f"{so_ky_hieu or 'VanBan'}.pdf"
                    attachments = [{
                        "name": fname,
                        "download_url": download_url,
                        "view_url": view_url,
                        "info": "Tệp đính kèm chính"
                    }]
                elif not attachments:
                    attachments = []

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
                    "download_url": download_url,
                    "view_url": view_url,
                    "detail_url": detail_url,
                    "attachments": attachments
                }

                is_new = db.upsert_incoming_doc(doc)
                if is_new and scope == "personal":
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

                parsed_docs.append(doc)

            return parsed_docs
        except Exception as e:
            self.last_error = f"Lỗi lấy công văn đến: {str(e)}"
            return []

    def fetch_outgoing_docs_department(self, from_date=None, to_date=None):
        """1. Toàn bộ công văn đi của Phòng (có hỗ trợ mốc thời gian lọc)"""
        curr_year = datetime.now().year
        f_str = from_date.strftime("%d-%m-%Y") if hasattr(from_date, "strftime") else (from_date or f"01-01-{curr_year}")
        t_str = to_date.strftime("%d-%m-%Y") if hasattr(to_date, "strftime") else (to_date or f"31-12-{curr_year}")

        url_filtered = f"{BASE_URL}/doc/view/shipdoc-provin/from/{f_str}/to/{t_str}"
        docs = self._fetch_outgoing_table(url_filtered, scope="department")
        if not docs:
            docs = self._fetch_outgoing_table(URLS["outgoing_department"], scope="department")
        return docs

    def fetch_outgoing_docs_personal(self, from_date=None, to_date=None):
        """2. Công văn đi cá nhân (tự động tra cứu theo tên cán bộ và khoảng thời gian)"""
        import urllib.parse
        all_docs = []
        officer = db.get_officer_name()
        curr_year = datetime.now().year

        f_str = from_date.strftime("%d-%m-%Y") if hasattr(from_date, "strftime") else (from_date or f"01-01-{curr_year - 1}")
        t_str = to_date.strftime("%d-%m-%Y") if hasattr(to_date, "strftime") else (to_date or f"31-12-{curr_year + 1}")

        if officer:
            enc = urllib.parse.quote(officer)
            url_filter = f"{BASE_URL}/doc/view/shipdoc-send/from/{f_str}/to/{t_str}/sendname/{enc}"
            docs_filtered = self._fetch_outgoing_table(url_filter, scope="personal")
            all_docs.extend(docs_filtered)

        # Quét thêm danh sách mặc định để lấy các văn bản dự thảo / chờ xử lý mới nhất
        docs_default = self._fetch_outgoing_table(URLS["outgoing_personal"], scope="personal")
        all_docs.extend(docs_default)
        return all_docs

    def fetch_outgoing_docs_processing(self):
        """3. Công văn đi đang xử lý (trạng thái)"""
        return self._fetch_outgoing_table(URLS["outgoing_processing"], scope="processing")

    def _fetch_outgoing_table(self, url, scope="department", retry=True):
        try:
            self.ensure_logged_in()
            r = self.session.get(url, timeout=20)
            if "login" in r.url.lower() or r.status_code in (301, 302, 401, 403):
                self.is_logged_in = False
                if retry and self.ensure_logged_in(force=True):
                    return self._fetch_outgoing_table(url, scope=scope, retry=False)
                return []

            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.find('table', {'id': lambda x: x and 'grdData' in x}) or soup.find('table')
            if not table:
                return []

            rows = table.find_all("tr")
            parsed_docs = []

            for row in rows:
                tds = row.find_all("td")
                if len(tds) < 4:
                    continue

                so_trinh_ky = tds[0].get_text(strip=True) if len(tds) > 0 else ""
                so_di = tds[1].get_text(strip=True) if len(tds) > 1 else ""
                ngay_ban_hanh = tds[2].get_text(strip=True) if len(tds) > 2 else ""
                trich_yeu = tds[3].get_text(separator=' ', strip=True) if len(tds) > 3 else ""
                nguoi_ky = tds[4].get_text(strip=True) if len(tds) > 4 else ""
                soan_thao = tds[5].get_text(separator=' ', strip=True) if len(tds) > 5 else ""
                cv_tra_loi = tds[6].get_text(strip=True) if len(tds) > 6 else ""

                # Bỏ qua dòng tiêu đề bảng
                if "số trình ký" in so_trinh_ky.lower() or "trích yếu" in trich_yeu.lower():
                    continue

                # Loại trừ các văn bản rác / giả lập dạng "Công văn đi không phải trả lời cho công văn đến"
                if "không phải trả lời cho công văn đến" in trich_yeu.lower():
                    continue

                # Trích xuất itemid từ các link trong hàng
                itemid = ""
                for a in row.find_all("a"):
                    h = a.get("href", "")
                    m = re.search(r'/itemid/([a-zA-Z0-9\-]+)', h)
                    if m:
                        itemid = m.group(1)
                        break

                doc_id = f"ship_{itemid}" if itemid else f"out_{so_trinh_ky}_{so_di}_{soan_thao}"

                # Xác định trạng thái chính xác theo nguồn và dữ liệu
                if so_di and so_di.strip():
                    trang_thai = "Đã ban hành"
                elif "shipdoc-provin" in url:
                    trang_thai = "Đã ban hành"
                elif "shipdoc-progress" in url:
                    trang_thai = "Chờ xử lý / Trình ký"
                elif "shipdoc-send" in url:
                    trang_thai = "Đã xử lý"
                else:
                    trang_thai = "Đang xử lý / Trình ký"

                if "chờ duyệt" in trich_yeu.lower():
                    trang_thai = "Chờ duyệt"
                elif "đã ký" in nguoi_ky.lower():
                    trang_thai = "Đã ký số"

                download_url, view_url = self._extract_links(tds[-1])
                if not download_url:
                    d2, v2 = self._extract_links(tds[3])
                    download_url = download_url or d2
                    view_url = view_url or v2

                doc = {
                    "id": doc_id,
                    "so_trinh_ky": so_trinh_ky,
                    "so_di": so_di,
                    "so_ky_hieu": so_di or so_trinh_ky,
                    "trich_yeu": trich_yeu,
                    "ngay_ban_hanh": ngay_ban_hanh,
                    "ngay_tao": ngay_ban_hanh,
                    "trang_thai": trang_thai,
                    "nguoi_ky": nguoi_ky,
                    "soan_thao": soan_thao,
                    "cv_tra_loi": cv_tra_loi,
                    "scope": scope,
                    "download_url": download_url,
                    "view_url": view_url
                }

                has_up = db.upsert_outgoing_doc(doc)
                officer_name = db.get_officer_name()
                is_officer = (officer_name.lower() in soan_thao.lower()) if (officer_name and soan_thao) else False
                if has_up and (scope == "personal" or is_officer):
                    notifier.play_alert_chime()
                    msg = f"📤 *CÔNG VĂN ĐI CÓ CẬP NHẬT TRẠNG THÁI!*\n\n" \
                          f"📌 *Số đi / Trình ký:* `{doc['so_di'] or doc['so_trinh_ky']}`\n" \
                          f"📝 *Trích yếu:* {doc['trich_yeu']}\n" \
                          f"🚀 *Trạng thái mới:* *{doc['trang_thai']}*\n" \
                          f"👤 *Người ký:* {doc['nguoi_ky']}"
                    notifier.send_telegram_alert(msg)
                    if hasattr(self, "on_outgoing_status_updated") and callable(self.on_outgoing_status_updated):
                        self.on_outgoing_status_updated(doc)

                parsed_docs.append(doc)

            return parsed_docs
        except Exception:
            return []

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
