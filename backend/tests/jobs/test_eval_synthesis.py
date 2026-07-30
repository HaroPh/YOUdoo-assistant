# backend/tests/jobs/test_eval_synthesis.py
"""Set synthesis: grounded_acc / false_answer (gate cứng) / false_insufficient."""
import pytest

from evals import cases, fixtures, run_eval


def test_fixtures_load_chunks_returns_chunk_objects():
    topics = fixtures.available_topics()
    assert topics, "chunks.json rỗng — chạy lại Step 1"
    chunks = fixtures.load_chunks(topics[0])
    assert chunks
    c = chunks[0]
    assert isinstance(c.text, str) and c.text.strip()
    assert hasattr(c, "section_path") and hasattr(c, "rrf_score")


def test_fixtures_unknown_topic_raises():
    with pytest.raises(KeyError):
        fixtures.load_chunks("khong_ton_tai_topic_nao_the_nay")


def test_synthesis_cases_shape_and_topics_exist():
    assert len(cases.SYNTHESIS_CASES) >= 8
    topics = set(fixtures.available_topics())
    kinds = set()
    for topic, question, kind, expect in cases.SYNTHESIS_CASES:
        assert topic in topics, f"topic {topic} không có trong fixture"
        assert isinstance(question, str) and question.strip()
        assert kind in ("answerable", "insufficient")
        kinds.add(kind)
        if kind == "answerable":
            assert expect.strip(), "case answerable phải khai báo expect"
    assert kinds == {"answerable", "insufficient"}, "cần cả 2 loại case"


def test_answerable_expect_strings_actually_exist_in_fixture():
    """Chặn case tự mâu thuẫn: đòi model nói dữ kiện mà tài liệu KHÔNG chứa.
    Nếu test này đỏ → sửa `expect` theo nội dung chunk THẬT (script Task 4
    Step 2), TUYỆT ĐỐI không sửa fixture cho khớp case."""
    for topic, question, kind, expect in cases.SYNTHESIS_CASES:
        if kind != "answerable":
            continue
        corpus = " ".join(c.text for c in fixtures.load_chunks(topic)).casefold()
        assert expect.casefold() in corpus, (
            f"expect {expect!r} không có trong chunk của topic {topic}")


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


@pytest.mark.asyncio
async def test_answerable_correct_gives_perfect(monkeypatch):
    topic = fixtures.available_topics()[0]
    only = [(topic, "câu hỏi gì đó?", "answerable", "3 ngày")]
    monkeypatch.setattr(run_eval, "SYNTHESIS_CASES", only)
    llm = _ScriptedLLM(["Thời hạn là 3 ngày làm việc.\nNGUỒN_DÙNG: 1"])
    r = await run_eval.eval_synthesis(llm)
    assert r["set"] == "synthesis" and r["grounded_acc"] == 1.0
    assert r["false_answer"] == 0 and r["false_insufficient"] == 0


@pytest.mark.asyncio
async def test_insufficient_case_answered_is_false_answer(monkeypatch):
    topic = fixtures.available_topics()[0]
    only = [(topic, "giá cổ phiếu công ty hôm nay?", "insufficient", "")]
    monkeypatch.setattr(run_eval, "SYNTHESIS_CASES", only)
    llm = _ScriptedLLM(["Giá cổ phiếu hôm nay là 25.000 đồng."])
    r = await run_eval.eval_synthesis(llm)
    assert r["false_answer"] == 1
    assert r["grounded_acc"] == 0.0


@pytest.mark.asyncio
async def test_insufficient_case_refused_is_correct(monkeypatch):
    topic = fixtures.available_topics()[0]
    only = [(topic, "giá cổ phiếu công ty hôm nay?", "insufficient", "")]
    monkeypatch.setattr(run_eval, "SYNTHESIS_CASES", only)
    llm = _ScriptedLLM(["KHÔNG_ĐỦ_THÔNG_TIN"])
    r = await run_eval.eval_synthesis(llm)
    assert r["false_answer"] == 0 and r["grounded_acc"] == 1.0


@pytest.mark.asyncio
async def test_answerable_refused_is_false_insufficient(monkeypatch):
    topic = fixtures.available_topics()[0]
    only = [(topic, "câu hỏi gì đó?", "answerable", "3 ngày")]
    monkeypatch.setattr(run_eval, "SYNTHESIS_CASES", only)
    llm = _ScriptedLLM(["KHÔNG_ĐỦ_THÔNG_TIN"])
    r = await run_eval.eval_synthesis(llm)
    assert r["false_insufficient"] == 1
    assert r["false_answer"] == 0        # hướng NGƯỢC lại, không phải bịa
    assert r["grounded_acc"] == 0.0


@pytest.mark.asyncio
async def test_synthesis_reports_latency(monkeypatch):
    topic = fixtures.available_topics()[0]
    only = [(topic, "câu hỏi gì đó?", "answerable", "3 ngày")]
    monkeypatch.setattr(run_eval, "SYNTHESIS_CASES", only)
    llm = _ScriptedLLM(["3 ngày làm việc."])
    r = await run_eval.eval_synthesis(llm)
    assert "lat_p50" in r and "lat_p95" in r
