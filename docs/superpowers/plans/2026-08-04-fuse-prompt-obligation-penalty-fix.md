# Sửa `FUSE_PROMPT` — đối chiếu đủ cặp nghĩa vụ + hậu quả/mức phạt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm đúng 1 quy tắc vào `FUSE_PROMPT` (`backend/src/agents/prompts.py`)
để sửa lỗi "tổng hợp kém" đã đo được (100% lặp lại, 8/8) ở ca
`sla_giao_hang`/`WH/OUT/00001` của set eval `multi_source_gather`, mà
KHÔNG làm lùi set đang gác thật `multi_source`.

**Architecture:** Thêm 1 dòng bullet vào cuối khối "Quy tắc:" của
`FUSE_PROMPT` — quy tắc đã được ĐO THẬT (không phải suy đoán) trên cả 8 ca
`MULTI_SOURCE_GATHER_CASES`, cho kết quả 6/8 → 7/8, KHÔNG hồi quy ca nào.
Nội dung dòng mới phải chép ĐÚNG NGUYÊN VĂN từ spec — đây là văn bản đã
qua thực nghiệm, không phải chỗ để diễn giải lại.

**Tech Stack:** Python 3.12, pytest, LangChain, `evals/run_eval.py`,
`jobs/eval_gate.py`.

**Spec:** `docs/superpowers/specs/2026-08-04-fuse-prompt-obligation-penalty-fix-design.md`

## Global Constraints

- `FUSE_PROMPT` là prompt SẢN XUẤT thật (`make_fuse_answer_node` dùng cho
  MỌI câu hỏi nhánh `mixed`), không phải fixture/test — sửa sai ảnh hưởng
  người dùng thật, không chỉ điểm eval.
- **`multi_source` KHÔNG được lùi.** Set này đang GÁC thật (`_gate()` yêu
  cầu `citation_validity == 1.0`, `fabricated_number == 0`,
  `both_source_coverage >= baseline`). Nếu đo thật sau khi sửa cho kết quả
  lùi, DỪNG và báo cáo — không tự ý coi là chấp nhận được.
- Dòng quy tắc mới PHẢI khớp nguyên văn nội dung đã đo thật ở spec §3:
  `"- Với câu hỏi về việc có TUÂN THỦ/VI PHẠM một điều khoản hay không (SLA, thời hạn, chính sách): nếu TÀI LIỆU có một đoạn nêu NGHĨA VỤ/THỜI HẠN và một đoạn KHÁC nêu HẬU QUẢ/MỨC PHẠT khi vi phạm, hãy dùng CẢ HAI — xác định trước có vi phạm nghĩa vụ hay không, rồi nêu hậu quả/mức phạt tương ứng nếu có vi phạm."`
  — một dòng dài, KHÔNG xuống dòng giữa chừng, đúng văn phong các bullet
  khác trong `FUSE_PROMPT`.
- `S00042` (ca fail còn lại của `multi_source_gather`) CỐ Ý KHÔNG nằm
  trong phạm vi plan này — nguyên nhân khác (thiếu field "khẩn cấp" trong
  dữ liệu ERP, xem spec §5). KHÔNG cố sửa nó bằng cách nới rộng quy tắc
  prompt thêm nữa — đã thử và bị bác bỏ ở spec §2 (Variant A gây hồi quy
  thật).
- Chạy test: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest <path> -q`
- Chạy eval thật cần env: `set -a && source ../.env && set +a` trước khi
  gọi `-m jobs run eval-gate` (bash), và Postgres `youdoo` + Odoo (cho
  `verify_erp_grounding`/tool thật nếu có) phải đang chạy. Model role
  `fusion` = `gemini-3.1-flash-lite`, rpm=15 → pace 4.8s/lượt gọi
  (`(60/15)*1.2`).
- Comment/docstring trong repo này viết tiếng Việt — giữ đúng văn phong
  file đang sửa.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/src/agents/prompts.py` | Thêm 1 dòng quy tắc vào hằng số `FUSE_PROMPT` |
