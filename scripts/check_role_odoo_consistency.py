# scripts/check_role_odoo_consistency.py
"""Đối chiếu roles.py (tầng agent) với quyền THẬT trên tài khoản Odoo của
từng vai (tầng cưỡng chế) — final-review Fix 2, 2026-08-09-role-based-access.

VÌ SAO CẦN SCRIPT NÀY: `roles.py` khai own/needs_sign_off (agent ĐƯỢC gọi) và
other_dept/denied (agent BỊ chặn ở code) — nhưng lớp Odoo bên dưới có granularity
riêng của nó. Review thủ công trên Odoo thật tìm ra 4 khai báo other_dept KHÔNG
có "backstop" ở tầng Odoo (tài khoản Odoo thực ra VẪN có quyền write/create):
  - ai-accounting CÓ quyền ghi/tạo stock.picking → deliver_order,
    validate_picking, internal_transfer chỉ bị chặn ở agent
  - ai-warehouse CÓ quyền ghi sale.order → confirm_sale_order chỉ bị chặn ở agent
Đây KHÔNG phải lỗi code — là giới hạn độ mịn của nhóm quyền stock/sale chuẩn
của Odoo (xem odoo_setup_ai_accounts.py: "Inventory / User" cấp write trên toàn
bộ stock.picking, không có cách tách riêng theo picking_type qua UI groups).
Nhưng nó từng KHÔNG được ghi lại và KHÔNG được đo — script này biến nó thành
một bảng PASS/GAP tường minh, chạy lại được (drift-proof): nếu ai đó nới thêm
quyền Odoo cho một vai (vd thêm "Sales / User" cho ai-warehouse) mà không cập
nhật roles.py, GAP mới sẽ xuất hiện ở đây thay vì nằm im cho tới khi có sự cố.

CÁCH DÙNG:
    cd D:\\Youdoo\\...\\role-based-access
    backend/.venv/Scripts/python.exe scripts/check_role_odoo_consistency.py

ENV BẮT BUỘC: ODOO_URL, ODOO_DB, AI_ACCOUNT_PASSWORD (mật khẩu chung của 4 tài
khoản AI — xem scripts/odoo_setup_ai_accounts.py). Vai kiểm tra dùng
YOUDOO_POLICY_PROFILE nếu có (mặc định 'small-business', giống roles.py).

KHÔNG tự chạy script này — nó đăng nhập Odoo thật và không ghi gì, nhưng vẫn
là lệnh hạ tầng sống, do controller chạy.

GIỚI HẠN CỐ Ý: has_access(model, operation) được gọi trên RECORDSET RỖNG
(env[model], không ids cụ thể) — kiểm ir.model.access (quyền theo NHÓM),
KHÔNG kiểm ir.rule (quyền theo BẢN GHI, vd multi-company). Đúng phạm vi cần
đối chiếu ở đây: roles.py phân quyền theo NHÓM NGHIỆP VỤ, không theo bản ghi.
"""
import os
import sys
import xmlrpc.client
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
from src.agents import roles  # noqa: E402 — cần sys.path chỉnh trước

