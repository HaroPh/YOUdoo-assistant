# OCR bậc 2 — dựng bảng từ toạ độ chữ — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Từ toạ độ chữ Tesseract trả về, dựng lại lưới bảng `list[list[str]]`, để hàng bảng đọc-từ-ảnh đi vào corpus có cấu trúc cột thay vì một dòng phẳng.

**Architecture:** Một hàm thuần trong module lá `src/ocr/bang.py` biến `list[OcrWord]` thành lưới. Tín hiệu là **cụm căn lề** (mép trái cho cột chữ, mép phải cho cột số — nhưng để dữ liệu tự chọn mép nào chụm hơn, không gán cứng). Không có bộ dò bảng: trang không có cụm căn lề đủ mạnh tự nhiên ra một cột. Lưới đi tiếp qua `pdf_table.py` của B4 **không sửa một dòng nào** — module đó nhận đầu vào là lưới và không quan tâm lưới đến từ đâu.

**Tech Stack:** Python 3.11, `pytesseract` (đã có), `pypdfium2` (đã có), `pdfplumber` (đã có, chỉ dùng để sinh đáp án cho cổng A), `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-06-b5b-ocr-bac-2-dung-bang-design.md`
(spec cha: `docs/superpowers/specs/2026-09-04-tang-ocr-dung-chung-design.md`)

## Global Constraints

- **Bậc 2 chỉ lo CẤU TRÚC.** Trả lời "ô nào thuộc cột/hàng nào". Chữ sai trong ô là việc của bậc 1 và bậc 3 — không sửa chữ ở đây (spec §10).
- **KHÔNG sửa `backend/src/rag/pdf_table.py`.** Bậc 2 chỉ nối vào đầu vào của nó (spec §3).
- **KHÔNG dựng bộ dò bảng.** Suy biến về một cột là hành vi đúng cho trang văn xuôi (spec §4).
- **Tín hiệu là căn lề, KHÔNG phải khoảng trắng.** Cách khe-trắng-dọc đã đo và bác bỏ: trang 16 và 17 chỉ ra ĐÚNG MỘT khe cho bảng 5 cột. Bản vá "loại dòng chạy suốt" cũng hỏng: 0/4 trang loại được dòng nào (spec §2.1). Đừng thử lại.
- **Mọi tham số phải KHÔNG THỨ NGUYÊN**: dung sai theo *bề rộng ký tự trung vị*, ngưỡng ủng hộ theo *tỷ lệ số dòng*. Pixel là sai vì vỡ khi đổi DPI/cỡ chữ (spec §5).
- **Không hằng số nào được đặt trước khi đo.** Task 1 nhận tham số tường minh, không có mặc định. Task 2 đo trên 229 trang rồi mới chốt hằng số.
- ⚠️ **Bẫy tham số mặc định đóng băng.** Python tính giá trị mặc định MỘT LẦN lúc định nghĩa hàm. `def f(*, x=MODULE_CONST)` khiến việc đổi `MODULE_CONST` lúc chạy KHÔNG có tác dụng — đã cắn tầng OCR bậc 1 một lần và suýt vô hiệu hoá chính phép thử phá của nó. Luôn viết `x: T | None = None` rồi giải trong thân hàm.
- **`ARTIFACT_VERSION` 2 → 3** khi hình dạng vùng đổi (`document.py`). Đệm cũ tự lạc khoá qua dấu vân tay — không cần xoá tay.
- **Đường không-OCR phải BYTE-IDENTICAL.** Trang có lớp text không được đổi một bit nào.
- **Hỏng thì to tiếng nhưng không vỡ lượt nạp**: lùi về dòng phẳng + cảnh báo có tên qua `IngestReport`. Tệ nhất là mất cấu trúc, không mất nội dung (spec §9).
- **Định danh trong code bằng tiếng Anh hoặc không dấu.** Chú thích tiếng Việt có dấu thì được.
- **Lệnh pytest LUÔN kèm `-m "not integration and not live"`** trừ khi task nói khác. Lệnh trần từng gọi API thật và gây sự cố.
- Suite nền trước khi bắt đầu: **2409 passed, 1 skipped, 83 deselected**.

---

## Task 0: Nhánh làm việc

**Files:** không sửa gì.

- [ ] **Step 1: Tạo worktree riêng**

`main` đang ở `3d515ee`. KHÔNG thi hành trực tiếp trên `main`.

```bash
cd /d/Youdoo
git worktree add .claude/worktrees/ocr-bac-2 -b worktree-ocr-bac-2
```

Mọi lệnh từ đây chạy trong `/d/Youdoo/.claude/worktrees/ocr-bac-2`.

- [ ] **Step 2: Xác nhận suite nền xanh**

```bash
cd /d/Youdoo/.claude/worktrees/ocr-bac-2/backend
set -a; . <(grep -E '^(DATABASE_URL|RAG_SCHEMA|RAG_EMBED_PROVIDER|RAG_RERANK_ENABLED)=' /d/Youdoo/.env); set +a
export OLLAMA_URL=http://127.0.0.1:11435 PYTHONIOENCODING=utf-8
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q
```

Kỳ vọng: `2409 passed, 1 skipped, 83 deselected`. Khác con số này thì **dừng và báo** — nền đã trôi.

---

## Task 1: `bang.py` — hàm thuần dựng lưới

**Files:**
- Create: `backend/src/ocr/bang.py`
- Test: `backend/tests/ocr/test_bang.py`

**Interfaces:**
- Consumes: `src.ocr.engine.OcrWord` — `@dataclass(frozen=True)` với các trường `text: str`, `conf: float`, `left: int`, `top: int`, `width: int`, `height: int`, `line_id: tuple[int, int, int]`.
- Produces:
  - `be_rong_ky_tu(words: list[OcrWord]) -> float`
  - `@dataclass(frozen=True) class Moc: x: int; ben: str; do_manh: int`
  - `tim_moc_cot(words, *, dung_sai_ky_tu: float, ty_le_ung_ho: float) -> list[Moc]`
  - `dung_luoi(words, *, dung_sai_ky_tu: float, ty_le_ung_ho: float) -> list[list[str]]`
  - Cả ba tham số `dung_sai_ky_tu` / `ty_le_ung_ho` **bắt buộc, không có mặc định** ở task này. Task 2 mới thêm mặc định sau khi đo.

- [ ] **Step 1: Viết test thất bại cho đơn vị chuẩn hoá**

Tạo `backend/tests/ocr/test_bang.py`:

```python
"""Bậc 2 — dựng lưới từ toạ độ. Test trên từ DỰNG TAY, không chạy Tesseract:
hàm này phải thuần và kiểm được mà không cần binary nào."""
from src.ocr.bang import be_rong_ky_tu, dung_luoi, tim_moc_cot
from src.ocr.engine import OcrWord


def tu(text, left, top, width, height=20, line=0):
    """Dựng một OcrWord tối giản. `line_id` là (block, par, line) của
    Tesseract; ở đây chỉ cần hai từ cùng `line` là cùng hàng."""
    return OcrWord(text=text, conf=95.0, left=left, top=top,
                   width=width, height=height, line_id=(1, 1, line))


def test_be_rong_ky_tu_la_trung_vi_khong_phai_trung_binh():
    # "ab" rộng 20 -> 10/ký tự; "abcd" rộng 20 -> 5/ký tự; "abc" rộng 30 -> 10
    words = [tu("ab", 0, 0, 20), tu("abcd", 0, 0, 20), tu("abc", 0, 0, 30)]
    assert be_rong_ky_tu(words) == 10.0


def test_be_rong_ky_tu_khong_no_khi_khong_co_tu():
    assert be_rong_ky_tu([]) > 0
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

```bash
cd /d/Youdoo/.claude/worktrees/ocr-bac-2/backend
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_bang.py -q
```

Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'src.ocr.bang'`.

