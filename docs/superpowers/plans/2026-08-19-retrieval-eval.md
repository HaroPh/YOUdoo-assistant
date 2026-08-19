# Số đo truy xuất (P0) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm bộ eval `retrieval` chạy `retrieve()` thật trên corpus thật, đo `recall_at_20` / `recall_at_6` / `mrr` / `chunk_span`, và đo `rerank_delta` giữa reranker bật và tắt.

**Architecture:** Một file dữ liệu golden set (`evals/retrieval_cases.py`) neo nhãn vào cặp `(source_file, section_path)`; một hàm chấm điểm thuần (`evals/retrieval_score.py`) không chạm DB nên test được bằng unit test; một hàm `eval_retrieval()` trong `run_eval.py` nối hai thứ đó với `retrieve()` thật. Không sửa một dòng nào của đường production.

**Tech Stack:** Python 3.11, pytest 9.1.1, psycopg 3.3.4 + pgvector, Ollama `bge-m3` (local), `BAAI/bge-reranker-v2-m3` trên CUDA.

**Spec:** `docs/superpowers/specs/2026-08-19-retrieval-eval-design.md`

## Global Constraints

- **Định danh trong code viết bằng tiếng Anh.** Tên biến, tên hàm, tên tham số, key của dict — tất cả tiếng Anh. Comment và docstring tiếng Việt. (Người triển khai hay copy nguyên code trong plan, nên plan này đã viết sẵn đúng quy ước.)
- **Lệnh pytest LUÔN kèm `-m "not integration and not live"`** trừ khi bước ghi rõ khác. Lệnh trần từng gọi API LLM thật và gây sự cố.
- Chạy pytest từ thư mục `backend/`, dùng `./.venv/Scripts/python.exe -m pytest`.
- **Không sửa** `src/rag/retrieve.py`, `src/rag/chunking.py`, `src/rag/config.py`, `src/agents/**`. Plan này chỉ thêm khả năng quan sát.
- `OLLAMA_URL` phải là `http://127.0.0.1:11435`, **không phải** `localhost` — `localhost` trả giá ~2s mỗi lời gọi embed trên Windows (đo 2026-08-19: 2300ms vs 270ms).
- Marker embedding hiện tại: `bge-m3` / 1024 chiều. Corpus: 3.300 chunk / 17 tài liệu.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/tests/evals/__init__.py` (tạo) | Thư mục `tests/evals/` CHƯA tồn tại. Mọi thư mục test khác (`tests/rag/`, `tests/agents/`, `tests/llm/`) đều có `__init__.py` rỗng — thiếu nó thì hai file `test_retrieval_*.py` va tên module với nhau lúc collection. |
| `backend/evals/retrieval_cases.py` (tạo) | Golden set: câu hỏi + nhãn `(source_file, section_path)` + hạng độ khó. Dữ liệu thuần, không logic. |
| `backend/evals/retrieval_score.py` (tạo) | Chấm điểm thuần: nhận danh sách chunk đã xếp hạng + nhãn → dict số đo. Không chạm DB, không chạm LLM. |
| `backend/tests/evals/test_retrieval_score.py` (tạo) | Unit test cho bộ chấm — chạy ở chế độ mặc định. |
| `backend/tests/evals/test_retrieval_cases.py` (tạo) | Test hợp đồng: mọi nhãn phải khớp hàng thật trong `rag_chunks`. Đánh dấu `integration`. |
| `backend/evals/run_eval.py` (sửa) | Thêm `eval_retrieval()`, nối vào `_FN` và `--set`. |
| `backend/evals/baseline-bge-m3-retrieval.json` (sinh ra) | Baseline, ghi bằng `--save-baseline`. |

---

## Task 1: Bộ chấm điểm thuần

**Files:**
- Create: `backend/evals/retrieval_score.py`
- Create: `backend/tests/evals/__init__.py` (rỗng)
- Test: `backend/tests/evals/test_retrieval_score.py`

**Interfaces:**
- Consumes: không gì (task đầu tiên).
- Produces:
  - `label_of(chunk) -> tuple[str, str]` — quy chunk về `(basename(source_file), section_path or sheet or "")`.
  - `score_one(ranked_labels: list[tuple[str, str]], expected: set[tuple[str, str]], k_pool: int, k_final: int) -> dict` — trả `{"recall_at_pool": float, "recall_at_final": float, "reciprocal_rank": float, "hit_ranks": list[int]}`.

Vì sao tách file: bộ chấm không cần DB, Ollama, hay GPU. Tách ra thì nó chạy trong chế độ pytest mặc định (48s cho 1706 test) thay vì phải dựng hạ tầng.

- [ ] **Step 1: Viết test đỏ**

Tạo thư mục và file `__init__.py` rỗng trước:

```bash
mkdir -p tests/evals && touch tests/evals/__init__.py
```

Rồi tạo `backend/tests/evals/test_retrieval_score.py`:

```python
# backend/tests/evals/test_retrieval_score.py
"""Bộ chấm truy xuất — unit thuần, KHÔNG cần Postgres/Ollama/GPU."""
import pytest