# ── tool -> [(model, operation), ...] — TẬP TƯỜNG MINH, KHÔNG parser tự động ──
# Rút trực tiếp từ mcp-servers/odoo/tools/*.py: mỗi cặp là một lệnh odoo(model,
# method, ...) THẬT trong tool đó (method → operation qua
# mcp-servers/odoo/security.py ODOO_METHOD_OPERATION_MAP), chỉ giữ lệnh
# GHI/TẠO (bỏ qua các odoo(..., "search_read"/"read", ...) thuần đọc trong
# cùng tool — chúng không phải chỗ quyền phân biệt vai). Một tool có NHIỀU
# cặp nghĩa là nó chạm nhiều model/operation trong luồng thật; "has" của tool
# đó = có ĐỦ TẤT CẢ (thiếu một cặp là tool sẽ vỡ giữa chừng trên tài khoản đó).
TOOL_ACCESS_MAP = {
    # ── Kho (stock.*) ──
    "deliver_order":        [("stock.picking", "write")],       # button_validate, qua _validate_order_pickings
    "receive_order":        [("stock.picking", "write")],       # button_validate, qua _validate_order_pickings
    "validate_picking":     [("stock.picking", "write")],       # button_validate trực tiếp
    "internal_transfer":    [("stock.picking", "create"),        # inventory.py:150 create
                             ("stock.picking", "write")],        # :156-167 action_confirm/assign/button_validate
    "inventory_adjustment": [("stock.quant", "write"),           # inventory.py:88 write quant có sẵn
                             ("stock.quant", "create")],         # :91 nhánh chưa có quant — quyền RIÊNG, không dùng chung gate write
    "scrap_product":        [("stock.scrap", "create"),          # inventory.py:209 create
                             ("stock.scrap", "write")],          # :211 action_validate
    "return_order":         [("stock.return.picking", "create"),      # inventory.py:243 create WIZARD (không phải write)
                             ("stock.return.picking.line", "write"),  # :264-268
                             ("stock.picking", "create")],            # :271 action_create_returns sinh phiếu trả mới
    # ── Kế toán (account.*) ──
    "post_invoice":            [("account.move", "write")],           # action_post
    "register_payment":        [("account.move", "write"),            # accounting.py:233 action_register_payment
                                ("account.payment.register", "create")],  # :236 create wizard
    "create_credit_memo":      [("account.move.reversal", "create"),  # accounting.py:289 create wizard
                                ("account.move.reversal", "write")],  # :290 refund_moves
    "create_invoice_from_order": [("sale.advance.payment.inv", "create")],  # accounting.py:122 create_invoices
    "create_bill_from_po":     [("purchase.order", "write"),          # purchase.py:126 action_create_invoice trên PO CÓ SẴN
                                ("account.move", "create"),           # bill sinh ra
                                ("account.move", "write")],           # :136 đặt invoice_date
    # ── Bán/mua hàng (sale.order / purchase.order) ──
    "create_quotation":       [("sale.order", "create")],
    "create_rfq":              [("purchase.order", "create")],
    "confirm_sale_order":      [("sale.order", "write")],             # action_confirm
    "confirm_purchase_order":  [("purchase.order", "write")],         # button_confirm
    # ── Mail (2 coordinator gửi mail nêu trong roles.py) ──
    # mail.py:87 gọi send_mail trên mail.template CÓ SẴN (chỉ cần đọc template,
    # không tạo template); bản ghi thật sinh ra và bị sửa/xoá là mail.mail
    # (:87 create, :128 write, :163 unlink qua discard_prepared_email).
    "send_delivery_email": [("mail.template", "read"), ("mail.mail", "create"),
                            ("mail.mail", "write"), ("mail.mail", "unlink")],
    "send_invoice_email":  [("mail.template", "read"), ("mail.mail", "create"),
                            ("mail.mail", "write"), ("mail.mail", "unlink")],
    # ── Nghiệp vụ chung hai vai (crm.py) ──
    # mail.activity create đã True cho cả ba tài khoản ghi TRƯỚC nhánh
    # log_activity generalisation (đo spec §6) — không đo được cái nhánh đó
    # thêm. Quyền THẬT nhánh này thêm là ir.model READ (res_model_id tra
    # runtime, xem crm.py log_activity) qua nhóm "Youdoo AI / Activity" —
    # thiếu dòng này thì script live-check báo OK bất kể nhóm có được áp hay
    # không. Cùng kiểu gate-by-read hai dòng mail ở trên đã dùng.
    "log_activity":            [("mail.activity", "create"), ("ir.model", "read")],  # crm.py log_activity
    # action_feedback đặt active=False + state='done' trên chính bản ghi
    # mail.activity (đo 2026-08-14) — là "write", không phải "unlink".
    # Cặp READ cũng bắt buộc: tool search_read mail.activity TRƯỚC khi ghi
    # (crm.py:272) để lọc theo chủ sở hữu, và bộ lọc đó là lớp cưỡng chế DUY
    # NHẤT vì Odoo không chặn đóng việc của người khác. Mất quyền đọc =
    # sập lớp cưỡng chế, không phải chỉ mất tiện ích.
    "close_activity":          [("mail.activity", "read"),
                                ("mail.activity", "write")],  # crm.py close_activity
    # Tool CHỈ-ĐỌC. Đo 2026-08-14: cả hai vai non-admin đọc được, nhưng cả
    # hai trả 0 dòng của chính mình — nên quyền đọc hỏng sẽ trông y hệt
    # "không có việc nào được giao". Phải canh tường minh.
    "find_my_activities":      [("mail.activity", "read")],  # crm.py find_my_activities
}

# Tool nêu trong roles.py nhưng KHÔNG map sạch vào MỘT cặp (model, operation)
# — liệt kê tường minh thay vì âm thầm bỏ qua (yêu cầu của Fix 2).
UNMAPPED_TOOLS = {
    "flag_order_for_review": (
        "nhận model qua tham số gọi (sale.order HOẶC purchase.order — "
        "sales.py flag_order_for_review), nên không có MỘT cặp (model, "
        "operation) cố định để kiểm. Cả hai model đều dùng chung method "
        "'message_post' (operation write); kiểm riêng từng model nếu cần "
        "độ chính xác cao hơn."),
}

