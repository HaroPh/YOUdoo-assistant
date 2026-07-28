import pytest

from src.llm.budget import BudgetLedger, Verdict
from src.llm.catalog import spec_for
from src.llm.store import InMemoryUsageStore
from tests.llm.conftest import ExplodingStore, FakeClock

GEMMA = spec_for("gemma-4-26b")          # rpm 30, tpm 16_000, rpd 14_400, x1.0
GROQ = spec_for("groq-gpt-oss-20b")      # rpm 30, tpm  8_000, rpd  1_000, x2.3
OR_LING = spec_for("or-ling")            # rpd 50, quota_scope="account"
OR_NEMO = spec_for("or-nemotron")        # rpd 50, quota_scope="account"


def _ledger(clock, store=None):
    return BudgetLedger(store or InMemoryUsageStore(), clock=clock)


def _fill(ledger, spec, n, total_tokens=1):
    for _ in range(n):
        ledger.record(spec, prompt_tokens=1, completion_tokens=1,
                      total_tokens=total_tokens)


def test_so_sach_trong_thi_cho_goi(clock):
    assert _ledger(clock).can_afford(GEMMA, 100) is Verdict.OK


def test_cham_tran_rpm_thi_chan(clock):
    led = _ledger(clock)
    _fill(led, GEMMA, 30)
    assert led.can_afford(GEMMA, 100) is Verdict.RPM


def test_qua_mot_phut_thi_rpm_hoi_lai(clock):
    led = _ledger(clock)
    _fill(led, GEMMA, 30)
    clock.advance(seconds=61)
    assert led.can_afford(GEMMA, 100) is Verdict.OK


def test_cham_tran_tpm_thi_chan(clock):
    led = _ledger(clock)
    _fill(led, GEMMA, 1, total_tokens=15_900)
    assert led.can_afford(GEMMA, 200) is Verdict.TPM


def test_he_so_token_cua_provider_duoc_ap_dung(clock):
    """Groq đếm nặng 2.3×. 3_000 token thô → ~6_900 ước lượng, vẫn lọt 8K.
    Nhưng 3_500 thô → ~8_050, vượt trần. Không nhân hệ số thì cả hai đều lọt."""
    led = _ledger(clock)
    assert led.can_afford(GROQ, 3_000) is Verdict.OK
    assert led.can_afford(GROQ, 3_500) is Verdict.TPM


def test_cham_tran_rpd_thi_chan(clock):
    led = _ledger(clock)
    _fill(led, GROQ, 1_000)
    clock.advance(hours=2)          # RPM/TPM đã hồi, RPD thì chưa
    assert led.can_afford(GROQ, 10) is Verdict.RPD


def test_cua_so_truot_24h_chu_khong_phai_ngay_lich(clock):
    led = _ledger(clock)
    _fill(led, GROQ, 1_000)
    clock.advance(hours=23)
    assert led.can_afford(GROQ, 10) is Verdict.RPD
    clock.advance(hours=2)          # tổng 25h — bản ghi cũ rơi khỏi cửa sổ
    assert led.can_afford(GROQ, 10) is Verdict.OK


def test_rpd_duoc_bao_truoc_tpm(clock):
    """Cạn ngân sách ngày mà báo "tpm_exhausted" là gợi ý sai — nó khiến người
    đọc tưởng chờ một phút là xong."""
    led = _ledger(clock)
    _fill(led, GROQ, 1_000, total_tokens=7_999)
    assert led.can_afford(GROQ, 10_000) is Verdict.RPD


def test_quota_scope_account_gop_chung_moi_model_openrouter(clock):
    """OR_LING và OR_NEMO là hai model khác nhau nhưng chung một ví 50/ngày."""
    led = _ledger(clock)
    _fill(led, OR_LING, 50)
    assert led.can_afford(OR_NEMO, 10) is Verdict.RPD


def test_quota_scope_model_khong_gop_chung(clock):
    """Ngược lại: gemma-4-26b cạn không kéo theo groq-gpt-oss-20b."""
    led = _ledger(clock)
    _fill(led, GEMMA, 30)
    assert led.can_afford(GROQ, 10) is Verdict.OK


def test_cooldown_chan_roi_tu_het_han(clock):
    led = _ledger(clock)
    led.cooldown(GEMMA, seconds=30)
    assert led.can_afford(GEMMA, 10) is Verdict.COOLDOWN
    clock.advance(seconds=31)
    assert led.can_afford(GEMMA, 10) is Verdict.OK


def test_cooldown_chi_anh_huong_dung_alias_do(clock):
    led = _ledger(clock)
    led.cooldown(GEMMA, seconds=30)
    assert led.can_afford(GROQ, 10) is Verdict.OK


def test_kho_sap_thi_FAIL_OPEN_cho_goi(clock):
    """NGƯỢC với write_gate.py (fail-closed) và cố ý như vậy: write_gate chặn
    thao tác ghi ERP không hoàn tác được; ngân sách chỉ chắn một cái 429 tự
    lành mà chuỗi fallback đã xử lý. Fail-closed ở đây là đánh sập cả hệ thống
    để bảo vệ một hạn mức miễn phí."""
    led = _ledger(clock, store=ExplodingStore())
    assert led.can_afford(GEMMA, 100) is Verdict.OK


def test_kho_sap_luc_ghi_khong_lam_vo_luot_goi(clock):
    led = _ledger(clock, store=ExplodingStore())
    led.record(GEMMA, prompt_tokens=1, completion_tokens=1, total_tokens=2)


def test_han_muc_None_thi_khong_kiem(clock):
    """OpenRouter không công bố rpm/tpm — None nghĩa là không áp trần đó."""
    led = _ledger(clock)
    assert OR_LING.rpm is None and OR_LING.tpm is None
    assert led.can_afford(OR_LING, 10_000_000) is Verdict.OK


def test_record_dung_total_tokens_khong_phai_prompt_cong_completion(clock):
    """Gemma: p=11, c=36, total=337. Cộng p+c đếm thiếu 7 lần."""
    store = InMemoryUsageStore()
    led = _ledger(clock, store=store)
    led.record(GEMMA, prompt_tokens=11, completion_tokens=36, total_tokens=337)
    got = store.usage_since(since=clock() , alias="gemma-4-26b")
    assert got.total_tokens == 337
