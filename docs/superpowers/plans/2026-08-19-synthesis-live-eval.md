# `synthesis_live` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm bộ eval `synthesis_live` chạy `retrieve()` → `synthesize()` THẬT trên corpus thật, đo `fact_acc` / `refusal_acc` / `citation_acc`, và chứng minh nó nhạy với tầng truy xuất bằng cách đo nhánh `rag-section-cap-parked`.

**Architecture:** Một file dữ liệu ca gây áp lực; một bộ chấm thuần không chạm DB/LLM nên test được ở chế độ mặc định; một hàm `eval_synthesis_live()` nối hai thứ đó với đúng hàm production `synthesize()`. Hàm khớp nguyên văn `_grounded_match` được tách ra module dùng chung trước, để bộ chấm mới dùng lại thay vì sao chép.

**Tech Stack:** Python 3.11, pytest 9.1.1, psycopg 3.3.4 + pgvector, Ollama `bge-m3`, `gemini-3.1-flash-lite` (vai `synthesis`).

**Spec:** `docs/superpowers/specs/2026-08-19-synthesis-live-eval-design.md`

## Global Constraints

- **Định danh trong code viết bằng tiếng Anh.** Tên biến, hàm, tham số, key dict — tiếng Anh. Comment/docstring tiếng Việt.
- **Lệnh pytest LUÔN kèm `-m "not integration and not live"`** trừ khi bước ghi rõ khác. Lệnh trần gọi API LLM thật và đã gây sự cố.
- Chạy pytest từ `backend/`, dùng `./.venv/Scripts/python.exe -m pytest`.
- Chạy `evals.run_eval` cần nạp env trước (nó KHÔNG tự đọc `.env`):
  ```bash
  set -a; . <(grep -E '^(DATABASE_URL|RAG_SCHEMA|RAG_EMBED_PROVIDER|RAG_RERANK_ENABLED|GOOGLE_API_KEY|GROQ_API_KEY|OPENROUTER_API_KEY)=' /d/Youdoo/.env); set +a
  export OLLAMA_URL=http://127.0.0.1:11435 PYTHONIOENCODING=utf-8
  ```
  `PYTHONIOENCODING=utf-8` là **bắt buộc**: thiếu nó, in kết quả chứa tiếng Việt sẽ ném `UnicodeEncodeError` trên console Windows.
- **Không sửa** `src/rag/**`, `src/agents/**`, hay `evals/cases.py`. Plan này chỉ thêm khả năng quan sát.
- Corpus: 3.300 chunk / 17 tài liệu, embedding `bge-m3` / 1024 chiều.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/evals/matching.py` (tạo) | `_norm` + `_grounded_match` chuyển từ `run_eval.py` sang — DI CHUYỂN THUẦN, không đổi logic. Để bộ chấm mới dùng lại thay vì sao chép. |
| `backend/evals/run_eval.py` (sửa) | Import hai hàm trên từ `evals.matching`; thêm `eval_synthesis_live`; nối vào `--set` và `_FN`. |
| `backend/evals/synthesis_live_cases.py` (tạo) | ~20 ca gây áp lực. Dữ liệu thuần, không logic. |
| `backend/evals/synthesis_live_score.py` (tạo) | Chấm một câu trả lời → dict. Không chạm DB/LLM. |
| `backend/tests/evals/test_synthesis_live_score.py` (tạo) | Unit test bộ chấm, chạy ở chế độ mặc định. |
| `backend/tests/evals/test_synthesis_live_cases.py` (tạo) | Test hợp đồng: mọi `expect` phải có thật trong chunk thật, và ca `deep_chunk` phải THỰC SỰ sâu. |
| `backend/evals/baseline-gemini-3.1-flash-lite-synthesis_live.json` (sinh ra) | Baseline. |

---

## Task 1: Tách `_norm` / `_grounded_match` ra module dùng chung

**Files:**
- Create: `backend/evals/matching.py`
- Modify: `backend/evals/run_eval.py` (xoá 2 định nghĩa, thêm 1 dòng import)

**Interfaces:**
- Consumes: không gì.
- Produces: `evals.matching._norm(v) -> str`, `evals.matching._grounded_match(expect: str | tuple[str, ...], body: str) -> bool`. Giữ NGUYÊN tên (kể cả dấu gạch dưới đầu) để 14 chỗ gọi trong `run_eval.py` không phải sửa một ký tự nào.

Đây là **DI CHUYỂN THUẦN**. Không sửa một dòng logic nào. Lý do tách: `synthesis_live_score.py` cần `_grounded_match`, mà nó không thể import `run_eval` (chính `run_eval` sẽ import nó — vòng lặp import).

- [ ] **Step 1: Đọc nguyên văn hai hàm hiện tại**

```bash
cd /d/Youdoo/backend
sed -n '/^def _norm/,/^# Chuẩn hoá 1 lần/p' evals/run_eval.py > /tmp/moved.txt
wc -l /tmp/moved.txt && cat /tmp/moved.txt
```

Đầu ra là `_norm`, `_grounded_match` (kèm docstring dài ~25 dòng) và dòng comment mở đầu khối tiếp theo. **Docstring đó phải đi theo nguyên vẹn** — nó ghi lại lý do bác bỏ khớp mờ, là thứ ngăn người sau vô tình làm lại.

- [ ] **Step 2: Tạo `evals/matching.py` bằng nội dung đã đọc**

Tạo file với header dưới đây, rồi dán **nguyên văn** `_norm` và `_grounded_match` từ Step 1 (KHÔNG gõ lại tay, KHÔNG rút gọn docstring):

```python
# backend/evals/matching.py
"""Khớp nguyên văn dùng chung cho các bộ eval — DI CHUYỂN THUẦN từ run_eval.py
ngày 2026-08-19, không đổi một dòng logic nào.

Vì sao tách: synthesis_live_score.py cần _grounded_match, mà nó không thể
import run_eval (chính run_eval import nó — vòng lặp import). Sao chép hàm
sang file thứ hai là cách chắc chắn nhất để hai bản trôi lệch khỏi nhau.

Tên giữ nguyên dấu gạch dưới đầu để mọi chỗ gọi trong run_eval.py không phải
sửa gì.
"""
```

- [ ] **Step 3: Sửa `run_eval.py` — xoá định nghĩa, thêm import**

Xoá hai hàm `_norm` và `_grounded_match` khỏi `evals/run_eval.py` (giữ nguyên dòng comment `# Chuẩn hoá 1 lần —...` và mọi thứ sau nó). Thêm vào khối import, ngay dưới `from evals import fixtures`:

