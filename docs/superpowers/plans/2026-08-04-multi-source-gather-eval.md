# Set eval `multi_source_gather` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm set eval `multi_source_gather` đo TOÀN CHUỖI nhánh `mixed`
(`gather_erp` THẬT → `fuse_answer`), song song với `multi_source` hiện có
(vốn nạp sẵn `erp_block` viết tay và chưa từng gọi `gather_erp`).

**Architecture:** Tách phần chấm điểm của `eval_multi_source` thành helper
thuần `_score_fusion` dùng chung; thêm danh sách case
`MULTI_SOURCE_GATHER_CASES` phản chiếu 1-1 `MULTI_SOURCE_CASES` nhưng thay
`erp_block` bằng `tool_fixtures`; thêm `eval_multi_source_gather` gọi
`make_gather_erp_node` thật trên tool giả lập rồi đưa `erp_facts` thu được
vào `render_fuse_input`; đăng ký set mới vào `eval_gate` ở chế độ GHI NHẬN
(gate luôn PASS, loại khỏi `--set all`).

**Tech Stack:** Python 3.12, pytest, LangChain/LangGraph, `evals/run_eval.py`,
`jobs/eval_gate.py`.

**Spec:** `docs/superpowers/specs/2026-08-04-multi-source-gather-eval-design.md`

## Global Constraints

- **`eval_multi_source` phải giữ nguyên hành vi tuyệt đối.** Set này đang GÁC
  thật (`_gate()` yêu cầu `citation_validity == 1.0`, `fabricated_number == 0`,
  `both_source_coverage >= baseline`). Refactor ở Task 1 là thuần cấu trúc;
  bất kỳ khác biệt kết quả nào là lỗi.
- **`MULTI_SOURCE_GATHER_CASES` phản chiếu 1-1 `MULTI_SOURCE_CASES`**: cùng
  `topic`, `question`, `doc_fact`, `erp_fact`, CÙNG THỨ TỰ. Chỉ ERP đổi.
- **Fixture chỉ được dùng field tool THẬT SỰ đọc.** Đây là "hạng lỗi thứ ba"
  đã tái diễn 4 lần trong project. Contract test ở Task 4 canh việc này.
- **Set mới KHÔNG gate**: `_gate("multi_source_gather", ...)` trả `True` vô
  điều kiện; loại khỏi `--set all`; không có entry trong `BASELINES`.
- Chạy test: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest <path> -q`
- Chạy eval thật cần env: `set -a && source ../.env && set +a` trước khi gọi
  `-m jobs run eval-gate` (bash), và Postgres `youdoo` phải đang chạy.
- Comment/docstring trong repo này viết tiếng Việt — giữ đúng văn phong file
  đang sửa.
- KHÔNG sửa fixture `get_product_price` của `GATHER_CASES` (khẳng định "đã áp
  chiết khấu số lượng 12%" trong khi hàm thật chỉ đọc `list_price`) — cố ý
  ngoài phạm vi, xem spec §7. Chỉ thêm comment cảnh báo.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/evals/run_eval.py` | `_score_fusion` (helper chấm điểm thuần, dùng chung); `eval_multi_source` (giữ nguyên hành vi, gọi helper); `eval_multi_source_gather` (mới) |
| `backend/evals/cases.py` | `MULTI_SOURCE_GATHER_CASES` (mới, 8 ca); dọn 2 comment CẢNH BÁO lỗi thời; thêm comment cảnh báo `get_product_price` |
| `backend/jobs/eval_gate.py` | Đăng ký set mới (`EVAL_FN`, `ROLE_FOR_SET`, `--set choices`), `_gate()` trả True, loại khỏi `all`, nhánh in báo cáo |
| `backend/tests/jobs/test_eval_multi_source.py` | Test chốt refactor Task 1 giữ nguyên hành vi |
| `backend/tests/jobs/test_eval_multi_source_gather.py` (mới) | Test tự-nhất-quán danh sách mới, parity, wiring, đăng ký eval_gate |
| `backend/tests/jobs/test_eval_gather.py` | Mở rộng contract test sang danh sách mới |

---

### Task 1: Tách `_score_fusion` — refactor giữ nguyên hành vi

**Files:**
- Modify: `backend/evals/run_eval.py:590-657` (`eval_multi_source`)
- Test: `backend/tests/jobs/test_eval_multi_source.py`

**Interfaces:**
- Consumes: `_grounded_match`, `_cited_indices`, `_digits`, `_format_context`,
  `_MARKER_RE`, `MULTI_SOURCE_DERIVED_DIGITS` — tất cả đã có sẵn trong
  `run_eval.py`.
- Produces:
  ```python
  def _score_fusion(body: str, chunks, erp_text: str,
                    doc_fact, erp_fact, topic: str, question: str,
                    allowed_extra_text: str = "") -> dict
  # trả {"both": bool, "citation_ok": bool, "fabricated": list[str]}
  ```
  Task 3 gọi hàm này với `allowed_extra_text=question`.

- [ ] **Step 1: Viết test chốt refactor (chạy TRƯỚC khi sửa code — phải FAIL vì hàm chưa tồn tại)**

Thêm vào cuối `backend/tests/jobs/test_eval_multi_source.py`:

```python
# ── Chốt refactor _score_fusion (plan 2026-08-04) ────────────────────────────


def test_score_fusion_matches_legacy_formula():
    """multi_source đang GÁC thật — tách helper mà đổi kết quả một ca nào là
    đổi cổng. So _score_fusion với công thức CŨ chép nguyên văn (từ
    eval_multi_source trước khi tách), trên chunk thật + case thật, không
    cần LLM."""
    from src.agents.synthesis import _format_context, _MARKER_RE
    from evals import cases, fixtures
    from evals.run_eval import (_cited_indices, _digits, _grounded_match,
                                _score_fusion)

    def legacy(body, chunks, erp_block, doc_fact, erp_fact, topic, question):
        both = _grounded_match(doc_fact, body) and _grounded_match(erp_fact, body)
        cited = _cited_indices(body)
        citation_ok = all(1 <= i <= len(chunks) for i in cited)
        allowed = _digits(erp_block) | _digits(_format_context(chunks))
        allowed |= cases.MULTI_SOURCE_DERIVED_DIGITS.get((topic, question),
                                                         frozenset())
        m = _MARKER_RE.search(body)
        prose = body[:m.start()] if m else body
        fabricated = sorted(_digits(prose) - allowed)
        return {"both": both, "citation_ok": citation_ok,
                "fabricated": fabricated}

    bodies = [
        "Đơn S00042 được giao trong 3 ngày, đúng SLA.\nĐã dùng: 1, 2",
        "Không đủ căn cứ để trả lời.",
        "Một số lạ 987654321 xuất hiện ở đây.\nĐã dùng: 99",
        "Hóa đơn INV/2026/00020 quá hạn từ 01/08/2026.\nĐã dùng: 1",
        "",
    ]
    for topic, erp_block, question, doc_fact, erp_fact in cases.MULTI_SOURCE_CASES:
        chunks = fixtures.load_chunks(topic)
        for body in bodies:
            assert _score_fusion(body, chunks, erp_block, doc_fact, erp_fact,
                                 topic, question) == legacy(
                body, chunks, erp_block, doc_fact, erp_fact, topic, question), (
                f"lệch ở case {topic} / body {body[:40]!r}")


def test_score_fusion_allowed_extra_text_whitelists_question_digits():
    """Bất đối xứng CÓ CHỦ ĐÍCH (spec §5): số nằm nguyên văn trong câu hỏi
    thì model chép lại không thể gọi là "bịa". CHỈ set multi_source_gather
    bật cờ này — erp_block viết tay của multi_source xưa nay vẫn nhắc lại
    số của câu hỏi nên không cần, còn đầu ra tool thật thì không (ca S00050:
    get_overdue_invoices trả hóa đơn, không trả mã đơn bán)."""
    from evals import fixtures
    from evals.run_eval import _score_fusion

    chunks = fixtures.load_chunks("chinh_sach_thanh_toan")
    question = "Đơn S09999123 có bị tạm dừng xử lý không?"
    body = "Đơn S09999123 bị tạm dừng xử lý."
    common = dict(chunks=chunks, erp_text="dữ kiện ERP không nhắc mã đơn",
                  doc_fact="tạm dừng", erp_fact="S09999123",
                  topic="chinh_sach_thanh_toan", question=question)
    without = _score_fusion(body, **common)
    with_q = _score_fusion(body, allowed_extra_text=question, **common)
    assert "09999123" in without["fabricated"]
    assert "09999123" not in with_q["fabricated"]


def test_eval_multi_source_uses_helper_without_extra_text():
    """Chống trôi: eval_multi_source PHẢI đi qua helper (không giữ bản sao
    công thức) và PHẢI KHÔNG truyền allowed_extra_text — set đang gác giữ
    nguyên công thức cũ."""
    import inspect
    from evals import run_eval
    src = inspect.getsource(run_eval.eval_multi_source)
    assert "_score_fusion" in src
    assert "allowed_extra_text" not in src
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/jobs/test_eval_multi_source.py -q`
Expected: FAIL — `ImportError: cannot import name '_score_fusion' from 'evals.run_eval'`

