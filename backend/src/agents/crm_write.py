# backend/src/agents/crm_write.py
"""Deterministic CRM coordinators (tier-1): create_lead / convert_lead /
log_activity. Slot-filling qua _msg (KHÔNG interrupt — lượt sau planner đọc
lại full history tự dựng args đầy đủ hơn, pattern inventory_write); resolve
qua erp_query.crm; disambiguation + confirm qua interrupt; rồi gọi MCP tool
phẳng. Không LLM. Xem docs/superpowers/specs/2026-07-18-crm-lead-activity-design.md."""
from datetime import date

from langgraph.types import interrupt as _interrupt

from .state import ERPAgentState
from .tool_result import parse_write_result
from .create_order import (resolve_entity_for_order, _by_id, _ttl_expiry, _msg,
                           _disambig_q, WRITE_DISABLED_MSG)
from . import write_gate
from .prompts import WRITE_CONFIRM_SUFFIX
from ..erp_query import crm


def _finish(tool_name: str, result) -> dict:
    """Đường trả về sau write thành công — cùng contract create_order.py:
    last_write feed write_continuation (chuỗi create_lead→convert_lead).
    crm.lead/mail.activity không thuộc ORDER_MODELS → derive_working_context
    trả None, không set working_context (chủ đích, nhất quán post_invoice)."""
    display, env = parse_write_result(result)
    upd = {**_msg(display), "pending_action": None,
           "last_write": {"tool": tool_name, **env} if env else None}
    return upd


# Live-run finding (2026-07-19): Odoo's crm.lead name_search is plain ilike
# substring match. Users commonly refer to a lead by "anh/chị + tên" even
# though the stored title may not carry that honorific (e.g. create_lead's
# LLM-extracted contact_name dropped "anh" while convert_lead/log_activity's
# ref kept it verbatim) — the query becomes a superset string that no
# longer substring-matches, so a lead that clearly exists resolves to "none".
# Deterministic strip + retry once — tất định, không đoán bằng LLM.
_HONORIFIC_PREFIXES = ("anh ", "chị ", "ông ", "bà ", "em ", "cô ", "chú ", "bác ")


def _strip_honorific(ref: str) -> str | None:
    low = ref.strip().lower()
    for p in _HONORIFIC_PREFIXES:
        if low.startswith(p):
            return ref.strip()[len(p):].strip()
    return None


def _resolve_lead(lead_ref: str):
    """→ ("ok", {"id","name"}) | ("msg", <dict return ngay>) — gói chung
    resolve + disambiguation cho convert_lead/log_activity."""
    kind, val = resolve_entity_for_order(crm.find_lead(lead_ref), lead_ref)
    if kind == "none":
        stripped = _strip_honorific(lead_ref)
        if stripped:
            kind, val = resolve_entity_for_order(crm.find_lead(stripped), stripped)
    if kind == "error":
        return "msg", _msg(val)
    if kind == "none":
        return "msg", _msg(f"Không tìm thấy lead/cơ hội '{lead_ref}'.")
    if kind == "ambiguous":
        chosen = _interrupt({"kind": "disambiguation",
                             "question": _disambig_q("lead/cơ hội", val),
                             "options": val, "expires_at": _ttl_expiry()})
        lead = _by_id(val, chosen)
        if lead is None:
            return "msg", _msg("Đã hủy.")
        return "ok", lead
    return "ok", val


# Model giải bằng tra `name =` chính xác: mã của chúng vốn là mã máy
# (S00119, WH/OUT/00138, P00068) nên tìm mờ không thêm giá trị mà chỉ thêm
# đường sai. crm.lead KHÔNG nằm đây — nó có _resolve_lead riêng với tìm mờ,
# bỏ kính ngữ và hỏi lại khi trùng, và mất ba thứ đó là gỡ tính năng đang chạy.
_EXACT_NAME_MODELS = ("sale.order", "purchase.order", "account.move",
                      "stock.picking", "mrp.production")


