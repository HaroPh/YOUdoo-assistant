# Gán tên "Youdoo" vào `CHITCHAT_PROMPT` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm tên "Youdoo" vào câu đầu tiên của `CHITCHAT_PROMPT`
(`backend/src/agents/prompts.py`) — đóng gap đã đo được qua request thật
tới backend đang chạy: hệ thống chưa từng tự giới thiệu bằng tên thương
hiệu khi được hỏi "bạn là ai".

**Architecture:** Sửa ĐÚNG 1 câu trong prompt sản xuất thật, không đổi bất
kỳ quy tắc/nội dung nào khác của `CHITCHAT_PROMPT`. Xác nhận bằng 2 lớp đo
thật: `eval_chitchat` (set đang gác, `violations` phải giữ 0) và 1 request
thật tới backend live đang chạy.

**Tech Stack:** Python 3.12, pytest, LangChain, `evals/run_eval.py`,
`jobs/eval_gate.py`, FastAPI backend (`backend/run.py`).

**Spec:** `docs/superpowers/specs/2026-08-05-chitchat-brand-identity-fix-design.md`

## Global Constraints

- Sửa ĐÚNG 1 dòng của `CHITCHAT_PROMPT` (dòng đầu tiên) — không đổi danh
  sách năng lực, quy tắc chống bịa hành động, quy tắc không tiết lộ nhà
  cung cấp model, hay giọng văn.
- Nội dung mới: `"Bạn là Youdoo, trợ lý ERP nội bộ, trả lời bằng tiếng Việt với giọng chuyên nghiệp, thân thiện."`
  — chép nguyên văn, không diễn giải lại.
- `eval_chitchat` đang GÁC thật (`violations == 0`, kiểm bằng
  `HALLUCINATION_MARKERS`) — không được hồi quy.
- KHÔNG sửa `SYSTEM_PROMPT`, `FUSE_PROMPT`, `RAG_SYNTHESIS_PROMPT`,
  `GATHER_ERP_PROMPT`, hay bất kỳ prompt nào khác — phạm vi chỉ
  `CHITCHAT_PROMPT`.
- Chạy test: `cd D:/Youdoo/.claude/worktrees/chitchat-brand-identity-fix/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest <path> -q`
  (thay đúng path worktree được cấp cho plan này — KHÔNG phải
  `D:/Youdoo/backend`).
- Chạy eval thật cần env: `set -a && source ../.env && set +a` trước khi
  gọi `-m jobs run eval-gate` (bash), và Postgres `youdoo` phải đang chạy.
- Test backend thật cần: backend FastAPI (`run.py`) đang chạy ở
  `http://localhost:8000` — CHẠY TỪ REPO CHÍNH (`D:/Youdoo/backend`), không
  phải worktree (worktree không có tiến trình backend riêng). Nếu backend
  live không chạy, khởi động nó TỪ REPO CHÍNH trước khi verify Step cuối,
  không phải từ worktree.
- Comment/docstring trong repo này viết tiếng Việt.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/src/agents/prompts.py` | Sửa 1 dòng đầu `CHITCHAT_PROMPT` |
| `backend/tests/agents/test_prompts.py` | Test chốt "Youdoo" có trong `CHITCHAT_PROMPT` |
| `docs/superpowers/plans/2026-08-05-chitchat-brand-identity-fix-report.md` (mới) | Report đo thật `--set chitchat` + request thật tới backend live |

---

### Task 1: Sửa prompt + test + đo thật

**Files:**
- Modify: `backend/src/agents/prompts.py:126` (`CHITCHAT_PROMPT`)
- Test: `backend/tests/agents/test_prompts.py`
- Create: `docs/superpowers/plans/2026-08-05-chitchat-brand-identity-fix-report.md`

**Interfaces:** Không đổi. `CHITCHAT_PROMPT` vẫn là hằng số `str`, vẫn
được `make_respond_unknown_node`/`evals.run_eval.eval_chitchat` import y
hệt cũ.

- [ ] **Step 1: Viết test chốt (chạy TRƯỚC khi sửa — phải FAIL)**

Thêm vào cuối `backend/tests/agents/test_prompts.py`:

```python
def test_chitchat_prompt_has_brand_name():
    """Gán tên thương hiệu (plan 2026-08-05-chitchat-brand-identity-fix):
    đo thật qua request tới backend live cho thấy hệ thống chưa từng tự
    giới thiệu bằng tên "Youdoo" khi được hỏi "bạn là ai" — grep toàn bộ
    prompts.py xác nhận 0 lần xuất hiện trước khi sửa. Chốt cứng để không
    bị mất khi ai đó sửa lại CHITCHAT_PROMPT sau này."""
    from src.agents.prompts import CHITCHAT_PROMPT
    assert "Youdoo" in CHITCHAT_PROMPT
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `cd D:/Youdoo/.claude/worktrees/chitchat-brand-identity-fix/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_prompts.py::test_chitchat_prompt_has_brand_name -v`
Expected: FAIL — `AssertionError`.

