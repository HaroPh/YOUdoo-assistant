# Câu hỏi tổng hợp — Kế hoạch A: đo được và sửa nền

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Câu hỏi dạng "tóm tắt / tổng quan / liệt kê / có bao nhiêu" trên đường tài liệu trở nên **đo được** (bộ eval `aggregate` với hai thước độ phủ), và hai lỗi nền chặn mọi hướng sửa sau đó được đóng: `doc_title` trùng nhau ở 8/9 PDF luật, và `retrieve()` không biết mình đã đọc bao nhiêu phần của tài liệu.

**Architecture:** Ba khối độc lập, không khối nào đổi hành vi TRẢ LỜI. (1) Bộ eval mới `aggregate` — chấm bằng ĐỘ PHỦ (`doc_coverage`, `section_coverage`) chứ không phải "≥1 nhãn lọt top-k", vì với câu tổng hợp thước cũ sai về bản chất; thuần Python, không LLM. (2) `doc_title` suy từ heading đầu tiên KHÔNG PHẢI quốc hiệu, cộng cổng `Warning` phát khi hai `doc_id` mang cùng tên — heuristic nào rồi cũng sai, thứ không được phép là sai IM LẶNG. (3) `retrieve()` trả thêm `coverage` cho biết đã chạm bao nhiêu chunk/mục trên tổng của từng tài liệu; Kế hoạch A chỉ PHƠI con số, chưa dùng nó trong prompt.

**Tech Stack:** Python 3.11, psycopg 3, pytest, Postgres 17 + pgvector.

**Spec:** `docs/superpowers/specs/2026-09-08-cau-hoi-tong-hop-design.md` — đọc trước khi bắt đầu, đặc biệt mục 1 (số đo đề bài), mục 6 (bốn phương án `doc_title` và vì sao chọn B), mục 7 (vì sao thước cũ sai) và mục 9 (rủi ro chưa đóng).

## Global Constraints

- **Định danh trong MÃ SẢN PHẨM (`backend/src`) đặt tên tiếng Anh.** Chú thích, docstring, thông điệp lỗi viết tiếng Việt. *(Tên hàm test tiếng Việt là quy ước sẵn có của `backend/tests`, giữ nguyên.)*
- **Mọi lệnh pytest PHẢI kèm** `-m "not integration and not live"` **và** `PYTHONIOENCODING=utf-8`, dùng `.venv/Scripts/python.exe` chứ không phải `python` trần. `pytest.ini` không có `addopts` loại trừ, còn `conftest.py` tự nạp `.env` THẬT — lệnh trần sẽ gọi API LLM thật và chạm Postgres. Đã gây sự cố thật 2026-08-13.
- **Worktree KHÔNG có `.venv` riêng.** Dùng interpreter cây chính với cwd trong worktree.
- **Mốc nền suite: ĐO LẠI TRƯỚC KHI BẮT ĐẦU.** Số `2474 passed, 1 skipped, 83 deselected` (2026-09-08) đã CŨ — ngày 2026-09-17 `main` đo `2707 passed, 1 skipped, 113 deselected` sau 4 lượt merge. Mọi con số "Expected: N passed" trong plan này viết theo mốc 2474; cộng lệch (+233 passed, +30 deselected) hoặc tự tính lại từ mốc mới. Mọi task phải giữ hoặc tăng số passed.
- **Không đổi một bit hành vi trả lời trong Kế hoạch A.** `RAG_SYNTHESIS_PROMPT`, `COS_FLOOR`, `TOP_K`, `routing.py` KHÔNG được sửa. Chúng thuộc Kế hoạch B và cần A/B `synthesis_live`.
- **Nhãn trong golden set phải ĐỐI CHIẾU với `rag_chunks` thật, chép nguyên văn** — không viết theo trí nhớ. Test hợp đồng (`integration`) gác lại điều này.
- **Không hằng số rút từ không khí.** Ngưỡng nào cũng phải kèm số đo hoặc lý do trong spec.
- Dấu phân cách breadcrumb là `" › "` (U+203A có khoảng trắng hai bên), phải trùng `chunking.chunk_text_blocks`.

---

## File Structure

| tệp | trách nhiệm |
|---|---|
| `backend/evals/aggregate_score.py` | **Tạo mới.** Chấm điểm độ phủ. THUẦN — không chạm DB/Ollama/LLM, chạy được ở chế độ pytest mặc định. |
| `backend/evals/aggregate_cases.py` | **Tạo mới.** Golden set câu hỏi tổng hợp, nhãn viết tay đã đối chiếu corpus. |
| `backend/evals/run_eval.py` | **Sửa.** Thêm `eval_aggregate()` và `--set aggregate`. |
| `backend/tests/evals/test_aggregate_score.py` | **Tạo mới.** Chấm điểm — thuần dữ liệu giả, không cần DB. |
| `backend/tests/evals/test_aggregate_cases.py` | **Tạo mới.** Hợp đồng golden set ↔ corpus thật (`integration`). |
| `backend/src/rag/chunking.py` | **Sửa.** `doc_title` bỏ qua quốc hiệu; thêm `document_title()`. |
| `backend/tests/rag/test_document_title.py` | **Tạo mới.** Bộ suy tên tài liệu, thuần `list[dict]`. |
| `backend/src/rag/ingest.py` | **Sửa.** Cổng trùng tên → `Warning` của `ingest_report`. |
| `backend/tests/rag/test_cong_trung_ten.py` | **Tạo mới.** Chân đối chứng cổng trùng tên. |
| `backend/src/rag/types.py` | **Sửa.** `DocCoverage` + `RetrievalResult.coverage`. |
| `backend/src/rag/retrieve.py` | **Sửa.** Tính `coverage` sau `compress()`. |
| `backend/tests/rag/test_coverage_signal.py` | **Tạo mới.** Tín hiệu độ phủ, dùng conn giả + một ca `integration`. |

**Thứ tự bắt buộc:** Task 1 → 2 → 3 (lấy mốc nền TRƯỚC khi sửa gì) → 4 → 5 → 6 (nạp lại corpus) → 7. Task 3 phải chạy trên corpus CHƯA sửa, nếu không mất mốc so sánh.

---

### Task 1: Thước đo độ phủ

**Files:**
- Create: `backend/evals/aggregate_score.py`
- Create: `backend/tests/evals/test_aggregate_score.py`

**Interfaces:**
- Consumes: không gì (module thuần).
- Produces:
  - `aggregate_score.SEP: str = " › "`
  - `aggregate_score.doc_of(chunk) -> str`
  - `aggregate_score.top_section_of(chunk) -> str | None`
  - `aggregate_score.score_one(chunks, expected_docs: frozenset[str], target_doc: str | None, expected_sections: frozenset[str]) -> dict` — trả `{"doc_coverage": float, "section_coverage": float | None, "docs_hit": list[str], "sections_hit": list[str]}`

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/evals/test_aggregate_score.py`:

```python
# backend/tests/evals/test_aggregate_score.py
"""Thước độ phủ — thuần, không chạm DB.

Vì sao KHÔNG dùng lại retrieval_score: bộ đó chấm "≥1 nhãn đúng lọt top-k".
Với câu "tóm tắt Luật Doanh nghiệp" thì lọt 1 chunk đúng tài liệu là hiển
nhiên và vô nghĩa — cái thiếu là ĐỘ PHỦ (spec 2026-09-08 mục 7).
"""
from dataclasses import dataclass

from evals.aggregate_score import doc_of, score_one, top_section_of


@dataclass
class ChunkGia:
    source_file: str
    section_path: str | None
    sheet: str | None = None


def test_doc_of_lay_basename_khong_lay_duong_dan():
    c = ChunkGia("D:/Youdoo/backend/src/rag/seed/law/luat-doanhnghiep.pdf", "Chương I")
    assert doc_of(c) == "luat-doanhnghiep.pdf"


def test_doc_of_chiu_duoc_dau_gach_nguoc_windows():
    c = ChunkGia(r"src\rag\seed\policy.docx", "Chính sách hoàn hàng › Mục 1")
    assert doc_of(c) == "policy.docx"


def test_top_section_lay_dung_nut_cap_1():
    c = ChunkGia("a.pdf", "Chương II › CĂN CỨ TÍNH THUẾ › Điều 9. Thuế suất")
    assert top_section_of(c) == "Chương II"


