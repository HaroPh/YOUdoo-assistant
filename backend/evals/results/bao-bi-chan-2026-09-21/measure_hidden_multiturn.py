"""Đo C1 (review cuối nhánh): lượt bóng tính LƯỢT TRƯỚC với trọng số đầy đủ.

Bằng chứng tái lập được cho quyết định "lượt bóng chỉ dùng câu hiện tại"
(`src/rag/retrieve.py`, sóng sửa cuối sau review toàn nhánh, 2026-09-22) —
đưa vào repo theo ruling của controller ở sóng sửa cuối (xem spec
`2026-09-21-bao-bi-chan-tang-rag-design.md` §10 Task 11) để bằng chứng không
biến mất khi workspace SDD bị dọn.

Chỉ đọc — KHÔNG sửa mã production. Nhúng qua Ollama MỘT LẦN cho mỗi câu (109
câu), rồi ghép cặp từ các tuple đã tính, nên các cặp chỉ tốn SQL.

Hai chế độ so sánh, CÙNG cặp (lượt trước, lượt này):
  with_prev     — prepared = [câu này, câu trước]   (đúng như retrieve() TRƯỚC sửa)
  current_only  — prepared = [câu này]              (đúng như retrieve() SAU sửa)

Đo ba loại cặp:
  A. lượt trước = ca THƯƠNG MẠI, lượt này = ca KHÁC (990)  -> mỗi ca là TỪ CHỐI OAN
     (đúng luồng "vừa bị từ chối, giờ hỏi việc khác" của C1)
  B. lượt trước = ca KHÁC, lượt này = ca KHÁC              -> mỗi ca là TỪ CHỐI OAN
     (đối chứng: lệch nền mà không cần lượt trước thương mại)
  C. lượt trước = ca KHÁC, lượt này = ca THƯƠNG MẠI        -> có là BẮT ĐÚNG
     (chỉ-câu-hiện-tại không được làm mất phát hiện của chính câu hiện tại)

TỰ CHỨNG: chế độ current_only với lượt trước bất kỳ phải cho ĐÚNG kết quả
một-lượt của cổng ÂM (9/10 thương mại có cờ, 0/99 khác có cờ — Task 9). Nếu
lệch, script này sai.

Chạy như MỘT SCRIPT, không phải `-m` (thư mục kết quả có dấu `-` trong tên,
không phải identifier hợp lệ cho import theo module) — cwd PHẢI là `backend/`
để `sys.path.insert(0, ".")` thấy được `evals`/`src`, và `DATABASE_URL`/
`OLLAMA_URL` phải đã có trong môi trường (`.env` đã nạp, hoặc set tay):
    python evals/results/bao-bi-chan-2026-09-21/measure_hidden_multiturn.py
Xem README cùng thư mục cho lệnh đầy đủ kèm nạp môi trường. 109 lượt gọi Ollama
(một lần nhúng mỗi câu trong 109 câu của bộ ca; các cặp lượt-trước/lượt-này ghép
lại từ các vector đã nhúng, không nhúng lại) — vài phút, không gọi LLM.
"""
import random
import sys

sys.path.insert(0, ".")

from evals.compare_visibility import _is_commercial_case          # noqa: E402
from evals.retrieval_cases import RETRIEVAL_CASES                 # noqa: E402
from src.cli_console import use_utf8_streams                      # noqa: E402
from src.rag import retrieve as rt                                # noqa: E402
from src.rag.db import connect                                    # noqa: E402
from src.rag.embed import embed_query                             # noqa: E402
from src.rag.visibility import UNRESTRICTED, resolve               # noqa: E402

WAREHOUSE_VISIBILITY = resolve(frozenset({"all"}))
N_OTHER_OTHER_SAMPLE = 400   # số cặp ngẫu nhiên cho loại B (99*98 quá nhiều)
SEED = 20260922


def _prepared_tuple(q: str):
    return (embed_query(q), rt.segment_vi(q), rt.fold_vi(q))


def _flags_hidden(conn, prepared) -> bool:
    shadow, _fold = rt._fuse_legs(conn, prepared, UNRESTRICTED)
    return bool(rt._hidden_in_top_k(shadow, WAREHOUSE_VISIBILITY))


def main() -> int:
    use_utf8_streams()
    commercial = [q for q, e, _d in RETRIEVAL_CASES if _is_commercial_case(e)]
    other = [q for q, e, _d in RETRIEVAL_CASES if not _is_commercial_case(e)]
    print(f"thuong mai = {len(commercial)} | khac = {len(other)} — dang nhung...",
          flush=True)
    prepared = {q: _prepared_tuple(q) for q in commercial + other}
    conn = connect()
    try:
        # Tự chứng một-lượt
        single_turn_commercial = sum(_flags_hidden(conn, [prepared[q]]) for q in commercial)
        single_turn_other = sum(_flags_hidden(conn, [prepared[q]]) for q in other)
        print(f"[tu chung] mot luot: thuong mai co co {single_turn_commercial}/{len(commercial)}, "
              f"khac co co {single_turn_other}/{len(other)}  (phai la 9/10 va 0/99)", flush=True)

        # A: trước = thương mại, nay = khác
        a_with_prev = a_current_only = 0
        examples = []
        for p in commercial:
            for q in other:
                with_prev = _flags_hidden(conn, [prepared[q], prepared[p]])
                current_only = _flags_hidden(conn, [prepared[q]])
                a_with_prev += with_prev
                a_current_only += current_only
                if with_prev and not current_only and len(examples) < 5:
                    examples.append((p, q))
        n_a = len(commercial) * len(other)
        print(f"\nA. truoc=THUONG MAI, nay=KHAC ({n_a} cap) — TU CHOI OAN:")
        print(f"   with_prev: {a_with_prev}/{n_a} ({100*a_with_prev/n_a:.1f}%)   "
              f"current_only: {a_current_only}/{n_a}")
        for p, q in examples:
            print(f"   vi du: truoc='{p[:40]}' -> nay='{q[:40]}'")

        # B: trước = khác, nay = khác (mẫu ngẫu nhiên)
        rng = random.Random(SEED)
        pairs_b = [(p, q) for p in other for q in other if p != q]
        rng.shuffle(pairs_b)
        pairs_b = pairs_b[:N_OTHER_OTHER_SAMPLE]
        b_with_prev = sum(_flags_hidden(conn, [prepared[q], prepared[p]]) for p, q in pairs_b)
        b_current_only = sum(_flags_hidden(conn, [prepared[q]]) for p, q in pairs_b)
        print(f"\nB. truoc=KHAC, nay=KHAC ({len(pairs_b)} cap ngau nhien, seed {SEED}) — TU CHOI OAN:")
        print(f"   with_prev: {b_with_prev}/{len(pairs_b)}   current_only: {b_current_only}/{len(pairs_b)}")

        # C: trước = khác, nay = thương mại
        c_with_prev = c_current_only = 0
        for p in other:
            for q in commercial:
                c_with_prev += _flags_hidden(conn, [prepared[q], prepared[p]])
                c_current_only += _flags_hidden(conn, [prepared[q]])
        n_c = len(other) * len(commercial)
        print(f"\nC. truoc=KHAC, nay=THUONG MAI ({n_c} cap) — BAT DUNG:")
        print(f"   with_prev: {c_with_prev}/{n_c} ({100*c_with_prev/n_c:.1f}%)   "
              f"current_only: {c_current_only}/{n_c} ({100*c_current_only/n_c:.1f}%)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
