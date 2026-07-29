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


@mcp.tool()
def log_activity(lead_id: int, activity_type: str, summary: str,
                 date_deadline: str = "") -> str:
    """Lên lịch hoạt động chăm sóc (Call | Meeting) trên một lead/cơ hội CRM.
    activity_type nhận giá trị chuẩn "Call" hoặc "Meeting" (coordinator đã map
    alias tiếng Việt). YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        lead_id: ID lead/cơ hội.
        activity_type: "Call" | "Meeting" (tên loại hoạt động trong Odoo).
        summary: Nội dung ngắn gọn.
        date_deadline: Hạn (YYYY-MM-DD); bỏ trống = hôm nay.
    """
    try:
        rows = odoo("crm.lead", "search_read", [[["id", "=", lead_id]]],
                   {"fields": ["id", "name"], "limit": 1})
        if not rows:
            return envelope(False, f"Không tìm thấy lead/cơ hội ID {lead_id}.")
        lead = rows[0]

        types = odoo("mail.activity.type", "search_read",
                    [[["name", "=", activity_type]]],
                    {"fields": ["id", "name"], "limit": 1})
        if not types:
            return envelope(False, f"Loại hoạt động '{activity_type}' không hợp "
                                   f"lệ. Chỉ nhận: Call, Meeting.")

        # Probe-verified (2026-07-19): mail.activity create BẮT BUỘC res_model_id
        # (ir.model id, tra runtime) — shape res_model (char) bị Odoo từ chối;
        # date_deadline là field required duy nhất, luôn gửi.
        model_ids = odoo("ir.model", "search",
                        [[["model", "=", "crm.lead"]]], {"limit": 1})
        act_id = odoo("mail.activity", "create",
                     [{"res_model_id": model_ids[0], "res_id": lead_id,
                      "activity_type_id": types[0]["id"],
                      "summary": summary,
                      "date_deadline": date_deadline or today_iso(),
                      "user_id": get_uid()}])
        return envelope(True,
                        f"Đã lên lịch {types[0]['name']} cho '{lead['name']}': "
                        f"{summary} — hạn {date_deadline or today_iso()}.",
                        ref=lead["name"], model="mail.activity", res_id=act_id,
                        state="planned")
    except Exception as e:  # noqa: BLE001
        return envelope(False, f"Lỗi khi lên lịch hoạt động: {e}")
