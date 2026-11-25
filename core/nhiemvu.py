import requests
import json
import urllib3
import os
from core import db

urllib3.disable_warnings()

def _load_env_file():
    """Tự động nạp cấu hình từ tệp .env nếu tồn tại mà không phụ thuộc thư viện ngoài"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

_load_env_file()

def get_supabase_config():
    """Lấy địa chỉ máy chủ và khóa truy cập Supabase từ biến môi trường hoặc cấu hình CSDL"""
    url = os.getenv("SUPABASE_URL") or db.get_setting("supabase_url", "https://afapnpzmrgypyzvopaia.supabase.co")
    key = os.getenv("SUPABASE_ANON_KEY") or db.get_setting("supabase_anon_key", "")
    return url.strip(), key.strip()

DASHBOARD_URL = "https://nhiemvu.drvn.gov.vn/dashboard"

def login_nhiemvu(email, password):
    """
    Xác thực tài khoản với hệ thống theo dõi nhiệm vụ DRVN qua Supabase Auth API.
    """
    if not email or not password:
        return False, "Vui lòng nhập Email và Mật khẩu Hệ thống theo dõi nhiệm vụ!"

    supabase_url, supabase_key = get_supabase_config()
    if not supabase_key:
        return False, "Chưa thiết lập khóa API Supabase. Vui lòng cấu hình file .env hoặc biến môi trường."

    url = f"{supabase_url}/auth/v1/token?grant_type=password"
    headers = {
        "apikey": supabase_key,
        "Content-Type": "application/json"
    }
    body = {
        "email": email.strip(),
        "password": password.strip()
    }

    try:
        r = requests.post(url, headers=headers, json=body, timeout=12)
        if r.status_code == 200:
            data = r.json()
            access_token = data.get("access_token", "")
            user_info = data.get("user", {})
            user_id = user_info.get("id", "")

            # Lưu vào cài đặt
            db.set_setting("nhiemvu_email", email.strip())
            db.set_setting("nhiemvu_password", password.strip())
            db.set_setting("nhiemvu_token", access_token)
            db.set_setting("nhiemvu_user_id", user_id)
            db.set_setting("nhiemvu_logged_in", "1")

            return True, "Đăng nhập Hệ thống theo dõi nhiệm vụ thành công!"
        else:
            try:
                err_data = r.json()
                err_msg = err_data.get("msg") or err_data.get("error_description") or r.text
            except Exception:
                err_msg = r.text
            if "Invalid login credentials" in err_msg:
                err_msg = "Email hoặc Mật khẩu không chính xác."
            return False, f"Đăng nhập thất bại: {err_msg}"
    except Exception as e:
        return False, f"Lỗi kết nối tới máy chủ nhiệm vụ: {str(e)}"

def sync_tasks_from_remote():
    """
    Đồng bộ danh sách nhiệm vụ từ Supabase về SQLite nội bộ.
    Nếu chưa đăng nhập hoặc lỗi, giữ nguyên dữ liệu hiện tại.
    """
    token = db.get_setting("nhiemvu_token", "")
    if not token:
        # Nếu đã có email và pass nhưng chưa có token, thử login tự động
        email = db.get_setting("nhiemvu_email", "")
        pwd = db.get_setting("nhiemvu_password", "")
        if email and pwd:
            ok, _ = login_nhiemvu(email, pwd)
            if ok:
                token = db.get_setting("nhiemvu_token", "")
        if not token:
            return False, "Chưa đăng nhập tài khoản Hệ thống nhiệm vụ. Vui lòng khai báo trong Cấu hình."

    supabase_url, supabase_key = get_supabase_config()
    if not supabase_key:
        return False, "Chưa thiết lập khóa API Supabase. Vui lòng cấu hình file .env hoặc biến môi trường."

    url = f"{supabase_url}/rest/v1/tasks?select=*"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {token}"
    }

    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            tasks_list = r.json()
            synced_count = 0
            for item in tasks_list:
                # Chuẩn hóa trường dữ liệu
                task_id = str(item.get("id", ""))
                task_code = item.get("code") or item.get("task_code") or f"NV-{task_id[:6]}"
                title = item.get("title") or item.get("name") or "Nhiệm vụ chưa đặt tên"
                source = item.get("source") or item.get("document_source") or "Văn bản chỉ đạo"
                department = item.get("department") or item.get("department_name") or "Phòng ban chuyên môn"
                assignee = item.get("assignee") or item.get("assignee_name") or "Chuyên viên xử lý"
                coordinators = item.get("coordinators") or ""
                priority = item.get("priority") or "binh_thuong"
                status = item.get("status") or "dang_xu_ly"
                start_date = item.get("start_date") or ""
                due_date = item.get("due_date") or item.get("deadline") or ""
                completed_date = item.get("completed_date") or ""
                progress = int(item.get("progress") or 0)
                report_content = item.get("report_content") or item.get("description") or ""
                note = item.get("note") or ""

                db.upsert_task({
                    "id": task_id,
                    "code": task_code,
                    "title": title,
                    "source": source,
                    "department": department,
                    "assignee": assignee,
                    "coordinators": coordinators,
                    "priority": priority,
                    "status": status,
                    "start_date": start_date,
                    "due_date": due_date,
                    "completed_date": completed_date,
                    "progress": progress,
                    "report_content": report_content,
                    "note": note
                })
                synced_count += 1
            return True, f"Đã đồng bộ thành công {synced_count} nhiệm vụ từ hệ thống trực tuyến!"
        elif r.status_code == 401:
            # Token hết hạn -> Thử đăng nhập lại
            email = db.get_setting("nhiemvu_email", "")
            pwd = db.get_setting("nhiemvu_password", "")
            if email and pwd:
                ok, _ = login_nhiemvu(email, pwd)
                if ok:
                    return sync_tasks_from_remote()
            return False, "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại tài khoản nhiệm vụ."
        else:
            return False, f"Máy chủ nhiệm vụ phản hồi mã lỗi HTTP {r.status_code}."
    except Exception as e:
        return False, f"Lỗi đồng bộ trực tuyến: {str(e)}"
