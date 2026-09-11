"""(c) bảng mã số theo thông tư — `src/ocr/ma_so/tt99.json`, sinh bởi
`tools/derive_form_table.py` từ mẫu docx chính thức TT 99/2025.

Ba câu hỏi, đo trên 7 trang đáp án SCID (TT 99) + 3 trang DVT (TT 107):

1. Bảng đúng KHÔNG BAO GIỜ sai trên đáp án (chiều nguy hiểm).
2. Bảng đúng phủ được bao nhiêu — riêng (c), và gộp (e1) ∪ (c) ∪ (b).
3. **Q4**: áp bảng SAI (TT 99 lên DVT TT 107; B02 lên trang B03...) thì có ràng
   buộc KHÁC 0 nào qua nhầm không. Đo 2026-09-11: **0/6 cặp** — bảng sai sinh
   FAIL (loại hàng đúng — chi phí phạm vi) chứ không sinh PASS giả. Vì thế chọn
   thông tư sai KHÔNG tạo `vision_verified` sai; nó chỉ làm mất phủ.

Số đo 2026-09-11 (sàn theo lệ `>=`, đo ÍT ĐI phải đỏ):
    (c) riêng, SCID:          33/40 ràng buộc tay nội trang, 0 FAIL
    (e1)∪(c)∪(b), 10 trang:    48/55 ràng buộc; 131/136 hàng có số xác minh ở chế
                               độ VLM (strict_absent=False), 0 hàng bị loại. 5 hàng
                               còn lại: 52 (tr9, phân phối — không có ràng buộc),
                               70/71 (tr16, lãi trên cổ phiếu), 280/440/50 (tổng
                               xuyên trang) — tất cả `unverified`, không mất.
"""
import glob
import json
import os

import pytest

from src.ocr import so_hoc
from src.ocr.so_hoc import RowStatus, Verdict

_THU_MUC = os.path.join(os.path.dirname(__file__), "..", "fixtures", "ocr_bang_that")
_COT_NHAN = ("muc", "chi_tieu", "ma_so", "thuyet_minh")
_TT99 = "99/2025/TT-BTC"
# nhom trong đáp án SCID -> mẫu. tr17/18 là phương pháp GIÁN TIẾP (08 = 01 + 02..07).
_MAU_SCID = {"bang_can_doi": "B01-DN", "ket_qua_kd": "B02-DN", "luu_chuyen_tien": "B03-DN-GT"}

SAN_C_RIENG_SCID = 33
SAN_C_RIENG_SCID_TONG = 40
SAN_GOP_TAT_CA = 48
SAN_GOP_TAT_CA_TONG = 55
SAN_HANG_XAC_MINH_VLM = 131          # / 136 hàng có số, chế độ strict_absent=False
SAN_HANG_CO_SO = 136


def _keys(prefix=""):
    return sorted(glob.glob(os.path.join(_THU_MUC, f"{prefix}*.json")))


def _load(p):
    d = json.load(open(p, encoding="utf-8"))
    return d, d["hang"], [c for c in d["cot"] if c not in _COT_NHAN]


def _khoa(c):
    return (c.total, tuple(sorted(c.terms)))


def _tay_noi_trang(d):
    out = set()
    for rb in d["rang_buoc_so_hoc"]:
        terms = [(x, 1) if isinstance(x, str) else (x[0], x[1]) for x in rb["cong"]]
        if any(":" in m for m, _ in terms):
            continue
        out.add(_khoa(so_hoc.Constraint(rb["tong"], terms, "dap_an")))
    return out


def _all_layers(d, rows):
    e1 = [c for c in (so_hoc.parse_printed_formula(h.get("chi_tieu") or "") for h in rows) if c]
    ft = so_hoc.form_table(_TT99, _MAU_SCID[d["nhom"]]) if d["nhom"] in _MAU_SCID else None
    c = ft.constraints if ft else []
    b = so_hoc.derive_hierarchy(rows) if "can_doi" in d["nhom"] else []
    return so_hoc.merge_constraints(e1, c, b)