# ── 9 khoảng trống Odoo đã biết (đo 2026-08-11 bằng bảng map ĐÃ SỬA — xem
# docstring trên). role, tool → giải thích. Script PASS (không coi là lỗi) khi
# thấy ĐÚNG những GAP này; bất kỳ sai khác nào khác (kể cả GAP mới) đều được
# nêu riêng, nổi bật, và làm script thoát mã khác 0 — phần "drift-proof".
#
# LỊCH SỬ: bảng này từng ghi 4. Con số đó sai vì 8/18 dòng TOOL_ACCESS_MAP
# ánh xạ sai operation hoặc thiếu cặp (ví dụ create_bill_from_po khai
# ("purchase.order","create") trong khi tool gọi action_create_invoice trên PO
# CÓ SẴN — cần "write"). Sau khi sửa map và đo lại: 9 khoảng trống thật.
KNOWN_ODOO_GAPS = {
    # ── kho: tồn tại vì Odoo không có nhóm "chỉ xác nhận đơn" ──
    ("warehouse", "confirm_sale_order"): "ai-warehouse vẫn có write trên sale.order (không có nhóm Odoo tách riêng 'chỉ xác nhận').",
    ("warehouse", "send_invoice_email"): "nhóm Youdoo AI / Mail cấp mail.mail cho MỌI vai; mail.template ai cũng đọc được. Tầng mail không có backstop Odoo.",
    # ── kế toán: "Accounting / Invoicing" kéo theo cả cụm quyền kho ──
    ("accounting", "deliver_order"): "ai-accounting vẫn có write trên stock.picking (nhóm Odoo không tách theo picking_type).",
    ("accounting", "receive_order"): "ai-accounting vẫn có write trên stock.picking.",
    ("accounting", "validate_picking"): "ai-accounting vẫn có write trên stock.picking.",
    ("accounting", "internal_transfer"): "ai-accounting vẫn có create+write trên stock.picking.",
    ("accounting", "confirm_sale_order"): "ai-accounting vẫn có write trên sale.order.",
    ("accounting", "confirm_purchase_order"): "ai-accounting vẫn có write trên purchase.order (cần cho create_bill_from_po, không tách được).",
    ("accounting", "send_delivery_email"): "cùng lý do như (warehouse, send_invoice_email) — nhóm Youdoo AI / Mail dùng chung.",
}

ROLE_LOGINS = {"warehouse": "ai-warehouse", "accounting": "ai-accounting"}


def _authenticate(url, db, login, password):
    common = xmlrpc.client.ServerProxy(url + "/xmlrpc/2/common")
    uid = common.authenticate(db, login, password, {})
    if not uid:
        sys.exit(f"Đăng nhập Odoo thất bại cho '{login}' — kiểm tra "
                 f"AI_ACCOUNT_PASSWORD và tài khoản đã được tạo "
                 f"(scripts/odoo_setup_ai_accounts.py) chưa.")
    return uid


def _has_access(obj_proxy, db, uid, password, model, operation) -> bool:
    """has_access gọi trên recordset RỖNG (env[model]) — kiểm ir.model.access
    theo NHÓM, không theo bản ghi. Xem 'GIỚI HẠN CỐ Ý' ở docstring module.

    LƯU Ý CONTRACT execute_kw (bug thật, bắt bởi live run 2026-08-11):
    `args` của execute_kw truyền THEO VỊ TRÍ cho method — với một method gọi
    trên recordset (như has_access), phần tử ĐẦU TIÊN của args luôn là danh
    sách ids (rỗng = env[model], đúng ý ta cần ở đây), KHÔNG PHẢI tham số
    đầu tiên của has_access(self, operation). Thiếu `[]` dẫn ids này khiến
    Odoo hiểu `operation` (chuỗi) là ids và báo thiếu tham số 'operation' —
    lỗi CONTRACT của lệnh gọi, không phải kết quả quyền. Dễ lặp lại (đã lặp
    lại ít nhất 2 lần trong dự án, xem backend/spikes/) — để ý mọi
    execute_kw(..., "has_access", ...) khác thêm vào sau này."""
    return bool(obj_proxy.execute_kw(db, uid, password, model, "has_access", [[], operation]))


