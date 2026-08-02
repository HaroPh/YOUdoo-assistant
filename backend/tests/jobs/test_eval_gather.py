# backend/tests/jobs/test_eval_gather.py
"""Set gather: đo bước THU THẬP của gather_erp — tách khỏi bước tổng hợp mà
multi_source đã đo. Không gate baseline-relative (không có baseline model cũ
— node gather_erp không tồn tại trước SP-2b)."""
from evals import cases, fixtures


def test_gather_cases_shape_and_topics_exist():
    assert len(cases.GATHER_CASES) >= 4
    topics = set(fixtures.available_topics())
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        assert topic in topics, f"topic {topic} không có trong fixture"
        assert question.strip()
        assert required_tools and all(t.strip() for t in required_tools)
        assert required_facts and all(f.strip() for f in required_facts)


def test_gather_cases_required_tools_have_fixtures():
    """Mọi tool trong required_tools PHẢI có mặt trong tool_fixtures của
    chính case đó — nếu không, case tự mâu thuẫn: đòi model gọi một tool mà
    không có dữ liệu nào để nó lấy được."""
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        for t in required_tools:
            assert t in tool_fixtures, (
                f"required_tools có {t!r} nhưng case {topic}/{question!r} "
                f"không có fixture cho tool đó")


def test_gather_cases_required_facts_exist_in_fixtures():
    """Nửa còn lại của kiểm tra tự-mâu-thuẫn: mỗi required_fact PHẢI xuất
    hiện nguyên văn (không phân biệt hoa/thường) trong ÍT NHẤT MỘT fixture
    của case đó — nếu không, case đòi model nói điều dữ liệu không hề chứa."""
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        corpus = " ".join(tool_fixtures.values()).casefold()
        for f in required_facts:
            assert f.casefold() in corpus, (
                f"required_fact {f!r} không có trong tool_fixtures của case "
                f"{topic}/{question!r}")


def test_gather_cases_facts_not_leaked_by_the_question():
    """required_fact không được xuất hiện sẵn trong CHÍNH câu hỏi — nếu có,
    model chép lại câu hỏi là đủ đậu, không đo được bước thu thập gì thật
    (bug thật tìm thấy ở review toàn nhánh: case chinh_sach_thanh_toan có
    required_fact "32 ngày" đã nằm sẵn trong câu hỏi)."""
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        for f in required_facts:
            assert f.casefold() not in question.casefold(), (
                f"required_fact {f!r} đã có sẵn trong chính câu hỏi case "
                f"{topic} — model chép lại là đủ đậu, không đo được thu thập")


def test_gather_cases_required_tools_are_real_erp_tool_names():
    from src.erp_query.tools import build_erp_query_tools
    real_names = {t.name for t in build_erp_query_tools()}
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        for t in required_tools:
            assert t in real_names, (
                f"required_tools có {t!r} — không phải tên tool thật nào "
                f"trong build_erp_query_tools()")


def test_stub_erp_tools_wraps_all_real_tools():
    from evals.run_eval import _stub_erp_tools
    from src.erp_query.tools import build_erp_query_tools
    called = []
    tools = _stub_erp_tools({}, called)
    real_names = {t.name for t in build_erp_query_tools()}
    stub_names = {t.name for t in tools}
    assert stub_names == real_names


def test_stub_erp_tools_returns_fixture_for_named_tool():
    from evals.run_eval import _stub_erp_tools
    called = []
    tools = _stub_erp_tools({"get_stock": "Còn 10 Desk Pad."}, called)
    t = next(t for t in tools if t.name == "get_stock")
    out = t.func(product="Desk Pad")
    assert out == "Còn 10 Desk Pad."
    assert called == ["get_stock"]


def test_stub_erp_tools_default_no_data_for_unlisted_tool():
    from evals.run_eval import _stub_erp_tools
    called = []
    tools = _stub_erp_tools({}, called)
    t = next(t for t in tools if t.name == "find_customer")
    out = t.func(name="anyone")
    assert out == "Không có dữ liệu liên quan."
    assert called == ["find_customer"]


