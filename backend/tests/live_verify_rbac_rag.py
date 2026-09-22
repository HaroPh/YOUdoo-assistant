# coding: utf-8
"""Probe sống 19b: cùng câu hỏi, 4 vai, qua backend THẬT, trên CẢ HAI tuyến
`rag` và `mixed` (spec 2026-09-21 §4/§5; task-7-brief.md 3 lần bổ sung của
controller).
Chạy TỪ backend/: python -m tests.live_verify_rbac_rag — cần backend :8002 (mã
worktree), YOUDOO_ROLE_MAP + YOUDOO_API_TOKEN trong env. Marker live; không vào
pytest thường.

Oracle theo MARKER + FOOTER, không theo chuỗi con "5%" ("15%" chứa "5%").

KIẾN TRÚC: `evaluate_rag`/`evaluate_mixed`/`expected_denied_message` là HÀM
THUẦN — nhận chuỗi, không mạng, không đọc env, không DB (test unit
tests/test_live_verify_rbac_rag_oracle.py chứng minh từng điều kiện đỏ được
mà không cần backend/launcher). `main()` chỉ làm việc I/O: gọi backend, in
nguyên văn từng câu trả lời, gọi hai hàm oracle, in tóm tắt, trả exit code.

── CÂU HỎI RAG (CAU_HOI) ────────────────────────────────────────────────────
Hỏi thẳng chính sách chiết khấu — không kèm dữ kiện ERP nào, nên tuyến `rag`
(không phải `mixed`) là tuyến hợp lý duy nhất. `rag_node` (nodes.py) trả CÂU
TỪ CHỐI TẤT ĐỊNH `rag_access.denied_message(role_cfg, hidden_classes)` NGUYÊN
VĂN cho vai bị chặn — không LLM, không footer trích dẫn — nên oracle so khớp
CHÍNH XÁC chuỗi đó (tính qua `expected_denied_message()`, không hardcode).

── CÂU HỎI MIXED (CAU_HOI_MIXED) ────────────────────────────────────────────
"Theo chính sách chiết khấu, sản phẩm [E-COM07] Large Cabinet hiện còn tồn
kho bao nhiêu, và nếu khách Azure Interior thuộc cấp thân thiết thì được giảm
giá bao nhiêu phần trăm?"

Vì sao câu này CHẮC CHẮN cần CẢ HAI vế:
  - "tồn kho Large Cabinet còn bao nhiêu" là một CON SỐ ERP THẬT — sản phẩm
    [E-COM07] Large Cabinet (product_id=20) là dữ liệu demo THẬT, đã verify
    trực tiếp qua XML-RPC ở tests/live_verify_skill_discount.py (PRODUCT_ID=20,
    UNIT_PRICE=320.0); truy vấn qua tool `get_stock` (erp_query/tools.py).
  - "khách cấp thân thiết được giảm bao nhiêu %" chỉ nằm trong
    discount_policy.docx — lớp tài liệu 'commercial' (rag/visibility.py),
    đúng lớp bị giấu với vai kho. "cấp thân thiết" → 5%, đã verify cùng file
    live-verify trên (UNIT_PRICE * 0.95).
  - Theo prompts.py (render_intent_router_prompt, quy tắc `intent`): "needs
    BOTH an internal document/policy AND specific live ERP records together"
    → `mixed`, với chính ví dụ khuôn "theo chính sách X, [sự kiện ERP] Y
    không?" — câu trên dùng ĐÚNG khuôn đó.
  - Câu KẾT THÚC BẰNG "?": lớp phủ quyết tất định `looks_like_question`
    (routing.py, `decide_route`) do đó vẫn thắng ngay cả khi Lớp 1 (LLM) lỡ
    đề cử `sop` (miền "chiết khấu") — câu hỏi không bao giờ bị kéo vào SOP
    ghi (discount_quote), nó CHỈ có thể đi `rag`/`mixed`/`erp_read`/`unknown`
    tuỳ Lớp 1 phân loại `intent`.

KHÔNG CHỨNG MINH TĨNH ĐƯỢC tuyến `mixed` sẽ thực sự được chọn — Lớp 1 là LLM
(routing.py docstring, "LỚP 1 — XÁC SUẤT"). ⚠️ TASK 8 BẮT BUỘC PHẢI XÁC NHẬN
TUYẾN THẬT SỰ ĐI (trace Langfuse hoặc log backend) TRƯỚC KHI TIN kết quả câu
mixed — nếu nó rơi vào `rag`/`erp_read` thay vì `mixed`, đó là "chưa đo được
tuyến mixed", không phải PASS/FAIL của tính năng.

Cũng vì lý do tương tự, oracle `count(DENIED_MARKER) == 1` không phân biệt
được "model tự viết thêm một câu từ chối bằng lời khác" (không chứa
DENIED_MARKER) — máy không bắt được ca đó. `main()` in NGUYÊN VĂN mọi câu trả
lời mixed (cả 4 vai) ra stdout để Task 8 đọc bằng mắt.

Chi phí: 2 câu hỏi × 4 vai = 8 lời gọi LLM thật (rag: 1 câu × 4 vai đã có từ
bản trước; mixed: thêm 1 câu × 4 vai, spec bổ sung). Task 7 KHÔNG chạy file
này — cần backend :8002 và tốn hạn mức thật; Task 8 chạy dưới giám sát.
"""
import sys
import uuid

