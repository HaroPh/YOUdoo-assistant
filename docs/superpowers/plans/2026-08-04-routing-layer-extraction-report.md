# Report: Tách tầng định tuyến ra `routing.py` (2026-08-04)

Kế hoạch: `docs/superpowers/plans/2026-08-04-routing-layer-extraction.md`
Spec: `docs/superpowers/specs/2026-08-04-routing-layer-extraction-design.md`

## 1. SHA

| Mốc | SHA | Ghi chú |
|---|---|---|
| Baseline (trước Task 1) | `3c1cae7a5cb4edfd7cef5f3da15201d2e37a6e93` | docs(routing): làm rõ ràng buộc test |
| Task 1 | `621cb417d6354774da420d619513cac8f34af253` | refactor(routing): chuyển lớp đề xuất sang routing.py, `parse_proposal` trả `RouteProposal` |
| Task 2 | `aec27bb6faeb081124ede8b68e1a8cb485d10778` | refactor(routing): chuyển lớp veto sang routing.py, docstring hợp đồng 2 lớp |
| Sửa plan (giữa T2 và T3) | `826e164504d0a0dcb4a152880aaaf9fe9f3da716` | docs(plan): sửa grep Task 3 — pattern trần khớp cả tên hàm test |
| Task 3 (cuối) | *(commit theo sau report này — xem git log)* | docs(routing): sửa cross-reference còn lại + report |

## 2. Suite unit-only

- Trước Task 1 (baseline): **1121 passed / 4 skipped / 43 deselected**.
- Sau Task 1: **1122 passed / 4 skipped / 43 deselected** (+1 test mới cho `RouteProposal`).
- Sau Task 2: giữ nguyên 1122 passed.
- Sau Task 3 (đo thật, lệnh dưới): **1122 passed / 4 skipped / 43 deselected, 0 failed.**

Lệnh chạy (từ worktree, dùng interpreter của repo chính vì worktree không có
`.venv` riêng — gitignored):
```
cd D:/Youdoo/.claude/worktrees/routing-layer-extraction/backend
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 "D:/Youdoo/backend/.venv/Scripts/python.exe" -m pytest -q -m "not integration and not live"
```
Kết quả thô: `1122 passed, 4 skipped, 43 deselected in 29.45s`.

**Không assert nào bị sửa nội dung, xuyên suốt cả 3 commit (Task 1, Task 2,
Task 3).** Task 3 tự nó chỉ đụng comment/docstring (18 dòng, 10 file — xem
mục 5); không một dòng code thực thi hay một `assert` nào bị đổi ở Task 3.
Phạm vi rộng hơn — toàn nhánh, không chỉ Task 3 — được final whole-branch
review xác nhận cơ học: áp bảng đổi tên symbol lên các blob trước Task 1
(baseline), rồi diff kết quả với trạng thái sau Task 3; diff không còn lệch
nào ngoài các chỗ đổi tên đã biết, tức không `assert` nào ở bất kỳ commit
nào trong 3 commit bị đổi giá trị kỳ vọng. Số `passed` không tăng thêm so
với sau Task 1/2 vì Task 3 không thêm test mới — chỉ vệ sinh prose.

Chú ý vận hành: bộ `tests/rag/` re-serialize 2 fixture nhị phân
(`backend/tests/rag/fixtures/bang_gia.xlsx`, `policy.docx`) mỗi lần chạy. Sau
mỗi lần chạy full suite đã `git checkout --` phục hồi 2 file này trước khi
stage — xác nhận bằng `git status --short` rỗng ở đường dẫn đó trước commit.

## 3. Suite `-m integration`

Postgres `youdoo-postgres` đang chạy (container healthy, đã xác nhận bằng
`docker ps`). Lệnh:
```
cd D:/Youdoo/.claude/worktrees/routing-layer-extraction/backend
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 "D:/Youdoo/backend/.venv/Scripts/python.exe" -m pytest -q -m integration
```
Kết quả: `27 passed, 1142 deselected in 6.11s`. Không tăng fail so với trước
(0 failed).

## 4. Đo xác nhận `--set sop_select`

Postgres + Odoo (`localhost:8069`) đều đang chạy. Lệnh:
```
cd D:/Youdoo/.claude/worktrees/routing-layer-extraction/backend
set -a && source ../.env && set +a
PYTHONIOENCODING=utf-8 "D:/Youdoo/backend/.venv/Scripts/python.exe" -m jobs run eval-gate --set sop_select
```
Kết quả:
```
[sop_select] model=gemma-4-26b pace=2.4s acc=0.9411764705882353 hijack=0 → FAIL
```
- `acc = 0.9411764705882353` = **16/17** → đạt bar (`acc ≥ 16/17`).
- `hijack = 0` → đạt bar (`hijack = 0`).
- Ca fail duy nhất: `"quy trình nhập kho cho đơn mua P00021"` (expected
  `nhap-kho`, got `rag`) — đúng ca hồi quy 2026-07-16 đã biết trước và cố ý
  giữ lại; đây là lý do dòng `gate` in `FAIL` dù `acc`/`hijack` đều đạt bar.
  Không đọc verdict `FAIL` như tín hiệu lỗi — đọc `acc`/`hijack`.
