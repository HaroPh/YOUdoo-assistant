# backend/jobs/e2e_skill_delivery.py
"""Job `e2e-skill-delivery` — bọc `tests.live_verify_skill_delivery` thành job ON-DEMAND ONLY.

Toàn bộ phần chạy/chấm điểm nằm ở `jobs.e2e_common`; tệp này chỉ khai báo. Xem
docstring của e2e_common để biết vì sao bốn job không lặp lại nhau.
"""
from jobs.e2e_common import register_e2e

register_e2e("e2e-skill-delivery", "tests.live_verify_skill_delivery",
             "E2E skill agentic: giao-hang (3 kịch bản, cần full stack + write thật)",
             "tạo + xác nhận sale.order THẬT và giao hàng trong Odoo (giao-hang) — dọn tay nếu cần")