```python
from evals.matching import _norm, _grounded_match
```

- [ ] **Step 4: Chứng minh là DI CHUYỂN THUẦN, không phải viết lại**

```bash
cd /d/Youdoo/backend
./.venv/Scripts/python.exe -c "
import inspect, evals.matching as m
import subprocess
old = subprocess.run(['git','show','HEAD:backend/evals/run_eval.py'],
                     capture_output=True, text=True, encoding='utf-8', cwd='..').stdout
for fn in ('_norm', '_grounded_match'):
    new_src = inspect.getsource(getattr(m, fn))
    assert new_src.strip() in old.replace('\r\n','\n'), f'{fn} KHONG khop ban goc'
    print(fn, 'khop nguyen van ban goc')
"
```

Kỳ vọng: in ra hai dòng `khớp nguyên văn bản gốc`. Nếu đỏ, bạn đã viết lại chứ không di chuyển — quay lại Step 2.

- [ ] **Step 5: Chạy toàn bộ test**

```bash
./.venv/Scripts/python.exe -m pytest -q -m "not integration and not live"
```

Kỳ vọng: PASS (mốc trước plan: 1722 passed, 2 skipped).

- [ ] **Step 6: Commit**

```bash
cd /d/Youdoo
git add backend/evals/matching.py backend/evals/run_eval.py
git commit -m "refactor(evals): tach _norm/_grounded_match ra evals/matching.py (di chuyen thuan)"
```

---

## Task 2: Bộ chấm thuần

**Files:**
- Create: `backend/evals/synthesis_live_score.py`
- Test: `backend/tests/evals/test_synthesis_live_score.py`

**Interfaces:**
- Consumes: `evals.matching._grounded_match` (Task 1).
- Produces: `score_answer(body: str, kind: str, expect, expect_source: str) -> dict` trả `{"refusal_ok": bool, "fact_ok": bool | None, "citation_ok": bool | None}`. `None` = **không áp dụng** cho loại ca đó (ca `insufficient` không có sự kiện lẫn trích dẫn để chấm). Bên gọi chỉ tính trung bình trên các ca áp dụng — trả `True` thay cho `None` sẽ thổi phồng số đo.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/evals/test_synthesis_live_score.py`:

```python
# backend/tests/evals/test_synthesis_live_score.py
"""Bộ chấm synthesis_live — unit thuần, KHÔNG cần Postgres/Ollama/LLM."""
from src.agents.synthesis import GUARD_MSG
from evals.synthesis_live_score import score_answer

_FOOTER = "\n\n📄 Nguồn:\n• Điều 113. Nghỉ hằng năm (boluat-laodong.pdf, tr.39)"


def test_answerable_all_three_ok():
    body = "Từ ngày thứ 03 trở đi được tính thêm thời gian đi đường." + _FOOTER
    got = score_answer(body, "deep_chunk", "ngày thứ 03", "boluat-laodong.pdf")
    assert got == {"refusal_ok": True, "fact_ok": True, "citation_ok": True}


def test_answerable_refused_is_failure_on_all_applicable():
    # Từ chối một câu TRẢ LỜI ĐƯỢC là hỏng: không có sự kiện, không có footer.
    got = score_answer(GUARD_MSG, "deep_chunk", "ngày thứ 03", "boluat-laodong.pdf")
    assert got == {"refusal_ok": False, "fact_ok": False, "citation_ok": False}


def test_fact_missing_but_citation_right():
    # Dẫn đúng nguồn mà không nêu được sự kiện — hai số đo phải TÁCH nhau,
    # nếu gộp thì không biết lỗi ở truy xuất hay ở sinh.
    body = "Tôi không rõ con số cụ thể." + _FOOTER
    got = score_answer(body, "deep_chunk", "ngày thứ 03", "boluat-laodong.pdf")
    assert got["fact_ok"] is False
    assert got["citation_ok"] is True


def test_fact_right_but_citation_wrong_file():
    # Trả lời ĐÚNG nhưng dẫn NHẦM nguồn — lỗi thật mà fact_acc không thấy.
    body = ("Từ ngày thứ 03 trở đi được tính thêm."
            "\n\n📄 Nguồn:\n• Điều 9. Thuế suất (luat-thuegtgt.pdf, tr.3)")
    got = score_answer(body, "deep_chunk", "ngày thứ 03", "boluat-laodong.pdf")
    assert got["fact_ok"] is True
    assert got["citation_ok"] is False


