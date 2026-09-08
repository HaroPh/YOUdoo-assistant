# OCR bậc 2 — dựng bảng từ toạ độ chữ — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Từ toạ độ chữ Tesseract trả về, dựng lại lưới bảng `list[list[str]]`, để hàng bảng đọc-từ-ảnh đi vào corpus có cấu trúc cột thay vì một dòng phẳng.

**Architecture:** Một hàm thuần trong module lá `src/ocr/table.py` biến `list[OcrWord]` thành lưới. Tín hiệu là **cụm KHE**: trong từng dòng, khe giữa hai từ rộng hơn một bội bề rộng ký tự là ứng viên ranh giới cột; ứng viên phải cụm lại cùng một x qua đủ nhiều dòng mới thành ranh giới thật (đó chính là đòi hỏi căn lề). Không có bộ dò bảng: trang không có khe nào cụm đủ mạnh tự nhiên ra một cột. Lưới đi tiếp qua `pdf_table.py` của B4 **không sửa một dòng nào** — module đó nhận đầu vào là lưới và không quan tâm lưới đến từ đâu.

**Tech Stack:** Python 3.11, `pytesseract` (đã có), `pypdfium2` (đã có), `pdfplumber` (đã có, chỉ dùng để sinh đáp án cho cổng A), `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-06-b5b-ocr-bac-2-dung-bang-design.md`
(spec cha: `docs/superpowers/specs/2026-09-04-tang-ocr-dung-chung-design.md`)

## Global Constraints

- **Bậc 2 chỉ lo CẤU TRÚC.** Trả lời "ô nào thuộc cột/hàng nào". Chữ sai trong ô là việc của bậc 1 và bậc 3 — không sửa chữ ở đây (spec §10).
- **KHÔNG sửa `backend/src/rag/pdf_table.py`.** Bậc 2 chỉ nối vào đầu vào của nó (spec §3).
- **KHÔNG dựng bộ dò bảng.** Suy biến về một cột là hành vi đúng cho trang văn xuôi (spec §4).
- **Khe phải đo CỤC BỘ trong từng dòng, rồi mới cụm qua các dòng.** Khe trắng chạy dọc SUỐT CẢ TRANG đã đo và bác bỏ: trang 16 và 17 chỉ ra ĐÚNG MỘT khe cho bảng 5 cột vì một dòng tiêu đề ngang là đủ bịt; bản vá "loại dòng chạy suốt" cũng hỏng, 0/4 trang loại được dòng nào (spec §2.1). Đừng thử lại HAI cách đó. Cụm khe cục bộ thì khác hẳn: dòng tiêu đề chỉ không đóng góp ứng viên nào, mấy chục dòng thân vẫn đóng góp.
- **Mọi tham số phải KHÔNG THỨ NGUYÊN**: `gap_factor` theo *bề rộng ký tự trung vị*, `support_ratio` theo *tỷ lệ số dòng*. Pixel là sai vì vỡ khi đổi DPI/cỡ chữ (spec §5).
- **Không hằng số nào được đặt trước khi đo.** Task 1 nhận tham số tường minh, không có mặc định. Task 2 đo trên 229 trang rồi mới chốt hằng số.
- ⚠️ **Bẫy tham số mặc định đóng băng.** Python tính giá trị mặc định MỘT LẦN lúc định nghĩa hàm. `def f(*, x=MODULE_CONST)` khiến việc đổi `MODULE_CONST` lúc chạy KHÔNG có tác dụng — đã cắn tầng OCR bậc 1 một lần và suýt vô hiệu hoá chính phép thử phá của nó. Luôn viết `x: T | None = None` rồi giải trong thân hàm.
- **`ARTIFACT_VERSION` 2 → 3** khi hình dạng vùng đổi (`document.py`). Đệm cũ tự lạc khoá qua dấu vân tay — không cần xoá tay.
- **Đường không-OCR phải BYTE-IDENTICAL.** Trang có lớp text không được đổi một bit nào.
- **Hỏng thì to tiếng nhưng không vỡ lượt nạp**: lùi về dòng phẳng + cảnh báo có tên qua `IngestReport`. Tệ nhất là mất cấu trúc, không mất nội dung (spec §9).
- **Định danh trong code (tên hàm, class, biến, hằng số, tên tệp) BẮT BUỘC bằng TIẾNG ANH.** Chú thích thì viết tiếng Việt có dấu. Yêu cầu của chủ dự án, đã ghi trong ký ức dự án — plan này ban đầu vi phạm và đã phải đổi tên toàn bộ giữa chừng.
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
- Create: `backend/src/ocr/table.py`
- Test: `backend/tests/ocr/test_table.py`

