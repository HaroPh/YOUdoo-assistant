# Live-verify — suy ra bảng bộ phận + chốt drift bảng quyền (2026-08-12)

**Môi trường:** worktree `role-decl-derivation` (nhánh `feat/role-declaration-derivation`),
đo **TRƯỚC merge**. Stack cũ dừng hẳn trước khi khởi động stack của nhánh.

## Tóm tắt

| # | Kịch bản | Trước | Sau | |
|---|---|---|---|---|
| KB3 | kho xin gửi mail hóa đơn | *"liên hệ bộ phận **khác**"* | *"liên hệ bộ phận **Kế toán**"* | ĐẠT |
| KB4 | kế toán xin gửi mail giao hàng | trả lời hội thoại, không từ chối | **vẫn vậy qua HTTP** — nhưng gốc rễ KHÁC với chẩn đoán trong spec | xem §2 |
| — | kho gửi mail giao hàng (thuộc quyền) | chạy | chạy | ĐẠT |
| — | kế toán gửi mail hóa đơn (thuộc quyền) | chạy | chạy | ĐẠT |
| — | `check_role_odoo_consistency.py` | exit 0, 9 gap | exit 0, **9/9 gap** | ĐẠT |

Script nhất quán giữ đúng 9 gap là bằng chứng cho bất biến quan trọng nhất của
đợt này: `allowed_tools()` **không đổi**, nên quyền tài khoản Odoo không bị
đụng — chỉ nội dung prompt đổi.

## 1. KB3 — đóng đúng như thiết kế

```
Việc này không thuộc quyền hạn của bộ phận Kho.
Vui lòng liên hệ bộ phận Kế toán để thực hiện.
```

Trước đợt này câu cuối là "bộ phận khác", vì `send_invoice_email` không có
trong `_DEPT_OF`. Task 1 đóng nó.

## 2. KB4 — chẩn đoán trong spec §1.2 KHÔNG ĐẦY ĐỦ

Đây là phần đáng giá nhất của vòng đo, nên viết dài.

### 2.1 Thay đổi của nhánh HOẠT ĐỘNG — đo riêng từng tầng

`roles.load_profile()['accounting'].state_of('send_delivery_email')` nay trả
`other_dept` (trước: `denied`), và prompt của vai kế toán **có** dòng:

```
#   - send_delivery_email → thuộc bộ phận Kho
```

Gọi **thẳng** node planner của vai kế toán với đúng câu KB4, chạy 3 lần:

```
lần 1..3 | pending_action=None
          Việc này không thuộc quyền hạn của bộ phận Kế toán.
          Vui lòng liên hệ bộ phận Kho để thực hiện.
```

**3/3 từ chối đúng, nêu đúng bộ phận.** Vậy Task 1 + Task 2 làm đúng việc của
chúng.

### 2.2 Nhưng qua HTTP vẫn hỏng — và không phải vì checkpoint cũ

Giả thuyết đầu tiên của tôi là thread trùng với đợt đo trước nên resume
checkpoint cũ. **Sai.** Ép `session_id` mới (đường ưu tiên 2 của
`_derive_thread_id`) với đúng câu chữ gốc — vẫn ra câu hội thoại lan man.

### 2.3 Gốc rễ thật: intent router, không phải `other_dept`

Khác biệt giữa probe và đường thật là **danh sách SOP skill**. Vai kế toán
không nạp skill nào (nạp-skill-theo-vai bỏ cả 3), nên `render_worker_block([])`
trả chuỗi rỗng. Đo trực tiếp intent router, 3 lần mỗi cấu hình:

| cấu hình | intent |
|---|---|
| block CÓ + sops CÓ | `erp_write` ×3 |
| block CÓ + sops RỖNG | `erp_write` ×3 |
| **block RỖNG** + sops CÓ | **`unknown` ×3** |
| **block RỖNG** + sops RỖNG | **`unknown` ×3** |

Biến quyết định là **worker block**, không phải danh sách tên SOP. Block rỗng
⇒ router phân loại `unknown` ⇒ đi nhánh `respond_unknown` ⇒ **planner không
bao giờ chạy**, nên guard tất định không có gì để chặn.

**Đây là cùng họ lỗi với sự cố coordinator mail của đợt trước:** lọc theo vai
gỡ mất một thứ mà thành phần phía sau đang dựa vào — lần trước là tool giúp
việc, lần này là khối văn bản trong prompt của router.

### 2.4 Đính chính spec

Spec §1.2 viết `other_dept` "quyết định lời từ chối có XẢY RA hay không". Đúng
nhưng **chưa đủ**: nó là điều kiện **cần**, không phải điều kiện **đủ**. Router
phải định tuyến vào `erp_write` trước đã. Với vai kế toán, ở ít nhất một số
cách diễn đạt, nó không.

Không phải hồi quy của nhánh này — hành vi này có sẵn từ khi có nạp-skill-theo-vai.

### 2.5 Một quan sát phụ, đã có tài liệu từ trước

Với câu diễn đạt khác (*"nhờ gửi mail thông báo giao hàng…"*), planner trả về
tên tool **bịa** `'other'`, nên `dept_of('other')` = `"khác"` và câu từ chối
mất tên bộ phận. Đây là hành vi đã ghi trong đợt phân quyền (hợp đồng JSON bắt
buộc nêu tool, LLM không có cách diễn đạt "từ chối"), không phải khoảng trống
`DEPT_OF`.

## 3. Đối chứng âm — không chặn nhầm việc thuộc quyền

Cùng câu chữ gốc, thread mới:

- kho → `send_delivery_email`: soạn được, đúng người nhận, có cổng xác nhận
- kế toán → `send_invoice_email`: soạn được, đúng người nhận, có cổng xác nhận

Thiếu đối chứng này thì "chặn được nhiều hơn" không phân biệt được với "chặn hỏng".

## 4. Dọn dẹp

Mọi bản nháp `mail.mail` sinh ra khi đo đã xoá; `state='outgoing'` = 0. Không
xác nhận gửi ở bất kỳ kịch bản nào.

## 5. Việc phát sinh, chuyển sang đợt sau

1. **Worker block rỗng làm hỏng định tuyến ý định** (§2.3). Đo được, tất định
   3/3 cả hai chiều, cô lập được về một biến. Ảnh hưởng rộng hơn câu từ chối:
   vai kế toán có thể lỡ route cả những yêu cầu **thuộc quyền** nó, tùy cách
   diễn đạt — đối chứng ở §3 chạy được, nên không phải mọi câu đều hỏng.
2. **`DEPT_OF` vẫn thiếu 16/34 tool** (final review I2), gồm 3 coordinator mail
   của chính đợt trước. Cần quyết định nghiệp vụ cho từng tool, không phải chép
   máy móc.
3. **Guard drift chỉ bắt 3/8 dòng** từng sai (final review I1) — đã ghi đúng số
   đo trong docstring; nâng lên cần kiểm ở phạm vi `operation`, mà spec §4.3
   giải thích vì sao chưa làm được tin cậy.
4. **`enterprise/warehouse` không sở hữu `flag_order_for_review`** nên
   `skill_role_gap` âm thầm bỏ SOP `nhap-kho` cho vai đó (final review I3).
   Comment đã sửa cho đúng sự thật; câu hỏi chính sách còn treo.
