"""Bậc 3 nối vào `parse_pdf` — spec 2026-09-11 lát 3.

Trang đọc-từ-ảnh có TIÊU ĐỀ báo cáo chính mà số học không vouch được cho
Tesseract → VLM (client giả) đọc → cổng số học → block theo trạng thái hàng.
Cả đường hỏng: một chữ số sai → cụm hàng vắng, cảnh báo nêu mã số; hết khoá →
dừng VLM phần còn lại, giữ Tesseract; không cấu hình → không cảnh báo VLM.
"""
import json
import os

import pytest

from src.ocr import vision
from src.ocr.document import PageRead, Region
from src.rag import parse
from tests.rag.test_parse_pdf_ocr import _dung_canh

_THU_MUC = os.path.join(os.path.dirname(__file__), "..", "fixtures", "ocr_bang_that")
# Dòng tiêu đề Tesseract đọc ĐÚNG trên DVT tr7 dù thân trang là rác (đo 2026-09-11).
_TEXT_TR7 = ("TRUNG TÂM ĐÀO TẠO NGHIỆP VỤ GIAO THÔNG VẬN TẢI BÌNH ĐỊNH Mẫu B01/BCTC\n"
             "Báo cáo tình hình tài chính (Ban hành theo TT số 107/2017/TT-BTC\n"
             "Tại ngày 31 tháng 12 năm 2022\n"
             "STT Chỉ tiêu Mã số Thuyết minh Số cuối năm Số đầu năm\n"
             "Pap s | | c pliị . .s\n"
             "F káananyee 000 26 02m] (4.487463232)\n" + "rác\n" * 10)
_GRID_RAC = [["Pap s", "", "", "25900585)"], ["F káananyee", "", "", "83316921)"]] * 6


def _in(v):
    if not isinstance(v, int):
        return v
    s = f"{abs(v):,}".replace(",", ".")
    return f"({s})" if v < 0 else s


def _payload_tr7():
    d = json.load(open(os.path.join(_THU_MUC, "DVT_2022_tr7.json"), encoding="utf-8"))
    return {"trang": {"mau": "B01/BCTC", "thong_tu": "107/2017/TT-BTC",
                      "cot_gia_tri": ["Số cuối năm", "Số đầu năm"]},
            "hang": [{"muc": h["muc"], "nhan": h["chi_tieu"], "ma_so": h["ma_so"], "thuyet_minh": None,
                      "so_tien": [] if h["ma_so"] is None else [_in(h["so_cuoi_nam"]), _in(h["so_dau_nam"])]}
                     for h in d["hang"]]}


class _FakeVision:
    def __init__(self, payload=None, exc=None):
        self.payload, self.exc, self.calls = payload, exc, 0

    def read_table(self, png):
        self.calls += 1
        assert png[:8] == b"\x89PNG\r\n\x1a\n", "phải nhận PNG bytes của ảnh trang"
        if self.exc:
            raise self.exc
        return vision.VisionTable(payload=self.payload, raw=json.dumps(self.payload), model="fake",
                                  prompt_version="v1", prompt_tokens=1, completion_tokens=1, total_tokens=2)


def _trang_anh(monkeypatch, text=_TEXT_TR7, grid=_GRID_RAC, rotation=0):
    p = _dung_canh(monkeypatch, [""])
    monkeypatch.setattr(p, "read_page", lambda path, pageno, **kw: PageRead(
        page=1, mean_conf=63.3, tu_dem=False, rotation=rotation,
        regions=[Region(kind="text", text=text, mean_conf=63.3, bbox=(0, 0, 100, 100), words=[], grid=grid)]))
    from PIL import Image
    anh = {"xoay": []}

    class _Img:
        def rotate(self, goc, expand=False):
            anh["xoay"].append(goc)
            return Image.new("RGB", (8, 8), "white")

        def save(self, buf, format):
            Image.new("RGB", (8, 8), "white").save(buf, format=format)
    monkeypatch.setattr(p, "_anh_cua_trang", lambda path, pageno, dpi: _Img())
    return p, anh


def test_trang_bao_cao_chinh_tesseract_hong_di_VLM_va_so_qua_cong_moi_duoc_luu(monkeypatch):
    p, _ = _trang_anh(monkeypatch)
    fake = _FakeVision(_payload_tr7())
    monkeypatch.setattr(p, "VISION_READER_FACTORY", lambda: fake)
    blocks, warnings = p.parse_pdf("dvt.pdf")
    assert fake.calls == 1
    kinds = {b["source_kind"] for b in blocks}
    assert kinds <= {"vision_verified", "vision_unverified"}, kinds
    verified = [b for b in blocks if b["source_kind"] == "vision_verified"]
    assert len(verified) == 12, "12 hàng có số của tr7 đều được số học bảo lãnh"
    assert all(b.get("atomic") for b in verified)
    tong = next(b for b in verified if "Mã số: 50" in b["text"])
    assert "69.862.687.223" in tong["text"] and "Số đầu năm" in tong["text"]
    # Không còn block Tesseract nào của trang này (một xuất xứ mỗi trang).
    assert not any(b["source_kind"] == "ocr" for b in blocks)
    vlm_w = [w for w in warnings if w[0] == "trang 1 (VLM)"]
    assert len(vlm_w) == 1 and "xác minh 12/12" in vlm_w[0][1] and "fake/v1" in vlm_w[0][1]