def test_top_section_rong_tra_None_khong_tra_chuoi_rong():
    # 8 chunk trong corpus có section_path rỗng (spec mục 9). Chúng phải
    # KHÔNG được đếm là một mục, nếu không mẫu số bị thổi lên.
    assert top_section_of(ChunkGia("a.pdf", "")) is None
    assert top_section_of(ChunkGia("a.pdf", None)) is None


def test_doc_coverage_dem_ty_le_tai_lieu_mong_doi_bi_cham():
    chunks = [ChunkGia("policy.docx", "x"), ChunkGia("sla.docx", "y")]
    got = score_one(chunks, frozenset({"policy.docx", "sla.docx", "sop.docx"}),
                    None, frozenset())
    assert got["doc_coverage"] == 2 / 3
    assert got["docs_hit"] == ["policy.docx", "sla.docx"]


def test_doc_coverage_bo_qua_tai_lieu_ngoai_danh_sach_mong_doi():
    # Trúng thêm tài liệu lạc đề KHÔNG được làm điểm tăng.
    chunks = [ChunkGia("policy.docx", "x"), ChunkGia("boluat-laodong.pdf", "y")]
    got = score_one(chunks, frozenset({"policy.docx", "sla.docx"}), None, frozenset())
    assert got["doc_coverage"] == 1 / 2


def test_section_coverage_chi_dem_trong_tai_lieu_dich():
    # Chương I của tài liệu KHÁC không được tính cho tài liệu đích.
    chunks = [ChunkGia("luat-doanhnghiep.pdf", "Chương I › A › B"),
              ChunkGia("boluat-laodong.pdf", "Chương V › C")]
    got = score_one(chunks, frozenset({"luat-doanhnghiep.pdf"}),
                    "luat-doanhnghiep.pdf",
                    frozenset({"Chương I", "Chương V", "Chương X"}))
    assert got["section_coverage"] == 1 / 3
    assert got["sections_hit"] == ["Chương I"]


def test_section_coverage_la_None_khi_ca_khong_co_tai_lieu_dich():
    got = score_one([ChunkGia("policy.docx", "x")],
                    frozenset({"policy.docx"}), None, frozenset())
    assert got["section_coverage"] is None


def test_khong_chia_cho_khong_khi_khong_co_nhan():
    got = score_one([], frozenset(), None, frozenset())
    assert got["doc_coverage"] == 0.0
    assert got["section_coverage"] is None
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/evals/test_aggregate_score.py -m "not integration and not live" -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.aggregate_score'`

- [ ] **Step 3: Viết bản cài đặt tối thiểu**

Tạo `backend/evals/aggregate_score.py`:

```python
# backend/evals/aggregate_score.py
"""Chấm điểm câu hỏi TỔNG HỢP — THUẦN, không chạm DB/Ollama/LLM.

Tách khỏi run_eval.py cùng lý do retrieval_score: toàn bộ logic chấm chạy
được ở chế độ pytest mặc định, không cần dựng hạ tầng.

VÌ SAO KHÔNG DÙNG LẠI retrieval_score: bộ đó chấm "≥1 nhãn đúng lọt top-k".
Với câu "tóm tắt Luật Doanh nghiệp", lọt được 1 chunk đúng tài liệu là hiển
nhiên và vô nghĩa — cái thiếu là ĐỘ PHỦ. Đo được 2026-09-08: câu đó lấy 6
chunk, cả 6 nằm trong Chương I của 10 chương, và `passes_floor` vẫn CHO QUA
(spec 2026-09-08 mục 1).

Nhãn neo theo basename tệp và nút CẤP 1, cùng quy ước với
retrieval_score.label_of() — chunk_id là bigserial, re-index đổi sạch.
"""
import os

# Phải trùng chunking.chunk_text_blocks.
SEP = " › "


def doc_of(chunk) -> str:
    """Quy một chunk về basename tệp.

    source_file trong DB là đường dẫn tuyệt đối phụ thuộc máy đã ingest, còn
    nhãn viết tay thì không mang đường dẫn đó. Quy đổi ở ĐÚNG một chỗ này.
    """
    return os.path.basename(str(chunk.source_file).replace("\\", "/"))


def top_section_of(chunk) -> str | None:
    """Nút CẤP 1 của chunk, None khi chunk không có breadcrumb.

    None chứ KHÔNG phải chuỗi rỗng: 8 chunk trong corpus có section_path
    rỗng, và nếu chúng được đếm như một mục thì mẫu số của section_coverage
    bị thổi lên bởi một mục không tồn tại.
    """
    path = getattr(chunk, "section_path", None)
    if not path:
        return None
    head = path.split(SEP)[0].strip()
    return head or None


def score_one(chunks, expected_docs: frozenset[str],
              target_doc: str | None,
              expected_sections: frozenset[str]) -> dict:
    """Độ phủ của MỘT ca.

    doc_coverage — phần tài liệu MONG ĐỢI bị chạm. Tài liệu ngoài danh sách
    không làm điểm tăng: câu "liệt kê tất cả chính sách công ty" mà trúng
    thêm bộ luật thì đó là lạc đề, không phải công.

    section_coverage — phần nút cấp 1 của TÀI LIỆU ĐÍCH bị chạm; None khi ca
    không nêu tài liệu đích (câu liệt kê/đếm trọn corpus không có khái niệm
    này). Chỉ đếm mục nằm TRONG tài liệu đích: "Chương I" của một luật khác
    không được tính.

    Mẫu số lấy từ FIXTURE chứ không từ corpus, có chủ đích: cây section_path
    của PDF luật còn lẫn nút rác cấp 1 ("LUẬT", "QUỐC HỘI CỘNG HÒA…" — đo
    được ở luat-doanhnghiep và boluat-laodong). Lấy mẫu số từ corpus là để
    rác quyết định thước đo.
    """
    docs_hit = sorted({doc_of(c) for c in chunks} & expected_docs)
    doc_cov = len(docs_hit) / len(expected_docs) if expected_docs else 0.0

    section_cov = None
    sections_hit: list[str] = []
    if target_doc and expected_sections:
        seen = {top_section_of(c) for c in chunks if doc_of(c) == target_doc}
        sections_hit = sorted(s for s in seen if s is not None
                              and s in expected_sections)
        section_cov = len(sections_hit) / len(expected_sections)

    return {"doc_coverage": doc_cov, "section_coverage": section_cov,
            "docs_hit": docs_hit, "sections_hit": sections_hit}
```

- [ ] **Step 4: Chạy để xác nhận XANH**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/evals/test_aggregate_score.py -m "not integration and not live" -q`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/evals/aggregate_score.py backend/tests/evals/test_aggregate_score.py
git commit -m "feat(eval): thuoc do phu cho cau hoi tong hop

Thuoc cu (>=1 nhan lot top-k) sai ban chat voi cau tom tat: lot 1 chunk
dung tai lieu la hien nhien. Do 2026-09-08: 'tom tat luat doanh nghiep'
lay 6 chunk, ca 6 trong Chuong I cua 10 chuong, passes_floor VAN CHO QUA.

Mau so lay tu fixture chu khong tu corpus: cay section_path con lan nut
rac cap 1 (LUAT, QUOC HOI CONG HOA...).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Golden set câu hỏi tổng hợp

**Files:**
- Create: `backend/evals/aggregate_cases.py`
- Create: `backend/tests/evals/test_aggregate_cases.py`

**Interfaces:**
- Consumes: `aggregate_score.doc_of`, `aggregate_score.top_section_of`, `src.rag.db`.
- Produces: `aggregate_cases.AggregateCase` (NamedTuple: `question`, `kind`, `expected_docs`, `target_doc`, `expected_sections`), `aggregate_cases.AGGREGATE_CASES: list[AggregateCase]`, `aggregate_cases.VALID_KINDS: frozenset[str]`.

**Ghi chú cho người thực thi:** mọi nhãn dưới đây ĐÃ đối chiếu `rag_chunks` ngày 2026-09-08 (10 chương của `luat-doanhnghiep.pdf`, 17 chương của `boluat-laodong.pdf`, 7 tệp `.docx` nghiệp vụ). Chép nguyên văn, đừng sửa theo trí nhớ — test hợp đồng ở Step 3 sẽ đỏ nếu nhãn trôi.

- [ ] **Step 1: Viết golden set**

Tạo `backend/evals/aggregate_cases.py`:

```python
# backend/evals/aggregate_cases.py
"""Golden set câu hỏi TỔNG HỢP — spec 2026-09-08 mục 7.

CẤU TRÚC: AggregateCase(question, kind, expected_docs, target_doc, expected_sections)

  kind:
    summary  — tóm tắt MỘT tài liệu; chấm bằng section_coverage
    overview — tổng quan một chủ đề trải nhiều tài liệu; chấm bằng doc_coverage
    list     — liệt kê trọn một nhóm tài liệu; chấm bằng doc_coverage
    count    — đếm trên corpus; chấm bằng doc_coverage (phải chạm ĐỦ để đếm đúng)

  (Giá trị tiếng Anh cho khớp `difficulty` của retrieval_cases: easy/hard/trap.)

  expected_docs      — basename tệp PHẢI được chạm. Mẫu số của doc_coverage.
  target_doc         — tài liệu đích của câu tóm tắt; None với ba kind kia.
  expected_sections  — nút CẤP 1 của target_doc. Mẫu số của section_coverage.

VÌ SAO MẪU SỐ VIẾT TAY: cây section_path của PDF luật còn lẫn nút rác cấp 1
("LUẬT", "QUỐC HỘI CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM" — đo được ở cả
luat-doanhnghiep và boluat-laodong). Lấy mẫu số từ corpus là để lỗi ingest
quyết định thước đo. Nút rác sẽ biến mất dần; fixture thì không được trôi
theo.

MỐC NỀN DỰ KIẾN RẤT THẤP — đó là điểm. Không sửa được thứ chưa đo được.
"""
from typing import NamedTuple