- [ ] **Step 3: Thêm `_score_fusion` vào `run_eval.py`**

Chèn NGAY TRƯỚC `async def eval_multi_source` (hiện ở dòng 590), sau
`def _digits(...)`:

```python
def _score_fusion(body: str, chunks, erp_text: str, doc_fact, erp_fact,
                  topic: str, question: str,
                  allowed_extra_text: str = "") -> dict:
    """Chấm một câu trả lời tổng hợp 2 nguồn — DÙNG CHUNG cho
    eval_multi_source (ERP = erp_block viết tay) và eval_multi_source_gather
    (ERP = tool_fixtures mà gather_erp thật đi lấy).

    Tách ra vì đoạn này có lịch sử lỗi riêng đáng kể: `allowed` từng dựng
    sai basis (model nhìn thấy _format_context(chunks) nhưng allowed chỉ
    dựng từ c.text trần → số trong nhãn mục bị quy oan là "bịa"), và
    MULTI_SOURCE_DERIVED_DIGITS ra đời từ 2 lượt gate fail thật. Chép lại
    công thức này sang hàm thứ hai là mời đúng lớp lỗi đó quay lại.

    `erp_text` là NGUỒN SỰ THẬT của phía ERP, không phải văn bản model sinh
    ra: ở set gather nó là tool_fixtures ghép lại, KHÔNG phải erp_facts —
    lấy erp_facts làm basis sẽ tự hợp thức hóa số do chính tầng gather bịa.

    `allowed_extra_text` (mặc định "" = không đổi gì) cho phép whitelist
    thêm một nguồn số hợp lệ. eval_multi_source KHÔNG dùng — giữ nguyên
    công thức của một set đang GÁC thật. Xem spec §5.
    """
    both = _grounded_match(doc_fact, body) and _grounded_match(erp_fact, body)
    cited = _cited_indices(body)
    citation_ok = all(1 <= i <= len(chunks) for i in cited)
    allowed = (_digits(erp_text) | _digits(_format_context(chunks))
               | _digits(allowed_extra_text))
    allowed |= MULTI_SOURCE_DERIVED_DIGITS.get((topic, question), frozenset())
    # bỏ marker trước khi soi số, tránh coi chính index trích dẫn là số bịa
    m = _MARKER_RE.search(body)
    prose = body[:m.start()] if m else body
    fabricated = sorted(_digits(prose) - allowed)
    return {"both": both, "citation_ok": citation_ok, "fabricated": fabricated}
```

- [ ] **Step 4: Thay thân `eval_multi_source.call()` bằng lời gọi helper**

Trong `eval_multi_source`, thay TOÀN BỘ khối từ `body = (resp.content or "").strip()`
tới `"fabricated": fabricated}` (hiện dòng 612-639) bằng:

```python
        body = (resp.content or "").strip()
        score = _score_fusion(body, chunks, erp_block, doc_fact, erp_fact,
                              topic, question)
        if score["both"] and score["citation_ok"] and not score["fabricated"]:
            return None
        return {"topic": topic, "question": question, "response": body[:300],
                **score}
```

Cập nhật docstring của `eval_multi_source`: thêm một câu ở cuối —
`"Chấm điểm nằm ở _score_fusion (dùng chung với eval_multi_source_gather);
set này KHÔNG truyền allowed_extra_text để giữ nguyên công thức đang gác."`

- [ ] **Step 5: Chạy test — phải PASS**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/jobs/test_eval_multi_source.py tests/jobs/test_eval_gate.py -q`
Expected: PASS toàn bộ.

- [ ] **Step 6: Commit**

```bash
git add backend/evals/run_eval.py backend/tests/jobs/test_eval_multi_source.py
git commit -m "refactor(eval): tách _score_fusion dùng chung, eval_multi_source giữ nguyên hành vi"
```

---

### Task 2: `MULTI_SOURCE_GATHER_CASES` + dọn comment lỗi thời

**Files:**
- Modify: `backend/evals/cases.py` (thêm danh sách mới sau `MULTI_SOURCE_CASES`
  kết thúc ở dòng 439; sửa 2 comment CẢNH BÁO trong `GATHER_CASES` dòng
  ~517-527 và ~536-542; thêm comment cảnh báo tại fixture `get_product_price`
  dòng ~566-576)
- Test: `backend/tests/jobs/test_eval_multi_source_gather.py` (TẠO MỚI)

**Interfaces:**
- Produces: `cases.MULTI_SOURCE_GATHER_CASES: list[tuple[str, dict[str, str], str, str | tuple[str, ...], str | tuple[str, ...]]]`
  — hình dạng mỗi phần tử `(topic, tool_fixtures, question, doc_fact, erp_fact)`.
  Task 3 và Task 4 đều đọc danh sách này.

- [ ] **Step 1: Viết test tự-nhất-quán + parity (chạy trước, phải FAIL)**

Tạo `backend/tests/jobs/test_eval_multi_source_gather.py`:

```python
# backend/tests/jobs/test_eval_multi_source_gather.py
"""Set multi_source_gather: đo TOÀN CHUỖI nhánh mixed (gather_erp thật →
fuse_answer) trên cùng bộ câu hỏi/kỳ vọng của multi_source. Không gate —
chưa có baseline (spec 2026-08-04 §3)."""
from evals import cases, fixtures


def test_gather_cases_mirror_multi_source_cases_exactly():
    """Ràng buộc trung tâm của cả plan (spec §4): hai danh sách phải khớp
    (topic, question, doc_fact, erp_fact) theo ĐÚNG thứ tự. Lệch một chỗ là
    hai bộ số hết so sánh được — mà so sánh được chính là toàn bộ lý do set
    này tồn tại. Cũng là điều kiện để dùng CHUNG
    MULTI_SOURCE_DERIVED_DIGITS (khoá theo (topic, question))."""
    assert len(cases.MULTI_SOURCE_GATHER_CASES) == len(cases.MULTI_SOURCE_CASES)
    for g, m in zip(cases.MULTI_SOURCE_GATHER_CASES, cases.MULTI_SOURCE_CASES):
        g_topic, _g_fixtures, g_question, g_doc, g_erp = g
        m_topic, _m_block, m_question, m_doc, m_erp = m
        assert (g_topic, g_question, g_doc, g_erp) == \
               (m_topic, m_question, m_doc, m_erp)


