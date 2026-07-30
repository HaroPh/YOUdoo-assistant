# backend/tests/jobs/test_eval_multi_source.py
"""Set multi_source: both_source_coverage / citation_validity / fabricated_number."""
import pytest

from evals import cases, fixtures, run_eval


def test_multi_source_cases_shape_and_topics_exist():
    assert len(cases.MULTI_SOURCE_CASES) >= 8
    topics = set(fixtures.available_topics())
    for topic, erp_block, question, doc_fact, erp_fact in cases.MULTI_SOURCE_CASES:
        assert topic in topics, f"topic {topic} không có trong fixture"
        assert erp_block.strip() and question.strip()
        assert doc_fact.strip() and erp_fact.strip()
        # dữ kiện ERP kỳ vọng PHẢI có trong erp_block đóng băng, nếu không
        # case tự mâu thuẫn (đòi model nói điều dữ liệu không hề chứa)
        assert erp_fact.casefold() in erp_block.casefold()


def test_doc_facts_actually_exist_in_fixture():
    """Nửa còn lại của kiểm tra tự-mâu-thuẫn: dữ kiện TÀI LIỆU kỳ vọng phải
    có thật trong chunk. Nếu đỏ → sửa `expect_doc_fact` theo chunk THẬT
    (script Task 4 Step 2), KHÔNG sửa fixture cho khớp case."""
    for topic, erp_block, question, doc_fact, erp_fact in cases.MULTI_SOURCE_CASES:
        corpus = " ".join(c.text for c in fixtures.load_chunks(topic)).casefold()
        assert doc_fact.casefold() in corpus, (
            f"doc_fact {doc_fact!r} không có trong chunk của topic {topic}")


def test_cited_indices_parses_marker():
    assert run_eval._cited_indices("trả lời gì đó\nNGUỒN_DÙNG: 1,3") == {1, 3}


def test_cited_indices_missing_marker_is_empty():
    assert run_eval._cited_indices("không có marker") == set()


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _ScriptedLLM:
    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = 0

    async def ainvoke(self, messages):
        i = min(self.calls, len(self.contents) - 1)
        self.calls += 1
        return _FakeResp(self.contents[i])


def _one_case(monkeypatch):
    topic = fixtures.available_topics()[0]
    only = [(topic, "Đơn S00042 | Azure Interior | 1.500.000",
             "Đơn S00042 có đúng SLA không?", "3 ngày", "S00042")]
    monkeypatch.setattr(run_eval, "MULTI_SOURCE_CASES", only)
    return topic


@pytest.mark.asyncio
async def test_both_sources_present_and_valid_citation(monkeypatch):
    _one_case(monkeypatch)
    llm = _ScriptedLLM(["Theo quy định 3 ngày, đơn S00042 đạt yêu cầu.\n"
                        "NGUỒN_DÙNG: 1"])
    r = await run_eval.eval_multi_source(llm)
    assert r["set"] == "multi_source"
    assert r["both_source_coverage"] == 1.0
    assert r["citation_validity"] == 1.0
    assert r["fabricated_number"] == 0


@pytest.mark.asyncio
async def test_missing_doc_fact_lowers_coverage(monkeypatch):
    _one_case(monkeypatch)
    llm = _ScriptedLLM(["Đơn S00042 ổn.\nNGUỒN_DÙNG: 1"])
    r = await run_eval.eval_multi_source(llm)
    assert r["both_source_coverage"] == 0.0


@pytest.mark.asyncio
async def test_out_of_range_citation_is_invalid(monkeypatch):
    _one_case(monkeypatch)
    # fixture chỉ có N chunk; 99 chắc chắn ngoài phạm vi
    llm = _ScriptedLLM(["Theo quy định 3 ngày, đơn S00042 đạt.\n"
                        "NGUỒN_DÙNG: 99"])
    r = await run_eval.eval_multi_source(llm)
    assert r["citation_validity"] == 0.0


@pytest.mark.asyncio
async def test_fabricated_number_detected(monkeypatch):
    _one_case(monkeypatch)
    # 9.999.999 không có trong fixture chunk lẫn erp_block
    llm = _ScriptedLLM(["Theo quy định 3 ngày, đơn S00042 trị giá 9.999.999.\n"
                        "NGUỒN_DÙNG: 1"])
    r = await run_eval.eval_multi_source(llm)
    assert r["fabricated_number"] == 1


@pytest.mark.asyncio
async def test_multi_source_reports_latency(monkeypatch):
    _one_case(monkeypatch)
    llm = _ScriptedLLM(["Theo quy định 3 ngày, đơn S00042 đạt.\nNGUỒN_DÙNG: 1"])
    r = await run_eval.eval_multi_source(llm)
    assert "lat_p50" in r and "lat_p95" in r


@pytest.mark.asyncio
async def test_so_trong_nhan_muc_khong_bi_quy_la_bia(monkeypatch):
    """Tái hiện đúng bug đã sửa: _format_context() gắn chỉ số [i] + nhãn mục
    (section_path/sheet/basename) vào MỖI chunk. Trước fix, allowed chỉ dựng
    từ c.text trần nên số trong nhãn mục (vd chunk thứ [3], hay nhãn
    "(Điều 3.2)") bị quy oan là bịa dù model chỉ đang trích dẫn đúng."""
    topic = _one_case(monkeypatch)
    from evals import fixtures
    chunks = fixtures.load_chunks(topic)
    # _format_context số hoá chunk từ 1 — chunk đầu chắc chắn mang nhãn "[1]"
    llm = _ScriptedLLM([
        "Theo mục [1], đơn S00042 đạt yêu cầu trong 3 ngày.\nNGUỒN_DÙNG: 1"])
    r = await run_eval.eval_multi_source(llm)
    assert r["fabricated_number"] == 0, (
        f"chỉ số [1] trong _format_context() bị quy nhầm là số bịa: "
        f"{r['fails']}")