from evals.retrieval_score import label_of, score_one


class _Chunk:
    """Đủ field mà label_of() đọc — không dựng src.rag.types.Chunk thật
    (14 tham số bắt buộc, phần lớn vô nghĩa với bài test này)."""

    def __init__(self, source_file, section_path=None, sheet=None):
        self.source_file = source_file
        self.section_path = section_path
        self.sheet = sheet


def test_label_of_uses_basename_not_full_path():
    # doc_id/source_file là đường dẫn tuyệt đối phụ thuộc máy; nhãn viết tay
    # thì không thể mang đường dẫn đó. Quy về basename ở ĐÚNG một chỗ.
    c = _Chunk(r"D:/Youdoo/backend/src/rag/seed/policy.docx", "Mục 2")
    assert label_of(c) == ("policy.docx", "Mục 2")


def test_label_of_falls_back_to_sheet_for_xlsx():
    c = _Chunk("/x/bang_gia.xlsx", None, "Bảng giá")
    assert label_of(c) == ("bang_gia.xlsx", "Bảng giá")


def test_label_of_empty_string_when_no_section_or_sheet():
    c = _Chunk("/x/a.pdf")
    assert label_of(c) == ("a.pdf", "")


def test_score_one_perfect_hit_at_rank_one():
    ranked = [("a.pdf", "Điều 1"), ("b.pdf", "Điều 9")]
    got = score_one(ranked, {("a.pdf", "Điều 1")}, k_pool=20, k_final=6)
    assert got["recall_at_pool"] == 1.0
    assert got["recall_at_final"] == 1.0
    assert got["reciprocal_rank"] == 1.0
    assert got["hit_ranks"] == [1]


def test_score_one_miss_gives_zero_reciprocal_rank():
    ranked = [("b.pdf", "Điều 9")]
    got = score_one(ranked, {("a.pdf", "Điều 1")}, k_pool=20, k_final=6)
    assert got["recall_at_pool"] == 0.0
    assert got["reciprocal_rank"] == 0.0
    assert got["hit_ranks"] == []


def test_score_one_partial_recall_with_two_expected_labels():
    ranked = [("a.pdf", "Điều 1"), ("c.pdf", "Điều 3")]
    expected = {("a.pdf", "Điều 1"), ("b.pdf", "Điều 2")}
    got = score_one(ranked, expected, k_pool=20, k_final=6)
    assert got["recall_at_pool"] == pytest.approx(0.5)


def test_score_one_final_cut_is_narrower_than_pool():
    # Nhãn đúng nằm ở hạng 8 — trong pool 20 nhưng NGOÀI top-6. Đây chính là
    # ca phân biệt hai số đo; gộp chúng làm một là mù trước tác dụng rerank.
    ranked = [("x.pdf", f"E{i}") for i in range(7)] + [("a.pdf", "Điều 1")]
    got = score_one(ranked, {("a.pdf", "Điều 1")}, k_pool=20, k_final=6)
    assert got["recall_at_pool"] == 1.0
    assert got["recall_at_final"] == 0.0
    assert got["reciprocal_rank"] == pytest.approx(1 / 8)


def test_score_one_duplicate_labels_count_once():
    # Nhiều chunk cùng một mục quy về CÙNG một nhãn (đánh đổi đã chấp nhận ở
    # spec §4). Recall không được vượt 1.0 vì trúng lặp.
    ranked = [("a.pdf", "Điều 1"), ("a.pdf", "Điều 1")]
    got = score_one(ranked, {("a.pdf", "Điều 1")}, k_pool=20, k_final=6)
    assert got["recall_at_pool"] == 1.0


def test_score_one_empty_ranked_list_is_total_miss():
    got = score_one([], {("a.pdf", "Điều 1")}, k_pool=20, k_final=6)
    assert got["recall_at_pool"] == 0.0
    assert got["reciprocal_rank"] == 0.0


def test_score_one_reciprocal_rank_uses_first_hit_only():
    ranked = [("z.pdf", "E0"), ("a.pdf", "Điều 1"), ("b.pdf", "Điều 2")]
    expected = {("a.pdf", "Điều 1"), ("b.pdf", "Điều 2")}
    got = score_one(ranked, expected, k_pool=20, k_final=6)
    assert got["reciprocal_rank"] == pytest.approx(1 / 2)
    assert got["hit_ranks"] == [2, 3]
