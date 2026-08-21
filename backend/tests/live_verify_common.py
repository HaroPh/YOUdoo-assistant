# backend/tests/live_verify_common.py
"""Helper dùng chung cho 3 script live-verify skill agentic (warehouse/delivery/
discount). Tái dùng erp_query.transport.XmlRpcTransport thay vì hand-roll
xmlrpc.client riêng — tránh lặp lại cách làm thủ công của các script scratchpad
live-verify trước đây. Xem docs/superpowers/specs/2026-07-17-agentic-skill-eval-jobs-design.md."""
import json
import os
from dataclasses import dataclass, field

import requests

from src.erp_query.transport import XmlRpcTransport
from src.agents.tool_leak_guard import TOOL_NAME_LEAK_MARKERS, has_tool_leak  # noqa: F401


def load_env(env_path: str | None = None) -> None:
    """Đọc .env, setdefault vào os.environ (idempotent — an toàn gọi nhiều lần,
    không ghi đè biến đã set sẵn trong môi trường gọi). Test script tự đọc .env
    thay vì bắt caller export tay."""
    path = env_path or os.path.join(os.path.dirname(__file__), "../../.env")
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


try:
    load_env()
except FileNotFoundError:      # .env không track git — vắng mặt là hợp lệ
    pass
BASE_URL = f"http://localhost:{os.environ.get('BACKEND_PORT', '8002')}"
CHAT_ENDPOINT = f"{BASE_URL}/v1/chat/completions"


def odoo_transport() -> XmlRpcTransport:
    load_env()
    return XmlRpcTransport(os.environ["ODOO_URL"], os.environ["ODOO_DB"],
                           os.environ["ODOO_USERNAME"], os.environ["ODOO_PASSWORD"])


# Model đã thật sự phục vụ lượt nghiệm thu này.
#
# VÌ SAO CẦN. Cạn hạn mức KHÔNG chỉ gây lỗi — nó làm lượt gọi TỤT xuống mắt
# xích yếu hơn, và model yếu vẫn trả lời trôi chảy nhưng bỏ qua chỉ dẫn trong
# SOP. Nhìn từ ngoài, thứ đó KHÔNG phân biệt được với một lỗi hành vi thật.
#
# Đo được 2026-08-21: `e2e-skill-warehouse` đỏ 2/5, trong đó `no_po_tool_leak`
# chạy đủ 3 lượt, không lỗi, chỉ thiếu câu bridge mà SOP dặn. Tôi dự đoán đổi
# khoá sẽ KHÔNG chữa được nó (vì nó không phải lỗi hạ tầng) — đổi khoá xong nó
# PASS. Dự đoán sai vì không ai nhìn thấy model nào đã trả lời.
MODELS_DA_PHUC_VU: set[str] = set()


def role_user_id(role: str | None = None) -> str | None:
    """Id người dùng Open WebUI ứng với một vai, suy từ `YOUDOO_ROLE_MAP`.

    VÌ SAO CẦN: backend Youdoo suy vai từ header `x-openwebui-user-id`
    (main._role_from_headers) và **TỪ CHỐI** khi không suy được — trả
    "Không xác định được quyền truy cập của bạn" chứ không mặc định thành
    admin. Helper này được port sang Youdoo ở SP-1B nhưng `chat()` không gửi
    header nào, nên mọi script dùng nó sẽ nhận câu từ chối thay vì câu trả
    lời thật. Lỗi nằm im vì tới 2026-08-21 helper KHÔNG CÓ script nào gọi.

    Không ghi cứng id vào mã: id là dữ liệu môi trường, và ghi cứng thì máy
    khác chạy sẽ hỏng câm. Trả None khi không suy được — caller vẫn gửi được
    (backend sẽ từ chối rõ ràng), tốt hơn là nổ ở đây với thông điệp mờ hơn.
    """
    want = role or os.environ.get("YOUDOO_LIVE_VERIFY_ROLE", "admin")
    for muc in os.environ.get("YOUDOO_ROLE_MAP", "").split(","):
        if ":" not in muc:
            continue
        uid, _, vai = muc.strip().partition(":")
        if vai.strip() == want:
            return uid.strip()
    return None


def chat(history: list[dict], sid: str, msg: str,
         user_id: str | None = None) -> str:
    history.append({"role": "user", "content": msg})
    body = {"model": "erp-assistant", "session_id": sid,
           "messages": history, "stream": False}
    headers = {}
    uid = user_id if user_id is not None else role_user_id()
    if uid:
        headers["x-openwebui-user-id"] = uid
    r = requests.post(CHAT_ENDPOINT, json=body, headers=headers, timeout=150)
    r.raise_for_status()
    payload = r.json()
    # Trường `model` mang tên model THẬT đã sinh câu trả lời (2026-08-21,
    # spec model-picker §8.3). Gom lại để RESULT_JSON nói được một lượt đỏ là
    # "đỏ vì suy giảm" hay "đỏ vì hành vi" — xem MODELS_DA_PHUC_VU.
    if payload.get("model"):
        MODELS_DA_PHUC_VU.add(payload["model"])
    answer = payload["choices"][0]["message"]["content"]
    history.append({"role": "assistant", "content": answer})
    return answer


