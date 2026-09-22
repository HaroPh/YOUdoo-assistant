"""Đo: nếu đổi luật "hạng-1" thành "có lớp bị giấu trong top-k" thì bắt thêm được
bao nhiêu ca thương mại, và trả giá bao nhiêu ca TỪ CHỐI OAN?

Bằng chứng tái lập được cho quyết định `HIDDEN_TOP_K = 3` (`src/rag/retrieve.py`,
Task 9, spec `2026-09-21-bao-bi-chan-tang-rag-design.md` §3/§6.3) — được đưa vào
repo theo ruling của `final-fix-findings.md` (sóng sửa cuối, 2026-09-22) để bằng
chứng không biến mất khi workspace SDD bị dọn.

Chỉ đọc — KHÔNG sửa mã production. Chạy cục bộ: embed qua Ollama, truy vấn
Postgres. Không gọi LLM.

In bảng k = 1..5 (MỘT LƯỢT, không `aux` — `shadow_classes()` gọi
`_prepare_queries(question, ())`, không phụ thuộc `HIDDEN_TOP_K` hiện hành của
`retrieve.py` vì tự tính hạng bằng chính `_fuse_legs`): (bắt được / 10 ca
thương mại) và (từ chối oan / 99 ca khác).

TỰ CHỨNG: hàng k=1 của bảng phải khớp ĐÚNG số đo cổng ÂM thật đã chạy với luật
hạng-1 gốc, Task 8 (5/10 · 0/99) — công thức hạng ở đây độc lập với hằng
`HIDDEN_TOP_K` hiện tại nên đây là một phép kiểm tra chéo thật, không phải
hằng đúng. Nếu k=1 lệch khỏi 5/10 · 0/99, script này sai, đừng tin số của nó.

Chạy như MỘT SCRIPT, không phải `-m` (thư mục kết quả có dấu `-` trong tên,
không phải identifier hợp lệ cho import theo module) — cwd PHẢI là `backend/`
để `sys.path.insert(0, ".")` thấy được `evals`/`src`, và `DATABASE_URL`/
`OLLAMA_URL` phải đã có trong môi trường (`.env` đã nạp, hoặc set tay):
    python evals/results/bao-bi-chan-2026-09-21/measure_hidden_topk.py
Xem README cùng thư mục cho lệnh đầy đủ kèm nạp môi trường.
"""
import sys

sys.path.insert(0, ".")

from evals.compare_visibility import _is_commercial_case          # noqa: E402
from evals.retrieval_cases import RETRIEVAL_CASES                 # noqa: E402
from src.cli_console import use_utf8_streams                      # noqa: E402
from src.rag import retrieve as rt                                # noqa: E402
from src.rag.db import connect                                    # noqa: E402
from src.rag.visibility import UNRESTRICTED, resolve               # noqa: E402

WAREHOUSE_VISIBILITY = resolve(frozenset({"all"}))
MAX_K = 5


def shadow_classes(conn, question: str) -> list[str]:
    """Lớp của top-MAX_K ứng viên trong bản BÓNG (không lọc), dùng chính
    đường mã của retrieve(): cùng _prepare_queries, cùng _fuse_legs, cùng RRF."""
    prepared = rt._prepare_queries(question, ())
    fused, _fold = rt._fuse_legs(conn, prepared, UNRESTRICTED)
    if not fused:
        return []
    ordered = sorted(fused.values(), key=lambda e: e["rrf"], reverse=True)
    return [e["row"][rt.VIS_IDX] for e in ordered[:MAX_K]]


def main() -> int:
    use_utf8_streams()
    conn = connect()
    try:
        caught = {k: 0 for k in range(1, MAX_K + 1)}
        false_refusal = {k: 0 for k in range(1, MAX_K + 1)}
        n_commercial = n_other = 0
        detail = []
        for question, expected, _difficulty in RETRIEVAL_CASES:
            is_commercial = _is_commercial_case(expected)
            classes = shadow_classes(conn, question)
            hidden_positions = [i for i, c in enumerate(classes)
                                if c not in WAREHOUSE_VISIBILITY]
            first_hidden_rank = (hidden_positions[0] + 1) if hidden_positions else None
            if is_commercial:
                n_commercial += 1
                detail.append((first_hidden_rank, question))
            else:
                n_other += 1
            for k in range(1, MAX_K + 1):
                hit = first_hidden_rank is not None and first_hidden_rank <= k
                if is_commercial and hit:
                    caught[k] += 1
                if (not is_commercial) and hit:
                    false_refusal[k] += 1
        print(f"ca thuong mai = {n_commercial} | ca khac = {n_other}\n")
        print(f"{'k':>2}  {'bat duoc':>12}  {'tu choi oan':>12}")
        for k in range(1, MAX_K + 1):
            print(f"{k:>2}  {str(caught[k]) + '/' + str(n_commercial):>12}  "
                  f"{str(false_refusal[k]) + '/' + str(n_other):>12}")
        print("\nHang cua tai lieu BI GIAU dau tien trong ban bong, tung ca thuong mai:")
        for rank, q in sorted(detail, key=lambda t: (t[0] is None, t[0] or 0)):
            print(f"  hang={rank if rank else '>%d' % MAX_K:>3}  {q[:66]}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