- [ ] **Step 3: Sửa `CHITCHAT_PROMPT`**

Trong `backend/src/agents/prompts.py`, tìm dòng đầu tiên của
`CHITCHAT_PROMPT` (hiện dòng 126):

```
Bạn là trợ lý ERP nội bộ, trả lời bằng tiếng Việt với giọng chuyên nghiệp, thân thiện.
```

Thay bằng (CHỈ dòng này, giữ nguyên mọi dòng khác của `CHITCHAT_PROMPT`
phía dưới):

```
Bạn là Youdoo, trợ lý ERP nội bộ, trả lời bằng tiếng Việt với giọng chuyên nghiệp, thân thiện.
```

- [ ] **Step 4: Chạy lại test — phải PASS**

Run: `cd D:/Youdoo/.claude/worktrees/chitchat-brand-identity-fix/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_prompts.py::test_chitchat_prompt_has_brand_name -v`
Expected: PASS.

- [ ] **Step 5: Chạy toàn bộ suite unit-only — phải PASS**

Run: `cd D:/Youdoo/.claude/worktrees/chitchat-brand-identity-fix/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"`
Expected: PASS toàn bộ, không giảm số PASS so với baseline đã biết trước
khi bắt đầu (ghi lại số PASS ở bước đầu phiên làm việc để đối chiếu).

- [ ] **Step 6: Đo thật `--set chitchat` — xác nhận `violations == 0`**

Cần Postgres `youdoo` đang chạy. Chạy (bash):

```bash
cd D:/Youdoo/.claude/worktrees/chitchat-brand-identity-fix/backend && set -a && source ../.env && set +a && \
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set chitchat
```

Expected: gate PASS, `violations=0`. Nếu `violations > 0`, DỪNG — đọc
`fails[].matched_markers` để biết câu mới vô tình khớp
`HALLUCINATION_MARKERS` nào, báo cáo thay vì tự sửa thêm.

- [ ] **Step 7: Gọi backend LIVE thật — xác nhận response nhắc "Youdoo"**

Backend FastAPI phải đang chạy ở `http://localhost:8000` — chạy TỪ REPO
CHÍNH (không phải worktree này):

```bash
cd D:/Youdoo/backend && set -a && source ../.env && set +a && \
  PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe run.py
```

(Nếu backend đã đang chạy sẵn từ trước — kiểm tra bằng
`curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/v1/models` — bỏ
qua bước khởi động, chỉ cần xác nhận backend đó đã nạp code MỚI, tức là
phải RESTART backend nếu nó khởi động trước khi Step 3 sửa file — code
Python không tự reload theo mặc định của `run.py`.)

Gửi request thật (viết JSON ra file tạm để tránh lỗi encode UTF-8 ở
shell, KHÔNG dùng `-d` inline với chuỗi tiếng Việt):

```bash
cat > /tmp/test-chitchat.json <<'EOF'
{"model":"erp-assistant","messages":[{"role":"user","content":"Bạn là ai?"}]}
EOF
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json; charset=utf-8" \
  --data-binary @/tmp/test-chitchat.json --max-time 40
```

Expected: response JSON's `choices[0].message.content` chứa chuỗi
"Youdoo". Ghi nguyên văn response vào report. Xoá file tạm sau khi xong.

- [ ] **Step 8: Viết report**

Tạo `docs/superpowers/plans/2026-08-05-chitchat-brand-identity-fix-report.md`
gồm: kết quả `--set chitchat` (violations=0, log JSON path), response thật
nguyên văn từ Step 7 xác nhận có "Youdoo", kết luận theo tiêu chí hoàn
thành của spec §7.

- [ ] **Step 9: Commit**

```bash
git add backend/src/agents/prompts.py backend/tests/agents/test_prompts.py docs/superpowers/plans/2026-08-05-chitchat-brand-identity-fix-report.md
git commit -m "fix(agents): gán tên Youdoo vào CHITCHAT_PROMPT — đo thật xác nhận backend live tự giới thiệu đúng tên"
```

---

## Self-Review

**Spec coverage:**

| Mục spec | Task |
|---|---|
| §1-3 vấn đề + phạm vi + ràng buộc gate (đã xác định khi viết spec, không lặp lại) | — |
| §4 nội dung sửa nguyên văn | Task 1 Step 3 |
| §5 kiểm chứng (test + eval-gate + backend live) | Task 1 Step 4-7 |
| §6 file bị chạm | Task 1 (prompts.py, test_prompts.py, report) |
| §7 tiêu chí hoàn thành | Task 1 Step 4-7 |

**Type consistency:** `CHITCHAT_PROMPT` vẫn là hằng số `str` module-level,
không đổi kiểu dữ liệu. Không có hàm/API mới.