**Interfaces:**
- Consumes: `src.ocr.engine.OcrWord` — `@dataclass(frozen=True)` với các trường `text: str`, `conf: float`, `left: int`, `top: int`, `width: int`, `height: int`, `line_id: tuple[int, int, int]`.
- Produces:
  - `median_char_width(words: list[OcrWord]) -> float`
  - `find_column_bounds(words, *, gap_factor: float, support_ratio: float) -> list[int]`
  - `build_grid(words, *, gap_factor: float, support_ratio: float) -> list[list[str]]`
  - Hai tham số `gap_factor` / `support_ratio` **bắt buộc, không có mặc định** ở task này. Task 2 mới thêm mặc định sau khi đo.

- [ ] **Step 1: Viết test thất bại cho đơn vị chuẩn hoá**

Tạo `backend/tests/ocr/test_table.py`:

```python
"""Bậc 2 — dựng lưới từ toạ độ. Test trên từ DỰNG TAY, không chạy Tesseract:
hàm này phải thuần và kiểm được mà không cần binary nào."""
from src.ocr.bang import median_char_width, build_grid, find_column_bounds
from src.ocr.engine import OcrWord


def tu(text, left, top, width, height=20, line=0):
    """Dựng một OcrWord tối giản. `line_id` của Tesseract là
    `(block_num, par_num, line_num)`; ta chỉ đổi thành phần CUỐI, nên hai từ
    cùng `line` là cùng hàng."""
    return OcrWord(text=text, conf=95.0, left=left, top=top,
                   width=width, height=height, line_id=(1, 1, line))


def test_be_rong_ky_tu_la_TRUNG_VI_khong_phai_trung_binh():
    """Ba từ: 20/2=10, 20/4=5, 30/3=10 mỗi ký tự.

    Trung vị các tỷ lệ TỪNG TỪ = 10,0.
    Trung bình gộp (tổng rộng / tổng ký tự) = 70/9 = 7,78 — SAI.

    Đây không phải chuyện làm đẹp: `median_char_width` là đơn vị chuẩn hoá của
    MỌI ngưỡng trong module, nên lệch nó là lệch tất cả. Và scan thật SINH RA
    token rác bbox rộng ít ký tự — đo được 2026-09-06 trên trang 1 bản BCTC:
    dấu mộc đỏ đọc thành `_Ƒ_Gẻ]ùỉ—m//—.ẶẲó—[`. Một token như thế kéo trung
    bình đi rất xa; trung vị miễn nhiễm.
    """
    words = [tu("ab", 0, 0, 20), tu("abcd", 0, 0, 20), tu("abc", 0, 0, 30)]
    assert median_char_width(words) == 10.0


def test_be_rong_ky_tu_khong_no_khi_khong_co_tu():
    assert median_char_width([]) > 0
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

```bash
cd /d/Youdoo/.claude/worktrees/ocr-bac-2/backend
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_table.py -q
```

Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'src.ocr.bang'`.

- [ ] **Step 3: Viết `median_char_width`**

Tạo `backend/src/ocr/table.py`:

```python
"""Bậc 2 của tầng OCR — dựng lại lưới bảng từ toạ độ chữ.

HÀM THUẦN: không đọc tệp, không gọi mạng, không biết gì về PDF. Vào là
`list[OcrWord]`, ra là `list[list[str]]`. Lưới đó đi tiếp qua `pdf_table.py`
của B4 — module đó nhận đầu vào là lưới và KHÔNG quan tâm lưới đến từ đâu,
nên hàng bảng đọc-từ-ảnh và đọc-từ-vector đi cùng một đường sau điểm này.

Cơ chế là CỤM KHE CỤC BỘ: trong từng dòng, khe giữa hai từ rộng hơn một bội
bề rộng ký tự là ứng viên ranh giới cột; ứng viên phải cụm lại cùng một x qua
đủ nhiều dòng mới thành ranh giới thật.

HAI cách đã thử và BÁC BỎ, đừng thử lại (spec §2.1 và ledger P1):
  - khe trắng chạy dọc SUỐT CẢ TRANG: trang 16 và 17 của BCTC scan thật chỉ
    ra ĐÚNG MỘT khe cho bảng 5 cột, vì một dòng tiêu đề ngang là đủ bịt;
  - loại các dòng "chạy suốt" trước khi tính khe: 0/4 trang loại được dòng
    nào, vì văn xuôi cũng có khe giữa từ;
  - cụm MÉP trái/phải: không phân biệt được khe giữa hai từ trong CÙNG một ô
    (khoảng một ký tự) với khe sang cột khác (hàng chục ký tự).