```

- [ ] **Step 2: Chạy để xác nhận đỏ**

```bash
./.venv/Scripts/python.exe -m pytest tests/evals/test_retrieval_score.py -q -m "not integration and not live"
```

Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'evals.retrieval_score'`.

- [ ] **Step 3: Viết implementation tối thiểu**

Tạo `backend/evals/retrieval_score.py`:

```python
# backend/evals/retrieval_score.py
"""Chấm điểm truy xuất — THUẦN, không chạm DB/Ollama/LLM.

Tách khỏi run_eval.py có chủ đích: nhờ vậy toàn bộ logic chấm chạy trong
chế độ pytest mặc định, không cần dựng hạ tầng. Bài học từ eval_synthesis —
logic chấm nằm chung với logic gọi model thì không ai test được nó.

Nhãn là CẶP (basename tệp, section_path) chứ không phải chunk_id: chunk_id
là bigserial, re-index đổi sạch, mà re-index chính là việc bắt buộc khi thử
embedding mới (spec §4).
"""
import os


def label_of(chunk) -> tuple[str, str]:
    """Quy một chunk về nhãn so sánh được.

    basename chứ không phải đường dẫn đầy đủ: source_file trong DB là đường
    dẫn tuyệt đối phụ thuộc máy đã ingest, còn nhãn viết tay thì không thể
    mang đường dẫn đó. Quy đổi ở ĐÚNG một chỗ này.

    sheet đỡ cho chunk xlsx (section_path của chúng luôn None); "" khi không
    có cả hai — vẫn là nhãn hợp lệ, chỉ là thô.
    """
    base = os.path.basename(str(chunk.source_file).replace("\\", "/"))
    section = chunk.section_path or chunk.sheet or ""
    return (base, section)


def score_one(ranked_labels: list[tuple[str, str]],
              expected: set[tuple[str, str]],
              k_pool: int, k_final: int) -> dict:
    """Số đo cho MỘT câu hỏi.

    ranked_labels: nhãn theo đúng thứ tự retrieve() trả về (hạng 1 trước).
    expected: tập nhãn đúng (>=1 phần tử).

    recall_at_pool đo trên k_pool đầu, recall_at_final trên k_final đầu —
    tách đôi vì reranker CHỈ sắp xếp lại, không thêm ứng viên: pool là trần
    mà rerank không bao giờ vượt được, final là thứ LLM thật sự nhìn thấy.
    Gộp hai số này làm một là mù trước tác dụng của rerank (spec §5).

    reciprocal_rank lấy hạng của nhãn đúng ĐẦU TIÊN, tính trên toàn danh
    sách (không cắt) — cắt rồi mới tính sẽ biến "hạng 8" thành "trượt", làm
    mất đúng tín hiệu cần để thấy rerank kéo nó lên.
    """
    hit_ranks = [i + 1 for i, lab in enumerate(ranked_labels) if lab in expected]

    def _recall(cut: int) -> float:
        seen = set(ranked_labels[:cut]) & expected
        return len(seen) / len(expected) if expected else 0.0

    return {
        "recall_at_pool": _recall(k_pool),
        "recall_at_final": _recall(k_final),
        "reciprocal_rank": 1.0 / hit_ranks[0] if hit_ranks else 0.0,
        "hit_ranks": hit_ranks,
    }
```

- [ ] **Step 4: Chạy để xác nhận xanh**

```bash
./.venv/Scripts/python.exe -m pytest tests/evals/test_retrieval_score.py -q -m "not integration and not live"
```

Kỳ vọng: PASS, 10 test.

- [ ] **Step 5: Commit**

```bash
git add backend/evals/retrieval_score.py backend/tests/evals/test_retrieval_score.py
git commit -m "feat(evals): bo cham diem truy xuat thuan (recall@pool/final, MRR)"
```

---

## Task 2: Golden set + test hợp đồng

**Files:**
- Create: `backend/evals/retrieval_cases.py`
- Test: `backend/tests/evals/test_retrieval_cases.py`

**Interfaces:**
- Consumes: `label_of` từ Task 1 (dùng trong test hợp đồng).
- Produces: `RETRIEVAL_CASES: list[tuple[str, frozenset[tuple[str, str]], str]]` — `(question, expected_labels, difficulty)` với `difficulty` thuộc `{"easy", "hard", "trap"}`.

- [ ] **Step 1: Đọc corpus thật để lấy nhãn CÓ THẬT**

**Không được đoán nhãn.** Chạy script này và dùng đầu ra để viết `RETRIEVAL_CASES`:

```bash
./.venv/Scripts/python.exe -c "
import sys, io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from dotenv import load_dotenv; load_dotenv('../.env')
import os; os.environ['OLLAMA_URL'] = 'http://127.0.0.1:11435'
from src.rag import db
conn = db.connect()
rows = conn.execute(
    'select source_file, section_path, count(*) '
    'from rag_chunks group by 1,2 order by 1,2').fetchall()
for src, sec, n in rows:
    print('%3d | %-28s | %s' % (n, os.path.basename(src.replace(chr(92), '/')), sec))
conn.close()" > /tmp/labels.txt; wc -l /tmp/labels.txt
```

Mọi nhãn viết vào `RETRIEVAL_CASES` **phải xuất hiện nguyên văn** trong đầu ra này.

- [ ] **Step 2: Viết test hợp đồng (đỏ trước)**

Tạo `backend/tests/evals/test_retrieval_cases.py`:

```python
# backend/tests/evals/test_retrieval_cases.py
"""Hợp đồng golden set ↔ corpus thật.

Nhãn viết tay có thể trỏ vào cặp (tệp, section_path) KHÔNG tồn tại — sai
chính tả, đổi tên tệp, hay heading bị parse_pdf cắt khác đi. Nhãn như vậy
làm recall tụt mà không ai hiểu vì sao, và trông y hệt "model kém đi".

Đây đúng lớp lỗi GATHER_CASES từng dính: fixture trôi khỏi dữ liệu thật mà
không ai biết, phải thêm test hợp đồng sau. Lần này viết cùng lúc.
"""
import pytest

from evals.retrieval_cases import RETRIEVAL_CASES
from evals.retrieval_score import label_of
from src.rag import db as _db


def test_moi_ca_co_it_nhat_mot_nhan():
    for question, expected, _difficulty in RETRIEVAL_CASES:
        assert expected, f"ca không có nhãn nào: {question!r}"


def test_difficulty_chi_nhan_ba_gia_tri():
    for question, _expected, difficulty in RETRIEVAL_CASES:
        assert difficulty in ("easy", "hard", "trap"), \
            f"hạng lạ {difficulty!r} ở ca {question!r}"


def test_co_du_ca_ba_hang_do_kho():
    # trap BẮT BUỘC phải có: 9 PDF luật đều mở đầu bằng cùng cấu trúc
    # ("Điều 1. Phạm vi điều chỉnh"), nên bộ đo thiếu ca bẫy sẽ không bao
    # giờ thấy lỗi trúng-nhầm-văn-bản.
    seen = {d for _q, _e, d in RETRIEVAL_CASES}
    assert seen == {"easy", "hard", "trap"}


def test_khong_co_cau_hoi_trung_lap():
    questions = [q for q, _e, _d in RETRIEVAL_CASES]
    assert len(questions) == len(set(questions))


@pytest.mark.integration
def test_moi_nhan_khop_it_nhat_mot_chunk_that():
    """Nhãn không khớp hàng nào trong rag_chunks → ĐỎ, kèm tên nhãn."""
    conn = _db.connect()
    try:
        rows = conn.execute(
            "select source_file, section_path, sheet from rag_chunks").fetchall()
    finally:
        conn.close()

    class _Row:
        def __init__(self, r):
            self.source_file, self.section_path, self.sheet = r

    real = {label_of(_Row(r)) for r in rows}
    missing = sorted({lab for _q, exp, _d in RETRIEVAL_CASES for lab in exp
                      if lab not in real})
    assert not missing, (
        f"{len(missing)} nhãn không khớp chunk thật nào — golden set đã trôi "
        f"khỏi corpus (hoặc sai chính tả). Nhãn hỏng: {missing[:10]}")
```

- [ ] **Step 3: Chạy để xác nhận đỏ**

```bash
./.venv/Scripts/python.exe -m pytest tests/evals/test_retrieval_cases.py -q -m "not integration and not live"
```

Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'evals.retrieval_cases'`.

- [ ] **Step 4: Viết golden set**

Tạo `backend/evals/retrieval_cases.py`. Khung dưới đây có sẵn **12 ca mẫu đã đúng cấu trúc** — nhiệm vụ là mở rộng lên **~60 ca** bằng đầu ra của Step 1.

Phân bổ bắt buộc:
- **≥35 ca chạm 9 PDF luật** (98.7% corpus, hiện KHÔNG bộ eval nào chạm tới).
- ~15 ca cho tài liệu nghiệp vụ, **tái dùng câu hỏi đã có** trong `cases.py` (`INTENT_CASES`, `SOP_SELECT_CASES`, `SYNTHESIS_CASES`, `MULTI_SOURCE_CASES`) — chép nguyên văn câu hỏi để hai bộ đo nói về cùng một thứ.
- **≥8 ca `trap`**, mỗi ca nhãn đúng là văn bản KHÁC với văn bản mà từ khoá gợi ý.

```python
# backend/evals/retrieval_cases.py
"""Golden set truy xuất — spec 2026-08-19 §7.

CẤU TRÚC: (question, expected_labels, difficulty)
  expected_labels: frozenset[(basename tệp, section_path)] — xem
  retrieval_score.label_of(). Neo vào CẶP chứ không phải chunk_id (bigserial,
  re-index đổi sạch) và không phải section_path đơn ("Điều 3. Giải thích từ
  ngữ" có 32 chunk nằm rải ở nhiều luật khác nhau — neo đơn sẽ tính trúng
  nhầm luật thành trúng).

  difficulty:
    easy — từ khoá câu hỏi trùng mặt chữ trong chunk; FTS một mình cũng trúng
    hard — diễn đạt khác hẳn, phải hiểu nghĩa; chỗ dense + rerank kiếm ăn
    trap — từ khoá trùng nhưng ý KHÁC; nhãn đúng là văn bản khác với văn bản
           mà từ khoá gợi ý. Bắt lỗi trúng-nhầm.

MỌI NHÃN PHẢI CÓ THẬT trong rag_chunks — test_retrieval_cases.py chốt điều
này, đừng viết tay theo trí nhớ.
"""

