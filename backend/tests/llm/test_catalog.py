import pytest

from src.llm.catalog import (CATALOG, CHAINS, TOKEN_MOI_LUOT_UOC,
                             nhip_toi_thieu, HEAVY_ROLES, HEAVY_TPM_FLOOR,
                             MODEL_CHON_DUOC, ROLES, RPD_SAN_PHUC_VU,
                             TOOL_ROLES, chain_for, spec_for)


def test_moi_alias_trong_chain_deu_ton_tai_trong_catalog():
    """Bất biến #2 — chuỗi trỏ tới alias lạ là lỗi cấu hình, phải chết sớm."""
    for role, aliases in CHAINS.items():
        for alias in aliases:
            assert alias in CATALOG, f"chuỗi {role!r} trỏ tới alias lạ: {alias!r}"


def test_khong_hai_mat_xich_nao_trong_mot_chuoi_chung_upstream():
    """Bất biến #1 — fallback phải vượt qua ranh giới miền lỗi thật.

    Đo 2026-07-28: google/gemma-4-31b-it:free trên OpenRouter trả 429 kèm
    provider_name "Google AI Studio" — nó proxy ngược về chính Google. Rơi từ
    Gemini xuống đó là rơi vào lại chỗ vừa ngã.
    """
    for role, aliases in CHAINS.items():
        upstreams = [CATALOG[a].upstream for a in aliases]
        assert len(upstreams) == len(set(upstreams)), (
            f"chuỗi {role!r} có hai mắt xích chung upstream: {upstreams}")


def test_vai_nang_chi_dung_model_du_tpm():
    """Bất biến #3 — một lượt synthesis có RAG tốn ~3–4K token input."""
    for role in HEAVY_ROLES:
        for spec in chain_for(role):
            assert spec.tpm is None or spec.tpm >= HEAVY_TPM_FLOOR, (
                f"{spec.alias!r} có tpm={spec.tpm} < {HEAVY_TPM_FLOOR}, "
                f"không gánh nổi vai nặng {role!r}")


def test_vai_can_tool_chi_dung_model_ho_tro_tool():
    """Bất biến #4 — vai gọi tool mà trúng model không tool-call thì hỏng câm."""
    for role in TOOL_ROLES:
        for spec in chain_for(role):
            assert spec.supports_tools, (
                f"{spec.alias!r} không hỗ trợ tool nhưng nằm trong chuỗi "
                f"của vai {role!r}")


def test_moi_vai_deu_co_chuoi_va_khong_co_chuoi_thua():
    assert set(CHAINS) == set(ROLES)


def test_khong_co_model_openrouter_nao_co_upstream_google():
    """Chốt cứng phát hiện 2026-07-28 ở tầng dữ liệu, không chỉ ở chuỗi."""
    for spec in CATALOG.values():
        if spec.provider == "openrouter":
            assert spec.upstream != "google", (
                f"{spec.alias!r} proxy về Google — không được vào catalog")


def test_quota_scope_chi_nhan_hai_gia_tri_hop_le():
    for spec in CATALOG.values():
        assert spec.quota_scope in ("model", "account")


def test_openrouter_dung_quota_scope_account():
    """Hạn mức free của OpenRouter tính theo TÀI KHOẢN, dùng chung mọi model."""
    for spec in CATALOG.values():
        if spec.provider == "openrouter":
            assert spec.quota_scope == "account"


def test_alias_khop_voi_khoa_trong_catalog():
    for key, spec in CATALOG.items():
        assert spec.alias == key


def test_spec_for_nem_loi_voi_alias_la():
    with pytest.raises(KeyError):
        spec_for("model-khong-ton-tai")


def test_chain_for_nem_loi_voi_vai_la():
    with pytest.raises(KeyError):
        chain_for("vai-khong-ton-tai")


def test_chain_for_tra_ve_dung_thu_tu():
    specs = chain_for("read")
    assert [s.alias for s in specs] == list(CHAINS["read"])


def test_hai_mat_xich_dau_phai_du_ganh_mot_ngay():
    """Bất biến #5 — hai vị trí đầu của mọi chuỗi phải có rpd đủ một ngày.

    Kiểm với CẢ `prefer=None` LẪN từng model trong dropdown, vì `prefer` đổi
    thứ tự: mắt xích 1 cũ tụt xuống vị trí 2, tức chỗ MỌI cú tụt đi qua. Chỉ
    kiểm bảng CHAINS tĩnh là mù đúng với đường mà người dùng thật đi.

    Sinh ra từ lỗi 2026-08-21: `gemini-3.5-flash` (rpd=20) ở mắt xích 1 của
    `chitchat`; người dùng chọn 3.5-flash-lite (đã cạn ngày) thì tán gẫu được
    phục vụ bằng model chết sau ~20 lượt.
    """
    for prefer in (None, *MODEL_CHON_DUOC):
        for role in CHAINS:
            for vi_tri, spec in enumerate(chain_for(role, prefer)[:2]):
                assert spec.rpd is None or spec.rpd >= RPD_SAN_PHUC_VU, (
                    f"chuỗi {role!r} (prefer={prefer!r}) có {spec.alias!r} "
                    f"rpd={spec.rpd} < {RPD_SAN_PHUC_VU} ở vị trí {vi_tri + 1}")