"""
import statistics

from .engine import OcrWord


def median_char_width(words: list[OcrWord]) -> float:
    """Bề rộng một ký tự, lấy TRUNG VỊ trên tỷ lệ của TỪNG TỪ.

    Đây là ĐƠN VỊ CHUẨN HOÁ của cả module. Mọi ngưỡng tính theo nó chứ không
    theo pixel: pixel vỡ ngay khi đổi DPI hoặc cỡ chữ, tức là vỡ đúng lúc đổi
    sang tài liệu định dạng khác (spec §5).

    TRUNG VỊ chứ không trung bình, và tính trên tỷ lệ TỪNG TỪ chứ không phải
    tổng-chia-tổng: scan thật sinh ra token rác bbox rộng mà ít ký tự (đo được
    trên trang 1 bản BCTC — dấu mộc đỏ đọc thành `_Ƒ_Gẻ]ùỉ—m//—.ẶẲó—[`). Một
    token như thế kéo trung bình đi rất xa; trung vị miễn nhiễm. Lệch đơn vị
    chuẩn hoá là lệch MỌI ngưỡng trong module.
    """
    rong = [w.width / len(w.text) for w in words if w.text]
    if not rong:
        return 1.0          # không có từ nào: trả 1 để phép chia sau không nổ
    return statistics.median(rong)
```

- [ ] **Step 4: Chạy để xác nhận XANH**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_table.py -q
```

Kỳ vọng: 2 passed.

- [ ] **Step 5: Viết test thất bại cho `find_column_bounds`**

Thêm vào `backend/tests/ocr/test_table.py`:

```python
def _bang_hai_cot_tien():
    """Ba hàng: nhãn ở x=100, hai cột số căn PHẢI ở x=500 và x=800."""
    words = []
    for i, (nhan, a, b) in enumerate([("Tien", "1.000", "2.000"),
                                      ("Hang", "30.000", "40.000"),
                                      ("Khac", "500.000", "600.000")]):
        words.append(tu(nhan, 100, 100 + i * 30, 40, line=i))
        words.append(tu(a, 500 - len(a) * 10, 100 + i * 30, len(a) * 10, line=i))
        words.append(tu(b, 800 - len(b) * 10, 100 + i * 30, len(b) * 10, line=i))
    return words


def test_tim_ranh_cot_bat_duoc_hai_ranh_giua_ba_cot():
    ranh = find_column_bounds(_bang_hai_cot_tien(), gap_factor=2.0, support_ratio=0.6)
    assert len(ranh) == 2
    assert 140 < ranh[0] < 450 and 500 < ranh[1] < 730


def test_khe_GIUA_TU_trong_cung_mot_o_KHONG_thanh_ranh_cot():
    """Đây là chỗ cơ chế cụm-mép hỏng: khe giữa `Tai` và `san` là một bề rộng
    ký tự, khe sang cột số là 30 — phải phân biệt được hai loại khe đó."""
    words = []
    for i in range(3):
        words.append(tu("Tai", 100, 100 + i * 30, 30, line=i))
        words.append(tu("san", 140, 100 + i * 30, 30, line=i))
        words.append(tu("100", 470, 100 + i * 30, 30, line=i))
    ranh = find_column_bounds(words, gap_factor=2.0, support_ratio=0.6)
    assert len(ranh) == 1, "chi duoc mot ranh: giua nhan hai tu va cot so"
    assert 170 < ranh[0] < 470


def test_van_xuoi_khong_can_le_ra_KHONG_ranh_nao():
    """Không có bộ dò bảng: trang văn xuôi tự nhiên suy biến về một cột."""
    words = [tu(f"dong{i}", 100 + i * 37, 100 + i * 30, 60, line=i)
             for i in range(6)]
    assert find_column_bounds(words, gap_factor=2.0, support_ratio=0.6) == []
```

- [ ] **Step 6: Chạy để xác nhận ĐỎ**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_table.py -q
```

Kỳ vọng: FAIL — `ImportError: cannot import name 'find_column_bounds'`.

- [ ] **Step 7: Viết `find_column_bounds`**

Thêm vào `backend/src/ocr/table.py`:

```python
def _theo_dong(words: list[OcrWord]) -> dict:
    """Gom từ theo `line_id`, GIỮ NGUYÊN thứ tự dòng xuất hiện."""
    ra: dict = {}
    for w in words:
        ra.setdefault(w.line_id, []).append(w)
    return ra


def _cum(gia_tri: list[int], dung_sai: float) -> list[list[int]]:
    """Gom số gần nhau thành cụm, tham lam theo thứ tự tăng dần."""
    if not gia_tri:
        return []
    da_sap = sorted(gia_tri)
    xong: list[list[int]] = [[da_sap[0]]]
    for v in da_sap[1:]:
        if v - xong[-1][-1] <= dung_sai:
            xong[-1].append(v)
        else:
            xong.append([v])
    return xong


def find_column_bounds(words: list[OcrWord], *, gap_factor: float,
                 support_ratio: float) -> list[int]:
    """Ranh giới cột = vị trí KHE LỚN trong dòng, CỤM LẠI qua nhiều dòng.

    Hai bước, và cả hai đều cần thiết:

    1. Trong TỪNG dòng, một khe giữa hai từ liền nhau là ứng viên ranh giới khi
       nó rộng hơn `gap_factor` lần bề rộng ký tự. Đây là thứ phân biệt khe giữa
       hai từ trong CÙNG một ô (khoảng một ký tự) với khe sang cột khác (hàng
       chục ký tự). Cụm căn lề đơn thuần KHÔNG phân biệt được hai loại khe đó —
       đó là lý do cơ chế cụm-mép bị loại (ledger, mục P1).
    2. Ứng viên phải CỤM LẠI cùng một x qua đủ nhiều dòng mới thành ranh giới
       thật. Đây chính là đòi hỏi CĂN LỀ mà spec §2.2 đo được.

    KHÔNG mâu thuẫn spec §2.1 (khe trắng đã bị bác bỏ): §2.1 bác khe chạy dọc
    SUỐT CẢ TRANG — một dòng tiêu đề ngang là đủ bịt nó. Ở đây khe đo CỤC BỘ
    trong từng dòng rồi mới cụm, nên dòng tiêu đề chỉ đơn giản không đóng góp
    ứng viên nào, còn mấy chục dòng thân vẫn đóng góp.
    """
    if not words:
        return []
    dong = _theo_dong(words)
    rong_ky_tu = median_char_width(words)
    nguong_khe = gap_factor * rong_ky_tu

    ung_vien: list[int] = []
    for ws in dong.values():
        theo_x = sorted(ws, key=lambda w: w.left)
        for a, b in zip(theo_x, theo_x[1:]):
            het_a = a.left + a.width
            if b.left - het_a >= nguong_khe:
                ung_vien.append((het_a + b.left) // 2)

    # Dung sai cụm = MỘT bề rộng ký tự: một ranh giới xê dịch quá một ký tự
    # giữa các dòng thì là ranh giới KHÁC, không phải cùng một cột.
    toi_thieu = max(2, int(len(dong) * support_ratio))
    return sorted(int(statistics.median(c))
                  for c in _cum(ung_vien, rong_ky_tu) if len(c) >= toi_thieu)
```

- [ ] **Step 8: Chạy để xác nhận XANH**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_table.py -q
```

Kỳ vọng: 5 passed.

- [ ] **Step 9: Viết test thất bại cho `build_grid`**

Thêm vào `backend/tests/ocr/test_table.py`:

```python
def test_dung_luoi_tra_dung_luoi_ba_cot():
    luoi = build_grid(_bang_hai_cot_tien(), gap_factor=2.0, support_ratio=0.6)
    assert luoi == [["Tien", "1.000", "2.000"],
                    ["Hang", "30.000", "40.000"],
                    ["Khac", "500.000", "600.000"]]


def test_dung_luoi_noi_nhieu_tu_trong_cung_mot_o():
    """Nhãn nhiều từ phải thành MỘT ô, không phải nhiều cột."""
    words = []
    for i in range(3):
        words.append(tu("Tai", 100, 100 + i * 30, 30, line=i))
        words.append(tu("san", 140, 100 + i * 30, 30, line=i))
        words.append(tu("100", 470, 100 + i * 30, 30, line=i))
    ket = build_grid(words, gap_factor=2.0, support_ratio=0.6)
    assert ket == [["Tai san", "100"]] * 3


def test_van_xuoi_ra_luoi_MOT_cot_giu_nguyen_tung_dong():
    words = [tu(f"dong{i}", 100 + i * 37, 100 + i * 30, 60, line=i)
             for i in range(6)]
    ket = build_grid(words, gap_factor=2.0, support_ratio=0.6)
    assert ket == [[f"dong{i}"] for i in range(6)]


def test_dung_luoi_KHONG_sap_lai_hang_theo_toa_do_y():
    """Bậc 1 đã ghi bài học: khác biệt thứ tự đọc từng bị nhầm thành OCR kém.

    Đầu vào ở đây CỐ Ý không theo thứ tự y (từ ở y=500 đứng trước từ ở y=100),
    mô phỏng một trang mà tesseract đọc theo thứ tự khác thứ tự hình học. Đầu
    ra phải theo ĐÚNG THỨ TỰ ĐẦU VÀO, chứng minh ta không tự sắp lại theo y.
    Đòi đầu ra theo `line_id` mới là sắp lại — đúng thứ bị cấm."""
    words = [tu("duoc_doc_truoc", 100, 500, 40, line=1),
             tu("duoc_doc_sau", 100, 100, 40, line=0)]
    ket = build_grid(words, gap_factor=2.0, support_ratio=0.6)
    assert ket == [["duoc_doc_truoc"], ["duoc_doc_sau"]]
```

- [ ] **Step 10: Chạy để xác nhận ĐỎ**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_table.py -q
```

Kỳ vọng: FAIL — `ImportError: cannot import name 'build_grid'`.

- [ ] **Step 11: Viết `build_grid`**

Thêm vào `backend/src/ocr/table.py`:

```python
def build_grid(words: list[OcrWord], *, gap_factor: float,
              support_ratio: float) -> list[list[str]]:
    """`list[OcrWord]` -> `list[list[str]]`.

    Hàng lấy theo `line_id` Tesseract đã trả sẵn, GIỮ NGUYÊN thứ tự xuất hiện.
    Không tự gom lại theo toạ độ y: tesseract gom tốt hơn, và bậc 1 đã ghi bài
    học "đừng sắp xếp lại thứ tự đọc" — khác biệt thứ tự đọc từng bị nhầm thành
    chất lượng OCR kém.

    Không ranh giới nào = MỘT cột. Đó là đường suy biến cho trang văn xuôi,
    KHÔNG phải lỗi: không có bộ dò bảng thì không có gì để bắn nhầm (spec §4).
    """
    if not words:
        return []
    ranh = find_column_bounds(words, gap_factor=gap_factor, support_ratio=support_ratio)
    luoi: list[list[str]] = []
    for ws in _theo_dong(words).values():
        o: list[list[str]] = [[] for _ in range(len(ranh) + 1)]
        for w in sorted(ws, key=lambda x: x.left):
            tam = w.left + w.width // 2
            o[sum(1 for r in ranh if tam > r)].append(w.text)
        luoi.append([" ".join(phan) for phan in o])
    return luoi
```

- [ ] **Step 12: Chạy để xác nhận XANH**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_table.py -q
```

Kỳ vọng: 9 passed.

- [ ] **Step 13: Commit**

```bash
git add backend/src/ocr/table.py backend/tests/ocr/test_table.py
git commit -m "feat(ocr): bac 2 - ham thuan dung luoi bang tu toa do chu

Co che la CUM KHE CUC BO: trong tung dong, khe giua hai tu rong hon mot boi be
rong ky tu la ung vien ranh cot; ung vien phai cum lai cung mot x qua du nhieu
dong moi thanh ranh that (do chinh la doi hoi CAN LE ma spec muc 2.2 do duoc).

Ba cach da thu va BAC BO, ghi trong docstring de khong ai thu lai: khe trang
doc suot ca trang (mot dong tieu de ngang la du bit - spec muc 2.1); loai dong
chay suot roi moi tinh khe (0/4 trang loai duoc dong nao); va cum MEP trai/phai
(khong phan biet duoc khe giua hai tu trong cung mot o voi khe sang cot khac).

median_char_width lay TRUNG VI tren ty le tung tu, khong phai tong-chia-tong: scan
that sinh token rac bbox rong it ky tu (dau moc do), keo trung binh di rat xa.
No la don vi chuan hoa cua MOI nguong trong module.

KHONG co bo do bang: khong khe nao cum du manh thi suy bien ve MOT cot = hanh
vi hom nay cho trang van xuoi.

Tham so con BAT BUOC, chua co mac dinh - Task 2 do tren 229 trang roi moi chot.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: Hiệu chỉnh trên 229 trang, rồi mới chốt hằng số

**Files:**
- Create: `backend/tools/calibrate_table.py`
- Modify: `backend/src/ocr/table.py` (thêm hằng số + mặc định)
- Test: `backend/tests/ocr/test_table.py` (thêm test cho mặc định)

**Interfaces:**
- Consumes: `build_grid(words, *, gap_factor, support_ratio)` từ Task 1.
- Produces: `GAP_FACTOR: float`, `SUPPORT_RATIO: float` trong `bang.py`; và `build_grid` / `find_column_bounds` nhận thêm mặc định `None`.

- [ ] **Step 1: Viết script đo**

Tạo `backend/tools/calibrate_table.py`:

```python
"""Hiệu chỉnh tham số bậc 2 trên MỌI trang bảng vector của corpus.

