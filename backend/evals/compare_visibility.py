# backend/evals/compare_visibility.py
"""Cổng ÂM của 19b — so hai lượt `--set retrieval`: admin (không lọc) và một
vai bị chặn (spec 2026-09-20 §7).

Bất biến:
  (a) ca THUẦN thương mại (mọi nhãn mong đợi thuộc DOC_VISIBILITY) →
      recall_at_pool của vai bị chặn == 0. Không phải "thấp": bằng 0.
  (b) ca khác → recall_at_pool bị chặn >= admin. Gỡ ứng viên không-đáp-án
      khỏi pool 20 không đẩy được đáp án ra, chỉ kéo được vào.
  (c) cờ `hidden` phải bật ở mọi ca thuần thương mại và tắt ở mọi ca khác —
      precision/recall của phép báo bị chặn (Task 6, spec 2026-09-21 §3).
recall_at_final CHỈ báo cáo: pool khác → reranker thấy tập khác.

Trước khi so ca, compare() còn đòi hỏi CHÍNH LƯỢT ĐO có ý nghĩa — thiếu điều
này cổng qua được mà không chứng minh gì (vd so hai lượt kho, hay so một tệp
với chính nó):
  (d) vế admin phải tự khai role="admin" (khoá `role` trong JSON, thêm ở
      Task 7);
  (e) vế bị chặn phải khai một role KHÁC vế admin;
  (f) vế admin phải THẬT SỰ thấy ít nhất một ca thương mại (recall_at_pool >
      0) — nếu không, "admin" ở đây có thể cũng đang bị chặn hoặc nạp nhầm
      tệp, và phép so sánh không đo được gì.

Chạy: python -m evals.compare_visibility admin.json warehouse.json → exit 0/1.
"""
import json
import sys

from evals.retrieval_cases import RETRIEVAL_CASES
from src.cli_console import use_utf8_streams
from src.rag.visibility import DOC_VISIBILITY, basename


def _is_commercial_case(expected) -> bool | None:
    """True/False, hoặc None nếu LẪN (có cả hai loại tệp)."""
    kinds = {basename(doc) in DOC_VISIBILITY for doc, _section in expected}
    return None if len(kinds) == 2 else kinds.pop()


def compare(admin: dict, restricted: dict, cases=RETRIEVAL_CASES) -> dict:
    # Cổng ÂM chỉ chứng minh điều gì nếu vế "admin" THẬT SỰ là admin và vế
    # "restricted" THẬT SỰ là một vai KHÁC — không kiểm hai điều này thì so
    # hai lượt kho với nhau, hay so một tệp với chính nó, vẫn in PASS mà
    # không đo được gì (đã xảy ra: hai JSON tự khai `role` từ Task 7, nhưng
    # compare() trước bản sửa này chưa từng đọc khoá đó).
    admin_role = admin.get("role", "admin")
    if admin_role != "admin":
        raise ValueError(f"vế admin không phải vai admin: role={admin_role!r}")
    restricted_role = restricted.get("role")
    if restricted_role == admin_role:
        raise ValueError(
            f"hai vế cùng vai ({admin_role!r}) — cổng ÂM cần so HAI vai KHÁC "
            f"nhau, không so một vai với chính nó (hay hai lượt cùng vai)")
    by_q_admin = {r["question"]: r for r in admin["per_case"]}
    by_q_res = {r["question"]: r for r in restricted["per_case"]}
    leaked, regressed = [], []
    unflagged, flagged = [], []
    n_commercial = n_other = 0
    admin_thay_thuong_mai = False
    for question, expected, _difficulty in cases:
        if question not in by_q_admin or question not in by_q_res:
            raise ValueError(f"thiếu ca ở một bên: {question!r}")
        kind = _is_commercial_case(expected)
        if kind is None:
            raise ValueError(f"ca lẫn (nhãn từ cả tệp thương mại lẫn tệp khác), "
                             f"không xếp được: {question!r}")
        a, r = by_q_admin[question], by_q_res[question]
        if kind:
            n_commercial += 1
            if a["recall_at_pool"] > 0:
                admin_thay_thuong_mai = True
            if r["recall_at_pool"] != 0:
                leaked.append({"question": question, "recall_at_pool": r["recall_at_pool"]})
            # KeyError trên recall_at_pool phải nổ TRƯỚC — giữ hành vi cũ cho
            # ca thiếu khoá (test_thieu_khoa_trong_mot_ca_bao_loi_ngay_khong_lang_le).
            if "hidden" not in r:
                raise ValueError(f"thiếu khoá 'hidden' ở vế bị chặn cho ca {question!r} — "
                                 f"chạy lại eval sau khi retrieve() có hidden_classes")
            if not r["hidden"]:
                unflagged.append({"question": question})
        else:
            n_other += 1
            if r["recall_at_pool"] < a["recall_at_pool"]:
                regressed.append({"question": question,
                                  "admin": a["recall_at_pool"],
                                  "restricted": r["recall_at_pool"]})
            if "hidden" not in r:
                raise ValueError(f"thiếu khoá 'hidden' ở vế bị chặn cho ca {question!r} — "
                                 f"chạy lại eval sau khi retrieve() có hidden_classes")
            if r["hidden"]:
                flagged.append({"question": question, "recall_at_pool": r["recall_at_pool"]})
    if n_commercial and not admin_thay_thuong_mai:
        raise ValueError(
            "vế admin không thấy tài liệu thương mại ở BẤT KỲ ca nào "
            "(recall_at_pool = 0 trên toàn bộ ca thương mại) — không giống "
            "một lượt đo không-lọc thật, cổng không chứng minh được gì")
    return {"ok": not leaked and not regressed and not unflagged and not flagged,
            "n_commercial": n_commercial, "n_other": n_other,
            "commercial_leaked": leaked, "regressed": regressed,
            "commercial_unflagged": unflagged, "other_flagged": flagged}


def main(argv=None) -> int:
    use_utf8_streams()
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("dùng: python -m evals.compare_visibility <admin.json> <restricted.json>")
        return 2
    admin = json.load(open(argv[0], encoding="utf-8"))
    restricted = json.load(open(argv[1], encoding="utf-8"))
    result = compare(admin, restricted)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"CỔNG ÂM {'PASS' if result['ok'] else 'FAIL'} — thương mại {result['n_commercial']} ca "
          f"(lộ {len(result['commercial_leaked'])}, không báo chặn {len(result['commercial_unflagged'])}), "
          f"khác {result['n_other']} ca (kém đi {len(result['regressed'])}, "
          f"từ chối oan {len(result['other_flagged'])})")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