def _self_check(obj_proxy, db, uid, password):
    """Gọi has_access() MỘT LẦN cho (res.partner, read) — mọi tài khoản nội
    bộ (BASE_USER, group_user) đều có quyền này qua Odoo mặc định, nên nếu
    _has_access TỰ NÓ raise ở đây thì đó là LỖI SCRIPT (sai contract
    execute_kw, method đổi tên/chữ ký ở version Odoo khác, v.v...) — KHÔNG
    PHẢI phát hiện về quyền. py_compile chỉ chứng minh cú pháp đúng, không
    chứng minh contract gọi đúng (đo thật: script này từng crash ngay ở lần
    chạy sống đầu tiên với TypeError, dù py_compile sạch) — self-check này
    tách hai loại lỗi ra ngay từ đầu thay vì để nó lẫn vào bảng PASS/GAP."""
    try:
        _has_access(obj_proxy, db, uid, password, "res.partner", "read")
    except Exception as e:  # noqa: BLE001 — cố ý bắt rộng, phân loại rõ bằng thông điệp
        sys.exit(
            f"LỖI SCRIPT (không phải phát hiện về quyền): has_access() tự nó "
            f"raise khi tự kiểm với (res.partner, read) — {type(e).__name__}: {e}\n"
            f"Kiểm tra lại contract execute_kw (xem docstring _has_access) "
            f"trước khi tin bất kỳ dòng nào trong bảng bên dưới.")


def check_tool(obj_proxy, db, uid, password, tool):
    pairs = TOOL_ACCESS_MAP[tool]
    results = [(m, op, _has_access(obj_proxy, db, uid, password, m, op)) for m, op in pairs]
    has_all = all(ok for _, _, ok in results)
    return has_all, results


def main():
    url = os.environ["ODOO_URL"]
    db = os.environ["ODOO_DB"]
    password = os.environ["AI_ACCOUNT_PASSWORD"]
    profile = roles.load_profile()  # dùng YOUDOO_POLICY_PROFILE nếu set, giống roles.py runtime
    obj = xmlrpc.client.ServerProxy(url + "/xmlrpc/2/object")

    rows = []          # (role, tool, expected, actual, status, note)
    unexpected = []

    for role_name, login in ROLE_LOGINS.items():
        role_cfg = profile.get(role_name)
        if role_cfg is None:
            continue
        uid = _authenticate(url, db, login, password)
        _self_check(obj, db, uid, password)

        for tool, pairs in TOOL_ACCESS_MAP.items():
            state = role_cfg.state_of(tool)
            expected_has = state in (roles.OWN, roles.NEEDS_SIGN_OFF)
            actual_has, detail = check_tool(obj, db, uid, password, tool)

            if actual_has == expected_has:
                status = "OK"
            elif actual_has and not expected_has:
                key = (role_name, tool)
                if key in KNOWN_ODOO_GAPS:
                    status = "GAP (known)"
                else:
                    status = "GAP (NEW — undocumented!)"
                    unexpected.append((role_name, tool, KNOWN_ODOO_GAPS.get(key, "")))
            else:  # not actual_has and expected_has — Odoo blocks something roles.py says is own/sign-off
                status = "BLOCKED (unexpected — tool will fail live for this role)"
                unexpected.append((role_name, tool, ""))

            rows.append((role_name, tool, "has" if expected_has else "lacks",
                        "has" if actual_has else "lacks", status, detail))

    # ── report ──────────────────────────────────────────────────────────────
    print(f"{'role':<11} {'tool':<28} {'expect':<7} {'actual':<7} status")
    print("-" * 95)
    for role_name, tool, expected, actual, status, detail in rows:
        print(f"{role_name:<11} {tool:<28} {expected:<7} {actual:<7} {status}")

    if UNMAPPED_TOOLS:
        print("\nKHÔNG KIỂM (không map sạch vào 1 cặp model/operation):")
        for tool, why in UNMAPPED_TOOLS.items():
            print(f"  - {tool}: {why}")

    known_gaps_seen = [r for r in rows if r[4] == "GAP (known)"]
    print(f"\n{len(known_gaps_seen)} GAP đã biết (agent-enforced only, xem KNOWN_ODOO_GAPS):")
    for role_name, tool, _, _, status, _ in known_gaps_seen:
        print(f"  - {role_name}/{tool}: {KNOWN_ODOO_GAPS[(role_name, tool)]}")

    if unexpected:
        print(f"\n*** {len(unexpected)} KẾT QUẢ NGOÀI DỰ KIẾN — cần xem lại roles.py "
             f"hoặc quyền Odoo, KHÔNG nằm trong {len(KNOWN_ODOO_GAPS)} gap đã biết: ***")
        for role_name, tool, _ in unexpected:
            print(f"  - {role_name}/{tool}")
        sys.exit(1)

    print(f"\nKhông có sai khác ngoài dự kiến — đúng {len(known_gaps_seen)}/"
          f"{len(KNOWN_ODOO_GAPS)} gap đã biết, còn lại khớp roles.py.")


if __name__ == "__main__":
    main()