def _search_by_name(model, domain, fields, **kw):
    """Tách ra thành hàm riêng để test monkeypatch được mà không cần Odoo."""
    from ..erp_query.gateway import default_gateway
    return default_gateway().search_read(model, domain, fields, **kw)


def _resolve_doc(res_model: str, ref: str):
    """→ ("ok", {"id","name"}) | ("msg", <dict trả ngay>).

    Fail-closed: model chưa biết cách giải thì TỪ CHỐI, không đoán."""
    if res_model == "crm.lead":
        return _resolve_lead(ref)
    if res_model not in _EXACT_NAME_MODELS:
        ho_tro = ", ".join(("crm.lead",) + _EXACT_NAME_MODELS)
        return "msg", _msg(f"Chưa hỗ trợ gắn hoạt động vào '{res_model}'. "
                           f"Hiện hỗ trợ: {ho_tro}.")
    rows = _search_by_name(res_model, [["name", "=", ref]], ["id", "name"],
                           limit=2)
    if not rows:
        # Hoá đơn NHÁP có name=False (đo 2026-08-08) nên tra theo mã chỉ tìm
        # được hoá đơn ĐÃ phát hành — nói rõ để người dùng không tưởng gõ sai.
        them = (" Lưu ý: hoá đơn nháp chưa có số nên chưa tra được theo mã."
                if res_model == "account.move" else "")
        return "msg", _msg(f"Không tìm thấy '{ref}' trong {res_model}.{them}")
    if len(rows) > 1:
        return "msg", _msg(f"Có nhiều bản ghi tên '{ref}' trong {res_model}. "
                           f"Vui lòng nêu rõ hơn.")
    return "ok", rows[0]


def make_create_lead_node(tools):
    by_name = {t.name: t for t in tools}

    async def create_lead_node(state: ERPAgentState) -> dict:
        if not write_gate.write_actions_enabled():
            return _msg(WRITE_DISABLED_MSG)
        args = (state.get("pending_action") or {}).get("args") or {}
        contact = str(args.get("contact_name") or "").strip()
        company = str(args.get("partner_name") or "").strip()
        email = str(args.get("email") or "").strip()
        phone = str(args.get("phone") or "").strip()
        if not (contact or company or email or phone):
            return _msg("Vui lòng cho biết tên người liên hệ hoặc công ty "
                        "(kèm email/SĐT nếu có) để mình tạo lead.")
        title = str(args.get("name") or "").strip() or f"Lead: {contact or company}"

        dup_note = ""
        if email or phone:
            denv = crm.find_lead_duplicates(email or None, phone or None)
            rows = (denv.get("data") or {}).get("rows") or []
            if rows:
                names = "; ".join(f"'{r['name']}'" for r in rows)
                dup_note = f"\n  ⚠ Đã có lead trùng email/SĐT: {names}"

        # chain_note: user nói "tạo lead ... rồi chuyển thành cơ hội luôn" →
        # planner set chain_note — câu confirm PHẢI hiện toàn bộ chuỗi (cùng
        # Invariant-C-style với create_order/edit_order, spec auto-chain §3).
        note = (state.get("pending_action") or {}).get("chain_note") or ""
        draft = (f"Tạo lead mới:\n"
                 f"  Tiêu đề: {title}\n"
                 f"  Liên hệ: {contact or '—'} | Công ty: {company or '—'}\n"
                 f"  Email: {email or '—'} | SĐT: {phone or '—'}"
                 f"{dup_note}{note}\n" + WRITE_CONFIRM_SUFFIX)
        confirmed = _interrupt({"kind": "confirm", "question": draft,
                                "expires_at": _ttl_expiry()})
        if not confirmed:
            return _msg("Đã hủy tạo lead.")

        tool = by_name.get("create_lead")
        if tool is None:
            return _msg("Công cụ tạo lead không khả dụng.")
        try:
            result = await tool.ainvoke({
                "name": title, "contact_name": contact, "partner_name": company,
                "email": email, "phone": phone,
                "description": str(args.get("description") or "")})
        except Exception as e:  # noqa: BLE001 — never crash the graph
            return _msg(f"Lỗi khi tạo lead: {e}")
        return _finish("create_lead", result)

    return create_lead_node