class AggregateCase(NamedTuple):
    question: str
    kind: str
    expected_docs: frozenset
    target_doc: str | None
    expected_sections: frozenset


VALID_KINDS = frozenset({"summary", "overview", "list", "count"})

_POLICY = "policy.docx"
_DISCOUNT = "discount_policy.docx"
_PAYMENT = "payment_policy.docx"
_SLA = "sla.docx"
_SOP = "sop.docx"
_SALES = "sales_process.docx"
_OUTBOUND = "warehouse_outbound.docx"

_DOANHNGHIEP = "luat-doanhnghiep.pdf"
_LAODONG = "boluat-laodong.pdf"

# 7 tệp .docx nghiệp vụ. bang_gia.xlsx CỐ Ý không nằm đây: nó là bảng giá,
# không phải chính sách/quy trình, và section_path của chunk xlsx luôn None.
_NGHIEP_VU = frozenset({_POLICY, _DISCOUNT, _PAYMENT, _SLA, _SOP, _SALES,
                        _OUTBOUND})

# Đối chiếu rag_chunks 2026-09-08: luat-doanhnghiep.pdf có đúng 10 chương.
_CHUONG_DOANHNGHIEP = frozenset({
    "Chương I", "Chương II", "Chương III", "Chương IV", "Chương V",
    "Chương VI", "Chương VII", "Chương VIII", "Chương IX", "Chương X"})

# Đối chiếu rag_chunks 2026-09-08: boluat-laodong.pdf có đúng 17 chương.
_CHUONG_LAODONG = frozenset({
    "Chương I", "Chương II", "Chương III", "Chương IV", "Chương V",
    "Chương VI", "Chương VII", "Chương VIII", "Chương IX", "Chương X",
    "Chương XI", "Chương XII", "Chương XIII", "Chương XIV", "Chương XV",
    "Chương XVI", "Chương XVII"})

AGGREGATE_CASES: list[AggregateCase] = [

    # ══ TÓM TẮT MỘT TÀI LIỆU ═════════════════════════════════════════════
    # Đo 2026-09-08: câu đầu tiên lấy 6 chunk, CẢ 6 trong Chương I.
    AggregateCase("tóm tắt luật doanh nghiệp", "summary",
                  frozenset({_DOANHNGHIEP}), _DOANHNGHIEP, _CHUONG_DOANHNGHIEP),
    AggregateCase("luật doanh nghiệp gồm những nội dung chính nào?", "summary",
                  frozenset({_DOANHNGHIEP}), _DOANHNGHIEP, _CHUONG_DOANHNGHIEP),
    AggregateCase("tóm tắt bộ luật lao động", "summary",
                  frozenset({_LAODONG}), _LAODONG, _CHUONG_LAODONG),
    AggregateCase("cho tôi cái nhìn tổng quan về bộ luật lao động", "summary",
                  frozenset({_LAODONG}), _LAODONG, _CHUONG_LAODONG),

    # ══ TỔNG QUAN TRẢI NHIỀU TÀI LIỆU ════════════════════════════════════
    # Đo 2026-09-08: câu đầu lấy 3/6 chunk từ PDF LUẬT, 1 chunk rác OCR.
    AggregateCase("tổng quan các chính sách bán hàng của công ty", "overview",
                  frozenset({_SALES, _DISCOUNT, _PAYMENT}), None, frozenset()),
    AggregateCase("công ty có những quy định gì về kho?", "overview",
                  frozenset({_SOP, _OUTBOUND}), None, frozenset()),
    AggregateCase("tổng quan quy trình từ lúc nhận đơn tới lúc giao hàng",
                  "overview", frozenset({_SALES, _OUTBOUND}), None, frozenset()),

    # ══ LIỆT KÊ TRỌN NHÓM ════════════════════════════════════════════════
    # Đo 2026-09-08: câu đầu lấy 4/6 chunk từ PDF LUẬT + 2 chunk rác OCR
    # ("49 GB", "_—" P SN"). doc_coverage nền gần như bằng 0.
    AggregateCase("liệt kê tất cả các chính sách của công ty", "list",
                  frozenset({_POLICY, _DISCOUNT, _PAYMENT}), None, frozenset()),
    AggregateCase("công ty có những tài liệu nội bộ nào?", "list",
                  _NGHIEP_VU, None, frozenset()),
    AggregateCase("kể tên các quy trình nội bộ đang áp dụng", "list",
                  frozenset({_SOP, _OUTBOUND, _SALES}), None, frozenset()),

    # ══ ĐẾM TRÊN CORPUS ══════════════════════════════════════════════════
    # Trả lời đúng đòi chạm ĐỦ tài liệu trong nhóm — thiếu một tệp là đếm sai.
    AggregateCase("có bao nhiêu quy trình kho trong tài liệu nội bộ?", "count",
                  frozenset({_SOP, _OUTBOUND}), None, frozenset()),
    AggregateCase("công ty có mấy chính sách liên quan tới khách hàng?", "count",
                  frozenset({_DISCOUNT, _PAYMENT, _POLICY}), None, frozenset()),
]
```

- [ ] **Step 2: Viết test hợp đồng**

Tạo `backend/tests/evals/test_aggregate_cases.py`:

```python
# backend/tests/evals/test_aggregate_cases.py
"""Hợp đồng golden set ↔ corpus thật.

Cùng lớp lỗi GATHER_CASES từng dính: fixture trôi khỏi dữ liệu thật mà
không ai biết, và độ phủ tụt trông y hệt "model kém đi". Lần này viết cùng lúc.
"""
import pytest

from evals.aggregate_cases import AGGREGATE_CASES, VALID_KINDS
from src.rag import db as _db


def test_moi_ca_co_it_nhat_mot_tai_lieu_mong_doi():
    for case in AGGREGATE_CASES:
        assert case.expected_docs, f"ca không có tài liệu mong đợi: {case.question!r}"


def test_kind_chi_nhan_gia_tri_hop_le():
    for case in AGGREGATE_CASES:
        assert case.kind in VALID_KINDS, f"kind lạ {case.kind!r} ở {case.question!r}"


def test_ca_tom_tat_phai_co_tai_lieu_dich_va_muc_mong_doi():
    # Thiếu một trong hai thì section_coverage lặng lẽ thành None và ca đó
    # không đo gì cả — đúng lớp lỗi "test không đo gì" đã tái diễn 3 lần.
    for case in AGGREGATE_CASES:
        if case.kind == "summary":
            assert case.target_doc, f"ca summary thiếu target_doc: {case.question!r}"
            assert case.expected_sections, \
                f"ca summary thiếu expected_sections: {case.question!r}"


def test_ca_khong_phai_tom_tat_thi_khong_co_tai_lieu_dich():
    for case in AGGREGATE_CASES:
        if case.kind != "summary":
            assert case.target_doc is None, \
                f"ca {case.kind} không được có target_doc: {case.question!r}"


def test_tai_lieu_dich_phai_nam_trong_danh_sach_mong_doi():
    for case in AGGREGATE_CASES:
        if case.target_doc:
            assert case.target_doc in case.expected_docs, \
                f"target_doc ngoài expected_docs: {case.question!r}"


