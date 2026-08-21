#!/usr/bin/env python3
# coding: utf-8
"""E2E live-verify: auto-chain (chuỗi tự động sau một câu khai báo).

3 kịch bản:
  1. chain_ngan       — "…rồi xác nhận luôn" ⇒ có chain_note, và sau khi đồng ý
                        thì bước kế TỰ CHẠY, kết thúc bằng gợi ý bước sau nữa.
  2. entry_giua_chuoi — vào giữa chuỗi trên một đơn đã tồn tại.
  3. khong_khai_chuoi — câu một bước ⇒ KHÔNG được có chain_note (hồi quy).

Cần: start-dev.ps1 đang chạy (backend :8002 + MCP :8003), write-toggle Odoo bật.
⚠️ TẠO ĐƠN NHÁP THẬT trong Odoo mỗi lần chạy.

PORT SANG YOUDOO 2026-08-21 (mục #2 bảng trạng thái). Đây là bản VIẾT LẠI chứ
không phải chép — bản gốc ở D:\\Project là mã nháp và ba chỗ của nó không dùng
lại được ở đây:

  1. Nó tự chế `chat()` riêng, ghim cứng `:8000`, và KHÔNG gửi header vai —
     backend Youdoo sẽ trả câu từ chối quyền chứ không phải câu trả lời.
     Nay dùng `live_verify_common.chat/drive_conversation` như ba script skill.
  2. Nó tự đặt `sys.stdout = io.TextIOWrapper(...)`. Youdoo đã có
     `src.cli_console.use_utf8_streams()` làm đúng việc đó cho CẢ BẢY cửa vào
     CLI; dựng thêm một bản riêng ở đây là dựng lại đúng thứ vừa được gom.
  3. Nó chỉ in text, KHÔNG phát `RESULT_JSON`, nên job bọc nó chỉ đọc được
     `returncode` trong khi ba job skill kia đọc được từng kịch bản. Nay phát
     `RESULT_JSON` qua `print_result`, để bốn job cùng một khuôn.

Và một khác biệt về NỘI DUNG kiểm: bản gốc so khớp nguyên văn
"Sau đó tự động: Xác nhận báo giá" và "Xác nhận? (có / không)". Chuỗi thứ hai
KHÔNG tồn tại trong mã Youdoo, còn chuỗi thứ nhất ghép từ nhãn trong
`write_registry.NEXT_STEPS`. Nên ở đây nhãn được SUY TỪ chính bảng đó: đổi nhãn
trong registry thì script đi theo, thay vì đỏ vì một lý do không liên quan.
"""
import re
import sys
import uuid

from src.agents.write_registry import NEXT_STEPS
from tests.live_verify_common import (Scenario, _looks_like_confirm_gate,
                                      drive_conversation, print_result)

CHAIN_NOTE = "Sau đó tự động: "
KHACH = "Azure Interior"
HANG = "[E-COM07] Large Cabinet"

# Nhãn suy từ registry, không ghim chuỗi — xem docstring.
NHAN_XAC_NHAN = NEXT_STEPS["create_quotation"].label      # "Xác nhận báo giá"
NHAN_GIAO_HANG = NEXT_STEPS["confirm_sale_order"].label   # "Giao hàng"


def _sid(ten: str) -> str:
    return f"live-verify-autochain-{ten}-{uuid.uuid4().hex[:8]}"


def _note_truoc_cau_hoi(answer: str) -> bool:
    """chain_note phải đứng TRƯỚC câu hỏi xác nhận.

    Bản gốc so vị trí với chuỗi nguyên văn "Xác nhận? (có / không)". Ở đây neo
    vào dấu "?" CUỐI CÙNG: câu hỏi xác nhận luôn là câu hỏi chốt của lượt, nên
    "note nằm trước dấu ? cuối" là cùng một tính chất mà không phụ thuộc cách
    diễn đạt (`create_order.render_draft` có thể đổi chữ, thứ tự thì không).
    """
    return CHAIN_NOTE in answer and answer.rindex("?") > answer.index(CHAIN_NOTE)


