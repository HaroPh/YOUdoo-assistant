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


# --- (b) suy ràng buộc từ phân cấp đánh dấu ---------------------------------

_ROMAN_RE = re.compile(r"^(?=[IVX])M{0,3}(X{0,3})(IX|IV|V?I{0,3})$")


def _marker_level(muc) -> int | None:
    """Mức phân cấp của đánh dấu STT: 0 = chữ cái (A-/B-), 1 = la-mã (I./II.),
    2 = số (1./2.), 3 = không đánh dấu hoặc gạch đầu dòng (-). None = không
    hiểu được (không tham gia phân cấp)."""
    if muc is None:
        return 3
    s = str(muc).strip().rstrip(".-").strip()
    if not s:
        return 3                                  # "-" gạch đầu dòng -> như không đánh dấu
    if len(s) == 1 and s.isalpha() and s.isupper() and s not in "IVX":
        return 0
    if _ROMAN_RE.match(s):
        return 1
    if s.isdigit():
        return 2
    return None


def derive_hierarchy(rows: list[dict]) -> list[Constraint]:
    """Suy `cha = Σ con` từ đánh dấu STT, theo thứ tự hàng trên trang.

    Quy tắc: mỗi hàng là con của tổ tiên ĐANG MỞ gần nhất phía trên ở mức phân
    cấp nhỏ hơn — bất kể cách mấy bậc (chữ cái > la-mã > số > không đánh dấu).
    Nhảy bậc là chuyện thật trên mẫu TT 99 (xem chú thích trong vòng lặp). Hàng cha không có
    mã số (tiêu đề mục như "I. Hoạt động hành chính") vẫn giới hạn phạm vi con,
    nhưng không sinh ràng buộc vì không có ô tổng.

    Mọi hệ số là +1 — nên tầng này SAI trên báo cáo kết quả kinh doanh và lưu
    chuyển tiền (12 = 10 - 11). Spec giới hạn nó vào B01; phép đo Q1 chứng minh
    lý do bằng cách để nó FAIL trên SCID tr16/17.

    Chỉ sinh ràng buộc khi cha có >= 2 con — xem chú thích trong `_close`.
    Dư số đã biết: nếu một trang có HAI hàng không STT liền sau hàng số cuối
    (chưa gặp trên 10 trang), (b) vẫn có thể gán sai; (e1)/(c) đứng trước nó
    nên hàng TỔNG CỘNG có công thức in sẽ được ưu tiên đúng.

    Tầng ưu tiên THẤP NHẤT: chỉ điền chỗ (e1)/(c) chưa phủ. Và MÙ với hàng bị
    rơi: ràng buộc suy từ chính các hàng có mặt, nên VLM bỏ một hàng thành phần
    thì (b) chỉ thấy tổng lệch — không biết vì thiếu hàng. Chỉ (e1)/(c), tham
    chiếu mã số cố định, mới báo được `absent`.
    """
    # stack[level] = (ma_so hoặc None, list con). Chỉ giữ 4 mức.
    stack: list[tuple[str | None, list[str]] | None] = [None, None, None, None]
    parents: list[tuple[str, list[str]]] = []      # (ma_so cha, con) theo thứ tự gặp

    def _close(level: int) -> None:
        for lv in range(level, 4):
            if stack[lv] is not None:
                ma, con = stack[lv]
                # >= 2 con, có chủ ý: đo trên 10 trang đáp án (2026-09-11), ràng
                # buộc MỘT hạng tử chỉ tồn tại dưới dạng đồng nhất xuyên trang
                # (80 = tt107:50, 440 = 280) — không có tổng phụ nội trang nào
                # một con. Cho phép 1 con thì hàng TỔNG CỘNG (không STT) bị gán
                # làm con của hàng số cuối cùng → "74 = 80", "279 = 280",
                # "429 = 440" — ba ràng buộc SAI đo được trên B01 ở Q1.
                if ma is not None and len(con) >= 2:
                    parents.append((ma, con))
                stack[lv] = None

    for r in rows:
        lv = _marker_level(r.get("muc"))
        if lv is None:
            continue
        ma = r.get("ma_so")
        # Đóng mọi mức >= lv TRƯỚC khi gắn — anh em cùng mức đã xong.
        _close(lv)
        if lv > 0 and ma is not None:
            # Cha = tổ tiên ĐANG MỞ gần nhất ở BẤT KỲ mức nhỏ hơn — không phải
            # "đúng một bậc". Q1 đo được hai kiểu nhảy bậc trên B01 thật:
            # SCID tr13 IV.(240) rồi "-"(241, 242) — gạch đầu dòng thẳng dưới
            # la-mã, không qua mức số; SCID tr15 D-(400) rồi 1.(411)... — số
            # thẳng dưới chữ cái, không qua la-mã.
            for up in range(lv - 1, -1, -1):
                if stack[up] is not None:
                    # Không thêm cùng mã số hai lần: hàng lặp đã bị (e2) loại
                    # khỏi lookup, cộng nó hai lần chỉ làm ràng buộc sai và
                    # kéo cả cụm hàng đúng đi theo.
                    if str(ma) not in stack[up][1]:
                        stack[up][1].append(str(ma))
                    break
        if lv == 3:
            continue                      # hàng không đánh dấu không có con
        stack[lv] = (str(ma) if ma is not None else None, [])
    _close(0)
    return [Constraint(cha, [(c, 1) for c in con], "phan_cap") for cha, con in parents]


