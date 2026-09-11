"""Sinh bảng mã số theo thông tư (`src/ocr/ma_so/tt99.json`) TỪ MẪU CHÍNH THỨC.

Spec VLM bậc 3, tầng (c): bảng thông tư "suy từ mẫu docx chính thức, không gõ
tay". Mẫu TT 99/2025 nằm ở `D:\\Youdoo\\tmp-docs\\*.docx` (ngoài worktree, cùng
lý do đường dẫn tuyệt đối như `calibrate_table.py`). Mỗi mẫu cho ra:

- `nhan`      — mã số -> nhãn chuẩn (lát 5: so nhãn VLM đọc với nhãn chuẩn);
- `rang_buoc` — ràng buộc số học, nguồn ghi từng dòng:
    * `in_san`   : công thức in ngay trên mẫu — `(280 = 100 + 200)`;
    * `phan_cap` : suy từ đánh dấu STT của MẪU bằng CHÍNH `derive_hierarchy`
                   production (B01) — khác (b) ở chỗ chạy trên mẫu sạch, nên
                   VLM đọc sai đánh dấu không đổi được ràng buộc, và hàng bị
                   rơi hiện ra dưới dạng `absent`;
    * `cau_truc_b03`: quy tắc riêng của mẫu lưu chuyển tiền — thành phần đứng
                   TRƯỚC tổng, tổng là hàng không đánh dấu cuối nhóm la-mã;
                   phương pháp gián tiếp còn có tổng phụ chạy (08 = 01 + 02..07,
                   20 = 08 + 09..17);
    * `tay`      : B02-DN (kết quả kinh doanh) — KHÔNG có mẫu docx trong
                   tmp-docs và quan hệ có dấu (10 = 01 - 02) không nằm trong
                   bố cục mẫu mà trong văn bản hướng dẫn. Gõ tay, đối chiếu
                   trên SCID tr16; ghi rõ để ai đọc biết đây là tầng yếu nhất
                   của tệp này.

Kết quả là ARTIFACT có tên nguồn + sha256 của mẫu; production chỉ đọc JSON,
không bao giờ đọc docx. Chạy lại khi mẫu đổi:

    python -m tools.derive_form_table
"""
import hashlib
import json
import os
import re
import sys
from datetime import date

import docx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.ocr import so_hoc  # noqa: E402

FORMS_DIR = r"D:\Youdoo\tmp-docs"
OUT = os.path.join(os.path.dirname(__file__), "..", "src", "ocr", "ma_so", "tt99.json")

# Tệp -> mã mẫu. `b02-dn.docx` trong tmp-docs là bản B01 dán nhầm (sha256 trùng
# `b01-dn.docx`), `B02a-DN.docx` là B01-DNKLT — không có B02 thật, xem `tay`.
FORMS = {
    "B01-DN": "b01-dn.docx",
    "B03-DN-TT": "b03-dn-truc-tiep.docx",
    "B03-DN-GT": "b03-dn-pp-gian-tiep.docx",
}

_MARKER_RE = re.compile(
    r"^(?:(?P<hoa>[A-Z])\s*-|(?P<lama>[IVX]+)\.|(?P<so>\d+)\.|(?P<thuong>[a-z])\)|(?P<gach>-))\s*(?P<nhan>.*)$")


def _sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


def _rows(path: str) -> list[dict]:
    """Bảng chỉ tiêu của mẫu -> hàng {muc, chi_tieu, ma_so}, theo đúng hình dạng
    hàng đáp án/VLM để `derive_hierarchy` dùng nguyên."""
    d = docx.Document(path)
    t = max(d.tables, key=lambda t: len(t.rows))
    out = []
    for r in t.rows:
        cells = [c.text.strip().replace("\n", " ") for c in r.cells]
        nhan, ma = cells[0], cells[1]
        if not nhan or nhan in ("TÀI SẢN", "NGUỒN VỐN", "Chỉ tiêu", "1"):
            continue
        m = _MARKER_RE.match(nhan)
        if m:
            muc = next(v for k, v in m.groupdict().items() if v is not None and k != "nhan")
            if m.group("hoa"):
                muc += "-"
            elif m.group("lama") or m.group("so"):
                muc += "."
            elif m.group("thuong"):
                muc += ")"
            nhan = m.group("nhan").strip()
        else:
            muc = None
        out.append({"muc": muc, "chi_tieu": nhan, "ma_so": ma or None})
    return out