def test_citation_ok_when_expected_source_among_several():
    # Chấm là "CÓ MẶT", không phải "là nguồn duy nhất" (spec §5): build_citations
    # dựng footer từ mọi chunk sống sót sau verify_citations.
    body = ("ngày thứ 03\n\n📄 Nguồn:\n"
            "• Điều 9. Thuế suất (luat-thuegtgt.pdf, tr.3)\n"
            "• Điều 113. Nghỉ hằng năm (boluat-laodong.pdf, tr.39)")
    got = score_answer(body, "deep_chunk", "ngày thứ 03", "boluat-laodong.pdf")
    assert got["citation_ok"] is True


def test_expect_may_be_tuple_of_observed_alternatives():
    # Cơ chế tuple của _grounded_match: mỗi phương án là một diễn đạt THẬT đã
    # quan sát, vẫn khớp nguyên văn — không có logic mờ nào.
    body = "được tính thêm thời gian đi đường" + _FOOTER
    got = score_answer(body, "deep_chunk",
                       ("ngày thứ 03", "được tính thêm thời gian đi đường"),
                       "boluat-laodong.pdf")
    assert got["fact_ok"] is True


def test_insufficient_refused_correctly():
    got = score_answer(GUARD_MSG, "insufficient", "", "")
    assert got == {"refusal_ok": True, "fact_ok": None, "citation_ok": None}


def test_insufficient_answered_is_fabrication():
    body = "Thủ đô nước Pháp là Paris." + _FOOTER
    got = score_answer(body, "insufficient", "", "")
    assert got["refusal_ok"] is False
    assert got["fact_ok"] is None


def test_distractor_kind_scored_like_answerable():
    body = "Đáp án đúng." + _FOOTER
    got = score_answer(body, "distractor", "Đáp án đúng", "boluat-laodong.pdf")
    assert got == {"refusal_ok": True, "fact_ok": True, "citation_ok": True}


def test_citation_ok_false_when_no_footer_at_all():
    got = score_answer("ngày thứ 03", "deep_chunk", "ngày thứ 03", "boluat-laodong.pdf")
    assert got["fact_ok"] is True
    assert got["citation_ok"] is False


def test_fact_not_matched_from_citation_footer_text():
    # BẪY THẬT: footer chứa section_path, nên nếu expect trùng chữ trong tiêu
    # đề mục thì so khớp trên TOÀN BỘ body sẽ tính ĐẠT dù thân bài không hề
    # nêu. Phải chấm sự kiện trên phần THÂN, không tính footer.
    body = "Tôi không tìm thấy thông tin.\n\n📄 Nguồn:\n• Điều 113. Nghỉ hằng năm (boluat-laodong.pdf, tr.39)"
    got = score_answer(body, "deep_chunk", "Nghỉ hằng năm", "boluat-laodong.pdf")
    assert got["fact_ok"] is False
```

- [ ] **Step 2: Chạy để xác nhận đỏ**

```bash
cd /d/Youdoo/backend
./.venv/Scripts/python.exe -m pytest tests/evals/test_synthesis_live_score.py -q -m "not integration and not live"
```

Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'evals.synthesis_live_score'`.

- [ ] **Step 3: Viết implementation**

Tạo `backend/evals/synthesis_live_score.py`:

```python
# backend/evals/synthesis_live_score.py
"""Chấm điểm synthesis_live — THUẦN, không chạm DB/Ollama/LLM.

Tách khỏi run_eval.py để toàn bộ logic chấm chạy trong chế độ pytest mặc
định. Cùng lối đã dùng cho evals/retrieval_score.py.

GUARD_MSG import từ chính production (src.agents.synthesis) chứ không chép
lại chuỗi: bộ đo phải hỏng lớn tiếng nếu ai đổi câu từ chối, thay vì âm thầm
chấm sai.
"""
from src.agents.synthesis import GUARD_MSG
from evals.matching import _grounded_match

CITATION_HEADER = "📄 Nguồn:"


def split_body_and_footer(answer: str) -> tuple[str, str]:
    """Tách thân bài khỏi footer trích dẫn.

    BẮT BUỘC tách trước khi chấm sự kiện: footer chứa section_path, nên một
    `expect` trùng chữ với tiêu đề mục ("Nghỉ hằng năm") sẽ khớp nhờ footer dù
    thân bài không hề nêu — tính ĐẠT cho một câu trả lời rỗng."""
    head, sep, tail = answer.partition(CITATION_HEADER)
    return (head, tail) if sep else (answer, "")


def score_answer(body: str, kind: str, expect, expect_source: str) -> dict:
    """Chấm MỘT câu trả lời đầu-cuối.

    kind: "deep_chunk" | "distractor" | "insufficient".
    Trả None cho số đo KHÔNG áp dụng — ca `insufficient` không có sự kiện lẫn
    trích dẫn để chấm. Bên gọi chỉ trung bình trên ca áp dụng; trả True thay
    cho None sẽ thổi phồng số đo.
    """
    answer = body or ""
    refused = GUARD_MSG in answer
    if kind == "insufficient":
        return {"refusal_ok": refused, "fact_ok": None, "citation_ok": None}

    text, footer = split_body_and_footer(answer)
    return {
        "refusal_ok": not refused,
        "fact_ok": (not refused) and _grounded_match(expect, text),
        "citation_ok": (not refused) and bool(footer) and expect_source in footer,
    }
```

- [ ] **Step 4: Chạy để xác nhận xanh**

