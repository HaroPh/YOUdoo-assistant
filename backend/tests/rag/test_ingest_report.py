# backend/tests/rag/test_ingest_report.py
"""Kiểu kết quả nạp — spec 2026-08-29 mục 4.

Vì sao có tệp này: `_ingest_file` từng trả dict ba số đếm, nên tệp đuôi lạ
trả toàn 0 và KHÔNG phân biệt được với "thư mục không có gì để làm". Ba
trạng thái phải là ba thứ đọc được, không phải ba con số.
"""
from src.rag.ingest_report import IngestReport, Rejection, Warning


def test_bao_cao_rong_la_ok():
    r = IngestReport()
    assert r.ok is True
    assert r.ingested == 0 and r.unchanged == 0 and r.chunks == 0


def test_co_tep_bi_tu_choi_thi_khong_ok():
    r = IngestReport(rejected=[Rejection("a.doc", "chưa hỗ trợ")])
    assert r.ok is False


def test_merge_cong_don_ca_so_dem_lan_danh_sach_tu_choi():
    a = IngestReport(ingested=1, chunks=5)
    b = IngestReport(unchanged=2, chunks=0,
                     rejected=[Rejection("x.ppt", "không có bộ chuyển đổi")])
    a.merge(b)
    assert (a.ingested, a.unchanged, a.chunks) == (1, 2, 5)
    assert [x.path for x in a.rejected] == ["x.ppt"]
    assert a.ok is False


def test_merge_khong_dung_chung_danh_sach_giua_hai_bao_cao():
    """Bẫy mutable default: hai IngestReport() rỗng phải có list RIÊNG.
    Nếu dùng `rejected: list = []` làm default thì mọi báo cáo dùng chung
    một list và một lượt nạp hỏng sẽ nhiễm sang lượt sau."""
    a, b = IngestReport(), IngestReport()
    a.merge(IngestReport(rejected=[Rejection("p.doc", "lý do")]))
    assert a.rejected != []
    assert b.rejected == []


def test_render_goi_TEN_tung_tep_bi_tu_choi():
    """Báo cáo phải gọi TÊN tệp. Một con số tổng không cho người dùng biết
    tài liệu nào của họ vắng mặt khỏi corpus."""
    r = IngestReport(ingested=3, unchanged=1, chunks=40,
                     rejected=[Rejection("quy_che.doc", "không có LibreOffice"),
                               Rejection("slide.pptx", "parse ra rỗng")])
    out = r.render()
    assert "quy_che.doc" in out and "không có LibreOffice" in out
    assert "slide.pptx" in out and "parse ra rỗng" in out
    assert "3" in out and "1" in out


def test_canh_bao_khong_lam_bao_cao_that_bai():
    """Cảnh báo mức sheet KHÁC từ chối mức tệp: tệp vẫn nạp được."""
    r = IngestReport(ingested=1, warnings=[Warning("a.xlsx", "DM KH", "tiêu đề độ tin cậy thấp")])
    assert r.ok is True


def test_merge_cong_don_ca_canh_bao():
    a = IngestReport(ingested=1)
    b = IngestReport(warnings=[Warning("b.xlsx", "Sheet2", "lý do")])
    a.merge(b)
    assert [w.where for w in a.warnings] == ["Sheet2"]


def test_hai_bao_cao_rong_khong_dung_chung_danh_sach_canh_bao():
    a, b = IngestReport(), IngestReport()
    a.merge(IngestReport(warnings=[Warning("x", "y", "z")]))
    assert b.warnings == []


def test_render_goi_TEN_tung_cho_bi_canh_bao():
    r = IngestReport(ingested=2, warnings=[
        Warning("so_ke_toan.xlsm", "BK NHẬP - XUẤT", "nhãn cột trông như công thức"),
    ])
    out = r.render()
    assert "so_ke_toan.xlsm" in out
    assert "BK NHẬP - XUẤT" in out
    assert "nhãn cột trông như công thức" in out
