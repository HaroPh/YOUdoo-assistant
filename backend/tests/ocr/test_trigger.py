"""`ocr/trigger.py` — quy tắc kích hoạt VLM. Số đo nền ở
`tools/calibrate_vlm_trigger_result.txt`; đây là hợp đồng của quy tắc."""
from src.ocr import trigger

_DVT7 = ("TRUNG TÂM ĐÀO TẠO NGHIỆP VỤ Mẫu B01/BCTC\nBáo cáo tình hình tài chính (Ban hành theo TT số "
         "107/2017/TT-BTC\nSTT Chỉ tiêu Mã sô minh Số cuôi năm Sô đâu năm\n" + "Pap s\n" * 20)
_PGI8 = "TONG CÔNG TY CO PHAN BẢO HIẾM PETROLIMEX\nMẫu số B 01-DNPNT\nBANG CAN DOI KE TOÁN\nTai ngay\n" + "x\n" * 20
_NOTES = ("CÔNG TY CỔ PHẦN ĐẦU TƯ\nBÁO CÁO TÀI CHÍNH HỢP NHẤT GIỮA NIÊN ĐỘ\n"
          "Bản thuyết minh Báo cáo tài chính hợp nhất giữa niên độ (tiếp theo)\n"
          "Lưu chuyển tiền thuần từ hoạt động kinh doanh\n" + "x\n" * 20)
_MUC_LUC = ("MỤC LỤC\nBáo cáo tình hình tài chính 5\nBáo cáo kết quả hoạt động kinh doanh 7\n"
            "Báo cáo lưu chuyển tiền tệ 9\n" + "x\n" * 20)


def test_title_kinds_doc_dung_tieu_de_du_than_trang_rac():
    assert trigger.title_kinds(_DVT7) == ["B01"]
    assert trigger.statement_kind(_PGI8) == "B01"


def test_trang_thuyet_minh_khong_kich_hoat_du_nhac_ten_bao_cao():
    assert trigger.title_kinds(_NOTES) == []


def test_muc_luc_nhac_ca_ba_bao_cao_la_van_xuoi():
    assert len(trigger.title_kinds(_MUC_LUC)) == 3
    assert trigger.statement_kind(_MUC_LUC) is None
    qd = trigger.decide(_MUC_LUC, [])
    assert not qd.call_vlm and "3 loại" in qd.reason


def test_tieu_de_chi_xet_phan_dau_trang():
    text = "x\n" * 60 + "Báo cáo tình hình tài chính\n"
    assert trigger.title_kinds(text) == []


def test_decide_goi_vlm_khi_khong_dung_duoc_cot_ma_so():
    qd = trigger.decide(_DVT7, [["Pap s", "", "25900585)"]] * 5)
    assert qd.kind == "B01" and qd.call_vlm and "không dựng được cột mã số" in qd.reason


def test_decide_khong_goi_khi_so_hoc_vouch():
    from tests.ocr.test_grid_rows_assess import _tr7_grid
    qd = trigger.decide(_DVT7, _tr7_grid())
    assert qd.kind == "B01" and not qd.call_vlm and qd.tesseract is not None
    assert "vouch" in qd.reason


def test_decide_goi_khi_co_cot_ma_so_nhung_so_hoc_khong_vouch():
    from tests.ocr.test_grid_rows_assess import _tr7_grid
    grid = _tr7_grid()
    for r in grid:
        if r[3] == "11":
            r[5] = "8.812.478.001"
    qd = trigger.decide(_DVT7, grid)
    assert qd.call_vlm and "FAIL 1" in qd.reason or "FAIL 2" in qd.reason
