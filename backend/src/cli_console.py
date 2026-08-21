# backend/src/cli_console.py
"""Ép stdout/stderr về UTF-8 cho mọi cửa vào CLI.

VÌ SAO CẦN. Khi stdout/stderr bị chuyển hướng ra tệp — đúng cách Task Scheduler
chạy `>> log 2>&1` — Windows dùng ANSI codepage (cp1252 trên máy này) thay vì
UTF-8. Mọi thông điệp tiếng Việt có dấu (kể cả "→") làm CHÍNH dòng in ném
`UnicodeEncodeError`. Hậu quả không phải mất một dòng log, mà là:

  - chẩn đoán thật bị nuốt sạch (dòng đang in chính là dòng báo lỗi);
  - mã thoát đổi từ 2 (INFRA ERROR đọc được) thành 1 trống rỗng, phá hợp đồng
    exit 0/1/2 mà job runner dựa vào.

Console tương tác KHÔNG dính (Python dùng Windows Console API, không qua
codepage) — đó là lý do lỗi này ẩn qua mọi lần thử tay.

ĐÃ CẮN HAI LẦN. Lần đầu ở CLI `jobs` (whole-branch review SP-1C1, xếp Critical).
Lần hai ngày 2026-08-21 ở `evals/run_eval.py`: lỗi thật là "cạn chuỗi ...
=cooldown" nhưng không ai thấy, và một phiên mất một lượt đi tìm nguyên nhân sai
chỗ. Test gác lớp lỗi này CÓ TỒN TẠI
(`tests/jobs/test_cli.py::test_cli_survives_redirected_cp1252_stdout`) nhưng
đang bị skip cứng vì thiếu job `e2e-smoke` — bài học đã được ghi thành test rồi
tắt đi, nên nó không cứu được lần thứ hai.

HAI BẬC, CÓ CHỦ ĐÍCH:
  1. `encoding="utf-8"` — giữ nguyên tiếng Việt. Đây là thứ ta muốn: tệp log
     đọc được, không mất chữ.
  2. `errors="replace"` — chỉ khi (1) không được. Mất dấu (thành "?") nhưng
     KHÔNG BAO GIỜ ném. Thà log xấu còn hơn nuốt mất chẩn đoán.
  3. Bỏ qua — stream không hỗ trợ reconfigure (đã bị bọc, hoặc StringIO trong
     test). Không được ném ở đây: một hàm vệ sinh console mà làm hỏng tiến
     trình thì tệ hơn vấn đề nó đi chữa.
"""
import sys


def use_utf8_streams() -> None:
    """Gọi ĐẦU TIÊN trong mọi hàm main() của CLI, trước bất kỳ lệnh in nào."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
            continue
        except (AttributeError, ValueError):
            pass
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