```bash
./.venv/Scripts/python.exe -m pytest tests/evals/test_synthesis_live_score.py -q -m "not integration and not live"
```

Kỳ vọng: PASS, 11 test.

- [ ] **Step 5: Commit**

```bash
cd /d/Youdoo
git add backend/evals/synthesis_live_score.py backend/tests/evals/test_synthesis_live_score.py
git commit -m "feat(evals): bo cham synthesis_live (fact/refusal/citation), tach than bai khoi footer"
```

---

## Task 3: Bộ ca gây áp lực + test hợp đồng

**Files:**
- Create: `backend/evals/synthesis_live_cases.py`
- Test: `backend/tests/evals/test_synthesis_live_cases.py`

**Interfaces:**
- Consumes: không gì (dữ liệu thuần).
- Produces: `SYNTHESIS_LIVE_CASES: list[tuple[str, str, object, str]]` — `(question, kind, expect, expect_source)`. `kind` ∈ `{"deep_chunk", "distractor", "insufficient"}`. `expect` là `str` hoặc `tuple[str, ...]`. `expect_source` là **basename** (`"boluat-laodong.pdf"`), đúng thứ `build_citations` in ra.

- [ ] **Step 1: Khai thác ứng viên `deep_chunk` từ corpus thật**

**KHÔNG viết `expect` theo trí nhớ.** Chạy script này để lấy danh sách mục có số liệu riêng chỉ xuất hiện từ chunk thứ 2 trở đi (đo 2026-08-19: 191 mục như vậy):

```bash
cd /d/Youdoo/backend
./.venv/Scripts/python.exe -c "
import sys, io, re; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from dotenv import load_dotenv; load_dotenv('../.env')
from src.rag import db
from collections import defaultdict
c = db.connect()
rows = c.execute('select source_file, section_path, chunk_index, chunk_text from rag_chunks where section_path is not null').fetchall()
c.close()
sec = defaultdict(list)
for sf, sp, ci, tx in rows: sec[(sf, sp)].append((ci, tx))
num = re.compile(r'\d+(?:[.,]\d+)?\s*(?:%|ngày|tháng|năm|đồng|lần)')
for (sf, sp), items in sec.items():
    if len(items) < 2: continue
    items.sort(); first = items[0][1]
    for ci, tx in items[1:]:
        hits = [m.group(0) for m in num.finditer(tx) if m.group(0) not in first]
        if hits:
            print('%-26s | %-46s | idx=%d | %s' % (
                sf.replace(chr(92),'/').split('/')[-1][:26], sp[:46], ci, hits[:3]))
            break
" > /tmp/deep.txt; wc -l < /tmp/deep.txt; head -30 /tmp/deep.txt
```

- [ ] **Step 2: Xác minh từng chuỗi `expect` là DUY NHẤT trong corpus**

Với mỗi chuỗi định dùng, chạy:

```bash
./.venv/Scripts/python.exe -c "
import sys, io; sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from dotenv import load_dotenv; load_dotenv('../.env')
from src.rag import db
c = db.connect()
s = 'THAY_BANG_CHUOI_CAN_KIEM'
rows = c.execute('select source_file, section_path, chunk_index from rag_chunks where chunk_text like %s', ('%'+s+'%',)).fetchall()
print(len(rows), 'chunk khop')
for sf, sp, ci in rows:
    print('  ', sf.replace(chr(92),'/').split('/')[-1], '|', sp, '| idx =', ci)
c.close()"
```

Chuỗi tốt = khớp **đúng 1 chunk**, và `chunk_index` của nó **không phải** chỉ số nhỏ nhất của mục đó. Ví dụ đã xác minh 2026-08-19: `"từ ngày thứ 03 trở đi được tính thêm thời gian đi đường"` khớp đúng 1 chunk, `boluat-laodong.pdf › Điều 113. Nghỉ hằng năm`, `idx=193`, trong khi chunk đầu của mục là `idx=191`.

- [ ] **Step 3: Viết test hợp đồng (đỏ trước)**

Tạo `backend/tests/evals/test_synthesis_live_cases.py`:

```python
# backend/tests/evals/test_synthesis_live_cases.py
"""Hợp đồng bộ ca synthesis_live ↔ corpus thật.

Bài học GATHER_CASES: fixture trôi khỏi dữ liệu thật mà không ai biết, phải
thêm test hợp đồng sau. Lần này viết cùng lúc.

Test `deep_chunk` ở đây làm nhiều hơn kiểm chính tả: nó khẳng định ca đó THỰC
SỰ sâu. Một ca `deep_chunk` mà đáp án nằm ở chunk ĐẦU của mục là ca gắn nhãn
sai — nó không gây áp lực gì lên tầng truy xuất, và cả bộ eval sẽ vô cảm đúng
như recall@6 đã vô cảm.
"""
import pytest

from evals.synthesis_live_cases import SYNTHESIS_LIVE_CASES
from src.rag import db as _db


def _expects(expect):
    return expect if isinstance(expect, tuple) else (expect,)


def test_kind_chi_nhan_ba_gia_tri():
    for q, kind, _e, _s in SYNTHESIS_LIVE_CASES:
        assert kind in ("deep_chunk", "distractor", "insufficient"), \
            f"loại lạ {kind!r} ở ca {q!r}"


def test_co_du_ca_ba_loai():
    seen = {k for _q, k, _e, _s in SYNTHESIS_LIVE_CASES}
    assert seen == {"deep_chunk", "distractor", "insufficient"}


def test_ca_tra_loi_duoc_phai_co_expect_va_nguon():
    for q, kind, expect, source in SYNTHESIS_LIVE_CASES:
        if kind == "insufficient":
            continue
        assert expect, f"ca {q!r} thiếu expect"
        assert source.endswith((".pdf", ".docx", ".xlsx")), \
            f"expect_source của {q!r} phải là basename có đuôi tệp, gặp {source!r}"


def test_khong_co_cau_hoi_trung_lap():
    questions = [q for q, _k, _e, _s in SYNTHESIS_LIVE_CASES]
    assert len(questions) == len(set(questions))


@pytest.mark.integration
def test_moi_expect_co_that_trong_dung_tep_nguon():
    conn = _db.connect()
    try:
        bad = []
        for q, kind, expect, source in SYNTHESIS_LIVE_CASES:
            if kind == "insufficient":
                continue
            for alt in _expects(expect):
                n = conn.execute(
                    "select count(*) from rag_chunks "
                    "where source_file like %s and chunk_text like %s",
                    ("%" + source, "%" + alt + "%")).fetchone()[0]
                if n == 0:
                    bad.append((q, alt, source))
    finally:
        conn.close()
    assert not bad, (
        f"{len(bad)} chuỗi expect KHÔNG có trong tệp nguồn đã khai — bộ ca đã "
        f"trôi khỏi corpus hoặc chép sai: {bad[:5]}")


@pytest.mark.integration
def test_ca_deep_chunk_thuc_su_nam_o_chunk_sau():
    """Đáp án phải nằm ngoài chunk ĐẦU của mục, nếu không ca này vô nghĩa."""
    conn = _db.connect()
    try:
        shallow = []
        for q, kind, expect, source in SYNTHESIS_LIVE_CASES:
            if kind != "deep_chunk":
                continue
            first_alt = _expects(expect)[0]
            row = conn.execute(
                "select section_path, chunk_index from rag_chunks "
                "where source_file like %s and chunk_text like %s "
                "order by chunk_index limit 1",
                ("%" + source, "%" + first_alt + "%")).fetchone()
            assert row is not None, f"không tìm thấy chunk chứa {first_alt!r}"
            section, idx = row
            first_idx = conn.execute(
                "select min(chunk_index) from rag_chunks "
                "where source_file like %s and section_path = %s",
                ("%" + source, section)).fetchone()[0]
            if idx == first_idx:
                shallow.append((q, section, idx))
    finally:
        conn.close()
    assert not shallow, (
        f"{len(shallow)} ca gắn nhãn deep_chunk nhưng đáp án nằm ở chunk ĐẦU "
        f"của mục — không gây áp lực gì lên tầng truy xuất: {shallow}")


@pytest.mark.integration
def test_ca_distractor_co_expect_duy_nhat_o_mot_tep():
    """Với ca bẫy, expect phải CHỈ có ở tệp nguồn đúng — nhờ vậy trả lời đúng
    chuỗi đó là bằng chứng đã dùng ĐÚNG văn bản, không phải văn bản gần giống."""
    conn = _db.connect()
    try:
        leaky = []
        for q, kind, expect, source in SYNTHESIS_LIVE_CASES:
            if kind != "distractor":
                continue
            for alt in _expects(expect):
                n = conn.execute(
                    "select count(*) from rag_chunks "
                    "where source_file not like %s and chunk_text like %s",
                    ("%" + source, "%" + alt + "%")).fetchone()[0]
                if n:
                    leaky.append((q, alt, n))
    finally:
        conn.close()
    assert not leaky, (
        f"expect của ca bẫy xuất hiện ở tệp KHÁC nên không chứng minh được gì: "
        f"{leaky[:5]}")
```

- [ ] **Step 4: Chạy để xác nhận đỏ**

```bash
./.venv/Scripts/python.exe -m pytest tests/evals/test_synthesis_live_cases.py -q -m "not integration and not live"
```

Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'evals.synthesis_live_cases'`.

- [ ] **Step 5: Viết bộ ca**

Tạo `backend/evals/synthesis_live_cases.py`. Khung dưới có **1 ca đã xác minh đầy đủ** làm mẫu; mở rộng lên **~20 ca** bằng đầu ra Step 1 và phép kiểm Step 2.

Phân bổ bắt buộc: **≥10 ca `deep_chunk`**, **≥5 ca `distractor`**, **≥4 ca `insufficient`**.

```python
# backend/evals/synthesis_live_cases.py
"""Bộ ca gây áp lực cho synthesis_live — spec 2026-08-19 §4.

CẤU TRÚC: (question, kind, expect, expect_source)
  kind:
    deep_chunk   — đáp án nằm ở chunk thứ 2+ của một Điều dài. Bắt mọi thay
                   đổi ở compress()/TOP_K làm mất phần sau của đúng điều luật.
                   55% chunk của corpus nằm trong mục nhiều-chunk.
    distractor   — có điều luật gần-đúng trong pool mang con số KHÁC. Bắt lỗi
                   "trả lời đúng số của nhầm văn bản" (spec P0 §11.1).
    insufficient — ngoài corpus hoàn toàn. Bắt bịa, và bắt guard hỏng.
  expect: chuỗi phải xuất hiện NGUYÊN VĂN, hoặc tuple nhiều phương án ĐÃ QUAN
          SÁT THẬT (cơ chế của _grounded_match — không có logic mờ nào).
  expect_source: BASENAME tệp, đúng thứ build_citations in ra.

MỌI CHUỖI expect PHẢI CHÉP TỪ CHUNK THẬT. test_synthesis_live_cases.py chốt
lại: có thật trong đúng tệp, ca deep_chunk thực sự nằm ở chunk sau, và expect
của ca bẫy không rò sang tệp khác.

KHÔNG dùng các "mục" rác do parse_pdf sinh ra (quốc hiệu, tên cơ quan, mảnh
câu tham chiếu chéo "Điều 11 của Luật này quy định.") — chúng sẽ biến mất khi
P3 chạy.
"""

