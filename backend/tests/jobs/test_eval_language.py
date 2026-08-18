"""Bộ dò ngôn ngữ đầu ra phải phân biệt NHÃN với DANH TỪ RIÊNG.

Spike 2026-08-18 báo động giả vì đếm tên tài liệu tiếng Việt ở phần trích dẫn
nguồn là lỗi. Tên riêng giữ nguyên mới đúng — dịch chúng thì mất khả năng tra
ngược tài liệu/sản phẩm.
"""
import pytest

from evals import run_eval
from evals.cases import LANGUAGE_CASES
from evals.run_eval import looks_vietnamese, _has_english_evidence


def test_cau_tieng_anh_thuan_thi_khong_bi_bao_dong():
    assert looks_vietnamese("Order P00003 from Azure Interior. Status: Draft.") is False


def test_cau_tieng_anh_kem_TEN_RIENG_tieng_viet_thi_khong_bi_bao_dong():
    """Đây đúng ca spike đếm nhầm."""
    assert looks_vietnamese(
        "The receipt procedure has 4 steps.\n\nSources:\n"
        "- Quy trình nhập kho › Bước 1 (sop.docx)") is False


def test_cau_tieng_viet_that_thi_bi_bao_dong():
    assert looks_vietnamese(
        "Chi tiết đơn mua P00003 từ nhà cung cấp Azure Interior.") is True


def test_moi_prompt_deu_co_ca_hai_ngon_ngu():
    for ten in ("CHITCHAT_PROMPT", "RAG_SYNTHESIS_PROMPT", "FUSE_PROMPT"):
        langs = {lang for p, _q, lang in LANGUAGE_CASES if p == ten}
        assert langs == {"vi", "en"}, ten


def test_khong_bi_bao_dong_sai_cho_anh_va_cho_viet():
    """Hồi quy: "cho" trong tiếng Anh (echo, school, anchor, chose, psychology)
    không còn dọng báo động sai bằng ranh giới từ \b."""
    assert looks_vietnamese("I need to echo this value back") is False
    assert looks_vietnamese("Go to school tomorrow") is False
    assert looks_vietnamese("Drop the anchor into the water") is False
    assert looks_vietnamese("I chose this option") is False
    assert looks_vietnamese("Psychology is the study of behavior") is False


def test_tieng_viet_that_van_dung_sau_ranh_gioi():
    """Hồi quy: tiếng Việt thật với "cho" vẫn được nhận diện đúng sau khi
    thêm ranh giới từ."""
    assert looks_vietnamese("Cho tôi xin lỗi vì đã làm việc này") is True
    assert looks_vietnamese("Vui lòng xác nhận đơn hàng này") is True


def test_bang_chung_duong_tieng_anh_can_it_nhat_hai_hu_tu():
    # Một hư từ đơn lẻ (va chạm ngẫu nhiên) không đủ — cùng ngưỡng detect_lang
    # (Fix 1) để tránh 2 bộ đo trôi khỏi nhau.
    assert _has_english_evidence("the order") is True          # 2 từ
    assert _has_english_evidence("a") is False                 # 1 từ, không đủ
    assert _has_english_evidence("42 100 999") is False        # không từ nào


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
async def test_body_rong_khong_duoc_tinh_la_en(monkeypatch):
    """Bug đã sửa: body rỗng/lỗi từng ngầm định là "en" (thiếu bằng chứng
    tiếng Việt) và lọt qua gate acc==1.0 tuyệt đối. Giờ phải bị gắn cờ EMPTY,
    không được coi là pass ngầm."""
    only = [("CHITCHAT_PROMPT", "hi, who are you?", "en")]
    monkeypatch.setattr(run_eval, "LANGUAGE_CASES", only)
    llm = _ScriptedLLM([""])
    r = await run_eval.eval_language(llm)
    assert r["acc"] == 0.0
    assert r["fails"][0]["got"] == "EMPTY"


@pytest.mark.asyncio
async def test_body_khong_ro_ngon_ngu_khong_duoc_tinh_la_en(monkeypatch):
    """Cùng lớp bug: body không có hư từ tiếng Việt LẪN tiếng Anh (ví dụ toàn
    số) trước đây rơi vào nhánh else → "en" ngầm định. Giờ phải INCONCLUSIVE."""
    only = [("CHITCHAT_PROMPT", "hi, who are you?", "en")]
    monkeypatch.setattr(run_eval, "LANGUAGE_CASES", only)
    llm = _ScriptedLLM(["42 100 999"])
    r = await run_eval.eval_language(llm)
    assert r["acc"] == 0.0
    assert r["fails"][0]["got"] == "INCONCLUSIVE"


@pytest.mark.asyncio
async def test_body_tieng_anh_that_van_pass_binh_thuong(monkeypatch):
    only = [("CHITCHAT_PROMPT", "hi, who are you?", "en")]
    monkeypatch.setattr(run_eval, "LANGUAGE_CASES", only)
    llm = _ScriptedLLM(["Hi! I am the Youdoo assistant, how can I help you?"])
    r = await run_eval.eval_language(llm)
    assert r["acc"] == 1.0
    assert r["fails"] == []
