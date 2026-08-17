"""Bộ ca sop_select phải đo cả MIỀN lẫn ĐỘ SÂU, và phải phủ được câu đời thật.

Trước 2026-08-16 bộ này mù với nhận diện ngữ nghĩa: mỗi skill đúng 1 ca dương
không-chữ-"quy trình", và cả ba ca đó vẫn nói rõ điều kiện ra.
"""
from evals.cases import SOP_SELECT_CASES

SOPS = {"giao-hang", "nhap-kho", "bao-gia-chiet-khau"}


def test_moi_ca_la_bo_ba():
    for ca in SOP_SELECT_CASES:
        assert len(ca) == 3, ca


def test_depth_ky_vong_luon_hop_le():
    from src.agents.routing import VALID_DEPTHS
    for _text, _dich, depth in SOP_SELECT_CASES:
        assert depth in VALID_DEPTHS, depth


def test_ca_hoi_ve_quy_trinh_thi_depth_la_none():
    """Câu hỏi-VỀ-quy-trình ⇒ sop rỗng ⇒ depth "none" (bất biến của
    parse_proposal). Đây cũng chính là nhóm hijack: depth khác "none" ở một ca
    `rag` nghĩa là router đã điền sop cho một câu tra cứu tài liệu.

    KHÔNG assert "mọi ca không-phải-SOP đều depth none": đích `erp_write` có
    thể đến từ (sop được điền, one_step) — đó là đúng thiết kế, không phải
    sop rỗng."""
    for text, dich, depth in SOP_SELECT_CASES:
        if dich == "rag":
            assert depth == "none", text


def test_du_ca_ngu_nghia():
    """Ca ngữ nghĩa = câu KHÔNG chứa "quy trình"/"SOP" mà router vẫn phải nhận
    ra MIỀN. Nhận diện miền thành công ⟺ depth != "none" (bất biến
    parse_proposal), BẤT KỂ đích cuối là node SOP hay erp_write — vì
    decide_route đưa one_step về erp_write.

    Đây là nhóm bộ đo cũ thiếu hẳn: trước 2026-08-16 mỗi skill đúng 1 ca, và
    cả ba ca đó vẫn nói rõ điều kiện ra."""
    ngu_nghia = [t for t, _dich, d in SOP_SELECT_CASES
                 if d != "none"
                 and "quy trình" not in t.lower()
                 and "sop" not in t.lower()]
    assert len(ngu_nghia) >= 6, ngu_nghia


def test_co_ca_unsure():
    assert any(d == "unsure" for _t, _dich, d in SOP_SELECT_CASES)


def test_moi_skill_co_ca_full_sop_lan_one_step():
    for sop in SOPS:
        depths = {d for _t, dich, d in SOP_SELECT_CASES if dich == sop}
        assert "full_sop" in depths, sop
    assert any(d == "one_step" for _t, _dich, d in SOP_SELECT_CASES)


# ── hijack: đo HƯỚNG NGUY HIỂM, không phải "đích cuối có phải node SOP không" ──


def test_hijack_khong_dem_ca_hoi_lai_do_sau():
    """DƯƠNG TÍNH GIẢ đo được 2026-08-17 (spike biến thể prompt): một ca kỳ
    vọng `clarify_depth` mà chạy thẳng SOP của ĐÚNG miền đó bị công thức cũ
    (`expected not in valid_sops and got in valid_sops`) đếm là hijack.

    Không có gì bị chiếm quyền cả: người dùng THẬT SỰ muốn làm việc trong miền
    đó, lỗi chỉ là đáng ra phải hỏi độ sâu trước. Đếm nó là hijack làm hỏng
    đúng con số mà báo cáo nào cũng trích như chỉ số an toàn."""
    from evals.run_eval import _is_hijack
    assert _is_hijack("clarify_depth", "nhap-kho") is False


def test_hijack_dem_cau_tra_cuu_bi_dien_sop_du_di_duong_nao():
    """ĐIỂM MÙ của công thức cũ: câu tra cứu tài liệu bị router điền `sop` rồi
    `decide_route` đưa sang `erp_write` (vì depth=one_step) thì `got` KHÔNG
    phải tên node SOP nên công thức cũ đếm 0.

    Chính đợt tách miền/độ sâu làm `sop` được điền nhiều hơn hẳn, tức đúng lúc
    vùng phơi nhiễm rộng ra thì độ phủ của bộ đếm lại hẹp đi. Hướng nguy hiểm
    thật là "câu KHÔNG phải yêu cầu làm việc mà bị gán một miền", bất kể sau đó
    lớp phủ quyết tất định có cứu được hay không."""
    from evals.run_eval import _is_hijack
    assert _is_hijack("rag", "nhap-kho") is True
    assert _is_hijack("rag", None) is False


def test_hijack_khong_dem_ca_yeu_cau_lam_viec():
    from evals.run_eval import _is_hijack
    assert _is_hijack("erp_write", "nhap-kho") is False
    assert _is_hijack("nhap-kho", "nhap-kho") is False