SYNTHESIS_LIVE_CASES: list[tuple[str, str, object, str]] = [

    # ── deep_chunk ────────────────────────────────────────────────────────
    # ĐÃ XÁC MINH 2026-08-19: chuỗi khớp đúng 1 chunk trong toàn corpus,
    # boluat-laodong.pdf › "Điều 113. Nghỉ hằng năm", chunk_index=193, trong
    # khi chunk ĐẦU của mục là 191. Chunk đầu nói "12 ngày"/"14 ngày" (số
    # ngày phép) — con số hoàn toàn khác, nên trả lời đúng chuỗi này chứng
    # minh đã đọc tới chunk thứ ba.
    ("nghỉ phép hằng năm mà đi đường mất nhiều ngày thì có được tính thêm không?",
     "deep_chunk",
     "từ ngày thứ 03 trở đi được tính thêm thời gian đi đường",
     "boluat-laodong.pdf"),

    # THÊM >=9 ca deep_chunk nữa từ /tmp/deep.txt (Step 1), mỗi ca qua phép
    # kiểm Step 2 trước khi viết vào đây.

    # ── distractor ────────────────────────────────────────────────────────
    # THÊM >=5 ca. Công thức: chọn một chủ đề mà >=2 luật cùng nói tới
    # ("thời hạn nộp thuế" có ở cả luat-quanlythue lẫn luat-thuexuatnhapkhau;
    # "phạt vi phạm" có ở cả boluat-thuongmai lẫn boluat-danssu), rồi lấy
    # expect là chuỗi CHỈ có ở tệp đúng — test_ca_distractor_co_expect_duy_
    # nhat_o_mot_tep chốt điều đó.

    # ── insufficient ──────────────────────────────────────────────────────
    # Chủ đề ngoài corpus hoàn toàn. expect và expect_source để rỗng.
    ("giá cổ phiếu công ty hôm nay là bao nhiêu?", "insufficient", "", ""),
    ("thủ đô nước Pháp là thành phố nào?", "insufficient", "", ""),
    ("dự báo thời tiết Hà Nội tuần sau thế nào?", "insufficient", "", ""),
    ("giám đốc công ty tên gì?", "insufficient", "", ""),
]
```

- [ ] **Step 6: Chạy cả hai chế độ**

```bash
./.venv/Scripts/python.exe -m pytest tests/evals/test_synthesis_live_cases.py -q -m "not integration and not live"
./.venv/Scripts/python.exe -m pytest tests/evals/test_synthesis_live_cases.py -q -m "integration"
```

Kỳ vọng: PASS cả hai. Test đỏ thì **sửa bộ ca theo corpus**, KHÔNG sửa test.

- [ ] **Step 7: Commit**

```bash
cd /d/Youdoo
git add backend/evals/synthesis_live_cases.py backend/tests/evals/test_synthesis_live_cases.py
git commit -m "feat(evals): bo ca gay ap luc synthesis_live + test hop dong deep_chunk"
```

---

## Task 4: `eval_synthesis_live()` và nối vào harness

**Files:**
- Modify: `backend/evals/run_eval.py`

**Interfaces:**
- Consumes: `SYNTHESIS_LIVE_CASES` (Task 3), `score_answer` (Task 2), `retrieve` từ `src.rag.retrieve`, `synthesize` từ `src.agents.synthesis`, `run_resilient` từ `jobs.resilience`.
- Produces: `eval_synthesis_live(llm, pace=0.0, checkpoint_path=None) -> dict` với các khoá `set`, `n`, `fact_acc`, `refusal_acc`, `citation_acc`, `by_kind`, `lat_p50`, `lat_p95`, `fails`, `errors`.

- [ ] **Step 1: Thêm import**

Trong `backend/evals/run_eval.py`, cạnh các import `from evals ...`:

```python
from evals.synthesis_live_cases import SYNTHESIS_LIVE_CASES
from evals.synthesis_live_score import score_answer
from src.agents.synthesis import synthesize as _synthesize
```

(`_retrieve` đã được import sẵn từ bộ `retrieval`.)

- [ ] **Step 2: Thêm hàm, đặt ngay trước `async def main(`**

```python
async def eval_synthesis_live(llm, pace: float = 0.0, checkpoint_path=None):
    """Đo chuỗi TRẢ LỜI TÀI LIỆU đầu-cuối: retrieve() thật → synthesize() thật.

    Khác `synthesis` ở đúng một điểm, và đó là điểm quan trọng nhất:
    `synthesis` nạp fixtures.load_chunks() nên retriever bị bypass, còn bộ này
    gọi retrieve() thật trên corpus thật. Đó là lý do reranker chết 6 tuần mà
    không số đo nào nhúc nhích (spec 2026-08-19 §1).

    Gọi ĐÚNG synthesize() của production, không mirror hình dạng prompt. Bài
    học SP-2a: eval_intent mirror hợp đồng ở module khác, hợp đồng đổi, acc rơi
    0,870 → 0,148 và không ai nghi ngờ vì lỗi trông y hệt lỗi chất lượng model.
    """
    lat: list[float] = []
    per_case: list[dict] = []

    async def call(case):
        question, kind, expect, source = case
        expect = tuple(expect) if isinstance(expect, list) else expect
        result = await asyncio.to_thread(_retrieve, question)
        answer, ms = await _timed(_synthesize(question, result, llm))
        lat.append(ms)
        score = score_answer(answer, kind, expect, source)
        per_case.append({"kind": kind, **score})
        if all(v is not False for v in score.values()):
            return None
        return {"question": question, "kind": kind, "expect": expect,
                "expect_source": source, "answer": answer[:400], **score}

    # expect có thể là tuple → chuyển sang list cho JSON-serializable, vì
    # run_resilient ghi item vào error-record và checkpoint.
    items = [(q, k, list(e) if isinstance(e, tuple) else e, s)
             for q, k, e, s in SYNTHESIS_LIVE_CASES]
    fails, errors = await run_resilient(items, call, pace=pace,
                                        checkpoint_path=checkpoint_path)

    def _acc(key: str, rows) -> float:
        vals = [r[key] for r in rows if r[key] is not None]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    by_kind = {}
    for k in ("deep_chunk", "distractor", "insufficient"):
        rows = [r for r in per_case if r["kind"] == k]
        by_kind[k] = {"n": len(rows), "fact_acc": _acc("fact_ok", rows),
                      "refusal_acc": _acc("refusal_ok", rows),
                      "citation_acc": _acc("citation_ok", rows)}

    p50, p95 = _percentiles(lat)
    return {"set": "synthesis_live", "n": len(SYNTHESIS_LIVE_CASES),
            "fact_acc": _acc("fact_ok", per_case),
            "refusal_acc": _acc("refusal_ok", per_case),
            "citation_acc": _acc("citation_ok", per_case),
            "by_kind": by_kind,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}
```

- [ ] **Step 3: Nối vào `main()`**

Thêm `"synthesis_live"` vào `choices` của `--set`:

```python
                    choices=["intent", "confirm", "chitchat", "planner", "read",
                             "synthesis", "multi_source", "sop_select",
                             "language", "localize", "retrieval",
                             "synthesis_live"],
```

Thêm vào `_FN`:

```python
               "retrieval": eval_retrieval,
               "synthesis_live": eval_synthesis_live}
