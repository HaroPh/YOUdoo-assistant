"""Kiểm tra đăng ký + công thức gate của set sop_select — KHÔNG gọi LLM."""
from evals.cases import SOP_SELECT_CASES
from jobs.eval_gate import BASELINE_SETS, EVAL_FN, ROLE_FOR_SET, _gate


def test_set_registered_everywhere():
    assert ROLE_FOR_SET["sop_select"] == "router"
    assert "sop_select" in EVAL_FN
    assert "sop_select" not in BASELINE_SETS  # gate tuyệt đối, không baseline


def test_gate_requires_perfect_score_and_zero_hijack():
    assert _gate("sop_select", {"acc": 1.0, "hijack": 0}, None) is True
    assert _gate("sop_select", {"acc": 0.99, "hijack": 0}, None) is False
    assert _gate("sop_select", {"acc": 1.0, "hijack": 1}, None) is False


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