- [ ] **Step 3: Viết `be_rong_ky_tu`**

Tạo `backend/src/ocr/bang.py`:

```python
"""Bậc 2 của tầng OCR — dựng lại lưới bảng từ toạ độ chữ.

HÀM THUẦN: không đọc tệp, không gọi mạng, không biết gì về PDF. Vào là
`list[OcrWord]`, ra là `list[list[str]]`. Lưới đó đi tiếp qua `pdf_table.py`
của B4 — module đó nhận đầu vào là lưới và KHÔNG quan tâm lưới đến từ đâu,
nên hàng bảng đọc-từ-ảnh và đọc-từ-vector đi cùng một đường sau điểm này.

TÍN HIỆU LÀ CĂN LỀ, KHÔNG PHẢI KHOẢNG TRẮNG. Cách hiển nhiên hơn — tìm khe
trắng dọc suốt trang — đã đo và BÁC BỎ: trang 16 và 17 của BCTC scan thật chỉ
ra ĐÚNG MỘT khe cho bảng 5 cột, vì dòng tiêu đề chạy hết bề ngang bịt mọi khe.
Bản vá hiển nhiên (loại các dòng chạy suốt trước khi tính khe) cũng hỏng: 0/4
trang loại được dòng nào, vì văn xuôi cũng có khe giữa từ. Xem spec
`2026-09-06-b5b-ocr-bac-2-dung-bang-design.md` §2.1 — đừng thử lại.
"""
import statistics
from dataclasses import dataclass

from .engine import OcrWord


def be_rong_ky_tu(words: list[OcrWord]) -> float:
    """Bề rộng một ký tự, lấy TRUNG VỊ trên các từ.

    Đây là ĐƠN VỊ CHUẨN HOÁ của cả module. Mọi dung sai phải tính theo nó chứ
    không theo pixel: pixel vỡ ngay khi đổi DPI hoặc cỡ chữ, tức là vỡ đúng lúc
    đổi sang tài liệu định dạng khác (spec §5).

    Trung vị chứ không trung bình: một từ bị OCR đọc dính (bbox rộng, ít ký tự)
    kéo trung bình đi rất xa.
    """
    rong = [w.width / len(w.text) for w in words if w.text]
    if not rong:
        return 1.0          # không có từ nào: trả 1 để phép chia sau không nổ
    return statistics.median(rong)
```

- [ ] **Step 4: Chạy để xác nhận XANH**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_bang.py -q
```

Kỳ vọng: 2 passed.

- [ ] **Step 5: Viết test thất bại cho `tim_moc_cot`**

Thêm vào `backend/tests/ocr/test_bang.py`:

```python
def _bang_hai_cot_tien():
    """Ba hàng: nhãn căn TRÁI ở x=100, hai cột số căn PHẢI ở x=500 và x=800."""
    words = []
    for i, (nhan, a, b) in enumerate([("Tien", "1.000", "2.000"),
                                      ("Hang", "30.000", "40.000"),
                                      ("Khac", "500.000", "600.000")]):
        words.append(tu(nhan, 100, 100 + i * 30, 40, line=i))
        words.append(tu(a, 500 - len(a) * 10, 100 + i * 30, len(a) * 10, line=i))
        words.append(tu(b, 800 - len(b) * 10, 100 + i * 30, len(b) * 10, line=i))
    return words


def test_tim_moc_cot_bat_duoc_ca_moc_trai_lan_moc_phai():
    mocs = tim_moc_cot(_bang_hai_cot_tien(), dung_sai_ky_tu=0.5,
                       ty_le_ung_ho=0.6)
    # 3 cột: nhãn neo mép TRÁI ở 100; hai cột số neo mép PHẢI ở 500 và 800.
    assert [m.x for m in mocs] == [100, 500, 800]
    assert [m.ben for m in mocs] == ["trai", "phai", "phai"]


def test_van_xuoi_khong_can_le_ra_MOT_moc():
    """Không có bộ dò bảng: trang văn xuôi phải tự nhiên suy biến về một cột.
    Mỗi dòng bắt đầu ở một x khác nhau -> không cụm nào đủ ủng hộ."""
    words = [tu(f"dong{i}", 100 + i * 37, 100 + i * 30, 60, line=i)
             for i in range(6)]
    mocs = tim_moc_cot(words, dung_sai_ky_tu=0.5, ty_le_ung_ho=0.6)
    assert len(mocs) == 1
```

- [ ] **Step 6: Chạy để xác nhận ĐỎ**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_bang.py -q
```

Kỳ vọng: FAIL — `ImportError: cannot import name 'tim_moc_cot'`.

- [ ] **Step 7: Viết `Moc` và `tim_moc_cot`**

Thêm vào `backend/src/ocr/bang.py`:

```python
@dataclass(frozen=True)
class Moc:
    """Một mốc cột: vị trí, và MÉP NÀO của từ được neo vào nó."""
    x: int
    ben: str            # "trai" | "phai"
    do_manh: int        # số từ ủng hộ mốc này


def _cum(gia_tri: list[int], dung_sai: float) -> list[list[int]]:
    """Gom số gần nhau thành cụm, tham lam theo thứ tự tăng dần."""
    if not gia_tri:
        return []
    xong: list[list[int]] = [[sorted(gia_tri)[0]]]
    for v in sorted(gia_tri)[1:]:
        if v - xong[-1][-1] <= dung_sai:
            xong[-1].append(v)
        else:
            xong.append([v])
    return xong


def tim_moc_cot(words: list[OcrWord], *, dung_sai_ky_tu: float,
                ty_le_ung_ho: float) -> list[Moc]:
    """Tìm mốc cột bằng cụm CĂN LỀ.

    Cụm CẢ HAI mép rồi để dữ liệu tự nói mép nào chụm hơn. Cố ý KHÔNG gán cứng
    quy tắc "số căn phải, chữ căn trái" dù nó đúng trên BCTC Việt: đó là quy
    ước kế toán Việt/Âu, biểu mẫu khác có thể căn khác, và gán cứng là đưa một
    giả định định dạng vào lõi thuật toán (spec §4).

    `ty_le_ung_ho` là TỶ LỆ trên số dòng, không phải số tuyệt đối — cùng lý do
    dung sai không tính bằng pixel.
    """
    if not words:
        return []
    so_dong = len({w.line_id for w in words})
    toi_thieu = max(2, int(so_dong * ty_le_ung_ho))
    dung_sai = dung_sai_ky_tu * be_rong_ky_tu(words)

    ung_vien: list[Moc] = []
    for ben, lay in (("trai", lambda w: w.left),
                     ("phai", lambda w: w.left + w.width)):
        for c in _cum([lay(w) for w in words], dung_sai):
            if len(c) >= toi_thieu:
                ung_vien.append(Moc(x=int(statistics.median(c)), ben=ben,
                                    do_manh=len(c)))

    # Hai mép của CÙNG một cột đều có thể vượt ngưỡng (cột chữ hẹp, đều nhau).
    # Giữ mốc MẠNH HƠN, bỏ mốc yếu nằm trong dung sai của nó — nếu không, một
    # cột sẽ bị đếm hai lần và mọi từ trong đó bị tách đôi.
    ung_vien.sort(key=lambda m: (-m.do_manh, m.x))
    giu: list[Moc] = []
    for m in ung_vien:
        if all(abs(m.x - g.x) > dung_sai for g in giu):
            giu.append(m)

    if not giu:
        # Không cụm nào đủ ủng hộ = trang văn xuôi. MỘT cột, neo mép trái nhỏ
        # nhất. Đây là đường suy biến, KHÔNG phải lỗi — không có bộ dò bảng thì
        # không có gì để bắn nhầm (spec §4).
        return [Moc(x=min(w.left for w in words), ben="trai", do_manh=len(words))]
    return sorted(giu, key=lambda m: m.x)
```