RETRIEVAL_CASES: list[tuple[str, frozenset, str]] = [
    # ── tài liệu nghiệp vụ: câu hỏi CHÉP NGUYÊN VĂN từ cases.py ────────────
    ("chính sách đổi trả hàng như thế nào?",
     frozenset({("policy.docx", "Chính sách hoàn hàng › Mục 1 — Điều kiện hoàn hàng"),
                ("policy.docx", "Chính sách hoàn hàng › Mục 3 — Quy trình hoàn hàng")}),
     "easy"),
    ("hàng giảm giá có được hoàn trả không?",
     frozenset({("policy.docx", "Chính sách hoàn hàng › Mục 2 — Ngoại lệ không được hoàn trả")}),
     "easy"),
    ("thời gian xử lý hoàn tiền là bao lâu?",
     frozenset({("policy.docx", "Chính sách hoàn hàng › Mục 4 — Hoàn tiền")}),
     "easy"),

    # ── PHẦN CẦN MỞ RỘNG ───────────────────────────────────────────────────
    # Thêm ~50 ca nữa từ đầu ra Step 1. Mẫu cho từng hạng:
    #
    # BA mẫu dưới đây đã ĐỐI CHIẾU với rag_chunks ngày 2026-08-19, chép
    # nguyên văn. Bỏ dấu comment và dùng thẳng.
    #
    # easy — từ khoá trùng mặt chữ:
    #   ("thời hiệu khởi kiện về hợp đồng là bao lâu?",
    #    frozenset({("boluat-danssu.pdf", "Điều 429. Thời hiệu khởi kiện về hợp đồng")}),
    #    "easy"),
    #
    # hard — diễn đạt khác hẳn, KHÔNG mượn từ ngữ của chunk:
    #   ("công ty muốn cho nhân viên nghỉ việc thì phải báo trước bao nhiêu ngày?",
    #    frozenset({("boluat-laodong.pdf", "Điều 36. Quyền đơn phương chấm dứt hợp đồng lao động của người sử dụng lao động")}),
    #    "hard"),
    #
    # trap — từ khoá gợi ý SAI văn bản ("thuế suất" kéo mạnh về
    # luat-thuegtgt.pdf, nhãn đúng nằm ở luật xuất nhập khẩu):
    #   ("căn cứ tính thuế với hàng nhập khẩu theo tỷ lệ phần trăm là gì?",
    #    frozenset({("luat-thuexuatnhapkhau.pdf",
    #                "Điều 5. Căn cứ tính thuế xuất khẩu, thuế nhập khẩu đối với hàng hóa áp dụng phương pháp tính thuế theo tỷ lệ phần trăm")}),
    #    "trap"),
    #
    # ⚠️ CẢNH BÁO khi gán nhãn cho PDF luật (đo 2026-08-19): parse_pdf dùng
    # heuristic, nên trong rag_chunks có những "mục" KHÔNG phải mục thật —
    # "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "CHỦ TỊCH QUỐC HỘI", "Chương I"
    # trống, và 15 mảnh câu tham chiếu chéo kiểu "Điều 11 của Luật này quy
    # định." ĐỪNG dùng chúng làm nhãn đúng: chúng là lỗi ingest (P3 sẽ xoá),
    # gán nhãn vào đó là đóng đinh lỗi vào chính thước đo.
]
```

- [ ] **Step 5: Chạy cả hai chế độ**

```bash
./.venv/Scripts/python.exe -m pytest tests/evals/test_retrieval_cases.py -q -m "not integration and not live"
./.venv/Scripts/python.exe -m pytest tests/evals/test_retrieval_cases.py -q -m "integration"
```

Kỳ vọng: PASS cả hai. Nếu test hợp đồng đỏ, **sửa nhãn theo đầu ra Step 1** — không sửa test.

- [ ] **Step 6: Commit**

```bash
git add backend/evals/retrieval_cases.py backend/tests/evals/test_retrieval_cases.py
git commit -m "feat(evals): golden set truy xuat ~60 cau + test hop dong nhan"
```

---

## Task 3: `eval_retrieval()` nối vào harness

**Files:**
- Modify: `backend/evals/run_eval.py` (thêm import, thêm hàm, sửa `--set` choices và `_FN` trong `main()`)

**Interfaces:**
- Consumes: `RETRIEVAL_CASES` (Task 2), `label_of` / `score_one` (Task 1), `retrieve` từ `src.rag.retrieve`, `TOP_N` / `TOP_K` từ `src.rag.config`, `run_resilient` từ `jobs.resilience`.
- Produces: `eval_retrieval(pace=0.0, checkpoint_path=None, rerank=True) -> dict` với các khoá `set`, `n`, `recall_at_20`, `recall_at_6`, `mrr`, `chunk_span`, `by_difficulty`, `lat_p50`, `lat_p95`, `fails`, `errors`.

**Điểm khác biệt quan trọng so với mọi bộ eval hiện có:** bộ này **không dùng LLM**. `main()` hiện dựng `_llm(args.model, role=args.set)` cho mọi bộ; `chain_for("retrieval")` sẽ nổ vì `"retrieval"` không nằm trong `catalog.ROLES`. Phải rẽ nhánh.

- [ ] **Step 1: Thêm import**

Trong `backend/evals/run_eval.py`, cạnh các import `from evals ...` sẵn có (quanh dòng 25):

```python
from evals.retrieval_cases import RETRIEVAL_CASES
from evals.retrieval_score import label_of, score_one
from src.rag.retrieve import retrieve as _retrieve
from src.rag.config import TOP_N as _TOP_N, TOP_K as _TOP_K
```

- [ ] **Step 2: Thêm `eval_retrieval()`**

Đặt ngay trước `async def main(...)`:

```python
async def eval_retrieval(pace: float = 0.0, checkpoint_path=None,
                         rerank: bool = True):
    """Đo TẦNG TRUY XUẤT trên corpus thật — KHÔNG gọi LLM lần nào.

    Khác mọi bộ eval khác ở đúng điểm này: `synthesis` và `multi_source` nạp
    fixtures.load_chunks(), tức retriever bị bypass và chúng đo LLM trên ngữ
    cảnh hoàn hảo. Đó là lý do reranker chết 6 tuần mà không số đo nào nhúc
    nhích. Bộ này gọi retrieve() thật.

    rerank=False đặt RAG_RERANK_ENABLED=0 cho cả lượt chạy — chân đối chứng
    của rerank_delta (spec §6).
    """
    import os as _os

    lat: list[float] = []
    per_case: list[dict] = []
    prev = _os.environ.get("RAG_RERANK_ENABLED")
    _os.environ["RAG_RERANK_ENABLED"] = "1" if rerank else "0"

    async def call(case):
        question, expected, difficulty = case
        result, ms = await _timed(asyncio.to_thread(_retrieve, question))
        lat.append(ms)
        ranked = [label_of(c) for c in result.chunks]
        score = score_one(ranked, set(expected), k_pool=_TOP_N, k_final=_TOP_K)
        per_case.append({"question": question, "difficulty": difficulty,
                         "method": result.method, **score})
        if score["recall_at_pool"] > 0:
            return None
        return {"question": question, "difficulty": difficulty,
                "expected": sorted(expected), "got": ranked[:6],
                "method": result.method}

    try:
        fails, errors = await run_resilient(
            [(q, tuple(sorted(e)), d) for q, e, d in RETRIEVAL_CASES],
            call, pace=pace, checkpoint_path=checkpoint_path)
    finally:
        if prev is None:
            _os.environ.pop("RAG_RERANK_ENABLED", None)
        else:
            _os.environ["RAG_RERANK_ENABLED"] = prev

    n = len(RETRIEVAL_CASES)
    m = len(per_case) or 1

    def _avg(key: str, rows=None) -> float:
        rows = per_case if rows is None else rows
        return sum(r[key] for r in rows) / len(rows) if rows else 0.0

    by_difficulty = {}
    for d in ("easy", "hard", "trap"):
        rows = [r for r in per_case if r["difficulty"] == d]
        by_difficulty[d] = {"n": len(rows),
                            "recall_at_20": round(_avg("recall_at_pool", rows), 4),
                            "mrr": round(_avg("reciprocal_rank", rows), 4)}

    # chunk_span: nhãn phủ trung bình bao nhiêu chunk trong KẾT QUẢ. Tăng lên
    # nghĩa là neo (tệp, mục) đang mất sức phân giải (spec §4).
    span = sum(len(r["hit_ranks"]) for r in per_case) / m

    p50, p95 = _percentiles(lat)
    methods = {r["method"] for r in per_case}
    return {"set": "retrieval", "n": n, "rerank": rerank,
            "methods_seen": sorted(methods),
            "recall_at_20": round(_avg("recall_at_pool"), 4),
            "recall_at_6": round(_avg("recall_at_final"), 4),
            "mrr": round(_avg("reciprocal_rank"), 4),
            "chunk_span": round(span, 2),
            "by_difficulty": by_difficulty,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}