def _b01(rows: list[dict]) -> list[dict]:
    e1 = [c for c in (so_hoc.parse_printed_formula(r["chi_tieu"]) for r in rows) if c]
    b = so_hoc.derive_hierarchy(rows)
    merged, conflicts = so_hoc.merge_constraints(e1, b)
    assert not conflicts, conflicts
    return [_rb(c) for c in merged]


def _b03(rows: list[dict], *, gian_tiep: bool) -> list[dict]:
    """Nhóm la-mã: hàng có mã số theo thứ tự; tổng nhóm = hàng KHÔNG đánh dấu
    cuối nhóm. Trực tiếp: tổng = Σ hàng số. Gián tiếp: hàng số là MỐC — mốc
    sau = mốc trước + các gạch đầu dòng giữa hai mốc; tổng nhóm = mốc cuối +
    gạch sau nó — nhưng CHỈ nhóm có gạch (nhóm I); nhóm II/III gián tiếp giống
    trực tiếp. Phần đuôi (50, 60, 61, 70) không thuộc nhóm nào: 50 và 70 có
    công thức in. Mã số đuôi của B03 TT 99 là 50, 60, 61, 70 — đọc thẳng từ mẫu,
    nên "< 50" là ranh giới nhóm/đuôi."""
    out = []
    e1 = [c for c in (so_hoc.parse_printed_formula(r["chi_tieu"]) for r in rows) if c]
    out += [_rb(c) for c in e1]
    nhom: list[dict] = []

    def _dong_nhom() -> None:
        if not nhom:
            return
        tong = nhom[-1]
        assert tong["muc"] is None, tong
        thanh_phan = nhom[:-1]
        # Nhóm không có gạch đầu dòng (II/III của cả hai phương pháp): tổng = Σ
        # hàng số. Chỉ nhóm I gián tiếp mới có mốc + gạch.
        if not gian_tiep or not any(r["muc"] == "-" for r in thanh_phan):
            terms = [(r["ma_so"], 1) for r in thanh_phan]
            out.append(_rb(so_hoc.Constraint(tong["ma_so"], terms, "bang_tt"), "cau_truc_b03"))
            return
        moc: str | None = None
        gach: list[str] = []
        for r in thanh_phan:
            if r["muc"] == "-":
                gach.append(r["ma_so"])
            else:                                     # hàng số = mốc mới
                if moc is not None and gach:
                    out.append(_rb(so_hoc.Constraint(
                        r["ma_so"], [(moc, 1), *((g, 1) for g in gach)], "bang_tt"), "cau_truc_b03"))
                moc, gach = r["ma_so"], []
        assert moc is not None
        out.append(_rb(so_hoc.Constraint(
            tong["ma_so"], [(moc, 1), *((g, 1) for g in gach)], "bang_tt"), "cau_truc_b03"))

    for r in rows:
        if r["muc"] and re.match(r"^[IVX]+\.$", r["muc"]):
            _dong_nhom()                              # nhóm trước chưa có tổng: bỏ
            nhom = []
            continue
        if r["ma_so"] is None or so_hoc.ma_so_key(r["ma_so"])[0] >= 50:
            continue                                  # "2. Điều chỉnh..." / đuôi 50-70
        nhom.append(r)
        if r["muc"] is None:                          # tổng nhóm đóng nhóm
            _dong_nhom()
            nhom = []
    return out


def _rb(c: so_hoc.Constraint, nguon: str | None = None) -> dict:
    return {"tong": c.total, "cong": [[m, h] for m, h in c.terms], "nguon": nguon or c.source}