def test_co_du_bon_kind():
    seen = {c.kind for c in AGGREGATE_CASES}
    assert seen == VALID_KINDS, f"thiếu kind: {VALID_KINDS - seen}"


def test_khong_co_cau_hoi_trung_lap():
    questions = [c.question for c in AGGREGATE_CASES]
    assert len(questions) == len(set(questions))


@pytest.mark.integration
def test_moi_tai_lieu_mong_doi_ton_tai_that():
    """Basename không khớp tệp nào trong rag_chunks → ĐỎ, kèm tên tệp."""
    conn = _db.connect()
    try:
        rows = conn.execute("SELECT DISTINCT source_file FROM rag_chunks").fetchall()
    finally:
        conn.close()
    import os
    have = {os.path.basename(str(r[0]).replace("\\", "/")) for r in rows}
    want = {d for c in AGGREGATE_CASES for d in c.expected_docs}
    assert want <= have, f"tài liệu không có trong corpus: {sorted(want - have)}"


@pytest.mark.integration
def test_moi_muc_mong_doi_ton_tai_that():
    """Nút cấp 1 viết tay phải khớp corpus, nếu không mẫu số sai lặng lẽ."""
    import os
    from evals.aggregate_score import SEP
    conn = _db.connect()
    try:
        rows = conn.execute(
            "SELECT source_file, section_path FROM rag_chunks "
            "WHERE section_path IS NOT NULL AND section_path <> ''").fetchall()
    finally:
        conn.close()
    have: dict[str, set[str]] = {}
    for source_file, section_path in rows:
        base = os.path.basename(str(source_file).replace("\\", "/"))
        have.setdefault(base, set()).add(section_path.split(SEP)[0].strip())
    for case in AGGREGATE_CASES:
        if not case.target_doc:
            continue
        missing = case.expected_sections - have.get(case.target_doc, set())
        assert not missing, \
            f"{case.target_doc}: mục không có thật {sorted(missing)}"
```

- [ ] **Step 3: Chạy phần không cần DB**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/evals/test_aggregate_cases.py -m "not integration and not live" -q`
Expected: `7 passed, 2 deselected`

- [ ] **Step 4: Chạy test hợp đồng với DB thật**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/evals/test_aggregate_cases.py -m "integration" -q`
Expected: `2 passed, 7 deselected`

Nếu ĐỎ: nhãn đã trôi khỏi corpus. **Sửa nhãn theo corpus, không sửa test.** Đối chiếu bằng:
```bash
docker exec youdoo-postgres psql -U admin -d ai_assistant -c "SELECT DISTINCT split_part(section_path,' › ',1) FROM rag_chunks WHERE doc_id LIKE '%luat-doanhnghiep%' AND section_path<>'' ORDER BY 1;"
```

- [ ] **Step 5: Commit**

```bash
git add backend/evals/aggregate_cases.py backend/tests/evals/test_aggregate_cases.py
git commit -m "feat(eval): golden set 12 ca cau hoi tong hop

Bo eval hien tai MU voi lop nay: 64 ca retrieval + 28 ca synthesis_live
deu la tra cuu diem, khong mot ca nao chua 'tom tat' hay 'tong quan'.

Nhan doi chieu rag_chunks 2026-09-08, test hop dong (integration) gac lai.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Nối vào run_eval và lấy MỐC NỀN

**Files:**
- Modify: `backend/evals/run_eval.py` (thêm `eval_aggregate` cạnh `eval_retrieval` ~dòng 1072; đăng ký ở `--set` ~dòng 1371 và bảng dispatch ~dòng 1415)

**Interfaces:**
- Consumes: `aggregate_cases.AGGREGATE_CASES`, `aggregate_score.score_one`, `_retrieve`, `_TOP_K`, `run_resilient`, `_timed`, `_percentiles` — tất cả đã có sẵn trong `run_eval.py`.
- Produces: `run_eval.eval_aggregate(pace=0.0, checkpoint_path=None) -> dict`.

**QUAN TRỌNG:** task này phải chạy TRƯỚC Task 4. Mốc nền phải đo trên corpus CHƯA sửa `doc_title`, nếu không mất điểm so sánh.

- [ ] **Step 1: Thêm hàm eval**

Chèn vào `backend/evals/run_eval.py` ngay sau `eval_retrieval` (sau dòng ~1150):

```python
async def eval_aggregate(pace: float = 0.0, checkpoint_path=None):
    """Đo ĐỘ PHỦ trên câu hỏi tổng hợp — KHÔNG gọi LLM lần nào.

    k=_TOP_K (KHÁC eval_retrieval, vốn dùng _TOP_N): bộ này đo đúng cái
    người dùng thật nhận được. Câu hỏi ở đây hỏng vì TRẦN 6 chunk, nên đo
    trên pool 20 sẽ giấu mất chính lỗi đang đi đo.
    """
    lat: list[float] = []
    per_case: list[dict] = []

    async def call(case):
        question, kind, expected_docs, target_doc, expected_sections = case
        result, ms = await _timed(
            asyncio.to_thread(_retrieve, question, _TOP_K))
        lat.append(ms)
        score = score_aggregate(result.chunks, frozenset(expected_docs),
                                target_doc, frozenset(expected_sections))
        per_case.append({"question": question, "kind": kind, **score})
        if score["doc_coverage"] >= 1.0:
            return None
        return {"question": question, "kind": kind,
                "doc_coverage": round(score["doc_coverage"], 4),
                "section_coverage": (None if score["section_coverage"] is None
                                     else round(score["section_coverage"], 4)),
                "docs_hit": score["docs_hit"],
                "expected_docs": sorted(expected_docs)}

    fails, errors = await run_resilient(
        [(c.question, c.kind, sorted(c.expected_docs), c.target_doc,
          sorted(c.expected_sections)) for c in AGGREGATE_CASES],
        call, pace=pace, checkpoint_path=checkpoint_path)

    n = len(AGGREGATE_CASES)

    def _avg(key: str, rows) -> float:
        vals = [r[key] for r in rows if r[key] is not None]
        return sum(vals) / len(vals) if vals else 0.0

    by_kind = {}
    for k in ("summary", "overview", "list", "count"):
        rows = [r for r in per_case if r["kind"] == k]
        by_kind[k] = {"n": len(rows),
                      "doc_coverage": round(_avg("doc_coverage", rows), 4),
                      "section_coverage": round(_avg("section_coverage", rows), 4)}

    p50, p95 = _percentiles(lat)
    return {"set": "aggregate", "n": n,
            "doc_coverage": round(_avg("doc_coverage", per_case), 4),
            "section_coverage": round(_avg("section_coverage", per_case), 4),
            "by_kind": by_kind,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}
```

- [ ] **Step 2: Thêm import**

Cạnh dòng 27-28 (`from evals.retrieval_cases import ...`):

```python
from evals.aggregate_cases import AGGREGATE_CASES
from evals.aggregate_score import score_one as score_aggregate
```

- [ ] **Step 3: Đăng ký vào CLI**

Trong `ap.add_argument("--set", choices=[...])` (~dòng 1371) thêm `"aggregate"` vào danh sách. Trong bảng dispatch (~dòng 1415, cạnh `"retrieval": eval_retrieval`) thêm:

```python
               "aggregate": eval_aggregate,
```

Trong nhánh `if args.set in ("retrieval", "multiturn"):` (~dòng 1434) — **đọc kỹ chú thích tại chỗ** rồi thêm `"aggregate"` vào bộ này nếu nó cũng thuộc nhóm không cần `chain_for()`. Bộ `aggregate` KHÔNG gọi LLM nên nó thuộc nhóm đó.

Ở dòng chọn `metric` (~dòng 1475) thêm nhánh:

```python
               else "doc_coverage" if args.set == "aggregate"
```

- [ ] **Step 4: Chạy suite để chắc không gãy gì**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: `2490 passed, 1 skipped, 85 deselected` (2474 nền + 9 của Task 1 + 7 của Task 2; task này chưa thêm test đơn vị nào)

- [ ] **Step 5: LẤY MỐC NỀN trên corpus chưa sửa**

Run:
```bash
cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m evals.run_eval --set aggregate --model bge-m3 --save-baseline
```
Expected: sinh `backend/evals/baseline-bge-m3-aggregate.json`.

**Dự đoán ghi trước để đối chiếu** (nếu lệch nhiều thì dừng và điều tra, đừng chấp nhận im lặng): `section_coverage` của `summary` khoảng 0,1 (1/10 chương với luat-doanhnghiep); `doc_coverage` của `list` gần 0 với câu "liệt kê tất cả các chính sách".