def test_derived_digits_keys_all_reachable():
    """MULTI_SOURCE_DERIVED_DIGITS dùng CHUNG cho hai set — mọi khoá của nó
    phải ứng với một case có thật ở CẢ HAI danh sách, nếu không nó là cấu
    hình chết (đúng lớp lỗi _DATE_STATUS_LABELS['trạng thái giao'] đã mắc)."""
    gather_keys = {(t, q) for t, _f, q, _d, _e in cases.MULTI_SOURCE_GATHER_CASES}
    base_keys = {(t, q) for t, _b, q, _d, _e in cases.MULTI_SOURCE_CASES}
    for key in cases.MULTI_SOURCE_DERIVED_DIGITS:
        assert key in gather_keys, f"khoá {key} không ứng case gather nào"
        assert key in base_keys, f"khoá {key} không ứng case multi_source nào"


def test_gather_cases_shape_and_topics_exist():
    topics = set(fixtures.available_topics())
    for topic, tool_fixtures, question, doc_fact, erp_fact in cases.MULTI_SOURCE_GATHER_CASES:
        assert topic in topics, f"topic {topic} không có trong fixture"
        assert question.strip()
        assert tool_fixtures and all(
            k.strip() and v.strip() for k, v in tool_fixtures.items())
        assert doc_fact
        assert erp_fact


def test_gather_cases_tool_names_are_real():
    from src.erp_query.tools import build_erp_query_tools
    real_names = {t.name for t in build_erp_query_tools()}
    for topic, tool_fixtures, question, _doc, _erp in cases.MULTI_SOURCE_GATHER_CASES:
        for name in tool_fixtures:
            assert name in real_names, (
                f"case {topic}: tool_fixtures có {name!r} — không phải tên "
                f"tool thật nào trong build_erp_query_tools()")


def test_erp_fact_reachable_from_fixtures_or_question():
    """Tự-mâu-thuẫn là lỗi: erp_fact phải xuất hiện nguyên văn trong
    tool_fixtures HOẶC trong chính câu hỏi — nếu không, case đòi model nói
    điều không nguồn nào chứa. (Ca S00050 nằm ở vế "hoặc": mã đơn bán không
    bao giờ có trong đầu ra get_overdue_invoices thật, nó đến từ câu hỏi.)"""
    for topic, tool_fixtures, question, _doc, erp_fact in cases.MULTI_SOURCE_GATHER_CASES:
        corpus = (" ".join(tool_fixtures.values()) + " " + question).casefold()
        options = (erp_fact,) if isinstance(erp_fact, str) else erp_fact
        assert any(o.casefold() in corpus for o in options), (
            f"case {topic}: erp_fact {erp_fact!r} không có trong "
            f"tool_fixtures lẫn câu hỏi")
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/jobs/test_eval_multi_source_gather.py -q`
Expected: FAIL — `AttributeError: module 'evals.cases' has no attribute 'MULTI_SOURCE_GATHER_CASES'`

- [ ] **Step 3: Thêm `MULTI_SOURCE_GATHER_CASES` vào `cases.py`**

Chèn NGAY SAU khi `MULTI_SOURCE_CASES` đóng ngoặc (hiện dòng 439), TRƯỚC
`# ── SOP_SELECT_CASES ──`:

