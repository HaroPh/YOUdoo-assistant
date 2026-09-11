"""Q1 của spec VLM bậc 3: suy ràng buộc CHỈ TỪ HÀNG (nhãn, đánh dấu STT, mã số),
không nhìn `rang_buoc_so_hoc` tay, rồi hỏi hai câu trên 10 trang đáp án:

1. **Không được sinh ràng buộc SAI.** Đáp án là chân lý; một ràng buộc suy ra mà
   FAIL trên đáp án nghĩa là QUY TẮC SUY sai — thước hỏng theo chiều nguy hiểm
   (nó sẽ loại hàng VLM đọc đúng).
2. **Suy ra lại được bao nhiêu ràng buộc tay.** Đây là độ phủ — thước hỏng theo
   chiều ngược (nó bỏ qua hàng cần kiểm).

Số đo 2026-09-11, sau hai lần sửa quy tắc phân cấp đều do chính phép đo này
bắt được (hàng TỔNG CỘNG không STT bị gán làm con → "74 = 80"; nhảy bậc
IV.→"-" và D-→1.):

    B01 (cân đối, TT 99 + TT 107): suy lại 32/35 nội trang, 0 ràng buộc sai
    B02/B03 (KQKD, lưu chuyển tiền): 0/20 — (b) SAI 5 lần → lý do giới hạn (b) vào B01

Sàn 32/35 theo lệ `assert total >= N`: đo ÍT ĐI phải đỏ.
"""
import glob
import json
import os

import pytest

from src.ocr import so_hoc
from src.ocr.so_hoc import Verdict

_THU_MUC = os.path.join(os.path.dirname(__file__), "..", "fixtures", "ocr_bang_that")
_COT_NHAN = ("muc", "chi_tieu", "ma_so", "thuyet_minh")

# Sàn đo 2026-09-11. Nâng khi (c) bảng thông tư vào; KHÔNG hạ.
SAN_B01_SUY_LAI = 32
SAN_B01_TONG = 35


def _keys():
    return sorted(p for p in glob.glob(os.path.join(_THU_MUC, "*.json")))


def _cot_gia_tri(d):
    return [c for c in d["cot"] if c not in _COT_NHAN]


def _khoa(c: so_hoc.Constraint):
    return (c.total, tuple(sorted(c.terms)))


def _tay_noi_trang(d):
    """Ràng buộc tay, bỏ đồng nhất xuyên trang (`nhom:ma`) — ngoài phạm vi suy nội trang."""
    out = set()
    for rb in d["rang_buoc_so_hoc"]:
        terms = [(x, 1) if isinstance(x, str) else (x[0], x[1]) for x in rb["cong"]]
        if any(":" in m for m, _ in terms):
            continue
        out.add(_khoa(so_hoc.Constraint(rb["tong"], terms, "dap_an")))
    return out


def _suy(d):
    rows = d["hang"]
    e1 = [c for c in (so_hoc.parse_printed_formula(h.get("chi_tieu") or "") for h in rows) if c]
    b = so_hoc.derive_hierarchy(rows)
    return e1, b


def _fail_count(d, cs):
    rows = d["hang"]
    lookup = {str(h["ma_so"]): h for h in rows if h.get("ma_so")}.get
    return sum(so_hoc.evaluate(c, lookup, cot, strict_absent=True).verdict == Verdict.FAIL
               for c in cs for cot in _cot_gia_tri(d))


@pytest.mark.skipif(not glob.glob(os.path.join(_THU_MUC, "*.json")), reason="thiếu đáp án")
def test_printed_formulas_never_contradict_the_approved_keys():
    """(e1) là tầng mạnh nhất; một công thức in mà FAIL trên đáp án nghĩa là
    parser sai HOẶC đáp án sai — cả hai đều phải nhìn thấy."""
    for p in _keys():
        d = json.load(open(p, encoding="utf-8"))
        e1, _ = _suy(d)
        assert _fail_count(d, e1) == 0, f"{os.path.basename(p)}: công thức in FAIL trên đáp án"


@pytest.mark.skipif(not glob.glob(os.path.join(_THU_MUC, "*.json")), reason="thiếu đáp án")
def test_hierarchy_never_invents_a_false_constraint_on_balance_sheets():
    """Chiều nguy hiểm: (b) sinh ràng buộc sai → hàng VLM đọc ĐÚNG bị loại. Trên
    B01 phải là 0. (Q1 lần đầu đo được 6 — "74 = 80" và họ hàng — trước khi
    có luật >= 2 con.)"""
    for p in _keys():
        d = json.load(open(p, encoding="utf-8"))
        if "can_doi" not in d["nhom"]:
            continue
        _, b = _suy(d)
        assert _fail_count(d, b) == 0, f"{os.path.basename(p)}: (b) sinh ràng buộc SAI trên B01"


@pytest.mark.skipif(not glob.glob(os.path.join(_THU_MUC, "*.json")), reason="thiếu đáp án")
def test_hierarchy_recovers_most_hand_written_balance_sheet_constraints():
    tong = suy_lai = 0
    for p in _keys():
        d = json.load(open(p, encoding="utf-8"))
        if "can_doi" not in d["nhom"]:
            continue
        tay = _tay_noi_trang(d)
        e1, b = _suy(d)
        suy = {_khoa(c) for c in e1 + b}
        tong += len(tay)
        suy_lai += len(tay & suy)
    print(f"\n[Q1 B01] suy lai {suy_lai}/{tong} rang buoc tay noi trang")
    assert tong >= SAN_B01_TONG, f"chỉ {tong} ràng buộc B01 — bộ đáp án đo ÍT ĐI"
    assert suy_lai >= SAN_B01_SUY_LAI, f"suy lại {suy_lai}/{tong} < sàn {SAN_B01_SUY_LAI}"


@pytest.mark.skipif(not glob.glob(os.path.join(_THU_MUC, "*.json")), reason="thiếu đáp án")
def test_hierarchy_DOES_fail_on_income_and_cash_flow_statements():
    """Test "vì sao": (b) toàn hệ số +1, nên trên B02 (12 = 10 - 11) và B03 (thành
    phần đứng TRƯỚC tổng) nó phải sai. Nếu một ngày test này xanh, đó KHÔNG phải
    tin tốt — nghĩa là (b) không còn sinh ràng buộc nào ở đó, tức phạm vi của
    nó đã bị thu hẹp mà không ai đo."""
    fail = 0
    for p in _keys():
        d = json.load(open(p, encoding="utf-8"))
        if "can_doi" in d["nhom"]:
            continue
        _, b = _suy(d)
        fail += _fail_count(d, b)
    assert fail > 0, "(b) không còn sai trên B02/B03 — phạm vi của nó đổi mà chưa đo lại"