# --- (e2) bất biến cấu trúc — cổng chạy TRƯỚC số học ------------------------

_MA_SO_KEY_RE = re.compile(r"^(\d{1,3})([a-z]?)$")


def ma_so_key(ma) -> tuple[int, str] | None:
    """Khoá sắp xếp của mã số: `411a` -> (411, "a"); không hiểu -> None."""
    m = _MA_SO_KEY_RE.match(str(ma).strip()) if ma is not None else None
    return (int(m.group(1)), m.group(2)) if m else None


@dataclass(frozen=True)
class RowIssue:
    """Một vi phạm cấu trúc ở một hàng. `kind` là enum chuỗi nhỏ để log đếm được:
    `width` — thiếu ô so với cột khai báo;
    `bad_money` — ô tiền không đọc thành số (rác, chữ O thay 0, thiếu nhóm 3);
    `dup_ma_so` — mã số xuất hiện lần thứ hai (hàng lặp);
    `bad_ma_so` — mã số không đúng dạng `\\d{1,3}[a-z]?`;
    `non_monotonic` — mã số không lớn hơn hàng trước (hàng gộp, 13->18 đọc sai)."""
    index: int
    ma_so: str | None
    kind: str
    detail: str


def check_structure(rows: list[dict], value_columns: list[str]) -> list[RowIssue]:
    """(e2): bất biến rẻ, tất định, không cần ràng buộc nào.

    Đây là CỔNG chứ không phải ràng buộc: hàng `width`/`bad_money`/`dup_ma_so`/
    `bad_ma_so` bị loại ngay; `non_monotonic` trần cả trang ở `unverified`
    (không biết hàng nào lệch — hàng gộp là nguyên nhân dễ nhất). Mù với đọc
    sai giữ thứ tự (14 -> 15): đó là việc của số học.

    Hàng `ma_so` None (tiêu đề mục) không tham gia đơn điệu/trùng; ô null của
    nó không phải `bad_money` — null nghĩa là "không tồn tại ô" theo quy ước
    đáp án, khác chuỗi rác.
    """
    issues: list[RowIssue] = []
    seen: set[str] = set()
    prev: tuple[int, str] | None = None
    for i, r in enumerate(rows):
        ma = r.get("ma_so")
        ma_s = None if ma is None else str(ma)
        thieu = [c for c in value_columns if c not in r]
        if thieu:
            issues.append(RowIssue(i, ma_s, "width", f"thiếu cột {thieu}"))
        for c in value_columns:
            if c in r and r[c] is not None and parse_money(r[c]) is BAD:
                issues.append(RowIssue(i, ma_s, "bad_money", f"cột {c}: {r[c]!r}"))
        if ma_s is None:
            continue
        if ma_s in seen:
            # Hàng lặp là lỗi CÓ TÊN, loại riêng hàng đó; không để nó kích thêm
            # `non_monotonic` (14 sau 14) rồi trần cả trang vì một hàng lặp.
            issues.append(RowIssue(i, ma_s, "dup_ma_so", "mã số lặp"))
            continue
        seen.add(ma_s)
        k = ma_so_key(ma_s)
        if k is None:
            issues.append(RowIssue(i, ma_s, "bad_ma_so", "mã số không đúng dạng"))
            continue
        if prev is not None and k <= prev:
            issues.append(RowIssue(i, ma_s, "non_monotonic", f"{ma_s} sau {prev[0]}{prev[1]}"))
        prev = k
    return issues