def _fails(rows, cs, cols, *, strict):
    rep = so_hoc.classify_rows(rows, cs, cols, strict_absent=strict)
    return [e for e in rep.evaluations if e.verdict == Verdict.FAIL], rep


# --- loader + tính toàn vẹn JSON ---------------------------------------------------

def test_loader_returns_none_for_unknown_pairs():
    assert so_hoc.form_table("200/2014/TT-BTC", "B01-DN") is None
    assert so_hoc.form_table(_TT99, "B99-DN") is None


def test_tt99_has_the_four_forms_with_provenance():
    assert set(so_hoc.known_forms()) == {(_TT99, m) for m in ("B01-DN", "B03-DN-TT", "B03-DN-GT", "B02-DN")}
    for tt, mau in so_hoc.known_forms():
        ft = so_hoc.form_table(tt, mau)
        assert ft.constraints and ft.labels
        assert "sha256:" in ft.origin or ft.origin.startswith("tay")
    # B02 là bảng gõ tay — phải NÓI ra trong nguồn, không giả làm suy từ mẫu.
    assert so_hoc.form_table(_TT99, "B02-DN").origin.startswith("tay")


def test_every_referenced_code_has_a_label_and_valid_shape():
    for tt, mau in so_hoc.known_forms():
        ft = so_hoc.form_table(tt, mau)
        for c in ft.constraints:
            for ma in (c.total, *(m for m, _ in c.terms)):
                assert so_hoc.ma_so_key(ma) is not None, (mau, ma)
                assert ma in ft.labels, (mau, ma)
            assert len({m for m, _ in c.terms}) == len(c.terms), (mau, c)
            assert c.source == "bang_tt"


def test_b01_table_recovers_the_printed_grand_totals_and_the_deep_nesting():
    cs = {_khoa(c) for c in so_hoc.form_table(_TT99, "B01-DN").constraints}
    assert ("280", (("100", 1), ("200", 1))) in cs
    assert ("440", (("300", 1), ("400", 1))) in cs
    assert ("233", (("234", 1), ("235", 1))) in cs          # a)/b) rồi gạch — mức 3 và 4
    assert ("420", (("420a", 1), ("420b", 1))) in cs        # KHÔNG kéo 440 vào (lỗi đã đo)


def test_b03_indirect_has_running_subtotals_and_direct_does_not():
    gt = {_khoa(c) for c in so_hoc.form_table(_TT99, "B03-DN-GT").constraints}
    tt = {_khoa(c) for c in so_hoc.form_table(_TT99, "B03-DN-TT").constraints}
    assert ("08", tuple((f"{i:02d}", 1) for i in range(1, 8))) in gt
    assert ("20", (("08", 1), *((f"{i:02d}", 1) for i in range(9, 18)))) in gt
    assert ("20", tuple((f"{i:02d}", 1) for i in range(1, 8))) in tt
    for s in (gt, tt):                                        # nhóm II/III giống nhau
        assert ("30", tuple((str(i), 1) for i in range(21, 28))) in s
        assert ("40", tuple((str(i), 1) for i in range(31, 37))) in s


# --- (c) trên đáp án: không sai, và phủ bao nhiêu ---------------------------------

def test_correct_table_never_fails_on_scid_keys():
    for p in _keys("SCID"):
        d, rows, cols = _load(p)
        ft = so_hoc.form_table(_TT99, _MAU_SCID[d["nhom"]])
        fails, _ = _fails(rows, ft.constraints, cols, strict=True)
        assert fails == [], f"{os.path.basename(p)}: {[e.reason for e in fails]}"


def test_correct_table_alone_recovers_most_hand_written_scid_constraints():
    tong = suy = 0
    for p in _keys("SCID"):
        d, rows, cols = _load(p)
        tay = _tay_noi_trang(d)
        c = {_khoa(x) for x in so_hoc.form_table(_TT99, _MAU_SCID[d["nhom"]]).constraints}
        tong += len(tay)
        suy += len(tay & c)
    print(f"\n[(c) rieng SCID] suy lai {suy}/{tong}")
    assert tong >= SAN_C_RIENG_SCID_TONG
    assert suy >= SAN_C_RIENG_SCID