```

Rồi sửa chỗ rẽ nhánh dựng LLM (khối đã có từ bộ `retrieval`) thành:

```python
        if args.set == "retrieval":
            # KHÔNG dựng LLM: bộ này thuần truy xuất.
            kwargs["rerank"] = not args.no_rerank
            result = await eval_retrieval(**kwargs)
        elif args.set == "synthesis_live":
            # "synthesis_live" KHÔNG nằm trong catalog.ROLES; production chạy
            # rag_node bằng llms["synthesis"], nên dùng đúng vai đó.
            result = await eval_synthesis_live(_llm(args.model, role="synthesis"),
                                               **kwargs)
        else:
            result = await _FN[args.set](_llm(args.model, role=args.set), **kwargs)
```

- [ ] **Step 4: Chạy thật**

```bash
cd /d/Youdoo/backend
set -a; . <(grep -E '^(DATABASE_URL|RAG_SCHEMA|RAG_EMBED_PROVIDER|RAG_RERANK_ENABLED|GOOGLE_API_KEY|GROQ_API_KEY|OPENROUTER_API_KEY)=' /d/Youdoo/.env); set +a
export OLLAMA_URL=http://127.0.0.1:11435 PYTHONIOENCODING=utf-8
./.venv/Scripts/python.exe -m evals.run_eval --set synthesis_live --model gemini-3.1-flash-lite --pace 4.8
```

`--pace 4.8` suy từ catalog: `(60/rpm)*1.2` với `rpm=15`.

Kỳ vọng: in JSON có `fact_acc`, `refusal_acc`, `citation_acc`, `by_kind`. Nếu `errors` không rỗng, đọc lý do trước khi ghi baseline — đừng đóng băng một lượt chạy hỏng.

- [ ] **Step 5: Ghi baseline**

```bash
./.venv/Scripts/python.exe -m evals.run_eval --set synthesis_live --model gemini-3.1-flash-lite --pace 4.8 --save-baseline
```

Kỳ vọng: sinh `backend/evals/baseline-gemini-3.1-flash-lite-synthesis_live.json`.

- [ ] **Step 6: Dọn docstring `eval_retrieval` cho đồng bộ**

`eval_retrieval` (thêm 2026-08-19, cùng file) viết docstring bằng tiếng Việt
**không dấu**, trong khi mọi hàm lân cận trong `run_eval.py` đều có dấu. Đây
là lỗi nhất quán lọt vào ở đợt trước, và sửa ngay lúc đang mở file thì rẻ hơn
để nó sinh sôi.

Đổi dòng docstring đầu của `eval_retrieval` và các comment không dấu trong
thân hàm sang tiếng Việt **có dấu**, giữ nguyên từng ý — KHÔNG viết lại nội
dung, chỉ bỏ dấu vào. Không đụng logic.

- [ ] **Step 7: Chạy toàn bộ test**

```bash
./.venv/Scripts/python.exe -m pytest -q -m "not integration and not live"
./.venv/Scripts/python.exe -m pytest -q -m "integration"
```

Kỳ vọng: PASS cả hai.

- [ ] **Step 8: Commit**

```bash
cd /d/Youdoo
git add backend/evals/run_eval.py backend/evals/baseline-gemini-3.1-flash-lite-synthesis_live.json
git commit -m "feat(evals): eval_synthesis_live chay retrieve()->synthesize() that + baseline"
```

---

## Task 5: Nghiệm thu — bộ eval phải tự chứng minh là nó nhạy

**Files:**
- Modify: `docs/superpowers/specs/2026-08-19-synthesis-live-eval-design.md` (thêm §9)

Đây là mục quan trọng nhất của cả plan (spec §6). Không có bước này thì ta chỉ có thêm một bộ đo chưa ai biết nó đo được gì.

- [ ] **Step 1: Đo trên nhánh park (`cap=1`)**

Nhánh `rag-section-cap-parked` chứa `compress()` trần-theo-mục cùng `RAG_SECTION_CAP`. Lấy đúng hai file đó vào cây làm việc **mà không đổi nhánh** (nhánh hiện tại đang có bộ eval mới, nhánh park thì không):

```bash
cd /d/Youdoo
git checkout rag-section-cap-parked -- backend/src/rag/config.py backend/src/rag/retrieve.py
git status --short   # chỉ 2 file này được đổi
```

Rồi chạy hai lượt:

```bash
cd backend
set -a; . <(grep -E '^(DATABASE_URL|RAG_SCHEMA|RAG_EMBED_PROVIDER|RAG_RERANK_ENABLED|GOOGLE_API_KEY|GROQ_API_KEY|OPENROUTER_API_KEY)=' /d/Youdoo/.env); set +a
export OLLAMA_URL=http://127.0.0.1:11435 PYTHONIOENCODING=utf-8

