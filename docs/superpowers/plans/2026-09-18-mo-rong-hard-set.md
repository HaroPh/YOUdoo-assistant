# Mở rộng nhóm `hard` — kế hoạch thực thi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nâng nhóm `hard` của bộ `retrieval` từ 17 lên ~62 ca bằng lấy mẫu tất định + agent mù viết câu, đo lại 6 chân reranker trên bộ mở rộng, và ra kết luận theo quy tắc **đã đăng ký trước** (spec §8) — xác nhận hay bác bỏ tín hiệu +0,25 `hard mrr` của `qwen3-4b-override`.

**Architecture:** Bốn mảnh thuần, mỗi mảnh một tệp và test riêng: `hard_gate` (thước overlap), `retrieval_stats` (hoán vị + bootstrap), `sample_hard_sections` (lọc rác + phân tầng + bước nhảy; phần đọc DB tách khỏi phần thuần). Agent mù viết 45 câu từ tệp mẫu đã đóng băng, không thấy spec/kết quả. Bộ mới là danh sách riêng `HARD_EXPANSION_CASES` nối vào `RETRIEVAL_CASES`, để cổng overlap chỉ áp lên ca mới. Đo 6 chân sau khi commit đóng băng; `old-64` là đối chứng hạ tầng; quyết định đọc thẳng từ spec §8.

**Tech Stack:** Python 3.11, psycopg 3, pytest; reranker stack đã có trên nhánh (`RERANK_MODEL`, `RAG_RERANK_MODE`, `device_map`).

**Spec:** `docs/superpowers/specs/2026-09-18-mo-rong-hard-set-design.md` — đọc §3 (định nghĩa thước, ngưỡng 0,40 và vì sao), §4 (luật lọc + công thức bước nhảy + seed), §5 (hợp đồng agent mù), §7 (đối chứng `old-64`, dừng khi nào), §8 (quy tắc quyết định — không dời).

## Global Constraints

- **Worktree**: `D:/Youdoo/.claude/worktrees/so-sanh-reranker`, nhánh `worktree-so-sanh-reranker`, HEAD hiện tại `50cde13`. Không có `.venv` riêng — interpreter `d:/Youdoo/backend/.venv/Scripts/python.exe`, cwd `…/so-sanh-reranker/backend`. Không cd sang `D:/Youdoo` hay worktree khác.
- **Mọi lệnh pytest kèm** `-m "not integration and not live"` **và** `PYTHONIOENCODING=utf-8`, thêm `-p no:cacheprovider`. Không hai lượt pytest cùng lúc; không pytest khi một chân eval đang chạy.
- **Mốc nền suite: `2724 passed, 1 skipped, 113 deselected`** (HEAD `0f42f14`/`50cde13`). Mọi task giữ hoặc tăng.
- **64 ca cũ trong `retrieval_cases.py` không đổi một ký tự.** Có test băm gác.
- **Định danh trong `backend/src` và `backend/evals` tiếng Anh**; chú thích/docstring/thông điệp tiếng Việt; tên hàm test tiếng Việt theo quy ước `backend/tests`.
- **Thứ tự đóng băng (spec §7):** Task 1→5 xong, test hợp đồng kể cả `integration` xanh, **commit** — rồi mới chạy chân đo đầu tiên (Task 6). Không sửa câu nào sau khi đã thấy số.
- **Agent mù (Task 4) không được đọc** spec 2026-09-17, spec 2026-09-18, thư mục `evals/results/`, hay bất kỳ tệp nào ngoài danh sách brief liệt kê.
- **Env cho lệnh chạm DB** (script lấy mẫu, test `integration`, chân eval): chỉ export 3 biến:
  `export $(grep -E '^(DATABASE_URL|RAG_SCHEMA|OLLAMA_URL)=' D:/Youdoo/.claude/worktrees/so-sanh-reranker/.env | xargs -d '\n')` — không export gì khác, không in giá trị.
- **GPU (Task 6):** không start/stop/kill tiến trình hay container nào; `youdoo-postgres` + `youdoo-ollama` phải đang chạy; container `ollama` thứ hai phải đang dừng. Chủ dự án có thể lấy lại GPU giữa chừng — chân bị ngắt thì chạy lại chân đó, các chân đã xong giữ nguyên.
- **Không chạy lại 6 chân của ngày 2026-09-17/18** trong `evals/results/reranker-2026-09-17/` — chúng là đối chứng.
- Dấu phân cách breadcrumb là `" › "` (U+203A).

---

## File Structure

| tệp | trách nhiệm |
|---|---|
| `backend/evals/hard_gate.py` | **Mới.** `tokens`, `leaf`, `overlap`, hằng `HARD_MAX_OVERLAP = 0.40`. Thuần. |
| `backend/tests/evals/test_hard_gate.py` | **Mới.** |
| `backend/evals/retrieval_stats.py` | **Mới.** Nạp `per_case`, chênh ghép cặp, hoán vị, bootstrap, thắng/hoà/thua, văng top-6; CLI. Thuần. |
| `backend/tests/evals/test_retrieval_stats.py` | **Mới.** Dữ liệu giả có đáp án biết trước. |
| `backend/evals/sample_hard_sections.py` | **Mới.** `is_junk`, `allocate`, `stride_pick` (thuần) + `load_nodes`, `main` (DB). In JSON mẫu. |
| `backend/tests/evals/test_sample_hard_sections.py` | **Mới.** Phần thuần; một ca `integration` chạy `main()` thật. |
| `backend/evals/hard_expansion_sample.json` | **Mới, sinh bởi script, commit.** 45 nút + `chunk_text`. Đầu vào duy nhất của agent mù. |
| `backend/evals/hard_expansion_cases.py` | **Mới, agent mù viết.** `HARD_EXPANSION_CASES`. |
| `docs/superpowers/specs/2026-09-18-hard-expansion-justification.md` | **Mới, agent mù viết.** Mỗi ca: câu / nhãn / trích dẫn / overlap / số lần viết lại; danh sách nút bỏ. |
| `backend/evals/retrieval_cases.py` | **Sửa.** Đổi tên list literal thành `_CORE`; `RETRIEVAL_CASES = _CORE + HARD_EXPANSION_CASES`. |
| `backend/tests/evals/test_retrieval_cases.py` | **Sửa.** Thêm 3 test: băm `_CORE`, `n_hard ≥ 60`, cổng overlap cho bộ mới. |
| `backend/evals/results/reranker-2026-09-18-mo-rong/` | **Mới.** 6 JSON + `README.md`. |
| `docs/superpowers/specs/2026-09-18-mo-rong-hard-set-design.md` | **Sửa (Task 5, 7).** Bảng phân bổ thật + nút bỏ; §10 ghi chép; §11 kết luận. |
| `docs/trang-thai-chung.md` | **Sửa (Task 7).** Cập nhật mục #29. |

**Thứ tự bắt buộc:** 1 → 2 → 3 → 4 → 5 (đóng băng) → 6 → 7. Task 1 và 2 độc lập nhau nhưng làm tuần tự để không đụng suite.

---

### Task 1: Thước overlap — `hard_gate`

**Files:**
- Create: `backend/evals/hard_gate.py`
- Create: `backend/tests/evals/test_hard_gate.py`

**Interfaces:**
- Consumes: `src.rag.chunking.fold_vi(text: str) -> str` (đã có).
- Produces:
  - `hard_gate.SEP = " › "`
  - `hard_gate.HARD_MAX_OVERLAP: float = 0.40`
  - `hard_gate.tokens(text: str) -> set[str]`
  - `hard_gate.leaf(section_path: str) -> str`
  - `hard_gate.overlap(question: str, section_paths) -> float` — `section_paths` là iterable chuỗi; trả max; 0.0 khi không có lá nào có token.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/evals/test_hard_gate.py`:

```python
# backend/tests/evals/test_hard_gate.py
"""Thước overlap câu hỏi ↔ tiêu đề mục — spec 2026-09-18 §3.

Thước này biến "hard" từ phán đoán thành số đo. Hiệu chỉnh trên 64 ca cũ:
easy trung vị 0,67, hard trung vị 0,33 → ngưỡng 0,40 loại 28/31 easy.
Đổi định nghĩa token hay lá là đổi thước — các số đó phải đo lại.
"""
from evals.hard_gate import HARD_MAX_OVERLAP, leaf, overlap, tokens


def test_nguong_la_0_40():
    assert HARD_MAX_OVERLAP == 0.40


def test_tokens_bo_dau_lower_va_bo_token_mot_ky_tu():
    assert tokens("Đơn phương chấm dứt") == {"don", "phuong", "cham", "dut"}
    assert tokens("a B cc") == {"cc"}


def test_leaf_lay_phan_sau_dau_phan_cach_cuoi():
    assert leaf("Chương I › NHỮNG QUY ĐỊNH CHUNG › Điều 4. Giải thích") == "Điều 4. Giải thích"
    assert leaf("Điều 428. Đơn phương chấm dứt") == "Điều 428. Đơn phương chấm dứt"


