# Báo cáo — contract test cho GATHER_CASES

Plan: `docs/superpowers/plans/2026-08-02-gather-cases-contract-test.md`
Spec: `docs/superpowers/specs/2026-08-02-gather-cases-contract-test-design.md`

## Xác minh test có tác dụng thật (Step 4)

Xoá tạm dòng `("sla_giao_hang", "get_sale_order_detail", "ngày giao dự kiến")` khỏi `_KNOWN_GAPS`, chạy lại — kết quả:

```
AssertionError: case sla_giao_hang: fixture của tool 'get_sale_order_detail' dùng nhãn 'ngày giao dự kiến' nhưng tool không có field thật nào trong ('commitment_date', 'effective_date') (field thật: ['amount_total', 'date_order', 'delivery_status', 'id', 'name', 'partner_id', 'price_subtotal', 'price_unit', 'product_id', 'product_uom_qty', 'state'])
```

Kết luận: khớp đúng kỳ vọng — test bắt được lỗi thật. Đã khôi phục `_KNOWN_GAPS` về đầy đủ 2 dòng trước khi commit.

## Xác minh test

- `test_eval_gather.py` riêng: `24 passed`
- Unit-only: `1098 passed` (TRƯỚC: 1097)
- Integration: `27 passed` (TRƯỚC: 27)

## Kết luận

Đối chiếu §"Xong nghĩa là" của spec:

1. `test_gather_cases_fixture_labels_match_real_tool_fields` tồn tại, PASS trên `GATHER_CASES` hiện tại: **ĐẠT**
2. Xoá 1 dòng `_KNOWN_GAPS` khiến test FAIL đúng kỳ vọng (Step 4): **ĐẠT**
3. Không sửa `cases.py` hay code sản xuất nào: **ĐẠT, xác nhận qua git diff --stat**
4. Toàn bộ test 2 chế độ xanh: **ĐẠT**
5. `_KNOWN_GAPS` có đúng 2 mục, có comment trỏ report: **ĐẠT**
