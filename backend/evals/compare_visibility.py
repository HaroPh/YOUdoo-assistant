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
      NGOẠI LỆ (Task 10): các câu trong KNOWN_UNFLAGGED được miễn — nhưng
      LỘ và TỪ CHỐI OAN không bao giờ được miễn, và mỗi lượt chạy đều tự
      kiểm mục rữa (ca đã biết lại bắt được cờ, hoặc biến mất khỏi bộ ca).
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

# Danh sách ngoại lệ CÓ KIỂM MỤC RỮA (Task 10, controller quyết 2026-09-22).
#
# Sau khi đổi sang top-3 (Task 9), cổng ÂM chạy thật bắt được 9/10 ca thương
# mại, 0 lộ, 0 từ chối oan — đúng điều chủ dự án đã chọn khi xem bảng top-k.
# Ca còn sót, đo 2026-09-22: tài liệu bị giấu (sla.docx, Điều 4 — Đóng gói và
# vận chuyển) đứng hạng > 5 trong bản bóng KHÔNG lọc (unfiltered pass), nên
# KHÔNG có giá trị k nào (kể cả top-20) bắt được ca này — đây KHÔNG phải lỗi
# của luật top-3, mà là giới hạn của chính lượt truy xuất. Vì cổng là nhị
# phân (mọi danh sách phải rỗng), ca này sẽ khiến cổng FAIL VĨNH VIỄN nếu
# không được miễn — và một cổng đỏ vĩnh viễn là cổng người ta học cách bỏ
# qua (repo này đã dính lằn đó nhiều lần).
#
# NGUY HIỂM: danh sách miễn là cách một cổng âm thầm mất giá trị. Vì vậy
# compare() dưới đây tự kiểm mục RỮA mỗi lượt chạy: nếu ca này lại bắt được
# cờ (retrieval cải thiện) hoặc biến mất khỏi bộ ca (đổi tên/xoá câu hỏi),
# cổng phải FAIL và báo XOÁ dòng tương ứng khỏi hằng này — không được để nó
# âm thầm che một ca đã sửa được, như đã từng xảy ra với danh sách ngoại lệ
# của contract test GATHER_CASES (không có kiểm rữa).
KNOWN_UNFLAGGED = frozenset({
    "bên bán phải đóng gói hàng ra sao trước khi chuyển đi?",
})


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
    unflagged, unflagged_known, unflagged_new, flagged = [], [], [], []
    known_stale = []
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
            # Lộ KHÔNG BAO GIỜ được miễn — kiểm này không tra KNOWN_UNFLAGGED,
            # dù câu hỏi có nằm trong danh sách miễn hay không.
            if r["recall_at_pool"] != 0:
                leaked.append({"question": question, "recall_at_pool": r["recall_at_pool"]})
            # KeyError trên recall_at_pool phải nổ TRƯỚC — giữ hành vi cũ cho
            # ca thiếu khoá (test_thieu_khoa_trong_mot_ca_bao_loi_ngay_khong_lang_le).
            if "hidden" not in r:
                raise ValueError(f"thiếu khoá 'hidden' ở vế bị chặn cho ca {question!r} — "
                                 f"chạy lại eval sau khi retrieve() có hidden_classes")
            if not r["hidden"]:
                # commercial_unflagged vẫn trả ĐẦY ĐỦ — ca miễn KHÔNG bị lọc
                # bớt khỏi kết quả, chỉ được xếp thêm vào known/new bên dưới.
                unflagged.append({"question": question})
                if question in KNOWN_UNFLAGGED:
                    unflagged_known.append({"question": question})
                else:
                    unflagged_new.append({"question": question})
            elif question in KNOWN_UNFLAGGED:
                # KIỂM MỤC RỮA: câu này được liệt vào KNOWN_UNFLAGGED vì đo
                # 2026-09-22 nó KHÔNG bắt được cờ — nhưng lượt này lại bắt
                # được (hidden=True). Retrieval đã cải thiện, danh sách miễn
                # không còn cần nữa → đây là mục rữa, không phải PASS.
                known_stale.append({
                    "question": question,
                    "reason": ("đã bắt được cờ (hidden=True) ở lượt này — "
                               "xoá câu này khỏi KNOWN_UNFLAGGED")})
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
    # KIỂM MỤC RỮA loại 2: câu trong KNOWN_UNFLAGGED mà KHÔNG còn xuất hiện
    # trong bộ ca (ai đó đổi tên/xoá câu hỏi) — vòng lặp trên chỉ đi qua các
    # câu CÓ trong `cases` nên phải kiểm riêng bằng hiệu tập hợp.
    case_questions = {q for q, _expected, _difficulty in cases}
    for question in sorted(KNOWN_UNFLAGGED - case_questions):
        known_stale.append({
            "question": question,
            "reason": ("không còn trong bộ ca (đổi tên/xoá câu hỏi) — "
                       "xoá câu này khỏi KNOWN_UNFLAGGED")})
    return {"ok": (not leaked and not regressed and not flagged
                   and not unflagged_new and not known_stale),
            "n_commercial": n_commercial, "n_other": n_other,
            "commercial_leaked": leaked, "regressed": regressed,
            "commercial_unflagged": unflagged,
            "commercial_unflagged_known": unflagged_known,
            "commercial_unflagged_new": unflagged_new,
            "known_stale": known_stale,
            "other_flagged": flagged}


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
    # Banner phải NÊU RÕ số ca được miễn — không giấu rằng ngoại lệ đang áp
    # dụng. Dùng .get() cho ba khoá mới (commercial_unflagged_known/_new,
    # known_stale) để không phá test mock main() cũ vốn trả dict không có
    # các khoá này.
    n_known = len(result.get("commercial_unflagged_known", []))
    n_new = len(result.get("commercial_unflagged_new", []))
    known_stale = result.get("known_stale", [])
    banner = (f"CỔNG ÂM {'PASS' if result['ok'] else 'FAIL'} — thương mại {result['n_commercial']} ca "
              f"(lộ {len(result['commercial_leaked'])}, "
              f"không báo chặn {len(result['commercial_unflagged'])}"
              f" — trong đó {n_known} ca đã biết được miễn, {n_new} ca mới), "
              f"khác {result['n_other']} ca (kém đi {len(result['regressed'])}, "
              f"từ chối oan {len(result['other_flagged'])})")
    if known_stale:
        banner += (f" — RỮA {len(known_stale)} ca trong KNOWN_UNFLAGGED, "
                   f"xem 'known_stale' để xoá")
    print(banner)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
