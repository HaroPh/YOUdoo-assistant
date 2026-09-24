"""Lưới {luật cũ, luật mới} × k ∈ 1…6 trên CORPUS PRODUCTION.

Bản song sinh của `measure_grid.py` (chạy trên bench ngoài). Cần CẢ HAI vì
chúng trả lời hai câu khác nhau:
  - bench ngoài: mật độ `commercial` 27–40% chunk ⇒ nơi DUY NHẤT nhìn thấy
    được mặt hại của luật, nhưng nhãn là GIẢ LẬP (bộ từ khoá);
  - production: mật độ 24/3.901 = 0,6%, nhãn THẬT, nhưng chỉ 10 ca thương mại
    nên quá nhỏ để chốt một ngưỡng.
Chốt k theo bench, XÁC NHẬN không hồi quy theo production.

TỰ CHỨNG (bắt buộc đọc trước khi tin số): hàng `cũ` k=1 phải ra 5/10 · 0/99 và
hàng `cũ` k=3 phải ra 9/10 · 0/99 — đúng hai mốc đã đo của 19c (spec
`2026-09-21-bao-bi-chan-tang-rag-design.md` §3, và `measure_hidden_topk.py`
cùng repo). Công thức ở đây tự tính hạng bằng `_fuse_legs`, KHÔNG đọc hằng
`HIDDEN_TOP_K` hiện hành, nên đây là phép kiểm chéo thật. Lệch là script sai —
đừng tin số của nó.

Chỉ ĐỌC, không sửa mã production. Không gọi LLM.

Chạy như MỘT SCRIPT (thư mục có dấu `-`, không import theo module được), cwd
phải là `backend/`, `DATABASE_URL`/`OLLAMA_URL` đã có trong môi trường:
    python evals/results/luat-top3-2026-09-24/measure_grid_production.py
"""
import sys

sys.path.insert(0, ".")

from evals.compare_visibility import _is_commercial_case          # noqa: E402
from evals.retrieval_cases import RETRIEVAL_CASES                 # noqa: E402
from evals.retrieval_score import label_of, label_matches         # noqa: E402
from src.cli_console import use_utf8_streams                      # noqa: E402
from src.rag import retrieve as rt                                # noqa: E402
from src.rag.config import TOP_K                                  # noqa: E402
from src.rag.db import connect                                    # noqa: E402
from src.rag.visibility import UNRESTRICTED, resolve              # noqa: E402

KHO = resolve(frozenset({"all"}))
MAX_K = 6

# Hai mốc đã đo của 19c, dùng cho TỰ CHỨNG. Không phải hằng đúng — chúng đến
# từ cổng ÂM thật (Task 8) và bảng k (Task 9).
TU_CHUNG = {1: (5, 0), 3: (9, 0)}


def lop_bong(conn, question: str) -> list[str]:
    """Lớp của top-MAX_K ứng viên trong lượt BÓNG (không lọc) — cùng đường mã
    production: cùng `_prepare_queries`, cùng `_fuse_legs`, cùng RRF."""
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
        # [luật][k] -> số ca
        bat = {"cũ": {k: 0 for k in range(1, MAX_K + 1)},
               "mới": {k: 0 for k in range(1, MAX_K + 1)}}
        oan = {"cũ": {k: 0 for k in range(1, MAX_K + 1)},
               "mới": {k: 0 for k in range(1, MAX_K + 1)}}
        n_tm = n_khac = 0
        for question, expected, _difficulty in RETRIEVAL_CASES:
            la_tm = _is_commercial_case(expected)
            if la_tm is None:          # ca LẪN hai loại tệp — bỏ, như 19c
                continue
            lop = lop_bong(conn, question)
            # Vai kho CÓ tìm đúng đáp án trong top-6 của lượt LỌC không?
            res = rt.retrieve(question, TOP_K, conn, (), visibility=KHO)
            want = {tuple(x) for x in expected}
            tim_dung = any(label_matches(label_of(c), w)
                           for c in res.chunks for w in want)
            if la_tm:
                n_tm += 1
            else:
                n_khac += 1
            for k in range(1, MAX_K + 1):
                topk = lop[:k]
                cu = any(c not in KHO for c in topk)
                moi = not any(c in KHO for c in topk)
                for ten, tu_choi in (("cũ", cu), ("mới", moi)):
                    if la_tm and tu_choi:
                        bat[ten][k] += 1
                    if (not la_tm) and tu_choi and tim_dung:
                        oan[ten][k] += 1

        print(f"ca thương mại = {n_tm} | ca khác = {n_khac}\n")
        print(f"{'k':>2}  {'luật':<5} {'bắt đúng':>12}  {'từ chối oan (đã tìm đúng)':>27}")
        for ten in ("cũ", "mới"):
            for k in range(1, MAX_K + 1):
                print(f"{k:>2}  {ten:<5} {f'{bat[ten][k]}/{n_tm}':>12}  "
                      f"{f'{oan[ten][k]}/{n_khac}':>27}")
            print()

        loi = [f"k={k}: đo ({bat['cũ'][k]}, {oan['cũ'][k]}) ≠ mốc 19c {mong}"
               for k, mong in TU_CHUNG.items()
               if (bat["cũ"][k], oan["cũ"][k]) != mong]
        if loi:
            print("TỰ CHỨNG THẤT BẠI — script sai, ĐỪNG tin số ở trên:")
            for x in loi:
                print(f"  {x}")
            return 1
        print(f"TỰ CHỨNG ĐẠT: luật cũ k=1 → {TU_CHUNG[1]}, k=3 → {TU_CHUNG[3]}, "
              f"khớp mốc 19c.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