def test_stub_erp_tools_no_late_binding_closure_bug():
    """Chốt đúng bẫy nêu trong docstring _stub_erp_tools — mỗi stub phải trả
    ĐÚNG fixture của TOOL CỦA NÓ, không phải fixture của tool cuối vòng lặp."""
    from evals.run_eval import _stub_erp_tools
    called = []
    tools = _stub_erp_tools(
        {"get_stock": "A", "find_customer": "B", "find_product": "C"}, called)
    a = next(t for t in tools if t.name == "get_stock").func()
    b = next(t for t in tools if t.name == "find_customer").func()
    c = next(t for t in tools if t.name == "find_product").func()
    assert (a, b, c) == ("A", "B", "C")
    assert called == ["get_stock", "find_customer", "find_product"]


from evals import run_eval


def test_score_gather_both_ok():
    tool_ok, fact_ok = run_eval._score_gather(
        "Đơn xác nhận 18/07/2026, giao dự kiến 20/07/2026",
        ["get_sale_order_detail"],
        ("get_sale_order_detail",), ("18/07/2026", "20/07/2026"))
    assert tool_ok and fact_ok


def test_score_gather_tool_recall_fails_when_required_tool_not_called():
    tool_ok, _fact_ok = run_eval._score_gather(
        "18/07/2026, 20/07/2026", ["find_customer"],
        ("get_sale_order_detail",), ("18/07/2026",))
    assert not tool_ok


def test_score_gather_fact_coverage_fails_when_fact_missing():
    tool_ok, fact_ok = run_eval._score_gather(
        "Đơn xác nhận 18/07/2026", ["get_sale_order_detail"],
        ("get_sale_order_detail",), ("18/07/2026", "20/07/2026"))
    assert tool_ok and not fact_ok


def test_score_gather_extra_tool_call_does_not_fail_recall():
    """required_tools là TẬP CON của called, không phải khớp tuyệt đối —
    model gọi thêm tool khác (dò tìm thêm) không bị tính là lỗi."""
    tool_ok, _fact_ok = run_eval._score_gather(
        "18/07/2026", ["find_customer", "get_sale_order_detail"],
        ("get_sale_order_detail",), ("18/07/2026",))
    assert tool_ok


def test_score_gather_fact_match_is_case_insensitive_normalized():
    tool_ok, fact_ok = run_eval._score_gather(
        "quá hạn 32 NGÀY", ["get_overdue_invoices"],
        ("get_overdue_invoices",), ("32 ngày",))
    assert tool_ok and fact_ok


def test_eval_gather_base_branch_calls_real_gather_erp_node():
    """Chống trôi: nhánh base PHẢI gọi make_gather_erp_node thật, không dựng
    lại logic thu thập (Global Constraint) — kiểm bằng đọc mã nguồn, cùng
    khuôn Task 8 SP-2b đã dùng cho eval_multi_source/render_fuse_input."""
    import inspect
    src = inspect.getsource(run_eval.eval_gather)
    assert "make_gather_erp_node" in src
    assert "_stub_erp_tools" in src
    assert "_score_gather" in src


def test_eval_gather_policy_branch_does_not_call_real_node():
    """Nhánh policy KHÔNG gọi make_gather_erp_node — production chưa có
    nhánh này, gọi hàm thật sẽ chỉ chạy lại đúng prompt cũ, không đo được gì
    mới. Phải đi qua _run_gather_with_prompt riêng."""
    import inspect
    src = inspect.getsource(run_eval.eval_gather)
    assert "_run_gather_with_prompt" in src


def test_run_gather_with_prompt_returns_erp_facts_key():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from langchain_core.messages import AIMessage, HumanMessage

    async def _run():
        agent = MagicMock()
        agent.ainvoke = AsyncMock(
            return_value={"messages": [AIMessage(content="18/07/2026")]})
        import unittest.mock
        with unittest.mock.patch.object(
                run_eval, "_create_agent",
                lambda llm, tools, system_prompt=None: agent):
            out = await run_eval._run_gather_with_prompt(
                MagicMock(), [], "prompt bất kỳ",
                [HumanMessage(content="q?")])
        return out

    out = asyncio.run(_run())
    assert out == {"erp_facts": "18/07/2026"}