```

- [ ] **Step 3: Nối vào `main()`**

Trong `main()`, thêm `"retrieval"` vào `choices` của `--set`:

```python
    ap.add_argument("--set",
                    choices=["intent", "confirm", "chitchat", "planner", "read",
                             "synthesis", "multi_source", "sop_select",
                             "language", "localize", "retrieval"],
                    required=True)
```

Thêm cờ đối chứng ngay sau `--pace`:

```python
    ap.add_argument("--no-rerank", action="store_true",
                    help="chỉ với --set retrieval: chạy chân đối chứng "
                         "RAG_RERANK_ENABLED=0 để tính rerank_delta")
```

Rồi rẽ nhánh **trước** chỗ dựng LLM (thay khối `result = await _FN[...]`):

```python
        _FN = {"intent": eval_intent, "confirm": eval_confirm,
               "chitchat": eval_chitchat, "planner": eval_planner,
               "read": eval_read, "synthesis": eval_synthesis,
               "multi_source": eval_multi_source, "sop_select": eval_sop_select,
               "language": eval_language, "localize": eval_localize,
               "retrieval": eval_retrieval}
        kwargs = {"pace": args.pace}
        if args.set in role_config.ROLE_SENSITIVE_SETS:
            kwargs["role"] = args.role
        if args.set == "retrieval":
            # KHÔNG dựng LLM: bộ này thuần truy xuất. _llm() gọi
            # chain_for("retrieval") mà "retrieval" không nằm trong
            # catalog.ROLES → KeyError nếu đi đường chung.
            kwargs["rerank"] = not args.no_rerank
            result = await eval_retrieval(**kwargs)
        else:
            result = await _FN[args.set](_llm(args.model, role=args.set), **kwargs)
