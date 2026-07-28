import pytest
from langchain_openai import ChatOpenAI

from src.llm.catalog import spec_for
from src.llm.providers import BASE_URLS, ENV_KEYS, client_for, strip_thought

GEMMA = spec_for("gemma-4-26b")            # emits_thought_tags=True
GEMINI = spec_for("gemini-3.5-flash-lite")  # emits_thought_tags=False
GROQ = spec_for("groq-gpt-oss-20b")
OR_LING = spec_for("or-ling")


# ─── strip_thought ──────────────────────────────────────────────────────────

def test_go_khoi_thought_va_giu_lai_cau_tra_loi():
    raw = "<thought>Người dùng chào hỏi.</thought>Chào bạn! Mình khỏe."
    assert strip_thought(raw) == "Chào bạn! Mình khỏe."


def test_khong_co_the_thi_giu_nguyen():
    assert strip_thought("Chào bạn!") == "Chào bạn!"


def test_thought_nhieu_dong():
    raw = "<thought>dòng 1\ndòng 2\ndòng 3</thought>\n\nCâu trả lời."
    assert strip_thought(raw) == "Câu trả lời."


def test_thieu_the_dong_thi_tra_ve_RONG():
    """Bị cắt giữa chừng. Trả nửa khối suy nghĩ cho người dùng còn tệ hơn trả
    rỗng — rỗng thì node gọi degrade về SAFE_MSG, đúng đường đã có."""
    assert strip_thought("<thought>đang nghĩ dở thì bị cắt") == ""


def test_None_va_chuoi_rong_khong_lam_no_vo():
    assert strip_thought(None) == ""
    assert strip_thought("") == ""


def test_chi_toan_thought_thi_tra_ve_rong():
    assert strip_thought("<thought>nghĩ xong nhưng quên trả lời</thought>") == ""


def test_the_dong_o_giua_thi_chi_go_phan_dau():
    """Chỉ khối MỞ ĐẦU là suy nghĩ. Chuỗi giống thẻ nằm trong câu trả lời thật
    (ví dụ người dùng hỏi về chính cú pháp đó) không được đụng tới."""
    raw = "<thought>nghĩ</thought>Thẻ <thought> dùng để đánh dấu suy nghĩ."
    assert strip_thought(raw) == "Thẻ <thought> dùng để đánh dấu suy nghĩ."


def test_khoang_trang_dau_truoc_the_van_xu_ly_duoc():
    assert strip_thought("\n  <thought>nghĩ</thought>Xong.") == "Xong."


# ─── client_for ─────────────────────────────────────────────────────────────
# Google → ChatGoogleGenerativeAI (spike Task 1); Groq/OpenRouter → ChatOpenAI.
# Hai lớp có TÊN TRƯỜNG khác nhau cho cùng khái niệm (đã xác nhận từ mã nguồn
# langchain_google_genai._common, không suy đoán): ChatOpenAI dùng
# `model_name`/`openai_api_base`/`request_timeout`/`max_tokens`;
# ChatGoogleGenerativeAI dùng `model`/(không có base_url)/`timeout`/
# `max_output_tokens`. Test dưới đây test ĐÚNG trường của ĐÚNG lớp — không
# giả định hai lớp đối xứng.

def test_google_dung_ChatGoogleGenerativeAI_groq_openrouter_dung_ChatOpenAI(monkeypatch):
    """Đây là hành vi CHÍNH mà quyết định spike Task 1 đòi hỏi — nếu test này
    xanh mà client_for() vẫn trả ChatOpenAI cho Google, coi như chưa làm."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert isinstance(client_for(GEMINI), ChatGoogleGenerativeAI)
    assert isinstance(client_for(GEMMA), ChatGoogleGenerativeAI)
    assert isinstance(client_for(GROQ), ChatOpenAI)
    assert isinstance(client_for(OR_LING), ChatOpenAI)


def test_moi_provider_co_ten_bien_moi_truong_rieng():
    from src.llm.catalog import CATALOG
    for spec in CATALOG.values():
        assert spec.provider in ENV_KEYS


def test_groq_va_openrouter_co_base_url_google_thi_khong():
    """Google không có base_url — ChatGoogleGenerativeAI tự quản endpoint."""
    assert "groq" in BASE_URLS and "openrouter" in BASE_URLS
    assert "google" not in BASE_URLS


def test_client_google_dung_model_id_goc_qua_truong_model(monkeypatch):
    """ChatGoogleGenerativeAI dùng trường `model`, KHÔNG phải `model_name`."""
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    client = client_for(GEMMA)
    assert client.model == "gemma-4-26b-a4b-it"   # KHÔNG phải "gemma-4-26b"


def test_client_groq_dung_model_id_goc_qua_truong_model_name(monkeypatch):
    """ChatOpenAI dùng trường `model_name` (alias `model` lúc khởi tạo)."""
    monkeypatch.setenv("GROQ_API_KEY", "k")
    client = client_for(GROQ)
    assert client.model_name == "openai/gpt-oss-20b"


def test_client_groq_openrouter_lay_dung_base_url_theo_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert "groq.com" in str(client_for(GROQ).openai_api_base)
    assert "openrouter.ai" in str(client_for(OR_LING).openai_api_base)


def test_client_groq_lay_timeout_va_max_tokens_tu_catalog(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    client = client_for(GROQ)
    assert client.request_timeout == GROQ.timeout_s
    assert client.max_tokens == GROQ.max_output_tokens


def test_client_google_lay_timeout_va_max_output_tokens_tu_catalog(monkeypatch):
    """Field khác tên (max_output_tokens, không phải max_tokens) nhưng PHẢI
    nhận đúng giá trị từ catalog — đây chính là chỗ dễ gõ nhầm tên field."""
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    client = client_for(GEMINI)
    assert client.timeout == GEMINI.timeout_s
    assert client.max_output_tokens == GEMINI.max_output_tokens


def test_thieu_bien_moi_truong_thi_chet_ngay_voi_thong_bao_ro(monkeypatch):
    """Lỗi cấu hình lệch lạc phải chết ngay và ồn ào (spec §6). Kiểm cả hai
    nhánh client — RuntimeError phải ném TRƯỚC khi chạm tới constructor nào."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        client_for(GROQ)

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        client_for(GEMINI)


def test_temperature_luon_bang_khong_ca_hai_loai_client(monkeypatch):
    """Khớp repo nguồn: mọi vai đều temperature=0 để đầu ra tái lập được.
    ChatGoogleGenerativeAI cũng có trường `temperature` (khác mặc định 0.7 của
    thư viện) nên phải truyền tường minh, không dựa vào default."""
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert client_for(GEMINI).temperature == 0
    assert client_for(GROQ).temperature == 0
