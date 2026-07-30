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
            # expect có thể là 1 chuỗi hoặc tuple nhiều phương án (SP-1C1).
            # Assert kiểu rõ ràng — tránh lỗi mơ hồ kiểu AttributeError nếu
            # ai đó lỡ khai expect là list thay vì tuple.
            assert isinstance(expect, (str, tuple)), (
                f"expect {expect!r} phải là str hoặc tuple[str, ...]")
            alts = expect if isinstance(expect, tuple) else (expect,)
            assert alts, "case answerable phải khai báo ít nhất 1 phương án"
            for alt in alts:
                assert isinstance(alt, str) and alt.strip(), (
                    f"mỗi phương án expect phải là chuỗi không rỗng: {alt!r}")
    assert kinds == {"answerable", "insufficient"}, "cần cả 2 loại case"


def test_answerable_expect_strings_actually_exist_in_fixture():
    """Chặn case tự mâu thuẫn: đòi model nói dữ kiện mà tài liệu KHÔNG chứa.
    Nếu test này đỏ → sửa `expect` theo nội dung chunk THẬT (script Task 4
    Step 2), TUYỆT ĐỐI không sửa fixture cho khớp case.

    Với `expect` dạng tuple (SP-1C1): CHỈ phương án đầu tiên (nguyên văn
    chunk) bắt buộc có trong corpus — các phương án sau là diễn giải THẬT
    của model, không phải trích dẫn tài liệu, nên không cần (và thường sẽ
    không) xuất hiện nguyên văn trong chunk."""
    for topic, question, kind, expect in cases.SYNTHESIS_CASES:
        if kind != "answerable":
            continue
        corpus = " ".join(c.text for c in fixtures.load_chunks(topic)).casefold()
        first = expect[0] if isinstance(expect, tuple) else expect
        assert first.casefold() in corpus, (
            f"expect {first!r} không có trong chunk của topic {topic}")


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


def test_grounded_match_chuoi_don_khop_nguyen_van_nhu_cu():
    """`expect` là 1 chuỗi (đa số case): hành vi y hệt trước SP-1C1 — so
    khớp substring nguyên văn, không có gì khác."""
    assert run_eval._grounded_match("3 ngày", "Thời hạn là 3 ngày làm việc.")
    assert not run_eval._grounded_match("3 ngày", "Thời hạn là 5 ngày làm việc.")


def test_grounded_match_tuple_khop_bat_ky_phuong_an_nao():
    """`expect` là tuple nhiều phương án: khớp NGUYÊN VĂN với BẤT KỲ phương
    án nào là đủ. Tái hiện đúng case thật đã gặp ở gate lần 1 (chạy lại
    --set synthesis xác nhận ổn định): phương án đầu (nguyên văn chunk)
    không khớp, nhưng phương án hai (diễn giải THẬT của model) khớp."""
    expect = ("không được hoàn trả", "không được áp dụng chính sách hoàn trả")
    assert run_eval._grounded_match(
        expect,
        "Rất tiếc, các sản phẩm hàng giảm giá không được áp dụng "
        "chính sách hoàn trả.")
    # Phương án đầu (nguyên văn) cũng phải khớp được khi model lặp đúng.
    assert run_eval._grounded_match(expect, "Hàng giảm giá không được hoàn trả.")


def test_grounded_match_tuple_khong_khop_phuong_an_nao_thi_fail():
    """An toàn: nếu câu trả lời không khớp NGUYÊN VĂN với bất kỳ phương án
    nào trong tuple (kể cả khi các từ của phương án xuất hiện rải rác sai
    thứ tự, hoặc câu trả lời đảo cực tính) thì vẫn phải fail — so khớp
    nguyên văn từng phương án không có logic mờ nào để lọt qua.

    Review round 3 (bên ngoài): chỉ dùng câu dài (span rộng) thì test này
    VẪN PASS ngay cả khi lỡ đưa nhầm heuristic "khớp theo thứ tự từ, giới
    hạn span" của round 1/2 trở lại (đã bị bác bỏ 2 lần) — vì heuristic đó
    cũng chặn được câu span rộng. Thêm 2 câu SPAN NGẮN (đã lọt qua chính
    heuristic round 2) để test này thật sự khoá được thiết kế đã bị bác bỏ,
    không chỉ khoá phần dễ."""
    expect = ("không được hoàn trả", "không được áp dụng chính sách hoàn trả")
    assert not run_eval._grounded_match(
        expect,
        "Không có quy định hạn chế nào, nên hàng giảm giá vẫn được hoàn "
        "trả bình thường trong 30 ngày.")
    assert not run_eval._grounded_match(
        expect, "Hàng giảm giá được hoàn trả bình thường trong vòng 7 ngày.")
    assert not run_eval._grounded_match(
        expect, "Không sao, hàng vẫn được hoàn trả.")
    assert not run_eval._grounded_match(
        expect, "Hàng giảm giá không bị hạn chế, vẫn được hoàn trả.")