- [ ] **Step 8: Chạy để xác nhận XANH**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_bang.py -q
```

Kỳ vọng: 4 passed.

- [ ] **Step 9: Viết test thất bại cho `dung_luoi`**

Thêm vào `backend/tests/ocr/test_bang.py`:

```python
def test_dung_luoi_tra_dung_luoi_ba_cot():
    luoi = dung_luoi(_bang_hai_cot_tien(), dung_sai_ky_tu=0.5,
                     ty_le_ung_ho=0.6)
    assert luoi == [["Tien", "1.000", "2.000"],
                    ["Hang", "30.000", "40.000"],
                    ["Khac", "500.000", "600.000"]]


def test_dung_luoi_noi_nhieu_tu_trong_cung_mot_o():
    """Nhãn nhiều từ phải thành MỘT ô, không phải nhiều cột."""
    words = []
    for i in range(3):
        words.append(tu("Tai", 100, 100 + i * 30, 30, line=i))
        words.append(tu("san", 140, 100 + i * 30, 30, line=i))
        words.append(tu("100", 500 - 30, 100 + i * 30, 30, line=i))
    luoi = dung_luoi(words, dung_sai_ky_tu=0.5, ty_le_ung_ho=0.6)
    assert luoi == [["Tai san", "100"]] * 3


def test_van_xuoi_ra_luoi_MOT_cot_giu_nguyen_tung_dong():
    words = [tu(f"dong{i}", 100 + i * 37, 100 + i * 30, 60, line=i)
             for i in range(6)]
    luoi = dung_luoi(words, dung_sai_ky_tu=0.5, ty_le_ung_ho=0.6)
    assert luoi == [[f"dong{i}"] for i in range(6)]


def test_dung_luoi_giu_thu_tu_doc_cua_tesseract_khong_sap_lai():
    """Bậc 1 đã ghi bài học: thứ tự đọc khác từng bị nhầm thành OCR kém. Hàng
    phải theo thứ tự `line_id` xuất hiện, không sắp lại theo toạ độ y."""
    words = [tu("sau", 100, 500, 40, line=1), tu("truoc", 100, 100, 40, line=0)]
    luoi = dung_luoi(words, dung_sai_ky_tu=0.5, ty_le_ung_ho=0.6)
    assert luoi == [["truoc"], ["sau"]]
```

- [ ] **Step 10: Chạy để xác nhận ĐỎ**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_bang.py -q
```

Kỳ vọng: FAIL — `ImportError: cannot import name 'dung_luoi'`.

- [ ] **Step 11: Viết `dung_luoi`**

Thêm vào `backend/src/ocr/bang.py`:

```python
def _cot_cua_tu(w: OcrWord, mocs: list[Moc]) -> int:
    """Chỉ số cột của một từ: mốc nào gần nhất, ĐO THEO MÉP CỦA CHÍNH MỐC ĐÓ."""
    def kc(m: Moc) -> int:
        cua_tu = w.left if m.ben == "trai" else w.left + w.width
        return abs(cua_tu - m.x)
    return min(range(len(mocs)), key=lambda i: kc(mocs[i]))


def dung_luoi(words: list[OcrWord], *, dung_sai_ky_tu: float,
              ty_le_ung_ho: float) -> list[list[str]]:
    """`list[OcrWord]` -> `list[list[str]]`.

    Hàng lấy theo `line_id` Tesseract đã trả sẵn, GIỮ NGUYÊN thứ tự xuất hiện.
    Không tự gom lại theo toạ độ y: tesseract gom tốt hơn, và bậc 1 đã ghi bài
    học "đừng sắp xếp lại thứ tự đọc" — khác biệt thứ tự đọc từng bị nhầm
    thành chất lượng OCR kém.
    """
    if not words:
        return []
    mocs = tim_moc_cot(words, dung_sai_ky_tu=dung_sai_ky_tu,
                       ty_le_ung_ho=ty_le_ung_ho)

    thu_tu: list[tuple] = []
    theo_dong: dict[tuple, list[OcrWord]] = {}
    for w in words:
        if w.line_id not in theo_dong:
            theo_dong[w.line_id] = []
            thu_tu.append(w.line_id)
        theo_dong[w.line_id].append(w)

    luoi: list[list[str]] = []
    for lid in thu_tu:
        o = [[] for _ in mocs]
        for w in sorted(theo_dong[lid], key=lambda x: x.left):
            o[_cot_cua_tu(w, mocs)].append(w.text)
        luoi.append([" ".join(p) for p in o])
    return luoi
```

- [ ] **Step 12: Chạy để xác nhận XANH**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_bang.py -q
```

Kỳ vọng: 8 passed.

- [ ] **Step 13: Commit**

```bash
git add backend/src/ocr/bang.py backend/tests/ocr/test_bang.py
git commit -m "feat(ocr): bac 2 - ham thuan dung luoi bang tu toa do chu

Tin hieu la CUM CAN LE, khong phai khoang trang (khe trang doc suot trang da
do va bac bo, spec muc 2.1). Cum CA HAI mep roi de du lieu tu chon mep nao
chum hon - khong gan cung 'so can phai, chu can trai' vi do la quy uoc ke toan
Viet/Au, khong tong quat.

KHONG co bo do bang: khong cum nao du ung ho thi suy bien ve MOT cot = hanh vi
hom nay cho trang van xuoi.

Tham so con BAT BUOC, chua co mac dinh - Task 2 do tren 229 trang roi moi chot.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: Hiệu chỉnh trên 229 trang, rồi mới chốt hằng số

**Files:**
- Create: `backend/tools/hieu_chinh_bang.py`
- Modify: `backend/src/ocr/bang.py` (thêm hằng số + mặc định)
- Test: `backend/tests/ocr/test_bang.py` (thêm test cho mặc định)

**Interfaces:**
- Consumes: `dung_luoi(words, *, dung_sai_ky_tu, ty_le_ung_ho)` từ Task 1.
- Produces: `DUNG_SAI_KY_TU: float`, `TY_LE_UNG_HO: float` trong `bang.py`; và `dung_luoi` / `tim_moc_cot` nhận thêm mặc định `None`.

- [ ] **Step 1: Viết script đo**

Tạo `backend/tools/hieu_chinh_bang.py`:

```python
"""Hiệu chỉnh tham số bậc 2 trên MỌI trang bảng vector của corpus.

Đáp án TỰ SINH: trang bảng vector rasterise ra ảnh, đọc lại bằng OCR, dựng
lưới, rồi so với lưới `pdfplumber` bóc từ CHÍNH trang đó. Không gõ tay ô nào,
và phủ nhiều định dạng — đúng chỗ yếu của việc hiệu chỉnh trên một tài liệu.

Chạy:  python -m tools.hieu_chinh_bang [so_trang_toi_da]
"""
import glob
import itertools
import os
import sys

import pdfplumber

from src.ocr import bang, engine
from src.ocr.document import _anh_cua_trang

THU_MUC = ["src/rag/seed/law", "../tmp-docs"]
DPI = 200


def _tu_trong_bbox(words, bbox, ty_le):
    """Chỉ giữ từ nằm trong khung bảng. `bbox` theo ĐIỂM (pdfplumber), toạ độ
    từ theo PIXEL ảnh — nhân `ty_le` = DPI/72 để về cùng hệ."""
    x0, top, x1, bot = (v * ty_le for v in bbox)
    return [w for w in words
            if x0 <= w.left and w.left + w.width <= x1
            and top <= w.top and w.top + w.height <= bot]


def _diem(dap_an: list[list], luoi: list[list[str]]) -> tuple[int, int]:
    """(số ô khớp, tổng ô có nội dung trong đáp án).

    So theo TẬP TỪ, không so nguyên văn: chữ đọc lệch là việc của tầng đọc
    (spec §2.4), cổng này chỉ hỏi ô có nằm đúng chỉ số (hàng, cột) không.
    """
    khop = tong = 0
    for i, hang in enumerate(dap_an):
        for j, o in enumerate(hang):
            muc = " ".join((o or "").split())
            if not muc:
                continue
            tong += 1
            if i < len(luoi) and j < len(luoi[i]):
                if set(muc.split()) == set(luoi[i][j].split()):
                    khop += 1
    return khop, tong


def main(argv):
    gioi_han = int(argv[1]) if len(argv) > 1 else 10**9
    tep = sorted(itertools.chain.from_iterable(
        glob.glob(os.path.join(t, "*.pdf")) for t in THU_MUC))

    luoi_tham_so = [(ds, tl) for ds in (0.3, 0.5, 0.8, 1.2)
                    for tl in (0.3, 0.5, 0.7)]
    diem = {k: [0, 0] for k in luoi_tham_so}
    da_lam = 0

    for p in tep:
        if da_lam >= gioi_han:
            break
        with pdfplumber.open(p) as pdf:
            for pageno, pg in enumerate(pdf.pages, 1):
                if da_lam >= gioi_han:
                    break
                bangs = pg.find_tables()
                if not bangs:
                    continue
                img = _anh_cua_trang(p, pageno, DPI)
                kq = engine.ocr_image(img)
                for b in bangs:
                    try:
                        dap_an = b.extract()
                    except Exception:
                        continue
                    ws = _tu_trong_bbox(kq.words, b.bbox, DPI / 72)
                    if not ws:
                        continue
                    for ds, tl in luoi_tham_so:
                        luoi = bang.dung_luoi(ws, dung_sai_ky_tu=ds,
                                              ty_le_ung_ho=tl)
                        k, t = _diem(dap_an, luoi)
                        diem[(ds, tl)][0] += k
                        diem[(ds, tl)][1] += t
                da_lam += 1
                print(f"  {os.path.basename(p)[:34]:36s} tr{pageno:>3}"
                      f"  ({da_lam} trang)", flush=True)

    print(f"\n{'dung_sai':>10}{'ty_le':>8}{'khop':>9}{'tong':>9}{'ty le':>9}")
    for (ds, tl), (k, t) in sorted(diem.items(), key=lambda x: -x[1][0] / max(x[1][1], 1)):
        print(f"{ds:>10}{tl:>8}{k:>9}{t:>9}{k / max(t, 1):>9.4f}")


if __name__ == "__main__":
    main(sys.argv)
```

- [ ] **Step 2: Chạy đo trên một tập nhỏ trước để bắt lỗi script**

```bash
cd /d/Youdoo/.claude/worktrees/ocr-bac-2/backend
export PYTHONIOENCODING=utf-8 OMP_THREAD_LIMIT=1
/d/Youdoo/backend/.venv/Scripts/python.exe -m tools.hieu_chinh_bang 5
```

Kỳ vọng: in 5 dòng tiến trình rồi một bảng 12 dòng tham số với tỷ lệ khớp. Nếu mọi tỷ lệ = 0,0000 thì **dừng** — script sai, không phải thuật toán sai.

- [ ] **Step 3: Chạy đo đầy đủ**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m tools.hieu_chinh_bang \
  > /tmp/hieu_chinh_bang.txt 2>&1
tail -20 /tmp/hieu_chinh_bang.txt
```

Mất khoảng 12–15 phút (229 trang × ~3 s OCR). Chạy nền được.

- [ ] **Step 4: Chốt hằng số từ số đo**

Lấy cặp `(dung_sai, ty_le)` có tỷ lệ khớp cao nhất. Ghi **con số thật đo được** vào chú thích — không làm tròn cho đẹp, không lấy số từ plan này.

Thêm vào đầu `backend/src/ocr/bang.py`, ngay sau phần import:

```python
# ĐO 2026-09-06 trên toàn bộ trang bảng vector của corpus (106 tệp, 229 trang,
# 31.416 ô) — đáp án tự sinh từ `pdfplumber` bóc chính trang đó. Quét lưới
# 4x3 tham số, chọn cặp có tỷ lệ ô khớp cao nhất.
#
# THAY <...> BẰNG SỐ THẬT TỪ `tools/hieu_chinh_bang.py`. Không được để nguyên.
#   dung_sai=<a> ty_le=<b> -> <x>/<y> = <z>   <- chọn
#   (dán trọn bảng 12 dòng vào đây để người sau so lại được)
#
# ĐƠN VỊ KHÔNG THỨ NGUYÊN, có chủ ý: dung sai theo BỀ RỘNG KÝ TỰ TRUNG VỊ và
# ngưỡng theo TỶ LỆ SỐ DÒNG. Pixel vỡ ngay khi đổi DPI hoặc cỡ chữ, tức là vỡ
# đúng lúc đổi sang tài liệu định dạng khác (spec §5).
DUNG_SAI_KY_TU = <a>
TY_LE_UNG_HO = <b>
```

- [ ] **Step 5: Viết test cho đường mặc định**

Thêm vào `backend/tests/ocr/test_bang.py`:

```python
def test_mac_dinh_doc_lai_hang_so_luc_GOI_khong_dong_bang_luc_dinh_nghia():
    """Bẫy tham số mặc định đóng băng: Python tính giá trị mặc định MỘT LẦN lúc
    định nghĩa hàm. Nếu viết `def f(*, x=HANG_SO)` thì đổi HANG_SO lúc chạy sẽ
    KHÔNG có tác dụng — đã cắn tầng OCR bậc 1 một lần và suýt vô hiệu hoá chính
    phép thử phá của nó. Test này gác đúng chuyện đó."""
    from src.ocr import bang as m

    words = _bang_hai_cot_tien()
    goc = m.TY_LE_UNG_HO
    try:
        m.TY_LE_UNG_HO = 0.99      # gần như không cụm nào đủ ủng hộ
        it_cot = m.dung_luoi(words)
        m.TY_LE_UNG_HO = 0.1       # dễ dãi
        nhieu_cot = m.dung_luoi(words)
    finally:
        m.TY_LE_UNG_HO = goc
    assert len(it_cot[0]) < len(nhieu_cot[0]), (
        "đổi hằng số lúc chạy KHÔNG đổi kết quả -> mặc định đã bị đóng băng")
```

- [ ] **Step 6: Chạy để xác nhận ĐỎ**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_bang.py -q
```

Kỳ vọng: FAIL — `TypeError: dung_luoi() missing 2 required keyword-only arguments`.

- [ ] **Step 7: Thêm mặc định GIẢI LÚC GỌI**

Sửa chữ ký hai hàm trong `backend/src/ocr/bang.py`:

```python
def tim_moc_cot(words: list[OcrWord], *, dung_sai_ky_tu: float | None = None,
                ty_le_ung_ho: float | None = None) -> list[Moc]:
```

và ngay đầu thân hàm, TRƯỚC mọi dòng khác:

```python
    # Giải lúc GỌI, không dùng hằng số làm giá trị mặc định — xem test
    # `test_mac_dinh_doc_lai_hang_so_luc_GOI...` và bẫy đã cắn bậc 1.
    dung_sai_ky_tu = DUNG_SAI_KY_TU if dung_sai_ky_tu is None else dung_sai_ky_tu
    ty_le_ung_ho = TY_LE_UNG_HO if ty_le_ung_ho is None else ty_le_ung_ho
```

Làm y hệt cho `dung_luoi` (nó chỉ chuyển tiếp xuống `tim_moc_cot`, nhưng vẫn phải nhận `None` để người gọi không phải truyền).