```python
# ── multi_source_gather set (2026-08-04) ─────────────────────────────────────
# (topic fixture, tool_fixtures, câu hỏi, dữ kiện TÀI LIỆU kỳ vọng, dữ kiện
#  ERP kỳ vọng).
#
# PHẢN CHIẾU 1-1 MULTI_SOURCE_CASES: cùng topic, cùng question, cùng
# doc_fact, cùng erp_fact, CÙNG THỨ TỰ (test chốt cứng ở
# tests/jobs/test_eval_multi_source_gather.py). Khác biệt DUY NHẤT: phía ERP
# đổi từ erp_block viết tay — thứ fuse_answer được NẠP SẴN — thành
# tool_fixtures mà gather_erp THẬT phải tự đi lấy. Nhờ chỉ đổi đúng một
# biến, chênh lệch số đo giữa hai set quy được về đúng một nguyên nhân.
#
# Vì sao set này tồn tại: eval_multi_source chưa từng gọi gather_erp, nên 4
# plan liên tiếp sửa đúng vào năng lực thu thập ERP (2026-08-01 → 2026-08-02)
# đều không làm both_source_coverage nhúc nhích. Xem
# docs/superpowers/specs/2026-08-04-multi-source-gather-eval-design.md.
#
# tool_fixtures: dict {tool_name: text}, cùng cơ chế GATHER_CASES
# (run_eval._stub_erp_tools — tool không có trong dict trả "Không có dữ liệu
# liên quan."). KỶ LUẬT VIẾT: fixture phải mô phỏng đầu ra THẬT của tool đó,
# chỉ dùng field hàm business-layer thật sự đọc. Contract test ở
# tests/jobs/test_eval_gather.py quét CẢ danh sách này.
MULTI_SOURCE_GATHER_CASES = [
    # sla_giao_hang ← sla.docx
    # get_sale_order_detail đọc: id, name, partner_id, amount_total, state,
    # date_order, delivery_status, commitment_date, effective_date
    # (sales.py:52-55) — mọi nhãn dưới đây ứng đúng một field trong đó.
    ("sla_giao_hang",
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | Tổng 1.500.000\n"
      "  trạng thái: sale | ngày xác nhận: 18/07/2026 | "
      "ngày giao dự kiến: 20/07/2026 | ngày giao thực tế: 21/07/2026 | "
      "trạng thái giao: full"},
     "Đơn S00042 có đáp ứng SLA giao hàng không?", "3 ngày", "S00042"),
    # list_late_deliveries đọc stock.picking: name, partner_id,
    # scheduled_date, state (inventory.py:115-117). KHÔNG có ngày giao thực
    # tế — dùng nhãn "hẹn" đúng như dòng display thật, không phải "ngày giao
    # dự kiến" (nhãn đó thuộc về commitment_date của sale.order).
    ("sla_giao_hang",
     {"list_late_deliveries":
      "1 phiếu trễ hạn:\n"
      "  WH/OUT/00001 | Azure Interior | hẹn 18/07/2026 | assigned"},
     "Phiếu WH/OUT/00001 có vi phạm SLA không?", "0,5%", "WH/OUT/00001"),
    # chinh_sach_hoan_hang ← policy.docx
    ("chinh_sach_hoan_hang",
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | Tổng 1.500.000\n"
      "  trạng thái: done | ngày xác nhận: 10/07/2026 | "
      "ngày giao thực tế: 15/07/2026 | trạng thái giao: full"},
     "Đơn S00042 còn được hoàn hàng theo chính sách không?", "30 ngày",
     "S00042"),
    # list_invoices/get_overdue_invoices dùng chung accounting._FIELDS:
    # name, partner_id, invoice_date, invoice_date_due, amount_total,
    # amount_residual, payment_state (accounting.py:7-8).
    ("chinh_sach_hoan_hang",
     {"list_invoices":
      "1 hóa đơn:\n"
      "  INV/2026/00017 | Azure Interior | ngày hóa đơn 12/07/2026 | "
      "đến hạn 11/08/2026 | 1.500.000 | còn 0 | paid"},
     "Hóa đơn INV/2026/00017 có được hoàn tiền không?", "5 đến 10 ngày",
     "INV/2026/00017"),
    # chinh_sach_thanh_toan ← payment_policy.docx
    #
    # KHÁC BIỆT CÓ CHỦ ĐÍCH so với erp_block của MULTI_SOURCE_CASES (spec
    # §4.2): erp_block cũ chỉ nêu "xuất ngày 01/07/2026", buộc model tự cộng
    # 30 ngày. list_invoices THẬT luôn trả kèm invoice_date_due, nên fixture
    # này có sẵn ngày đến hạn và ca này DỄ HƠN ca tương ứng bên
    # MULTI_SOURCE_CASES. Không phải làm nhẹ đề — đó là tính chất thật của
    # pipeline thật. Đừng đọc chênh lệch số đo giữa hai set ở ca này như
    # chênh lệch chất lượng model.
    ("chinh_sach_thanh_toan",
     {"list_invoices":
      "1 hóa đơn:\n"
      "  INV/2026/00020 | Wood Corner | ngày hóa đơn 01/07/2026 | "
      "đến hạn 31/07/2026 | 2.000.000 | còn 2.000.000 | not_paid"},
     "Hóa đơn INV/2026/00020 xuất ngày 01/07/2026, khi nào thì quá hạn thanh toán?",
     "30 ngày", "INV/2026/00020"),
    # Fixture lấy NGUYÊN VĂN từ GATHER_CASES (cùng câu hỏi, cùng tool) — hai
    # bộ đo kể cùng một câu chuyện về cùng dữ liệu.
    # erp_fact là tuple 2 phương án, thừa kế nguyên do từ MULTI_SOURCE_CASES
    # (model trả lời đúng nhưng gọi khách hàng bằng TÊN thay vì lặp mã đơn).
    # Lưu ý: "S00050" KHÔNG có trong fixture — get_overdue_invoices trả hóa
    # đơn, không trả mã đơn bán. Mã đó đến từ chính câu hỏi; đây là ca duy
    # nhất khiến eval_multi_source_gather phải truyền
    # allowed_extra_text=question (spec §5).
    ("chinh_sach_thanh_toan",
     {"get_overdue_invoices":
      "2 hóa đơn quá hạn:\n"
      "  INV/2026/00030 | Gemini Furniture | đến hạn 30/06/2026 | "
      "quá hạn 32 ngày | còn 4.200.000\n"
      "  INV/2026/00031 | Wood Corner | đến hạn 05/07/2026 | "
      "quá hạn 20 ngày | còn 1.000.000"},
     "Đơn S00050 quá hạn thanh toán 32 ngày, đơn hàng mới của khách này có "
     "bị tạm dừng xử lý không?",
     "tạm dừng xử lý", ("S00050", "Gemini Furniture")),
    # bang_gia_chiet_khau ← discount_policy.docx
    #
    # get_product_price THẬT chỉ đọc name + list_price (sales.py:81-82) và
    # docstring nói rõ nó KHÔNG áp pricelist/chiết khấu (cần ORM method mà
    # gateway read-only không cho phép). Fixture dưới đây viết đúng như vậy:
    # ERP cấp giá niêm yết + khách hàng, phần trăm chiết khấu đến từ TÀI
    # LIỆU. Đây là phân công nguồn đúng cho một câu hỏi 2 nguồn.
    ("bang_gia_chiet_khau",
     {"find_customer": "Tìm thấy 1 khách hàng: Azure Interior (ID 42)",
      "find_product": "Tìm thấy 1 sản phẩm: Large Cabinet (ID 108)",
      "get_product_price": "Giá Large Cabinet: 2.400.000 (SL 50)."},
     "Azure Interior đặt 50 Large Cabinet được chiết khấu bao nhiêu?",
     "chiết khấu", "Azure Interior"),
    ("bang_gia_chiet_khau",
     {"find_customer": "Tìm thấy 1 khách hàng: Azure Interior (ID 42)",
      "find_product": "Tìm thấy 1 sản phẩm: Desk Pad (ID 55)",
      "get_product_price": "Giá Desk Pad: 90.000 (SL 2)."},
     "Đơn 2 Desk Pad của Azure Interior có được chiết khấu không?",
     "chiết khấu", "Desk Pad"),
]
```

