# backend/tests/agents/test_confirmation.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import AIMessage


from evals.cases import KEYWORD_CASES
from src.agents.confirmation import (
    CONFIRM, CANCEL, UNCLEAR,
    classify_keyword, classify_confirmation,
)


# ── classify_keyword ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", ["có", "Có", "có!", "yes", "ok", "đồng ý", "xác nhận"])
def test_keyword_clear_yes_returns_confirm(text):
    assert classify_keyword(text) == CONFIRM


@pytest.mark.parametrize("text", ["không", "Không", "no", "hủy", "thôi", "đừng"])
def test_keyword_clear_no_returns_cancel(text):
    assert classify_keyword(text) == CANCEL


def test_keyword_yes_phrase_with_extra_words_returns_confirm():
    assert classify_keyword("ừ làm đi") == CONFIRM


def test_keyword_no_phrase_with_extra_words_returns_cancel():
    assert classify_keyword("thôi khỏi") == CANCEL


def test_keyword_negation_has_both_signals_returns_unclear():
    # "không đồng ý" = do NOT agree — contains a cancel word and a confirm word
    assert classify_keyword("không đồng ý") == UNCLEAR


def test_keyword_neither_signal_returns_unclear():
    assert classify_keyword("nó sẽ làm gì?") == UNCLEAR


@pytest.mark.parametrize("text", ["ừm", "um", "ừm để tôi xem lại đã, chưa chắc lắm"])
def test_keyword_hesitation_filler_returns_unclear(text):
    # Regression (found 2026-07-16 via a live confirm-gate probe on
    # feat/agentic-wr-guardrails): "ừm"/"um" are Vietnamese hesitation
    # fillers ("um..."), not affirmatives. They used to sit in
    # _CONFIRM_WORDS, so a hedging reply like "ừm để tôi xem lại đã, chưa
    # chắc lắm" ("um, let me check again, not quite sure") matched the
    # confirm keyword alone (no cancel word present) and short-circuited
    # straight to CONFIRM at the keyword fast-path — skipping the LLM
    # fallback entirely, which would have classified it UNCLEAR. Reproduced
    # 2/2 live model runs (qwen3:8b, qwythos-9b), same root cause both
    # times. A write-confirmation gate must never treat a hesitation filler
    # as a clean one-sided yes (see module docstring: "the danger is
    # asymmetric").
    assert classify_keyword(text) == UNCLEAR


async def test_hybrid_hesitation_filler_falls_back_to_llm_not_auto_confirm():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="UNCLEAR"))
    result = await classify_confirmation("ừm để tôi xem lại đã, chưa chắc lắm", llm)
    assert result == UNCLEAR
    llm.ainvoke.assert_awaited_once()


# ── classify_confirmation (hybrid) ────────────────────────────────────────────

async def test_hybrid_keyword_hit_skips_llm():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="CONFIRM"))
    result = await classify_confirmation("có", llm)
    assert result == CONFIRM
    llm.ainvoke.assert_not_awaited()


async def test_hybrid_keyword_miss_falls_back_to_llm():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="CONFIRM"))
    result = await classify_confirmation("sao cũng được, bạn quyết đi", llm)
    assert result == CONFIRM
    llm.ainvoke.assert_awaited_once()


async def test_hybrid_llm_garbage_returns_unclear():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="tôi không chắc lắm"))
    result = await classify_confirmation("ờ thì tùy bạn vậy", llm)
    assert result == UNCLEAR


# ── bẫy "dung" không dấu (vá 2026-08-22) ────────────────────────────────────
def test_dung_khong_dau_KHONG_duoc_hieu_la_dong_y():
    """Không dấu, "dung" là dạng chung của ĐÚNG / DỪNG / ĐỪNG — hai trong ba
    nghĩa là TỪ CHỐI. Trước bản vá nó nằm ở phía CONFIRM, nên người gõ không
    dấu để bảo *dừng lại* bị hệ thống ghi thẳng vào Odoo.

    Đây là bẫy với NGƯỜI DÙNG ĐÚNG ĐẮN, không cần ai có ác ý.
    """
    assert classify_keyword("dung") == UNCLEAR


def test_dung_dung_lam_KHONG_duoc_hieu_la_dong_y():
    """Ca đo được trước bản vá, tệ hơn ví dụ trong báo cáo kiểm toán:
    "dung, dung lam" = "dừng, đừng làm" → phân loại CONFIRM → THỰC THI."""
    assert classify_keyword("dung, dung lam") == UNCLEAR


def test_dung_CO_DAU_van_giu_nguyen_y_nghia():
    """Nửa còn lại của cặp: `_normalize()` KHÔNG bỏ dấu, nên bản vá chỉ được
    chạm đường không dấu. Gỡ nhầm cả "đúng" là làm hỏng lối tắt hợp lệ."""
    assert classify_keyword("đúng") == CONFIRM
    assert classify_keyword("dừng") == CANCEL
    assert classify_keyword("đừng") == CANCEL