- [ ] **Step 8: Chạy để xác nhận XANH**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_bang.py -q
```

Kỳ vọng: 9 passed.

- [ ] **Step 9: Commit**

```bash
git add backend/src/ocr/bang.py backend/tests/ocr/test_bang.py backend/tools/hieu_chinh_bang.py
git commit -m "feat(ocr): hieu chinh tham so bac 2 tren 229 trang bang vector

Dap an TU SINH: rasterise trang bang vector, doc lai bang OCR, so luoi voi
luoi pdfplumber boc tu chinh trang do. Phu nhieu dinh dang (phu luc luat, bieu
mau BCTC, 100 hoa don, bieu mau SSC, so tay tieng Anh) - dung cho yeu cua viec
hieu chinh tren mot tai lieu.

Quet luoi 4x3 tham so, chot cap co ty le o khop cao nhat. So do that dan tron
vao chu thich de nguoi sau so lai duoc.

Mac dinh GIAI LUC GOI (param=None roi resolve trong than ham), co test gac:
bay tham so mac dinh dong bang da can tang OCR bac 1 mot lan va suyt vo hieu
hoa chinh phep thu pha cua no.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Cổng A — tự nuôi, đa định dạng, chạy trong suite

**Files:**
- Create: `backend/tests/ocr/test_cong_bang_vector.py`

**Interfaces:**
- Consumes: `bang.dung_luoi(words)` (mặc định đã chốt ở Task 2); `src.ocr.document._anh_cua_trang(path, pageno, dpi)`; `src.ocr.engine.ocr_image(img)`.
- Produces: hằng số `NGUONG_KHOP` trong tệp test — suy từ số đo, không đặt trước.

- [ ] **Step 1: Viết cổng**

Tạo `backend/tests/ocr/test_cong_bang_vector.py`:

```python
"""Cổng A của bậc 2 — TỰ NUÔI, đa định dạng.

Cơ chế: lấy trang bảng VECTOR (pdfplumber bóc được) → rasterise → vứt lớp text
→ dựng lưới bằng bậc 2 → so với lưới pdfplumber bóc từ CHÍNH trang đó. Đáp án
tự sinh, không gõ tay ô nào.

Vì sao cần cổng này bên cạnh cổng scan thật: cổng kia chỉ có MỘT tài liệu, một
định dạng. Cổng này phủ phụ lục luật, biểu mẫu BCTC, hoá đơn, biểu mẫu SSC và
sổ tay tiếng Anh.

GIỚI HẠN nói thẳng: ảnh rasterise SẠCH HƠN scan đời thật — giống hệt giới hạn
của cổng tự nuôi bậc 1. Cổng này chứng minh "còn sống và đại khái đúng trên
nhiều định dạng", KHÔNG chứng minh "chịu được scan đời thật".
"""
import os

import pdfplumber
import pytest

from src.ocr import bang
from src.ocr.document import _anh_cua_trang
from src.ocr.engine import ocr_image, tesseract_path

DPI = 200

# NGƯỠNG ĐO ĐƯỢC — thay <n> bằng số thật từ Step 3, KHÔNG để nguyên.
# Cách suy giữ nguyên như bậc 1: làm tròn xuống hai chữ số của
# (giá trị nhỏ nhất quan sát được − 0,05). Biên 0,05 chỉ để chịu sai khác
# máy/phiên bản tesseract, KHÔNG để che một hồi quy thật.
NGUONG_KHOP = <n>

# Tập con đủ nhanh cho suite đơn vị, chọn để mỗi dòng là một ĐỊNH DẠNG khác
# nhau — không phải 6 trang cùng một biểu mẫu.
TAP_TRANG = [
    ("src/rag/seed/law/luat-dautu.pdf", 38),
    ("src/rag/seed/law/luat-thuexuatnhapkhau.pdf", 14),
    ("../tmp-docs/bieumau_bctc_hopnhat.pdf", 3),
    ("../tmp-docs/ssc_bieumau.pdf", 2),
    ("../tmp-docs/invoice_51109301.pdf", 1),
    ("../tmp-docs/USA_Employee_Handbook-Freely_Available.pdf", 5),
]


def _tu_trong_bbox(words, bbox, ty_le):
    x0, top, x1, bot = (v * ty_le for v in bbox)
    return [w for w in words
            if x0 <= w.left and w.left + w.width <= x1
            and top <= w.top and w.top + w.height <= bot]


def _ty_le_khop(dap_an, luoi) -> tuple[int, int]:
    """So theo TẬP TỪ, không nguyên văn: chữ đọc lệch là việc của tầng đọc,
    cổng này chỉ hỏi ô có nằm đúng chỉ số (hàng, cột) không."""
    khop = tong = 0
    for i, hang in enumerate(dap_an):
        for j, o in enumerate(hang):
            muc = " ".join((o or "").split())
            if not muc:
                continue
            tong += 1
            if i < len(luoi) and j < len(luoi[i]) \
                    and set(muc.split()) == set(luoi[i][j].split()):
                khop += 1
    return khop, tong


@pytest.mark.skipif(tesseract_path() is None, reason="chua cai tesseract")
@pytest.mark.parametrize("tep,trang", TAP_TRANG)
def test_dung_lai_bang_tu_anh_khop_luoi_vector(tep, trang):
    if not os.path.isfile(tep):
        pytest.skip(f"khong co {tep}")
    with pdfplumber.open(tep) as pdf:
        bangs = pdf.pages[trang - 1].find_tables()
        assert bangs, f"{tep} tr{trang}: pdfplumber khong thay bang -> chon lai trang"
        dap_an = bangs[0].extract()
        bbox = bangs[0].bbox

    kq = ocr_image(_anh_cua_trang(tep, trang, DPI))
    ws = _tu_trong_bbox(kq.words, bbox, DPI / 72)
    assert ws, "khong tu nao nam trong khung bang -> bbox hoac ty le sai"

    khop, tong = _ty_le_khop(dap_an, bang.dung_luoi(ws))
    assert tong > 0, "dap an khong co o nao co noi dung -> chon lai trang"
    ty_le = khop / tong
    assert ty_le >= NGUONG_KHOP, (
        f"{os.path.basename(tep)} tr{trang}: {khop}/{tong} = {ty_le:.4f} "
        f"< nguong {NGUONG_KHOP}")
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ (ngưỡng chưa có)**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_cong_bang_vector.py -q
```

Kỳ vọng: FAIL khi thu thập — `NameError` / `SyntaxError` vì `<n>` chưa thay.

- [ ] **Step 3: Đo tỷ lệ thật trên 6 trang rồi chốt ngưỡng**

Đặt tạm `NGUONG_KHOP = 0.0` và thêm một dòng in ngay TRƯỚC `assert ty_le >=`:

```python
    print(f"\n{os.path.basename(tep)} tr{trang}: {khop}/{tong} = {ty_le:.4f}")
```

Chạy với `-s` để thấy nó:

```bash
export PYTHONIOENCODING=utf-8 OMP_THREAD_LIMIT=1
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest   tests/ocr/test_cong_bang_vector.py -q -s
```

Ghi lại 6 con số. **Giữ nguyên dòng in** — nó có ích mỗi lần cổng đỏ. Rồi đặt:

`NGUONG_KHOP = làm tròn xuống 2 chữ số của (min(6 con số) − 0.05)`

Dán cả 6 con số vào chú thích trên `NGUONG_KHOP`.

Nếu con số nhỏ nhất **dưới 0,5**, dừng và báo: một định dạng đang hỏng nặng,
cần xem trước khi chốt ngưỡng thấp che nó.

