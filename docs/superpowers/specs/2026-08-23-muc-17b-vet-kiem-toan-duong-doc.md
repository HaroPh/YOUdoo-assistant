# Mục 17b — vệt kiểm toán cho ĐƯỜNG ĐỌC

**Ngày**: 2026-08-23. **Nhánh**: `main`.

## 1. Đề bài

28 tool `erp_query` sinh ra **0 dòng** kiểm toán: `transport.py` gọi Odoo bằng
`ServerProxy` riêng, không qua `odoo()` của MCP, nên không qua `log_mcp_event`.
Câu *"ai đã đọc công nợ khách hàng / bảng giá"* không trả lời được từ bất kỳ đâu
— đúng câu hỏi mà thảo luận RBAC tầng RAG (19b) nêu ra.

## 2. Ba quyết định thiết kế

### 2.1 Ghi ở tầng TOOL, không ở `transport.call()`

`Gateway._call()` là điểm thắt nút thật, **nhưng nó chỉ biết `model` + `method`**
— không biết tên tool. Và một tool gọi gateway vài lượt (`sales.py` một mình có
9 chỗ), nên ghi ở đó cho nhiều dòng vô danh cho một hành động.

`build_erp_query_tools` kết thúc bằng một vòng lặp áp sẵn hai wrapper — thêm
wrapper thứ ba ở đó là **một chỗ, phủ cả 28 tool**, và cho **một dòng mỗi lời
gọi tool** kèm tên + tham số. Đúng đối xứng với cách đường GHI log ở `odoo()`.

### 2.2 KHÔNG hash-chain

* `compute_entry_hash` sống ở cây `mcp-servers/odoo`; backend không dùng chung.
  Chain nghĩa là **chép lại công thức băm** (đặt một nguyên thủy an ninh ở hai
  nơi rồi chờ nó trôi) hoặc nhập chéo cây.
* `verify_audit_chain` **lọc `WHERE entry_hash IS NOT NULL`** — dòng không
  chained **hợp lệ theo thiết kế**; dòng `chain_reset` của migration 005 đang
  dùng đúng thế.
* Chain lấy `pg_advisory_xact_lock` mỗi dòng; đọc nhiều hơn ghi nên mọi lượt đọc
  sẽ nối đuôi với mọi lượt ghi qua 6 tiến trình.

Muốn chain sau thì việc đúng là đưa `audit_chain.py` ra chỗ dùng chung — một đợt
refactor riêng.

### 2.3 LƯU GIÁ TRỊ tham số — ngược với quyết định ở mục 17

Chủ dự án chọn **phương án B** sau khi tôi nêu đánh đổi:

| ghi vào log | trả lời được |
|---|---|
| `get_partner_balance` + digest | *"có người xem công nợ"* — không biết **của ai** |
| `get_partner_balance` + args | *"vai kho xem công nợ Azure Interior 14:32"* |

Ở đường GHI, digest là đúng (câu hỏi là "đã ghi gì"). Ở đường ĐỌC, **chính tham
số mới là câu trả lời**. Đánh đổi đã biết: log chứa tên khách, mã đơn, khoảng
ngày người dùng tra — **không** chứa số tiền (đó là *kết quả*, không phải tham
số).

## 3. Nghiệm thu sống (qua cổng vào production)

    06:24:52  erp_query/warehouse  get_partner_balance  user=8d8487b0…  args={"name": "Azure Interior"}
    06:24:53  erp_query/warehouse  get_customer_detail  user=8d8487b0…  args={"name": "Azure Interior"}
    06:24:58  erp_query/sales      find_product         user=2e6aed12…  args={"name_or_code": "Bàn làm việc chân sắt"}
    06:24:59  erp_query/sales      get_product_price    user=2e6aed12…  args={"product_id": 70, "qty": 1.0}

Đúng câu hỏi mục 17b đặt ra, trả lời được cả **ai**, **vai nào**, và **của ai**.

