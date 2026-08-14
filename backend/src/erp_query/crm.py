"""CRM bounded context — leads/opportunities. crm.lead KHÔNG nằm trong
MODEL_DENYLIST của gateway (đã verify); res.users NẰM TRONG denylist nên
resolve assignee ở MCP-side (server.py), không ở đây."""
from .envelope import ok, err
from .gateway import default_gateway
from .resolve import resolve_entity


def find_lead(name, *, gw=None):
    return resolve_entity("crm.lead", name, gw=gw)


def find_lead_duplicates(email=None, phone=None, *, gw=None):
    """Dup-check tất định cho create_lead (SOP1: 'tránh trùng lặp'). Chỉ check
    khi có email/phone; không có gì → rows rỗng, KHÔNG chạm gateway."""
    conds = []
    if str(email or "").strip():
        conds.append(["email_from", "ilike", email])
    if str(phone or "").strip():
        conds.append(["phone", "ilike", phone])
    if not conds:
        return ok({"rows": []}, "Không có email/SĐT để kiểm tra trùng.")
    domain = (["|"] + conds) if len(conds) == 2 else conds
    gw = gw or default_gateway()
    try:
        rows = gw.search_read("crm.lead", domain, ["name", "type"], limit=5)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi kiểm tra lead trùng: {e}")
    return ok({"rows": rows},
              f"{len(rows)} lead trùng email/SĐT." if rows else "Không trùng.")


def list_crm_leads(kind=None, stage=None, limit=50, *, gw=None):
    gw = gw or default_gateway()
    domain = []
    if kind:
        domain.append(["type", "=", kind])
    if stage:
        domain.append(["stage_id.name", "ilike", stage])
    try:
        rows = gw.search_read("crm.lead", domain,
                              ["name", "type", "contact_name", "partner_name",
                               "stage_id", "user_id", "expected_revenue"],
                              order="id desc", limit=limit)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra cứu lead/cơ hội: {e}")
    if not rows:
        return ok({"rows": [], "count": 0}, "Chưa có lead/cơ hội nào phù hợp.")
    lines = [f"{r['name']} | {'lead' if r['type'] == 'lead' else 'cơ hội'} "
             f"| {r['contact_name'] or r['partner_name'] or '—'} "
             f"| {(r['stage_id'] or [0, '—'])[1]} "
             f"| {(r['user_id'] or [0, '—'])[1]}" for r in rows]
    return ok({"rows": rows, "count": len(rows)},
              f"{len(rows)} lead/cơ hội:\n" + "\n".join(lines))


ACTIVITY_FIELDS = ["summary", "user_id", "res_model", "res_id", "res_name",
                   "date_deadline", "activity_type_id"]


def list_my_activities(login, limit=20, *, gw=None):
    """Activity đang mở giao cho `login`, hạn gần nhất trước.

    LỌC TƯỜNG MINH theo login truyền vào, KHÔNG theo "người dùng hiện tại":
    đường đọc chạy bằng ai-readonly còn đường ghi chạy bằng tài khoản của vai,
    nên "người dùng hiện tại" ở đây luôn là ai-readonly — sai người.

    Đường chấm `user_id.login` đi qua được dù res.users nằm trong
    MODEL_DENYLIST: denylist chỉ chặn model ở cấp cao nhất (gateway._check_model).

    mail.activity bản chất là việc CHƯA xong — Odoo unlink bản ghi khi đánh dấu
    hoàn tất — nên không cần điều kiện "đang mở" nào thêm."""
    login = str(login or "").strip()
    if not login:
        return ok({"rows": []}, "Không xác định được tài khoản để tra việc.")
    gw = gw or default_gateway()
    try:
        rows = gw.search_read("mail.activity", [["user_id.login", "=", login]],
                              ACTIVITY_FIELDS, order="date_deadline asc",
                              limit=limit)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra việc được giao: {e}")
    if not rows:
        return ok({"rows": []}, "Hiện không có việc nào được giao cho bạn.")
    lines = [f"- {r.get('res_name') or r.get('res_model')}: "
            f"{r.get('summary') or '(không có mô tả)'} "
            f"(hạn {r.get('date_deadline') or 'chưa đặt'})" for r in rows]
    return ok({"rows": rows},
              f"{len(rows)} việc đang được giao cho bạn:\n" + "\n".join(lines))