- [ ] **Step 4: Chạy để xác nhận XANH**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_cong_bang_vector.py -q
```

Kỳ vọng: 6 passed.

- [ ] **Step 5: THỬ PHÁ — cổng phải biết đỏ**

Cổng chưa từng thấy đỏ thì chưa được tin. Ép `TY_LE_UNG_HO` lên 0,99 (gần như
không cụm nào đủ ủng hộ ⇒ mọi bảng suy biến về một cột):

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0, '.')
from src.ocr import bang
bang.TY_LE_UNG_HO = 0.99
import pytest
sys.exit(pytest.main(['tests/ocr/test_cong_bang_vector.py', '-q']))
"
```

Kỳ vọng: **FAIL** ở phần lớn tham số hoá. Nếu vẫn xanh thì cổng không đo gì —
**dừng và báo**, đừng đi tiếp.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/ocr/test_cong_bang_vector.py
git commit -m "test(ocr): cong A - tu nuoi da dinh dang cho bac 2

Trang bang VECTOR rasterise -> dung luoi bang bac 2 -> so voi luoi pdfplumber
boc tu chinh trang do. Dap an tu sinh, khong go tay o nao.

6 trang, moi trang mot DINH DANG khac nhau (phu luc luat, bieu thue, bieu mau
BCTC, bieu mau SSC, hoa don, so tay tieng Anh) - khong phai 6 trang cung mot
bieu mau.

So theo TAP TU chu khong nguyen van: chu doc lech la viec cua tang doc, cong
nay chi hoi o co nam dung chi so (hang, cot) khong.

Nguong suy tu so do that (lam tron xuong cua min - 0,05), da THU PHA bang cach
ep TY_LE_UNG_HO=0.99 va xac nhan cong do.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Cổng B — scan thật, dùng lại cổng số học đã duyệt

**Files:**
- Create: `backend/tests/ocr/test_cong_bang_scan_that.py`

**Interfaces:**
- Consumes: `bang.dung_luoi(words)`; `src.ocr.document.read_page(path, pageno)`; các tệp đáp án `backend/tests/fixtures/ocr_bang_that/SCID_2026H1_tr{12..18}.json` (trạng thái `DA_DUYET`).
- Produces: không có gì cho task sau.

- [ ] **Step 1: Viết cổng**

Tạo `backend/tests/ocr/test_cong_bang_scan_that.py`:

```python
"""Cổng B của bậc 2 — SCAN THẬT.

Cổng A chứng minh bậc 2 chạy trên nhiều định dạng, nhưng trên ảnh rasterise
SẠCH. Cổng này chạy trên bản scan đời thật duy nhất đang có (BCTC hợp nhất bán
niên SCID, 150 DPI, 0 ký tự lớp text), đối chiếu với đáp án ĐÃ DUYỆT.

KHÔNG cần đặt tên cột. Với mỗi hàng trong đáp án, chỉ hỏi: các giá trị của nó
có rơi vào CÙNG MỘT hàng đầu ra không. Dựng sai cột là gãy ngay, mà không phải
suy diễn cột nào là cột nào — tránh được một tầng suy diễn có thể tự nó sai.

HAI LOẠI ĐỎ, phải phân biệt được:
  (a) bậc 2 dựng sai cột      -> LỖI CỦA TASK NÀY
  (b) tầng đọc đọc sai chữ    -> KHÔNG phải lỗi bậc 2 (spec §2.4: Tesseract sai
      3/14 cột Mã số hai chữ số). Nếu không phân biệt, cổng sẽ đỏ oan vài lần
      rồi có người tắt nó — mà cổng bị tắt thì bằng không.
Cách phân biệt: chỉ tính những giá trị mà tầng đọc ĐỌC ĐƯỢC (xuất hiện đâu đó
trong text phẳng của trang). Giá trị tầng đọc đã đọc hỏng thì bỏ khỏi mẫu số và
ĐẾM RA, không âm thầm bỏ qua.
"""
import glob
import json
import os

import pytest

from src.ocr import bang
from src.ocr.document import read_page
from src.ocr.engine import OcrWord, tesseract_path

PDF = ("D:/downloads/SID_000000016657191_01VI_BaoCaoTaiChinhBanNien_HopNhat"
       "_SoatXet_2026_signed_05092026111802.pdf")
DAP_AN = "tests/fixtures/ocr_bang_that"

# NGƯỠNG ĐO ĐƯỢC — thay <m> bằng số thật từ Step 3, KHÔNG để nguyên.
NGUONG_CUNG_HANG = <m>


def _vn(n: int) -> str:
    s = f"{abs(n):,}".replace(",", ".")
    return f"({s})" if n < 0 else s


def _cac_tep_dap_an():
    return sorted(glob.glob(os.path.join(DAP_AN, "SCID_2026H1_tr*.json")))


@pytest.mark.skipif(tesseract_path() is None, reason="chua cai tesseract")
@pytest.mark.skipif(not os.path.isfile(PDF), reason="khong co ban scan that")
@pytest.mark.parametrize("duong", _cac_tep_dap_an())
def test_gia_tri_cung_hang_van_cung_hang_sau_khi_dung_lai(duong):
    d = json.load(open(duong, encoding="utf-8"))
    assert d["trang_thai"] == "DA_DUYET", f"{duong} chua duoc duyet"
    cots = [c for c in d["cot"]
            if c not in ("muc", "chi_tieu", "ma_so", "thuyet_minh")]

    kq = read_page(PDF, d["trang_pdf"])
    tho = kq.text
    luoi = bang.dung_luoi([
        OcrWord(text=w["t"], conf=w["c"], left=w["l"], top=w["y"],
                width=w["w"], height=w["h"], line_id=tuple(w["g"]))
        for r in kq.regions for w in r.words])

    cung_hang = tong = bo_qua = 0
    for h in d["hang"]:
        muc = [_vn(h[c]) for c in cots if isinstance(h.get(c), int)]
        if len(muc) < 2:
            continue                      # cần >=2 giá trị mới nói được "cùng hàng"
        if any(m not in tho for m in muc):
            bo_qua += 1                   # tầng đọc đọc hỏng -> KHÔNG tính vào mẫu số
            continue
        tong += 1
        if any(all(m in " ".join(hang) for m in muc) for hang in luoi):
            cung_hang += 1

    print(f"\n{os.path.basename(duong)}: {cung_hang}/{tong} hang giu nguyen "
          f"({bo_qua} hang bo qua vi TANG DOC doc hong, khong phai loi bac 2)")
    assert tong > 0, "khong hang nao du dieu kien -> phep do nay khong do gi"
    assert cung_hang / tong >= NGUONG_CUNG_HANG
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_cong_bang_scan_that.py -q
```

Kỳ vọng: FAIL khi thu thập vì `<m>` chưa thay.

- [ ] **Step 3: Đo rồi chốt ngưỡng**

Tạm đặt `NGUONG_CUNG_HANG = 0.0`, chạy `pytest ... -s` và đọc 7 dòng in ra. Đặt:

`NGUONG_CUNG_HANG = làm tròn xuống 2 chữ số của (min(7 tỷ lệ) − 0.05)`

Dán cả 7 con số vào chú thích. Nếu con số nhỏ nhất **dưới 0,5**, dừng và báo.

- [ ] **Step 4: Chạy để xác nhận XANH**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_cong_bang_scan_that.py -q
```

Kỳ vọng: 7 passed.

- [ ] **Step 5: THỬ PHÁ**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0, '.')
from src.ocr import bang
bang.DUNG_SAI_KY_TU = 100.0     # dung sai khong lo -> moi tu vao cung mot cot
import pytest
sys.exit(pytest.main(['tests/ocr/test_cong_bang_scan_that.py', '-q']))
"
```

Kỳ vọng: **FAIL**. Vẫn xanh thì cổng không đo gì — dừng và báo.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/ocr/test_cong_bang_scan_that.py
git commit -m "test(ocr): cong B - bac 2 tren ban scan doi that