```

- [ ] **Step 4: Chạy thật, cả hai chân**

`--model` vẫn bắt buộc theo argparse; truyền **tên model embedding** vì baseline của bộ này đổi khi embedding đổi, không phải khi LLM đổi:

```bash
./.venv/Scripts/python.exe -m evals.run_eval --set retrieval --model bge-m3
./.venv/Scripts/python.exe -m evals.run_eval --set retrieval --model bge-m3 --no-rerank
```

Kỳ vọng: cả hai in JSON có `recall_at_20`, `mrr`. Lượt đầu `methods_seen == ["hybrid-rrf+rerank"]`, lượt sau `["hybrid-rrf"]`. **Nếu lượt đầu ra `["hybrid-rrf"]` thì reranker đang chết — dừng và điều tra, đừng ghi baseline.**

- [ ] **Step 5: Kiểm bất biến của phép đo**

`recall_at_20` PHẢI bằng nhau giữa hai lượt (rerank chỉ sắp xếp lại pool, không thêm ứng viên). Lệch nghĩa là phép đo hỏng, không phải reranker tốt lên.

```bash
./.venv/Scripts/python.exe -c "
import asyncio, json
from evals.run_eval import eval_retrieval
a = asyncio.run(eval_retrieval(rerank=True))
b = asyncio.run(eval_retrieval(rerank=False))
print('recall@20  on=%.4f  off=%.4f  (PHAI BANG NHAU)' % (a['recall_at_20'], b['recall_at_20']))
print('recall@6   on=%.4f  off=%.4f  delta=%+.4f' % (a['recall_at_6'], b['recall_at_6'], a['recall_at_6']-b['recall_at_6']))
print('mrr        on=%.4f  off=%.4f  delta=%+.4f' % (a['mrr'], b['mrr'], a['mrr']-b['mrr']))
assert abs(a['recall_at_20'] - b['recall_at_20']) < 1e-9, 'PHEP DO HONG'
print('bat bien OK')"
```

- [ ] **Step 6: Ghi baseline**

```bash
./.venv/Scripts/python.exe -m evals.run_eval --set retrieval --model bge-m3 --save-baseline
```

Kỳ vọng: sinh `backend/evals/baseline-bge-m3-retrieval.json`.

- [ ] **Step 7: Chạy toàn bộ test, xác nhận không hồi quy**

```bash
./.venv/Scripts/python.exe -m pytest -q -m "not integration and not live"
./.venv/Scripts/python.exe -m pytest -q -m "integration"
```

Kỳ vọng: PASS cả hai (mốc trước plan: 1706 passed / 2 skipped, và 33 passed).

- [ ] **Step 8: Commit**

```bash
git add backend/evals/run_eval.py backend/evals/baseline-bge-m3-retrieval.json
git commit -m "feat(evals): bo eval retrieval chay retrieve() that + baseline bge-m3"
```

---

## Task 4: Ghi lại kết quả `rerank_delta`

**Files:**
- Modify: `docs/superpowers/specs/2026-08-19-retrieval-eval-design.md` (thêm mục "10. Kết quả đo")

Task này tồn tại vì `rerank_delta` là **lý do tồn tại** của việc ghim `torch==2.11.0+cu128` (~2.5GB). Con số phải nằm trong repo, không phải trong scrollback của một phiên chat.

- [ ] **Step 1: Thêm mục kết quả vào spec**

Chép số THẬT từ Task 3 Step 5 vào bảng (thay `<...>`):

```markdown
## 10. Kết quả đo (baseline đầu tiên, <ngày>)

