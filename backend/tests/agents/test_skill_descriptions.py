"""Mô tả skill chỉ được nói về MIỀN NGHIỆP VỤ.

Logic độ sâu (chạy đủ quy trình hay làm nhanh một bước) sống ở luật `depth`
trong INTENT_ROUTER_PROMPT. Để nó lẫn vào mô tả là tái lập đúng lỗi mà đợt
2026-08-16 đi sửa: một trường phải trả lời hai câu hỏi.
"""
import pytest

from src.agents.skill_loader import load_skill_specs

# Cụm chỉ độ sâu — không cụm nào được xuất hiện trong mô tả miền.
CUM_DO_SAU = ("NGẮN GỌN một bước", "một bước", "planner tier-1")


@pytest.mark.parametrize("ten", ["nhap-kho", "giao-hang", "bao-gia-chiet-khau"])
def test_mo_ta_khong_con_logic_do_sau(ten):
    spec = next(s for s in load_skill_specs() if s.name == ten)
    for cum in CUM_DO_SAU:
        assert cum not in spec.description, f"{ten} còn cụm độ sâu: {cum!r}"


@pytest.mark.parametrize("ten", ["nhap-kho", "giao-hang", "bao-gia-chiet-khau"])
def test_mo_ta_van_giu_ve_loai_tru_cau_hoi(ten):
    """Nới nhận diện KHÔNG được đánh đổi bằng hijack: mô tả vẫn phải nói rõ
    câu hỏi-VỀ-quy-trình không thuộc miền này."""
    spec = next(s for s in load_skill_specs() if s.name == ten)
    assert "KHÔNG chọn khi" in spec.description


def test_bao_gia_khong_con_doi_chu_chiet_khau():
    """Mô tả cũ của bao-gia-chiet-khau mỏng hơn hẳn hai skill kia và đòi khái
    niệm "chiết khấu" — đo 2026-08-16: "Wood Corner mua 10 Desk Pad, tính giá
    cho khách này giúp tôi" rơi sang erp_read, tức không tạo báo giá và không
    áp chính sách chiết khấu nào."""
    spec = next(s for s in load_skill_specs()
                if s.name == "bao-gia-chiet-khau")
    assert "tính giá bán cho một khách hàng cụ thể" in spec.description


# Mốc "đặc trưng phân biệt": mô tả phải nói THẲNG rằng nêu chứng từ cụ thể là
# muốn LÀM việc, thay vì bắt model tự suy ra điều đó.
MOC_CHUNG_TU = {
    "nhap-kho": "MÃ ĐƠN MUA",
    "giao-hang": "MÃ ĐƠN BÁN",
    "bao-gia-chiet-khau": "TÊN KHÁCH",
}

# Cụm mà vế loại trừ TỪNG mở đầu bằng, và một yêu cầu thi hành hợp lệ cũng mở
# đầu y hệt — nguồn gốc ca hỏng bền bỉ nhất repo.
CUM_VA_CHAM = {
    "nhap-kho": "hỏi quy trình nhập kho",
    "giao-hang": "hỏi quy trình giao hàng",
}


@pytest.mark.parametrize("ten", ["nhap-kho", "giao-hang", "bao-gia-chiet-khau"])
def test_mo_ta_neu_thang_dac_trung_phan_biet(ten):
    """Đo 2026-08-17 (spike sau khi đợt tách miền/độ sâu lên main): mô tả bắt
    model TỰ SUY RA rằng có mã chứng từ nghĩa là muốn thi hành, và nó KHÔNG suy
    — nó khớp mẫu câu mở đầu. Nêu thẳng đặc trưng này là thứ đưa ca hồi quy
    2026-07-16 về đúng sau 4 lần sửa thất bại."""
    spec = next(s for s in load_skill_specs() if s.name == ten)
    assert MOC_CHUNG_TU[ten] in spec.description


@pytest.mark.parametrize("ten", sorted(CUM_VA_CHAM))
def test_ve_loai_tru_khong_trung_mo_dau_voi_cau_thi_hanh(ten):
    """Gốc rễ ca "quy trình nhập kho cho đơn mua P00021" (hỏng từ 2026-07-16,
    sống sót qua 2 model và 3 lần viết lại mô tả): vế loại trừ chứa "chỉ hỏi
    quy trình nhập kho gồm những gì", mà câu THI HÀNH hợp lệ ở trên lại mở đầu
    bằng đúng cụm "quy trình nhập kho" đó.

    Đo được 2026-08-17, giữ nguyên ngữ nghĩa chỉ đổi trật tự từ:
      "quy trình nhập kho cho đơn mua P00021"        -> rag/none      ✗
      "thực hiện quy trình nhập kho cho đơn mua P00021" -> nhap-kho/full_sop ✓
      "đơn mua P00021 cần làm theo quy trình nhập kho"  -> nhap-kho/full_sop ✓

    Vế loại trừ phải mô tả bằng ĐẶC TRƯNG (không nêu chứng từ nào) chứ không
    chép lại cụm mà câu thi hành cũng dùng."""
    spec = next(s for s in load_skill_specs() if s.name == ten)
    assert CUM_VA_CHAM[ten] not in spec.description


def test_khong_log_missing_negative_clause_warning(caplog):
    """Loader sử dụng NEGATIVE_CLAUSE_MARKERS để chấp nhận cả "KHÔNG dùng khi"
    và "KHÔNG chọn khi" — chỉ đưa ra cảnh báo nếu KHÔNG MỘT cụm nào có.
    Bài test gọi load_skill_specs() thật (không mock) và xác nhận ba skill
    hiện tại KHÔNG trigger warning MISSING_NEGATIVE_WARNING."""
    import logging
    with caplog.at_level(logging.WARNING):
        specs = load_skill_specs()

    # Xác nhận ba skill được nạp
    skill_names = {s.name for s in specs}
    assert {"nhap-kho", "giao-hang", "bao-gia-chiet-khau"}.issubset(skill_names)

    # Xác nhận không có warning nào chứa skill name và "KHÔNG" cho ba skill
    for skill_name in ("nhap-kho", "giao-hang", "bao-gia-chiet-khau"):
        matching_warnings = [
            r for r in caplog.records
            if r.levelno == logging.WARNING and skill_name in r.message
            and ("KHÔNG" in r.message and ("dùng khi" in r.message or "chọn khi" in r.message))
        ]
        assert not matching_warnings, \
            f"Unexpected MISSING_NEGATIVE_WARNING for {skill_name}: {[r.message for r in matching_warnings]}"