Doi chieu voi dap an DA DUYET (7 trang BCTC SCID, trang thai DA_DUYET).
KHONG dat ten cot: chi hoi cac gia tri cua mot hang co roi vao CUNG MOT hang
dau ra khong - dung sai cot la gay ngay, ma khong phai suy dien cot nao la
cot nao.

Phan biet HAI LOAI DO: gia tri ma tang doc doc hong bi loai khoi mau so va
DEM RA, khong am tham bo qua. Khong phan biet thi cong se do oan vai lan roi
co nguoi tat no, ma cong bi tat thi bang khong.

Nguong suy tu so do that, da THU PHA bang DUNG_SAI_KY_TU=100.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Nối vào `document.py` và `parse.py`

**Files:**
- Modify: `backend/src/ocr/document.py` (`ARTIFACT_VERSION`, `Region`, `read_page`, `_tu_json`)
- Modify: `backend/src/rag/parse.py` (`_doc_trang_bang_anh` và nhánh dùng nó)
- Test: `backend/tests/ocr/test_document.py`, `backend/tests/rag/test_parse_pdf_ocr.py`

**Interfaces:**
- Consumes: `bang.dung_luoi(words)`; `src.rag.pdf_table.{split_header_body, column_names, row_to_text}`.
- Produces: `Region.luoi: list[list[str]]` (rỗng cho vùng `text`); `_doc_trang_bang_anh` trả thêm phần tử lưới.

- [ ] **Step 1: Viết test thất bại cho hình dạng artifact mới**

Thêm vào `backend/tests/ocr/test_document.py`:

```python
def test_artifact_version_da_len_3_va_region_mang_luoi():
    """Hình dạng vùng đổi (thêm `luoi`) thì ARTIFACT_VERSION PHẢI tăng, nếu
    không đệm cũ sẽ được đọc lại dưới hình dạng mới và sai âm thầm."""
    from src.ocr import document
    assert document.ARTIFACT_VERSION == 3
    r = document.Region(kind="text", text="x", mean_conf=90.0,
                        bbox=(0, 0, 10, 10))
    assert r.luoi == []
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_document.py -q
```

Kỳ vọng: FAIL — `assert 2 == 3`.

- [ ] **Step 3: Sửa `document.py`**

Trong `backend/src/ocr/document.py`:

Đổi khối chú thích + hằng số:

```python
# 3 (2026-09-06, bậc 2): vùng mang thêm trường "luoi" (lưới bảng dựng từ toạ
# độ). Hình dạng artifact đã đổi, phải bump — đệm cũ tự lạc khoá qua dấu vân
# tay, không cần xoá tay.
ARTIFACT_VERSION = 3
```

Thêm trường vào `Region` (SAU `words` để không đổi thứ tự tham số vị trí đang dùng):

```python
    luoi: list[list[str]] = field(default_factory=list)   # bậc 2; rỗng nếu chưa dựng
    luoi_loi: str | None = None    # lý do dựng lưới hỏng; None = không hỏng
```

`luoi_loi` tồn tại để lỗi **đi tiếp được** thay vì chết tại chỗ: `document.py`
là module lá, không biết `IngestReport`, nên nó ghi lý do, còn `parse.py` mới
biến nó thành cảnh báo có tên. Không có trường này thì bậc 2 hỏng sẽ **im
lặng** — đúng thứ "hỏng lớn tiếng còn hơn thiếu âm thầm" cấm.

Trong `read_page`, sau `kq = engine.ocr_image(img)`, thêm:

```python
    # Bậc 2: dựng lưới từ toạ độ. Hỏng thì KHÔNG làm vỡ lượt đọc — mất cấu
    # trúc còn hơn mất nội dung (spec §9). Nhưng KHÔNG được nuốt im lặng: ghi
    # lý do vào artifact để `parse.py` biến nó thành cảnh báo CÓ TÊN. Tầng này
    # là module lá, không biết `IngestReport`, nên nó chỉ ghi — không tự báo.
    try:
        luoi, luoi_loi = bang.dung_luoi(kq.words), None
    except Exception as e:                               # noqa: BLE001
        luoi, luoi_loi = [], f"{type(e).__name__}: {e}"
```

Đưa `luoi=luoi` và `luoi_loi=luoi_loi` vào lời gọi `Region(...)`, và cả hai
khoá `"luoi"` / `"luoi_loi"` vào dict `regions` khi ghi đệm.

Trong `_tu_json`, đọc lại có mặc định (đệm phiên bản trước không có khoá này —
tuy vân tay đã đổi nên ca này hiếm, nhưng `.get` rẻ hơn một traceback):

```python
                      words=r["words"], luoi=r.get("luoi", []),
                      luoi_loi=r.get("luoi_loi"))
```

Thêm `from . import bang` vào phần import đầu tệp.

- [ ] **Step 4: Chạy để xác nhận XANH**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/ -q
```

Kỳ vọng: mọi test trong `tests/ocr/` passed.

- [ ] **Step 5: Viết test thất bại cho đường `parse.py`**

Thêm vào `backend/tests/rag/test_parse_pdf_ocr.py`:

```python
def test_trang_ocr_co_luoi_sinh_block_atomic_theo_HANG(monkeypatch):
    """Trang đọc-từ-ảnh có lưới >1 cột phải sinh MỖI HÀNG một block atomic,
    đi đúng đường của B4 — không có đường code thứ hai phải giữ đồng bộ."""
    from src.ocr.document import PageRead, Region
    from src.rag import parse

    luoi = [["Chi tieu", "Ma so", "So tien"],
            ["Tien mat", "111", "1.000"],
            ["Tien gui", "112", "2.000"]]
    parse = _dung_canh(monkeypatch, [""])          # 1 trang RỖNG -> đi qua OCR
    monkeypatch.setattr(parse, "read_page", lambda path, pageno, **kw: PageRead(
        page=1, mean_conf=90.0, tu_dem=False,
        regions=[Region(kind="text", mean_conf=90.0, bbox=(0, 0, 100, 100),
                        text="\n".join(" ".join(h) for h in luoi),
                        words=[], luoi=luoi)]))

    blocks, warnings = parse.parse_pdf("x.pdf")
    atomic = [b for b in blocks if b.get("atomic")]
    assert len(atomic) == 2, "phai co 2 hang than, moi hang mot block atomic"
    assert all(b["source_kind"] == "ocr" for b in atomic)
    assert all(b["ocr_conf"] == 90.0 for b in atomic)
    assert "Ma so: 111" in atomic[0]["text"]
    assert warnings == []


def test_dung_luoi_HONG_thi_bao_co_ten_va_van_giu_du_noi_dung(monkeypatch):
    """Spec §9: mất cấu trúc còn hơn mất nội dung — nhưng KHÔNG được im lặng."""
    from src.ocr.document import PageRead, Region
    from src.rag import parse

    parse = _dung_canh(monkeypatch, [""])
    monkeypatch.setattr(parse, "read_page", lambda path, pageno, **kw: PageRead(
        page=1, mean_conf=90.0, tu_dem=False,
        regions=[Region(kind="text", mean_conf=90.0, bbox=(0, 0, 100, 100),
                        text="Điều 1. Chữ đọc từ ảnh.", words=[], luoi=[],
                        luoi_loi="ValueError: hong that")]))

    blocks, warnings = parse.parse_pdf("x.pdf")
    # noi dung phai con nguyen — mat cau truc KHONG duoc keo theo mat chu
    assert [b["text"] for b in blocks] == ["Điều 1. Chữ đọc từ ảnh."]
    # va phai co canh bao CO TEN, khong duoc nuot
    assert len(warnings) == 1
    assert "hong that" in warnings[0][1]
```

- [ ] **Step 6: Chạy để xác nhận ĐỎ**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/test_parse_pdf_ocr.py -q
```

