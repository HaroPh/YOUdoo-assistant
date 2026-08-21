# backend/jobs/e2e_skill_warehouse.py
"""Job `e2e-skill-warehouse` — bọc `tests.live_verify_skill_warehouse` thành job ON-DEMAND ONLY.

Toàn bộ phần chạy/chấm điểm nằm ở `jobs.e2e_common`; tệp này chỉ khai báo. Xem
docstring của e2e_common để biết vì sao bốn job không lặp lại nhau.
"""
from jobs.e2e_common import register_e2e

register_e2e("e2e-skill-warehouse", "tests.live_verify_skill_warehouse",
             "E2E skill agentic: nhap-kho (5 kịch bản, cần full stack + write thật)",
             "tạo + xác nhận purchase.order THẬT và nhận hàng trong Odoo (nhap-kho) — dọn tay nếu cần")