# B02-DN — GÕ TAY. Quan hệ theo hướng dẫn lập báo cáo kết quả kinh doanh TT
# 99/2025 (kế thừa TT 200); đối chiếu trên SCID tr16 (7/7 khớp tới đồng).
# 60 có HAI đồng nhất: theo cấu thành (50 - 51 - 52) và theo phân bổ (61 + 62).
_B02_TAY = [
    {"tong": "10", "cong": [["01", 1], ["02", -1]], "nguon": "tay"},
    {"tong": "20", "cong": [["10", 1], ["11", -1]], "nguon": "tay"},
    {"tong": "30", "cong": [["20", 1], ["21", 1], ["22", 1], ["23", -1], ["25", -1], ["26", -1], ["27", 1]], "nguon": "tay"},
    {"tong": "40", "cong": [["31", 1], ["32", -1]], "nguon": "tay"},
    {"tong": "50", "cong": [["30", 1], ["40", 1]], "nguon": "tay"},
    {"tong": "60", "cong": [["50", 1], ["51", -1], ["52", -1]], "nguon": "tay"},
    {"tong": "60", "cong": [["61", 1], ["62", 1]], "nguon": "tay"},
]
_B02_NHAN = {
    "01": "Doanh thu bán hàng và cung cấp dịch vụ", "02": "Các khoản giảm trừ doanh thu",
    "10": "Doanh thu thuần về bán hàng và cung cấp dịch vụ", "11": "Giá vốn hàng bán",
    "20": "Lợi nhuận gộp về bán hàng và cung cấp dịch vụ",
    "21": "Lãi/lỗ của hoạt động bán, thanh lý bất động sản đầu tư",
    "22": "Doanh thu hoạt động tài chính", "23": "Chi phí tài chính", "24": "Trong đó: chi phí đi vay",
    "25": "Chi phí bán hàng", "26": "Chi phí quản lý doanh nghiệp",
    "27": "Phần lãi hoặc lỗ trong công ty liên doanh, liên kết",
    "30": "Lợi nhuận thuần từ hoạt động kinh doanh", "31": "Thu nhập khác", "32": "Chi phí khác",
    "40": "Lợi nhuận khác", "50": "Tổng lợi nhuận kế toán trước thuế",
    "51": "Chi phí thuế thu nhập doanh nghiệp hiện hành", "52": "Chi phí thuế thu nhập doanh nghiệp hoãn lại",
    "60": "Lợi nhuận sau thuế thu nhập doanh nghiệp", "61": "Lợi nhuận sau thuế của công ty mẹ",
    "62": "Lợi nhuận sau thuế của cổ đông không kiểm soát",
    "70": "Lãi cơ bản trên cổ phiếu", "71": "Lãi suy giảm trên cổ phiếu",
}


def main() -> None:
    mau: dict = {}
    for ten, tep in FORMS.items():
        path = os.path.join(FORMS_DIR, tep)
        rows = _rows(path)
        if ten == "B01-DN":
            rb = _b01(rows)
        else:
            rb = _b03(rows, gian_tiep=ten.endswith("GT"))
        mau[ten] = {
            "nguon": f"{tep} sha256:{_sha(path)}",
            "nhan": {r["ma_so"]: r["chi_tieu"] for r in rows if r["ma_so"]},
            "rang_buoc": rb,
        }
        print(f"{ten}: {len(rows)} hàng, {len(rb)} ràng buộc "
              f"({sum(r['nguon'] == 'in_san' for r in rb)} in sẵn)")
    mau["B02-DN"] = {"nguon": "tay — không có mẫu docx; đối chiếu SCID tr16",
                     "nhan": _B02_NHAN, "rang_buoc": _B02_TAY}
    data = {"thong_tu": "99/2025/TT-BTC", "sinh_boi": "tools/derive_form_table.py",
            "ngay": date.today().isoformat(), "mau": mau}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("->", os.path.relpath(OUT))


if __name__ == "__main__":
    main()