Kỳ vọng: FAIL — `assert 0 == 2` (chưa có đường lưới).

- [ ] **Step 7: Sửa `parse.py`**

Trong `backend/src/rag/parse.py`, đổi `_doc_trang_bang_anh` để trả thêm lưới:

```python
def _doc_trang_bang_anh(path: str, pageno: int
                        ) -> tuple[list[str], float | None,
                                   tuple[str, str] | None, list[list[str]]]:
```

Mọi lệnh `return` hiện có thêm `[]` ở cuối; lệnh `return` thành công thành:

```python
    loi = next((r.luoi_loi for r in kq.regions if r.luoi_loi), None)
    if loi:
        # Bậc 2 hỏng: nội dung vẫn về đủ (dòng phẳng), chỉ mất cấu trúc cột.
        # Nói TO chứ không nuốt (spec §9).
        return lines, kq.mean_conf, (
            f"trang {pageno}",
            f"đọc được chữ nhưng KHÔNG dựng được cấu trúc bảng: {loi}"), []
    luoi = next((r.luoi for r in kq.regions if len(r.luoi) > 1), [])
    return lines, kq.mean_conf, None, luoi
```

Lưu ý: nhánh này trả **cả `lines` lẫn cảnh báo** — khác các nhánh hỏng khác
(trả `[]` cho `lines`). Có chủ ý: bậc 2 hỏng thì nội dung vẫn còn nguyên, chỉ
mất cấu trúc. Người gọi phải xử được cảnh báo đi kèm dòng KHÔNG rỗng.

Tại chỗ gọi (khoảng dòng 540), nhận thêm biến và, khi lưới có >1 cột, sinh
block theo hàng thay vì dòng phẳng:

```python
            if not text_toan_trang:
                text_toan_trang, conf, canh_bao, luoi_ocr = \
                    _doc_trang_bang_anh(path, pageno)
                if canh_bao:
                    all_warnings.append(canh_bao)
                if text_toan_trang:
                    ocr_pages[pageno] = conf
                    if luoi_ocr and max(len(h) for h in luoi_ocr) > 1:
                        luoi_theo_trang[pageno] = luoi_ocr
```

Khai báo `luoi_theo_trang: dict[int, list[list[str]]] = {}` cạnh `ocr_pages`.

Ở lượt hai, TRƯỚC khi sinh block dòng phẳng cho trang đó, chèn:

```python
        if pageno in luoi_theo_trang:
            # Cùng một đường với bảng vector của B4 — không viết lại logic
            # tách header/đặt tên cột/xuất khuôn `|`.
            header_rows, body_rows, _ = split_header_body(luoi_theo_trang[pageno])
            columns = column_names(header_rows)
            for row in body_rows:
                blocks.append({"text": row_to_text(row, columns),
                               "heading_level": None, "page": pageno,
                               "atomic": True, "source_kind": "ocr",
                               "ocr_conf": ocr_pages.get(pageno)})
            continue
```

- [ ] **Step 8: Chạy để xác nhận XANH**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/rag/ tests/ocr/ -q
```

Kỳ vọng: mọi test passed.

- [ ] **Step 9: Bất biến an toàn — đường không-OCR phải BYTE-IDENTICAL**

Dựng cây ở commit TRƯỚC đợt này, chạy cùng một script trên cả hai cây, so kết quả.

```bash
cat > /tmp/bam_block.py <<'EOF'
import hashlib, os, sys
sys.path.insert(0, ".")
from src.rag.parse import parse_pdf
for p in ["src/rag/seed/law/luat-dautu.pdf",
          "src/rag/seed/law/luat-thuexuatnhapkhau.pdf",
          "src/rag/seed/law/boluat-danssu.pdf",
          "src/rag/seed/law/luat-thuegtgt.pdf"]:
    b, _ = parse_pdf(p)
    h = hashlib.sha256(chr(30).join(x["text"] for x in b).encode()).hexdigest()
    print(f"{os.path.basename(p):40s} {len(b):6d} block  {h[:16]}")
EOF

git worktree add /tmp/truoc-bac-2 3d515ee
export PYTHONIOENCODING=utf-8

cd /tmp/truoc-bac-2/backend
/d/Youdoo/backend/.venv/Scripts/python.exe /tmp/bam_block.py > /tmp/truoc.txt

cd /d/Youdoo/.claude/worktrees/ocr-bac-2/backend
/d/Youdoo/backend/.venv/Scripts/python.exe /tmp/bam_block.py > /tmp/sau.txt

diff /tmp/truoc.txt /tmp/sau.txt && echo "BYTE-IDENTICAL"
```

Kỳ vọng: **không có dòng khác nhau**. Bất kỳ khác biệt nào cũng là hồi quy —
bậc 2 chỉ được đụng tới trang đi qua OCR, mọi trang khác phải ra kết quả không
đổi một bit. Dọn:

```bash
cd /d/Youdoo && git worktree remove /tmp/truoc-bac-2
```

- [ ] **Step 10: Suite đầy đủ**

```bash
cd /d/Youdoo/.claude/worktrees/ocr-bac-2/backend
set -a; . <(grep -E '^(DATABASE_URL|RAG_SCHEMA|RAG_EMBED_PROVIDER|RAG_RERANK_ENABLED)=' /d/Youdoo/.env); set +a
export OLLAMA_URL=http://127.0.0.1:11435 PYTHONIOENCODING=utf-8
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q
```

Kỳ vọng: ≥ 2409 passed (nền cũ) cộng số test mới, 0 failed.

- [ ] **Step 11: Commit**

```bash
git add backend/src/ocr/document.py backend/src/rag/parse.py \
        backend/tests/ocr/test_document.py backend/tests/rag/test_parse_pdf_ocr.py
git commit -m "feat(ocr): noi bac 2 vao duong nap - hang bang doc-tu-anh co cau truc

Region mang them truong luoi; ARTIFACT_VERSION 2 -> 3 (hinh dang artifact doi,
dem cu tu lac khoa qua dau van tay).

Trang doc-tu-anh co luoi >1 cot thi sinh MOI HANG mot block atomic, di dung
duong cua B4 (split_header_body -> column_names -> row_to_text). KHONG viet lai
logic do, va KHONG sua mot dong nao trong pdf_table.py - hang bang doc-tu-anh
va doc-tu-vector di cung mot duong sau diem nay.

dung_luoi hong thi lui ve dong phang, khong lam vo luot nap: mat cau truc con
hon mat noi dung.

Da kiem bat bien an toan: duong khong-OCR BYTE-IDENTICAL tren 4 tai lieu luat.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: Ghi chú thi hành

**Files:**
- Modify: `docs/superpowers/specs/2026-08-31-tang-nap-tai-lieu-ghi-chu-thuc-thi.md`

- [ ] **Step 1: Nối mục mới**

Thêm một mục `## OCR bậc 2 — dựng bảng từ toạ độ` vào cuối tệp, gồm:

- số đo hiệu chỉnh thật (bảng 12 dòng tham số từ Task 2 Step 3)
- ngưỡng hai cổng và cách suy ra
- kết quả thử phá cả hai cổng
- kết quả byte-identical
- **giới hạn còn mở, nói thẳng**: cổng A dùng ảnh rasterise sạch; cổng B chỉ
  một tài liệu, phẳng và sạch; chưa có tài liệu nghiêng/nhiễu/photo nhiều đời;
  rủi ro dương tính giả với bố cục văn xuôi nhiều cột (spec §11); ô có nội dung
  xuống dòng bị tách thành hai hàng (spec §10)

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-08-31-tang-nap-tai-lieu-ghi-chu-thuc-thi.md
git commit -m "docs(ocr): ghi chu thi hanh bac 2 - so do, nguong, gioi han con mo

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```
