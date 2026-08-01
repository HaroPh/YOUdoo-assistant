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
        assert doc_fact.strip()
        # erp_fact: str đơn (7/8 case) hoặc tuple nhiều phương án đã quan sát
        # thật (Task 11, case S00050) — chuẩn hoá về tuple để kiểm đồng nhất,
        # cùng khuôn với _grounded_match().
        alts = erp_fact if isinstance(erp_fact, tuple) else (erp_fact,)
        for alt in alts:
            assert alt.strip()
            # dữ kiện ERP kỳ vọng PHẢI có trong erp_block đóng băng, nếu không
            # case tự mâu thuẫn (đòi model nói điều dữ liệu không hề chứa)
            assert alt.casefold() in erp_block.casefold(), (
                f"phương án {alt!r} không có trong erp_block của case {topic}")


def test_derived_digits_keys_ton_tai_trong_cases():
    """An toàn (review độc lập, round 1): nếu ai đó sửa lại wording câu hỏi
    trong MULTI_SOURCE_CASES mà quên cập nhật MULTI_SOURCE_DERIVED_DIGITS,
    entry cũ trở thành dead code lặng lẽ — allowed thu hẹp lại, gate đỏ lại,
    chỉ phát hiện được qua một lượt chạy live tốn tiền. Test này bắt lỗi đó
    ngay ở mức unit, rẻ."""
    keys = {(t, q) for t, _erp, q, _doc, _erp_fact in cases.MULTI_SOURCE_CASES}
    assert set(cases.MULTI_SOURCE_DERIVED_DIGITS) <= keys, (
        "MULTI_SOURCE_DERIVED_DIGITS có key không khớp câu hỏi nào trong "
        "MULTI_SOURCE_CASES — có thể câu hỏi đã bị sửa mà quên cập nhật")


def test_doc_facts_actually_exist_in_fixture():
    """Nửa còn lại của kiểm tra tự-mâu-thuẫn: dữ kiện TÀI LIỆU kỳ vọng phải
    có thật trong chunk. Nếu đỏ → sửa `expect_doc_fact` theo chunk THẬT
    (script Task 4 Step 2), KHÔNG sửa fixture cho khớp case."""
    for topic, erp_block, question, doc_fact, erp_fact in cases.MULTI_SOURCE_CASES:
        corpus = " ".join(c.text for c in fixtures.load_chunks(topic)).casefold()
        assert doc_fact.casefold() in corpus, (
            f"doc_fact {doc_fact!r} không có trong chunk của topic {topic}")


def _s00050_case():
    """Case thật gây hồi quy both_source_coverage ở Task 10 (đo SAU) — trả
    về entry gốc từ MULTI_SOURCE_CASES (không hard-code lại tuple) để test
    luôn đi cùng dữ liệu thật, không lệch nếu case đổi sau này."""
    return next(c for c in cases.MULTI_SOURCE_CASES
                if c[0] == "chinh_sach_thanh_toan"
                and c[2].startswith("Đơn S00050"))


def test_s00050_grounded_match_khop_qua_ten_khach_hang():
    """Tái hiện NGUYÊN VĂN lý do hồi quy Task 10: model trả lời ĐÚNG, khẳng
    định, dùng cả 2 nguồn — nhưng gọi khách hàng bằng TÊN thay vì lặp mã đơn.
    _grounded_match phải khớp erp_fact qua phương án "Gemini Furniture" dù
    body KHÔNG chứa "S00050"."""
    erp_fact = _s00050_case()[4]
    body = ("Có, đơn hàng mới của Gemini Furniture sẽ bị tạm dừng xử lý. "
            "Theo quy định, khi khách hàng có đơn hàng quá hạn thanh toán "
            "trên 30 ngày, các đơn hàng mới sẽ bị tạm dừng cho đến khi "
            "khách hàng hoàn tất thanh toán các khoản nợ cũ.")
    assert "S00050" not in body
    assert run_eval._grounded_match(erp_fact, body)


def test_s00050_grounded_match_khop_khi_ca_hai_phuong_an_cung_co_mat():
    """Không loại trừ lẫn nhau — body chứa CẢ HAI phương án ("S00050" và
    "Gemini Furniture") vẫn phải khớp, không phải "chỉ đúng 1 trong 2"."""
    erp_fact = _s00050_case()[4]
    body = "Đơn S00050 của khách Gemini Furniture sẽ bị tạm dừng xử lý."
    assert run_eval._grounded_match(erp_fact, body)


def test_s00050_grounded_match_khong_khop_khi_thieu_ca_hai_phuong_an():
    """An toàn: tuple KHÔNG được làm phép đo lỏng lẻo tuỳ tiện — body không
    chứa "S00050" lẫn "Gemini Furniture" vẫn phải bị coi là KHÔNG khớp."""
    erp_fact = _s00050_case()[4]
    body = "Đơn hàng mới của khách này sẽ bị tạm dừng xử lý."
    assert not run_eval._grounded_match(erp_fact, body)


def test_chi_case_s00050_doi_kieu_erp_fact_7_case_con_lai_van_la_str():
    """Ranh giới thay đổi (Global Constraints task 11): CHỈ case S00050 được
    đổi erp_fact thành tuple; 7 case còn lại của MULTI_SOURCE_CASES phải giữ
    nguyên kiểu str đơn — không bị đổi kiểu nhầm khi sửa case này."""
    tuple_cases = [
        (topic, question) for topic, _erp, question, _doc, erp_fact
        in cases.MULTI_SOURCE_CASES if isinstance(erp_fact, tuple)
    ]
    assert tuple_cases == [("chinh_sach_thanh_toan",
                             "Đơn S00050 quá hạn thanh toán 32 ngày, đơn "
                             "hàng mới của khách này có bị tạm dừng xử lý "
                             "không?")]
    s00050_erp_fact = _s00050_case()[4]
    assert s00050_erp_fact == ("S00050", "Gemini Furniture")


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


