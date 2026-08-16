"""Bản tin "hôm nay tôi cần xử lý gì?" — quét mọi hàng đợi việc tồn đọng.

Vì sao tổng hợp ở ĐÂY chứ không để LLM tự gọi 5 tool: đo 2026-08-15 cho thấy
LLM LÀM ĐƯỢC khi được bảo tường minh, nhưng số hàng đợi nó quét mỗi lượt là
XÁC SUẤT. Gom vào một hàm biến câu hỏi không kiểm được ("có quét đủ 5 không?")
thành câu hỏi cùng loại với mọi tool khác ("có chọn đúng một tool không?"), và
làm bản tin test được mà không cần gọi LLM.
"""
import logging

from . import accounting, crm, inventory, purchase
from .envelope import ok

logger = logging.getLogger(__name__)

# Cửa sau CHỈ dùng cho test: test đặt hàm/kết quả giả vào đây thay vì
# monkeypatch từng module. Rỗng trong chạy thật.
_FAKE_QUEUES: dict = {}

# ── Tầng 1: bản thân định nghĩa đã là việc tồn đọng ───────────────────────────
# (tên, nhãn tiếng Việt, bộ phận, hàm gọi). Bộ phận None = việc giao đích danh,
# luôn đứng đầu, không xếp theo bộ phận.
TIER_ONE = [
    ("list_my_activities",   "việc được giao đích danh", None,
     lambda role: crm.list_my_activities(f"ai-{role}" if role else "", limit=20)),
    ("list_late_deliveries", "phiếu giao/nhận trễ hạn",  "Kho",
     lambda role: inventory.list_late_deliveries()),
    ("get_overdue_invoices", "hóa đơn quá hạn",          "Kế toán",
     lambda role: accounting.get_overdue_invoices(limit=20)),
    ("list_reorder_needed",  "mặt hàng cần đặt bổ sung", "Mua hàng",
     lambda role: inventory.list_reorder_needed()),
    ("list_po_mismatches",   "đơn mua lệch hóa đơn",     "Mua hàng",
     lambda role: purchase.list_po_mismatches()),
]

# ── Tầng 2: chỉ thành việc khi lọc trạng thái ────────────────────────────────
# KHÔNG quét mặc định; là nguyên liệu tất định cho câu "còn gì nữa không".
TIER_TWO = [
    "list_sale_orders(state=draft)",
    "list_purchase_orders(state=draft)",
    "list_manufacturing_orders(state=confirmed)",
    "list_crm_leads",
    "find_open_invoices",
]


def dept_for_role(role: str | None) -> str | None:
    """Bộ phận của một vai — SUY RA từ tool nó sở hữu, không khai bảng thứ hai.

    Lấy đa số của DEPT_OF trên cfg.own, từ đúng profile ĐANG CHẠY
    (roles.load_profile()) — KHÔNG duyệt mọi profile. Đo 2026-08-15: kho
    {Kho: 9}, kế toán {Kế toán: 4, Kho: 2}. Hai phiếu "Kho" của kế toán là
    log_activity/close_activity, mà roles.py tự ghi rằng giá trị đó TUỲ TIỆN
    — nên kết quả được ghim bằng test, không thả trôi.

    Vai unrestricted (admin) không có bộ phận ⇒ None ⇒ giữ thứ tự khai. Biến
    môi trường YOUDOO_POLICY_PROFILE gõ sai ⇒ load_profile() KeyError ⇒ cũng
    trả None thay vì làm sập cả bản tin.
    """
    if not role:
        return None
    from collections import Counter

    from ..agents import roles as roles_mod

    try:
        profile = roles_mod.load_profile()
    except KeyError:
        return None
    cfg = profile.get(role)
    if cfg is None or getattr(cfg, "unrestricted", False):
        return None
    counts = Counter(roles_mod.DEPT_OF[t] for t in cfg.own
                     if t in roles_mod.DEPT_OF)
    return counts.most_common(1)[0][0] if counts else None