def test_chitchat_khong_con_dung_model_rpd_20():
    """Chốt cứng bản sửa 2026-08-21 ở tầng dữ liệu.

    Bất biến #5 đã cấm rồi, nhưng nó cấm theo NGƯỠNG; nếu ai đó nới ngưỡng thì
    lỗi cũ quay lại im lặng. Đây là mỏ neo cho đúng một model đã gây sự cố.
    """
    assert "gemini-3.5-flash" not in CHAINS["chitchat"]
    # Entry vẫn còn trong CATALOG — cố ý, để `--model gemini-3.5-flash` ghim đo
    # được. Bất biến #5 là thứ giữ cho việc giữ entry này an toàn.
    assert "gemini-3.5-flash" in CATALOG


def test_moi_vai_bind_tool_deu_co_du_phong_NGOAI_GOOGLE():
    """Bất biến #6 — mỗi vai bind tool phải có ít nhất một mắt xích NGOÀI Google
    và mắt xích đó phải `supports_tools`.

    Vì sao đòi ngoài-Google: một mắt xích dự phòng chỉ đáng gọi là dự phòng nếu
    nó mua được đường thoát khi upstream chính ngã. Hai model Gemini dùng chung
    hạ tầng, chung hồ hạn mức theo project; xếp chúng cạnh nhau thì chuỗi dài
    ra mà miền lỗi không rộng thêm chút nào. Đây chính là lý do
    `gemini-3.5-flash` (rpd 20) BỊ LOẠI khỏi vị trí này ngày 2026-08-22 dù nó
    sẵn có và không tốn gì thêm.

    ⚠️ Bản đầu của test này còn đòi thêm `tpm >= 8_040`, lấy từ một phép đo bind
    cả 35 tool MCP vào LLM. Ngưỡng đó ĐÃ BỊ GỠ: production không gửi payload
    đó (xem chú thích "Payload THẬT" trong catalog.py). Giữ lại một con số rút
    từ hình dạng sai còn tệ hơn không có con số nào — nó biến một phép đo nhầm
    thành luật.
    """
    for vai in sorted(TOOL_ROLES):
        du_phong = [a for a in CHAINS[vai]
                    if CATALOG[a].upstream != "google" and CATALOG[a].supports_tools]
        assert du_phong, (
            f"vai {vai!r} bind tool nhưng cả chuỗi nằm trong một miền lỗi: "
            f"{[(a, CATALOG[a].upstream) for a in CHAINS[vai]]}")


def test_nhip_lay_tran_CHAT_HON_giua_rpm_va_tpm():
    """Bản trước chỉ xét rpm. Đúng với Gemini (tpm rộng thênh thang) nhưng SAI
    HẲN với Groq, nơi tpm mới là ràng buộc — và cái sai đó tạo ra một lượt đo
    có `acc` trông như thật (0,5556) trong khi 23/54 ca lỗi."""
    from dataclasses import replace

    goc = CATALOG["gemini-3.5-flash-lite"]
    rpm_chat = replace(goc, rpm=15, tpm=10_000_000)     # rpm là ràng buộc
    tpm_chat = replace(goc, rpm=1_000, tpm=8_000)       # tpm là ràng buộc

    assert nhip_toi_thieu(rpm_chat) == pytest.approx((60 / 15) * 1.2)
    assert nhip_toi_thieu(tpm_chat) == pytest.approx(
        (60 / (8_000 / TOKEN_MOI_LUOT_UOC)) * 1.2)
    assert nhip_toi_thieu(tpm_chat) > nhip_toi_thieu(rpm_chat)


def test_nhip_cua_gemini_KHONG_doi_sau_ban_sua():
    """Đối chứng chống hồi quy: bản sửa chỉ được LÀM CHẬM chỗ đang sai, không
    được đụng chỗ đang đúng. 4,8s là con số mọi baseline Gemini đã chạy với."""
    assert nhip_toi_thieu(CATALOG["gemini-3.1-flash-lite"]) == pytest.approx(4.8)


def test_nhip_khop_voi_so_DO_THAT_tren_groq():
    """Đo 2026-08-22: một lượt `intent` trên groq-gpt-oss-120b tốn 857 token.
    Trần 8 000/phút ⇒ tối đa ~9 lượt/phút ⇒ nhịp tối thiểu ~6,4s. Công thức
    phải cho ra một con số KHÔNG NHỎ HƠN mức đó."""
    assert nhip_toi_thieu(CATALOG["groq-gpt-oss-120b"]) >= 60 / (8_000 / 857)