def test_overlap_trung_het_la_1_khong_trung_la_0():
    assert overlap("thuế suất", ["Điều 9. Thuế suất"]) == 1.0
    assert overlap("giá bán lẻ", ["Điều 9. Thuế suất"]) == 0.0


def test_overlap_la_ti_le_tren_token_cua_la():
    # lá: {dieu, 428, don, phuong, cham, dut} = 6; câu trúng {cham, dut} = 2
    got = overlap("hợp đồng bị chấm dứt thì sao", ["Điều 428. Đơn phương chấm dứt"])
    assert abs(got - 2 / 6) < 1e-9


def test_overlap_khong_phu_thuoc_dau():
    a = overlap("đơn phương chấm dứt", ["Điều 428. Đơn phương chấm dứt"])
    b = overlap("don phuong cham dut", ["Điều 428. Đơn phương chấm dứt"])
    assert a == b


def test_overlap_nhieu_nhan_lay_max():
    got = overlap("thuế suất", ["Điều 1. Phạm vi", "Điều 9. Thuế suất"])
    assert got == 1.0


def test_overlap_la_rong_tra_0():
    assert overlap("gì đó", [""]) == 0.0
    assert overlap("gì đó", []) == 0.0
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/evals/test_hard_gate.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.hard_gate'`

- [ ] **Step 3: Cài đặt**

Tạo `backend/evals/hard_gate.py`:

```python
# backend/evals/hard_gate.py
"""Thước "hard" tất định — spec 2026-09-18 §3.

overlap = |tokens(câu hỏi) ∩ tokens(lá tiêu đề)| / |tokens(lá)|. Đo trên 64 ca
cũ (2026-09-18): easy trung vị 0,67 / p25 0,60; hard trung vị 0,33 / p75 0,50.
Ngưỡng 0,40 loại 28/31 ca easy. Cổng CHỈ áp lên ca mới (HARD_EXPANSION_CASES):
vài ca hard cũ được gán bằng ngữ nghĩa, overlap tới 0,83.

Dùng ở hai nơi và PHẢI là cùng một hàm: agent viết câu tự kiểm, và test hợp
đồng gác lại. Đổi định nghĩa token/lá là đổi thước — số hiệu chỉnh phải đo lại.
"""
import re

from src.rag.chunking import fold_vi

SEP = " › "
HARD_MAX_OVERLAP = 0.40
_TOKEN_RE = re.compile(r"\w+")


def tokens(text: str) -> set[str]:
    """Tập token bỏ dấu, lower, bỏ token một ký tự (dấu câu, số điều lẻ)."""
    return {t for t in _TOKEN_RE.findall(fold_vi(text).lower()) if len(t) > 1}


def leaf(section_path: str) -> str:
    """Phần sau dấu › cuối — tiêu đề mục đích, không phải cả breadcrumb."""
    return section_path.split("›")[-1].strip()


def overlap(question: str, section_paths) -> float:
    """Max overlap của câu hỏi với lá của từng nhãn; 0.0 khi không có lá nào."""
    q = tokens(question)
    best = 0.0
    for sp in section_paths:
        lt = tokens(leaf(sp))
        if lt:
            best = max(best, len(q & lt) / len(lt))
    return best
```

- [ ] **Step 4: Chạy để xác nhận XANH**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/evals/test_hard_gate.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: `8 passed`

- [ ] **Step 5: Xác nhận số hiệu chỉnh trong spec vẫn đúng với hàm này**

Run:
```bash
PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -c "
import statistics as st
from evals.retrieval_cases import RETRIEVAL_CASES
from evals.hard_gate import overlap
rows={}
for q,exp,d in RETRIEVAL_CASES: rows.setdefault(d,[]).append(overlap(q,[s for _,s in exp]))
for d in ('easy','hard','trap'): print(d, len(rows[d]), round(st.median(rows[d]),2))
print('easy bi loai o 0.40:', sum(1 for x in rows['easy'] if x>0.40), '/', len(rows['easy']))"
```
Expected: `easy 31 0.67`, `hard 17 0.33`, `trap 16 0.64`, `easy bi loai o 0.40: 28 / 31`. Lệch → hàm không cùng thước với spec §3; sửa hàm, không sửa spec.

- [ ] **Step 6: Commit**

```bash
git add backend/evals/hard_gate.py backend/tests/evals/test_hard_gate.py
git commit -m "feat(eval): thuoc overlap cau hoi <-> tieu de muc (hard_gate)

Bien 'hard' tu phan doan thanh so do. Hieu chinh tren 64 ca cu: easy trung
vi 0,67, hard 0,33; nguong 0,40 loai 28/31 easy. Chi ap len ca MOI.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Thống kê ghép cặp — `retrieval_stats`

**Files:**
- Create: `backend/evals/retrieval_stats.py`
- Create: `backend/tests/evals/test_retrieval_stats.py`

**Interfaces:**
- Consumes: JSON kết quả của `run_eval --set retrieval` có `per_case` (mỗi hàng: `question`, `difficulty`, `reciprocal_rank`, `recall_at_final`, `hit_ranks`, `method`).
- Produces:
  - `retrieval_stats.load_per_case(path: str) -> dict[str, dict]` — `question → row`.
  - `retrieval_stats.select(rows: dict, difficulty: str | None = None, questions=None) -> list[str]` — danh sách câu theo thứ tự ổn định.
  - `retrieval_stats.paired_diffs(base: dict, other: dict, questions: list[str], key: str = "reciprocal_rank") -> list[float]` — `other − base`.
  - `retrieval_stats.permutation_p(diffs: list[float], max_exact: int = 22, n_mc: int = 20000, seed: int = 0) -> float` — hai phía, sign-flip; chính xác khi số chênh ≠ 0 ≤ `max_exact`, Monte Carlo khi lớn hơn.
  - `retrieval_stats.bootstrap_ci(diffs, n: int = 20000, seed: int = 0, alpha: float = 0.05) -> tuple[float, float]`
  - `retrieval_stats.wins_ties_losses(diffs) -> tuple[int, int, int]`
  - `retrieval_stats.dropouts(base: dict, other: dict, questions: list[str]) -> list[str]` — câu có `other.recall_at_final == 0` và `base.recall_at_final > 0`.
  - `retrieval_stats.compare(base: dict, other: dict, questions: list[str]) -> dict` — gộp: `n, mean_diff, ci_lo, ci_hi, p, wins, ties, losses, dropouts`.
  - CLI: `python -m evals.retrieval_stats BASE.json OTHER.json [--difficulty hard] [--questions-from FILE.json]` in bảng một dòng + danh sách văng.

- [ ] **Step 1: Viết test đỏ**

Tạo `backend/tests/evals/test_retrieval_stats.py`:

```python
# backend/tests/evals/test_retrieval_stats.py
"""Kiểm định ghép cặp — spec 2026-09-18 §1/§8. Thuần, dữ liệu giả có đáp án."""
import json

import pytest

from evals import retrieval_stats as rs


def _rows(vals, difficulty="hard", final=None):
    """vals: dict question -> reciprocal_rank; final: dict question -> recall_at_final."""
    return {q: {"question": q, "difficulty": difficulty, "reciprocal_rank": v,
                "recall_at_final": (final or {}).get(q, 1.0 if v > 0 else 0.0),
                "hit_ranks": [], "method": "x"} for q, v in vals.items()}


def test_paired_diffs_la_other_tru_base_theo_thu_tu_cau():
    base = _rows({"a": 1.0, "b": 0.5}); other = _rows({"a": 0.5, "b": 1.0})
    assert rs.paired_diffs(base, other, ["a", "b"]) == [-0.5, 0.5]


def test_permutation_moi_chenh_deu_duong_p_bang_2_tren_2_mu_n():
    # n=10 chênh đều +1: chỉ 2/1024 cách gán dấu có |mean| >= 1 (toàn + hoặc toàn −).
    p = rs.permutation_p([1.0] * 10)
    assert abs(p - 2 / 1024) < 1e-12


def test_permutation_khong_co_chenh_p_bang_1():
    assert rs.permutation_p([0.0, 0.0, 0.0]) == 1.0


def test_permutation_bo_qua_chenh_bang_0_khi_dem_hoan_vi():
    # 5 chênh +1 và 5 chênh 0: hoán vị chỉ trên 5 chênh ≠ 0 → 2/32.
    p = rs.permutation_p([1.0] * 5 + [0.0] * 5)
    assert abs(p - 2 / 32) < 1e-12


def test_permutation_monte_carlo_khi_qua_nhieu_chenh():
    diffs = [1.0] * 30                       # > max_exact=22 → Monte Carlo
    p = rs.permutation_p(diffs, n_mc=2000, seed=1)
    assert 0.0 <= p < 0.01                  # gần 2/2^30, không thể bằng 1


