import os

import pytest

from src.ocr import engine
from src.ocr.engine import OcrWord, parse_tsv, words_to_lines

# TSV THẬT của tesseract 5.4.0, chép từ phép đo 2026-09-05 trên
# luat-thuexuatnhapkhau.pdf trang 6 (rút gọn còn 5 hàng đầu + 1 từ nữa).
# Cột: level page_num block_num par_num line_num word_num left top width height conf text
_TSV = "\n".join([
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
    "1\t1\t0\t0\t0\t0\t0\t0\t2200\t1700\t-1\t",
    "2\t1\t1\t0\t0\t0\t67\t47\t2065\t1607\t-1\t",
    "3\t1\t1\t1\t0\t0\t67\t47\t2065\t1607\t-1\t",
    "4\t1\t1\t1\t1\t0\t67\t47\t1199\t16\t-1\t",
    "5\t1\t1\t1\t1\t1\t67\t47\t51\t16\t95.924789\t22:41",
    "5\t1\t1\t1\t1\t2\t130\t47\t80\t16\t92.5\tngày",
    "5\t1\t1\t1\t2\t1\t67\t70\t60\t16\t88.25\tĐiều",
])


def test_parse_tsv_chi_lay_hang_TU_that():
    words = parse_tsv(_TSV)
    # 4 hàng level 1-4 là KHUNG CẤU TRÚC (trang/khối/đoạn/dòng), conf=-1,
    # text rỗng — không phải từ. Chỉ 3 hàng level 5 mới là từ.
    assert [w.text for w in words] == ["22:41", "ngày", "Điều"]
    assert words[0].conf == 95.924789
    assert (words[0].left, words[0].top, words[0].width, words[0].height) == (67, 47, 51, 16)


def test_parse_tsv_giu_dinh_danh_dong_de_gom_lai_duoc():
    words = parse_tsv(_TSV)
    assert words[0].line_id == (1, 1, 1)
    assert words[2].line_id == (1, 1, 2)


def test_words_to_lines_gom_theo_dong_giu_thu_tu():
    words = parse_tsv(_TSV)
    assert words_to_lines(words) == ["22:41 ngày", "Điều"]


def test_words_to_lines_rong_thi_tra_rong():
    assert words_to_lines([]) == []


def test_tesseract_path_uu_tien_bien_moi_truong(monkeypatch, tmp_path):
    gia = tmp_path / "tesseract.exe"
    gia.write_text("")
    monkeypatch.setenv(engine.TESSERACT_ENV, str(gia))
    assert engine.tesseract_path() == str(gia)


def test_tesseract_path_bo_qua_bien_tro_vao_cho_khong_ton_tai(monkeypatch, tmp_path):
    # Biến môi trường SAI không được che mất đường dò tiếp theo — nếu không,
    # một biến cũ còn sót lại trong shell sẽ làm cả tầng OCR chết câm.
    monkeypatch.setenv(engine.TESSERACT_ENV, str(tmp_path / "khong-co-that.exe"))
    monkeypatch.setattr(engine.shutil, "which", lambda name: "/usr/bin/tesseract-gia")
    assert engine.tesseract_path() == "/usr/bin/tesseract-gia"


def test_dam_bao_moi_truong_nem_khi_thieu_binary(monkeypatch):
    monkeypatch.setattr(engine, "tesseract_path", lambda: None)
    with pytest.raises(engine.TesseractMissing):
        engine._dam_bao_moi_truong()


def test_dam_bao_moi_truong_KHONG_de_len_tessdata_nguoi_dung_da_dat(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "tesseract_path", lambda: str(tmp_path / "t.exe"))
    monkeypatch.setenv(engine.TESSDATA_ENV, "/cua-nguoi-trien-khai")
    monkeypatch.setattr(engine, "tessdata_prefix", lambda: "/phong-doan-cua-ta")
    engine._dam_bao_moi_truong()
    assert os.environ[engine.TESSDATA_ENV] == "/cua-nguoi-trien-khai"


from PIL import Image, ImageDraw


@pytest.mark.skipif(engine.tesseract_path() is None, reason="chưa cài tesseract")
def test_ocr_image_doc_duoc_chu_tren_anh_tu_dung():
    img = Image.new("RGB", (900, 220), "white")
    ImageDraw.Draw(img).text((20, 60), "TONG CONG TAI SAN 280",
                             fill="black", font_size=64)
    kq = engine.ocr_image(img)
    assert "280" in kq.text
    assert kq.words, "phải đọc được ít nhất một từ"
    assert 0 < kq.mean_conf <= 100
    # Toạ độ phải THẬT, không phải 0 mặc định — bậc 2 dựng bảng dựa vào đây.
    assert any(w.left > 0 and w.width > 0 for w in kq.words)


@pytest.mark.skipif(engine.tesseract_path() is None, reason="chưa cài tesseract")
def test_ocr_image_anh_trang_tra_ve_rong_chu_khong_no():
    kq = engine.ocr_image(Image.new("RGB", (400, 200), "white"))
    assert kq.words == []
    assert kq.text == ""
    assert kq.mean_conf == 0.0