Đáp án TỰ SINH: trang bảng vector rasterise ra ảnh, đọc lại bằng OCR, dựng
lưới, rồi so với lưới `pdfplumber` bóc từ CHÍNH trang đó. Không gõ tay ô nào,
và phủ nhiều định dạng — đúng chỗ yếu của việc hiệu chỉnh trên một tài liệu.

Chạy:  python -m tools.calibrate_table [so_trang_toi_da]
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

    luoi_tham_so = [(ds, tl) for ds in (1.0, 2.0, 3.0, 5.0)
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
                        luoi = table.build_grid(ws, gap_factor=ds,
                                              support_ratio=tl)
                        k, t = _diem(dap_an, luoi)
                        diem[(ds, tl)][0] += k
                        diem[(ds, tl)][1] += t
                da_lam += 1
                print(f"  {os.path.basename(p)[:34]:36s} tr{pageno:>3}"
                      f"  ({da_lam} trang)", flush=True)

    print(f"\n{'gap_factor':>10}{'ty_le':>8}{'khop':>9}{'tong':>9}{'ty le':>9}")
    for (ds, tl), (k, t) in sorted(diem.items(), key=lambda x: -x[1][0] / max(x[1][1], 1)):
        print(f"{ds:>10}{tl:>8}{k:>9}{t:>9}{k / max(t, 1):>9.4f}")


if __name__ == "__main__":
    main(sys.argv)
```

- [ ] **Step 2: Chạy đo trên một tập nhỏ trước để bắt lỗi script**

```bash
cd /d/Youdoo/.claude/worktrees/ocr-bac-2/backend
export PYTHONIOENCODING=utf-8 OMP_THREAD_LIMIT=1
/d/Youdoo/backend/.venv/Scripts/python.exe -m tools.calibrate_table 5
```

Kỳ vọng: in 5 dòng tiến trình rồi một bảng 12 dòng tham số với tỷ lệ khớp. Nếu mọi tỷ lệ = 0,0000 thì **dừng** — script sai, không phải thuật toán sai.

- [ ] **Step 3: Chạy đo đầy đủ**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m tools.calibrate_table \
  > /tmp/hieu_chinh_bang.txt 2>&1
tail -20 /tmp/hieu_chinh_bang.txt
```

Mất khoảng 12–15 phút (229 trang × ~3 s OCR). Chạy nền được.

- [ ] **Step 4: Chốt hằng số từ số đo**

Lấy cặp `(dung_sai, ty_le)` có tỷ lệ khớp cao nhất. Ghi **con số thật đo được** vào chú thích — không làm tròn cho đẹp, không lấy số từ plan này.

Thêm vào đầu `backend/src/ocr/table.py`, ngay sau phần import:

```python
# ĐO 2026-09-06 trên toàn bộ trang bảng vector của corpus (106 tệp, 229 trang,
# 31.416 ô) — đáp án tự sinh từ `pdfplumber` bóc chính trang đó. Quét lưới
# 4x3 tham số, chọn cặp có tỷ lệ ô khớp cao nhất.
#
# THAY <...> BẰNG SỐ THẬT TỪ `tools/calibrate_table.py`. Không được để nguyên.
#   gap_factor=<a> ty_le=<b> -> <x>/<y> = <z>   <- chọn
#   (dán trọn bảng 12 dòng vào đây để người sau so lại được)
#
# ĐƠN VỊ KHÔNG THỨ NGUYÊN, có chủ ý: dung sai theo BỀ RỘNG KÝ TỰ TRUNG VỊ và
# ngưỡng theo TỶ LỆ SỐ DÒNG. Pixel vỡ ngay khi đổi DPI hoặc cỡ chữ, tức là vỡ
# đúng lúc đổi sang tài liệu định dạng khác (spec §5).
GAP_FACTOR = <a>
SUPPORT_RATIO = <b>
```

- [ ] **Step 5: Viết test cho đường mặc định**

Thêm vào `backend/tests/ocr/test_table.py`:

```python
def test_mac_dinh_doc_lai_hang_so_luc_GOI_khong_dong_bang_luc_dinh_nghia():
    """Bẫy tham số mặc định đóng băng: Python tính giá trị mặc định MỘT LẦN lúc
    định nghĩa hàm. Nếu viết `def f(*, x=HANG_SO)` thì đổi HANG_SO lúc chạy sẽ
    KHÔNG có tác dụng — đã cắn tầng OCR bậc 1 một lần và suýt vô hiệu hoá chính
    phép thử phá của nó. Test này gác đúng chuyện đó."""
    from src.ocr import bang as m

    words = _bang_hai_cot_tien()
    goc = m.SUPPORT_RATIO
    try:
        m.SUPPORT_RATIO = 0.99      # gần như không cụm nào đủ ủng hộ
        it_cot = m.build_grid(words)
        m.SUPPORT_RATIO = 0.1       # dễ dãi
        nhieu_cot = m.build_grid(words)
    finally:
        m.SUPPORT_RATIO = goc
    assert len(it_cot[0]) < len(nhieu_cot[0]), (
        "đổi hằng số lúc chạy KHÔNG đổi kết quả -> mặc định đã bị đóng băng")
```

- [ ] **Step 6: Chạy để xác nhận ĐỎ**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_table.py -q
```

Kỳ vọng: FAIL — `TypeError: build_grid() missing 2 required keyword-only arguments`.

- [ ] **Step 7: Thêm mặc định GIẢI LÚC GỌI**

Sửa chữ ký hai hàm trong `backend/src/ocr/table.py`:

```python
def find_column_bounds(words: list[OcrWord], *, gap_factor: float | None = None,
                support_ratio: float | None = None) -> list[int]:
```

và ngay đầu thân hàm, TRƯỚC mọi dòng khác:

```python
    # Giải lúc GỌI, không dùng hằng số làm giá trị mặc định — xem test
    # `test_mac_dinh_doc_lai_hang_so_luc_GOI...` và bẫy đã cắn bậc 1.
    gap_factor = GAP_FACTOR if gap_factor is None else gap_factor
    support_ratio = SUPPORT_RATIO if support_ratio is None else support_ratio
```

Làm y hệt cho `build_grid` (nó chỉ chuyển tiếp xuống `find_column_bounds`, nhưng vẫn phải nhận `None` để người gọi không phải truyền).

- [ ] **Step 8: Chạy để xác nhận XANH**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_table.py -q
```

Kỳ vọng: 9 passed.

- [ ] **Step 9: Commit**

```bash
git add backend/src/ocr/table.py backend/tests/ocr/test_table.py backend/tools/calibrate_table.py
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
- Create: `backend/tests/ocr/test_table_gate_vector.py`

**Interfaces:**
- Consumes: `table.build_grid(words)` (mặc định đã chốt ở Task 2); `src.ocr.document._anh_cua_trang(path, pageno, dpi)`; `src.ocr.engine.ocr_image(img)`.
- Produces: hằng số `MATCH_THRESHOLD` trong tệp test — suy từ số đo, không đặt trước.

- [ ] **Step 1: Viết cổng**

Tạo `backend/tests/ocr/test_table_gate_vector.py`:

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
MATCH_THRESHOLD = <n>

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

    khop, tong = _ty_le_khop(dap_an, table.build_grid(ws))
    assert tong > 0, "dap an khong co o nao co noi dung -> chon lai trang"
    ty_le = khop / tong
    assert ty_le >= MATCH_THRESHOLD, (
        f"{os.path.basename(tep)} tr{trang}: {khop}/{tong} = {ty_le:.4f} "
        f"< nguong {MATCH_THRESHOLD}")
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ (ngưỡng chưa có)**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_table_gate_vector.py -q
```

Kỳ vọng: FAIL khi thu thập — `NameError` / `SyntaxError` vì `<n>` chưa thay.

- [ ] **Step 3: Đo tỷ lệ thật trên 6 trang rồi chốt ngưỡng**

Đặt tạm `MATCH_THRESHOLD = 0.0` và thêm một dòng in ngay TRƯỚC `assert ty_le >=`:

```python
    print(f"\n{os.path.basename(tep)} tr{trang}: {khop}/{tong} = {ty_le:.4f}")
```

Chạy với `-s` để thấy nó:

```bash
export PYTHONIOENCODING=utf-8 OMP_THREAD_LIMIT=1
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest   tests/ocr/test_table_gate_vector.py -q -s
```

Ghi lại 6 con số. **Giữ nguyên dòng in** — nó có ích mỗi lần cổng đỏ. Rồi đặt:

`MATCH_THRESHOLD = làm tròn xuống 2 chữ số của (min(6 con số) − 0.05)`

Dán cả 6 con số vào chú thích trên `MATCH_THRESHOLD`.

Nếu con số nhỏ nhất **dưới 0,5**, dừng và báo: một định dạng đang hỏng nặng,
cần xem trước khi chốt ngưỡng thấp che nó.

- [ ] **Step 4: Chạy để xác nhận XANH**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_table_gate_vector.py -q
```

Kỳ vọng: 6 passed.

- [ ] **Step 5: THỬ PHÁ — cổng phải biết đỏ**

Cổng chưa từng thấy đỏ thì chưa được tin. Ép `SUPPORT_RATIO` lên 0,99 (gần như
không cụm nào đủ ủng hộ ⇒ mọi bảng suy biến về một cột):

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0, '.')
from src.ocr import bang
bang.SUPPORT_RATIO = 0.99
import pytest
sys.exit(pytest.main(['tests/ocr/test_table_gate_vector.py', '-q']))
"
```

Kỳ vọng: **FAIL** ở phần lớn tham số hoá. Nếu vẫn xanh thì cổng không đo gì —
**dừng và báo**, đừng đi tiếp.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/ocr/test_table_gate_vector.py
git commit -m "test(ocr): cong A - tu nuoi da dinh dang cho bac 2

Trang bang VECTOR rasterise -> dung luoi bang bac 2 -> so voi luoi pdfplumber
boc tu chinh trang do. Dap an tu sinh, khong go tay o nao.

6 trang, moi trang mot DINH DANG khac nhau (phu luc luat, bieu thue, bieu mau
BCTC, bieu mau SSC, hoa don, so tay tieng Anh) - khong phai 6 trang cung mot
bieu mau.

So theo TAP TU chu khong nguyen van: chu doc lech la viec cua tang doc, cong
nay chi hoi o co nam dung chi so (hang, cot) khong.

Nguong suy tu so do that (lam tron xuong cua min - 0,05), da THU PHA bang cach
ep SUPPORT_RATIO=0.99 va xac nhan cong do.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Cổng B — scan thật, dùng lại cổng số học đã duyệt

**Files:**
- Create: `backend/tests/ocr/test_cong_bang_scan_that.py`

**Interfaces:**
- Consumes: `table.build_grid(words)`; `src.ocr.document.read_page(path, pageno)`; các tệp đáp án `backend/tests/fixtures/ocr_bang_that/SCID_2026H1_tr{12..18}.json` (trạng thái `DA_DUYET`).
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
SAME_ROW_THRESHOLD = <m>


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
    luoi = table.build_grid([
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
    assert cung_hang / tong >= SAME_ROW_THRESHOLD
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

```bash
/d/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/ocr/test_cong_bang_scan_that.py -q
```

Kỳ vọng: FAIL khi thu thập vì `<m>` chưa thay.

- [ ] **Step 3: Đo rồi chốt ngưỡng**

Tạm đặt `SAME_ROW_THRESHOLD = 0.0`, chạy `pytest ... -s` và đọc 7 dòng in ra. Đặt:

`SAME_ROW_THRESHOLD = làm tròn xuống 2 chữ số của (min(7 tỷ lệ) − 0.05)`

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
table.GAP_FACTOR = 1000.0    # khong khe nao du lon -> moi bang suy bien MOT cot
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

Nguong suy tu so do that, da THU PHA bang GAP_FACTOR=100.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Nối vào `document.py` và `parse.py`

**Files:**
- Modify: `backend/src/ocr/document.py` (`ARTIFACT_VERSION`, `Region`, `read_page`, `_tu_json`)
- Modify: `backend/src/rag/parse.py` (`_doc_trang_bang_anh` và nhánh dùng nó)
- Test: `backend/tests/ocr/test_document.py`, `backend/tests/rag/test_parse_pdf_ocr.py`

**Interfaces:**
- Consumes: `table.build_grid(words)`; `src.rag.pdf_table.{split_header_body, column_names, row_to_text}`.
- Produces: `Region.grid: list[list[str]]` (rỗng cho vùng `text`); `_doc_trang_bang_anh` trả thêm phần tử lưới.

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
    grid_error: str | None = None    # lý do dựng lưới hỏng; None = không hỏng
```

`grid_error` tồn tại để lỗi **đi tiếp được** thay vì chết tại chỗ: `document.py`
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
        luoi, grid_error = table.build_grid(kq.words), None
    except Exception as e:                               # noqa: BLE001
        luoi, grid_error = [], f"{type(e).__name__}: {e}"
```

Đưa `grid=grid` và `grid_error=grid_error` vào lời gọi `Region(...)`, và cả hai
khoá `"luoi"` / `"grid_error"` vào dict `regions` khi ghi đệm.

Trong `_tu_json`, đọc lại có mặc định (đệm phiên bản trước không có khoá này —
tuy vân tay đã đổi nên ca này hiếm, nhưng `.get` rẻ hơn một traceback):

```python
                      words=r["words"], luoi=r.get("luoi", []),
                      grid_error=r.get("grid_error"))
```

Thêm `from . import table` vào phần import đầu tệp.

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
                        words=[], grid=grid)]))

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
                        grid_error="ValueError: hong that")]))

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
    loi = next((r.grid_error for r in kq.regions if r.grid_error), None)
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
                text_toan_trang, conf, canh_bao, ocr_grid = \
                    _doc_trang_bang_anh(path, pageno)
                if canh_bao:
                    all_warnings.append(canh_bao)
                if text_toan_trang:
                    ocr_pages[pageno] = conf
                    if ocr_grid and max(len(h) for h in ocr_grid) > 1:
                        grid_by_page[pageno] = ocr_grid
```

Khai báo `grid_by_page: dict[int, list[list[str]]] = {}` cạnh `ocr_pages`.

Ở lượt hai, TRƯỚC khi sinh block dòng phẳng cho trang đó, chèn:

```python
        if pageno in grid_by_page:
            # Cùng một đường với bảng vector của B4 — không viết lại logic
            # tách header/đặt tên cột/xuất khuôn `|`.
            header_rows, body_rows, _ = split_header_body(grid_by_page[pageno])
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

build_grid hong thi lui ve dong phang, khong lam vo luot nap: mat cau truc con
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