def test_bootstrap_du_lieu_hang_thi_ci_bang_hang():
    lo, hi = rs.bootstrap_ci([0.25] * 8)
    assert lo == 0.25 and hi == 0.25


def test_bootstrap_ci_chua_mean_va_tai_lap_theo_seed():
    d = [0.9, -0.3, 0.6, 0.0, 0.4, -0.1, 0.7, 0.2]
    lo1, hi1 = rs.bootstrap_ci(d, seed=7); lo2, hi2 = rs.bootstrap_ci(d, seed=7)
    assert (lo1, hi1) == (lo2, hi2)
    m = sum(d) / len(d)
    assert lo1 <= m <= hi1


def test_wins_ties_losses():
    assert rs.wins_ties_losses([0.5, 0.0, -0.2, 0.1]) == (2, 1, 1)


def test_dropouts_chi_dem_ca_base_giu_ma_other_lam_van():
    base = _rows({"a": 1.0, "b": 0.0, "c": 0.5}, final={"a": 1, "b": 0, "c": 1})
    other = _rows({"a": 0.0, "b": 0.0, "c": 0.5}, final={"a": 0, "b": 0, "c": 1})
    assert rs.dropouts(base, other, ["a", "b", "c"]) == ["a"]


def test_select_loc_theo_difficulty_va_theo_danh_sach_cau():
    rows = {**_rows({"a": 1.0}, "hard"), **_rows({"b": 1.0}, "easy")}
    assert rs.select(rows, difficulty="hard") == ["a"]
    assert rs.select(rows, questions=["b", "zzz"]) == ["b"]


def test_compare_gop_du_truong():
    base = _rows({"a": 1.0, "b": 0.5, "c": 0.0}); other = _rows({"a": 1.0, "b": 1.0, "c": 0.5})
    got = rs.compare(base, other, ["a", "b", "c"])
    assert got["n"] == 3 and abs(got["mean_diff"] - 1 / 3) < 1e-9
    assert set(got) >= {"ci_lo", "ci_hi", "p", "wins", "ties", "losses", "dropouts"}
    assert (got["wins"], got["ties"], got["losses"]) == (2, 1, 0)


def test_load_per_case_doc_json_that(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"per_case": [{"question": "q1", "difficulty": "hard",
                                           "reciprocal_rank": 0.5, "recall_at_final": 1.0,
                                           "hit_ranks": [2], "method": "m"}]}),
                 encoding="utf-8")
    rows = rs.load_per_case(str(p))
    assert rows["q1"]["reciprocal_rank"] == 0.5
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/evals/test_retrieval_stats.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.retrieval_stats'`

- [ ] **Step 3: Cài đặt**

Tạo `backend/evals/retrieval_stats.py`:

```python
# backend/evals/retrieval_stats.py
"""Kiểm định ghép cặp giữa hai chân đo `retrieval` — spec 2026-09-18 §1, §8.

Vì sao có module này: ngày 2026-09-18 phép kiểm đầu tiên chạy bằng lệnh gõ
tay trong shell và phát hiện chỉ 1/12 phép so có CI không cắt 0. Một phép
kiểm quyết định có đổi reranker production hay không thì phải là mã có test,
tái lập bằng seed, không phải một đoạn shell ai nhớ ai quên.

Thuần Python: không numpy, không DB, không model. Sign-flip permutation hai
phía (chính xác tới `max_exact` chênh ≠ 0, Monte Carlo khi nhiều hơn) và
bootstrap percentile.
"""
import argparse
import itertools
import json
import random


def load_per_case(path: str) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {row["question"]: row for row in data["per_case"]}


def select(rows: dict, difficulty: str | None = None, questions=None) -> list[str]:
    """Danh sách câu, thứ tự ổn định (thứ tự trong `rows`, hoặc trong `questions`)."""
    if questions is not None:
        return [q for q in questions if q in rows]
    return [q for q, r in rows.items()
            if difficulty is None or r["difficulty"] == difficulty]


def paired_diffs(base: dict, other: dict, questions: list[str],
                 key: str = "reciprocal_rank") -> list[float]:
    return [float(other[q][key]) - float(base[q][key]) for q in questions]


def permutation_p(diffs: list[float], max_exact: int = 22,
                  n_mc: int = 20000, seed: int = 0) -> float:
    """p hai phía cho H0 "chênh có dấu ngẫu nhiên". Chênh = 0 không đổi dấu
    được nên không tham gia đếm, nhưng vẫn nằm trong mẫu số của mean."""
    n = len(diffs)
    if n == 0:
        return 1.0
    nz = [d for d in diffs if abs(d) > 1e-12]
    if not nz:
        return 1.0
    obs = abs(sum(diffs) / n)
    if len(nz) <= max_exact:
        hits = total = 0
        for signs in itertools.product((1, -1), repeat=len(nz)):
            m = abs(sum(s * d for s, d in zip(signs, nz)) / n)
            total += 1
            if m >= obs - 1e-12:
                hits += 1
        return hits / total
    rng = random.Random(seed)
    hits = 0
    for _ in range(n_mc):
        m = abs(sum(d if rng.random() < 0.5 else -d for d in nz) / n)
        if m >= obs - 1e-12:
            hits += 1
    return hits / n_mc


def bootstrap_ci(diffs: list[float], n: int = 20000, seed: int = 0,
                 alpha: float = 0.05) -> tuple[float, float]:
    if not diffs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    k = len(diffs)
    means = sorted(sum(rng.choices(diffs, k=k)) / k for _ in range(n))
    return means[int(alpha / 2 * n)], means[min(n - 1, int((1 - alpha / 2) * n))]


def wins_ties_losses(diffs: list[float]) -> tuple[int, int, int]:
    w = sum(1 for d in diffs if d > 1e-12)
    l = sum(1 for d in diffs if d < -1e-12)
    return w, len(diffs) - w - l, l


def dropouts(base: dict, other: dict, questions: list[str]) -> list[str]:
    """Câu bị `other` làm văng khỏi top-k trong khi `base` còn giữ."""
    return [q for q in questions
            if other[q]["recall_at_final"] == 0 and base[q]["recall_at_final"] > 0]


def compare(base: dict, other: dict, questions: list[str]) -> dict:
    d = paired_diffs(base, other, questions)
    lo, hi = bootstrap_ci(d)
    w, t, l = wins_ties_losses(d)
    return {"n": len(d), "mean_diff": (sum(d) / len(d)) if d else 0.0,
            "ci_lo": lo, "ci_hi": hi, "p": permutation_p(d),
            "wins": w, "ties": t, "losses": l,
            "dropouts": dropouts(base, other, questions)}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="So hai chân đo retrieval theo ghép cặp.")
    ap.add_argument("base"); ap.add_argument("other")
    ap.add_argument("--difficulty", default=None)
    ap.add_argument("--questions-from", default=None,
                    help="JSON có per_case; chỉ so trên các câu của tệp này")
    a = ap.parse_args(argv)
    base, other = load_per_case(a.base), load_per_case(a.other)
    qs = None
    if a.questions_from:
        qs = list(load_per_case(a.questions_from))
    questions = select(base, a.difficulty, qs)
    if a.difficulty and qs:
        questions = [q for q in questions if base[q]["difficulty"] == a.difficulty]
    r = compare(base, other, questions)
    print(f"n={r['n']}  chenh_TB={r['mean_diff']:+.4f}  CI95=[{r['ci_lo']:+.3f},{r['ci_hi']:+.3f}]"
          f"  p={r['p']:.4f}  thang/hoa/thua={r['wins']}/{r['ties']}/{r['losses']}")
    for q in r["dropouts"]:
        print(f"  VANG (other mat, base giu): {q}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Chạy để xác nhận XANH**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/evals/test_retrieval_stats.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: `12 passed`

- [ ] **Step 5: Đối chứng với số đã công bố trong spec §1**

Run:
```bash
PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m evals.retrieval_stats evals/results/reranker-2026-09-17/bge-v2-m3.json evals/results/reranker-2026-09-17/qwen3-4b-override.json --difficulty hard
```
Expected: `n=17  chenh_TB=+0.2500  CI95=[+0.059,+0.436]  p=0.0273  thang/hoa/thua=8/8/1` (CI có thể lệch ±0,005 do seed bootstrap; p phải bằng đúng vì hoán vị chính xác). Lệch p → module sai, sửa module.

- [ ] **Step 6: Commit**

```bash
git add backend/evals/retrieval_stats.py backend/tests/evals/test_retrieval_stats.py
git commit -m "feat(eval): retrieval_stats - hoan vi ghep cap + bootstrap, co test

Doi chung voi spec 2026-09-18 §1: hard n=17, +0,2500, p=0,0273.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Lấy mẫu tất định — `sample_hard_sections`

**Files:**
- Create: `backend/evals/sample_hard_sections.py`
- Create: `backend/tests/evals/test_sample_hard_sections.py`
- Create (sinh ra, commit): `backend/evals/hard_expansion_sample.json`

