import requests
import json
import os
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from core import db


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

DASHBOARD_URL = "https://nhiemvu.drvn.gov.vn/dashboard"
API_BASE_URL = os.getenv("NHIEMVU_API_URL", "https://todolist-gttm.onrender.com/api").rstrip("/")

STATUS_MAP = {
    "IN_PROGRESS": "dang_xu_ly",
    "COMPLETED_EARLY": "hoan_thanh",
    "COMPLETED_ON_TIME": "hoan_thanh",
    "COMPLETED_LATE": "hoan_thanh",
    "INCOMPLETE": "qua_han",
    "OVERDUE": "qua_han",
}

PRIORITY_MAP = {
    "URGENT": "khan",
    "HIGH": "khan",
    "IMPORTANT": "quan_trong",
    "MEDIUM": "quan_trong",
    "NORMAL": "binh_thuong",
    "LOW": "binh_thuong",
}


def get_supabase_config():
    """Lấy địa chỉ máy chủ và khóa truy cập Supabase từ biến môi trường hoặc cấu hình CSDL"""
    url = os.getenv("SUPABASE_URL") or db.get_setting("supabase_url", "https://afapnpzmrgypyzvopaia.supabase.co")
    key = os.getenv("SUPABASE_ANON_KEY") or db.get_setting("supabase_anon_key", "")
    return url.strip(), key.strip()


def _iso_to_vn_date(iso_str):
    """Chuyển đổi chuỗi ISO UTC (vd 2026-05-14T17:00:00.000Z) sang ngày Việt Nam dd/mm/yyyy."""
    if not iso_str:
        return ""
    s = str(iso_str).strip()
    try:
        if s.endswith("Z"):
            dt = datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S") + timedelta(hours=7)
            return dt.strftime("%d/%m/%Y")
        if "T" in s:
            dt = datetime.fromisoformat(s[:19])
            return dt.strftime("%d/%m/%Y")
        dt = datetime.strptime(s[:10], "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return s[:10]


def _map_task_item(item):
    """Chuẩn hóa một bản ghi nhiệm vụ từ API todolist-gttm sang cấu trúc bảng drvn_tasks."""
    task_id = str(item.get("id", ""))
    task_code = item.get("taskCode") or item.get("code") or f"NV-{task_id[:6]}"
    title = item.get("title") or item.get("name") or "Nhiệm vụ chưa đặt tên"

    doc_num = (item.get("documentNumber") or "").strip()
    src_raw = (item.get("source") or "").strip()
    if doc_num and src_raw:
        source = f"{doc_num} ({src_raw})"
    else:
        source = doc_num or src_raw or "Văn bản chỉ đạo"

    owner_dept = item.get("ownerDepartment")
    if isinstance(owner_dept, dict):
        department = owner_dept.get("name") or owner_dept.get("code") or "Đơn vị chuyên môn"
    else:
        department = item.get("department") or "Đơn vị chuyên môn"

    creator = item.get("creator")
    creator_name = creator.get("fullName") if isinstance(creator, dict) else ""
    assignee = (item.get("assignedBy") or creator_name or "Lãnh đạo Cục").strip()
    coordinators = (item.get("coordinatingUnits") or "").strip()

    raw_prio = str(item.get("priority") or "NORMAL").upper()
    priority = PRIORITY_MAP.get(raw_prio, "binh_thuong")

    raw_status = str(item.get("status") or "IN_PROGRESS").upper()
    if raw_status == "NO_EVALUATION":
        status = "hoan_thanh" if item.get("actualCompletionDate") else "dang_xu_ly"
    else:
        status = STATUS_MAP.get(raw_status, "dang_xu_ly")

    start_date = _iso_to_vn_date(item.get("assignedDate") or item.get("start_date"))
    due_date = _iso_to_vn_date(item.get("requiredCompletionDate") or item.get("due_date"))
    completed_date = _iso_to_vn_date(item.get("actualCompletionDate") or item.get("completed_date"))

    if item.get("progress") is not None:
        progress = int(item.get("progress") or 0)
    elif status == "hoan_thanh":
        progress = 100
    elif status == "qua_han":
        progress = 0
    else:
        progress = 50

    report_content = (item.get("content") or item.get("report_content") or item.get("description") or "").strip()
    status_lbl = (item.get("statusLabel") or "").strip()
    approval_lbl = (item.get("approvalStatusLabel") or "").strip()
    note_parts = [p for p in (status_lbl, approval_lbl) if p]
    note = " | ".join(note_parts) if note_parts else (item.get("note") or "")

    return {
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
        "note": note,
    }


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
    if urlsplit(url).scheme != "https":
        return False, "Máy chủ xác thực nhiệm vụ yêu cầu HTTPS."
    headers = {
        "apikey": supabase_key,
        "Content-Type": "application/json"
    }
    body = {
        "email": email.strip(),
        "password": password.strip()
    }

    try:
        r = requests.post(url, headers=headers, json=body, timeout=12, allow_redirects=False)
        if r.status_code == 200:
            data = r.json()
            access_token = data.get("access_token", "")
            user_info = data.get("user", {})
            user_id = user_info.get("id", "")

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


def sync_tasks_from_remote(_retried=False):
    """
    Đồng bộ toàn bộ danh sách nhiệm vụ từ Backend API của nhiemvu.drvn.gov.vn về SQLite nội bộ.
    Nếu chưa đăng nhập hoặc lỗi, giữ nguyên dữ liệu hiện tại.
    """
    if urlsplit(API_BASE_URL).scheme != "https":
        return False, "Máy chủ nhiệm vụ yêu cầu HTTPS."
    token = db.get_setting("nhiemvu_token", "")
    if not token:
        email = db.get_setting("nhiemvu_email", "")
        pwd = db.get_setting("nhiemvu_password", "")
        if email and pwd:
            ok, _ = login_nhiemvu(email, pwd)
            if ok:
                token = db.get_setting("nhiemvu_token", "")
        if not token:
            return False, "Chưa đăng nhập tài khoản Hệ thống nhiệm vụ. Vui lòng khai báo trong Cấu hình."

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        all_items = []
        page = 1
        total_pages = 1
        while page <= total_pages:
            url = f"{API_BASE_URL}/tasks?page={page}&limit=100"
            r = requests.get(url, headers=headers, timeout=30, allow_redirects=False)
            if r.status_code == 401 and not _retried:
                email = db.get_setting("nhiemvu_email", "")
                pwd = db.get_setting("nhiemvu_password", "")
                if email and pwd:
                    ok, _ = login_nhiemvu(email, pwd)
                    if ok:
                        return sync_tasks_from_remote(_retried=True)
                return False, "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại tài khoản nhiệm vụ."
            if r.status_code != 200:
                return False, f"Máy chủ nhiệm vụ phản hồi mã lỗi HTTP {r.status_code}."

            payload = r.json()
            page_items = payload.get("data", []) if isinstance(payload, dict) else payload
            all_items.extend(page_items)

            pagination = payload.get("pagination", {}) if isinstance(payload, dict) else {}
            total_pages = int(pagination.get("totalPages", 1) or 1)
            page += 1

        if all_items:
            db.clear_sample_tasks()

        synced_count = 0
        for item in all_items:
            db.upsert_task(_map_task_item(item))
            synced_count += 1

        return True, f"Đã đồng bộ thành công {synced_count} nhiệm vụ từ hệ thống trực tuyến!"
    except Exception as e:
        return False, f"Lỗi đồng bộ trực tuyến: {str(e)}"