def scenario_chain_ngan() -> Scenario:
    history = []
    result = drive_conversation(
        history, _sid("ngan"),
        opening_msg=f"tạo báo giá cho {KHACH}, 2 {HANG} rồi xác nhận luôn",
        responders=[], final_answer="có, tôi xác nhận")
    dau = result.all_answers[0]
    if CHAIN_NOTE + NHAN_XAC_NHAN not in dau:
        return Scenario("chain_ngan", False, result.turns,
                        f"thiếu chain_note {CHAIN_NOTE + NHAN_XAC_NHAN!r}: {dau[:200]}")
    if not _note_truoc_cau_hoi(dau):
        return Scenario("chain_ngan", False, result.turns,
                        "chain_note không đứng trước câu hỏi xác nhận")
    if not result.completed:
        return Scenario("chain_ngan", False, result.turns,
                        f"không tới được cổng xác nhận sau {result.turns} lượt")
    # Chuỗi chạy xong tới confirm_sale_order ⇒ continuation gợi ý bước kế.
    if NHAN_GIAO_HANG not in result.final_answer:
        return Scenario("chain_ngan", False, result.turns,
                        f"sau khi đồng ý, không thấy bước kế {NHAN_GIAO_HANG!r}: "
                        f"{result.final_answer[:200]}")
    return Scenario("chain_ngan", True, result.turns,
                    f"chain_note đúng chỗ, tự chạy tới bước gợi ý {NHAN_GIAO_HANG!r}")


def scenario_entry_giua_chuoi() -> Scenario:
    # Dựng một đơn đã xác nhận qua chính hội thoại (không XML-RPC): kịch bản
    # này đo ĐƯỜNG VÀO GIỮA CHUỖI, nên đơn phải được tạo đúng như người dùng
    # tạo thì mã đơn mới xuất hiện trong câu trả lời để bóc ra.
    history = []
    dung = drive_conversation(
        history, _sid("setup"),
        opening_msg=f"tạo báo giá cho {KHACH}, 1 {HANG}",
        responders=[], final_answer="có, tôi xác nhận")
    if not dung.completed:
        return Scenario("entry_giua_chuoi", False, dung.turns,
                        "dựng đơn nền không qua được cổng xác nhận")
    ma = None
    for a in reversed(dung.all_answers):
        m = re.search(r"S\d{5}", a)
        if m:
            ma = m.group(0)
            break
    if ma is None:
        return Scenario("entry_giua_chuoi", False, dung.turns,
                        f"không bóc được mã đơn: {dung.final_answer[:200]}")

    history = []
    result = drive_conversation(
        history, _sid("giua"),
        opening_msg=f"xác nhận {ma} rồi giao hàng luôn",
        responders=[], final_answer="có, tôi xác nhận")
    dau = result.all_answers[0]
    if CHAIN_NOTE + NHAN_GIAO_HANG not in dau:
        return Scenario("entry_giua_chuoi", False, result.turns,
                        f"thiếu chain_note {CHAIN_NOTE + NHAN_GIAO_HANG!r} trên {ma}: "
                        f"{dau[:200]}")
    return Scenario("entry_giua_chuoi", True, result.turns,
                    f"{ma}: chain_note giao hàng xuất hiện khi vào giữa chuỗi")


def scenario_khong_khai_chuoi() -> Scenario:
    """Hồi quy: câu MỘT bước không được sinh chain_note.

    Đây là kịch bản duy nhất khẳng định PHỦ ĐỊNH, nên nó cũng phải khẳng định
    lượt đó thật sự có xảy ra — nếu không, một câu trả lời lỗi (không chứa gì
    cả) cũng "không có chain_note" và kịch bản xanh giả.
    """
    history = []
    result = drive_conversation(
        history, _sid("mot-buoc"),
        opening_msg=f"tạo báo giá cho {KHACH}, 1 {HANG}",
        responders=[], final_answer="không")
    dau = result.all_answers[0]
    if not _looks_like_confirm_gate(dau.lower(), ("xác nhận",)):
        return Scenario("khong_khai_chuoi", False, result.turns,
                        f"không thấy cổng xác nhận — lượt này không đo được gì: {dau[:200]}")
    if CHAIN_NOTE in dau:
        return Scenario("khong_khai_chuoi", False, result.turns,
                        f"có chain_note dù câu chỉ một bước: {dau[:200]}")
    return Scenario("khong_khai_chuoi", True, result.turns,
                    "có cổng xác nhận, không có chain_note — đúng")


def main():
    scenarios = [scenario_chain_ngan(), scenario_entry_giua_chuoi(),
                 scenario_khong_khai_chuoi()]
    ok = print_result("e2e-smoke", scenarios)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