| `backend/tests/agents/test_prompts.py` | Test chốt substring quy tắc mới có trong `FUSE_PROMPT` |
| `docs/superpowers/plans/2026-08-04-fuse-prompt-obligation-penalty-fix-report.md` (mới) | Report đo thật: N=5 lặp lại ca WH/OUT/00001, `--set multi_source` (không lùi), `--set multi_source_gather` (kỳ vọng 7/8) |

---

### Task 1: Thêm quy tắc vào `FUSE_PROMPT` + test chốt

**Files:**
- Modify: `backend/src/agents/prompts.py:158-168` (`FUSE_PROMPT`)
- Test: `backend/tests/agents/test_prompts.py`

**Interfaces:** Không đổi. `FUSE_PROMPT` vẫn là `str`, vẫn kết thúc bằng
`/no_think`, vẫn được `make_fuse_answer_node`/`evals.run_eval` import y
hệt cũ.

- [ ] **Step 1: Viết test chốt (chạy TRƯỚC khi sửa — phải FAIL)**

Thêm vào cuối `backend/tests/agents/test_prompts.py`:

```python
def test_fuse_prompt_has_obligation_penalty_rule():
    """Quy tắc mới (plan 2026-08-04-fuse-prompt-obligation-penalty-fix):
    đối chiếu đủ cặp nghĩa vụ/thời hạn + hậu quả/mức phạt cho câu hỏi
    tuân thủ/vi phạm — đo thật trên 8 ca multi_source_gather trước khi
    thêm, xem spec §2. Chốt cứng để không bị xoá nhầm khi ai đó dọn
    FUSE_PROMPT sau này."""
    from src.agents.prompts import FUSE_PROMPT
    assert ("một đoạn nêu NGHĨA VỤ/THỜI HẠN và một đoạn KHÁC nêu HẬU QUẢ/"
            "MỨC PHẠT khi vi phạm") in FUSE_PROMPT
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_prompts.py::test_fuse_prompt_has_obligation_penalty_rule -v`
Expected: FAIL — `AssertionError`.

- [ ] **Step 3: Thêm dòng quy tắc vào `FUSE_PROMPT`**

Trong `backend/src/agents/prompts.py`, tìm khối `FUSE_PROMPT` (hiện dòng
158-168). Tìm dòng:

```
- Trả lời tự nhiên, thân thiện, ngắn gọn bằng tiếng Việt.
```

Thay bằng (thêm 1 dòng MỚI ngay TRƯỚC, giữ nguyên dòng cũ):

```
- Với câu hỏi về việc có TUÂN THỦ/VI PHẠM một điều khoản hay không (SLA, thời hạn, chính sách): nếu TÀI LIỆU có một đoạn nêu NGHĨA VỤ/THỜI HẠN và một đoạn KHÁC nêu HẬU QUẢ/MỨC PHẠT khi vi phạm, hãy dùng CẢ HAI — xác định trước có vi phạm nghĩa vụ hay không, rồi nêu hậu quả/mức phạt tương ứng nếu có vi phạm.
- Trả lời tự nhiên, thân thiện, ngắn gọn bằng tiếng Việt.
```

**Chép đúng nguyên văn dòng mới — đây là câu đã qua đo thật (spec §2/§3),
không diễn giải lại, không rút gọn.** Không đổi bất kỳ dòng nào khác của
`FUSE_PROMPT` (đầu prompt, các bullet khác, đoạn `NGUỒN_DÙNG`, hay
`/no_think` ở cuối).

- [ ] **Step 4: Chạy lại test — phải PASS**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_prompts.py::test_fuse_prompt_has_obligation_penalty_rule -v`
Expected: PASS.

- [ ] **Step 5: Xác nhận không vỡ test hiện có phụ thuộc `FUSE_PROMPT`**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_prompts.py tests/agents/test_fanout.py -q`
Expected: PASS toàn bộ — đặc biệt các test đã có từ trước:
`FUSE_PROMPT.rstrip().endswith("/no_think")` và
`captured["system"] == FUSE_PROMPT` (test_fanout.py) phải vẫn đúng vì chỉ
thêm 1 dòng ở giữa, không đụng đầu/cuối chuỗi.