@dataclass
class DriveResult:
    final_answer: str
    turns: int
    completed: bool
    all_answers: list[str] = field(default_factory=list)


def _looks_like_confirm_gate(low: str, confirm_markers: tuple[str, ...]) -> bool:
    # Task 2 live-run (e2e-skill-discount, 2026-07-17) found a false positive:
    # a product-disambiguation clarification ("...Vui lòng xác nhận chính xác
    # tên sản phẩm...") contains "xác nhận" as an ordinary verb, mid-sentence,
    # with no "?" anywhere — NOT the real money-confirm gate. Every real
    # confirm-gate question in this codebase (agentic_gate._confirm_write's
    # callers, create_order.render_draft) ends in "?" (either "...cho đơn mua
    # P00021?" or "...Xác nhận? (có / không)"); ordinary clarification prose
    # in this codebase does not. Requiring "?" alongside the marker closes
    # this specific, real, evidence-based gap without needing an LLM-judge.
    return any(marker in low for marker in confirm_markers) and "?" in low


def drive_conversation(history: list[dict], sid: str, opening_msg: str,
                       responders: list[tuple], final_answer: str,
                       confirm_markers: tuple[str, ...] = ("xác nhận",),
                       max_turns: int = 8) -> DriveResult:
    """Lái hội thoại đa lượt chịu được model trôi tham số (Đợt 3 tier2-retirement
    live-verify). responders: [(predicate: str->bool, reply: str), ...] xét theo
    thứ tự trên câu trả lời agent (lowercase) tới khi khớp; reply được gửi lại.
    Khi câu trả lời chứa 1 trong confirm_markers VÀ có "?" (xem
    _looks_like_confirm_gate) → gửi final_answer, DỪNG (dùng HÀM NÀY CHO CẢ
    happy-path lẫn refusal — chỉ khác final_answer truyền vào). Không câu nào
    khớp → dừng, completed=False. all_answers tích luỹ MỌI câu trả lời agent
    trong phiên (kể cả khi completed=False)."""
    ans = chat(history, sid, opening_msg)
    all_answers = [ans]
    turns = 1
    while turns < max_turns:
        low = ans.lower()
        if _looks_like_confirm_gate(low, confirm_markers):
            ans = chat(history, sid, final_answer)
            all_answers.append(ans)
            return DriveResult(ans, turns + 1, True, all_answers)
        for predicate, reply in responders:
            if predicate(low):
                ans = chat(history, sid, reply)
                all_answers.append(ans)
                turns += 1
                break
        else:
            return DriveResult(ans, turns, False, all_answers)
    return DriveResult(ans, turns, False, all_answers)


def drive_fixed_turns(history: list[dict], sid: str, opening_msg: str,
                      followups: list[str]) -> list[str]:
    """Lái hội thoại theo kịch bản CỐ ĐỊNH (không tìm confirm-gate) — dùng cho
    kịch bản không kỳ vọng chạm write thật. Trả list MỌI câu trả lời agent, theo
    đúng thứ tự."""
    answers = [chat(history, sid, opening_msg)]
    for msg in followups:
        answers.append(chat(history, sid, msg))
    return answers


@dataclass
class Scenario:
    name: str
    passed: bool
    turns: int
    detail: str


def print_result(job: str, scenarios: list[Scenario]) -> bool:
    """In JSON kết quả có cấu trúc (job wrapper parse) + summary người đọc.
    Trả True nếu tất cả pass."""
    n, passed = len(scenarios), sum(1 for s in scenarios if s.passed)
    result = {"job": job, "n": n, "passed": passed,
             "models": sorted(MODELS_DA_PHUC_VU),
             "scenarios": [{"name": s.name, "passed": s.passed,
                            "turns": s.turns, "detail": s.detail}
                           for s in scenarios]}
    print("\n=== RESULT_JSON ===")
    print(json.dumps(result, ensure_ascii=False))
    print("=== END_RESULT_JSON ===\n")
    for s in scenarios:
        status = "PASS" if s.passed else "FAIL"
        print(f"[{status}] {s.name} (turns={s.turns}): {s.detail}")
    print(f"\n{passed}/{n} scenarios passed")
    return passed == n