# --- gộp ràng buộc từ nhiều tầng ---------------------------------------------

# Thứ tự ưu tiên theo spec: (e1) công thức in > (c) bảng thông tư > (b) phân cấp.
_SOURCE_RANK = {"in_san": 0, "bang_tt": 1, "phan_cap": 2, "dap_an": -1}


def merge_constraints(*groups: list[Constraint]) -> tuple[list[Constraint], list[tuple[Constraint, Constraint]]]:
    """Khử trùng THEO TỔNG: mỗi mã số tổng giữ một ràng buộc, tầng ưu tiên cao
    thắng. Trả thêm các cặp (thắng, thua) KHÁC thành phần — spec: "(e1) thắng
    khi cùng tổng khác thành phần → cảnh báo nêu cả hai"."""
    chon: dict[str, Constraint] = {}
    conflicts: list[tuple[Constraint, Constraint]] = []
    for c in sorted((c for g in groups for c in g), key=lambda c: _SOURCE_RANK[c.source]):
        cu = chon.get(c.total)
        if cu is None:
            chon[c.total] = c
        elif sorted(cu.terms) != sorted(c.terms):
            conflicts.append((cu, c))
    return list(chon.values()), conflicts


# --- trạng thái hàng + báo cáo trang ------------------------------------------

class RowStatus:
    REJECTED = "REJECTED"                   # không lưu
    VERIFIED = "vision_verified"            # mọi cột có số đều có >= 1 PASS phủ
    UNVERIFIED = "vision_unverified"        # còn lại
    LABEL = "label"                         # hàng tiêu đề, không có ô số


@dataclass(frozen=True)
class RowVerdict:
    index: int
    ma_so: str | None
    status: str
    reason: str = ""
    numeric: bool = False               # có >= 1 ô số nguyên (khác "-" và null)


@dataclass(frozen=True)
class PageReport:
    """Kết quả kiểm một trang — thứ `parse.py` biến thành `Warning` có tên và
    thứ test Q5/Q8 soi từng hàng. Không biết PDF, không biết DB."""
    rows: list[RowVerdict]
    evaluations: list[Evaluation]
    issues: list[RowIssue]
    capped_unverified: bool             # trang không đơn điệu -> trần cả trang
    conflicts: list[tuple[Constraint, Constraint]] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(r.status == status for r in self.rows)

    @property
    def summary(self) -> str:
        """Một dòng cho `Warning` — LUÔN phát, kể cả khi 0 hàng xác minh, để
        lượt 0/12 nhìn khác lượt 12/12."""
        co_so = sum(r.numeric for r in self.rows)
        gach = sum(r.status == RowStatus.UNVERIFIED and not r.numeric for r in self.rows)
        p = sum(e.verdict == Verdict.PASS for e in self.evaluations)
        f = sum(e.verdict == Verdict.FAIL for e in self.evaluations)
        na = sum(e.verdict == Verdict.NA for e in self.evaluations)
        s = (f"xác minh {self.count(RowStatus.VERIFIED)}/{co_so} hàng có số · "
             f"chưa xác minh {self.count(RowStatus.UNVERIFIED) - gach} · "
             f"toàn gạch ngang {gach} · "
             f"loại {self.count(RowStatus.REJECTED)} · "
             f"ràng buộc PASS {p} / FAIL {f} / NA {na}")
        if self.capped_unverified:
            s += " · mã số KHÔNG đơn điệu, cả trang trần unverified"
        return s


_REJECT_KINDS = frozenset({"width", "bad_money", "dup_ma_so", "bad_ma_so"})


