"""Cổng số học cho bảng tài chính — TẤT ĐỊNH, không LLM, không nguồn ngoài.

Spec: docs/superpowers/specs/2026-09-11-ocr-bac-3-vlm-kiem-so-hoc-design.md.

Ý tưởng: một báo cáo tài chính TỰ MANG đáp án. Dòng tổng phải bằng tổng (có dấu)
các dòng thành phần. Ai đọc sai một ô — Tesseract, VLM, hay người — thì chuỗi
ràng buộc gãy ở đâu đó.

Vì sao module này nằm trong `src/` chứ không chỉ trong `tests/fixtures/`: VLM
(bậc 3) sẽ đọc cả SỐ trên trang Tesseract hỏng hẳn, và số đó chỉ được lưu khi
qua được cổng này. Bộ đánh giá trong production và bộ đánh giá canh đáp án
phải là MỘT — CLI `kiem_so_hoc.py` uỷ quyền lại cho đây, nên cổng 118/118 trên
đáp án đã duyệt cũng canh chính mã production. Hai thước là hai chỗ để lệch.

Module lá: import được từ bất cứ đâu, không kéo theo DB, PDF, hay LLM.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# --- ô tiền ------------------------------------------------------------------

class _Sentinel:
    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return self.name


# `DASH`: ô CÓ trên giấy nhưng in dấu gạch — bằng 0 về nghiệp vụ.
# `BAD`:  chuỗi không đọc thành số được — KHÔNG được coi là 0, không được đoán.
DASH = _Sentinel("DASH")
BAD = _Sentinel("BAD")

# Hình dạng in trên giấy của báo cáo tài chính Việt Nam: nhóm 3 chữ số cách
# nhau bằng dấu chấm, số âm trong ngoặc đơn. Bắt buộc đúng hình dạng này —
# một chuỗi 11 chữ số không dấu phân cách KHÔNG được nhận, vì mất luôn phép tự
# kiểm nhóm-3 (README ghi Tesseract đọc đúng 204/208 ô có dấu phân cách; số
# không phân cách là số đã bị rụng/ghép chữ số).
_MONEY_RE = re.compile(r"^\(?\d{1,3}(?:\.\d{3})*\)?$")
_DASHES = frozenset({"-", "–", "—"})


def parse_money(o) -> int | _Sentinel:
    """Ô tiền -> số nguyên | DASH | BAD.

    Nhận cả `int` (đáp án đã lưu số) lẫn chuỗi in nguyên văn (VLM trả về).
    `(x)` là số âm. Ngoặc lệch, chữ lẫn số, nhóm sai độ dài -> BAD.
    """
    if isinstance(o, bool):            # bool là int trong Python; chặn sớm
        return BAD
    if isinstance(o, int):
        return o
    if not isinstance(o, str):
        return BAD
    s = o.strip()
    if s in _DASHES:
        return DASH
    if not _MONEY_RE.match(s):
        return BAD
    am = s.startswith("(")
    if am != s.endswith(")"):
        return BAD
    so = int(s.strip("()").replace(".", ""))
    return -so if am else so


# --- ràng buộc ---------------------------------------------------------------

@dataclass(frozen=True)
class Constraint:
    """`total = Σ coef·term`. `source` nói ràng buộc từ đâu tới:
    `in_san` (công thức in trong nhãn), `bang_tt` (bảng thông tư), `phan_cap`
    (suy từ đánh dấu I./1.), `dap_an` (khai tường minh trong tệp đáp án)."""
    total: str
    terms: tuple[tuple[str, int], ...]
    source: str

    def __init__(self, total: str, terms, source: str) -> None:
        object.__setattr__(self, "total", total)
        object.__setattr__(self, "terms", tuple((str(m), int(h)) for m, h in terms))
        object.__setattr__(self, "source", source)

    def __eq__(self, other) -> bool:
        if isinstance(other, Constraint):
            return (self.total, self.terms, self.source) == (other.total, other.terms, other.source)
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.total, self.terms, self.source))


# --- (e1) công thức in sẵn trong nhãn ---------------------------------------

# Mã số: 2–3 chữ số, tuỳ ý một chữ thường theo sau (411a, 411b).
_MA_SO = r"\d{1,3}[a-z]?"
_TOKEN_RE = re.compile(rf"\s*({_MA_SO}|[+\-()])")
# Đầu công thức: "(50=" hoặc "(280 = ". Ngoặc đóng tương ứng tìm bằng ĐẾM ĐỘ
# SÂU, không bằng regex — regex không biết "(25+26)" nằm trong "(30 = ... - (25+26))".
_FORMULA_START_RE = re.compile(rf"\(\s*({_MA_SO})\s*=")


def _tokens(expr: str) -> list[str] | None:
    """Tách vế phải thành token. Trả None nếu gặp ký tự lạ."""
    out, pos = [], 0
    expr = expr.strip()
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if not m:
            return None
        out.append(m.group(1))
        pos = m.end()
    return out


def _parse_terms(tokens: list[str], i: int, sign: int) -> tuple[list[tuple[str, int]], int] | None:
    """Đệ quy: đọc dãy hạng tử tới hết hoặc tới `)`. Dấu trước ngoặc NHÂN vào
    mọi hạng tử bên trong — `- (25+26)` là -25 -26, không phải -25 +26."""
    terms: list[tuple[str, int]] = []
    pending = 1
    expect_term = True
    while i < len(tokens):
        t = tokens[i]
        if t == ")":
            if expect_term and terms:
                return None                       # "(... +)" — dấu treo
            return terms, i
        if t in "+-":
            if not expect_term:
                pending = 1 if t == "+" else -1
                expect_term = True
                i += 1
                continue
            # Dấu ngay đầu hoặc hai dấu liền: cho phép dấu đơn đầu vế
            pending = pending * (1 if t == "+" else -1)
            i += 1
            continue
        if t == "(":
            inner = _parse_terms(tokens, i + 1, sign * pending)
            if inner is None:
                return None
            sub, j = inner
            if j >= len(tokens) or tokens[j] != ")":
                return None                       # thiếu ngoặc đóng
            terms += sub
            i = j + 1
        else:
            terms.append((t, sign * pending))
            i += 1
        pending = 1
        expect_term = False
    if expect_term and terms:
        return None                               # kết thúc bằng dấu
    return terms, i


def parse_printed_formula(label: str) -> Constraint | None:
    """Nhãn -> ràng buộc, nếu nhãn IN kèm công thức kiểu `(50=01+05+...)`.

    Đây là tầng ràng buộc mạnh nhất: nó nằm trên giấy, do chính đơn vị in theo
    mẫu thông tư, không phải bảng ta nuôi cũng không phải LLM đoán. Parse tất
    định trong mã — KHÔNG hỏi model trích công thức ra (hỏi trích là hỏi diễn
    giải; ta muốn chép).

    Hỗ trợ dấu âm và ngoặc lồng có đổi dấu (TT 200 dòng 30:
    `30 = 20 + (21-22) + 24 - (25+26)`). Không có công thức -> None.
    """
    if not label:
        return None
    for m in _FORMULA_START_RE.finditer(label):
        # Tìm ngoặc đóng khớp với ngoặc mở ở m.start() bằng đếm độ sâu.
        depth, j = 1, m.end()
        while j < len(label) and depth:
            depth += {"(": 1, ")": -1}.get(label[j], 0)
            j += 1
        if depth:
            continue                              # không có ngoặc đóng khớp
        rhs = label[m.end():j - 1]
        toks = _tokens(rhs)
        if not toks:
            continue
        parsed = _parse_terms(toks, 0, 1)
        if parsed is None:
            continue
        terms, end = parsed
        if end != len(toks) or not terms:
            continue
        return Constraint(m.group(1), terms, "in_san")
    return None


# --- đánh giá một ràng buộc ở một cột ---------------------------------------

class Verdict:
    """PASS: Σ khớp tổng chính xác. FAIL: lệch, kèm độ lệch. NA: không đánh giá
    được — ô null/BAD/vắng — và NA KHÔNG BAO GIỜ được đọc là "qua"."""
    PASS = "PASS"
    FAIL = "FAIL"
    NA = "NA"


@dataclass(frozen=True)
class Evaluation:
    constraint: Constraint
    column: str
    verdict: str
    total_value: int | None = None
    computed: int | None = None
    delta: int | None = None            # total - computed, chỉ khi FAIL
    absent: tuple[str, ...] = ()        # thành phần VẮNG khỏi trang (chế độ lenient)
    reason: str = ""                    # vì sao NA, hoặc công thức khi FAIL

    def __post_init__(self) -> None:
        assert self.verdict in (Verdict.PASS, Verdict.FAIL, Verdict.NA)


def evaluate(c: Constraint, lookup, column: str, *, strict_absent: bool) -> Evaluation:
    """`lookup(ma_so) -> hàng | None`; hàng là dict `{cột: ô}`.

    `strict_absent=True` — ĐÁP ÁN: mọi hàng phải có mặt, thành phần vắng là NA.
    `strict_absent=False` — TRANG VLM: trang có thể bỏ hàng "-", thành phần vắng
    được tính bằng 0 NHƯNG ghi vào `absent` để người đọc thấy. Đây KHÔNG phải bẫy
    `null` README ghi (hàng tiêu đề bị cộng thành 0): ở đây là vắng-khỏi-trang,
    được đếm và báo — và một hàng KHÁC 0 bị rơi vẫn làm tổng lệch → FAIL.

    Ô `null` (không áp dụng) trong ràng buộc luôn là NA: một ràng buộc trỏ tới
    hàng tiêu đề là lỗi dữ liệu, không được lặng lẽ coi là 0.
    """
    hang_tong = lookup(c.total)
    if hang_tong is None:
        return Evaluation(c, column, Verdict.NA, reason=f"tổng {c.total} vắng")
    if column not in hang_tong:
        return Evaluation(c, column, Verdict.NA, reason=f"tổng {c.total} không có cột {column}")
    tong = parse_money(hang_tong[column])
    if tong is None or hang_tong[column] is None:
        return Evaluation(c, column, Verdict.NA, reason=f"tổng {c.total} là ô null")
    if tong is BAD:
        return Evaluation(c, column, Verdict.NA, reason=f"tổng {c.total} không đọc được")
    tong_v = 0 if tong is DASH else tong

    computed = 0
    absent: list[str] = []
    for ma, he_so in c.terms:
        hang = lookup(ma)
        if hang is None:
            if strict_absent:
                return Evaluation(c, column, Verdict.NA, reason=f"thành phần {ma} không tìm thấy")
            absent.append(ma)
            continue
        if column not in hang:
            return Evaluation(c, column, Verdict.NA, reason=f"thành phần {ma} không có cột {column}")
        o = hang[column]
        if o is None:
            return Evaluation(c, column, Verdict.NA, reason=f"thành phần {ma} là ô null (không áp dụng)")
        v = parse_money(o)
        if v is BAD:
            return Evaluation(c, column, Verdict.NA, reason=f"thành phần {ma} không đọc được: {o!r}")
        computed += he_so * (0 if v is DASH else v)

    cong_thuc = " ".join(("-" if h < 0 else "+") + m for m, h in c.terms).lstrip("+ ")
    if computed == tong_v:
        return Evaluation(c, column, Verdict.PASS, total_value=tong_v, computed=computed,
                          absent=tuple(absent))
    return Evaluation(c, column, Verdict.FAIL, total_value=tong_v, computed=computed,
                      delta=tong_v - computed, absent=tuple(absent),
                      reason=f"{c.total} = {cong_thuc}")