def test_all_layers_merged_recover_most_hand_written_constraints_on_all_keys():
    tong = suy = 0
    for p in _keys():
        d, rows, cols = _load(p)
        cs, _ = _all_layers(d, rows)
        tay = _tay_noi_trang(d)
        tong += len(tay)
        suy += len(tay & {_khoa(x) for x in cs})
    print(f"\n[(e1)+(c)+(b) 10 trang] suy lai {suy}/{tong}")
    assert tong >= SAN_GOP_TAT_CA_TONG
    assert suy >= SAN_GOP_TAT_CA


def test_merged_layers_in_vlm_mode_reject_nothing_and_verify_most_numeric_rows():
    """Chế độ production (strict_absent=False) trên đáp án: KHÔNG hàng đúng nào
    bị loại; tổng xuyên trang (280, 440, B03:50) ở `unverified`, không mất."""
    co_so = xac_minh = 0
    for p in _keys():
        d, rows, cols = _load(p)
        cs, conflicts = _all_layers(d, rows)
        fails, rep = _fails(rows, cs, cols, strict=False)
        assert fails == [], f"{os.path.basename(p)}: {[e.reason for e in fails]}"
        assert rep.count(RowStatus.REJECTED) == 0, os.path.basename(p)
        num = [r for r in rep.rows if r.numeric]
        co_so += len(num)
        xac_minh += sum(r.status == RowStatus.VERIFIED for r in num)
    print(f"\n[che do VLM, 10 trang] hang co so xac minh {xac_minh}/{co_so}")
    assert co_so >= SAN_HANG_CO_SO
    assert xac_minh >= SAN_HANG_XAC_MINH_VLM


def test_conflicts_between_table_and_page_hierarchy_are_omitted_zero_rows():
    """SCID bỏ hàng "không có số liệu" (ghi chú (1) của mẫu): 133, 213, 214, 317,
    335, 336 vắng → (b) suy từ trang thiếu chúng, (c) có chúng → xung đột. Cả hai
    đều đúng về số; (c) thắng và lenient coi hàng vắng = 0 → PASS. Test ghi rằng
    xung đột này là chuyện bình thường, không phải lỗi bảng."""
    xung_dot = 0
    for p in _keys("SCID"):
        d, rows, cols = _load(p)
        if "can_doi" not in d["nhom"]:
            continue
        _, conflicts = _all_layers(d, rows)
        for thang, thua in conflicts:
            assert thang.source == "bang_tt" and thua.source == "phan_cap"
            xung_dot += 1
    assert xung_dot >= 4


# --- Q4: bảng SAI không sinh PASS giả ---------------------------------------------

_Q4 = [("DVT_2022_tr7", "B01-DN"), ("DVT_2022_tr8", "B01-DN"), ("DVT_2022_tr9", "B02-DN"),
       ("SCID_2026H1_tr16", "B03-DN-GT"), ("SCID_2026H1_tr17", "B02-DN"), ("SCID_2026H1_tr12", "B03-DN-TT")]


@pytest.mark.parametrize("ten,mau", _Q4)
def test_q4_wrong_table_never_passes_a_nonzero_constraint(ten, mau):
    d, rows, cols = _load(os.path.join(_THU_MUC, f"{ten}.json"))
    ft = so_hoc.form_table(_TT99, mau)
    rep = so_hoc.classify_rows(rows, ft.constraints, cols, strict_absent=True)
    qua_khac_0 = [e for e in rep.evaluations if e.verdict == Verdict.PASS and e.total_value != 0]
    assert qua_khac_0 == [], [(e.constraint.total, e.column, e.total_value) for e in qua_khac_0]
    assert rep.count(RowStatus.VERIFIED) == 0