**Interfaces:**
- Consumes: `hard_gate.tokens`, `hard_gate.leaf`, `hard_gate.SEP` (Task 1); `evals.retrieval_cases._CORE` (64 ca cũ — task này đổi tên list literal thành `_CORE` và thêm alias `RETRIEVAL_CASES = _CORE`; Task 5 mới nối bộ mở rộng); `src.rag.db.connect`; `src.rag.chunking.fold_vi`.
- Produces:
  - `sample_hard_sections.SEED = 20260918`, `sample_hard_sections.N_TOTAL = 45`
  - `retrieval_cases._CORE` (đổi tên, nội dung 64 ca không đổi) và alias `RETRIEVAL_CASES = _CORE`
  - `sample_hard_sections.BUSINESS_DOCS: tuple[str, ...]` — 7 basename `.docx`.
  - `sample_hard_sections.LAW_DOCS: tuple[str, ...]` — 9 basename `.pdf`.
  - `sample_hard_sections.is_junk(basename: str, section_path: str) -> bool`
  - `sample_hard_sections.allocate(counts: dict[str, int], k: int, floor: int = 1) -> dict[str, int]`
  - `sample_hard_sections.stride_pick(items: list, k: int, seed: int) -> list`
  - `sample_hard_sections.load_nodes(conn) -> list[tuple[str, str]]` — distinct `(basename, section_path)`, sắp xếp.
  - `sample_hard_sections.load_chunk_text(conn, basename: str, section_path: str) -> str`
  - `sample_hard_sections.build_sample(conn, seed: int = SEED) -> dict` — `{"seed", "allocation": {...}, "nodes": [{"basename","section_path","chunk_text"}]}`
  - CLI `python -m evals.sample_hard_sections > evals/hard_expansion_sample.json` (bảng phân bổ in ra stderr).

- [ ] **Step 1: Viết test đỏ (phần thuần)**

Tạo `backend/tests/evals/test_sample_hard_sections.py`:

```python
# backend/tests/evals/test_sample_hard_sections.py
"""Lấy mẫu tất định — spec 2026-09-18 §4. Phần thuần không cần DB; ca cuối
là `integration` chạy build_sample() trên corpus thật."""
import pytest

from evals import sample_hard_sections as shs


def test_seed_ghi_trong_spec():
    assert shs.SEED == 20260918


def test_is_junk_quoc_hieu_va_tu_loai_van_ban_tran():
    assert shs.is_junk("luat-doanhnghiep.pdf", "QUỐC HỘI")
    assert shs.is_junk("luat-doanhnghiep.pdf", "QUỐC HỘI › CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
    assert shs.is_junk("luat-doanhnghiep.pdf", "LUẬT")
    assert shs.is_junk("boluat-laodong.pdf", "BỘ LUẬT")
    assert shs.is_junk("x.pdf", "Độc lập - Tự do - Hạnh phúc")


def test_is_junk_la_ngan_duoi_3_token():
    assert shs.is_junk("x.pdf", "Chương I › Điều 5.")      # {dieu} → 1 token
    assert not shs.is_junk("x.pdf", "Chương I › Điều 5. Chính sách về đầu tư kinh doanh")


def test_is_junk_bao_cao_tai_chinh_va_rong():
    assert shs.is_junk("SID_000000016657191_01VI_BaoCaoTaiChinhBanNien_HopNhat_SoatXet_2026_signed_05092026111802.pdf",
                       "Chương trình › 39 BIẾT KP")
    assert shs.is_junk("x.pdf", "")


def test_is_junk_khong_loai_muc_that():
    assert not shs.is_junk("luat-doanhnghiep.pdf",
                           "Chương I › NHỮNG QUY ĐỊNH CHUNG › Điều 4. Giải thích từ ngữ")


def test_allocate_theo_ti_le_phan_du_lon_nhat_san_1():
    # Ước tính spec §4.2 — phải ra đúng bảng đó.
    counts = {"danssu": 708, "thuongmai": 335, "laodong": 225, "doanhnghiep": 221,
              "quanlythue": 159, "bhxh": 147, "dautu": 65, "xnk": 27, "gtgt": 22}
    got = shs.allocate(counts, 38)
    assert got == {"danssu": 14, "thuongmai": 7, "laodong": 4, "doanhnghiep": 4,
                   "quanlythue": 3, "bhxh": 3, "dautu": 1, "xnk": 1, "gtgt": 1}
    assert sum(got.values()) == 38


def test_allocate_tong_dung_k_va_khong_duoi_san():
    got = shs.allocate({"a": 1000, "b": 1, "c": 1}, 5)
    assert sum(got.values()) == 5 and min(got.values()) >= 1


def test_stride_pick_tat_dinh_khong_trung_va_tang_dan():
    items = list(range(100))
    a = shs.stride_pick(items, 7, 20260918); b = shs.stride_pick(items, 7, 20260918)
    assert a == b and len(set(a)) == 7 and a == sorted(a)
    assert all(0 <= x < 100 for x in a)


def test_stride_pick_theo_cong_thuc_spec():
    # N=100, k=4: step=25; offset=(918/1000)*25=22.95 → [22, 47, 72, 97]
    assert shs.stride_pick(list(range(100)), 4, 20260918) == [22, 47, 72, 97]


def test_stride_pick_k_lon_hon_N_lay_het():
    assert shs.stride_pick([1, 2, 3], 5, 1) == [1, 2, 3]


def test_stride_pick_doi_seed_doi_ket_qua():
    items = list(range(100))
    assert shs.stride_pick(items, 4, 20260918) != shs.stride_pick(items, 4, 20260500)


@pytest.mark.integration
def test_build_sample_tren_corpus_that_ra_45_nut_hop_le():
    from src.rag import db as _db
    conn = _db.connect()
    try:
        sample = shs.build_sample(conn)
    finally:
        conn.close()
    nodes = sample["nodes"]
    assert len(nodes) == shs.N_TOTAL, sample["allocation"]
    bases = [n["basename"] for n in nodes]
    # Đo 2026-09-18: policy.docx đã bị 64 ca cũ gán nhãn 5/5 mục → 0 nút; 6 tệp kia 1 ca.
    for b in shs.BUSINESS_DOCS:
        assert bases.count(b) == (1 if sample["pool_after_filter"].get(b, 0) > 0 else 0), b
    n_business = sum(bases.count(b) for b in shs.BUSINESS_DOCS)
    assert n_business == 6
    assert sum(bases.count(b) for b in shs.LAW_DOCS) == shs.N_TOTAL - n_business
    assert all(not shs.is_junk(n["basename"], n["section_path"]) for n in nodes)
    assert all(n["chunk_text"].strip() for n in nodes)
    assert len({(n["basename"], n["section_path"]) for n in nodes}) == 45
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/evals/test_sample_hard_sections.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Cài đặt**

Tạo `backend/evals/sample_hard_sections.py`:

```python
# backend/evals/sample_hard_sections.py
"""Lấy mẫu 45 nút cho HARD_EXPANSION_CASES — tất định, phân tầng, tái lập được.

Spec 2026-09-18 §4. Vì sao không chọn tay: tiền lệ trong dự án — 7 trang tự
chọn để dựng cổng đạt 1,000, 21 trang còn lại của CÙNG tài liệu chỉ 0,537.
Luật lọc rác và phép chọn nằm ở ĐÂY, chạy lại là ra đúng bộ đó.

    python -m evals.sample_hard_sections > evals/hard_expansion_sample.json
"""
import json
import math
import os
import re
import sys

from evals.hard_gate import SEP, leaf, tokens
from src.rag.chunking import fold_vi

SEED = 20260918

BUSINESS_DOCS = ("policy.docx", "discount_policy.docx", "payment_policy.docx",
                 "sla.docx", "sop.docx", "sales_process.docx", "warehouse_outbound.docx")
LAW_DOCS = ("boluat-danssu.pdf", "boluat-thuongmai.pdf", "boluat-laodong.pdf",
            "luat-doanhnghiep.pdf", "luat-quanlythue.pdf", "luat-baohiemxahoi.pdf",
            "luat-dautu.pdf", "luat-thuexuatnhapkhau.pdf", "luat-thuegtgt.pdf")
N_TOTAL = 45
N_BUSINESS_PER_DOC = 1        # mỗi tệp nghiệp vụ CÒN nút chưa gán nhãn; hết nút → 0

# Lá là quốc hiệu/tiêu ngữ/từ loại văn bản trần → không phải mục có nội dung.
_BOILERPLATE = frozenset({
    "quoc hoi", "cong hoa xa hoi chu nghia viet nam",
    "quoc hoi cong hoa xa hoi chu nghia viet nam",
    "doc lap tu do hanh phuc", "chu tich quoc hoi",
    "luat", "bo luat", "nghi dinh", "thong tu",
})
_FINANCIAL_REPORT_RE = re.compile(r"BaoCaoTaiChinh", re.IGNORECASE)


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", fold_vi(text).lower()).split())