- [ ] **Step 6: Commit kèm SỐ ĐO trong commit message**

```bash
git add backend/evals/run_eval.py backend/evals/baseline-bge-m3-aggregate.json
git commit -m "feat(eval): noi bo aggregate vao run_eval + moc nen

Moc nen do tren corpus CHUA sua doc_title, co chu dich — de sau nay quy
duoc thay doi cho tung buoc.

<DAN SO DO THAT TU baseline-bge-m3-aggregate.json VAO DAY>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: `doc_title` bỏ qua quốc hiệu

**Files:**
- Modify: `backend/src/rag/chunking.py` (hàm `chunk_text_blocks`, dòng 82-84)
- Create: `backend/tests/rag/test_document_title.py`

**Interfaces:**
- Consumes: `blocks: list[dict]` với khoá `text`, `heading_level` — hợp đồng sẵn có của `chunk_text_blocks`.
- Produces: `chunking.BOILERPLATE_HEADINGS: frozenset[str]`, `chunking.BARE_DOC_TYPES: frozenset[str]`, `chunking.document_title(blocks: list[dict], source_file: str) -> str`.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/rag/test_document_title.py`:

```python
# backend/tests/rag/test_document_title.py
"""Suy tên tài liệu — spec 2026-09-08 mục 6.

Lỗi đang sửa, đo 2026-09-08: 8/9 PDF luật có doc_title = "QUỐC HỘI", bộ thứ
chín có "QUỐC HỘI CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM". Heading ĐẦU TIÊN của
một PDF luật là dòng quốc hiệu, không phải tên luật.
"""
from src.rag.chunking import document_title


def _b(text: str, level: int | None):
    return {"text": text, "heading_level": level, "page": 1}


def test_bo_qua_quoc_hieu_va_noi_tu_loai_van_ban_voi_dong_body():
    # Tái lập ĐÚNG đầu luat-doanhnghiep.pdf: tên thật bị cắt đôi, "LUẬT"
    # thành heading còn "DOANH NGHIỆP" rơi xuống body.
    blocks = [
        _b("QUỐC HỘI CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", 1),
        _b("Độc lập - Tự do - Hạnh phúc", None),
        _b("LUẬT", 1),
        _b("DOANH NGHIỆP Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam;", None),
        _b("Chương I", 1),
    ]
    assert document_title(blocks, "luat-doanhnghiep.pdf") == "LUẬT DOANH NGHIỆP"


def test_bo_luat_cung_duoc_noi():
    blocks = [
        _b("QUỐC HỘI", 1),
        _b("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", 1),
        _b("BỘ LUẬT", 1),
        _b("LAO ĐỘNG Căn cứ Hiến pháp", None),
    ]
    assert document_title(blocks, "boluat-laodong.pdf") == "BỘ LUẬT LAO ĐỘNG"


def test_tieu_de_that_thi_giu_nguyen_khong_noi_them():
    blocks = [_b("Chính sách hoàn hàng", 1), _b("Mục 1 — Điều kiện", 2)]
    assert document_title(blocks, "policy.docx") == "Chính sách hoàn hàng"


def test_khong_co_heading_nao_thi_lui_ve_ten_tep():
    blocks = [_b("một đoạn văn xuôi", None)]
    assert document_title(blocks, "D:/x/y/bao_cao.pdf") == "bao_cao.pdf"


def test_moi_heading_deu_la_quoc_hieu_thi_lui_ve_ten_tep():
    # KHÔNG được trả chuỗi rỗng: doc_title là cột NOT NULL và là nhãn hiển
    # thị cho trích dẫn.
    blocks = [_b("QUỐC HỘI", 1), _b("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", 1)]
    assert document_title(blocks, "la.pdf") == "la.pdf"


def test_tu_loai_van_ban_tran_ma_khong_co_body_thi_khong_noi_rong():
    blocks = [_b("QUỐC HỘI", 1), _b("NGHỊ ĐỊNH", 1)]
    assert document_title(blocks, "nd.pdf") == "NGHỊ ĐỊNH"


def test_dong_body_dai_bi_cat_khong_nuot_ca_can_cu():
    # "DOANH NGHIỆP Căn cứ Hiến pháp ..." — chỉ lấy phần TÊN, không lấy cả
    # đoạn căn cứ. Cắt ở chữ "Căn cứ".
    blocks = [
        _b("LUẬT", 1),
        _b("ĐẦU TƯ Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam;", None),
    ]
    assert document_title(blocks, "luat-dautu.pdf") == "LUẬT ĐẦU TƯ"
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/rag/test_document_title.py -m "not integration and not live" -q`
Expected: FAIL — `ImportError: cannot import name 'document_title'`

- [ ] **Step 3: Cài đặt**

Thêm vào `backend/src/rag/chunking.py`, ngay TRƯỚC `chunk_text_blocks`:

```python
# Heading hành chính KHÔNG BAO GIỜ là tên tài liệu. Đo 2026-09-08: heading
# đầu tiên của cả 9 PDF luật là dòng quốc hiệu, nên `doc_title` cũ (lấy
# heading đầu tiên) cho 8/9 bộ luật cùng giá trị "QUỐC HỘI" — hai tài liệu
# khác nhau không phân biệt được, và mọi phép lọc/đếm theo tên đều sai IM
# LẶNG. So khớp sau khi bỏ dấu câu và gộp khoảng trắng, vì PDF hai cột hay
# dính hai dòng quốc hiệu thành một.
BOILERPLATE_HEADINGS = frozenset({
    "quốc hội", "chính phủ", "bộ tài chính",
    "cộng hòa xã hội chủ nghĩa việt nam",
    "quốc hội cộng hòa xã hội chủ nghĩa việt nam",
    "độc lập tự do hạnh phúc",
})

# Từ loại văn bản đứng TRẦN một mình. `parse_pdf` tách "LUẬT DOANH NGHIỆP"
# thành heading "LUẬT" + body "DOANH NGHIỆP ..." (đo được ở
# luat-doanhnghiep.pdf), nên riêng nhóm này phải nối dòng body kế tiếp.
BARE_DOC_TYPES = frozenset({"luật", "bộ luật", "nghị định", "thông tư",
                            "quyết định", "nghị quyết"})

# Đoạn "Căn cứ ..." luôn theo ngay sau tên văn bản trong văn bản quy phạm —
# nó là chỗ cắt tự nhiên, không phải một hằng số rút từ không khí.
_TITLE_TAIL_RE = re.compile(r"\s+Căn\s+cứ\b.*$", re.DOTALL)


def _normalize_heading(text: str) -> str:
    """Bỏ dấu câu và gộp khoảng trắng để so với BOILERPLATE_HEADINGS."""
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def document_title(blocks: list[dict], source_file: str) -> str:
    """Nhãn hiển thị của tài liệu — heading đầu tiên KHÔNG PHẢI quốc hiệu.

    Lùi về TÊN TỆP (không phải đường dẫn đầy đủ, không phải rỗng) khi mọi
    heading đều là quốc hiệu hoặc không có heading nào: `doc_title` là cột
    NOT NULL và là nhãn cho hiển thị/trích dẫn, nên giữ một nhãn đọc được
    thì có ích.

    KHÔNG đi vào `index_text()` lẫn `ts_vector` — đổi hàm này không đụng tới
    vector của bất kỳ chunk nào.
    """
    headings = [b for b in blocks if b["heading_level"]]
    for i, b in enumerate(headings):
        text = b["text"].strip()
        if _normalize_heading(text) in BOILERPLATE_HEADINGS:
            continue
        if _normalize_heading(text) in BARE_DOC_TYPES:
            # Phần tên nằm ở dòng body ngay sau heading trần này.
            pos = blocks.index(b)
            tail = next((x["text"].strip() for x in blocks[pos + 1:]
                         if not x["heading_level"] and x["text"].strip()), "")
            tail = _TITLE_TAIL_RE.sub("", tail).strip()
            return f"{text} {tail}".strip() if tail else text
        return text
    return os.path.basename(source_file)
```

Đảm bảo `import re` có ở đầu `chunking.py` (đã có — nó dùng `_SENT_RE`).

- [ ] **Step 4: Nối vào `chunk_text_blocks`**

Thay dòng 82-84 của `chunk_text_blocks`:

```python
    # `doc_title` lùi về TÊN TỆP, không phải đường dẫn đầy đủ và cũng không
    # phải rỗng: nó là cột metadata cho hiển thị/trích dẫn (`schema.sql`,
    # `retrieve.py` SELECT ra), KHÔNG đi vào `index_text()` lẫn `ts_vector`.
    # Giữ một nhãn đọc được thì có ích; giữ nguyên đường dẫn thì không.
    doc_title = document_title(blocks, source_file)
```

- [ ] **Step 5: Chạy test mới + toàn suite**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/rag/test_document_title.py -m "not integration and not live" -q`
Expected: `7 passed`

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: `2497 passed, 1 skipped, 85 deselected` — **nếu có test CŨ chuyển sang đỏ, dừng lại**: nghĩa là có test đang ghim `doc_title` bằng giá trị quốc hiệu. Đọc test đó, quyết định xem nó ghim hành vi ĐÚNG hay ghim chính lỗi này, rồi báo lại trước khi sửa.

- [ ] **Step 6: Commit**

```bash
git add backend/src/rag/chunking.py backend/tests/rag/test_document_title.py
git commit -m "fix(rag): doc_title bo qua dong quoc hieu

Do 2026-09-08: 8/9 PDF luat co doc_title='QUOC HOI' vi heading dau tien
cua van ban quy pham la dong quoc hieu. Hai tai lieu khac nhau khong phan
biet duoc => moi phep loc/dem theo ten deu sai IM LANG.

Rieng tu loai van ban tran (LUAT, BO LUAT...) phai noi dong body ke tiep:
parse_pdf tach 'LUAT DOANH NGHIEP' thanh heading 'LUAT' + body 'DOANH NGHIEP'.

doc_title KHONG di vao index_text/ts_vector nen vector khong doi mot bit.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Cổng trùng tên tài liệu

**Files:**
- Modify: `backend/src/rag/ingest.py`
- Create: `backend/tests/rag/test_cong_trung_ten.py`

**Interfaces:**
- Consumes: `ingest_report.IngestReport`, `ingest_report.Warning(path, where, reason)` — đã có sẵn; `ingest_path(path, conn=None) -> IngestReport` (dòng 217).
- Produces: `ingest._duplicate_title_warnings(conn) -> list[Warning]`.

**Vì sao hỏi DB chứ không gom từ `IngestReport`:** `IngestReport` mang SỐ ĐẾM (`ingested: int`), không mang danh sách `doc_title` — luồn tên qua đó là đổi hợp đồng của một dataclass đang được 4 chỗ dùng. Hỏi `rag_chunks` ở cuối `ingest_path` vừa rẻ hơn vừa **mạnh hơn**: nó bắt được cả va chạm với tài liệu đã nạp từ lượt TRƯỚC, mà đó chính là hình dạng thật của lỗi hôm nay (9 PDF luật nạp cùng lượt hay khác lượt đều trùng như nhau).

`Warning` CỐ Ý không làm `ok` thành False (hợp đồng ba trạng thái TỆP ở `ingest_report.py`) — giữ nguyên tính chất đó.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/rag/test_cong_trung_ten.py`:

```python
# backend/tests/rag/test_cong_trung_ten.py
"""Cổng trùng tên — spec 2026-09-08 mục 6.

Heuristic suy tên tài liệu nào rồi cũng sai ở một tài liệu nào đó. Thứ
KHÔNG được phép lặp lại là sai IM LẶNG: lỗi doc_title='QUỐC HỘI' ở 8/9 PDF
luật sống nhiều tuần vì không có gì gọi tên nó.
"""
from src.rag.ingest import _duplicate_title_warnings
from src.rag.ingest_report import IngestReport, Warning


class ConnGia:
    """conn giả trả đúng shape mà _duplicate_title_warnings mong đợi."""
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _sql, _params=None):
        return self

    def fetchall(self):
        return self._rows


def test_hai_tai_lieu_cung_ten_thi_phat_canh_bao():
    conn = ConnGia([("QUỐC HỘI", ["a.pdf", "b.pdf"])])
    got = _duplicate_title_warnings(conn)
    assert len(got) == 1
    assert got[0].where == "doc_title"
    assert "QUỐC HỘI" in got[0].reason
    assert "a.pdf" in got[0].path and "b.pdf" in got[0].path


def test_ten_khac_nhau_thi_khong_phat_canh_bao():
    # Truy vấn đã lọc bằng HAVING, nên nhóm một phần tử không bao giờ tới
    # đây — ca này gác chiều ngược: danh sách rỗng vẫn ra danh sách rỗng.
    assert _duplicate_title_warnings(ConnGia([])) == []


def test_reason_neu_du_so_luong_de_doc_duoc_muc_do():
    conn = ConnGia([("QUỐC HỘI", ["a.pdf", "b.pdf", "c.pdf"])])
    got = _duplicate_title_warnings(conn)
    assert "3" in got[0].reason, "cảnh báo phải nói RÕ bao nhiêu tài liệu"


def test_canh_bao_khong_lam_hong_luot_nap():
    # Hợp đồng ba trạng thái TỆP: Warning là mối lo mức trong-tệp, không
    # được biến `ingested` thành `rejected`.
    report = IngestReport(ingested=2, chunks=10)
    report.warnings.append(Warning("a.pdf, b.pdf", "doc_title", "trùng tên"))
    assert report.ok
    assert report.ingested == 2
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/rag/test_cong_trung_ten.py -m "not integration and not live" -q`
Expected: FAIL — `ImportError: cannot import name '_duplicate_title_warnings'`

- [ ] **Step 3: Cài đặt cổng**

Thêm vào `backend/src/rag/ingest.py`, ngay TRƯỚC `ingest_path` (dòng 217):

```python
def _duplicate_title_warnings(conn) -> list[Warning]:
    """Cảnh báo khi hai `doc_id` khác nhau mang cùng `doc_title`.

    Vì sao cần (spec 2026-09-08 mục 6): heuristic suy tên tài liệu nào rồi
    cũng sai ở đâu đó; thứ KHÔNG được phép lặp lại là sai IM LẶNG. Trước
    2026-09-08, 8/9 PDF luật cùng mang tên "QUỐC HỘI" và mọi phép lọc/đếm
    theo tên gộp nhầm chúng mà không ai biết.

    Hỏi TRỌN corpus chứ không riêng lượt nạp này: va chạm với tài liệu đã
    nạp từ lượt trước cũng là va chạm, và đó là hình dạng thật của lỗi.
    """
    rows = conn.execute(
        "SELECT doc_title, array_agg(DISTINCT doc_id) FROM rag_chunks "
        "GROUP BY doc_title HAVING count(DISTINCT doc_id) > 1 "
        "ORDER BY doc_title"
    ).fetchall()
    return [Warning(path=", ".join(sorted(doc_ids)), where="doc_title",
                    reason=(f"{len(doc_ids)} tài liệu khác nhau cùng mang tên "
                            f"{title!r} — phép lọc/đếm theo tên sẽ gộp nhầm "
                            f"chúng"))
            for title, doc_ids in rows]
```

Rồi trong `ingest_path`, thay `return report` (dòng 262) bằng:

```python
        report.warnings.extend(_duplicate_title_warnings(conn))
        return report
```

- [ ] **Step 4: Chạy test + toàn suite**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/rag/test_cong_trung_ten.py -m "not integration and not live" -q`
Expected: `4 passed`

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: `2501 passed, 1 skipped, 85 deselected`

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/ingest.py backend/tests/rag/test_cong_trung_ten.py
git commit -m "feat(rag): cong canh bao khi hai tai lieu trung doc_title

Warning chu khong phai Rejection: hop dong ba trang thai TEP giu nguyen,
tep van duoc nap, nhung cho dang ngo duoc GOI TEN.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Nạp lại corpus và nghiệm thu `doc_title`

**Files:** không sửa mã. Thao tác trên DB thật.

> ⚠️ **BƯỚC PHÁ HUỶ.** Task này XOÁ `rag_documents` (kéo theo `rag_chunks` qua `ON DELETE CASCADE`) rồi nạp lại. **Phải hỏi chủ dự án trước khi chạy Step 2.** Lý do bắt buộc phải xoá: `content_hash` không mang dấu vân tay của parser, nên re-ingest là NO-OP và `doc_title` mới sẽ không bao giờ vào DB (spec mục 9).
>
> Corpus gồm 9 PDF luật + 8 tệp nghiệp vụ trong `backend/src/rag/seed/`, và **một tệp ngoài cây nguồn**: `D:/downloads/SID_..._BaoCaoTaiChinhBanNien_...pdf` (968 chunk). Xác nhận tệp đó còn tồn tại TRƯỚC khi xoá, nếu không nạp lại sẽ mất nó.

