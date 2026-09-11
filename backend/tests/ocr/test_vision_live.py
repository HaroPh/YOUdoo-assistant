"""Q8 — VLM đọc thật, so từng ô với đáp án tay, BẮT phản hồi thô làm fixture.

Chạy TAY, có chủ ý, tiêu hạn mức khoá VLM riêng (không đụng khoá chat):

    pytest tests/ocr/test_vision_live.py -m live -q -s

Mỗi trang đáp án (10 trang: SCID tr12–18 TT 99, DVT tr7–9 TT 107) gọi VLM
`SO_LAN` lần (spec: 2, cho tất định). Phản hồi thô ghi vào
`tests/fixtures/ocr_bang_that/vlm_raw/<tên>_lan<k>.json` — từ đó
`test_vision_replay.py` chạy OFFLINE mọi lần bộ kiểm đổi.

Số cứng của spec: **0 ô sai được lưu `vision_verified`**. Ghi thêm (không
assert): hàng đúng bị loại (chi phí phạm vi), độ phủ, đồng ý giữa hai lượt.
"""
import glob
import json
import os
from datetime import datetime, timezone

import pytest

from src.ocr import so_hoc, vision
from src.ocr.document import _anh_cua_trang, read_page
from src.ocr.engine import OCR_DPI

pytestmark = pytest.mark.live

_THU_MUC = os.path.join(os.path.dirname(__file__), "..", "fixtures", "ocr_bang_that")
_RAW = os.path.join(_THU_MUC, "vlm_raw")
SO_LAN = 2


def _keys():
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(_THU_MUC, "*.json")))


@pytest.fixture(scope="module")
def reader():
    if not vision.vlm_enabled():
        pytest.skip(f"không có {vision.VLM_ENV} — test live cần khoá VLM riêng")
    return vision.VisionReader()


@pytest.mark.parametrize("lan", range(1, SO_LAN + 1))
@pytest.mark.parametrize("ten", _keys())
def test_bat_phan_hoi_tho_va_khong_o_sai_nao_duoc_xac_minh(reader, ten, lan):
    d = json.load(open(os.path.join(_THU_MUC, ten), encoding="utf-8"))
    path, pg = d["duong_dan_goc"], d["trang_pdf"]
    if not os.path.isfile(path):
        pytest.skip(f"thiếu tệp gốc {path}")
    kq = read_page(path, pg)                         # để biết góc xoay OSD đã chọn
    img = _anh_cua_trang(path, pg, OCR_DPI)
    if kq.rotation:
        img = img.rotate(-kq.rotation, expand=True)
    t = reader.read_table(vision.page_png(img))

    os.makedirs(_RAW, exist_ok=True)
    out = os.path.join(_RAW, f"{ten[:-5]}_lan{lan}.json")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"dap_an": ten, "model": t.model, "prompt_version": t.prompt_version,
                   "rotation": kq.rotation, "ngay": datetime.now(timezone.utc).isoformat(),
                   "tokens": [t.prompt_tokens, t.completion_tokens, t.total_tokens],
                   "raw": t.raw, "payload": t.payload}, f, ensure_ascii=False, indent=1)

    from tests.ocr.test_vision_replay import so_voi_dap_an
    kq_so = so_voi_dap_an(t.payload, d)
    print(f"\n[Q8 {ten} lần {lan}] {kq_so['tom_tat']}")
    assert kq_so["sai_ma_verified"] == [], f"{ten}: ô SAI được lưu vision_verified: {kq_so['sai_ma_verified']}"