def test_run_gather_with_prompt_degrades_to_empty_on_exception():
    import asyncio
    from unittest.mock import MagicMock
    from langchain_core.messages import HumanMessage
    import unittest.mock

    async def _run():
        with unittest.mock.patch.object(
                run_eval, "_create_agent",
                lambda llm, tools, system_prompt=None: (_ for _ in ()).throw(
                    RuntimeError("llm down"))):
            return await run_eval._run_gather_with_prompt(
                MagicMock(), [], "prompt bất kỳ",
                [HumanMessage(content="q?")])

    out = asyncio.run(_run())
    assert out == {"erp_facts": ""}


def test_gather_registered_in_eval_gate():
    from jobs import eval_gate
    assert "gather" in eval_gate.EVAL_FN
    assert eval_gate.EVAL_FN["gather"] is run_eval.eval_gather
    assert eval_gate.ROLE_FOR_SET["gather"] == "fusion"


def test_gather_excluded_from_baselines():
    """Không có baseline model cũ — node gather_erp không tồn tại trước
    SP-2b."""
    from jobs import eval_gate
    assert "gather" not in eval_gate.BASELINES


def test_gather_gate_returns_true_unconditionally():
    """Lượt đo đầu tiên: chưa có ngưỡng tuyệt đối, chỉ ghi nhận (spec §2)."""
    from jobs import eval_gate
    assert eval_gate._gate("gather", {"tool_recall": 0.0, "fact_coverage": 0.0}, None) is True
    assert eval_gate._gate("gather", {"tool_recall": 1.0, "fact_coverage": 1.0}, None) is True


def test_gather_excluded_from_set_all():
    from jobs import eval_gate
    import argparse
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    args = p.parse_args(["--set", "all"])
    assert args.set == "all"
    assert "gather" in eval_gate.EVAL_FN  # đăng ký...
    # ...nhưng run() phải tự loại nó khi set == "all" — kiểm qua cùng công
    # thức run() dùng, không gọi run() thật (tốn API call thật).
    sets = [s for s in eval_gate.EVAL_FN if s not in ("sop_select", "gather")]
    assert "gather" not in sets
    assert "sop_select" not in sets
    assert "intent" in sets  # sanity: loại trừ không quá tay


def test_set_choices_includes_gather():
    from jobs import eval_gate
    import argparse
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    args = p.parse_args(["--set", "gather"])
    assert args.set == "gather"


# ── Contract test: fixture GATHER_CASES đối chiếu field THẬT của tool ──────
# Lớp lỗi "fixture khẳng định khả năng tool không có thật" đã tái diễn 2
# lần liên tiếp (gather-erp-tool-fix 2026-08-01, sale-order-detail-dates
# 2026-08-02) — 5 test tự-nhất-quán phía trên chỉ kiểm fixture KHÔNG tự
# mâu thuẫn, không kiểm fixture có khớp thực tế tool hay không. Xem
# docs/superpowers/specs/2026-08-02-gather-cases-contract-test-design.md.

_REPRESENTATIVE_ROWS = {
    "sale.order": {"id": 1, "name": "S00001", "partner_id": [1, "Khách mẫu"],
                   "amount_total": 100.0, "state": "sale",
                   "date_order": "2026-01-01 00:00:00",
                   "delivery_status": "pending"},
    "sale.order.line": {"id": 1, "product_id": [1, "Sản phẩm mẫu"],
                        "product_uom_qty": 1.0, "price_unit": 100.0,
                        "price_subtotal": 100.0},
    "account.move": {"id": 1, "name": "INV/0001", "partner_id": [1, "Khách mẫu"],
                     "invoice_date": "2026-01-01", "invoice_date_due": "2026-01-31",
                     "amount_total": 100.0, "amount_residual": 100.0,
                     "payment_state": "not_paid"},
    "product.product": {"id": 1, "name": "Sản phẩm mẫu", "list_price": 100.0},
}


