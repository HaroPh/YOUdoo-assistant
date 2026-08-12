"""Tool MCP domain CRM (crm.lead / mail.activity) — spec SP-1B §3c task 7.

Mọi đường ra Odoo đi qua odoo_call.odoo() (log_activity dùng thêm get_uid()
để gán người phụ trách hoạt động — cùng module odoo_call, không phải đường
tắt ra Odoo riêng).
"""
from server import mcp
from odoo_call import odoo, get_uid
from helpers import envelope, today_iso, resolve_unique


@mcp.tool()
def create_lead(name: str = "", contact_name: str = "", partner_name: str = "",
                email: str = "", phone: str = "", description: str = "") -> str:
    """Tạo lead CRM mới (khách tiềm năng liên hệ). Tool phẳng — coordinator
    phía backend đã slot-check/derive title trước khi gọi.
    YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        name: Tiêu đề lead (bắt buộc — coordinator tự derive nếu user không nêu).
        contact_name: Tên người liên hệ.
        partner_name: Tên công ty.
        email: Email liên hệ.
        phone: Số điện thoại.
        description: Ghi chú thêm.
    """
    try:
        if not str(name or "").strip():
            return envelope(False, "Thiếu tiêu đề lead.")
        vals = {"name": name, "type": "lead"}
        for k, v in (("contact_name", contact_name), ("partner_name", partner_name),
                     ("email_from", email), ("phone", phone),
                     ("description", description)):
            if str(v or "").strip():
                vals[k] = v
        lead_id = odoo("crm.lead", "create", [vals])
        return envelope(True, f"Đã tạo lead '{name}'.",
                        ref=name, model="crm.lead", res_id=lead_id, state="lead")
    except Exception as e:  # noqa: BLE001 — never raise through the MCP tool
        return envelope(False, f"Lỗi khi tạo lead: {e}")


@mcp.tool()
def convert_lead(lead_id: int, assignee_name: str = "") -> str:
    """Chuyển một lead CRM thành cơ hội (opportunity), tùy chọn giao cho một
    nhân viên phụ trách. YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        lead_id: ID lead cần chuyển.
        assignee_name: Tên nhân viên phụ trách (tìm gần đúng, tùy chọn).
    """
    try:
        rows = odoo("crm.lead", "search_read",
                   [[["id", "=", lead_id]]],
                   {"fields": ["id", "name", "type", "partner_id", "active"],
                    "limit": 1})
        if not rows:
            return envelope(False, f"Không tìm thấy lead ID {lead_id}.")
        lead = rows[0]
        if lead["type"] == "opportunity":
            return envelope(False, f"Lead '{lead['name']}' đã là cơ hội rồi.")
        if not lead.get("active", True):
            return envelope(False, f"Lead '{lead['name']}' đã bị lưu trữ.")

        # Resolve assignee TRƯỚC khi mutate — ambiguous/không tìm thấy phải fail
        # trước convert, không phải sau (Global Constraint).
        user_id = None
        if str(assignee_name or "").strip():
            urows = odoo("res.users", "name_search", [assignee_name], {"limit": 6})
            cand = [{"id": r[0], "name": r[1]} for r in urows]
            row, msg = resolve_unique(
                cand, "nhân viên",
                describe=lambda r: f"{r['name']} (ID {r['id']})",
                hint="Vui lòng nêu đúng tên nhân viên.")
            if msg:
                return envelope(False, msg)
            user_id = row["id"]

        # Probe-verified (2026-07-19): partner arg KHÔNG nhận int qua XML-RPC
        # (Odoo 19 cần recordset — AttributeError 'int' has no 'id') và truyền
        # False sẽ WIPE partner_id sẵn có → đọc partner trước, convert với
        # False, rồi restore/assign bằng MỘT lệnh write (write đã verify chạy).
        had_partner = lead["partner_id"][0] if lead.get("partner_id") else None
        odoo("crm.lead", "convert_opportunity", [[lead_id], False])
        restore = {}
        if had_partner:
            restore["partner_id"] = had_partner
        if user_id is not None:
            restore["user_id"] = user_id
        if restore:
            odoo("crm.lead", "write", [[lead_id], restore])

        after = odoo("crm.lead", "read", [[lead_id]],
                    {"fields": ["name", "type", "user_id"]})[0]
        if after["type"] != "opportunity":
            return envelope(False,
                            f"Chuyển lead '{lead['name']}' không thành công — "
                            f"vui lòng kiểm tra trên Odoo.")
        who = (f", giao cho {after['user_id'][1]}"
               if after.get("user_id") else "")
        return envelope(True,
                        f"Đã chuyển lead '{after['name']}' thành cơ hội{who}.",
                        ref=after["name"], model="crm.lead", res_id=lead_id,
                        state="opportunity")
    except Exception as e:  # noqa: BLE001
        return envelope(False, f"Lỗi khi chuyển lead thành cơ hội: {e}")


def _resolve_assignee(assignee: str):
    """→ user_id (int) | câu từ chối (str).

    Thứ tự: login chính xác → name chính xác → tìm gần đúng theo name.
    Trùng nhiều ở bước cuối thì TỪ CHỐI và liệt kê, không tự chọn — fail-closed
    giống mọi chỗ giải thực thể khác trong dự án.

    Chỉ xét người dùng nội bộ (share=False): người dùng portal không nhận
    việc được.
    """
    internal_only = [["share", "=", False]]
    for domain in ([["login", "=", assignee]] + internal_only,
                   [["name", "=", assignee]] + internal_only):
        rows = odoo("res.users", "search_read", [domain],
                    {"fields": ["id", "name", "login"], "limit": 2})
        if len(rows) == 1:
            return rows[0]["id"]
    rows = odoo("res.users", "search_read",
                [[["name", "ilike", assignee]] + internal_only],
                {"fields": ["id", "name", "login"], "limit": 6})
    if not rows:
        return f"Không tìm thấy người dùng '{assignee}'."
    if len(rows) > 1:
        names = ", ".join(f"{r['name']} ({r['login']})" for r in rows)
        return f"Có nhiều người khớp '{assignee}': {names}. Vui lòng nêu rõ hơn."
    return rows[0]["id"]


