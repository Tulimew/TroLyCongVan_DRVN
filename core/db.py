import sqlite3
import os
import re
import json
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "drvn_data.db")
DEFAULT_SAVE_FOLDER = os.path.join(os.path.expanduser("~"), "Downloads", "CongVan_DRVN")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Bảng cài đặt
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # Bảng công văn đến
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS incoming_docs (
        id TEXT PRIMARY KEY,
        so_den TEXT,
        so_ky_hieu TEXT,
        ngay_ban_hanh TEXT,
        trich_yeu TEXT,
        ngay_den TEXT,
        han_xu_ly TEXT,
        thoi_han TEXT,
        chi_dao TEXT,
        lanh_dao_cuc TEXT,
        lanh_dao_phong TEXT,
        xu_ly_chinh TEXT,
        phoi_hop TEXT,
        scope TEXT DEFAULT 'personal',
        download_url TEXT,
        view_url TEXT,
        is_read INTEGER DEFAULT 0,
        is_urgent INTEGER DEFAULT 0,
        days_remaining INTEGER DEFAULT 999,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Tự động thêm cột nếu bảng cũ chưa có
    cursor.execute("PRAGMA table_info(incoming_docs)")
    existing_cols = [row["name"] for row in cursor.fetchall()]
    new_cols = {
        "scope": "TEXT DEFAULT 'personal'",
        "lanh_dao_cuc": "TEXT",
        "lanh_dao_phong": "TEXT",
        "phoi_hop": "TEXT",
        "phan_loai_xu_ly": "TEXT",
        "download_url": "TEXT",
        "view_url": "TEXT",
        "detail_url": "TEXT",
        "attachments": "TEXT"
    }
    for col_name, col_type in new_cols.items():
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE incoming_docs ADD COLUMN {col_name} {col_type}")

    # Cập nhật phân loại xử lý mặc định cho các dòng cũ chưa có
    cursor.execute("""
    UPDATE incoming_docs 
    SET phan_loai_xu_ly = CASE 
        WHEN han_xu_ly IS NOT NULL AND TRIM(han_xu_ly) != '' THEN 'Công văn đến phải xử lý'
        ELSE 'Nhận để biết và lưu'
    END
    WHERE phan_loai_xu_ly IS NULL OR TRIM(phan_loai_xu_ly) = ''
    """)

    # Bảng công văn đi
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS outgoing_docs (
        id TEXT PRIMARY KEY,
        so_trinh_ky TEXT,
        so_di TEXT,
        so_ky_hieu TEXT,
        trich_yeu TEXT,
        ngay_tao TEXT,
        ngay_ban_hanh TEXT,
        trang_thai TEXT,
        nguoi_ky TEXT,
        soan_thao TEXT,
        cv_tra_loi TEXT,
        scope TEXT DEFAULT 'personal',
        download_url TEXT,
        view_url TEXT,
        has_update INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("PRAGMA table_info(outgoing_docs)")
    existing_out_cols = [row["name"] for row in cursor.fetchall()]
    new_out_cols = {
        "so_trinh_ky": "TEXT",
        "ngay_ban_hanh": "TEXT",
        "soan_thao": "TEXT",
        "cv_tra_loi": "TEXT",
        "scope": "TEXT DEFAULT 'personal'",
        "download_url": "TEXT",
        "view_url": "TEXT",
        "has_update": "INTEGER DEFAULT 0"
    }
    for col_name, col_type in new_out_cols.items():
        if col_name not in existing_out_cols:
            cursor.execute(f"ALTER TABLE outgoing_docs ADD COLUMN {col_name} {col_type}")

    # Tự động dọn dẹp các bản ghi trùng lặp (chỉ nhóm theo số đến khi có số đến thực tế)
    cursor.execute("""
    DELETE FROM incoming_docs 
    WHERE so_den IS NOT NULL AND TRIM(so_den) != '' AND rowid NOT IN (
        SELECT MAX(rowid) FROM incoming_docs WHERE TRIM(so_den) != '' GROUP BY so_den, scope
    )
    """)
    cursor.execute("""
    DELETE FROM outgoing_docs 
    WHERE so_di IS NOT NULL AND TRIM(so_di) != '' AND rowid NOT IN (
        SELECT MAX(rowid) FROM outgoing_docs WHERE TRIM(so_di) != '' GROUP BY so_di, scope
    )
    """)
    cursor.execute("""
    DELETE FROM outgoing_docs 
    WHERE LOWER(trich_yeu) LIKE '%không phải trả lời cho công văn đến%'
       OR trich_yeu = 'Trích yếu'
       OR so_di = 'Số đến'
       OR so_trinh_ky = 'Số trình ký'
       OR (soan_thao IS NULL AND so_trinh_ky IS NULL)
    """)

    # Bảng theo dõi nhiệm vụ (nhiemvu.drvn.gov.vn)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS drvn_tasks (
        id TEXT PRIMARY KEY,
        code TEXT,
        title TEXT,
        source TEXT,
        department TEXT,
        assignee TEXT,
        coordinators TEXT,
        priority TEXT DEFAULT 'binh_thuong',
        status TEXT DEFAULT 'dang_xu_ly',
        start_date TEXT,
        due_date TEXT,
        completed_date TEXT,
        progress INTEGER DEFAULT 0,
        report_content TEXT,
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Khởi tạo dữ liệu mẫu thực tế của DRVN nếu bảng nhiệm vụ đang trống
    cursor.execute("SELECT COUNT(*) FROM drvn_tasks")
    if cursor.fetchone()[0] == 0:
        sample_tasks = [
            ("NV-2026-001", "NV-2026-001", "Rà soát các văn bản QPPL liên quan đến Luật Đường bộ và các Nghị định hướng dẫn thi hành", "Nghị quyết số 12/NQ-CP của Chính phủ & Chỉ đạo của Cục trưởng", "Phòng Pháp chế - Thanh tra", "Nguyễn Văn Hùng", "Phòng Quản lý vận tải, Phòng Kế hoạch - Đầu tư", "khan", "dang_xu_ly", "10/11/2026", "27/11/2026", None, 75, "Đã hoàn thành dự thảo lần 2 lấy ý kiến các đơn vị", "Nhiệm vụ trọng tâm quý IV"),
            ("NV-2026-002", "NV-2026-002", "Triển khai hệ thống giám sát và xử lý vi phạm nồng độ cồn, tải trọng phương tiện toàn quốc", "Công văn số 8707/BQP-PC & Chỉ đạo Phó Cục trưởng Ngô Lâm Phó", "Phòng Quản lý vận tải", "Trần Trung Hà", "Văn phòng Cục, Các Khu QLĐB", "khan", "dang_xu_ly", "01/11/2026", "30/11/2026", None, 60, "Đang kết nối API với Trung tâm dữ liệu Cục C08", "Đôn đốc trước ngày 25/11"),
            ("NV-2026-003", "NV-2026-003", "Báo cáo công tác chuẩn bị phục vụ nhu cầu đi lại của nhân dân dịp Tết Nguyên đán 2027", "Chỉ đạo của Bộ trưởng Bộ Giao thông vận tải", "Phòng Quản lý vận tải", "Tăng Tuấn Linh", "Các Sở GTVT địa phương", "binh_thuong", "dang_xu_ly", "15/11/2026", "05/12/2026", None, 40, "Đã ban hành văn bản đôn đốc các bến xe và doanh nghiệp", "Kế hoạch cao điểm Tết"),
            ("NV-2026-004", "NV-2026-004", "Khắc phục các điểm đen tai nạn giao thông trên tuyến Quốc lộ 1A và Quốc lộ 14", "Kết luận cuộc họp giao ban tháng 10/2026 của Cục", "Phòng Quản lý bảo trì kết cấu hạ tầng", "Lê Hoàng Long", "Khu Quản lý đường bộ I, II, III, IV", "khan", "qua_han", "01/10/2026", "15/11/2026", None, 50, "Đang hoàn thiện hồ sơ thiết kế điều chỉnh tại Km 125+300", "Chậm tiến độ 5 ngày"),
            ("NV-2026-005", "NV-2026-005", "Tổng hợp báo cáo tiến độ giải ngân vốn đầu tư công và vốn sự nghiệp kinh tế năm 2026", "Văn bản số 18699/BXD-KHTC & Bộ Tài chính", "Phòng Kế hoạch - Đầu tư", "Đỗ Quốc Phong", "Phòng Tài chính - Kế toán", "khan", "dang_xu_ly", "05/11/2026", "24/11/2026", None, 85, "Đã giải ngân đạt 82.4% kế hoạch giao", "Sắp đến hạn báo cáo"),
            ("NV-2026-006", "NV-2026-006", "Hoàn thiện đề án Chuyển đổi số ngành đường bộ và tích hợp CSDL Giấy phép lái xe", "Quyết định số 06/QĐ-TTg của Thủ tướng Chính phủ (Đề án 06)", "Phòng KHCN, Môi trường và HTQT", "Vũ Minh Tuấn", "Trung tâm CNTT, C06 Bộ Công an", "quan_trong", "hoan_thanh", "01/09/2026", "10/11/2026", "08/11/2026", 100, "Đã hoàn thành nghiệm thu giai đoạn 1 và tích hợp VNeID", "Hoàn thành trước hạn 2 ngày"),
            ("NV-2026-007", "NV-2026-007", "Kiểm tra, rà soát hệ thống thu phí tự động không dừng (ETC) tại các trạm BOT trên toàn quốc", "Ý kiến chỉ đạo của Cục trưởng", "Phòng Quản lý bảo trì kết cấu hạ tầng", "Phạm Văn Nam", "Công ty VETC, VDTC", "binh_thuong", "hoan_thanh", "15/10/2026", "12/11/2026", "12/11/2026", 100, "Đã hoàn thành kiểm tra hiện trường 112 trạm BOT", "Đạt chuẩn kỹ thuật"),
            ("NV-2026-008", "NV-2026-008", "Xây dựng phương án phân luồng giao thông phục vụ sửa chữa cầu Thăng Long và cầu Gianh", "Kế hoạch bảo trì năm 2026 của Cục Đường bộ VN", "Phòng Quản lý bảo trì kết cấu hạ tầng", "Bùi Đức Thịnh", "Phòng Quản lý vận tải, Cảnh sát giao thông", "khan", "qua_han", "15/10/2026", "18/11/2026", None, 30, "Đang chờ ý kiến thống nhất từ Cục CSGT", "Cần họp khẩn liên ngành"),
            ("NV-2026-009", "NV-2026-009", "Tổ chức tập huấn nghiệp vụ cấp đổi phù hiệu, biển hiệu xe kinh doanh vận tải qua mạng", "Kế hoạch đào tạo nội bộ năm 2026", "Phòng Quản lý vận tải", "Trần Trung Hà", "Văn phòng Cục", "binh_thuong", "hoan_thanh", "01/11/2026", "16/11/2026", "15/11/2026", 100, "Đã tập huấn cho 63 Sở GTVT", "100% cán bộ nắm vững quy trình"),
            ("NV-2026-010", "NV-2026-010", "Kiểm tra công tác phòng chống thiên tai, bão lũ và đảm bảo giao thông an toàn mùa mưa bão", "Công điện khẩn của Ban Chỉ huy PCTT&TKCN Bộ GTVT", "Văn phòng Cục", "Lê Văn Tiến", "Toàn bộ các Phòng, Khu QLĐB", "khan", "dang_xu_ly", "12/11/2026", "22/11/2026", None, 90, "Các đội ứng trực đã sẵn sàng 24/7", "Đang theo dõi bão số 9")
        ]
        for t in sample_tasks:
            cursor.execute("""
            INSERT OR REPLACE INTO drvn_tasks (
                id, code, title, source, department, assignee, coordinators,
                priority, status, start_date, due_date, completed_date,
                progress, report_content, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, t)

    conn.commit()
    conn.close()

def parse_date_vietnam(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            pass
    return None

def calculate_days_remaining(han_str):
    d = parse_date_vietnam(han_str)
    if not d:
        return 999
    today = date.today()
    return (d - today).days

def parse_leaders(chi_dao_text):
    cuc = ""
    phong = ""
    if not chi_dao_text:
        return cuc, phong

    parts = chi_dao_text.split("Trưởng phòng")
    if len(parts) > 1:
        cuc = parts[0].strip()
        phong = "Trưởng phòng " + parts[1].strip()
    else:
        parts_pho = chi_dao_text.split("Phó Trưởng phòng")
        if len(parts_pho) > 1:
            cuc = parts_pho[0].strip()
            phong = "Phó Trưởng phòng " + parts_pho[1].strip()
        else:
            cuc = chi_dao_text.strip()
    return cuc, phong

def get_warning_days():
    val = get_setting("warning_days", "3")
    try:
        return max(1, int(val))
    except:
        return 3

def upsert_incoming_doc(doc):
    conn = get_connection()
    cursor = conn.cursor()

    doc_id = doc.get("id") or f"{doc.get('so_den', '')}_{doc.get('so_ky_hieu', '')}"
    han_xu_ly = doc.get("han_xu_ly", "").strip()
    days_left = calculate_days_remaining(han_xu_ly)
    warning_days = get_warning_days()
    is_urgent = 1 if ((days_left <= warning_days and days_left != 999) or (days_left < 0)) else 0

    chi_dao = doc.get("chi_dao", "")
    ld_cuc, ld_phong = parse_leaders(chi_dao)

    so_den = doc.get("so_den", "").strip()
    scope = doc.get("scope", "personal").strip()
    detail_url = doc.get("detail_url", "")
    raw_attach = doc.get("attachments")
    attach_json = json.dumps(raw_attach, ensure_ascii=False) if isinstance(raw_attach, list) else (raw_attach or "")
    
    phan_loai_xu_ly = doc.get("phan_loai_xu_ly", "").strip()
    if not phan_loai_xu_ly:
        phan_loai_xu_ly = "Công văn đến phải xử lý" if han_xu_ly else "Nhận để biết và lưu"

    # Kiểm tra bản ghi trùng: ưu tiên ID, link chi tiết hoặc số/ký hiệu + ngày ban hành
    existing_row = None
    if detail_url:
        cursor.execute("SELECT id, is_read, attachments, phan_loai_xu_ly FROM incoming_docs WHERE id = ? OR (detail_url = ? AND scope = ?)", (doc_id, detail_url, scope))
        existing_row = cursor.fetchone()
    if not existing_row and so_den and re.search(r'\d+', so_den):
        cursor.execute("SELECT id, is_read, attachments, phan_loai_xu_ly FROM incoming_docs WHERE id = ? OR (so_den = ? AND scope = ?)", (doc_id, so_den, scope))
        existing_row = cursor.fetchone()
    if not existing_row and doc.get("so_ky_hieu"):
        cursor.execute("SELECT id, is_read, attachments, phan_loai_xu_ly FROM incoming_docs WHERE id = ? OR (so_ky_hieu = ? AND ngay_ban_hanh = ? AND scope = ?)", (doc_id, doc.get("so_ky_hieu"), doc.get("ngay_ban_hanh", ""), scope))
        existing_row = cursor.fetchone()
    if not existing_row:
        cursor.execute("SELECT id, is_read, attachments, phan_loai_xu_ly FROM incoming_docs WHERE id = ?", (doc_id,))
        existing_row = cursor.fetchone()

    row = existing_row

    is_new = False
    if row is None:
        is_new = True
        cursor.execute("""
        INSERT INTO incoming_docs (
            id, so_den, so_ky_hieu, ngay_ban_hanh, trich_yeu, ngay_den,
            han_xu_ly, thoi_han, chi_dao, lanh_dao_cuc, lanh_dao_phong,
            xu_ly_chinh, phoi_hop, phan_loai_xu_ly, scope, download_url, view_url, detail_url, attachments,
            is_read, is_urgent, days_remaining
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (
            doc_id, so_den, doc.get("so_ky_hieu", ""),
            doc.get("ngay_ban_hanh", ""), doc.get("trich_yeu", ""),
            doc.get("ngay_den", ""), han_xu_ly, doc.get("thoi_han", ""),
            chi_dao, ld_cuc, ld_phong,
            doc.get("xu_ly_chinh", ""), doc.get("phoi_hop", ""),
            phan_loai_xu_ly,
            scope, doc.get("download_url", ""), doc.get("view_url", ""),
            detail_url, attach_json,
            is_urgent, days_left
        ))
    else:
        target_id = row["id"]
        # Nếu bản ghi cũ đã có attachments mà bản mới chưa có, giữ lại attachments cũ
        final_attach = attach_json if attach_json else (row["attachments"] or "")
        # Nếu đã có phân loại từ trước và bản mới không chỉ định rõ, giữ lại
        if not doc.get("phan_loai_xu_ly") and row["phan_loai_xu_ly"]:
            phan_loai_xu_ly = row["phan_loai_xu_ly"]

        cursor.execute("""
        UPDATE incoming_docs SET
            so_den = ?, so_ky_hieu = ?, ngay_ban_hanh = ?, trich_yeu = ?,
            ngay_den = ?, han_xu_ly = ?, thoi_han = ?, chi_dao = ?,
            lanh_dao_cuc = ?, lanh_dao_phong = ?, xu_ly_chinh = ?, phoi_hop = ?,
            phan_loai_xu_ly = ?, scope = ?, download_url = ?, view_url = ?, detail_url = ?, attachments = ?,
            is_urgent = ?, days_remaining = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (
            so_den, doc.get("so_ky_hieu", ""),
            doc.get("ngay_ban_hanh", ""), doc.get("trich_yeu", ""),
            doc.get("ngay_den", ""), han_xu_ly, doc.get("thoi_han", ""),
            chi_dao, ld_cuc, ld_phong, doc.get("xu_ly_chinh", ""), doc.get("phoi_hop", ""),
            phan_loai_xu_ly, scope, doc.get("download_url", ""), doc.get("view_url", ""),
            detail_url, final_attach,
            is_urgent, days_left, target_id
        ))

    conn.commit()
    conn.close()
    return is_new

def update_doc_phan_loai(doc_id, phan_loai):
    """Cập nhật phân loại xử lý cho công văn"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE incoming_docs SET phan_loai_xu_ly = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (phan_loai, doc_id))
    conn.commit()
    conn.close()

def update_doc_attachments(doc_id, attachments_list):
    """Cập nhật danh sách tệp đính kèm đầy đủ cho một công văn"""
    conn = get_connection()
    cursor = conn.cursor()
    attach_json = json.dumps(attachments_list, ensure_ascii=False)
    cursor.execute("UPDATE incoming_docs SET attachments = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (attach_json, doc_id))
    conn.commit()
    conn.close()

def get_doc_attachments_raw(doc):
    """Lấy danh sách tệp đính kèm thực tế đã lưu trong DB (không kèm fallback)"""
    raw = doc.get("attachments", "")
    if isinstance(raw, list):
        return raw
    if raw and isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed
        except Exception:
            pass
    return []

def get_doc_attachments_by_id(doc_id):
    """Lấy danh sách tệp đính kèm thực tế theo ID công văn"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT attachments FROM incoming_docs WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        try:
            parsed = json.loads(row[0])
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed
        except Exception:
            pass
    return []

def get_doc_attachments(doc):
    """Lấy danh sách tất cả các tệp đính kèm của công văn"""
    raw = doc.get("attachments", "")
    if isinstance(raw, list):
        return raw
    if raw and isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed
        except Exception:
            pass

    # Nếu chưa có danh sách attachments nhưng có download_url
    d_url = doc.get("download_url", "")
    v_url = doc.get("view_url", "") or d_url
    if d_url:
        so_kh = doc.get("so_ky_hieu", "Văn bản")
        return [{
            "name": f"Văn bản {so_kh}.pdf",
            "download_url": d_url,
            "view_url": v_url,
            "info": "Tệp đính kèm chính"
        }]
    return []

def get_officer_name():
    return get_setting("officer_name", "Tăng Tuấn Linh")

def upsert_outgoing_doc(doc):
    conn = get_connection()
    cursor = conn.cursor()
    doc_id = doc.get("id") or f"out_{doc.get('so_trinh_ky', '')}_{doc.get('so_di', '')}_{doc.get('soan_thao', '')}"
    so_trinh_ky = doc.get("so_trinh_ky", "").strip()
    so_di = doc.get("so_di", "").strip()
    trich_yeu = doc.get("trich_yeu", "").strip()
    soan_thao = doc.get("soan_thao", "").strip()
    new_status = doc.get("trang_thai", "")

    # Bỏ qua hoàn toàn các dòng giả lập không phải trả lời
    if "không phải trả lời cho công văn đến" in trich_yeu.lower():
        conn.close()
        return False

    cursor.execute("SELECT id, trang_thai FROM outgoing_docs WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    if not row and so_trinh_ky and trich_yeu:
        cursor.execute("SELECT id, trang_thai FROM outgoing_docs WHERE so_trinh_ky = ? AND trich_yeu = ?", (so_trinh_ky, trich_yeu))
        row = cursor.fetchone()

    has_update = 0
    if row:
        target_id = row["id"]
        old_status = row["trang_thai"]
        if old_status != new_status:
            has_update = 1

        cursor.execute("""
        UPDATE outgoing_docs SET
            so_di = CASE WHEN ? != '' THEN ? ELSE so_di END,
            ngay_ban_hanh = CASE WHEN ? != '' THEN ? ELSE ngay_ban_hanh END,
            soan_thao = CASE WHEN ? != '' THEN ? ELSE soan_thao END,
            cv_tra_loi = CASE WHEN ? != '' THEN ? ELSE cv_tra_loi END,
            trang_thai = ?,
            has_update = ?,
            download_url = CASE WHEN ? != '' THEN ? ELSE download_url END,
            view_url = CASE WHEN ? != '' THEN ? ELSE view_url END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """, (
            so_di, so_di,
            doc.get("ngay_ban_hanh", ""), doc.get("ngay_ban_hanh", ""),
            soan_thao, soan_thao,
            doc.get("cv_tra_loi", ""), doc.get("cv_tra_loi", ""),
            new_status, has_update,
            doc.get("download_url", ""), doc.get("download_url", ""),
            doc.get("view_url", ""), doc.get("view_url", ""),
            target_id
        ))
    else:
        cursor.execute("""
        INSERT INTO outgoing_docs (
            id, so_trinh_ky, so_di, so_ky_hieu, trich_yeu, ngay_tao,
            ngay_ban_hanh, trang_thai, nguoi_ky, soan_thao, cv_tra_loi,
            scope, download_url, view_url, has_update
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            doc_id, so_trinh_ky, so_di,
            doc.get("so_ky_hieu", ""), trich_yeu,
            doc.get("ngay_tao", ""), doc.get("ngay_ban_hanh", ""),
            new_status, doc.get("nguoi_ky", ""),
            soan_thao, doc.get("cv_tra_loi", ""),
            doc.get("scope", "personal"), doc.get("download_url", ""), doc.get("view_url", "")
        ))

    conn.commit()
    conn.close()
    return has_update == 1

def get_incoming_docs_filtered(scope=None, from_date=None, to_date=None, unread_only=False):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM incoming_docs WHERE 1=1"
    params = []

    if scope:
        query += " AND scope = ?"
        params.append(scope)
    if unread_only:
        query += " AND is_read = 0"

    cursor.execute(query + " ORDER BY created_at DESC", params)
    rows = cursor.fetchall()
    conn.close()

    result = [dict(r) for r in rows]

    if from_date or to_date:
        filtered = []
        for d in result:
            doc_d = parse_date_vietnam(d.get("ngay_den") or d.get("ngay_ban_hanh"))
            if not doc_d:
                filtered.append(d)
                continue
            if from_date and doc_d < from_date:
                continue
            if to_date and doc_d > to_date:
                continue
            filtered.append(d)
        return filtered

    return result

def get_outgoing_docs_filtered(scope=None, from_date=None, to_date=None, officer_name=None):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM outgoing_docs WHERE LOWER(trich_yeu) NOT LIKE '%không phải trả lời cho công văn đến%'"
    params = []

    if scope == "personal":
        name = (officer_name or get_officer_name()).strip()
        query += " AND (scope = 'personal' OR soan_thao LIKE ?)"
        params.append(f"%{name}%")
    elif scope == "department":
        query += " AND scope = 'department'"
    elif scope == "processing":
        query += " AND (scope = 'processing' OR trang_thai LIKE '%Chờ%' OR trang_thai LIKE '%Trình ký%')"
    elif scope:
        query += " AND scope = ?"
        params.append(scope)

    cursor.execute(query + " ORDER BY created_at DESC", params)
    rows = cursor.fetchall()
    conn.close()

    result = [dict(r) for r in rows]

    filtered = []
    if from_date or to_date:
        for d in result:
            doc_d = parse_date_vietnam(d.get("ngay_ban_hanh") or d.get("ngay_tao"))
            if not doc_d:
                # Văn bản dự thảo chưa có ngày ban hành luôn được hiển thị
                filtered.append(d)
                continue
            if from_date and doc_d < from_date:
                continue
            if to_date and doc_d > to_date:
                continue
            filtered.append(d)
    else:
        filtered = result

    # Sắp xếp chuẩn: ngày ban hành mới nhất lên đầu, tiếp đến là số đi giảm dần; văn bản chưa có ngày xuống cuối
    def sort_outgoing(x):
        d = parse_date_vietnam(x.get("ngay_ban_hanh") or x.get("ngay_tao"))
        d_val = d.strftime("%Y%m%d") if d else "00000000"
        s_di = x.get("so_di", "")
        try:
            m = re.search(r'\d+', str(s_di))
            num = int(m.group(0)) if m else 0
        except:
            num = 0
        return (d_val, num)

    filtered.sort(key=sort_outgoing, reverse=True)
    return filtered

def get_urgent_docs(scope=None, warning_days=None):
    if warning_days is None:
        warning_days = get_warning_days()
    conn = get_connection()
    cursor = conn.cursor()
    query = """
    SELECT * FROM incoming_docs 
    WHERE (days_remaining <= ? OR days_remaining < 0) AND days_remaining != 999
    """
    params = [warning_days]
    if scope:
        query += " AND scope = ?"
        params.append(scope)
    query += " ORDER BY days_remaining ASC, created_at DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_outgoing_status_updates(scope=None):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM outgoing_docs WHERE 1=1"
    params = []
    if scope:
        query += " AND scope = ?"
        params.append(scope)
    query += " ORDER BY updated_at DESC LIMIT 20"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def mark_as_read(doc_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE incoming_docs SET is_read = 1 WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()

def mark_all_as_read():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE incoming_docs SET is_read = 1")
    conn.commit()
    conn.close()

def recalculate_urgency():
    """Cập nhật lại trạng thái khẩn và số ngày còn lại của toàn bộ công văn theo cấu hình ngày mới"""
    warning_days = get_warning_days()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, han_xu_ly FROM incoming_docs")
    rows = cursor.fetchall()
    for r in rows:
        d_left = calculate_days_remaining(r["han_xu_ly"])
        urg = 1 if ((d_left <= warning_days and d_left != 999) or (d_left < 0)) else 0
        cursor.execute("UPDATE incoming_docs SET days_remaining = ?, is_urgent = ? WHERE id = ?", (d_left, urg, r["id"]))
    conn.commit()
    conn.close()

def get_counts():
    warning_days = get_warning_days()
    conn = get_connection()
    cursor = conn.cursor()
    # Đếm số lượng công văn cá nhân chưa đọc
    cursor.execute("SELECT COUNT(*) FROM incoming_docs WHERE scope = 'personal' AND is_read = 0")
    unread = cursor.fetchone()[0]

    # Đếm số lượng công văn cá nhân gần đến hạn hoặc quá hạn
    cursor.execute("""
    SELECT COUNT(*) FROM incoming_docs 
    WHERE scope = 'personal' AND (days_remaining <= ? OR days_remaining < 0) AND days_remaining != 999
    """, (warning_days,))
    urgent = cursor.fetchone()[0]

    officer = get_officer_name()
    cursor.execute("""
    SELECT COUNT(*) FROM outgoing_docs 
    WHERE (scope = 'personal' OR soan_thao LIKE ?) 
      AND LOWER(trich_yeu) NOT LIKE '%không phải trả lời cho công văn đến%'
    """, (f"%{officer}%",))
    outgoing = cursor.fetchone()[0]

    conn.close()
    return {"unread": unread, "urgent": urgent, "outgoing": outgoing}

def get_setting(key, default=""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

# =============================================================================
# HỆ THỐNG THEO DÕI NHIỆM VỤ (nhiemvu.drvn.gov.vn)
# =============================================================================

def clear_sample_tasks():
    """Xóa dữ liệu nhiệm vụ mẫu (NV-2026-xxx) khi đã đồng bộ được dữ liệu thật."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM drvn_tasks WHERE id LIKE 'NV-2026-%'")
    conn.commit()
    conn.close()

def upsert_task(task):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO drvn_tasks (
        id, code, title, source, department, assignee, coordinators,
        priority, status, start_date, due_date, completed_date,
        progress, report_content, note, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        task.get("id"), task.get("code"), task.get("title"), task.get("source"),
        task.get("department"), task.get("assignee"), task.get("coordinators"),
        task.get("priority", "binh_thuong"), task.get("status", "dang_xu_ly"),
        task.get("start_date"), task.get("due_date"), task.get("completed_date"),
        task.get("progress", 0), task.get("report_content"), task.get("note")
    ))
    conn.commit()
    conn.close()

def get_tasks_filtered(department=None, status=None, priority=None, keyword=None):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM drvn_tasks WHERE 1=1"
    params = []

    if department and department != "Tất cả đơn vị":
        query += " AND department = ?"
        params.append(department)

    if status and status != "Tất cả trạng thái":
        status_map = {
            "Đang thực hiện": "dang_xu_ly",
            "Đã hoàn thành": "hoan_thanh",
            "Quá hạn": "qua_han",
            "Chờ duyệt": "cho_duyet"
        }
        val = status_map.get(status, status)
        query += " AND status = ?"
        params.append(val)

    if priority and priority != "Tất cả ưu tiên":
        priority_map = {
            "Hỏa tốc / Khẩn": "khan",
            "Quan trọng": "quan_trong",
            "Bình thường": "binh_thuong"
        }
        val = priority_map.get(priority, priority)
        query += " AND priority = ?"
        params.append(val)

    if keyword:
        kw = f"%{keyword.strip()}%"
        query += " AND (title LIKE ? OR code LIKE ? OR assignee LIKE ? OR source LIKE ?)"
        params.extend([kw, kw, kw, kw])

    query += " ORDER BY CASE priority WHEN 'khan' THEN 1 WHEN 'quan_trong' THEN 2 ELSE 3 END, id ASC"

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_task_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM drvn_tasks")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM drvn_tasks WHERE status = 'dang_xu_ly'")
    in_progress = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM drvn_tasks WHERE status = 'hoan_thanh'")
    completed = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM drvn_tasks WHERE status = 'qua_han'")
    overdue = cursor.fetchone()[0]

    # Sắp đến hạn: Hạn trong vòng 3 ngày tới và đang xử lý
    today = date.today()
    cursor.execute("SELECT due_date FROM drvn_tasks WHERE status = 'dang_xu_ly'")
    near_due = 0
    for row in cursor.fetchall():
        d_str = row[0]
        d = parse_date_vietnam(d_str)
        if d:
            delta = (d - today).days
            if 0 <= delta <= 3:
                near_due += 1

    conn.close()
    rate = int((completed / total * 100) if total > 0 else 0)
    return {
        "total": total,
        "in_progress": in_progress,
        "completed": completed,
        "overdue": overdue,
        "near_due": near_due,
        "completion_rate": rate
    }

def get_tasks_by_department():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT department,
           COUNT(*) as total,
           SUM(CASE WHEN status = 'dang_xu_ly' THEN 1 ELSE 0 END) as in_progress,
           SUM(CASE WHEN status = 'hoan_thanh' THEN 1 ELSE 0 END) as completed,
           SUM(CASE WHEN status = 'qua_han' THEN 1 ELSE 0 END) as overdue
    FROM drvn_tasks
    GROUP BY department
    ORDER BY total DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# Tự động khởi tạo cấu trúc CSDL nếu chưa có
init_db()

save_fld = get_setting("save_folder", DEFAULT_SAVE_FOLDER)
if not os.path.exists(save_fld):
    try:
        os.makedirs(save_fld, exist_ok=True)
    except:
        pass