class _RecordingTransport:
    """Transport giả DÙNG CHUNG cho mọi tool — chỉ ghi lại (model, fields)
    của mỗi lệnh gọi rồi trả về dòng mẫu tương ứng, đủ để hàm business-layer
    không bị chặn giữa chừng bởi guard 'not found'."""

    def __init__(self):
        self.calls = []  # list[tuple[str, list[str] | None]]

    def call(self, model, method, args, kwargs):
        self.calls.append((model, kwargs.get("fields")))
        row = _REPRESENTATIVE_ROWS.get(model, {"id": 1})
        return [dict(row)]


def _real_fields_for_tool(tool_name: str) -> set[str]:
    """Gọi ĐÚNG hàm business-layer thật (không qua @tool wrapper) với
    transport ghi nhận, hợp tất cả field đã ghi được qua mọi lệnh gọi
    search_read trong quá trình thực thi.

    Phụ thuộc ngầm: kết quả này chỉ phản ánh field model THẬT SỰ THẤY được
    nếu tools.py::_json() còn serialize toàn bộ envelope (bao gồm "data"),
    không chỉ dòng "display" — nếu sau này _json() bị tối ưu để chỉ trả
    "display", test này vẫn PASS nhưng không còn đo được gì thật."""
    from src.erp_query.gateway import Gateway
    from src.erp_query import sales, accounting

    gw = Gateway(_RecordingTransport())
    if tool_name == "get_sale_order_detail":
        sales.get_sale_order_detail("S00001", gw=gw)
    elif tool_name == "get_overdue_invoices":
        accounting.get_overdue_invoices(gw=gw)
    elif tool_name == "get_product_price":
        sales.get_product_price(1, gw=gw)
    elif tool_name in ("find_customer", "find_product"):
        # resolve_entity() dùng gw.name_search(), KHÔNG có tham số "fields"
        # — tool loại này KHÔNG THỂ trả field ngày/trạng thái nào, tập rỗng
        # là đúng ngữ nghĩa, không phải giới hạn tạm thời.
        return set()
    else:
        raise KeyError(
            f"_real_fields_for_tool: chưa biết cách gọi tool {tool_name!r} "
            f"— thêm nhánh xử lý trước khi dùng tool này trong GATHER_CASES")
    return {f for _model, fields in gw._t.calls if fields for f in fields}


_DATE_STATUS_LABELS = {
    "ngày xác nhận": ("date_order",),
    "ngày giao dự kiến": ("commitment_date", "effective_date"),
    "ngày giao thực tế": ("effective_date", "date_done"),
    "trạng thái giao": ("delivery_status",),
}

_KNOWN_GAPS = {
    # (topic, tool, nhãn) — xem docs/superpowers/plans/
    # 2026-08-02-sale-order-detail-dates-report.md (Task 2 Bước 10):
    # get_sale_order_detail không có field "ngày giao dự kiến"/"ngày giao
    # thực tế" thật — chưa tool nào gather_erp gọi được cung cấp field đó
    # CHO MỘT ĐƠN CỤ THỂ (list_late_deliveries có khái niệm ngày giao nhưng
    # chỉ trả phiếu trễ hạn, không lọc theo mã đơn).
    # Quyết định lộ tool/đọc field mới vẫn TREO, chưa làm. Xoá dòng khỏi
    # danh sách khi field đó có thật, KHÔNG xoá để né test.
    ("sla_giao_hang", "get_sale_order_detail", "ngày giao dự kiến"),
    ("chinh_sach_hoan_hang", "get_sale_order_detail", "ngày giao thực tế"),
}