def classify_rows(rows: list[dict], constraints: list[Constraint],
                  value_columns: list[str], *, strict_absent: bool = False,
                  conflicts: list[tuple[Constraint, Constraint]] | None = None) -> PageReport:
    """Quy tắc theo hàng của spec — tất định, khớp đầu tiên thắng:

    1. REJECTED: có ô BAD / sai độ rộng / trùng mã số; HOẶC được BẤT KỲ ràng
       buộc FAIL nào tham chiếu (tổng hay thành phần, bất kỳ cột) — cả cụm đi.
    2. vision_verified: có >= 1 ô số nguyên, và MỌI cột có số đều có >= 1 ràng
       buộc tham chiếu hàng PASS ở cột đó.
    3. vision_unverified: còn lại (0 ràng buộc phủ, toàn NA, toàn "-", hay trang
       không đơn điệu -> trần cả trang).

    Hàng không có mã số và không có ô số -> `label` (block nhãn thuần).
    Tesseract đồng ý KHÔNG nâng bậc (F1) — không có tham số nào cho nó ở đây.
    """
    issues = check_structure(rows, value_columns)
    capped = any(i.kind == "non_monotonic" for i in issues)
    reject_idx: dict[int, str] = {}
    for i in issues:
        if i.kind in _REJECT_KINDS:
            reject_idx.setdefault(i.index, f"{i.kind}: {i.detail}")

    # Hàng bị loại vì cấu trúc KHÔNG được tham gia lookup: một hàng lặp mã số
    # nếu vào lookup sẽ che hàng thật; một ô BAD đã là NA sẵn nhưng loại sớm
    # cho nhất quán.
    by_ma: dict[str, dict] = {}
    for i, r in enumerate(rows):
        if i in reject_idx or r.get("ma_so") is None:
            continue
        by_ma[str(r["ma_so"])] = r
    evaluations = [evaluate(c, by_ma.get, col, strict_absent=strict_absent)
                   for c in constraints for col in value_columns]

    # ma_so -> {cột có PASS}; và mã số chạm ràng buộc FAIL (cả cụm đi).
    pass_at: dict[str, set[str]] = {}
    fail_reason: dict[str, str] = {}
    for e in evaluations:
        refs = [e.constraint.total, *(m for m, _ in e.constraint.terms)]
        if e.verdict == Verdict.PASS:
            for m in refs:
                pass_at.setdefault(m, set()).add(e.column)
        elif e.verdict == Verdict.FAIL:
            lech = f"{e.delta:,}".replace(",", ".")
            ly_do = f"loại {len(refs)} hàng vì {e.reason} lệch {lech} ở cột {e.column}"
            for m in refs:
                fail_reason.setdefault(m, ly_do)

    out: list[RowVerdict] = []
    for i, r in enumerate(rows):
        ma = r.get("ma_so")
        ma_s = None if ma is None else str(ma)
        if i in reject_idx:
            out.append(RowVerdict(i, ma_s, RowStatus.REJECTED, reject_idx[i]))
            continue
        cells = {c: parse_money(r[c]) for c in value_columns if r.get(c) is not None}
        so_cot = [c for c, v in cells.items() if isinstance(v, int)]
        if ma_s is None and not so_cot:
            out.append(RowVerdict(i, None, RowStatus.LABEL))
            continue
        num = bool(so_cot)
        if ma_s is not None and ma_s in fail_reason:
            out.append(RowVerdict(i, ma_s, RowStatus.REJECTED, fail_reason[ma_s], num))
            continue
        if capped:
            out.append(RowVerdict(i, ma_s, RowStatus.UNVERIFIED, "trang không đơn điệu", num))
            continue
        if not num:
            out.append(RowVerdict(i, ma_s, RowStatus.UNVERIFIED, "không có ô số", False))
            continue
        thieu = [c for c in so_cot if c not in pass_at.get(ma_s or "", set())]
        if thieu:
            out.append(RowVerdict(i, ma_s, RowStatus.UNVERIFIED,
                                  f"không ràng buộc PASS nào phủ cột {thieu}", True))
            continue
        out.append(RowVerdict(i, ma_s, RowStatus.VERIFIED, numeric=True))
    return PageReport(rows=out, evaluations=evaluations, issues=issues,
                      capped_unverified=capped, conflicts=list(conflicts or []))
