from src.agents import skill_gate


def test_unset_defaults_on(monkeypatch):
    # Default ON since 2026-07-16 (graduated from pilot flag after live
    # verification of both agentic skills + the intent-gate in
    # decide_route that stops trigger phrases hijacking read/RAG
    # questions).
    monkeypatch.delenv("ERP_SKILLS_ENABLED", raising=False)
    assert skill_gate.skills_enabled() is True


def test_explicit_zero_is_off(monkeypatch):
    # "0" is the ONLY recognized off-value — the emergency kill-switch.
    monkeypatch.setenv("ERP_SKILLS_ENABLED", "0")
    assert skill_gate.skills_enabled() is False


def test_explicit_one_is_on(monkeypatch):
    monkeypatch.setenv("ERP_SKILLS_ENABLED", "1")
    assert skill_gate.skills_enabled() is True


def test_garbage_value_is_on(monkeypatch):
    # Routing flag, not a security gate (write_gate is): default-on
    # semantics means any value other than the documented "0" enables.
    monkeypatch.setenv("ERP_SKILLS_ENABLED", "true")
    assert skill_gate.skills_enabled() is True


def test_fold_lowercases_and_strips_diacritics():
    from src.agents.skill_gate import _fold
    assert _fold("BÁO GIÁ Chiết Khấu") == "bao gia chiet khau"
    assert _fold("") == ""
    assert _fold(None) == ""


def test_fold_strips_dd_stroke_letter():
    # Regression (found 2026-07-16 via feat/agentic-delivery's wiring
    # tests): đ/Đ have no NFD decomposition (unlike á/ơ/ậ...), so plain
    # combining-mark stripping used to leave them untouched — a trigger
    # phrase containing "đơn" silently failed to match naturally-typed
    # diacritic input ("giao hàng cho đơn bán" folded to "...đon ban...",
    # not "...don ban...").
    from src.agents.skill_gate import _fold
    assert _fold("đơn hàng") == "don hang"
    assert _fold("Đơn Hàng") == "don hang"
    assert _fold("giao hàng cho đơn bán") == "giao hang cho don ban"


# ── decide_route ánh xạ cặp (sop, depth) ─────────────────────────────────────


def _state_sop(text: str, sop: str, depth: str):
    from langchain_core.messages import HumanMessage
    return {"messages": [HumanMessage(content=text)],
            "intent": "erp_write", "sop": sop, "depth": depth}


def test_full_sop_vao_node_sop():
    from src.agents.routing import decide_route
    got = decide_route(_state_sop(
        "làm quy trình nhập kho cho đơn mua P00021", "nhap-kho", "full_sop"))
    assert got == "nhap-kho"


def test_one_step_ve_write_planner_khong_vao_sop():
    """Quyết định của chủ dự án: one_step đi ĐÚNG đường erp_write hôm nay, nên
    hành vi cuối không đổi và ba ca eval đang kỳ vọng erp_write giữ nguyên kỳ
    vọng dù router nay điền `sop` cho chúng."""
    from src.agents.routing import decide_route
    got = decide_route(_state_sop(
        "giao hàng cho đơn S00040 luôn nhé", "giao-hang", "one_step"))
    assert got == "erp_write"


def test_depth_none_giu_nguyen_hanh_vi_cu():
    from src.agents.routing import decide_route
    got = decide_route(_state_sop(
        "nhập kho cho đơn P00021", "nhap-kho", "none"))
    assert got == "nhap-kho"


def test_unsure_tam_thoi_chay_full_sop_cho_task_5():
    """TẠM THỜI. Task 5 đổi nhánh này sang node clarify_depth. Ghim lại để
    trạng thái tạm không nằm im: khi Task 5 xong, test này PHẢI đỏ và được
    thay bằng test khẳng định route đi 'clarify_depth'."""
    from src.agents.routing import decide_route
    got = decide_route(_state_sop(
        "kho báo hàng P00021 đã tới, cần làm gì tiếp", "nhap-kho", "unsure"))
    assert got == "nhap-kho"


def test_phu_quyet_cau_hoi_van_can_du_depth_la_one_step():
    """Lớp phủ quyết tất định GIỮ NGUYÊN. Spike cho thấy model mới tự xử đúng
    15/15 ở nhóm an toàn — nhưng đó không phải lý do tháo một lớp phòng thủ
    tốn 10 dòng đã chứng minh giá trị."""
    from src.agents.routing import decide_route
    got = decide_route({"messages": [__import__(
        "langchain_core.messages", fromlist=["HumanMessage"]).HumanMessage(
            content="quy trình nhập kho là gì?")],
        "intent": "rag", "sop": "nhap-kho", "depth": "one_step"})
    assert got == "rag"