def test_cac_tu_dong_y_khac_KHONG_bi_anh_huong():
    """Đối chứng chống sửa quá tay."""
    for t in ("co", "có", "ok", "okay", "yes", "dong y", "xac nhan"):
        assert classify_keyword(t) == CONFIRM, t


def test_KHONG_token_khong_dau_nao_trung_dang_bo_dau_cua_phe_kia():
    """Bất biến bắt được bẫy "dung" một cách MÁY MÓC, không cần ai phán đoán.

    Bẫy đó không phải chuyện tinh tế về ngôn ngữ: "dung" ĐÚNG BẰNG dạng bỏ dấu
    của "đừng" và "dừng" — **cả hai đã nằm sẵn trong `_CANCEL_WORDS`**. Nghĩa là
    dữ liệu để phát hiện nó đã có trong repo từ đầu; chỉ thiếu người đối chiếu.

    Phạm vi hẹp có chủ đích — chỉ xét token VỐN ĐÃ không dấu:
    `_normalize()` KHÔNG bỏ dấu, nên "đúng" có dấu chỉ khớp khi người dùng gõ
    đúng dấu, không bao giờ va vào "dừng". Bắt cả token có dấu sẽ buộc phải gỡ
    "đúng" — một lối tắt hoàn toàn hợp lệ.
    """
    import unicodedata

    from src.agents.confirmation import _CANCEL_WORDS, _CONFIRM_WORDS

    def bo_dau(t: str) -> str:
        t = t.replace("đ", "d").replace("Đ", "D")
        return "".join(c for c in unicodedata.normalize("NFD", t)
                       if not unicodedata.combining(c))

    huy_bo_dau = {}
    for w in _CANCEL_WORDS:
        huy_bo_dau.setdefault(bo_dau(w), []).append(w)
    dong_y_bo_dau = {}
    for w in _CONFIRM_WORDS:
        dong_y_bo_dau.setdefault(bo_dau(w), []).append(w)

    va_cham = []
    for tu in _CONFIRM_WORDS:
        if bo_dau(tu) == tu and tu in huy_bo_dau:
            va_cham.append((tu, "CONFIRM", huy_bo_dau[tu]))
    for tu in _CANCEL_WORDS:
        if bo_dau(tu) == tu and tu in dong_y_bo_dau:
            va_cham.append((tu, "CANCEL", dong_y_bo_dau[tu]))

    assert va_cham == [], (
        "token không dấu trùng dạng bỏ dấu của phe đối lập — người gõ không "
        f"dấu sẽ bị hiểu ngược ý: {va_cham}")


# ── cổng gác cho LỚP TỪ KHOÁ (thêm 2026-08-22) ─────────────────────────────
@pytest.mark.parametrize("text,mong_doi", KEYWORD_CASES,
                         ids=[t for t, _ in KEYWORD_CASES])
def test_loi_tat_tu_khoa_dung_tren_tung_ca(text, mong_doi):
    """Lớp từ khoá quyết định phần lớn lượt xác nhận thật, nhưng tới
    2026-08-22 nó CHƯA TỪNG được đo: `CONFIRM_CASES` cố ý né nó, và đo được
    `classify_keyword` bắt **0/24** ca của bộ đó. Bẫy "dung" sống sót vì
    không cổng nào gác lớp này — cùng lớp lỗi với chân sparse chết và
    reranker chết.

    Bộ này tất định, không gọi LLM, nên chạy trong suite mặc định.
    """
    assert classify_keyword(text) == mong_doi


def test_loi_tat_KHONG_BAO_GIO_tu_quyet_khi_co_tin_hieu_HAI_CHIEU():
    """Cổng tuyệt đối, tương đương `false_confirm = 0` của bộ `confirm`.

    Một câu mang cả tín hiệu đồng ý lẫn từ chối mà lối tắt tự quyết là kiểu
    hỏng nguy hiểm nhất ở đây: nó THỰC THI mà không ai kịp hỏi lại.
    """
    for text in ("không đồng ý", "ừ nhưng khoan đã", "ok nhưng khoan",
                 "đúng, mà thôi", "co, huy di"):
        assert classify_keyword(text) == UNCLEAR, text


def test_hai_bo_ca_BU_NHAU_chu_khong_chong_len():
    """Khoá chính tính chất khiến lỗ hổng này tồn tại.

    `CONFIRM_CASES` đo LLM, `KEYWORD_CASES` đo lối tắt. Nếu một ngày ca của bộ
    đầu bắt đầu rơi vào lối tắt, thì bộ đó **thôi đo LLM** mà không ai biết —
    đúng kiểu "test vẫn xanh nhưng không còn đo gì".
    """
    from evals.cases import CONFIRM_CASES

    lot = [t for t, _ in CONFIRM_CASES if classify_keyword(t) != UNCLEAR]
    assert lot == [], (
        "ca của CONFIRM_CASES nay bị lối tắt bắt — bộ đó không còn đo LLM "
        f"trên các ca này nữa: {lot}")
