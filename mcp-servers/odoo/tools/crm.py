"""Tool MCP domain CRM (crm.lead / mail.activity) — spec SP-1B §3c task 7.

Mọi đường ra Odoo đi qua odoo_call.odoo() (log_activity dùng thêm get_uid()
để gán người phụ trách hoạt động — cùng module odoo_call, không phải đường
tắt ra Odoo riêng).
"""
import json

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
        # Lệnh Odoo ĐẦU TIÊN trên model đích — bọc RIÊNG lệnh này. Lỗi ở đúng
        # chỗ này chỉ có một nghĩa: vai hiện tại không đọc được loại chứng từ
        # này (thiếu quyền) hoặc model không tồn tại — biết được từ VỊ TRÍ lỗi
        # xảy ra, không cần đọc nội dung lỗi. KHÔNG dò chữ/mã lỗi Odoo (thông
        # điệp Odoo trả về theo ngôn ngữ tài khoản, không ổn định giữa các
        # bản cài đặt) và KHÔNG lộ nguyên văn lỗi hay tên nhóm quyền Odoo ra
        # ngoài.
        try:
            recs = odoo(res_model, "search_read", [[["id", "=", res_id]]],
                        {"fields": ["id", "name"], "limit": 1})
        except Exception:  # noqa: BLE001 — chỉ bọc lệnh này, không đổi hành
                            # vi các lệnh Odoo khác trong hàm
            return envelope(False,
                            f"Không đọc được dữ liệu '{res_model}' — model "
                            f"này có thể không tồn tại hoặc tài khoản hiện "
                            f"tại không có quyền truy cập.")
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


@mcp.tool()
def close_activity(activity_id: int, note: str = "") -> str:
    """Đánh dấu MỘT việc (hoạt động/activity) đang được giao cho tài khoản hiện
    tại là ĐÃ HOÀN TẤT. YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Chỉ đóng được việc giao cho CHÍNH tài khoản đang gọi. Đo trên Odoo thật
    2026-08-14: Odoo KHÔNG chặn một tài khoản đóng việc của người khác
    (ai-warehouse đóng trót lọt việc của ai-accounting), nên bộ lọc user_id
    dưới đây là lớp cưỡng chế DUY NHẤT — không được bỏ.

    Đóng việc KHÔNG xoá bản ghi: Odoo đặt active=False, state='done',
    date_done=<hôm nay>, và ghi một tin vào chatter của chứng từ kèm nguyên văn
    `note`. Thao tác hoàn tác được và có dấu vết.

    Args:
        activity_id: ID việc cần đóng (coordinator đã giải từ chứng từ).
        note: Lời nhắn ghi kèm, vào chatter chứng từ. Bỏ trống cũng được.
    """
    try:
        # Lệnh Odoo ĐẦU TIÊN trên model đích — bọc RIÊNG lệnh này. Lỗi ở đúng
        # chỗ này chỉ có một nghĩa: vai hiện tại không đọc được mail.activity
        # (thiếu quyền) — biết được từ VỊ TRÍ lỗi xảy ra, không cần đọc nội
        # dung lỗi. KHÔNG lộ nguyên văn lỗi hay tên nhóm quyền Odoo ra ngoài.
        try:
            rows = odoo("mail.activity", "search_read",
                        [[["id", "=", activity_id], ["user_id", "=", get_uid()]]],
                        {"fields": ["id", "summary", "res_name"], "limit": 1})
        except Exception:  # noqa: BLE001 — chỉ bọc lệnh này, không đổi hành vi các lệnh Odoo khác
            return envelope(False,
                            "Không đọc được dữ liệu việc — tài khoản hiện tại có thể "
                            "không có quyền truy cập.")
        if not rows:
            # MỘT câu cho cả hai nguyên nhân (việc của người khác / đã đóng
            # rồi) — tách ra là để lộ việc của bộ phận khác có tồn tại không.
            return envelope(False, "Việc này không được giao cho bộ phận của "
                                   "bạn, hoặc đã đóng rồi.")
        act = rows[0]
        odoo("mail.activity", "action_feedback", [[activity_id]],
             {"feedback": note or "Đã hoàn tất."})
        what = act.get("summary") or f"việc #{activity_id}"
        where = act.get("res_name") or ""
        where_part = f" trên '{where}'" if where else ""
        return envelope(True, f"Đã đóng {what}{where_part}.",
                        ref=where or what, model="mail.activity",
                        res_id=activity_id, state="done")
    except Exception as e:  # noqa: BLE001 — never raise through the MCP tool
        return envelope(False, f"Lỗi khi đóng việc: {e}")


@mcp.tool()
def find_my_activities(res_model: str = "", res_id: int = 0,
                       limit: int = 20) -> str:
    """Các việc (hoạt động/activity) ĐANG MỞ được giao cho tài khoản hiện tại,
    hạn gần nhất trước. Bỏ trống res_model/res_id = mọi chứng từ.

    Tool này phục vụ coordinator đóng việc (nó cần danh sách ứng viên trước khi
    hỏi người dùng chọn). Đường tra cứu của NGƯỜI DÙNG là list_my_activities ở
    tầng backend, không phải tool này.

    Lọc theo get_uid() — tài khoản Odoo đã xác thực của vai — chứ không theo
    một chuỗi login suy ra từ tên vai.

    "Đang mở" = active=True; Odoo lọc như vậy theo mặc định nên domain không
    cần điều kiện gì thêm. KHÔNG truyền active_test=False: đo 2026-08-14 cho
    thấy việc đã đóng vẫn CÒN bản ghi (active=False, state='done'), nên bật
    active_test=False sẽ cho phép đóng lại một việc đã xong.

    Args:
        res_model: Lọc theo model chứng từ, vd "sale.order". Bỏ trống = mọi model.
        res_id: Lọc theo ID chứng từ. Bỏ trống/0 = mọi chứng từ.
        limit: Số dòng tối đa.
    """
    try:
        domain = [["user_id", "=", get_uid()]]
        if str(res_model or "").strip():
            domain.append(["res_model", "=", res_model])
        if res_id:
            domain.append(["res_id", "=", res_id])
        rows = odoo("mail.activity", "search_read", [domain],
                    {"fields": ["id", "summary", "res_model", "res_id",
                                "res_name", "date_deadline"],
                     "order": "date_deadline asc", "limit": limit})
        return json.dumps({"ok": True, "rows": rows}, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001 — never raise through the MCP tool
        return json.dumps({"ok": False, "rows": [],
                           "display": f"Lỗi khi tra việc được giao: {e}"},
                          ensure_ascii=False)