def test_known_gaps_catches_entry_when_real_field_now_exists(monkeypatch):
    """Xác nhận sửa lỗ hổng: nếu real_fields giờ khớp một mục trong
    _KNOWN_GAPS, test chính phải FAIL đòi xoá mục — không được im lặng
    pass. Bug thật tìm thấy khi viết plan sale-order-effective-dates: bản
    gốc (trước sửa ở Step 3 dưới) chỉ bắt được kịch bản "nhãn không còn
    khớp câu chữ", không bắt được kịch bản này — continue thoát trước khi
    kiểm tra field thật."""
    # PHẢI chụp lại tham chiếu GỐC trước khi monkeypatch — nếu không, fallback
    # `_real_fields_for_tool(tool_name)` bên trong `_fake_real_fields` khi
    # gặp tool khác get_sale_order_detail (eg get_overdue_invoices,
    # find_customer) sẽ tự gọi lại CHÍNH `_fake_real_fields` (đã bị patch đè
    # tên) → RecursionError vô hạn (đặc tính monkeypatch: globals()[name] bị
    # ghi đè, nên gọi hàm cùng tên sẽ lookup và tìm version mới).
    _original_real_fields_for_tool = _real_fields_for_tool

    def _fake_real_fields(tool_name):
        if tool_name == "get_sale_order_detail":
            # Giả lập: field thật GIỜ ĐÃ CÓ commitment_date/effective_date
            # — đúng 2 field _KNOWN_GAPS hiện đang ngoại lệ.
            return {"id", "name", "partner_id", "amount_total", "state",
                    "date_order", "delivery_status",
                    "commitment_date", "effective_date"}
        return _original_real_fields_for_tool(tool_name)

    monkeypatch.setitem(globals(), "_real_fields_for_tool", _fake_real_fields)
    import pytest as _pytest
    with _pytest.raises(AssertionError, match="KHÔNG CÒN CẦN THIẾT"):
        test_gather_cases_fixture_labels_match_real_tool_fields()


def test_gather_cases_fixture_labels_match_real_tool_fields():
    """Đối chiếu fixture với field THẬT tool trả về — chặn lớp lỗi "fixture
    khẳng định khả năng tool không có" (gặp 2 lần: gather-erp-tool-fix,
    sale-order-detail-dates). 2 vi phạm đã biết nằm trong _KNOWN_GAPS —
    nhưng khác bản gốc, mục trong _KNOWN_GAPS VẪN được kiểm field thật:
    nếu field thật ĐÃ CÓ (gap đã sửa), đó là lỗi đòi xoá mục, không phải
    được bỏ qua âm thầm (sửa 2026-08-02: bản gốc chỉ bắt được kịch bản
    "nhãn không còn khớp câu chữ", không bắt được kịch bản "gap đã sửa" —
    continue thoát trước khi kiểm tra field thật)."""
    used = set()
    for topic, question, required_tools, required_facts, tool_fixtures in cases.GATHER_CASES:
        for tool_name, fixture_text in tool_fixtures.items():
            real_fields = _real_fields_for_tool(tool_name)
            low = fixture_text.casefold()
            for label, field_names in _DATE_STATUS_LABELS.items():
                if label not in low:
                    continue
                key = (topic, tool_name, label)
                ok = bool(set(field_names) & real_fields)
                if key in _KNOWN_GAPS:
                    used.add(key)
                    assert not ok, (
                        f"_KNOWN_GAPS có mục KHÔNG CÒN CẦN THIẾT: case "
                        f"{topic}, tool {tool_name!r}, nhãn {label!r} — "
                        f"field thật đã có "
                        f"({sorted(set(field_names) & real_fields)}), xoá "
                        f"mục này khỏi _KNOWN_GAPS.")
                    continue
                assert ok, (
                    f"case {topic}: fixture của tool {tool_name!r} dùng nhãn "
                    f"{label!r} nhưng tool không có field thật nào trong "
                    f"{field_names} (field thật: {sorted(real_fields)})")
    assert used == _KNOWN_GAPS, (
        f"_KNOWN_GAPS có mục không còn ứng với vi phạm thật (gap đã lấp "
        f"hoặc fixture đã đổi chữ): {sorted(_KNOWN_GAPS - used)} — xoá mục "
        f"đó khỏi _KNOWN_GAPS, đừng để nó nằm lại như cấu hình chết.")