- File log: `logs/jobs/eval-gate-20260804T233149.json`.

**Cả `acc` và `hijack` đều đạt bar ngay lượt đầu, không cần chạy lượt 2** (quy
tắc ở plan chỉ yêu cầu chạy lượt 2 khi `hijack > 0` hoặc `acc < 16/17`).

**Giới hạn phải ghi (chép nguyên ý từ plan):** prompt byte-identical và logic
parse/veto byte-identical so với trước refactor, nên bất kỳ lệch nào ở đây là
do **sampling của model**, KHÔNG kết luận được gì về đúng/sai của việc tách
`routing.py`. Đây là phép đo **xác nhận** (confirmation), không phải bằng
chứng cho refactor — bằng chứng thật nằm ở suite unit-only (mục 2), nơi
1122 test cũ (giá trị kỳ vọng KHÔNG đổi, chỉ đổi tên symbol) đều xanh.

## 5. Grep xác nhận không còn tên cũ

Lệnh (anchor `(^|[^A-Za-z0-9])` để không báo nhầm tên hàm test đã đúng, xem
lý do ở Step 1 của task-3-brief.md):
```
grep -rnE "(^|[^A-Za-z0-9])(_route_by_intent|_looks_like_question|_parse_router_output)" --include="*.py" backend/src backend/evals backend/tests
```
Kết quả: **rỗng** (0 dòng khớp). Trước khi sửa, cùng lệnh này ra 18 dòng ở 10
file (nhiều hơn 8 file nêu trong bảng gốc của Task 3 — 6 chỗ thêm do `main`
đã nhận merge từ nhánh song song: `graph.py:54`, `run_eval.py:379,428,429`,
`test_build_graph_skill_integration.py:125`, `test_skill_gate.py:7`). Tất cả
18 dòng đã sửa theo đúng quy tắc đổi tên (`_parse_router_output`→
`parse_proposal`, `_route_by_intent`→`decide_route`,
`_looks_like_question`→`looks_like_question`, và mọi qualifier
`graph.`/`nodes.` gắn liền các symbol đó →`routing.`).

Kiểm tên hàm test không bị hỏng:
```
grep -rn "def test_looks_like_question\|def test_decide_route" --include="*.py" backend/tests
```
Kết quả: 3 dòng — `test_looks_like_question_detects_all_markers`,
`test_looks_like_question_false_for_plain_commands`
(`backend/tests/agents/test_graph_build.py`) và
`test_decide_route_still_returns_plain_mixed_string`
(`backend/tests/agents/test_fanout_graph.py`) — đúng như dự kiến, không hàm
nào bị đụng.

Kiểm spec cũ không bị sửa (chạy từ worktree, KHÔNG phải `D:/Youdoo` như văn
bản gốc trong brief ghi nhầm — worktree này là checkout độc lập):
```
cd D:/Youdoo/.claude/worktrees/routing-layer-extraction
git status --short docs/superpowers/specs/
```
Kết quả: **rỗng** — không file spec nào bị sửa.

## 6. Đối chiếu §7 "Xong nghĩa là" của spec

1. ✅ `backend/src/agents/routing.py` tồn tại, chứa đủ 6 symbol (§2.1) với
   docstring đầu file mô tả hợp đồng 2 lớp (§2.2) — hoàn thành ở Task 1/2,
   xác nhận lại bằng đọc trực tiếp file trong Task 3.
2. ✅ `_QUESTION_MARKERS`, `_looks_like_question`, `_route_by_intent` KHÔNG
   còn trong `graph.py`; `VALID_INTENTS`, `_parse_router_output`,
   `make_intent_router_node` KHÔNG còn trong `nodes.py`. Không có shim
   re-export — xác nhận bằng grep trực tiếp 2 file, 0 kết quả.
3. ✅ Tên node graph vẫn là chuỗi `"intent_router"` — không đổi (xác nhận:
   `graph.py` dòng `g.add_conditional_edges("intent_router", decide_route, intent_targets)`).
4. ✅ **6 import site** đã sửa ở Task 1/2 (không phải 5 — 5 chỗ plan liệt kê
   cộng thêm `backend/tests/agents/test_sop_select_gate.py`, vốn import
   `VALID_INTENTS` từ `nodes`; đây là chỗ hụt trong danh sách file của plan,
   chỉ lộ ra khi một subagent chạy full suite); **18 dòng ở 10 file** (không
   phải 8 — xem mục 5) đã sửa ở Task 3; không file nào trong
   `docs/superpowers/specs/` bị đụng.
5. ✅ Suite unit-only 1122 passed / 0 failed, không tăng fail so với baseline
   (1121, trước Task 1 — mục 2); không assert nào bị sửa nội dung (mục 2).
6. ✅ Test mới cho `RouteProposal` (thêm ở Task 1, §5.3 spec) nằm trong 1122
   test xanh.
7. ✅ Một lượt `--set sop_select` đã chạy: `acc = 16/17`, `hijack = 0`, kèm
   ghi chú giới hạn (mục 4) — log tại
   `logs/jobs/eval-gate-20260804T233149.json`.

Cả 7 mục đạt.