- [ ] **Step 4: Chạy test — phải PASS**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/jobs/test_eval_multi_source_gather.py -q`
Expected: PASS (5 test).

- [ ] **Step 5: Dọn 2 comment CẢNH BÁO lỗi thời trong `GATHER_CASES`**

Trong `backend/evals/cases.py`, ca `sla_giao_hang` của `GATHER_CASES`: XOÁ
nguyên khối comment bắt đầu bằng `# CẢNH BÁO (fix wave sau final review,
2026-08-02): "18/07/2026" (ngày` cho tới hết dòng
`# (Task 2 Bước 10) để biết chi tiết và hướng sửa khả dĩ (chưa làm).`, thay
bằng:

```python
    # Nhãn ngày trong tool_fixtures dưới đây đã được đối chiếu với field
    # THẬT: get_sale_order_detail đọc date_order ("ngày xác nhận") và
    # commitment_date ("ngày giao dự kiến") — bổ sung ở plan
    # sale-order-effective-dates (2026-08-02). Cảnh báo cũ tại đây (nói
    # không tool nào trả về được ngày giao dự kiến) đã HẾT HIỆU LỰC từ lúc
    # đó; contract test test_eval_gather.py canh việc này tự động.
```

Ca `chinh_sach_hoan_hang`: XOÁ khối comment bắt đầu `# CẢNH BÁO (fix wave
sau final review, 2026-08-02): "15/07/2026" (ngày` cho tới hết dòng
`# (Task 2 Bước 10).`, thay bằng:

```python
    # "ngày giao thực tế" ứng field THẬT effective_date của
    # get_sale_order_detail (thêm ở plan sale-order-effective-dates,
    # 2026-08-02). Cảnh báo cũ tại đây đã hết hiệu lực.
```

- [ ] **Step 6: Thêm comment cảnh báo tại fixture `get_product_price` của `GATHER_CASES`**

Ngay TRƯỚC dòng `("bang_gia_chiet_khau", "Azure Interior đặt 50 Large Cabinet...`
trong `GATHER_CASES`, chèn thêm vào khối comment đang có:

```python
    # CẢNH BÁO CHƯA SỬA (phát hiện 2026-08-04, spec
    # 2026-08-04-multi-source-gather-eval-design.md §7): fixture
    # get_product_price dưới đây khẳng định "đã áp chiết khấu số lượng 12%",
    # nhưng sales.get_product_price (sales.py:73-90) chỉ đọc list_price và
    # docstring nói rõ nó KHÔNG áp pricelist/chiết khấu — pricelist cần ORM
    # method mà gateway read-only không cho phép. Đây là đúng "hạng lỗi thứ
    # ba" (fixture khẳng định năng lực tool không có), ở một tool contract
    # test chưa phủ (nhãn hiện chỉ về ngày/trạng thái, không về giá).
    # CỐ Ý chưa sửa: required_facts của ca này là ("12%",), sửa sẽ đổi số đo
    # của set `gather` và cần một lượt đo riêng để quy trách nhiệm.
```

- [ ] **Step 7: Chạy lại toàn bộ test eval — phải PASS**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/jobs/ -q`
Expected: PASS toàn bộ (comment thay đổi không ảnh hưởng logic).

- [ ] **Step 8: Commit**

```bash
git add backend/evals/cases.py backend/tests/jobs/test_eval_multi_source_gather.py
git commit -m "feat(eval): MULTI_SOURCE_GATHER_CASES phản chiếu 1-1 MULTI_SOURCE_CASES + dọn comment lỗi thời"
```

---

### Task 3: `eval_multi_source_gather` + đăng ký `eval_gate`

**Files:**
- Modify: `backend/evals/run_eval.py` (import `MULTI_SOURCE_GATHER_CASES` ở
  dòng 19-23; thêm hàm mới ngay sau `eval_multi_source`, hiện kết thúc dòng 657)
- Modify: `backend/jobs/eval_gate.py` (`ROLE_FOR_SET` dòng 36-42, `EVAL_FN`
  dòng 43-48, `_gate()` dòng 51-93, `run()` dòng 99-112 và 182-210,
  `add_args()` dòng 219-223)
- Test: `backend/tests/jobs/test_eval_multi_source_gather.py`

**Interfaces:**
- Consumes: `_score_fusion(body, chunks, erp_text, doc_fact, erp_fact, topic, question, allowed_extra_text="") -> dict`
  (Task 1); `cases.MULTI_SOURCE_GATHER_CASES` hình dạng
  `(topic, tool_fixtures, question, doc_fact, erp_fact)` (Task 2); sẵn có
  trong `run_eval.py`: `_stub_erp_tools(tool_fixtures, called) -> list`,
  `make_gather_erp_node(llm, tools) -> node`, `_timed(coro) -> (result, ms)`,
  `render_fuse_input(chunks, erp_facts, question) -> str`, `FUSE_PROMPT`,
  `run_resilient`, `_percentiles`.
- Produces: `async def eval_multi_source_gather(llm, pace: float = 0.0, checkpoint_path=None) -> dict`
  với các khoá `set, n, both_source_coverage, citation_validity,
  fabricated_number, lat_p50, lat_p95, fails, errors`.

- [ ] **Step 1: Viết test (chạy trước, phải FAIL)**

Thêm vào cuối `backend/tests/jobs/test_eval_multi_source_gather.py`:

```python
# ── eval_multi_source_gather + đăng ký eval_gate ─────────────────────────────

from evals import run_eval


def test_eval_calls_real_gather_node_and_real_fuse_prompt():
    """Chống trôi (cùng khuôn test_eval_gather.py đã dùng): hàm PHẢI đi qua
    node/prompt production thật, không dựng lại logic thu thập hay tổng
    hợp — đó là điều kiện để phép đo không trôi khỏi thứ nó đang đo."""
    import inspect
    src = inspect.getsource(run_eval.eval_multi_source_gather)
    for token in ("make_gather_erp_node", "_stub_erp_tools", "FUSE_PROMPT",
                  "render_fuse_input", "_score_fusion",
                  "allowed_extra_text=question"):
        assert token in src, f"thiếu {token}"


def test_eval_scores_against_tool_fixtures_not_model_output():
    """basis của `allowed` phải là tool_fixtures (sự thật gốc), KHÔNG phải
    erp_facts model sinh ra — nếu lấy erp_facts, số do chính tầng gather bịa
    sẽ tự được hợp thức hoá (spec §5)."""
    import inspect
    src = inspect.getsource(run_eval.eval_multi_source_gather)
    assert "tool_fixtures.values()" in src


def test_eval_wires_gather_output_into_fuse_input():
    """Kiểm THẬT SỰ chạy (không chỉ đọc mã): erp_facts do gather_erp trả về
    phải đi vào render_fuse_input, và `called` phải được ghi lại."""
    import asyncio
    import unittest.mock
    from langchain_core.messages import AIMessage

    seen_fuse_inputs = []

    class _FakeLLM:
        async def ainvoke(self, messages):
            seen_fuse_inputs.append(messages[-1].content)
            return AIMessage(content="câu trả lời bất kỳ\nĐã dùng: 1")

    async def _fake_node(state):
        return {"erp_facts": "DẤU-VÂN-TAY-GATHER"}

    with unittest.mock.patch.object(run_eval, "make_gather_erp_node",
                                    lambda llm, tools: _fake_node):
        out = asyncio.run(run_eval.eval_multi_source_gather(_FakeLLM()))

    assert out["set"] == "multi_source_gather"
    assert out["n"] == len(cases.MULTI_SOURCE_GATHER_CASES)
    assert not out["errors"], out["errors"]
    assert any("DẤU-VÂN-TAY-GATHER" in s for s in seen_fuse_inputs), (
        "erp_facts của gather_erp phải đi vào render_fuse_input")
    for f in out["fails"]:
        assert "called" in f, (
            "mỗi bản ghi fail phải kèm `called` — không có nó thì không phân "
            "biệt được 'chọn sai tool' với 'tổng hợp kém'")


def test_registered_in_eval_gate():
    from jobs import eval_gate
    assert eval_gate.EVAL_FN["multi_source_gather"] is run_eval.eval_multi_source_gather
    assert eval_gate.ROLE_FOR_SET["multi_source_gather"] == "fusion"


def test_no_baseline_and_gate_always_passes():
    """Chưa có baseline (set ra đời 2026-08-04, không model cũ nào từng đo)
    — GÁC NHẸ y như `gather`: chỉ ghi nhận."""
    from jobs import eval_gate
    assert "multi_source_gather" not in eval_gate.BASELINES
    assert eval_gate._gate("multi_source_gather",
                           {"both_source_coverage": 0.0,
                            "citation_validity": 0.0,
                            "fabricated_number": 9}, None) is True
    assert eval_gate._gate("multi_source_gather",
                           {"both_source_coverage": 1.0,
                            "citation_validity": 1.0,
                            "fabricated_number": 0}, None) is True


def test_excluded_from_set_all_but_selectable():
    """Trong `all` sẽ luôn PASS giả và làm loãng tín hiệu job hàng đêm —
    cùng lý do `gather`/`sop_select` bị loại."""
    import argparse
    from jobs import eval_gate
    p = argparse.ArgumentParser()
    eval_gate.add_args(p)
    assert p.parse_args(["--set", "multi_source_gather"]).set == "multi_source_gather"
    sets = [s for s in eval_gate.EVAL_FN
            if s not in ("sop_select", "gather", "multi_source_gather")]
    assert "multi_source_gather" not in sets
    assert "multi_source" in sets  # sanity: loại trừ không quá tay
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/jobs/test_eval_multi_source_gather.py -q`
Expected: FAIL — `AttributeError: module 'evals.run_eval' has no attribute 'eval_multi_source_gather'`

- [ ] **Step 3: Thêm `MULTI_SOURCE_GATHER_CASES` vào import của `run_eval.py`**

Sửa khối import dòng 19-23 thành:

```python
from evals.cases import (CHITCHAT_CASES, CONFIRM_CASES, GATHER_CASES,
                         HALLUCINATION_MARKERS, INTENT_CASES,
                         MULTI_SOURCE_CASES, MULTI_SOURCE_DERIVED_DIGITS,
                         MULTI_SOURCE_GATHER_CASES,
                         PLANNER_CASES, READ_CASES, SOP_SELECT_CASES,
                         SYNTHESIS_CASES, WRITE_TOOL_NAMES)
```

- [ ] **Step 4: Thêm `eval_multi_source_gather` ngay sau `eval_multi_source`**

```python
async def eval_multi_source_gather(llm, pace: float = 0.0, checkpoint_path=None):
    """Đo TOÀN CHUỖI nhánh mixed: gather_erp THẬT (make_gather_erp_node trên
    tool giả lập từ tool_fixtures) → fuse_answer, trên CÙNG bộ câu
    hỏi/doc_fact/erp_fact của multi_source.

    Khác eval_multi_source ở ĐÚNG một biến: erp_facts do node thật tự đi
    lấy, thay vì erp_block viết tay nạp sẵn. Nhờ vậy set này đo được thứ
    multi_source mù về mặt kiến trúc — năng lực THU THẬP ERP — mà vẫn dùng
    chung thước đo (_score_fusion) nên hai bộ số so sánh được.

    KHÔNG GATE (spec 2026-08-04 §3): chưa có baseline, _gate() trả True vô
    điều kiện, và set bị loại khỏi `--set all`. Số liệu vào báo cáo để người
    đọc tự đánh giá.

    Tool giả lập chứ không phải Odoo thật — cùng kỷ luật eval_gather: đo
    phải lặp lại được. Chẩn đoán khi viết spec cho thấy đúng rủi ro của lựa
    chọn ngược lại: đơn S00042 (mốc tham chiếu của 3 plan trước) nay ở trạng
    thái draft với mọi field ngày rỗng, nên đo trên Odoo thật sẽ trôi theo
    dữ liệu demo chứ không theo chất lượng model.
    """
    lat: list[float] = []

    async def call(case):
        topic, tool_fixtures, question, doc_fact, erp_fact = case
        called: list = []
        tools = _stub_erp_tools(tool_fixtures, called)
        node = make_gather_erp_node(llm, tools)
        chunks = fixtures.load_chunks(topic)

        async def _chain():
            out = await node({"messages": [HumanMessage(content=question)]})
            erp_facts = out.get("erp_facts") or ""
            resp = await llm.ainvoke([
                SystemMessage(content=FUSE_PROMPT),
                HumanMessage(content=render_fuse_input(chunks, erp_facts,
                                                       question)),
            ])
            return erp_facts, resp

        # Đo THỜI GIAN CẢ CHUỖI (gather + fuse) — latency của set này không
        # so trực tiếp được với multi_source (chỉ đo fuse), có chủ đích.
        (erp_facts, resp), ms = await _timed(_chain())
        lat.append(ms)
        body = (resp.content or "").strip()
        score = _score_fusion(body, chunks, "\n".join(tool_fixtures.values()),
                              doc_fact, erp_fact, topic, question,
                              allowed_extra_text=question)
        if score["both"] and score["citation_ok"] and not score["fabricated"]:
            return None
        return {"topic": topic, "question": question, "called": called,
                "erp_facts": erp_facts[:300], "response": body[:300], **score}

    fails, errors = await run_resilient(MULTI_SOURCE_GATHER_CASES, call,
                                        pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(MULTI_SOURCE_GATHER_CASES)
    measured = n - len(errors)
    # CHỈ đếm từ fails — lỗi API không bao giờ là trích dẫn sai / số bịa
    bad_cite = sum(1 for f in fails if not f["citation_ok"])
    no_both = sum(1 for f in fails if not f["both"])
    fabricated_number = sum(1 for f in fails if f["fabricated"])
    p50, p95 = _percentiles(lat)
    return {"set": "multi_source_gather", "n": n,
            "both_source_coverage": (measured - no_both) / n if n else 0.0,
            "citation_validity": (measured - bad_cite) / n if n else 0.0,
            "fabricated_number": fabricated_number,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}
```

- [ ] **Step 5: Đăng ký set trong `jobs/eval_gate.py`**

(a) `ROLE_FOR_SET` — thêm sau dòng `"multi_source": "fusion", "sop_select": "router",`:

```python
                # gather_erp và fuse_answer đều dùng role "fusion" — set này
                # chạy CẢ HAI nên vẫn đúng một role.
                "multi_source_gather": "fusion",
```

(b) `EVAL_FN` — thêm entry:

```python
           "multi_source_gather": run_eval.eval_multi_source_gather,
```

(c) `_gate()` — chèn NGAY SAU khối `if set_name == "multi_source": ... return (...)`:

```python
    if set_name == "multi_source_gather":
        # Chưa có baseline: set này ra đời 2026-08-04, không model cũ nào
        # từng đo qua đường gather_erp thật. GÁC NHẸ y hệt `gather` — mọi
        # lần chạy PASS, số vào báo cáo để người đọc tự đánh giá, không phải
        # job tự đánh giá thay. Siết thành ngưỡng thật khi đủ số đo.
        return True
```

(d) `run()` — dòng 112, thay:

```python
        sets = [s for s in EVAL_FN
                if s not in ("sop_select", "gather", "multi_source_gather")]
```

và thêm vào khối comment ngay trên đó:

```python
        # multi_source_gather CŨNG bị loại, cùng lý do với gather: gate trả
        # True vô điều kiện nên để trong "all" chỉ tạo PASS giả.
```

(e) `run()` — nhánh báo cáo `base is None`: chèn thêm một `elif` NGAY SAU
khối `elif set_name == "gather":` và TRƯỚC `else:  # chitchat`:

```python
            elif set_name == "multi_source_gather":
                entry.update(
                    both_source_coverage=result.get("both_source_coverage"),
                    citation_validity=result.get("citation_validity"),
                    fabricated_number=result.get("fabricated_number"),
                    lat_p50=result.get("lat_p50"),
                    lat_p95=result.get("lat_p95"))
                print(f"[{set_name}] model={model} pace={pace}s "
                      f"both_source_coverage="
                      f"{result.get('both_source_coverage'):.3f} "
                      f"citation_validity={result.get('citation_validity'):.3f} "
                      f"fabricated_number={result.get('fabricated_number')} "
                      f"→ {'PASS' if ok else 'FAIL'}")
```

Đồng thời sửa comment mô tả nhánh `base is None` (dòng 183-185) thành:

```python
            # base is None: chitchat (violations), sop_select (acc + hijack),
            # gather (tool_recall + fact_coverage), hoặc multi_source_gather
            # (both_source_coverage + citation_validity) — không set nào có
            # ngưỡng tuyệt đối, xem _gate()
```

(f) `add_args()` — thêm `"multi_source_gather"` vào `choices`:

```python
                   choices=["both", "all", "intent", "confirm", "chitchat",
                            "planner", "read", "synthesis", "multi_source",
                            "multi_source_gather", "sop_select", "gather"],
```

- [ ] **Step 6: Chạy test — phải PASS**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/jobs/ -q`
Expected: PASS toàn bộ.

- [ ] **Step 7: Commit**

```bash
git add backend/evals/run_eval.py backend/jobs/eval_gate.py backend/tests/jobs/test_eval_multi_source_gather.py
git commit -m "feat(eval): eval_multi_source_gather — gather_erp thật nối vào fuse_answer, đăng ký set không gate"
```

---

### Task 4: Mở rộng contract test + đo thật

**Files:**
- Modify: `backend/tests/jobs/test_eval_gather.py:262-419`
- Test: chính file đó
- Create: `docs/superpowers/plans/2026-08-04-multi-source-gather-eval-report.md`

**Interfaces:**
- Consumes: `cases.MULTI_SOURCE_GATHER_CASES` (Task 2);
  `run_eval.eval_multi_source_gather` (Task 3).
- Produces: không có API mới — chỉ mở rộng phạm vi test hiện có.

- [ ] **Step 1: Viết test canh cho danh sách MỚI (chạy trước, phải FAIL)**

Thêm vào cuối `backend/tests/jobs/test_eval_gather.py`:

```python
def test_contract_test_covers_multi_source_gather_cases():
    """Contract test phải quét CẢ MULTI_SOURCE_GATHER_CASES, không chỉ
    GATHER_CASES — nếu không, danh sách case mới (viết tay, cùng rủi ro y
    hệt) không được canh gì cả."""
    seen = {set_name for set_name, _topic, _fx in _all_fixture_cases()}
    assert seen == {"GATHER_CASES", "MULTI_SOURCE_GATHER_CASES"}


def test_new_tools_have_real_field_probes():
    """Mọi tool xuất hiện trong fixture của CẢ HAI danh sách phải có nhánh
    trong _real_fields_for_tool — hàm raise KeyError cho tool lạ (cố ý), nên
    test này biến lỗi-lúc-chạy thành lỗi-lúc-test."""
    for _set_name, _topic, tool_fixtures in _all_fixture_cases():
        for tool_name in tool_fixtures:
            _real_fields_for_tool(tool_name)  # không raise là đạt


def test_invoice_date_labels_map_to_real_fields():
    """2 nhãn mới (spec §6): nhãn hóa đơn phải ứng field thật của
    list_invoices/get_overdue_invoices (dùng chung accounting._FIELDS)."""
    assert _DATE_STATUS_LABELS["ngày hóa đơn"] == ("invoice_date",)
    assert _DATE_STATUS_LABELS["đến hạn"] == ("invoice_date_due",)
    for tool in ("list_invoices", "get_overdue_invoices"):
        real = _real_fields_for_tool(tool)
        assert "invoice_date" in real and "invoice_date_due" in real


def test_delivery_status_label_is_no_longer_dead_config():
    """Nhãn "trạng thái giao" nằm trong _DATE_STATUS_LABELS từ plan trước
    nhưng chưa fixture nào chạm tới (đã ghi nhận là cấu hình chết, hoãn
    lại). MULTI_SOURCE_GATHER_CASES dùng nó thật — chốt lại để nó không âm
    thầm chết trở lại."""
    corpus = " ".join(
        text for _s, _t, fx in _all_fixture_cases() for text in fx.values())
    assert "trạng thái giao" in corpus.casefold()
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -q`
Expected: FAIL — `NameError: name '_all_fixture_cases' is not defined`

- [ ] **Step 3: Thêm dòng mẫu `stock.picking` vào `_REPRESENTATIVE_ROWS`**

Thêm entry vào dict (dòng 262-275):

```python
    "stock.picking": {"id": 1, "name": "WH/OUT/0001",
                      "partner_id": [1, "Khách mẫu"],
                      # PHẢI là chuỗi: formatter thật cắt scheduled_date[:10]
                      "scheduled_date": "2026-01-01 00:00:00",
                      "state": "assigned"},
```

- [ ] **Step 4: Thêm 2 nhánh vào `_real_fields_for_tool`**

Sửa dòng import trong hàm thành:

```python
    from src.erp_query import sales, accounting, inventory
```

và chèn 2 nhánh NGAY SAU nhánh `get_product_price`:

```python
    elif tool_name == "list_invoices":
        accounting.list_invoices("out_invoice", gw=gw)
    elif tool_name == "list_late_deliveries":
        inventory.list_late_deliveries(gw=gw)
```

- [ ] **Step 5: Thêm 2 nhãn vào `_DATE_STATUS_LABELS`**

```python
_DATE_STATUS_LABELS = {
    "ngày xác nhận": ("date_order",),
    "ngày giao dự kiến": ("commitment_date",),
    "ngày giao thực tế": ("effective_date", "date_done"),
    "trạng thái giao": ("delivery_status",),
    # 2 nhãn hóa đơn (2026-08-04): accounting._FIELDS dùng chung cho
    # list_invoices và get_overdue_invoices. "đến hạn" phủ luôn fixture
    # get_overdue_invoices sẵn có trong GATHER_CASES — trước đó không nhãn
    # nào chạm tới nó.
    "ngày hóa đơn": ("invoice_date",),
    "đến hạn": ("invoice_date_due",),
}
```

- [ ] **Step 6: Thêm `_all_fixture_cases()` và đổi `_KNOWN_GAPS` sang khoá 4-tuple**

Chèn ngay sau `_DATE_STATUS_LABELS`:

```python
def _all_fixture_cases():
    """(set_name, topic, tool_fixtures) của MỌI danh sách case có
    tool_fixtures. Hai danh sách khác hình dạng tuple — chuẩn hoá ở đúng
    MỘT chỗ để contract test không phải biết hình dạng nào cả."""
    for topic, _question, _rt, _rf, tool_fixtures in cases.GATHER_CASES:
        yield ("GATHER_CASES", topic, tool_fixtures)
    for topic, tool_fixtures, _question, _doc, _erp in cases.MULTI_SOURCE_GATHER_CASES:
        yield ("MULTI_SOURCE_GATHER_CASES", topic, tool_fixtures)
```

Đổi khai báo `_KNOWN_GAPS` (dòng 330) thành 4-tuple và bổ sung lý do:

```python
_KNOWN_GAPS: set[tuple[str, str, str, str]] = set()
# Khoá: (set_name, topic, tool_name, label). Thêm set_name ở 2026-08-04 vì
# topic TRÙNG NHAU giữa hai danh sách (sla_giao_hang có ở cả hai) — khoá
# 3-tuple cũ sẽ nhập nhằng. Không cần migration: set đang RỖNG.
```

(giữ nguyên toàn bộ khối comment lịch sử phía dưới)

- [ ] **Step 7: Đổi test chính sang quét cả hai danh sách**

Đổi tên `test_gather_cases_fixture_labels_match_real_tool_fields` thành
`test_fixture_labels_match_real_tool_fields` và thay vòng lặp ngoài:

```python
def test_fixture_labels_match_real_tool_fields():
    """Đối chiếu fixture với field THẬT tool trả về — chặn lớp lỗi "fixture
    khẳng định khả năng tool không có" (đã gặp 4 lần: gather-erp-tool-fix,
    sale-order-detail-dates, và 2 lần trong chính hạ tầng test này). Quét CẢ
    GATHER_CASES lẫn MULTI_SOURCE_GATHER_CASES (mở rộng 2026-08-04) — danh
    sách sau cũng viết tay, cùng rủi ro y hệt.

    Mục trong _KNOWN_GAPS VẪN được kiểm field thật: nếu field thật ĐÃ CÓ
    (gap đã sửa), đó là lỗi đòi xoá mục, không phải được bỏ qua âm thầm."""
    used = set()
    for set_name, topic, tool_fixtures in _all_fixture_cases():
        for tool_name, fixture_text in tool_fixtures.items():
            real_fields = _real_fields_for_tool(tool_name)
            low = fixture_text.casefold()
            for label, field_names in _DATE_STATUS_LABELS.items():
                if label not in low:
                    continue
                key = (set_name, topic, tool_name, label)
                ok = bool(set(field_names) & real_fields)
                if key in _KNOWN_GAPS:
                    used.add(key)
                    assert not ok, (
                        f"_KNOWN_GAPS có mục KHÔNG CÒN CẦN THIẾT: {set_name} "
                        f"case {topic}, tool {tool_name!r}, nhãn {label!r} — "
                        f"field thật đã có "
                        f"({sorted(set(field_names) & real_fields)}), xoá "
                        f"mục này khỏi _KNOWN_GAPS.")
                    continue
                assert ok, (
                    f"{set_name} case {topic}: fixture của tool {tool_name!r} "
                    f"dùng nhãn {label!r} nhưng tool không có field thật nào "
                    f"trong {field_names} (field thật: {sorted(real_fields)})")
    assert used == _KNOWN_GAPS, (
        f"_KNOWN_GAPS có mục không còn ứng với vi phạm thật (gap đã lấp "
        f"hoặc fixture đã đổi chữ): {sorted(_KNOWN_GAPS - used)} — xoá mục "
        f"đó khỏi _KNOWN_GAPS, đừng để nó nằm lại như cấu hình chết.")
```

- [ ] **Step 8: Cập nhật test canh `_KNOWN_GAPS` sang khoá 4-tuple**

Trong `test_known_gaps_catches_entry_when_real_field_now_exists`, đổi:

```python
    fake_known_gaps = {("GATHER_CASES", "sla_giao_hang",
                        "get_sale_order_detail", "ngày giao dự kiến")}
```

và đổi lời gọi cuối hàm thành tên mới:

```python
    with _pytest.raises(AssertionError, match="KHÔNG CÒN CẦN THIẾT"):
        test_fixture_labels_match_real_tool_fields()
```

- [ ] **Step 9: Chạy toàn bộ test — phải PASS**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q`
Expected: PASS toàn bộ (chế độ unit-only mặc định).

- [ ] **Step 10: Kiểm nghiệm thật rằng contract test CÓ TÁC DỤNG (removal probe)**

Kỹ thuật này đã bắt được một lỗi thật mà đọc mã 2 vòng không thấy (plan
`sale-order-effective-dates`, 2026-08-02) — không bỏ qua bước này.

Tạo file tạm `backend/_probe_contract.py`:

```python
"""Removal probe: gỡ từng field khỏi tập field THẬT rồi xác nhận contract
test FAIL. Test nào không fail nghĩa là nhãn đó đang không được bảo vệ."""
import pytest
import tests.jobs.test_eval_gather as T

PROBES = [
    ("get_sale_order_detail", "commitment_date"),
    ("get_sale_order_detail", "effective_date"),
    ("get_sale_order_detail", "date_order"),
    ("get_sale_order_detail", "delivery_status"),
    ("list_invoices", "invoice_date"),
    ("list_invoices", "invoice_date_due"),
    ("get_overdue_invoices", "invoice_date_due"),
]
orig = T._real_fields_for_tool
for tool, field in PROBES:
    def fake(name, _tool=tool, _field=field):
        out = orig(name)
        return out - {_field} if name == _tool else out
    T._real_fields_for_tool = fake
    try:
        T.test_fixture_labels_match_real_tool_fields()
        print(f"KHÔNG BẢO VỆ: gỡ {tool}.{field} mà test vẫn PASS")
    except AssertionError:
        print(f"ok: gỡ {tool}.{field} → test FAIL đúng như kỳ vọng")
    finally:
        T._real_fields_for_tool = orig
```

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe _probe_contract.py`
Expected: **cả 7 dòng đều bắt đầu bằng `ok:`**. Bất kỳ dòng `KHÔNG BẢO VỆ`
nào là lỗi thật phải báo cáo và sửa trước khi đi tiếp — ghi nguyên văn đầu
ra vào report ở Step 12.

Xoá file tạm sau khi chạy: `rm backend/_probe_contract.py`

- [ ] **Step 11: Đo thật hai set**

Cần Postgres `youdoo` đang chạy. Chạy lần lượt (bash):

```bash
cd D:/Youdoo/backend && set -a && source ../.env && set +a && \
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set multi_source
```

Expected: `both_source_coverage=0.750 baseline=0.750 → PASS` — **giữ nguyên
số cũ là tiêu chí đậu của Task 1** (refactor không đổi hành vi). Nếu lệch,
DỪNG và báo cáo.

```bash
cd D:/Youdoo/backend && set -a && source ../.env && set +a && \
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set multi_source_gather
```

Expected: chạy trọn 8 ca, in `both_source_coverage=... citation_validity=...
fabricated_number=... → PASS`. **Con số THẤP HƠN multi_source là kết quả
được dự đoán trước, KHÔNG phải hồi quy** — spec §2 đã chẩn đoán rằng 2 ca
fail còn lại của multi_source có nguyên nhân ngoài phạm vi mọi bản sửa đã
làm. Ghi số đo và đường dẫn file log JSON.

- [ ] **Step 12: Viết report**

Tạo `docs/superpowers/plans/2026-08-04-multi-source-gather-eval-report.md` gồm:
số đo cả hai set (kèm đường dẫn `logs/jobs/eval-gate-*.json`); với MỖI ca
fail của set mới, bảng `topic | called | erp_facts (rút gọn) | both |
citation_ok | fabricated` và một câu quy nguyên nhân về "chọn sai tool" hay
"tổng hợp kém"; đầu ra nguyên văn của removal probe (Step 10); danh sách
những gì CỐ Ý không sửa (fixture `get_product_price` của `GATHER_CASES`, spec §7).

- [ ] **Step 13: Commit**

```bash
git add backend/tests/jobs/test_eval_gather.py docs/superpowers/plans/2026-08-04-multi-source-gather-eval-report.md
git commit -m "test(eval): contract test quét cả MULTI_SOURCE_GATHER_CASES + 2 nhãn hóa đơn, kèm số đo thật"
```

---

## Self-Review

**Spec coverage:**

| Mục spec | Task |
|---|---|
| §3 set mới không gate, loại khỏi `all` | Task 3 Step 5(c)(d)(f) |
| §4 hình dạng + phản chiếu 1-1 | Task 2 Step 3, test ở Step 1 |
| §4.1 kỷ luật fixture | Task 2 Step 3 (comment) + Task 4 (contract test) |
| §4.2 khác biệt có chủ đích, ghi rõ | Task 2 Step 3 (comment ca INV/2026/00020) |
| §5 `_score_fusion` + basis + `allowed_extra_text` | Task 1 toàn bộ, Task 3 Step 4 |
| §5 `called` trong fails | Task 3 Step 4, test ở Step 1 |
| §6.1 khoá 4-tuple | Task 4 Step 6 + Step 8 |
| §6.2 nhánh `_real_fields_for_tool` + `stock.picking` | Task 4 Step 3-4 |
| §6.3 hai nhãn mới | Task 4 Step 5 |
| §6 phụ lợi "trạng thái giao" hết chết | Task 4 Step 1 (test chốt) |
| §7 phát hiện phụ, không sửa | Task 2 Step 6 (comment cảnh báo) |
| §8 dọn 2 comment lỗi thời | Task 2 Step 5 |
| §10 tiêu chí hoàn thành | Task 4 Step 9-12 |

**Type consistency:** `_score_fusion(body, chunks, erp_text, doc_fact,
erp_fact, topic, question, allowed_extra_text="")` — Task 1 định nghĩa, Task
1 Step 4 và Task 3 Step 4 gọi, cùng thứ tự tham số. `MULTI_SOURCE_GATHER_CASES`
hình dạng `(topic, tool_fixtures, question, doc_fact, erp_fact)` — Task 2 tạo,
Task 3 và Task 4 giải nén đúng thứ tự đó. `_all_fixture_cases()` trả
`(set_name, topic, tool_fixtures)` — Task 4 tạo và dùng ở 4 chỗ, khớp.