def _count(data) -> int:
    """Số việc thật của một hàng đợi.

    ƯU TIÊN data["count"]: đo 2026-08-15, list_late_deliveries trả rows=15
    nhưng count=29 vì nó CHẶN rows. Đếm theo len(rows) là báo sai một nửa.
    Chỉ lùi về len(rows) khi không có khoá count (list_my_activities).
    """
    if not isinstance(data, dict):
        return 0
    if "count" in data:
        return int(data["count"] or 0)
    return len(data.get("rows") or [])


def _call_queue(name, fn, role):
    """Gọi một hàng đợi. Trả (count, None) khi được, (None, lý do) khi hỏng."""
    fake = _FAKE_QUEUES.get(name)
    try:
        res = fake(role) if callable(fake) else (fake if fake is not None else fn(role))
    except Exception as e:                                  # noqa: BLE001
        logger.exception("hàng đợi %s hỏng: %s: %s", name, type(e).__name__, e)
        return None, "lỗi hệ thống"
    # Hỏng KHÔNG chỉ đến dưới dạng exception: các hàm hàng đợi trả envelope,
    # nên status="error" cũng là hỏng. Nếu bỏ qua vế này, hàng đợi hỏng sẽ
    # được đếm thành 0 và trông y hệt hàng đợi rỗng — đúng lỗ hổng tính năng
    # này sinh ra để bịt.
    if not isinstance(res, dict) or res.get("status") != "success":
        logger.warning("hàng đợi %s trả envelope lỗi", name)
        return None, "không lấy được dữ liệu"
    return _count(res.get("data")), None


def list_pending_work(role: str | None = None) -> dict:
    """Quét tầng 1, trả bản tin ngắn có số.

    `role` do tool wrapper đóng gói truyền xuống, KHÔNG do LLM điền — mọi thứ
    LLM điền được đều là thứ tự khai được (cùng lý do như _role_from_headers).
    """
    checked, failed = [], []
    for name, label, dept, fn in TIER_ONE:
        count, reason = _call_queue(name, fn, role)
        if reason is not None:
            failed.append({"queue": name, "label": label, "reason": reason})
        else:
            checked.append({"queue": name, "label": label,
                            "dept": dept, "count": count})
    dept = dept_for_role(role)
    if dept:
        # Việc đích danh (dept None) luôn đứng đầu tuyệt đối; sau đó hàng đợi
        # thuộc bộ phận của vai; phần còn lại giữ nguyên thứ tự khai.
        checked.sort(key=lambda c: (c["dept"] is not None,
                                    c["dept"] != dept))
    data = {"checked": checked, "not_checked": list(TIER_TWO), "failed": failed}
    return ok(data, _render_display(checked, failed))


def _render_display(checked, failed) -> str:
    """Câu hiển thị.

    RÀNG BUỘC CỨNG (spec §4): không bao giờ nói "không còn việc gì nữa" — chỉ
    nói ĐÃ KIỂM NHỮNG GÌ. Khác biệt giữa "không có việc" và "không có việc TÔI
    BIẾT CÁCH TÌM" chính là con bug ADR-012 tồn tại để chỉ ra.
    """
    with_work = [c for c in checked if c["count"] > 0]
    lines = [f"- {c['label']}: {c['count']}" for c in with_work]
    if with_work:
        header = f"Có việc cần xử lý ở {len(with_work)} nhóm:"
    elif checked:
        header = f"Đã kiểm {len(checked)} hàng đợi, tất cả đang trống:"
        lines = [f"- {c['label']}: 0" for c in checked]
    else:
        header = "Không kiểm được hàng đợi nào."
        lines = []
    footer = []
    if failed:
        footer.append("Không kiểm được: "
                      + ", ".join(f"{f['label']}" for f in failed) + ".")
    if checked:
        footer.append("Đã kiểm: " + ", ".join(c["label"] for c in checked) + ".")
    return "\n".join([header, *lines, *footer])
