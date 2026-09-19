"""Tests for ocr.document — tầng tài liệu (trang 1 PDF → ảnh → vùng có kiểu + đệm)."""

import os
import pytest

from src.ocr import document
from src.ocr.engine import OcrResult, OcrWord


def test_artifact_version_da_len_4_va_page_mang_rotation():
    """Hình dạng đổi (3: vùng thêm `grid`; 4: trang thêm `rotation` + đọc ở hướng
    OSD) thì ARTIFACT_VERSION PHẢI tăng, nếu không đệm cũ sẽ được đọc lại dưới
    hình dạng mới và sai âm thầm."""
    assert document.ARTIFACT_VERSION == 4
    r = document.Region(kind="text", text="x", mean_conf=90.0,
                        bbox=(0, 0, 10, 10))
    assert r.grid == []
    assert r.grid_error is None
    assert document.PageRead(page=1, regions=[r], mean_conf=90.0, tu_dem=False).rotation == 0


def test_van_tay_doi_khi_DPI_doi(monkeypatch):
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.4.0")
    a = document.config_fingerprint(dpi=200)
    b = document.config_fingerprint(dpi=300)
    assert a != b


def test_van_tay_doi_khi_PHIEN_BAN_TESSERACT_doi(monkeypatch):
    # Đây là nửa mà `convert.py` đang THIẾU: nó khoá đệm chỉ theo hash tệp, nên
    # đổi tham số công cụ sẽ dùng lại bản cũ mà không ai biết (spec §7).
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.4.0")
    a = document.config_fingerprint()
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.5.0")
    b = document.config_fingerprint()
    assert a != b


def test_van_tay_on_dinh_khi_khong_doi_gi(monkeypatch):
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.4.0")
    assert document.config_fingerprint() == document.config_fingerprint()


def test_van_tay_doi_khi_OCR_PSM_bi_gan_luc_chay(monkeypatch):
    """Nếu task sau đổi engine.OCR_PSM lúc chạy (để đo lại), vân tay PHẢI
    thay đổi. Nếu không thì đệm sẽ trả kết quả PSM-6 cũ mà không ai biết —
    lỗi giống như convert.py đang mắc."""
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.4.0")
    a = document.config_fingerprint()
    # Giả lập task sau đổi OCR_PSM
    monkeypatch.setattr(document.engine, "OCR_PSM", 3)
    b = document.config_fingerprint()
    assert a != b, "đổi OCR_PSM lúc chạy phải làm vân tay đổi"


def test_van_tay_doi_khi_OCR_LANG_bi_gan_luc_chay(monkeypatch):
    """Tương tự với OCR_LANG."""
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.4.0")
    a = document.config_fingerprint()
    monkeypatch.setattr(document.engine, "OCR_LANG", "eng")
    b = document.config_fingerprint()
    assert a != b, "đổi OCR_LANG lúc chạy phải làm vân tay đổi"


def test_van_tay_doi_khi_HANG_SO_BAC_2_bi_gan_luc_chay(monkeypatch):
    """I3 (review toàn nhánh): `Region.grid` được GHI vào artifact và ĐỌC LẠI
    từ đó, nên `GAP_FACTOR`/`SUPPORT_RATIO` PHẢI nằm trong vân tay. Thiếu
    chúng thì đổi tham số bậc 2 xong khoá đệm không đổi -> dùng lại LƯỚI CŨ
    mà không ai biết, đúng lỗ hổng `convert.py` spec §7 viện dẫn để cấm."""
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.4.0")
    a = document.config_fingerprint()
    monkeypatch.setattr(document.table, "GAP_FACTOR", 9.0)
    b = document.config_fingerprint()
    assert a != b, "đổi GAP_FACTOR lúc chạy phải làm vân tay đổi"
    monkeypatch.setattr(document.table, "SUPPORT_RATIO", 0.9)
    c = document.config_fingerprint()
    assert b != c, "đổi SUPPORT_RATIO lúc chạy phải làm vân tay đổi"


def _kq_gia(text="XIN CHAO", conf=91.5):
    w = OcrWord(text=text, conf=conf, left=10, top=20, width=100, height=30,
                line_id=(1, 1, 1))
    return OcrResult(words=[w], text=text, mean_conf=conf)


@pytest.fixture
def kho_tam(monkeypatch, tmp_path):
    monkeypatch.setenv(document.OCR_CACHE_ENV, str(tmp_path))
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.4.0")
    monkeypatch.setattr(document.engine, "osd_rotation", lambda img: 0)
    return tmp_path


