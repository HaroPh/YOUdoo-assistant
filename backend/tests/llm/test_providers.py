import pytest
from langchain_openai import ChatOpenAI

from dataclasses import replace

from src.llm.catalog import spec_for
from src.llm.providers import (BASE_URLS, ENV_KEYS, client_for, keys_for,
                               strip_thought)

GEMINI = spec_for("gemini-3.5-flash-lite")
GROQ = spec_for("groq-gpt-oss-120b")

# Spec TỔNG HỢP, cố ý KHÔNG lấy từ CATALOG. Sau đợt gom 2026-08-21, cả 4 model
# còn lại đều có `model_id == alias`, nên dùng chúng thì test "client phải gửi
# model_id GỐC chứ không phải alias" KHÔNG CÒN PHÂN BIỆT ĐƯỢC gì — nó xanh kể
# cả khi code gửi nhầm alias. Trước đó gemma-4-26b (model_id
# "gemma-4-26b-a4b-it") giữ vai đó.
KHAC_ID = replace(GEMINI, alias="alias-khac-id", model_id="id-goc-that")

# Spec TỔNG HỢP cho provider "openrouter": cả tầng OpenRouter bị xoá khỏi
# CATALOG 2026-08-21, nhưng NHÁNH CODE của nó trong client_for/BASE_URLS vẫn
# còn và vẫn phải đúng. Không có spec này thì nhánh đó thành mã không ai chạy.
OR = replace(GROQ, alias="or-tong-hop", model_id="nha/model:free",
             provider="openrouter", upstream="x")


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
    assert isinstance(client_for(KHAC_ID), ChatGoogleGenerativeAI)
    assert isinstance(client_for(GROQ), ChatOpenAI)
    assert isinstance(client_for(OR), ChatOpenAI)


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
    client = client_for(KHAC_ID)
    assert client.model == "id-goc-that"          # KHÔNG phải "alias-khac-id"


def test_client_groq_dung_model_id_goc_qua_truong_model_name(monkeypatch):
    """ChatOpenAI dùng trường `model_name` (alias `model` lúc khởi tạo)."""
    monkeypatch.setenv("GROQ_API_KEY", "k")
    client = client_for(GROQ)
    assert client.model_name == "openai/gpt-oss-120b"


def test_client_groq_openrouter_lay_dung_base_url_theo_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert "groq.com" in str(client_for(GROQ).openai_api_base)
    assert "openrouter.ai" in str(client_for(OR).openai_api_base)


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


# ─── max_retries: SDK KHÔNG được tự thử lại (2026-08-19) ────────────────────
# Đo được: gemini-3.1-flash-lite cạn trần NGÀY, một lượt gọi mất 33,4s với
# max_retries=6 (mặc định của thư viện) so với 0,4s với max_retries=0 — tức
# SDK bắn lại nhiều lần. Mỗi lần bắn lại ĐỐT THÊM hạn mức mà sổ ngân sách
# KHÔNG ghi (Router._finish chỉ chạy trên phản hồi thành công). Hệ quả đo
# được ngày 2026-08-19: llm_usage ghi 179 lượt/24h trong khi Google tính
# 500/500 cho cùng model.
#
# Ba lớp thử lại chồng nhau, và lớp SDK là lớp DUY NHẤT mù: nó không phân
# biệt 429-trần-phút (đáng chờ) với 429-trần-ngày (vô vọng), không biết còn
# mắt xích nào để tụt xuống, và không ghi sổ. Router (chuỗi fallback +
# cooldown) và run_resilient của evals đều biết cả ba thứ đó.
#
# Test chống TRÔI: mặc định của thư viện có thể đổi giữa các bản nâng cấp.
# Không chốt tường minh thì một lần `pip install -U` là hạn mức lại lặng lẽ
# bốc hơi.

@pytest.mark.parametrize("spec", [GEMINI, GROQ],
                         ids=lambda s: s.alias)