def test_mot_chu_so_sai_thi_cum_hang_vang_va_canh_bao_neu_ma_so(monkeypatch):
    p, _ = _trang_anh(monkeypatch)
    payload = _payload_tr7()
    next(h for h in payload["hang"] if h["ma_so"] == "11")["so_tien"][0] = "8.812.478.001"
    monkeypatch.setattr(p, "VISION_READER_FACTORY", lambda: _FakeVision(payload))
    blocks, warnings = p.parse_pdf("dvt.pdf")
    texts = "\n".join(b["text"] for b in blocks)
    for ma in ("10", "11", "12", "13", "14"):
        assert f"Mã số: {ma} " not in texts and f"Mã số: {ma}|" not in texts, f"hàng {ma} phải vắng"
    assert "Mã số: 50" in texts, "cụm 50 không dính, vẫn được lưu"
    w = next(w for w in warnings if w[0] == "trang 1 (VLM)")[1]
    assert "loại 5" in w and "11:" in w and "lệch -1" in w


def test_trang_xoay_thi_anh_gui_VLM_da_xoay_theo_OSD(monkeypatch):
    p, anh = _trang_anh(monkeypatch, rotation=90)
    monkeypatch.setattr(p, "VISION_READER_FACTORY", lambda: _FakeVision(_payload_tr7()))
    p.parse_pdf("dvt.pdf")
    assert anh["xoay"] == [-90]


def test_khong_co_khoa_thi_giu_Tesseract_khong_canh_bao_VLM_va_khong_goi_lai(monkeypatch):
    p, _ = _trang_anh(monkeypatch)
    fake = _FakeVision(exc=vision.VisionUnavailable("không có khoá"))
    monkeypatch.setattr(p, "VISION_READER_FACTORY", lambda: fake)
    blocks, warnings = p.parse_pdf("dvt.pdf")
    assert fake.calls == 1
    assert blocks and all(b.get("source_kind") == "ocr" for b in blocks)
    assert not any("(VLM)" in w[0] for w in warnings)


def test_het_khoa_thi_canh_bao_va_dung_VLM_cho_trang_sau(monkeypatch):
    import pypdf
    p, _ = _trang_anh(monkeypatch)
    from tests.rag.test_parse_pdf_ocr import _FakePlumberPDF, _FakeReader
    import pdfplumber
    monkeypatch.setattr(pypdf, "PdfReader", lambda path: _FakeReader(["", ""]))
    monkeypatch.setattr(pdfplumber, "open", lambda path: _FakePlumberPDF(2))
    fake = _FakeVision(exc=vision.VisionQuotaExhausted("hết 2 khoá vì 429"))
    monkeypatch.setattr(p, "VISION_READER_FACTORY", lambda: fake)
    blocks, warnings = p.parse_pdf("dvt.pdf")
    assert fake.calls == 1, "trang 2 cũng là báo cáo chính nhưng KHÔNG gọi nữa"
    assert [w for w in warnings if "(VLM)" in w[0]] == [("trang 1 (VLM)", "dừng VLM cho phần còn lại: hết 2 khoá vì 429")]
    assert all(b["source_kind"] == "ocr" for b in blocks)


def test_phan_hoi_hong_thi_giu_Tesseract_va_van_thu_trang_sau(monkeypatch):
    p, _ = _trang_anh(monkeypatch)
    fake = _FakeVision(exc=vision.VisionBadResponse("JSON hỏng (12 ký tự)"))
    monkeypatch.setattr(p, "VISION_READER_FACTORY", lambda: fake)
    blocks, warnings = p.parse_pdf("dvt.pdf")
    assert all(b["source_kind"] == "ocr" for b in blocks)
    assert any("phản hồi không dùng được" in w[1] for w in warnings)


def test_trang_khong_phai_bao_cao_chinh_thi_khong_dung_bo_doc(monkeypatch):
    p, _ = _trang_anh(monkeypatch, text="Điều 1. Chữ đọc từ ảnh.\nKhoản 2. Nội dung khác.\n" * 5,
                      grid=[])
    monkeypatch.setattr(p, "VISION_READER_FACTORY", lambda: pytest.fail("không được dựng bộ đọc VLM"))
    blocks, warnings = p.parse_pdf("luat.pdf")
    assert blocks and not any("(VLM)" in w[0] for w in warnings)


def test_trang_bao_cao_chinh_ma_Tesseract_duoc_so_hoc_bao_lanh_thi_khong_goi_VLM(monkeypatch):
    """Lưới Tesseract dựng từ đáp án tr7: số học vouch → giữ hàng `ocr`, KHÔNG
    gọi VLM, nhưng cảnh báo NÓI RA lý do."""
    from tests.ocr.test_grid_rows_assess import _tr7_grid
    grid = _tr7_grid()
    p, _ = _trang_anh(monkeypatch, text=_TEXT_TR7, grid=grid)
    monkeypatch.setattr(p, "VISION_READER_FACTORY", lambda: pytest.fail("số học đã vouch, không gọi VLM"))
    blocks, warnings = p.parse_pdf("dvt.pdf")
    assert any(b["source_kind"] == "ocr" for b in blocks)
    assert any("số học vouch cho Tesseract" in w[1] for w in warnings)
