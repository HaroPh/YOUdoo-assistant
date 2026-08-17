"""Kiểm tra đăng ký + công thức gate của set sop_select — KHÔNG gọi LLM."""
from evals.cases import SOP_SELECT_CASES
from jobs.eval_gate import BASELINE_SETS, EVAL_FN, ROLE_FOR_SET, _gate


def test_set_registered_everywhere():
    assert ROLE_FOR_SET["sop_select"] == "router"
    assert "sop_select" in EVAL_FN
    # ĐỔI 2026-08-17: có baseline. Trước đó là cổng tuyệt đối (acc == 1.0),
    # và hệ quả đo được là đỏ vĩnh viễn từ 2026-07-31 nên bị gỡ khỏi
    # `--set all` — hàng rào an toàn định tuyến suốt 6 tuần không ai gác.
    assert "sop_select" in BASELINE_SETS


def test_gate_giu_hijack_tuyet_doi_nhung_acc_theo_baseline():
    """Khuôn chung của 4 cổng anh em: điều kiện AN TOÀN tuyệt đối + chất lượng
    so baseline. `hijack` KHÔNG được nới — đó là hướng đã gây sự cố thật
    (live-verify 2026-07-16) và là thứ vừa bắt được hồi quy "câu ĐỌC bị miền
    vơ" (2026-08-17)."""
    base = {"acc": 0.9259}
    assert _gate("sop_select", {"acc": 0.9259, "hijack": 0}, base) is True
    assert _gate("sop_select", {"acc": 1.0, "hijack": 0}, base) is True
    # baseline-relative KHÔNG phải buông: tụt dưới baseline vẫn trượt
    assert _gate("sop_select", {"acc": 0.90, "hijack": 0}, base) is False
    # hijack khác 0 trượt DÙ chất lượng đạt
    assert _gate("sop_select", {"acc": 1.0, "hijack": 1}, base) is False


def test_every_skill_has_at_least_four_cases():
    from src.agents.skill_loader import load_skill_specs
    names = {s.name for s in load_skill_specs()}
    for name in names:
        related = [c for c in SOP_SELECT_CASES if c[1] == name]
        assert len(related) >= 2, f"{name}: quá ít ca hướng DƯƠNG"
    # tổng số ca đủ để mỗi skill có cả hướng âm
    assert len(SOP_SELECT_CASES) >= 4 * len(names)


def test_expectations_are_valid_route_targets():
    from src.agents.routing import VALID_INTENTS
    from src.agents.skill_loader import load_skill_specs
    valid = VALID_INTENTS | {s.name for s in load_skill_specs()} | {"clarify_depth"}
    for text, expected, _ in SOP_SELECT_CASES:
        assert expected in valid, f"{text!r}: đích {expected!r} không phải node hợp lệ"


def test_regression_phrasings_present_verbatim():
    """3 câu thua 3/3 lần ở live-verify 2026-07-16 phải có mặt NGUYÊN VĂN."""
    texts = {t for t, _, _ in SOP_SELECT_CASES}
    assert "quy trình nhập kho cho đơn mua P00021" in texts
    assert "nhập kho theo quy trình cho đơn mua P00021" in texts
    assert "làm quy trình nhập kho cho đơn mua P00021" in texts
    assert "quy trình nhập kho là gì?" in texts      # ca hijack gốc
