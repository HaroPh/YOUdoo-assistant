"""Q7 — thăm dò GIẢI NGƯỢC (spec): bôi đen MỘT ô trên ảnh rồi hỏi VLM. Nếu nó trả
đúng con số bị che (= tổng − các thành phần còn lại) thay vì null/"-", thì số
học nội trang có lỗ đã chứng minh: hàng trong đúng một ràng buộc có thể được
"xác minh" bằng chính con số VLM tính ra.

Chạy TAY (3 lượt): pytest tests/ocr/test_vision_q7_live.py -m live -q -s
Phản hồi thô ghi vào vlm_raw/Q7_*.json. Kết quả ghi vào ghi chú thi hành.

Trang: SCID tr12, Tesseract đọc tốt nên toạ độ ô lấy từ token đệm sẵn.
  - ô thành phần 112 / Số cuối kỳ (54.180.578.081): 110 = 111 + 112 → giải ngược được
  - ô tổng 110 / Số cuối kỳ (148.058.124.948): = 111 + 112 → giải ngược được
  - ô "-" 124 / Số cuối kỳ: không giải ngược được — đối chứng
"""
import json
import os
from datetime import datetime, timezone

import pytest
from PIL import ImageDraw

from src.ocr import vision
from src.ocr.document import _anh_cua_trang, read_page
from src.ocr.engine import OCR_DPI

pytestmark = pytest.mark.live

_RAW = os.path.join(os.path.dirname(__file__), "..", "fixtures", "ocr_bang_that", "vlm_raw")
_SCID = "D:/downloads/SID_000000016657191_01VI_BaoCaoTaiChinhBanNien_HopNhat_SoatXet_2026_signed_05092026111802.pdf"
_TRANG = 12

# (tên, mã số, token Tesseract để định vị ô, giá trị thật, giải ngược được?)
_O = [("thanh_phan_112", "112", "54.180.578.081", "54.180.578.081", True),
      ("tong_110", "110", "148.058.124.948", "148.058.124.948", True),
      ("gach_124", "124", None, "-", False)]


def _bbox(kq, token, ma_so):
    words = [w for r in kq.regions for w in r.words]
    if token:
        w = next(w for w in words if w["t"] == token)
    else:
        # ô "-" trôi/không thành token: lấy hàng của mã số, cột của token tiền gần nhất phía trên
        ma = next(w for w in words if w["t"] == ma_so)
        ref = next(w for w in words if w["t"] == "54.180.578.081")
        w = {"l": ref["l"], "y": ma["y"], "w": ref["w"], "h": ma["h"]}
    return (w["l"] - 6, w["y"] - 6, w["l"] + w["w"] + 6, w["y"] + w["h"] + 6)


@pytest.mark.parametrize("ten,ma_so,token,that,giai_nguoc_duoc", _O)
def test_boi_den_mot_o_roi_xem_vlm_tra_gi(ten, ma_so, token, that, giai_nguoc_duoc):
    if not vision.vlm_enabled():
        pytest.skip("không có khoá VLM")
    if not os.path.isfile(_SCID):
        pytest.skip("thiếu SCID")
    kq = read_page(_SCID, _TRANG)
    img = _anh_cua_trang(_SCID, _TRANG, OCR_DPI)
    if kq.rotation:
        img = img.rotate(-kq.rotation, expand=True)
    ImageDraw.Draw(img).rectangle(_bbox(kq, token, ma_so), fill="black")
    t = vision.VisionReader().read_table(vision.page_png(img))
    hang = next((h for h in t.payload["hang"] if str(h.get("ma_so")) == ma_so), None)
    o = hang["so_tien"][0] if hang and hang.get("so_tien") else None
    os.makedirs(_RAW, exist_ok=True)
    with open(os.path.join(_RAW, f"Q7_{ten}.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"o_boi_den": ten, "ma_so": ma_so, "gia_tri_that": that, "vlm_tra": o,
                   "giai_nguoc": o == that and giai_nguoc_duoc,
                   "ngay": datetime.now(timezone.utc).isoformat(), "raw": t.raw, "payload": t.payload},
                  f, ensure_ascii=False, indent=1)
    print(f"\n[Q7 {ten}] ô bị che, giá trị thật {that!r} → VLM trả {o!r}"
          + ("  ← GIẢI NGƯỢC" if o == that and giai_nguoc_duoc else ""))
    # Không assert kết quả: đây là phép ĐO, hai chiều đều là thông tin. Chỉ đòi có phản hồi.
    assert hang is not None