def test_lan_dau_doc_that_lan_sau_lay_tu_dem(kho_tam, monkeypatch, tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-gia")
    dem_goi = {"n": 0}

    def _fake_ocr(img, **kw):
        dem_goi["n"] += 1
        return _kq_gia()

    monkeypatch.setattr(document, "_anh_cua_trang", lambda p, n, dpi: object())
    monkeypatch.setattr(document.engine, "ocr_image", _fake_ocr)

    a = document.read_page(str(pdf), 1)
    b = document.read_page(str(pdf), 1)

    assert dem_goi["n"] == 1, "lượt hai phải lấy từ đệm, không đọc lại"
    assert a.tu_dem is False and b.tu_dem is True
    assert a.text == b.text == "XIN CHAO"
    assert b.regions[0].kind == "text"
    assert b.regions[0].words[0]["t"] == "XIN CHAO"
    # Kiểm tra đệm giữ đủ trường: text, conf, toạ độ, line_id
    w = b.regions[0].words[0]
    assert w["c"] == 91.5, "conf phải giữ"
    assert w["l"] == 10 and w["y"] == 20 and w["w"] == 100 and w["h"] == 30, "toạ độ phải giữ"
    assert "g" in w, "line_id (khoá 'g') phải giữ"
    assert w["g"] == [1, 1, 1], "line_id phải là bộ ba [block, par, line]"


def test_doi_van_tay_cau_hinh_thi_KHONG_dung_lai_ban_cu(kho_tam, monkeypatch, tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-gia")
    monkeypatch.setattr(document, "_anh_cua_trang", lambda p, n, dpi: object())
    monkeypatch.setattr(document.engine, "ocr_image", lambda img, **kw: _kq_gia())
    document.read_page(str(pdf), 1)

    # Đổi phiên bản tesseract = đổi vân tay = phải đọc lại, KHÔNG dùng bản cũ.
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.9.9")
    lai = document.read_page(str(pdf), 1)
    assert lai.tu_dem is False


def test_doi_noi_dung_tep_thi_KHONG_dung_lai_ban_cu(kho_tam, monkeypatch, tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-mot")
    monkeypatch.setattr(document, "_anh_cua_trang", lambda p, n, dpi: object())
    monkeypatch.setattr(document.engine, "ocr_image", lambda img, **kw: _kq_gia())
    document.read_page(str(pdf), 1)
    pdf.write_bytes(b"%PDF-HAI-khac-han")
    assert document.read_page(str(pdf), 1).tu_dem is False


def test_dem_hong_giua_chung_KHONG_lam_no_ca_luot_nap(monkeypatch, tmp_path):
    # Tệp đệm cụt (ghi dở, đĩa đầy, tiến trình bị giết) không được làm hỏng
    # việc nạp — đọc lại là đủ. Nếu ném ở đây thì một tệp rác vĩnh viễn sẽ
    # chặn đúng tài liệu đó mãi mãi, vì khoá đệm không bao giờ tự lành.
    #
    # Tách thư mục PDF và đệm riêng để tránh làm hỏng PDF khi làm hỏng đệm.
    dem_dir = tmp_path / "dem"
    dem_dir.mkdir()
    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    pdf = pdf_dir / "x.pdf"
    pdf.write_bytes(b"%PDF-gia")
    monkeypatch.setenv(document.OCR_CACHE_ENV, str(dem_dir))
    monkeypatch.setattr(document.engine, "tesseract_version", lambda: "5.4.0")
    # `read_page` gọi `osd_rotation` (dò xoay, thêm 2026-09-11) TRƯỚC `ocr_image`;
    # không mock thì chạm Tesseract thật -> CI (windows-latest, không có
    # tesseract) đỏ từ 04/09 mà local xanh. Ba test khác trong tệp đã mock.
    monkeypatch.setattr(document.engine, "osd_rotation", lambda img: 0)

    dem_goi = {"n": 0}
    def _fake_ocr(img, **kw):
        dem_goi["n"] += 1
        return _kq_gia()

    monkeypatch.setattr(document, "_anh_cua_trang", lambda p, n, dpi: object())
    monkeypatch.setattr(document.engine, "ocr_image", _fake_ocr)

    # Lần 1: đọc từ PDF, ghi đệm
    a = document.read_page(str(pdf), 1)
    assert a.tu_dem is False and dem_goi["n"] == 1
    files_after_first = len(os.listdir(dem_dir))
    assert files_after_first == 1, "phải ghi 1 tệp đệm"

    # Làm hỏng tệp đệm
    for f in os.listdir(dem_dir):
        (dem_dir / f).write_text("{ khong phai json hop le")

    # Lần 2: đệm hỏng → phải đọc lại từ PDF
    b = document.read_page(str(pdf), 1)
    assert b.tu_dem is False, "nếu đệm hỏng phải đọc lại, tu_dem phải False"
    assert dem_goi["n"] == 2, "phải gọi OCR lần 2 vì đệm hỏng"
    assert b.text == "XIN CHAO", "kết quả phải đúng"

    # Lần 3: đệm phải được ghi lại (tự lành)
    c = document.read_page(str(pdf), 1)
    assert c.tu_dem is True, "lần 3 phải lấy từ đệm (đã được ghi lại)"
    assert dem_goi["n"] == 2, "không gọi OCR lần 3, lấy từ đệm"


@pytest.mark.parametrize("pageno", [0, -1])
def test_pageno_duoi_1_thi_nem_ValueError(pageno):
    # Finding review toàn nhánh B3: trước đây `pageno=0` (hay âm) lặng lẽ đọc
    # TRANG CUỐI qua chỉ số âm của `pdf[pageno - 1]` rồi đệm dưới khoá `p0` —
    # sai trang mà không ai biết. `pageno` đếm từ 1 nên phải bị từ chối
    # tường minh, không chạm tới đĩa/OCR chút nào.
    with pytest.raises(ValueError):
        document.read_page("khong-quan-trong.pdf", pageno)


from src.ocr.engine import tesseract_path

KHO_LUAT = "D:/Documents"


@pytest.mark.skipif(tesseract_path() is None or
                    not os.path.isfile(os.path.join(KHO_LUAT, "luat-thuegtgt.pdf")),
                    reason="chưa có tesseract hoặc kho luật")
def test_read_page_tren_pdf_that(tmp_path, monkeypatch):
    monkeypatch.setenv(document.OCR_CACHE_ENV, str(tmp_path))
    kq = document.read_page(os.path.join(KHO_LUAT, "luat-thuegtgt.pdf"), 1)
    assert kq.page == 1 and kq.tu_dem is False
    assert len(kq.text) > 200, "trang luật thật phải ra vài trăm ký tự"
    assert kq.mean_conf > 50, f"độ tin cậy quá thấp: {kq.mean_conf}"
    assert kq.regions[0].kind == "text"
    # Đệm phải ghi ra tệp THẬT, không chỉ nằm trong bộ nhớ.
    assert len(os.listdir(tmp_path)) == 1
    assert document.read_page(os.path.join(KHO_LUAT, "luat-thuegtgt.pdf"), 1).tu_dem


# --- xoay theo OSD (bậc 3 lát 1, đo 2026-09-11: 20/27 trang OSD báo xoay là thật) ----

class _AnhGia:
    def __init__(self, xoay=False):
        self.xoay = xoay
        self.size = (100, 200)

    def rotate(self, goc, expand=False):
        assert goc == -90 and expand
        return _AnhGia(xoay=True)


def _ocr_theo_huong(conf_thang: float, conf_xoay: float):
    def _fake(img, **kw):
        return _kq_gia(conf=conf_xoay if img.xoay else conf_thang)
    return _fake


def test_osd_bao_xoay_va_huong_xoay_doc_tot_hon_thi_giu_huong_xoay(kho_tam, monkeypatch, tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-gia")
    monkeypatch.setattr(document, "_anh_cua_trang", lambda p, n, dpi: _AnhGia())
    monkeypatch.setattr(document.engine, "osd_rotation", lambda img: 90)
    monkeypatch.setattr(document.engine, "ocr_image", _ocr_theo_huong(43.4, 86.5))   # DVT tr12 thật
    a = document.read_page(str(pdf), 1)
    assert a.rotation == 90 and a.mean_conf == 86.5
    b = document.read_page(str(pdf), 1)
    assert b.tu_dem and b.rotation == 90, "góc xoay phải nằm trong artifact đệm"


def test_osd_bao_xoay_nhung_huong_xoay_doc_TE_hon_thi_giu_huong_goc(kho_tam, monkeypatch, tmp_path):
    """7/27 trang OSD báo sai (độ tin 0–3): TDC tr25 conf 91,9 -> 46,9 sau khi xoay.
    Không tin OSD một chiều — hướng xoay phải TỰ chứng minh bằng lượt đọc."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-gia")
    monkeypatch.setattr(document, "_anh_cua_trang", lambda p, n, dpi: _AnhGia())
    monkeypatch.setattr(document.engine, "osd_rotation", lambda img: 90)
    monkeypatch.setattr(document.engine, "ocr_image", _ocr_theo_huong(91.9, 46.9))
    a = document.read_page(str(pdf), 1)
    assert a.rotation == 0 and a.mean_conf == 91.9


def test_osd_khong_xoay_thi_chi_doc_mot_lan(kho_tam, monkeypatch, tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-gia")
    dem = {"n": 0}

    def _fake(img, **kw):
        dem["n"] += 1
        return _kq_gia()
    monkeypatch.setattr(document, "_anh_cua_trang", lambda p, n, dpi: _AnhGia())
    monkeypatch.setattr(document.engine, "ocr_image", _fake)
    assert document.read_page(str(pdf), 1).rotation == 0
    assert dem["n"] == 1, "không xoay thì không được tốn lượt Tesseract thứ hai"
