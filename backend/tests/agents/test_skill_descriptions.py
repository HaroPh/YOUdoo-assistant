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