def is_junk(basename: str, section_path: str) -> bool:
    """Luật lọc §4.1 — mọi điều kiện đều tất định, không có phán đoán."""
    if not section_path or not section_path.strip():
        return True
    if _FINANCIAL_REPORT_RE.search(basename):
        return True
    lf = leaf(section_path)
    if _norm(lf) in _BOILERPLATE:
        return True
    if len(tokens(lf)) < 3:
        return True
    return False


def allocate(counts: dict[str, int], k: int, floor: int = 1) -> dict[str, int]:
    """Chia k theo tỉ lệ counts, phần dư lớn nhất, mỗi tầng ≥ floor."""
    total = sum(counts.values())
    quota = {d: counts[d] / total * k for d in counts}
    out = {d: max(floor, math.floor(quota[d])) for d in counts}
    rem = k - sum(out.values())
    if rem > 0:
        order = sorted(counts, key=lambda d: quota[d] - math.floor(quota[d]), reverse=True)
        for d in order:
            if rem == 0:
                break
            if math.floor(quota[d]) >= floor:      # tầng đã nhận sàn thì không cộng thêm
                out[d] += 1; rem -= 1
    while rem < 0:                                   # sàn đẩy quá k: bớt ở tầng lớn nhất
        d = max(out, key=lambda x: (out[x], quota[x]))
        out[d] -= 1; rem += 1
    return out


def stride_pick(items: list, k: int, seed: int) -> list:
    """k phần tử tại floor(offset + i·N/k), offset = ((seed mod 1000)/1000)·N/k."""
    n = len(items)
    if k >= n:
        return list(items)
    step = n / k
    offset = ((seed % 1000) / 1000) * step
    return [items[math.floor(offset + i * step)] for i in range(k)]


def _basename(source_file: str) -> str:
    return os.path.basename(str(source_file).replace("\\", "/"))


def load_nodes(conn) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT DISTINCT source_file, section_path FROM rag_chunks "
        "WHERE section_path IS NOT NULL AND section_path <> ''").fetchall()
    return sorted({(_basename(sf), sp) for sf, sp in rows})


def load_chunk_text(conn, basename: str, section_path: str) -> str:
    rows = conn.execute(
        "SELECT chunk_text FROM rag_chunks WHERE section_path = %s "
        "AND (source_file LIKE %s OR source_file LIKE %s) ORDER BY chunk_index",
        (section_path, "%/" + basename, "%\\" + basename)).fetchall()
    return "\n".join(r[0] for r in rows)


def _labelled() -> set[tuple[str, str]]:
    # _CORE, KHÔNG phải RETRIEVAL_CASES: sau khi nối bộ mở rộng, 45 nút mới cũng
    # "đã có nhãn" và chạy lại script sẽ ra bộ KHÁC — mất tính tái lập.
    from evals.retrieval_cases import _CORE
    return {(f, s) for _q, exp, _d in _CORE for f, s in exp}


def build_sample(conn, seed: int = SEED) -> dict:
    used = _labelled()
    nodes = [(b, s) for b, s in load_nodes(conn)
             if not is_junk(b, s) and (b, s) not in used]
    by_doc: dict[str, list] = {}
    for b, s in nodes:
        by_doc.setdefault(b, []).append((b, s))
    picked: list[tuple[str, str]] = []
    allocation: dict[str, int] = {}
    for b in BUSINESS_DOCS:
        chosen = stride_pick(sorted(by_doc.get(b, [])), N_BUSINESS_PER_DOC, seed)
        picked += chosen; allocation[b] = len(chosen)
    law_counts = {b: len(by_doc.get(b, [])) for b in LAW_DOCS}
    law_alloc = allocate(law_counts, N_TOTAL - len(picked))
    for b in LAW_DOCS:
        chosen = stride_pick(sorted(by_doc.get(b, [])), law_alloc[b], seed)
        picked += chosen; allocation[b] = len(chosen)
    pool = {**{b: len(by_doc.get(b, [])) for b in BUSINESS_DOCS}, **law_counts}
    return {"seed": seed, "allocation": allocation, "pool_after_filter": pool,
            "nodes": [{"basename": b, "section_path": s,
                       "chunk_text": load_chunk_text(conn, b, s)} for b, s in picked]}


