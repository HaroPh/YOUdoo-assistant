"""Q8 OFFLINE — chạy lại bộ kiểm trên phản hồi VLM thô đã bắt (`vlm_raw/`),
so từng ô với đáp án tay. Không API, chạy trong CI. Bỏ qua khi chưa có fixture
(lát 2 chưa chạy `test_vision_live.py`).

Số cứng: 0 ô sai được lưu `vision_verified`. Ngoài ra in: hàng đúng bị loại,
độ phủ, ô VLM đọc sai bị bắt ở tầng nào.
"""
import glob
import json
import os

import pytest

from src.ocr import so_hoc
from src.ocr.so_hoc import RowStatus

_THU_MUC = os.path.join(os.path.dirname(__file__), "..", "fixtures", "ocr_bang_that")
_RAW = os.path.join(_THU_MUC, "vlm_raw")
_COT_NHAN = ("muc", "chi_tieu", "ma_so", "thuyet_minh")


def _gia_tri_dap_an(o):
    """Ô đáp án -> int | DASH | None (null: không tồn tại ô)."""
    if o is None:
        return None
    return so_hoc.parse_money(o)


def so_voi_dap_an(payload: dict, dap_an: dict) -> dict:
    """So một payload VLM với một trang đáp án. Cột VLM ghép với cột đáp án THEO
    VỊ TRÍ (trái → phải) — đây cũng là chỗ điểm mù "đảo cột toàn trang" hiện ra
    nếu có: mọi ô sai cột nhưng số học vẫn qua."""
    rows, cols, issues = so_hoc.rows_from_vision(payload)
    a = so_hoc.assess_page(rows, cols, strict_absent=False, extra_issues=issues)
    key_cols = [c for c in dap_an["cot"] if c not in _COT_NHAN]
    key = {str(h["ma_so"]): h for h in dap_an["hang"] if h.get("ma_so")}
    status = {r.index: r for r in a.report.rows}

    sai_verified, sai_bat_duoc, dung_bi_loai, verified_dung = [], [], [], 0
    thieu = set(key)
    for i, r in enumerate(rows):
        ma = r.get("ma_so")
        if ma is None or ma not in key:
            continue
        thieu.discard(ma)
        h = key[ma]
        sai = []
        for k, (cv, kc) in enumerate(zip(cols, key_cols)):
            v = so_hoc.parse_money(r[cv]) if r.get(cv) is not None else None
            kv = _gia_tri_dap_an(h.get(kc))
            if kv is None and v is None:
                continue
            if v is None or v is so_hoc.BAD or kv is so_hoc.BAD or (v is not kv and v != kv):
                sai.append((cv, r.get(cv), h.get(kc)))
        st = status[i].status
        if sai and st == RowStatus.VERIFIED:
            sai_verified.append((ma, sai))
        elif sai:
            sai_bat_duoc.append((ma, st, sai))
        elif st == RowStatus.REJECTED:
            dung_bi_loai.append((ma, status[i].reason))
        elif st == RowStatus.VERIFIED:
            verified_dung += 1
    co_so = sum(1 for h in key.values() if any(isinstance(h.get(c), int) for c in key_cols))
    tom_tat = (f"form={a.form.mau if a.form else '-'} | {a.report.summary} | "
               f"ô sai→verified {len(sai_verified)} · ô sai bị bắt {len(sai_bat_duoc)} · "
               f"hàng đúng bị loại {len(dung_bi_loai)} · verified đúng {verified_dung}/{co_so} hàng có số · "
               f"mã số đáp án vắng {sorted(thieu)}")
    return {"sai_ma_verified": sai_verified, "sai_bat_duoc": sai_bat_duoc,
            "dung_bi_loai": dung_bi_loai, "verified_dung": verified_dung, "co_so": co_so,
            "thieu": sorted(thieu), "tom_tat": tom_tat, "assessment": a}


def _raws():
    """Fixture Q8 (trang nguyên vẹn). Q7_* là ảnh BỊ BÔI ĐEN có chủ ý — test riêng."""
    return sorted(p for p in glob.glob(os.path.join(_RAW, "*.json"))
                  if not os.path.basename(p).startswith("Q7_"))