- [ ] **Step 1: Chụp trạng thái trước, để đối chiếu**

```bash
docker exec youdoo-postgres psql -U admin -d ai_assistant -c "SELECT doc_title, count(DISTINCT doc_id) n_doc, count(*) n_chunk FROM rag_chunks GROUP BY 1 ORDER BY 2 DESC;" > /tmp/doc_title_truoc.txt
docker exec youdoo-postgres psql -U admin -d ai_assistant -c "SELECT count(*) FROM rag_chunks;"
ls -la "D:/downloads/SID_000000016657191_01VI_BaoCaoTaiChinhBanNien_HopNhat_SoatXet_2026_signed_05092026111802.pdf"
```
Kỳ vọng: 4870 chunk, 11 `doc_title` phân biệt cho 18 `doc_id`, và tệp báo cáo tài chính còn tồn tại.

- [ ] **Step 2: HỎI CHỦ DỰ ÁN, rồi xoá và nạp lại**

Sau khi được đồng ý:
```bash
docker exec youdoo-postgres psql -U admin -d ai_assistant -c "DELETE FROM rag_documents;"
cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m src.rag.ingest <đường dẫn seed + tệp báo cáo tài chính>
```
(Chữ ký CLI thật của `ingest` phải đọc từ `backend/src/rag/ingest.py` — đừng đoán.)

- [ ] **Step 3: Nghiệm thu**

```bash
docker exec youdoo-postgres psql -U admin -d ai_assistant -c "SELECT doc_title, count(DISTINCT doc_id) n_doc FROM rag_chunks GROUP BY 1 HAVING count(DISTINCT doc_id) > 1;"
```
Expected: **0 hàng.** Còn hàng nào tức là còn hai tài liệu trùng tên — và `report.warnings` của Step 2 phải đã gọi tên đúng chúng.

```bash
docker exec youdoo-postgres psql -U admin -d ai_assistant -c "SELECT count(*) FROM rag_chunks;"
```
Expected: xấp xỉ 4870. **Lệch quá 5% thì dừng và điều tra** — nghĩa là một tệp không nạp lại được.

- [ ] **Step 4: Chạy lại test hợp đồng golden set**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/evals -m "integration" -q`
Expected: tất cả xanh. Nếu đỏ: nhãn `retrieval_cases` hoặc `aggregate_cases` đã trôi vì lượt nạp lại — điều tra trước khi sửa nhãn.

- [ ] **Step 5: Đo lại bộ aggregate, KHÔNG ghi đè mốc nền**

```bash
cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m evals.run_eval --set aggregate --model bge-m3 --baseline evals/baseline-bge-m3-aggregate.json
```

Ghi lại delta. **Dự đoán: gần như không đổi** — `doc_title` không đi vào `index_text()`/`ts_vector` nên vector không đổi. Nếu độ phủ đổi ĐÁNG KỂ thì có thứ khác đã đổi theo trong lượt nạp lại; điều tra, đừng ăn mừng.

- [ ] **Step 6: Ghi lại và commit**

Ghi ba mục bắt buộc vào cuối spec (`docs/superpowers/specs/2026-09-08-cau-hoi-tong-hop-design.md`), mục mới "## 11. Ghi chép thực thi": *khó khăn thật sự gặp* / *hướng đã chọn và vì sao* / *giới hạn còn lại, đã đo hay chưa đo*. Kèm bảng `doc_title` trước/sau.

```bash
git add docs/superpowers/specs/2026-09-08-cau-hoi-tong-hop-design.md
git commit -m "docs: ghi chep nap lai corpus + bang doc_title truoc/sau

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Tín hiệu độ phủ trên `RetrievalResult`

**Files:**
- Modify: `backend/src/rag/types.py`
- Modify: `backend/src/rag/retrieve.py`
- Create: `backend/tests/rag/test_coverage_signal.py`

**Interfaces:**
- Consumes: `Chunk`, `RetrievalResult` (types.py), `_db.connect` (retrieve.py).
- Produces:
  - `types.DocCoverage` — dataclass đông cứng: `doc_id: str`, `doc_title: str`, `chunks_seen: int`, `chunks_total: int`, `sections_seen: int`, `sections_total: int`.
  - `types.RetrievalResult.coverage: tuple[DocCoverage, ...] = ()`
  - `retrieve._coverage(conn, chunks) -> tuple[DocCoverage, ...]`

**Phạm vi CÓ CHỦ ĐÍCH:** task này chỉ TÍNH và PHƠI con số. Không đưa vào `RAG_SYNTHESIS_PROMPT`, không đưa vào state LangGraph, không đổi câu trả lời. Đó là Kế hoạch B và cần A/B `synthesis_live` — đường prompt này đã có tiền sự: thêm một fact vô hại cũng phá hợp đồng guard (`refusal_acc` 1,0 → 0,9643).

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/rag/test_coverage_signal.py`:

```python
# backend/tests/rag/test_coverage_signal.py
"""Tín hiệu độ phủ — spec 2026-09-08 mục 5.

Đo 2026-09-08: "tóm tắt luật doanh nghiệp" lấy 6/530 chunk (1,1%) và
passes_floor VẪN cho qua. Không có chỗ nào trong hệ nói được "tôi mới đọc
6/530 đoạn". Task này làm con số đó tồn tại.
"""
import pytest

from src.rag.retrieve import _coverage
from src.rag.types import Chunk, DocCoverage, RetrievalResult


def _chunk(chunk_id, doc_id, section_path):
    return Chunk(chunk_id=chunk_id, doc_id=doc_id, source_file=doc_id,
                 doc_title="x", section_path=section_path, page=None,
                 sheet=None, row_range=None, text="t", dense_score=0.5,
                 sparse_score=None, rrf_score=0.1, rank=0)


class ConnGia:
    """conn giả trả đúng shape mà _coverage mong đợi."""
    def __init__(self, rows):
        self._rows = rows
        self.seen_params = None

    def execute(self, _sql, params):
        self.seen_params = params
        return self

    def fetchall(self):
        return self._rows


def test_dem_dung_phan_da_doc_tren_tong():
    chunks = [_chunk(1, "a.pdf", "Chương I › X"),
              _chunk(2, "a.pdf", "Chương I › Y")]
    conn = ConnGia([("a.pdf", "Luật A", 530, 10)])
    got = _coverage(conn, chunks)
    assert got == (DocCoverage(doc_id="a.pdf", doc_title="Luật A",
                               chunks_seen=2, chunks_total=530,
                               sections_seen=1, sections_total=10),)


def test_hai_tai_lieu_thi_tra_hai_dong():
    chunks = [_chunk(1, "a.pdf", "Chương I"), _chunk(2, "b.docx", "Mục 1")]
    conn = ConnGia([("a.pdf", "A", 100, 5), ("b.docx", "B", 5, 5)])
    got = _coverage(conn, chunks)
    assert {c.doc_id for c in got} == {"a.pdf", "b.docx"}


def test_chunk_khong_co_breadcrumb_khong_dem_thanh_mot_muc():
    # 8 chunk trong corpus có section_path rỗng.
    chunks = [_chunk(1, "a.pdf", None), _chunk(2, "a.pdf", "")]
    conn = ConnGia([("a.pdf", "A", 100, 5)])
    got = _coverage(conn, chunks)
    assert got[0].sections_seen == 0


def test_khong_co_chunk_thi_khong_truy_van_DB():
    conn = ConnGia([])
    assert _coverage(conn, []) == ()
    assert conn.seen_params is None, "gọi DB cho danh sách rỗng là lãng phí"


def test_retrieval_result_mac_dinh_coverage_rong():
    # Tương thích ngược: mọi chỗ dựng RetrievalResult cũ không được gãy.
    r = RetrievalResult(query="q", query_used="q", chunks=[], top_score=0.0,
                        total_candidates=0)
    assert r.coverage == ()


