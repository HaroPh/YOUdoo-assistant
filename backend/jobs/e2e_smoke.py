# backend/jobs/e2e_smoke.py
"""Job `e2e-smoke` — bọc `tests.live_verify_auto_chain` thành job ON-DEMAND ONLY.

Toàn bộ phần chạy/chấm điểm nằm ở `jobs.e2e_common`; tệp này chỉ khai báo. Xem
docstring của e2e_common để biết vì sao bốn job không lặp lại nhau.
"""
from jobs.e2e_common import register_e2e

register_e2e("e2e-smoke", "tests.live_verify_auto_chain",
             "e2e smoke auto-chain qua /v1 (cần full stack; tạo đơn nháp thật trong Odoo)",
             "tạo đơn nháp THẬT trong Odoo — dọn tay nếu cần")