def test_client_khong_de_sdk_tu_thu_lai(monkeypatch, spec):
    monkeypatch.setenv(ENV_KEYS[spec.provider], "khoa-gia-cho-test")
    assert client_for(spec).max_retries == 0


# ─── keys_for: nguyên liệu cho việc xoay khoá (mục 7, 2026-08-21) ───────────
def test_keys_for_theo_thu_tu_uu_tien(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "a")
    monkeypatch.setenv("GOOGLE_API_KEY_2", "b")
    monkeypatch.setenv("GOOGLE_API_KEY_3", "c")
    assert keys_for("google") == ("a", "b", "c")


def test_keys_for_KHONG_dung_o_khoang_trong(monkeypatch):
    """Xoá một khoá hỏng rồi để lại `_2` trống là chuyện thường. Dừng ở chỗ
    trống đầu tiên sẽ IM LẶNG vứt khoá `_4` — lớp lỗi "danh sách khai báo hụt
    mà không ai biết"."""
    monkeypatch.setenv("GOOGLE_API_KEY", "a")
    monkeypatch.delenv("GOOGLE_API_KEY_2", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY_4", "d")
    assert keys_for("google") == ("a", "d")


def test_keys_for_khu_trung_giu_thu_tu(monkeypatch):
    """Dán nhầm cùng một khoá vào hai biến là lỗi sao chép rất dễ xảy ra; không
    khử thì mỗi lượt 429 phải trả giá hai lần cho cùng MỘT ví."""
    monkeypatch.setenv("GOOGLE_API_KEY", "a")
    monkeypatch.setenv("GOOGLE_API_KEY_2", "b")
    monkeypatch.setenv("GOOGLE_API_KEY_3", "a")
    assert keys_for("google") == ("a", "b")


def test_thieu_khoa_CHINH_nhung_con_du_phong_thi_van_chay(monkeypatch):
    """Quyết định có chủ đích (2026-08-21): `keys_for` trả "mọi khoá dùng
    được", nên vắng khoá chính mà còn `_2` thì dùng `_2`. Đây là thay đổi hành
    vi so với trước — trước đó vắng `GOOGLE_API_KEY` là chết ngay bất kể có gì
    khác. Giữ tường minh bằng test để không ai "sửa" nó về cũ mà không biết."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY_2", "b")
    assert keys_for("google") == ("b",)
    client_for(GEMINI)          # không được ném


def test_khong_khoa_NAO_thi_van_chet_ngay_va_neu_ten_bien_chinh(monkeypatch):
    """Bảo đảm "fail loud" cũ KHÔNG bị cơ chế xoay khoá làm loãng: không khoá
    nào thì vẫn chết ngay, và thông báo nêu tên biến CHÍNH (thứ người ta đi
    đặt), không phải một hậu tố."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    for i in range(2, 10):
        monkeypatch.delenv(f"GOOGLE_API_KEY_{i}", raising=False)
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        client_for(GEMINI)


def test_client_for_dung_dung_khoa_duoc_truyen(monkeypatch):
    """Nếu `api_key` không thật sự đi xuống client thì mọi test xoay khoá ở
    test_key_rotation.py đo bằng client giả sẽ xanh giả."""
    monkeypatch.setenv("GOOGLE_API_KEY", "khoa-chinh")
    # Tên trường KHÁC NHAU giữa hai loại client (google_api_key vs
    # openai_api_key) và cả hai là SecretStr — kiểm cả hai nhánh, vì xoay khoá
    # là cơ chế generic, không riêng Google.
    monkeypatch.setenv("GROQ_API_KEY", "groq-chinh")
    g = client_for(GEMINI, api_key="khoa-rieng")
    assert g.google_api_key.get_secret_value() == "khoa-rieng"
    assert client_for(GEMINI).google_api_key.get_secret_value() == "khoa-chinh"

    o = client_for(GROQ, api_key="groq-rieng")
    assert o.openai_api_key.get_secret_value() == "groq-rieng"
    assert client_for(GROQ).openai_api_key.get_secret_value() == "groq-chinh"