@pytest.mark.integration
def test_tren_corpus_that_cau_tom_tat_chi_cham_mot_phan_nho():
    """Chân đối chứng SỐNG cho chính lỗi spec mô tả."""
    from src.rag.retrieve import retrieve
    result = retrieve("tóm tắt luật doanh nghiệp")
    assert result.coverage, "không có tín hiệu độ phủ"
    top = max(result.coverage, key=lambda c: c.chunks_seen)
    assert top.chunks_total > 100, "tài liệu đích phải là một bộ luật lớn"
    assert top.chunks_seen < top.chunks_total * 0.1, \
        f"kỳ vọng đọc <10% tài liệu, thực tế {top.chunks_seen}/{top.chunks_total}"
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/rag/test_coverage_signal.py -m "not integration and not live" -q`
Expected: FAIL — `ImportError: cannot import name 'DocCoverage'`

- [ ] **Step 3: Thêm kiểu**

Thêm vào `backend/src/rag/types.py`:

```python
@dataclass(frozen=True)
class DocCoverage:
    """Đã đọc bao nhiêu phần của một tài liệu trong lượt truy xuất này.

    Vì sao cần (spec 2026-09-08 mục 5): câu "tóm tắt luật doanh nghiệp" lấy
    6/530 chunk và `passes_floor` VẪN cho qua, còn prompt thì ép "nếu tài
    liệu CÓ đề cập chủ đề thì PHẢI trả lời". Hệ trả lời tự tin trên 1,1% tài
    liệu mà không chỗ nào biết điều đó.

    Tín hiệu này TẤT ĐỊNH và độc lập hoàn toàn với việc phân loại câu hỏi
    đúng hay sai — cùng tinh thần veto tất định ở routing.py.
    """
    doc_id: str
    doc_title: str
    chunks_seen: int
    chunks_total: int
    sections_seen: int
    sections_total: int
```

Và thêm trường vào `RetrievalResult` (SAU `method`, có giá trị mặc định để mọi chỗ dựng cũ không gãy):

```python
    # Rỗng là hợp lệ: lượt không có chunk nào thì không có gì để phủ.
    coverage: tuple[DocCoverage, ...] = ()
```

- [ ] **Step 4: Cài đặt `_coverage`**

Thêm vào `backend/src/rag/retrieve.py`:

```python
from .types import Chunk, DocCoverage, RetrievalResult

# Phải trùng chunking.chunk_text_blocks.
_SEP = " › "


def _coverage(conn, chunks: list[Chunk]) -> tuple[DocCoverage, ...]:
    """Phần tài liệu đã đọc / tổng, cho từng tài liệu bị chạm.

    MỘT truy vấn cho cả lượt (lọc theo doc_id, đã có index rag_chunks_doc_id)
    — không phải một truy vấn mỗi tài liệu.

    `NULLIF(..., '')` là bắt buộc, không phải trang trí: 8 chunk trong corpus
    có section_path rỗng, và không có nó thì `''` bị đếm thành một mục, thổi
    mẫu số lên bởi một mục không tồn tại.
    """
    if not chunks:
        return ()
    doc_ids = sorted({c.doc_id for c in chunks})
    rows = conn.execute(
        "SELECT doc_id, min(doc_title), count(*), "
        f"count(DISTINCT NULLIF(split_part(section_path, '{_SEP}', 1), '')) "
        "FROM rag_chunks WHERE doc_id = ANY(%s) GROUP BY doc_id",
        (doc_ids,),
    ).fetchall()
    seen_chunks: dict[str, int] = {}
    seen_sections: dict[str, set[str]] = {}
    for c in chunks:
        seen_chunks[c.doc_id] = seen_chunks.get(c.doc_id, 0) + 1
        head = (c.section_path or "").split(_SEP)[0].strip()
        if head:
            seen_sections.setdefault(c.doc_id, set()).add(head)
    return tuple(
        DocCoverage(doc_id=doc_id, doc_title=doc_title,
                    chunks_seen=seen_chunks.get(doc_id, 0),
                    chunks_total=chunks_total,
                    sections_seen=len(seen_sections.get(doc_id, ())),
                    sections_total=sections_total)
        for doc_id, doc_title, chunks_total, sections_total in rows)
```

- [ ] **Step 5: Nối vào `retrieve()`**

Trong `retrieve()`, sau `chunks = compress(query, chunks, k)` và TRƯỚC `return`:

```python
        coverage = _coverage(conn, chunks)
```

rồi thêm `coverage=coverage` vào lời dựng `RetrievalResult(...)`.

- [ ] **Step 6: Chạy test + toàn suite + đo độ trễ**

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/rag/test_coverage_signal.py -m "not integration and not live" -q`
Expected: `5 passed, 1 deselected`

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/rag/test_coverage_signal.py -m "integration" -q`
Expected: `1 passed, 5 deselected`

Run: `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest -m "not integration and not live" -q`
Expected: `2506 passed, 1 skipped, 86 deselected`

Đo độ trễ — task này thêm MỘT truy vấn vào MỌI lượt RAG:
```bash
cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m evals.run_eval --set aggregate --model bge-m3 --baseline evals/baseline-bge-m3-aggregate.json
```
So `lat_p50`/`lat_p95` với mốc nền. **Tăng quá 50ms p50 thì dừng và báo** — truy vấn này chạy trên index `rag_chunks_doc_id`, không được đắt.

- [ ] **Step 7: Commit**

```bash
git add backend/src/rag/types.py backend/src/rag/retrieve.py backend/tests/rag/test_coverage_signal.py
git commit -m "feat(rag): retrieve() tra ve tin hieu do phu

Do 2026-09-08: 'tom tat luat doanh nghiep' lay 6/530 chunk (1,1%) va
passes_floor VAN cho qua, con prompt thi ep 'neu tai lieu CO de cap chu de
thi PHAI tra loi'. He tra loi tu tin tren 1,1% tai lieu ma khong cho nao
biet dieu do.

CHI phoi con so — chua dua vao prompt. Doi RAG_SYNTHESIS_PROMPT thuoc Ke
hoach B va can A/B synthesis_live: duong nay da co tien su, them mot fact
vo hai cung pha hop dong guard (refusal_acc 1,0 -> 0,9643).

Mot truy van moi luot, tren index rag_chunks_doc_id. Do tre: <dan so do>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Cổng nghiệm thu Kế hoạch A

Chỉ được coi là xong khi **tất cả** đúng:

- [ ] `pytest -m "not integration and not live" -q` → `2506 passed, 1 skipped, 86 deselected` (2474 nền + 32 test đơn vị mới; 3 test `integration` mới nâng deselected 83 → 86), 0 failed.
- [ ] `pytest tests/evals tests/rag -m "integration" -q` → xanh toàn bộ.
- [ ] `SELECT doc_title, count(DISTINCT doc_id) FROM rag_chunks GROUP BY 1 HAVING count(DISTINCT doc_id) > 1;` → **0 hàng**.
- [ ] `backend/evals/baseline-bge-m3-aggregate.json` tồn tại và commit rồi.
- [ ] `retrieve("tóm tắt luật doanh nghiệp").coverage` trả về `chunks_seen < 10%` của `chunks_total` — tức tín hiệu PHƠI ĐÚNG lỗi, chứ không phải giấu nó.
- [ ] `lat_p50` của bộ `aggregate` không tăng quá 50ms so với mốc nền.
- [ ] `git status --porcelain` sạch (đặc biệt `backend/tests/rag/fixtures/` — full suite từng làm bẩn 2 fixture git-tracked; kiểm bằng `git status` chứ đừng tin trí nhớ).
- [ ] Spec có mục "## 11. Ghi chép thực thi" với ba mục bắt buộc.
- [ ] **Nghiệm thu SỐNG trước khi merge, trên worktree của chính nhánh** (không phải sau khi merge): hỏi backend một câu tổng hợp thật và một câu tra cứu điểm thật, xác nhận câu tra cứu điểm **không đổi hành vi**.

## Điều Kế hoạch A CỐ Ý KHÔNG làm

Ghi ở đây để không ai tưởng đã xử lý:

- **Không sửa câu trả lời cho câu hỏi tổng hợp.** Sau A, "tóm tắt luật doanh nghiệp" vẫn trả lời trên 6 chunk Chương I. Khác biệt duy nhất: giờ ta ĐO được điều đó và hệ có con số để dùng ở Kế hoạch B.
- **Không đụng `TOP_K`, `COS_FLOOR`, `RAG_SYNTHESIS_PROMPT`, `routing.py`.**
- **Không xử lý 47 chunk rác `"1."`** còn trong index (spec mục 9).
- **Không xử lý `content_hash` thiếu dấu vân tay parser** — Task 6 né bằng cách xoá tay, không sửa gốc.
- **Không xác nhận router đưa câu `"có bao nhiêu…"` vào `rag`** — cần lời gọi LLM thật, để Kế hoạch B.