def main() -> None:
    from src.rag import db as _db
    conn = _db.connect()
    try:
        sample = build_sample(conn)
    finally:
        conn.close()
    for b, k in sample["allocation"].items():
        print(f"{b:<32} {k:>3}  (pool {sample['pool_after_filter'].get(b, '-')})", file=sys.stderr)
    print(f"tong {len(sample['nodes'])}", file=sys.stderr)
    print(json.dumps(sample, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3b: Đổi tên list 64 ca thành `_CORE` (nội dung không đổi)**

Trong `backend/evals/retrieval_cases.py`: dòng 55 `RETRIEVAL_CASES: list[tuple[str, frozenset, str]] = [` → `_CORE: list[tuple[str, frozenset, str]] = [`; sau dòng `]` đóng list (277) thêm:

```python

# 64 ca gốc. Tên riêng có chủ đích: sample_hard_sections chỉ loại nút đã có nhãn
# trong _CORE (tái lập được sau khi nối bộ mở rộng), và test băm gác nội dung.
RETRIEVAL_CASES: list[tuple[str, frozenset, str]] = _CORE
```

Kiểm: `git diff -- backend/evals/retrieval_cases.py` chỉ có 1 dòng đổi tên + khối thêm; `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -c "import hashlib; from evals.retrieval_cases import _CORE; print(hashlib.sha256(repr([(q, sorted(e), d) for q, e, d in _CORE]).encode('utf-8')).hexdigest())"` phải in `845473c4d72d15ee7cdbccde4bb9262c168be97412bca466612b8700a00ea44e` (băm tính 2026-09-18 trên 64 ca hiện tại).

- [ ] **Step 4: Chạy để xác nhận XANH (thuần)**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/evals/test_sample_hard_sections.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: `11 passed, 1 deselected`

- [ ] **Step 5: Chạy `integration` và sinh tệp mẫu**

```bash
export $(grep -E '^(DATABASE_URL|RAG_SCHEMA|OLLAMA_URL)=' D:/Youdoo/.claude/worktrees/so-sanh-reranker/.env | xargs -d '\n')
PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/evals/test_sample_hard_sections.py -m integration -q -p no:cacheprovider
PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m evals.sample_hard_sections > evals/hard_expansion_sample.json
```
Expected: `1 passed`; stderr in bảng phân bổ 16 dòng (policy.docx = 0, pool 0) + `tong 45`. **Dán bảng phân bổ (kèm `pool`) vào spec §4.2** thay cho dòng "Ước tính trước khi lọc". Lệch ±1 so với ước tính là bình thường; lệch nhiều hơn thì kiểm luật lọc có loại nhầm mục thật không (xem 5 nút bị lọc ngẫu nhiên bằng cách in chúng ra), **không sửa phân bổ tay**.

- [ ] **Step 6: Commit (kèm tệp mẫu — đây là bước đóng băng đầu vào của agent mù)**

```bash
git add backend/evals/sample_hard_sections.py backend/tests/evals/test_sample_hard_sections.py backend/evals/hard_expansion_sample.json backend/evals/retrieval_cases.py docs/superpowers/specs/2026-09-18-mo-rong-hard-set-design.md
git commit -m "feat(eval): lay mau tat dinh 45 nut cho HARD_EXPANSION_CASES (seed 20260918)

<DÁN BẢNG PHÂN BỔ THẬT VÀO ĐÂY>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Agent mù viết 45 câu

**Files:**
- Create: `backend/evals/hard_expansion_cases.py`
- Create: `docs/superpowers/specs/2026-09-18-hard-expansion-justification.md`

**Interfaces:**
- Consumes — **và chỉ được đọc đúng ba thứ này**: `backend/evals/hard_expansion_sample.json`, `backend/evals/hard_gate.py`, brief của task. Không đọc `docs/superpowers/specs/2026-09-1*`, không đọc `backend/evals/results/`, không đọc `retrieval_cases.py`, không chạy eval, không tải model.
- Produces: `hard_expansion_cases.HARD_EXPANSION_CASES: list[tuple[str, frozenset, str]]` — mỗi phần tử `(question, frozenset({(basename, section_path)}), "hard")`, cùng shape với `RETRIEVAL_CASES`; `hard_expansion_cases.DROPPED_NODES: list[tuple[str, str]]`.

- [ ] **Step 1: Viết script tự kiểm (đây là "test đỏ" của task — trước khi có tệp ca thì nó đỏ)**

Tạo tạm trong `$TEMP` (không commit) `check_expansion.py`:

```python
import json, sys
sys.path.insert(0, ".")
from evals.hard_gate import HARD_MAX_OVERLAP, overlap
from evals.hard_expansion_cases import HARD_EXPANSION_CASES, DROPPED_NODES
sample = json.load(open("evals/hard_expansion_sample.json", encoding="utf-8"))
nodes = {(n["basename"], n["section_path"]) for n in sample["nodes"]}
labels = [next(iter(exp)) for _q, exp, _d in HARD_EXPANSION_CASES]
assert all(lab in nodes for lab in labels), "nhãn ngoài tệp mẫu"
assert len(set(labels)) == len(labels), "hai câu cùng nút"
assert set(labels) | set(DROPPED_NODES) == nodes, "thiếu nút: mỗi nút phải hoặc có câu hoặc nằm trong DROPPED"
assert all(d == "hard" for _q, _e, d in HARD_EXPANSION_CASES)
bad = [(q, round(overlap(q, [s for _f, s in exp]), 2)) for q, exp, _d in HARD_EXPANSION_CASES
       if overlap(q, [s for _f, s in exp]) > HARD_MAX_OVERLAP]
assert not bad, f"vượt cổng {HARD_MAX_OVERLAP}: {bad}"
qs = [q for q, _e, _d in HARD_EXPANSION_CASES]
assert len(set(qs)) == len(qs), "câu trùng"
print(f"OK: {len(HARD_EXPANSION_CASES)} ca, {len(DROPPED_NODES)} nút bỏ")
```

- [ ] **Step 2: Viết ca**

Với **mỗi** nút trong `hard_expansion_sample.json` (theo đúng thứ tự tệp):
1. Đọc `chunk_text`. Chọn **một** điều cụ thể mà đoạn trả lời được (một con số, một điều kiện, một hậu quả, một quyền/nghĩa vụ).
2. Viết **một câu hỏi** như người dùng thường hỏi trợ lý công ty: lời thường, không nêu số Điều/Mục/Chương, **không dùng từ ngữ của tiêu đề mục** (tiêu đề là phần sau `›` cuối của `section_path`). Diễn đạt lại khái niệm bằng từ khác — ví dụ "tự ý dừng hợp đồng giữa chừng" thay vì "đơn phương chấm dứt".
3. Tính `overlap(question, [section_path])`. > 0,40 → viết lại (tối đa 3 lần). Vẫn > 0,40 → đưa nút vào `DROPPED_NODES`, ghi lý do. **Không** thay bằng nút khác.
4. Ghi vào tệp justification: câu hỏi, nhãn, **một dòng trích nguyên văn** từ `chunk_text` chứa câu trả lời, overlap, số lần viết lại.

Tạo `backend/evals/hard_expansion_cases.py`:

```python
# backend/evals/hard_expansion_cases.py
"""45 ca `hard` mở rộng — spec 2026-09-18 §4-§5.

Nút lấy mẫu TẤT ĐỊNH bởi evals/sample_hard_sections.py (seed 20260918), đầu
vào là evals/hard_expansion_sample.json. Câu hỏi do một agent viết MÙ: không
thấy spec, không thấy kết quả đo nào, không biết đang so reranker nào.

Mỗi ca: (câu hỏi, frozenset({(basename, section_path)}), "hard"). Mọi ca qua
cổng hard_gate.overlap ≤ 0,40 — test hợp đồng gác lại. Trích dẫn chứng minh
"đáp án có thật ở đó" nằm ở docs/superpowers/specs/2026-09-18-hard-expansion-
justification.md.
"""

HARD_EXPANSION_CASES: list[tuple[str, frozenset, str]] = [
    # (câu hỏi, frozenset({(basename, section_path)}), "hard")
    # … 45 (hoặc ít hơn nếu có nút bỏ) phần tử, thứ tự theo tệp mẫu …
]

# Nút không viết được câu qua cổng sau 3 lần — bỏ, không thay.
DROPPED_NODES: list[tuple[str, str]] = [
    # (basename, section_path)
]
```

Tạo `docs/superpowers/specs/2026-09-18-hard-expansion-justification.md`:

```markdown
# Bằng chứng đáp án cho HARD_EXPANSION_CASES

Sinh từ `evals/hard_expansion_sample.json` (seed 20260918). Mỗi ca một mục:

## 1. <basename> › <section_path>
- **Câu hỏi:** …
- **Trích dẫn (nguyên văn trong chunk):** "…"
- **overlap:** 0,xx — **viết lại:** n lần

…

## Nút bỏ
- <basename> › <section_path> — lý do: overlap thấp nhất đạt được 0,xx sau 3 lần
```

- [ ] **Step 3: Chạy script tự kiểm**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe "$TEMP/check_expansion.py"`
Expected: `OK: N ca, M nút bỏ` với N + M = 45 và N ≥ 43. N < 43 → cổng quá chặt cho cách viết hiện tại; **dừng, báo DONE_WITH_CONCERNS** kèm 3 ví dụ câu tốt nhất vẫn vượt cổng — không tự nới ngưỡng.

- [ ] **Step 4: Commit**

```bash
git add backend/evals/hard_expansion_cases.py docs/superpowers/specs/2026-09-18-hard-expansion-justification.md
git commit -m "feat(eval): 45 ca hard mo rong - agent mu viet tu mau tat dinh

N ca qua cong overlap <= 0,40; M nut bo (ghi trong DROPPED_NODES).
Moi ca kem trich dan nguyen van chung minh dap an co that.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Nối vào `RETRIEVAL_CASES`, test hợp đồng, ĐÓNG BĂNG

**Files:**
- Modify: `backend/evals/retrieval_cases.py` (khối cuối: thay alias `RETRIEVAL_CASES = _CORE` bằng phép nối; `_CORE` đã có từ Task 3)
- Modify: `backend/tests/evals/test_retrieval_cases.py` (thêm 3 test)
- Modify: `docs/superpowers/specs/2026-09-18-mo-rong-hard-set-design.md` (§4.2 bảng thật đã dán ở Task 3; thêm số ca thật và nút bỏ vào §5)

**Interfaces:**
- Consumes: `hard_expansion_cases.HARD_EXPANSION_CASES` (Task 4), `hard_gate.overlap`, `hard_gate.HARD_MAX_OVERLAP` (Task 1).
- Produces: `retrieval_cases._CORE` (64 ca cũ, không đổi) và `retrieval_cases.RETRIEVAL_CASES = _CORE + HARD_EXPANSION_CASES`.

- [ ] **Step 1: Viết test đỏ**

Thêm vào cuối `backend/tests/evals/test_retrieval_cases.py` (TRƯỚC test `integration` sẵn có nếu muốn giữ nhóm; vị trí không quan trọng):

```python
import hashlib

from evals.hard_expansion_cases import HARD_EXPANSION_CASES
from evals.hard_gate import HARD_MAX_OVERLAP, overlap
from evals.retrieval_cases import _CORE

# Băm nội dung 64 ca cũ. Sinh MỘT LẦN khi nối bộ mở rộng (Task 5, 2026-09-18)
# bằng lệnh ở docstring; đỏ = ai đó đã sửa/xoá/thêm ca cũ — không được phép,
# vì old-64 là đối chứng hạ tầng (spec 2026-09-18 §7).
_CORE_SHA256 = "845473c4d72d15ee7cdbccde4bb9262c168be97412bca466612b8700a00ea44e"


def _core_digest() -> str:
    canon = repr([(q, sorted(exp), d) for q, exp, d in _CORE])
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def test_64_ca_cu_khong_doi_mot_ky_tu():
    assert len(_CORE) == 64
    assert _core_digest() == _CORE_SHA256, (
        "64 ca cũ đã đổi. Nếu CỐ Ý, cập nhật _CORE_SHA256 bằng:\n"
        "  python -c \"from tests.evals.test_retrieval_cases import _core_digest; print(_core_digest())\"")


def test_du_so_ca_hard_cho_thong_ke():
    # sd ≈ 0,395 trên chênh RR → se 0,05 cần ~62 ca (spec 2026-09-18 §1).
    n_hard = sum(1 for _q, _e, d in RETRIEVAL_CASES if d == "hard")
    assert n_hard >= 60, f"chỉ có {n_hard} ca hard"


def test_moi_ca_mo_rong_qua_cong_overlap():
    # Cổng CHỈ áp lên bộ mới — vài ca hard cũ gán theo ngữ nghĩa có overlap tới 0,83.
    bad = [(q, round(overlap(q, [s for _f, s in exp]), 2))
           for q, exp, _d in HARD_EXPANSION_CASES
           if overlap(q, [s for _f, s in exp]) > HARD_MAX_OVERLAP]
    assert not bad, f"vượt cổng {HARD_MAX_OVERLAP}: {bad}"
    assert all(d == "hard" for _q, _e, d in HARD_EXPANSION_CASES)
```

- [ ] **Step 2: Chạy để xác nhận ĐỎ**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/evals/test_retrieval_cases.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: FAIL — `test_du_so_ca_hard_cho_thong_ke` đỏ (`chỉ có 17 ca hard`); `test_64_ca_cu_khong_doi_mot_ky_tu` xanh (băm đã đúng từ Task 3).

- [ ] **Step 3: Nối bộ mở rộng**

Trong `backend/evals/retrieval_cases.py`, thay khối alias cuối tệp (`RETRIEVAL_CASES: list[...] = _CORE` và chú thích của nó) bằng:

```python

# ── Bộ mở rộng 2026-09-18 ─────────────────────────────────────────────────
# 45 ca `hard` lấy mẫu TẤT ĐỊNH (evals/sample_hard_sections.py, seed 20260918)
# và viết bởi agent MÙ — xem evals/hard_expansion_cases.py. Danh sách riêng có
# chủ đích: cổng overlap ≤ 0,40 chỉ áp lên bộ này; 64 ca cũ (_CORE) là đối
# chứng hạ tầng cho mọi lần đo lại, có test băm gác.
from evals.hard_expansion_cases import HARD_EXPANSION_CASES  # noqa: E402

RETRIEVAL_CASES: list[tuple[str, frozenset, str]] = _CORE + HARD_EXPANSION_CASES
```

**Kiểm chéo**: `git diff 50cde13 -- backend/evals/retrieval_cases.py` chỉ được có đúng 1 dòng đổi tên + khối thêm ở cuối; không dòng nào trong 64 ca bị đụng. Băm `_CORE_SHA256` trong test đã tính sẵn (2026-09-18) — test xanh là bằng chứng.

- [ ] **Step 4: Test hợp đồng — cả thuần lẫn `integration`**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/evals/test_retrieval_cases.py -m "not integration and not live" -q -p no:cacheprovider`
Expected: toàn bộ xanh (7 cũ + 3 mới).

Run (nhãn tồn tại THẬT trong `rag_chunks` — đây là cổng chặn nhãn bịa):
```bash
export $(grep -E '^(DATABASE_URL|RAG_SCHEMA|OLLAMA_URL)=' D:/Youdoo/.claude/worktrees/so-sanh-reranker/.env | xargs -d '\n')
PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest tests/evals/test_retrieval_cases.py -m integration -q -p no:cacheprovider
```
Expected: `1 passed`. Đỏ → một nhãn của bộ mới không khớp chunk nào; nhãn là chính nút lấy mẫu nên chỉ có thể do `section_path` bị sửa khi chép — sửa nhãn cho khớp tệp mẫu, **không** sửa câu hỏi.

- [ ] **Step 5: Toàn suite**

Run: `PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q -p no:cacheprovider`
Expected: `2724 + 8 + 12 + 11 + 3 = 2758 passed, 1 skipped, 114 deselected` (thêm 1 `integration` ở Task 3). Lệch → giải thích từng ca.

Thêm cổng tái lập (spec §4.2): chạy lại script lấy mẫu SAU khi đã nối bộ mở rộng phải cho JSON y hệt:
```bash
export $(grep -E '^(DATABASE_URL|RAG_SCHEMA|OLLAMA_URL)=' D:/Youdoo/.claude/worktrees/so-sanh-reranker/.env | xargs -d '\n')
PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -m evals.sample_hard_sections 2>/dev/null > "$TEMP/resample.json" && diff -q "$TEMP/resample.json" evals/hard_expansion_sample.json && echo TAI_LAP_OK
```
Expected: `TAI_LAP_OK`. Khác → `_labelled()` đang đọc `RETRIEVAL_CASES` thay vì `_CORE`; sửa script, không sửa JSON.

- [ ] **Step 6: Cập nhật spec §5 với số thật** (số ca vào, số nút bỏ, trỏ tới tệp justification), rồi **commit — đây là mốc ĐÓNG BĂNG**

```bash
git add backend/evals/retrieval_cases.py backend/tests/evals/test_retrieval_cases.py docs/superpowers/specs/2026-09-18-mo-rong-hard-set-design.md
git commit -m "feat(eval): noi HARD_EXPANSION_CASES vao RETRIEVAL_CASES - DONG BANG truoc khi do

n_hard = <N>; 64 ca cu bam sha256 <8 ky tu dau>; cong overlap <= 0,40 gac
bo moi; nhan ton tai that (integration xanh). Tu commit nay khong sua cau.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Đo 6 chân trên bộ mở rộng + đối chứng `old-64`

**Files:**
- Create: `backend/evals/results/reranker-2026-09-18-mo-rong/{no-rerank,bge-v2-m3,qwen3-0.6b,qwen3-4b,qwen3-0.6b-override,qwen3-4b-override}.json`
- Create: `backend/evals/results/reranker-2026-09-18-mo-rong/README.md`
- Modify: `backend/evals/baseline-bge-m3-retrieval.json` (sinh lại bằng `--save-baseline`, chân bge hoà)

**Interfaces:**
- Consumes: `run_eval --set retrieval` (đã trả `per_case`, `rerank_model`, `rerank_mode`); `retrieval_stats` CLI (Task 2); 6 JSON đối chứng trong `evals/results/reranker-2026-09-17/`.
- Produces: 6 JSON mới + bảng đối chứng trong README.

- [ ] **Step 1: Tiền kiểm** — HEAD phải là commit đóng băng của Task 5 (`git log -1`); `git status --porcelain` sạch; `docker ps` có `youdoo-postgres`, `youdoo-ollama`, KHÔNG có `ollama`; `nvidia-smi --query-gpu=memory.free --format=csv` ≥ 5000 MiB. Ghi cả ba vào báo cáo.

- [ ] **Step 2: Chạy 6 chân, tuần tự, chân sau chỉ bắt đầu khi chân trước xong**

```bash
cd D:/Youdoo/.claude/worktrees/so-sanh-reranker/backend
export $(grep -E '^(DATABASE_URL|RAG_SCHEMA|OLLAMA_URL)=' D:/Youdoo/.claude/worktrees/so-sanh-reranker/.env | xargs -d '\n')
R=evals/results/reranker-2026-09-18-mo-rong; mkdir -p $R
PY="d:/Youdoo/backend/.venv/Scripts/python.exe -m evals.run_eval --set retrieval --model bge-m3"

PYTHONIOENCODING=utf-8 $PY --no-rerank                                           > $R/no-rerank.json          2> $R/no-rerank.stderr.log
PYTHONIOENCODING=utf-8 RERANK_MODEL=BAAI/bge-reranker-v2-m3 $PY                  > $R/bge-v2-m3.json          2> $R/bge-v2-m3.stderr.log
PYTHONIOENCODING=utf-8 RERANK_MODEL=Qwen/Qwen3-Reranker-0.6B $PY                 > $R/qwen3-0.6b.json         2> $R/qwen3-0.6b.stderr.log
PYTHONIOENCODING=utf-8 RERANK_MODEL=Qwen/Qwen3-Reranker-0.6B RAG_RERANK_MODE=override $PY > $R/qwen3-0.6b-override.json 2> $R/qwen3-0.6b-override.stderr.log
PYTHONIOENCODING=utf-8 RERANK_MODEL=Qwen/Qwen3-Reranker-4B RERANK_DEVICE_MAP=auto RERANK_GPU_BUDGET=3GiB $PY > $R/qwen3-4b.json 2> $R/qwen3-4b.stderr.log
PYTHONIOENCODING=utf-8 RERANK_MODEL=Qwen/Qwen3-Reranker-4B RERANK_DEVICE_MAP=auto RERANK_GPU_BUDGET=3GiB RAG_RERANK_MODE=override $PY > $R/qwen3-4b-override.json 2> $R/qwen3-4b-override.stderr.log
```
Hai chân 4B để cuối và chạy nền, chờ theo đợt 5–10 phút. Chân 4B segfault (exit 139) → thử lại `RERANK_GPU_BUDGET=2GiB` rồi `1GiB`; **không** chạy CPU-only. Chân bị ngắt (chủ dự án lấy GPU) → chạy lại đúng chân đó.

- [ ] **Step 3: Kiểm hợp lệ TRƯỚC khi đọc số**

```bash
for f in $R/*.json; do printf "%-24s " "$(basename $f .json)"; PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -c "
import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8'))
print(d['methods_seen'], 'errors=',len(d['errors']), 'n=',len(d['per_case']), d.get('rerank_model'), d.get('rerank_mode'))" "$f"; done
```
Expected: `no-rerank` → `['dense+fold-rrf']`; 5 chân kia → đúng một giá trị kết thúc `+rerank`; `errors=0`; `n=` bằng số ca của `RETRIEVAL_CASES` (109 nếu không có nút bỏ); `rerank_model`/`rerank_mode` khớp lệnh. Sai bất kỳ → chân đó vô giá trị, đọc stderr, chạy lại.

- [ ] **Step 4: Đối chứng hạ tầng `old-64` — spec §7, DỪNG nếu lệch**

Với **mỗi** chân, so `per_case` của lần đo mới với lần đo 2026-09-17 của cùng chân, chỉ trên 64 câu cũ:

```bash
for leg in no-rerank bge-v2-m3 qwen3-0.6b qwen3-4b qwen3-0.6b-override qwen3-4b-override; do
  printf "%-22s " $leg
  PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0,'.')
from evals import retrieval_stats as rs
old=rs.load_per_case('evals/results/reranker-2026-09-17/$leg.json'); new=rs.load_per_case('$R/$leg.json')
qs=[q for q in old if q in new]
diff_final=[q for q in qs if old[q]['recall_at_final']!=new[q]['recall_at_final']]
hard=[q for q in qs if old[q]['difficulty']=='hard']
mo=sum(old[q]['reciprocal_rank'] for q in hard)/len(hard); mn=sum(new[q]['reciprocal_rank'] for q in hard)/len(hard)
print(f'old64 n={len(qs)}  recall_at_final khac={len(diff_final)}  hard17 mrr cu={mo:.4f} moi={mn:.4f} lech={abs(mo-mn):.4f}', diff_final[:2])"
done
```
Expected: `n=64`, `khac=0` (đúng 1 → ghi tên câu và đi tiếp), `lech ≤ 0.0200`. Vi phạm ở bất kỳ chân nào → **DỪNG**, báo BLOCKED kèm bảng; không đọc số bộ mới. (Nguyên nhân khả dĩ: corpus bị nạp lại, HNSW đổi, model tải khác phiên bản.)

- [ ] **Step 5: README + baseline + commit**

Viết `$R/README.md`: bảng chân → `rerank_model`/`rerank_mode`/env, ngày chạy, bảng đối chứng `old-64` của Step 4, ghi rõ 4B là đường `device_map` offload nên p50 không đại diện. Sinh lại baseline cho chân production:
```bash
PYTHONIOENCODING=utf-8 RERANK_MODEL=BAAI/bge-reranker-v2-m3 $PY --save-baseline > /dev/null
```
(ghi đè `evals/baseline-bge-m3-retrieval.json` để nó phản ánh 109 ca; chân này chạy lại 1 lần nữa, chấp nhận ~2 phút).

```bash
git add $R/*.json $R/README.md backend/evals/baseline-bge-m3-retrieval.json
git commit -m "eval(rag): 6 chan do tren bo hard mo rong (n_hard=<N>) + doi chung old-64

<DÁN BẢNG ĐỐI CHỨNG old-64 VÀO ĐÂY>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Kiểm định, kết luận theo §8, ghi chép

**Files:**
- Modify: `docs/superpowers/specs/2026-09-18-mo-rong-hard-set-design.md` (thêm `## 10. Ghi chép thực thi` và `## 11. Kết luận`)
- Modify: `docs/trang-thai-chung.md` (mục #29)

**Interfaces:**
- Consumes: `retrieval_stats` CLI, 6 JSON của Task 6, `hard_expansion_cases.HARD_EXPANSION_CASES` (để lấy danh sách câu `new-45`).

- [ ] **Step 1: Phép so chính và các phép so phụ (spec §8)**

```bash
cd D:/Youdoo/.claude/worktrees/so-sanh-reranker/backend
R=evals/results/reranker-2026-09-18-mo-rong
PYTHONIOENCODING=utf-8 d:/Youdoo/backend/.venv/Scripts/python.exe -c "
import json; from evals.hard_expansion_cases import HARD_EXPANSION_CASES
json.dump({'per_case':[{'question':q,'difficulty':'hard','reciprocal_rank':0,'recall_at_final':0,'hit_ranks':[],'method':''} for q,_e,_d in HARD_EXPANSION_CASES]}, open('$R/new-45-questions.json','w',encoding='utf-8'), ensure_ascii=False)"
S="d:/Youdoo/backend/.venv/Scripts/python.exe -m evals.retrieval_stats"
echo "== CHINH: hard-62, 4B override vs bge hoa =="; PYTHONIOENCODING=utf-8 $S $R/bge-v2-m3.json $R/qwen3-4b-override.json --difficulty hard
echo "== new-45 rieng =="; PYTHONIOENCODING=utf-8 $S $R/bge-v2-m3.json $R/qwen3-4b-override.json --questions-from $R/new-45-questions.json
echo "== cong 3-4: toan bo ca =="; PYTHONIOENCODING=utf-8 $S $R/bge-v2-m3.json $R/qwen3-4b-override.json
for leg in qwen3-0.6b qwen3-4b qwen3-0.6b-override; do echo "== hard-62: $leg vs bge =="; PYTHONIOENCODING=utf-8 $S $R/bge-v2-m3.json $R/$leg.json --difficulty hard; done
```
Ghi nguyên văn mọi dòng ra vào spec §10.

- [ ] **Step 2: Áp quy tắc §8 — không diễn giải thêm**

XÁC NHẬN khi và chỉ khi CẢ BỐN: (1) `CI95` của phép so chính không chứa 0; (2) `p < 0,01`; (3) `recall_at_6` của `qwen3-4b-override.json` ≥ của `bge-v2-m3.json` (đọc trường `recall_at_6` của hai JSON); (4) dòng `VANG` của phép so "toàn bộ ca" rỗng. Bất kỳ điều nào hỏng → KHÔNG XÁC NHẬN. Không có kết luận thứ ba.

- [ ] **Step 3: Viết spec §10 và §11**

§10 *Ghi chép thực thi*: bảng 6 chân trên bộ mở rộng (r@6, mrr, easy/hard/trap, p50) + bảng đối chứng `old-64` + toàn bộ đầu ra Step 1 + ba mục **Khó khăn / Hướng chọn / Giới hạn còn lại** (kể cả: số nút bỏ và vì sao; số lần chân bị ngắt; `new-45` có đồng thuận với `hard-62` không).
§11 *Kết luận*: một trong hai câu, nguyên văn theo §8:
- **XÁC NHẬN** → "Tín hiệu +0,25 `hard mrr` của `qwen3-4b-override` được xác nhận trên n=<N>: chênh <x>, CI95 [<a>; <b>], p=<p>. Việc còn lại trước khi thay production: cổng lượng tử hoá (độ trễ + giữ `trap`/`mrr`) — không còn là câu hỏi recall."
- **KHÔNG XÁC NHẬN** → "Không xác nhận. Giữ `bge-reranker-v2-m3` + hoà 1:1. Dừng hướng đổi reranker; chuyển sang cải thiện pool (4B override đã chạm trần `recall@6 = recall@20`)."

- [ ] **Step 4: `docs/trang-thai-chung.md` #29** — thay nội dung "còn treo" bằng kết luận §11 và điều còn mở tương ứng; giữ đúng định dạng dòng hiện có.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-09-18-mo-rong-hard-set-design.md docs/trang-thai-chung.md backend/evals/results/reranker-2026-09-18-mo-rong/new-45-questions.json
git commit -m "docs(eval): ket luan mo rong hard-set theo quy tac dang ky truoc

<XAC NHAN | KHONG XAC NHAN>: hard-<N> chenh <x> CI95 [<a>;<b>] p=<p>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Cổng nghiệm thu

- [ ] Suite: `2758 passed, 1 skipped, 114 deselected` (hoặc giải thích từng ca lệch), 0 failed.
- [ ] `pytest tests/evals -m integration` xanh (nhãn tồn tại thật; `build_sample` ra 45).
- [ ] `git diff 50cde13 -- backend/evals/retrieval_cases.py` chỉ đổi tên `RETRIEVAL_CASES`→`_CORE` và thêm khối cuối; `test_64_ca_cu_khong_doi_mot_ky_tu` xanh.
- [ ] Chạy lại `sample_hard_sections` sau đóng băng cho JSON y hệt tệp đã commit (`TAI_LAP_OK`).
- [ ] Commit đóng băng (Task 5) có trước mọi JSON trong `reranker-2026-09-18-mo-rong/` theo `git log`.
- [ ] 6 JSON: `errors=0`, `methods_seen` đúng, `rerank_model`/`rerank_mode` khớp tên tệp.
- [ ] Đối chứng `old-64`: 6 chân đều `khac ≤ 1`, `lech ≤ 0,02`.
- [ ] Spec §11 là **một trong hai** câu nguyên văn của Task 7 Step 3; không có câu thứ ba, không có "đo thêm".
- [ ] `git status --porcelain` sạch; không `.stderr.log` nào được commit.

## Điều kế hoạch này CỐ Ý không làm

- Không chạy lại 6 chân 2026-09-17 (chúng là đối chứng).
- Không đổi `RERANK_MODEL` mặc định, không đổi production.
- Không mở rộng `trap`/`easy` (quyết định theo `hard`; `trap` n=16 vẫn yếu — ghi ở §10 giới hạn).
- Không chạy cổng lượng tử hoá cho 4B — chỉ có ý nghĩa nếu §11 là XÁC NHẬN, và là plan riêng.