def make_convert_lead_node(tools):
    by_name = {t.name: t for t in tools}

    async def convert_lead_node(state: ERPAgentState) -> dict:
        if not write_gate.write_actions_enabled():
            return _msg(WRITE_DISABLED_MSG)
        args = (state.get("pending_action") or {}).get("args") or {}
        lead_ref = str(args.get("lead_ref") or "").strip()
        assignee = str(args.get("assignee") or "").strip()
        if not lead_ref:
            return _msg("Vui lòng cho biết lead nào cần chuyển thành cơ hội.")

        kind, lead = _resolve_lead(lead_ref)
        if kind == "msg":
            return lead

        who = f", giao cho {assignee}" if assignee else ""
        confirmed = _interrupt({
            "kind": "confirm",
            "question": (f"Chuyển lead '{lead['name']}' thành cơ hội{who}.\n"
                         + WRITE_CONFIRM_SUFFIX),
            "expires_at": _ttl_expiry()})
        if not confirmed:
            return _msg("Đã hủy chuyển lead.")

        tool = by_name.get("convert_lead")
        if tool is None:
            return _msg("Công cụ chuyển lead không khả dụng.")
        try:
            result = await tool.ainvoke({"lead_id": lead["id"],
                                         "assignee_name": assignee})
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi chuyển lead: {e}")
        return _finish("convert_lead", result)

    return convert_lead_node


def make_log_activity_node(tools):
    by_name = {t.name: t for t in tools}

    async def log_activity_node(state: ERPAgentState) -> dict:
        if not write_gate.write_actions_enabled():
            return _msg(WRITE_DISABLED_MSG)
        args = (state.get("pending_action") or {}).get("args") or {}
        res_model = str(args.get("res_model") or "").strip()
        ref = str(args.get("ref") or "").strip()
        activity_type = str(args.get("activity_type") or "").strip()
        summary = str(args.get("summary") or "").strip()
        deadline = str(args.get("date_deadline") or "").strip()
        assignee = str(args.get("assignee") or "").strip()

        # Slot-fill GỘP: liệt kê MỌI slot còn thiếu trong một câu.
        missing = []
        if not res_model or not ref:
            missing.append("gắn vào chứng từ nào (loại và mã, vd đơn bán S00119)")
        if not activity_type:
            missing.append("loại hoạt động (vd To-Do, Call, Meeting)")
        if not summary:
            missing.append("nội dung ngắn gọn")
        if missing:
            return _msg("Vui lòng cho biết: " + "; ".join(missing) + ".")

        kind, doc = _resolve_doc(res_model, ref)
        if kind == "msg":
            return doc

        deadline = deadline or date.today().isoformat()
        nguoi = f" — giao {assignee}" if assignee else ""
        confirmed = _interrupt({
            "kind": "confirm",
            "question": (f"Lên lịch {activity_type} cho '{doc['name']}': "
                         f"{summary} — hạn {deadline}{nguoi}.\n"
                         + WRITE_CONFIRM_SUFFIX),
            "expires_at": _ttl_expiry()})
        if not confirmed:
            return _msg("Đã hủy lên lịch hoạt động.")

        tool = by_name.get("log_activity")
        if tool is None:
            return _msg("Công cụ lên lịch hoạt động không khả dụng.")
        try:
            result = await tool.ainvoke({"res_model": res_model,
                                         "res_id": doc["id"],
                                         "activity_type": activity_type,
                                         "summary": summary,
                                         "date_deadline": deadline,
                                         "assignee": assignee})
        except Exception as e:  # noqa: BLE001
            return _msg(f"Lỗi khi lên lịch hoạt động: {e}")
        return _finish("log_activity", result)

    return log_activity_node