Corpus 3.300 chunk / 17 tài liệu, embedding `bge-m3`, n=<N> câu.

| Số đo | rerank BẬT | rerank TẮT | delta |
|---|---|---|---|
| `recall_at_20` | <a> | <b> | phải = 0 |
| `recall_at_6`  | <a> | <b> | <±> |
| `mrr`          | <a> | <b> | <±> |

Theo hạng độ khó (rerank BẬT):

| Hạng | n | recall@20 | mrr |
|---|---|---|---|
| easy | | | |
| hard | | | |
| trap | | | |

**Kết luận về `torch==2.11.0+cu128`:** <giữ / gỡ>, vì <lý do dựa trên delta>.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-08-19-retrieval-eval-design.md
git commit -m "docs(spec): ghi ket qua rerank_delta va ket luan ve dep torch"
```

---

## Các plan tiếp theo (KHÔNG thuộc plan này)

Mỗi mục là một plan riêng, **tất cả đều gate vào baseline sinh ra ở đây**:

| Plan | Nội dung | Vì sao cần P0 trước |
|---|---|---|
| P1 | Metadata schema (`doc_type`, `effective_date`, …) + `retrieve(filters=...)` | filter làm tụt recall trên HNSW; không đo thì không biết tụt bao nhiêu |
| P2 | Query rewrite + multi-query (bơm vào `aux_queries` đã có sẵn nhưng không ai gọi) | đây là món rẻ nhất, nhưng "rẻ" chỉ đúng nếu chứng minh được nó nâng recall |
| P3 | Chất lượng ingest: phân cấp luật thật, bỏ heuristic `isupper()`, sửa regex heading bắt giữa câu, PDF 0-block báo lỗi, XLSX gom cửa sổ hàng | đổi chunking là đổi mọi thứ; golden set neo `(tệp, mục)` sống sót được qua nó — đó là lý do chọn neo này |

**Bằng chứng đã đo cho P3 (2026-08-19), không phải phỏng đoán:**

- `_HEADING_RE` khớp cả tham chiếu chéo giữa câu — **15 "mục" trong
  `rag_chunks` thực chất là mảnh câu**: `"Điều 11 của Luật này quy định."`,
  `"Điều 133 của Bộ luật này."`, `"Điều 20 của Luật này được giải quyết thông
  qua một trong những cơ quan, tổ chức sau đây:"`. Mỗi mảnh như vậy **cắt đôi
  một mục thật**, làm nửa sau mất breadcrumb đúng.
- Luật `isupper()` biến quốc hiệu và tên cơ quan thành mục:
  `"CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"`, `"CHỦ TỊCH QUỐC HỘI"`, `"QUỐC HỘI"`,
  `"LUẬT"`.
- Heading PDF phẳng cấp 2 nên `"Chương I"`…`"Chương V"` đứng trơ không tiêu
  đề, và `"Điều 5. …"` KHÔNG nằm dưới chương của nó — phân cấp
  Chương › Điều mất sạch.
- `section_path` trùng giữa các luật: `"Điều 3. Giải thích từ ngữ"` có 32
  chunk nằm rải nhiều tệp. (Đây là lý do golden set neo bằng CẶP.)
| P4 | Thay stub `compress()`, sửa `passes_floor` (`sparse_score is not None` → có ngưỡng) | cả hai đều đổi `recall_at_6`, phải có số trước |
| — | Phân quyền RAG theo vai (`visibility`) — chủ dự án đã hoãn 2026-08-19 | |