## 4. ⚠️ Nghiệm thu sống lộ ra một lỗ mà test không thấy

Hai dòng ghi `caller=erp_query/?`, `user=—`: `skill_loader.build_skill_tools`
dựng tool đọc **không kèm vai**, và các nút SOP dùng chính instance đó. Nghĩa là
**mọi lượt đọc qua một SOP mất cả vai lẫn người dùng** — đúng nửa giá trị của
mục này, ở đúng đường mà nghiệp vụ phức tạp nhất đi qua.

Đã sửa: `role_cfg` đi qua `build_skill_node` → `build_skill_tools` →
`build_erp_query_tools`. Kiểm trực tiếp (không qua LLM, để không phụ thuộc router
có chọn đúng SOP hay không):

    role_cfg=warehouse  -> caller=erp_query/warehouse
    role_cfg=None       -> caller=erp_query/?      (lùi trung thực)

**Giới hạn thành thật:** tôi KHÔNG tái hiện được ca SOP qua cổng vào production
sau bản sửa — hai lần hỏi đều bị router đưa sang nhánh khác. Bằng chứng ở trên là
mức hàm, không phải đầu-cuối.

`evals/run_eval.py` vẫn gọi `build_erp_query_tools()` không vai ⇒ lượt chạy eval
ghi `erp_query/?`. Chấp nhận được: đó không phải lưu lượng người dùng, và nhãn
`?` nói đúng sự thật.

## 5. Khó khăn / hướng đã chọn / giới hạn còn lại

**Khó khăn 1 — vòng nhập.** `src/erp_query/audit.py` cần biết ai đang hỏi, mà
`agents/graph.py` đã nhập `src.erp_query.tools`. *Hướng đã chọn*: tách ContextVar
ra `src/phien.py` — module LÁ, không phụ thuộc nội bộ nào, nên không chu trình
nào tạo được. `erp_agent.py` re-export để mọi chỗ đang nhập không phải đổi.

**Khó khăn 2 — bộ quét rò lỗi bắt chính mã của tôi.** `test_khong_ro_loi_doc.py`
quét `src/erp_query/*.py` tìm nội suy nguyên văn exception. *Hướng đã chọn*: ghi
**chỉ tên loại lỗi** (`type(e).__name__`) — với vệt kiểm toán đọc thế là đủ,
nguyên văn đã được `envelope.fail_read` log riêng. Có cơ chế miễn trừ nhưng miễn
trừ là nợ, và ở đây không cần.
⚠️ Bộ quét đọc theo DÒNG nên nó bắt cả **chú thích** giải thích chính khuôn đó —
phải viết lại chú thích, không nới bộ quét.

**Khó khăn 3 — bộ test làm bẩn bảng kiểm toán, lần thứ hai.** Đo được ngay lượt
đầu: `tests/erp_query/` thêm **9 dòng**. *Hướng đã chọn*: conftest tắt
`DATABASE_URL`, cùng khuôn `tests/mcp/conftest.py`. Đo lại: 14 → 14.

**Khó khăn 4 — hai test ghim thứ không phải bất biến.**
`test_erp_write_executor_va_skill_node_khong_di_qua_tools_for_coordinator` ghim
`args[-1] == "tools"`; thêm `role_cfg` vào sau làm nó đỏ, dù bất biến thật
(`mcp_tools` phải là `tools`) không đổi. Và regex một dòng của nó không bắt được
lời gọi trải hai dòng, nên thông điệp lỗi nói sai hẳn bản chất (*"không tìm thấy
build_skill_node"* trong khi nó vẫn ở đó). Đã ghim theo **vị trí tham số
mcp_tools** + `re.S`.

**Giới hạn còn lại:** `args_json` **không** nằm trong chuỗi hash (§2.2), nên dòng
đọc sửa/xoá được mà không bị phát hiện. Nửa hệ quả nặng hơn (đường GHI) vẫn được
chuỗi bảo vệ.