- [ ] **Step 6: Chạy toàn bộ suite unit-only — phải PASS**

Run: `cd D:/Youdoo/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"`
Expected: PASS toàn bộ, số lượng khớp baseline đã biết trước khi bắt đầu
(ghi lại số PASS ở bước đầu tiên của phiên làm việc để đối chiếu).

- [ ] **Step 7: Commit**

```bash
git add backend/src/agents/prompts.py backend/tests/agents/test_prompts.py
git commit -m "fix(agents): FUSE_PROMPT đối chiếu đủ cặp nghĩa vụ+hậu quả cho câu hỏi tuân thủ/vi phạm"
```

---

### Task 2: Đo thật — lặp lại + `multi_source` (không lùi) + `multi_source_gather`

**Files:**
- Create: `docs/superpowers/plans/2026-08-04-fuse-prompt-obligation-penalty-fix-report.md`
- Test: không có test mới — đây là task ĐO, không phải task code.

**Interfaces:** Không có API mới. Dùng nguyên `evals.run_eval.eval_multi_source`,
`evals.run_eval.eval_multi_source_gather`, `jobs.eval_gate`.

- [ ] **Step 1: Ghi lại baseline TRƯỚC khi đo (đối chiếu môi trường)**

Xác nhận hạ tầng: `docker ps` có `youdoo-postgres` (healthy); Odoo phản
hồi ở `http://localhost:8069`. Nếu thiếu, DỪNG và báo BLOCKED — không đo
giả.

- [ ] **Step 2: Đo lặp lại N=5 lần đúng ca WH/OUT/00001 (fix có ổn định không)**

Bug gốc đã xác nhận lặp lại 100% (8/8, spec §1) — fix cũng cần kiểm tra
tương tự, không dừng ở 1 lần PASS.

Tạo file tạm `backend/_probe_fix_repeat.py`:

```python
"""Kiểm tra fix (Task 1 đã commit) LẶP LẠI được — chạy đúng ca WH/OUT/00001
N=5 lần qua production path thật. File tạm, xoá sau khi lấy kết quả."""
import asyncio

from langchain_core.messages import HumanMessage, SystemMessage

from evals import fixtures
from evals.cases import MULTI_SOURCE_GATHER_CASES
from evals.run_eval import _llm, _score_fusion, _stub_erp_tools
from src.agents.fanout import make_gather_erp_node, render_fuse_input
from src.agents.prompts import FUSE_PROMPT
from src.llm.catalog import chain_for

N = 5
PACE_S = 4.8

CASE = next(c for c in MULTI_SOURCE_GATHER_CASES
            if c[0] == "sla_giao_hang" and "WH/OUT/00001" in c[2])
topic, tool_fixtures, question, doc_fact, erp_fact = CASE
chunks = fixtures.load_chunks(topic)

role = "fusion"
llm = _llm(chain_for(role)[0].alias, role)


async def one_run(rep: int) -> bool:
    called: list = []
    tools = _stub_erp_tools(tool_fixtures, called)
    node = make_gather_erp_node(llm, tools)
    out = await node({"messages": [HumanMessage(content=question)]})
    erp_facts = out.get("erp_facts") or ""
    resp = await llm.ainvoke([
        SystemMessage(content=FUSE_PROMPT),
        HumanMessage(content=render_fuse_input(chunks, erp_facts, question)),
    ])
    body = (resp.content or "").strip()
    score = _score_fusion(body, chunks, "\n".join(tool_fixtures.values()),
                          doc_fact, erp_fact, topic, question,
                          allowed_extra_text=question)
    ok = score["both"] and score["citation_ok"] and not score["fabricated"]
    print(f"rep {rep}: {'PASS' if ok else 'FAIL'} "
          f"both={score['both']} citation_ok={score['citation_ok']} "
          f"fabricated={score['fabricated']}")
    if not ok:
        print(f"  response: {body[:400]}")
    return ok


async def main():
    results = []
    for rep in range(1, N + 1):
        results.append(await one_run(rep))
        if rep < N:
            await asyncio.sleep(PACE_S)
    print(f"=== {sum(results)}/{N} PASS ===")


asyncio.run(main())
```