def _thanh_toan_case(monkeypatch):
    """Case thật gây fail ở gate Task 7 (2 lượt chạy) — chinh_sach_thanh_toan/
    INV-2026-00020, câu hỏi đòi tính ngày dương lịch."""
    topic = "chinh_sach_thanh_toan"
    question = ("Hóa đơn INV/2026/00020 xuất ngày 01/07/2026, khi nào thì "
               "quá hạn thanh toán?")
    only = [(topic,
             "Hóa đơn INV/2026/00020 | Khách Wood Corner | xuất ngày "
             "01/07/2026 | chưa thanh toán",
             question, "30 ngày", "INV/2026/00020")]
    monkeypatch.setattr(run_eval, "MULTI_SOURCE_CASES", only)
    return topic, question


@pytest.mark.asyncio
async def test_so_suy_ra_duoc_cho_case_ngay_thang_khong_bi_quy_la_bia(monkeypatch):
    """Tái hiện NGUYÊN VĂN response thật đã gây fail ở cổng M3 (2 lượt chạy
    live, cùng 1 response): model tính đúng 31/07/2026 (01/07 + 30 ngày, Điều
    3) và 01/08/2026 (quá hạn từ hôm sau) — số học ngày tháng hợp lệ từ dữ
    kiện có căn cứ, không phải bịa. Đã ghi nhận thủ công trong
    MULTI_SOURCE_DERIVED_DIGITS (cases.py) sau khi Task 6's quyết định "chấp
    nhận, không mở rộng" được xem lại — không còn bị quy là bịa nữa."""
    _thanh_toan_case(monkeypatch)
    llm = _ScriptedLLM([
        "Hóa đơn INV/2026/00020 của khách hàng Wood Corner được xuất ngày "
        "01/07/2026. Theo quy định về thời hạn thanh toán mặc định là 30 "
        "ngày kể từ ngày xuất hóa đơn, hóa đơn này sẽ đến hạn thanh toán vào "
        "ngày 31/07/2026. Do đó, hóa đơn sẽ bắt đầu quá hạn từ ngày "
        "01/08/2026.\nNGUỒN_DÙNG: 3"])
    r = await run_eval.eval_multi_source(llm)
    assert r["fabricated_number"] == 0, r["fails"]


@pytest.mark.asyncio
async def test_so_suy_ra_duoc_khong_lan_sang_cau_hoi_khac_cung_topic(monkeypatch):
    """An toàn: MULTI_SOURCE_DERIVED_DIGITS khoá theo (topic, question) —
    một câu hỏi KHÁC trên CÙNG topic không được hưởng "08"/"31" đã ghi nhận
    riêng cho case ngày-tháng.

    Review độc lập (round 1) phát hiện bản đầu của test này KHÔNG thật sự
    kiểm được rò rỉ: response kịch bản dùng số "99" không liên quan, nên dù
    có giả lập rò "08"/"31" sang case này, kết quả (fabricated_number=1) vẫn
    y hệt — test "xanh" mà không chứng minh được gì. Sửa: response giờ
    chứa CHÍNH "08" và "31" (số đã ghi nhận cho case kia) — nếu có rò rỉ,
    2 số này sẽ bị coi là hợp lệ và fabricated sẽ RỖNG thay vì chứa đúng
    2 số đó. Assert trên DANH SÁCH fabricated, không chỉ đếm số lượng."""
    topic = "chinh_sach_thanh_toan"
    only = [(topic,
             "Đơn S00050 | Khách Gemini Furniture | quá hạn thanh toán 32 ngày",
             "Đơn S00050 quá hạn thanh toán 32 ngày, đơn hàng mới của khách "
             "này có bị tạm dừng xử lý không?",
             "tạm dừng xử lý", "S00050")]
    monkeypatch.setattr(run_eval, "MULTI_SOURCE_CASES", only)
    llm = _ScriptedLLM([
        "Đơn S00050 quá hạn 32 ngày, tạm dừng xử lý từ 31/08.\nNGUỒN_DÙNG: 1"])
    r = await run_eval.eval_multi_source(llm)
    assert r["fails"][0]["fabricated"] == ["08", "31"], (
        f"'08'/'31' (ghi nhận cho case INV-2026-00020 khác) không được rò "
        f"sang câu hỏi này — nếu rò, danh sách fabricated sẽ rỗng thay vì "
        f"chứa đúng 2 số đó: {r['fails']}")


@pytest.mark.asyncio
async def test_so_bia_that_van_bi_bat_du_cung_case_ngay_thang(monkeypatch):
    """An toàn: dù case này đã có 2 số suy ra được ("08"/"31") trong
    allowed, một số bịa KHÁC (không xuất hiện trong erp_block/chunk/số suy ra
    được) vẫn phải bị bắt — nới allowed không mở toang cửa cho mọi số."""
    _thanh_toan_case(monkeypatch)
    llm = _ScriptedLLM([
        "Hóa đơn INV/2026/00020 xuất ngày 01/07/2026, quá hạn thanh toán từ "
        "ngày 27/12/2026 (số 27 và 12 bịa hoàn toàn).\nNGUỒN_DÙNG: 3"])
    r = await run_eval.eval_multi_source(llm)
    assert r["fabricated_number"] == 1, r["fails"]


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