from src.agents.rag_access import DENIED_MARKER, denied_message
from src.agents.roles import load_profile

NGUON_MONG_DOI = "discount_policy.docx"   # footer trích dẫn của 3 vai được xem
CAU_HOI = "Chính sách chiết khấu của công ty như thế nào?"
CAU_HOI_MIXED = (
    "Theo chính sách chiết khấu, sản phẩm [E-COM07] Large Cabinet hiện còn tồn "
    "kho bao nhiêu, và nếu khách Azure Interior thuộc cấp thân thiết thì được "
    "giảm giá bao nhiêu phần trăm?"
)


def expected_denied_message(profile: dict | None = None) -> str:
    """Câu từ chối TẤT ĐỊNH kỳ vọng cho vai kho khi hỏi chính sách chiết khấu
    (lớp tài liệu bị giấu = {'commercial'} — discount_policy.docx, spec
    2026-09-20 §3 / 2026-09-21 §4). TÍNH qua `rag_access.denied_message()`,
    KHÔNG hardcode chuỗi (yêu cầu controller task-7-brief.md, bổ sung lần 2).

    `profile` mặc định lấy qua `roles.load_profile()` — CÙNG cách production
    chọn hồ sơ đang dùng (biến môi trường YOUDOO_POLICY_PROFILE, mặc định
    'small-business'); truyền tay `profile` khi caller đã có sẵn (vd unit
    test, để không phụ thuộc env — xem yêu cầu "hàm thuần, không đọc env" cho
    evaluate_rag/evaluate_mixed; hàm NÀY được phép đọc env vì nó chỉ chạy từ
    main(), không từ oracle thuần)."""
    profile = load_profile() if profile is None else profile
    return denied_message(profile["warehouse"], frozenset({"commercial"}), profile)


def evaluate_rag(ket: dict[str, str], expected_denied: str) -> tuple[bool, str]:
    """Oracle THUẦN cho câu RAG (không mixed) — nhận các câu trả lời dạng
    chuỗi, KHÔNG mạng, KHÔNG env, KHÔNG DB. Trả (ok, dòng tóm tắt nêu ĐÚNG
    điều kiện nào trượt, để người đọc output ở Task 8 biết hỏng ở đâu).

    `expected_denied in kho` là PHÉP CHỨA (không phải so bằng tuyệt đối): vai
    kho phải mang NGUYÊN VĂN câu tất định ở đâu đó trong câu trả lời — đúng
    hành vi thật của rag_node (không LLM, không hậu tố), nhưng phép chứa (thay
    vì `==`) vẫn cho phép hai điều kiện `kho_tu_choi`/`kho_khong_trich` ĐỘC
    LẬP với nhau: câu tất định + một đoạn hậu tố lạc đề vẫn được `in` nhận ra
    là "có câu tất định", và bị bắt riêng bởi `kho_khong_trich` — hai ca đột
    biến khác nhau, hai dòng test khác nhau (xem
    tests/test_live_verify_rbac_rag_oracle.py)."""
    kho = ket["warehouse"]
    kho_tu_choi = expected_denied in kho
    kho_khong_trich = NGUON_MONG_DOI not in kho
    thay = {v: NGUON_MONG_DOI in ket[v] and DENIED_MARKER not in ket[v]
            for v in ("sales", "accounting", "admin")}
    ok = kho_tu_choi and kho_khong_trich and all(thay.values())
    summary = (f"[rag] kho từ chối đúng câu tất định: {kho_tu_choi} | "
               f"kho không trích lạc đề: {kho_khong_trich} | thấy footer: {thay} | "
               f"{'PASS' if ok else 'FAIL'}")
    return ok, summary


