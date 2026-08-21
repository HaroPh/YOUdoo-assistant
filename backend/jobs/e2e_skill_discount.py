# backend/jobs/e2e_skill_discount.py
"""Job `e2e-skill-discount` — bọc `tests.live_verify_skill_discount` thành job ON-DEMAND ONLY.

Toàn bộ phần chạy/chấm điểm nằm ở `jobs.e2e_common`; tệp này chỉ khai báo. Xem
docstring của e2e_common để biết vì sao bốn job không lặp lại nhau.
"""
from jobs.e2e_common import register_e2e

register_e2e("e2e-skill-discount", "tests.live_verify_skill_discount",
             "E2E skill agentic: bao-gia-chiet-khau (3 kịch bản, cần full stack + write thật)",
             "tạo draft quotation THẬT trong Odoo (bao-gia-chiet-khau) — dọn tay nếu cần")