Run: `cd D:/Youdoo/backend && set -a && source ../.env && set +a && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe _probe_fix_repeat.py`
Expected: **5/5 PASS**. Nếu có lần FAIL, DỪNG — ghi nguyên văn kết quả vào
report (đừng coi là "chắc do may rủi", đây đúng câu hỏi mà bước này tồn
tại để trả lời) và báo cáo thay vì tiếp tục các bước sau.

Xoá file tạm sau khi lấy kết quả: `rm backend/_probe_fix_repeat.py`. Xác
nhận `git status --short` không còn file này trước khi qua Step 3.

- [ ] **Step 3: Đo thật `--set multi_source` — xác nhận KHÔNG lùi**

```bash
cd D:/Youdoo/backend && set -a && source ../.env && set +a && \
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set multi_source
```

Expected: gate PASS, `both_source_coverage` KHÔNG thấp hơn baseline hiện
có (giá trị baseline in ra cùng dòng kết quả). Ghi số đo + đường dẫn log
JSON vào report. **Nếu lùi: DỪNG, không tự ý coi 1 điểm số thấp hơn là
"chấp nhận được" — đây là ràng buộc cứng của Global Constraints.**

- [ ] **Step 4: Đo thật `--set multi_source_gather`**

```bash
cd D:/Youdoo/backend && set -a && source ../.env && set +a && \
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set multi_source_gather
```

Expected: `both_source_coverage` = 0.875 (7/8) — khớp thực nghiệm ở spec
§2. Ca fail còn lại phải là `S00042` (không phải ca nào khác — nếu có ca
KHÁC fail mới xuất hiện, đó là hồi quy thật, DỪNG và báo cáo). Ghi số đo
chi tiết (bảng per-fail-case như report của plan `multi-source-gather-eval`
trước) + đường dẫn log JSON vào report.

- [ ] **Step 5: Viết report**

Tạo `docs/superpowers/plans/2026-08-04-fuse-prompt-obligation-penalty-fix-report.md`
gồm: kết quả N=5 lặp lại (Step 2, nguyên văn cả 5 lần); số đo
`--set multi_source` trước/sau (Step 3, xác nhận không lùi); số đo
`--set multi_source_gather` (Step 4, bảng ca fail còn lại `S00042` + lý do
đã biết từ spec §5, KHÔNG lặp lại toàn văn spec — chỉ dẫn chiếu); kết luận
theo tiêu chí hoàn thành của spec §8.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/plans/2026-08-04-fuse-prompt-obligation-penalty-fix-report.md
git commit -m "test(agents): đo thật FUSE_PROMPT fix — N=5 lặp lại + multi_source không lùi + multi_source_gather 7/8"
```

---

## Self-Review

**Spec coverage:**

| Mục spec | Task |
|---|---|
| §1-2 chẩn đoán + thực nghiệm 2 biến thể (đã làm TRƯỚC khi viết plan, không lặp lại) | — |
| §3 nội dung sửa nguyên văn | Task 1 Step 3 |
| §4 ràng buộc `multi_source` không lùi | Task 2 Step 3 |
| §5 S00042 cố ý ngoài phạm vi | Task 2 Step 4 (xác nhận ca fail còn lại đúng là S00042, không có ca mới) |
| §6 kiểm chứng fix lặp lại (N=5) | Task 2 Step 2 |
| §7 file bị chạm | Task 1 (prompts.py, test_prompts.py), Task 2 (report) |
| §8 tiêu chí hoàn thành | Task 1 Step 4-6, Task 2 Step 2-4 |

**Type consistency:** `FUSE_PROMPT` vẫn là hằng số `str` module-level, không
đổi chữ ký/kiểu dữ liệu nào. Không có hàm mới, không có tham số mới cho bất
kỳ hàm nào trong `run_eval.py`/`fanout.py`/`eval_gate.py`.