def test_grounded_match_tam_dung_xu_ly_khong_bi_danh_lua_boi_thu_tu_tu():
    """`tạm dừng xử lý` là expect đa từ CÒN LẠI không dùng tuple (vẫn là
    chuỗi đơn) — review round 2 (bên ngoài) phát hiện đây cũng là expect
    "đủ điều kiện" bị lọt qua bởi heuristic cũ nếu còn tồn tại. Xác nhận
    không còn đường nào để lọt qua nữa vì đã bỏ hẳn logic mờ."""
    assert not run_eval._grounded_match(
        "tạm dừng xử lý", "Hệ thống tạm dừng, sau đó xử lý tiếp.")
    assert not run_eval._grounded_match(
        "tạm dừng xử lý", "Đơn hàng bị tạm ngưng xử lý sau 15 ngày.")


@pytest.mark.asyncio
async def test_answerable_dien_giai_da_biet_khong_bi_tinh_la_fail(monkeypatch):
    """Tái hiện nguyên văn case thật gặp ở SP-1C1 Task 7 (chạy gate thật):
    model diễn giải đúng nghĩa theo đúng phương án đã ghi nhận trong
    SYNTHESIS_CASES — không còn bị tính là fail."""
    topic = fixtures.available_topics()[0]
    expect = ("không được hoàn trả", "không được áp dụng chính sách hoàn trả")
    only = [(topic, "Hàng giảm giá có được hoàn trả không?",
             "answerable", expect)]
    monkeypatch.setattr(run_eval, "SYNTHESIS_CASES", only)
    llm = _ScriptedLLM(["Rất tiếc, các sản phẩm hàng giảm giá không được "
                        "áp dụng chính sách hoàn trả.\nNGUỒN_DÙNG: 4"])
    r = await run_eval.eval_synthesis(llm)
    assert r["grounded_acc"] == 1.0, r["fails"]
    assert r["false_answer"] == 0 and r["false_insufficient"] == 0


@pytest.mark.asyncio
async def test_answerable_dao_cuc_tinh_van_bi_tinh_la_fail(monkeypatch):
    """An toàn: model trả lời SAI (đảo cực tính) cho case answerable — kể cả
    khi câu trả lời chứa rải rác các từ của một phương án đã ghi nhận —
    vẫn phải bị tính là fail, vì so khớp là NGUYÊN VĂN, không có logic mờ
    theo thứ tự từ nào có thể bị đánh lừa."""
    topic = fixtures.available_topics()[0]
    expect = ("không được hoàn trả", "không được áp dụng chính sách hoàn trả")
    only = [(topic, "Hàng giảm giá có được hoàn trả không?",
             "answerable", expect)]
    monkeypatch.setattr(run_eval, "SYNTHESIS_CASES", only)
    llm = _ScriptedLLM(["Không có quy định hạn chế nào, nên hàng giảm giá "
                        "vẫn được hoàn trả bình thường trong 30 ngày.\n"
                        "NGUỒN_DÙNG: 4"])
    r = await run_eval.eval_synthesis(llm)
    assert r["grounded_acc"] == 0.0, "câu trả lời đảo cực tính phải bị fail"
    assert len(r["fails"]) == 1


@pytest.mark.asyncio
async def test_synthesis_reports_latency(monkeypatch):
    topic = fixtures.available_topics()[0]
    only = [(topic, "câu hỏi gì đó?", "answerable", "3 ngày")]
    monkeypatch.setattr(run_eval, "SYNTHESIS_CASES", only)
    llm = _ScriptedLLM(["3 ngày làm việc."])
    r = await run_eval.eval_synthesis(llm)
    assert "lat_p50" in r and "lat_p95" in r