def evaluate_mixed(kho_mixed: str, expected_denied: str) -> tuple[bool, str]:
    """Oracle THUẦN cho câu MIXED của vai kho — cùng chữ ký thuần như
    `evaluate_rag`. Bốn điều kiện (spec bổ sung controller, đợt "phủ đường
    MIXED"):
      1. `DENIED_MARKER` xuất hiện ĐÚNG MỘT LẦN — bắt cả "mất câu từ chối"
         (0 lần) lẫn "câu từ chối tất định BỊ LẶP vì model tự viết thêm một
         câu của riêng nó" (≥2 lần).
      2. Câu trả lời KẾT THÚC bằng đúng câu tất định (`fuse_answer` nối nó
         vào CUỐI — fanout.py `answer.rstrip() + "\\n\\n" + doc_denied`).
      3. Phần ĐỨNG TRƯỚC câu từ chối không rỗng — phần ERP thật sự có mặt,
         không bị model/verify nuốt mất.
      4. Không trích tài liệu lạc đề (`NGUON_MONG_DOI` không xuất hiện) — vai
         kho vẫn bị chặn tài liệu thương mại dù đang ở tuyến mixed.
    Điều kiện (3) chỉ TÍNH ĐƯỢC khi (2) đúng (nếu câu trả lời không kết thúc
    bằng câu tất định thì không có vị trí nào để cắt "phần trước" cho đúng) —
    cố ý: fixture đột biến riêng cho (2) và (3) trong file test chứng minh cả
    hai vẫn ĐỘC LẬP theo nghĩa mutation-testing (tắt riêng từng điều kiện vẫn
    đổi kết quả của đúng ca test nhắm vào nó)."""
    expected = expected_denied.strip()
    dem = kho_mixed.count(DENIED_MARKER)
    dung_1_lan = dem == 1
    da_rstrip = kho_mixed.rstrip()
    ket_thuc_dung = da_rstrip.endswith(expected)
    phan_truoc = da_rstrip[: len(da_rstrip) - len(expected)].strip() if ket_thuc_dung else ""
    phan_truoc_khong_rong = bool(phan_truoc)
    khong_trich_lac_de = NGUON_MONG_DOI not in kho_mixed
    ok = dung_1_lan and ket_thuc_dung and phan_truoc_khong_rong and khong_trich_lac_de
    summary = (f"[mixed] marker đúng 1 lần: {dung_1_lan} (đếm={dem}) | "
               f"kết bằng câu tất định: {ket_thuc_dung} | "
               f"phần ERP trước đó không rỗng: {phan_truoc_khong_rong} | "
               f"không trích lạc đề: {khong_trich_lac_de} | "
               f"{'PASS' if ok else 'FAIL'}")
    return ok, summary


def main() -> int:
    from src.cli_console import use_utf8_streams
    use_utf8_streams()
    # Import lười: live_verify_common tự đọc .env lúc import (bọc
    # try/except FileNotFoundError nên KHÔNG bắt buộc, xác minh thủ công
    # trong test_import_khong_can_database_url_hay_env), nhưng để `main()`
    # là NƠI DUY NHẤT chạm I/O mạng/env theo đúng yêu cầu controller, phần
    # network vẫn được nạp ở đây, không ở top-level.
    from tests.live_verify_common import chat, load_env, role_user_id

    load_env()
    profile = load_profile()
    expected_denied = expected_denied_message(profile)

    ket = {}
    for vai in ("warehouse", "sales", "accounting", "admin"):
        uid = role_user_id(vai)
        if not uid:
            print(f"[ERR] không tìm thấy user id cho vai {vai} trong YOUDOO_ROLE_MAP")
            return 2
        tra_loi = chat([], f"19b-rag-{vai}-{uuid.uuid4().hex[:6]}", CAU_HOI, user_id=uid)
        ket[vai] = tra_loi
        print(f"\n=== rag/{vai} ===\n{tra_loi}\n")

    ket_mixed = {}
    for vai in ("warehouse", "sales", "accounting", "admin"):
        uid = role_user_id(vai)
        if not uid:
            print(f"[ERR] không tìm thấy user id cho vai {vai} trong YOUDOO_ROLE_MAP")
            return 2
        tra_loi = chat([], f"19b-mixed-{vai}-{uuid.uuid4().hex[:6]}",
                      CAU_HOI_MIXED, user_id=uid)
        ket_mixed[vai] = tra_loi
        print(f"\n=== mixed/{vai} ===\n{tra_loi}\n")

    ok_rag, tom_tat_rag = evaluate_rag(ket, expected_denied)
    ok_mixed, tom_tat_mixed = evaluate_mixed(ket_mixed["warehouse"], expected_denied)
    print(tom_tat_rag)
    print(tom_tat_mixed)
    print("⚠️ NHẮC: Task 8 phải xác nhận tuyến MIXED thật sự đi (trace Langfuse "
         "hoặc log backend) trước khi tin kết quả câu mixed ở trên — một câu từ "
         "chối tự viết bằng lời khác (không chứa marker) không bị máy bắt được.")
    ok = ok_rag and ok_mixed
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