@mcp.tool()
def log_activity(res_model: str, res_id: int, activity_type: str, summary: str,
                 date_deadline: str = "", assignee: str = "") -> str:
    """Lên lịch một hoạt động (To-Do, Call, Meeting, Email, Document...) gắn
    vào MỘT chứng từ bất kỳ trong Odoo. YÊU CẦU XÁC NHẬN từ người dùng trước
    khi gọi.

    Loại hợp lệ do chính Odoo quyết định: mail.activity.type có res_model
    RỖNG dùng được cho mọi model, có giá trị thì chỉ model đó (vd
    "Maintenance Request" chỉ gắn được vào maintenance.request). KHÔNG có
    danh sách cấm viết tay ở đây.

    Args:
        res_model: Model của chứng từ, vd "sale.order".
        res_id: ID chứng từ (coordinator đã giải từ mã người dùng gõ).
        activity_type: Tên loại trong Odoo, vd "To-Do".
        summary: Nội dung ngắn gọn.
        date_deadline: Hạn (YYYY-MM-DD); bỏ trống = hôm nay.
        assignee: Người nhận — login hoặc tên. Bỏ trống = tài khoản đang gọi.
    """
    try:
        recs = odoo(res_model, "search_read", [[["id", "=", res_id]]],
                    {"fields": ["id", "name"], "limit": 1})
        if not recs:
            return envelope(False, f"Không tìm thấy bản ghi ID {res_id} "
                                   f"trong {res_model}.")
        rec = recs[0]
        ref = rec.get("name") or str(res_id)

        # Lọc NGAY trong domain: tên khớp VÀ (dùng chung mọi model HOẶC đúng
        # model này) (F4). Trước đây lấy 1 dòng theo tên rồi mới so model —
        # nếu có hai loại trùng tên (một dùng chung, một buộc model khác) thì
        # dòng có id nhỏ hơn thắng bất kể có khớp model hay không, khiến một
        # yêu cầu hợp lệ bị từ chối oan.
        types = odoo("mail.activity.type", "search_read",
                     [[["name", "=", activity_type],
                       "|", ["res_model", "=", False], ["res_model", "=", res_model]]],
                     {"fields": ["id", "name", "res_model"], "limit": 1})
        if not types:
            # Tên có tồn tại nhưng buộc vào model khác — tra riêng để GIỮ
            # NGUYÊN thông điệp cũ, không gộp với nhánh "không tồn tại thật"
            # bên dưới thành một câu mơ hồ (F4).
            mismatched = odoo("mail.activity.type", "search_read",
                              [[["name", "=", activity_type]]],
                              {"fields": ["id", "name", "res_model"], "limit": 1})
            if mismatched:
                other = mismatched[0]
                return envelope(False,
                                f"Loại '{other['name']}' chỉ dùng được cho "
                                f"{other['res_model']}, không phải {res_model}.")
            # Tên không tồn tại thật — nêu các loại DÙNG ĐƯỢC cho model này,
            # lấy trực tiếp từ Odoo, không từ danh sách viết tay (F3, spec
            # §4: tập hợp lệ luôn đến từ mail.activity.type, không hard-code).
            # Từ chối này xảy ra SAU cửa xác nhận (user đã đồng ý) — không
            # nêu lựa chọn thì họ không có gì để sửa và thử lại.
            usable = odoo("mail.activity.type", "search_read",
                         [["|", ["res_model", "=", False], ["res_model", "=", res_model]]],
                         {"fields": ["name"]})
            names = ", ".join(sorted(t["name"] for t in usable))
            hint = f" Loại hợp lệ cho {res_model}: {names}." if names else ""
            return envelope(False, f"Loại hoạt động '{activity_type}' không có "
                                   f"trong Odoo.{hint}")
        atype = types[0]

        user_id = get_uid()
        if assignee:
            user_id = _resolve_assignee(assignee)
            if isinstance(user_id, str):        # chuỗi = câu từ chối
                return envelope(False, user_id)

        # Probe-verified (2026-07-19): mail.activity create BẮT BUỘC
        # res_model_id (ir.model id, tra runtime) — shape res_model (char) bị
        # Odoo từ chối. Hai vai non-admin KHÔNG có ir.model read theo mặc
        # định; nhóm "Youdoo AI / Activity" cấp đúng quyền đó (spec §6).
        model_ids = odoo("ir.model", "search", [[["model", "=", res_model]]],
                         {"limit": 1})
        if not model_ids:
            return envelope(False, f"Model '{res_model}' không tồn tại trong Odoo.")

        deadline = date_deadline or today_iso()
        act_id = odoo("mail.activity", "create",
                      [{"res_model_id": model_ids[0], "res_id": res_id,
                        "activity_type_id": atype["id"],
                        "summary": summary,
                        "date_deadline": deadline,
                        "user_id": user_id}])
        return envelope(True,
                        f"Đã lên lịch {atype['name']} cho '{ref}': {summary} "
                        f"— hạn {deadline}.",
                        ref=ref, model="mail.activity", res_id=act_id,
                        state="planned")
    except Exception as e:  # noqa: BLE001
        return envelope(False, f"Lỗi khi lên lịch hoạt động: {e}")