def _q7():
    return sorted(glob.glob(os.path.join(_RAW, "Q7_*.json")))


@pytest.mark.skipif(not _raws(), reason="chưa có fixture vlm_raw (chạy test_vision_live.py -m live)")
@pytest.mark.parametrize("p", _raws())
def test_khong_o_sai_nao_duoc_luu_vision_verified(p):
    raw = json.load(open(p, encoding="utf-8"))
    d = json.load(open(os.path.join(_THU_MUC, raw["dap_an"]), encoding="utf-8"))
    kq = so_voi_dap_an(raw["payload"], d)
    print(f"\n[replay {os.path.basename(p)}] {kq['tom_tat']}")
    for ma, st, sai in kq["sai_bat_duoc"]:
        print(f"    bắt: {ma} {st} {sai}")
    for ma, ly_do in kq["dung_bi_loai"]:
        print(f"    loại oan: {ma} — {ly_do}")
    assert kq["sai_ma_verified"] == [], kq["sai_ma_verified"]


def test_so_voi_dap_an_bat_duoc_o_sai_tren_payload_gia():
    """Thước tự kiểm: payload đúng theo đáp án tr7 -> 0 sai; đổi một ô ở hàng
    được ràng buộc phủ -> ô sai bị BẮT (loại), không lọt vào verified."""
    d = json.load(open(os.path.join(_THU_MUC, "DVT_2022_tr7.json"), encoding="utf-8"))

    def _in(v):
        if not isinstance(v, int):
            return v
        s = f"{abs(v):,}".replace(",", ".")
        return f"({s})" if v < 0 else s
    payload = {"trang": {"cot_gia_tri": ["Số cuối năm", "Số đầu năm"]},
               "hang": [{"muc": h["muc"], "nhan": h["chi_tieu"], "ma_so": h["ma_so"], "thuyet_minh": None,
                         "so_tien": [] if h["ma_so"] is None else [_in(h["so_cuoi_nam"]), _in(h["so_dau_nam"])]}
                        for h in d["hang"]]}
    kq = so_voi_dap_an(payload, d)
    assert kq["sai_ma_verified"] == [] and kq["sai_bat_duoc"] == [] and kq["verified_dung"] == 12
    r11 = next(h for h in payload["hang"] if h["ma_so"] == "11")
    r11["so_tien"][0] = "8.812.478.001"
    kq = so_voi_dap_an(payload, d)
    assert kq["sai_ma_verified"] == []
    assert [x[0] for x in kq["sai_bat_duoc"]] == ["11"]
    assert {x[0] for x in kq["dung_bi_loai"]} == {"10", "12", "13", "14"}, "cả cụm đi — chi phí phạm vi, ghi rõ"


@pytest.mark.skipif(not _q7(), reason="chưa có fixture Q7 (chạy test_vision_q7_live.py -m live)")
@pytest.mark.parametrize("p", _q7())
def test_q7_o_bi_che_khong_bi_giai_nguoc_va_khong_lot_vao_verified(p):
    """Đo 2026-09-11 (SCID tr12, flash-lite): che ô thành phần 112 → VLM trả "-";
    che ô tổng 110 → null; che ô "-" → "-". KHÔNG tính ra số bị che. Bộ kiểm:
    "-" giả làm 110 = 111 + 112 lệch → cụm 3 hàng loại (2 hàng đúng bị loại —
    chi phí phạm vi); null → hàng 110 unverified (quy tắc ô trống). 0 ô sai
    được lưu verified ở cả ba."""
    raw = json.load(open(p, encoding="utf-8"))
    d = json.load(open(os.path.join(_THU_MUC, "SCID_2026H1_tr12.json"), encoding="utf-8"))
    if raw["gia_tri_that"] != "-":
        assert raw["vlm_tra"] != raw["gia_tri_that"], "VLM đã GIẢI NGƯỢC ô bị che — lỗ số học có thật"
    kq = so_voi_dap_an(raw["payload"], d)
    print(f"\n[Q7 replay {os.path.basename(p)}] VLM trả {raw['vlm_tra']!r} | {kq['tom_tat']}")
    assert kq["sai_ma_verified"] == [], kq["sai_ma_verified"]