RAG_SECTION_CAP=1 ./.venv/Scripts/python.exe -m evals.run_eval --set synthesis_live --model gemini-3.1-flash-lite --pace 4.8 > /tmp/cap1.json
RAG_SECTION_CAP=0 ./.venv/Scripts/python.exe -m evals.run_eval --set synthesis_live --model gemini-3.1-flash-lite --pace 4.8 > /tmp/cap0.json
```

- [ ] **Step 2: Trả cây làm việc về sạch**

```bash
cd /d/Youdoo
git checkout HEAD -- backend/src/rag/config.py backend/src/rag/retrieve.py
git status --short   # không còn 2 file đó
grep -c SECTION_CAP backend/src/rag/retrieve.py   # phải in 0
```

**Đừng bỏ qua bước này.** Bỏ sót sẽ commit code park vào nhánh chính một cách âm thầm.

- [ ] **Step 3: So hai lượt**

```bash
cd /d/Youdoo/backend
./.venv/Scripts/python.exe -c "
import json, re
def load(p):
    t = open(p, encoding='utf-8').read()
    return json.loads(t[t.index('{'):t.rindex('}')+1])
a, b = load('/tmp/cap1.json'), load('/tmp/cap0.json')
print('%-13s %8s %8s %9s' % ('so do', 'cap=1', 'cap=0', 'delta'))
for k in ('fact_acc', 'refusal_acc', 'citation_acc'):
    print('%-13s %8.4f %8.4f %+9.4f' % (k, a[k], b[k], a[k]-b[k]))
for kind in ('deep_chunk', 'distractor'):
    print('  %s fact: %.4f vs %.4f' % (kind, a['by_kind'][kind]['fact_acc'],
                                        b['by_kind'][kind]['fact_acc']))
"
```

- [ ] **Step 4: Ghi kết quả vào spec — kể cả khi kết quả là ÂM**

Thêm mục §9 vào `docs/superpowers/specs/2026-08-19-synthesis-live-eval-design.md`, điền số thật:

```markdown
## 9. Nghiệm thu độ nhạy (ngày <ngày>)

Đo bộ eval trên nhánh `rag-section-cap-parked`, `RAG_SECTION_CAP=1` vs `=0`:

| Số đo | cap=1 | cap=0 | delta |
|---|---|---|---|
| `fact_acc` | | | |
| `refusal_acc` | | | |
| `citation_acc` | | | |

`deep_chunk` fact_acc: <a> vs <b>.

**Kết luận:** <bộ eval NHẠY / KHÔNG nhạy với tầng truy xuất>, vì <lý do dựa
trên số>.

**Hệ quả cho nhánh park:** <merge / bỏ / vẫn chưa quyết, và vì sao>.
```

Nếu delta bằng 0 ở mọi số đo, **viết đúng như vậy**. Spec §6 đã chốt trước rằng kết quả âm cũng là kết luận có giá trị — đừng tô hồng, và đừng đi thêm ca cho tới khi hết delta.

- [ ] **Step 5: Commit**

```bash
cd /d/Youdoo
git add docs/superpowers/specs/2026-08-19-synthesis-live-eval-design.md
git commit -m "docs(spec): nghiem thu do nhay cua synthesis_live tren nhanh park"
```

---

## Sau plan này

| Việc | Điều kiện mở |
|---|---|
| Quyết định nhánh `rag-section-cap-parked` | Task 5 cho số |
| P3 dọn rác ingest | Nay đo được ảnh hưởng tới câu trả lời, không chỉ tới hạng |
| P1 metadata filtering, P2 query rewrite, P4 `compress`/`passes_floor` | Cả bốn đổi ngữ cảnh gửi cho LLM — nay có thước đo |
| Mở rộng nhóm `hard` của golden set P0 | Kết luận "rerank hại câu hard" đang dựa trên n=17 |
