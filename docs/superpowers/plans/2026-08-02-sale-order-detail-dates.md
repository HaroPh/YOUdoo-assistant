# Sửa lỗ hổng tra cứu trung gian — `get_sale_order_detail` có ngày — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `get_sale_order_detail` trả về thêm `date_order`/`delivery_status` (đã
chứng minh đọc được qua `list_sale_orders` trên cùng model), loại bỏ hoàn toàn
nhu cầu phối hợp 2 tool cho câu hỏi chỉ nêu mã đơn — và bỏ hẳn quy tắc
`GATHER_ERP_PROMPT` vừa thêm ở plan trước (tiền đề của nó không còn đúng, và
chính nó là nguồn gây một hồi quy khác đã vá tạm bằng loại trừ).

**Architecture:** Sửa `get_sale_order_detail` (thêm field vào `search_read`,
không cần sửa văn bản `message` — model đọc JSON đầy đủ qua `_json()`, không
qua prose). Bỏ hẳn quy tắc chọn tool trong `GATHER_ERP_PROMPT`. Sửa 2 fixture
`GATHER_CASES` đang giả định sai khả năng của `get_sale_order_detail` (bug
"hạng lỗi thứ ba" đã ghi nhận từ plan trước — fixture không khớp thực tế
tool). Trình tự xác minh giữ nguyên kỷ luật đã dùng suốt dự án: sửa code →
đo thật → có nhánh BLOCKED tường minh nếu không đạt kỳ vọng, không tự ý đoán
tiếp.

**Tech Stack:** Python 3.12, LangChain 1.2.18, pytest 9.1.1.

**Spec:** `docs/superpowers/specs/2026-08-02-sale-order-detail-dates-design.md`

## Global Constraints

- **0 dòng thay đổi trong `backend/src/agents/graph.py`, `fanout.py`,
  `state.py`.**
- **Chỉ sửa đơn bán** (`backend/src/erp_query/sales.py`). KHÔNG đụng
  `backend/src/erp_query/purchase.py` (`get_purchase_order_detail` có cùng
  hình dạng lỗi nhưng chưa có bằng chứng thật — ghi nhận rủi ro, không sửa).
- **Chỉ sửa 2 case `GATHER_CASES` đã có** (`sla_giao_hang`,
  `chinh_sach_hoan_hang`) — KHÔNG thêm case mới, KHÔNG đụng 2 case còn lại
  (`chinh_sach_thanh_toan`, `bang_gia_chiet_khau`).
- **Trình tự bắt buộc, không được đảo**: sửa `sales.py`/`tools.py` (Task 1) →
  sửa fixture + bỏ quy tắc prompt (Task 2) → đo THẬT xác nhận CẢ HAI case
  `gather` PASS KHÔNG CẦN quy tắc dẫn dắt. Nếu không đạt, DỪNG LẠI, báo cáo
  BLOCKED, KHÔNG tự ý thêm quy tắc mới hay đoán cách sửa khác.
- Chạy Python bằng `backend/.venv/Scripts/python.exe`. Đặt
  `PYTHONIOENCODING=utf-8` trước lệnh in tiếng Việt hoặc chạy job/script gọi
  LLM/Odoo thật. Job `jobs run eval-gate` KHÔNG tự nạp `.env` — export thủ
  công trước: `set -a && source ../.env && set +a` (chạy trong `backend/`).
- "Full suite" (Task 3) = `pytest -m "not integration and not live"` (unit-
  only) + `pytest -m integration`. Không có chế độ "mặc định" nào tự loại
  `live`/`integration`.
- Sau mỗi lượt chạy test đụng `tests/rag/`, nếu 2 file fixture nhị phân
  (`backend/tests/rag/fixtures/bang_gia.xlsx`, `policy.docx`) bị đổi, khôi
  phục: `git checkout -- backend/tests/rag/fixtures/bang_gia.xlsx backend/tests/rag/fixtures/policy.docx`.

---

## File Structure

| Thao tác | File | Trách nhiệm |
|---|---|---|
| Sửa | `backend/src/erp_query/sales.py` | `get_sale_order_detail` đọc thêm `date_order`/`delivery_status` |
| Sửa | `backend/src/erp_query/tools.py` | Docstring tool `get_sale_order_detail` nói rõ có ngày/trạng thái giao |
| Sửa | `backend/tests/erp_query/test_sales.py` | Test mới xác nhận field mới đọc được |
| Sửa | `backend/tests/erp_query/test_tools.py` | Test mới xác nhận docstring có nhắc ngày/trạng thái giao |
| Sửa | `backend/src/agents/prompts.py` | `GATHER_ERP_PROMPT` — bỏ hẳn quy tắc chọn tool vừa thêm ở plan trước |
| Sửa | `backend/evals/cases.py` | 2 case `GATHER_CASES` — `required_tools` quay về `get_sale_order_detail`, fixture có ngày |
| Sửa | `backend/tests/agents/test_fanout.py` | Xoá test guard cho quy tắc đã bỏ |
| Sửa | `docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix-report.md` | Đính chính mục "CẢNH BÁO QUAN TRỌNG" — đã vá |
| Tạo | `docs/superpowers/plans/2026-08-02-sale-order-detail-dates-report.md` | Báo cáo số đo TRƯỚC/SAU — sản phẩm chính của Task 2-3 |

---

## Task 1: `get_sale_order_detail` đọc thêm `date_order`/`delivery_status`

**Files:**
- Modify: `backend/src/erp_query/sales.py:49-68` (`get_sale_order_detail`)
- Modify: `backend/src/erp_query/tools.py:87-90` (docstring tool)
- Test: `backend/tests/erp_query/test_sales.py`
- Test: `backend/tests/erp_query/test_tools.py`

**Interfaces:**
- Consumes: không phụ thuộc task nào khác — task độc lập, kiểm tra được qua
  gateway giả lập, không cần LLM/Odoo thật.
- Produces: `sales.get_sale_order_detail(ref, *, gw=None)` trả về
  `out["data"]["order"]["date_order"]` và
  `out["data"]["order"]["delivery_status"]` khi gateway có dữ liệu. Tool
  `get_sale_order_detail` (LangChain `@tool`) có docstring mới. Task 2 dựa
  vào cả hai để đo thật.

- [ ] **Step 1: Đọc đúng vị trí cần sửa**

Mở `backend/src/erp_query/sales.py`, xác nhận `get_sale_order_detail` (dòng
49-68) khớp CHÍNH XÁC:

```python
def get_sale_order_detail(ref, *, gw=None):
    gw = gw or default_gateway()
    try:
        orders = gw.search_read("sale.order", [["name", "=", ref]],
                                ["id", "name", "partner_id", "amount_total", "state"], limit=2)
        if not orders:
            return err(f"Không tìm thấy đơn '{ref}'.")
        if len(orders) > 1:
            return err(f"Có nhiều đơn tên '{ref}'.")
        o = orders[0]
        lines = gw.search_read("sale.order.line", [["order_id", "=", o["id"]]],
                               ["id", "product_id", "product_uom_qty", "price_unit", "price_subtotal"],
                               order="id asc", limit=100)
    except Exception as e:                                  # noqa: BLE001
        return err(f"Lỗi tra cứu chi tiết đơn: {e}")
    body = "\n".join(f"  {(l['product_id'] or [0, 'N/A'])[1]} | SL {l['product_uom_qty']:.1f} "
                     f"| {l['price_unit']:,.0f} | {l['price_subtotal']:,.0f}" for l in lines)
    return ok({"order": o, "lines": lines},
              f"Đơn {o['name']} | {(o['partner_id'] or [0, 'N/A'])[1]} "
              f"| Tổng {o['amount_total']:,.0f}\n{body}")
```

Nếu KHÔNG khớp, DỪNG LẠI, báo cáo NEEDS_CONTEXT kèm nội dung thật.

- [ ] **Step 2: Viết test thất bại trước (TDD)**

Mở `backend/tests/erp_query/test_sales.py`. Thêm hàm test mới NGAY SAU
`test_get_sale_order_detail_includes_state` (kết thúc ở dòng 68):

```python
def test_get_sale_order_detail_includes_dates():
    order_rows = [{"id": 7, "name": "S00007", "partner_id": [41, "Azur"],
                   "amount_total": 320000.0, "state": "draft",
                   "date_order": "2026-07-18 16:55:50",
                   "delivery_status": "pending"}]
    line_rows = []

    class TwoCallTransport:
        def __init__(self): self.calls = []
        def call(self, model, method, args, kwargs):
            self.calls.append((model, method, args, kwargs))
            return order_rows if model == "sale.order" else line_rows

    gw = Gateway(TwoCallTransport())
    out = sales.get_sale_order_detail("S00007", gw=gw)
    assert out["status"] == "success"
    assert out["data"]["order"]["date_order"] == "2026-07-18 16:55:50"
    assert out["data"]["order"]["delivery_status"] == "pending"
    order_call = next(c for c in gw._t.calls if c[0] == "sale.order")
    assert "date_order" in order_call[3]["fields"]
    assert "delivery_status" in order_call[3]["fields"]
```

- [ ] **Step 3: Chạy test, xác nhận FAIL**

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/erp_query/test_sales.py::test_get_sale_order_detail_includes_dates -v
```

Expected: FAIL — `KeyError: 'date_order'` (field chưa được đọc).

- [ ] **Step 4: Sửa `get_sale_order_detail` — thêm 2 field**

Thay đúng dòng `search_read` đầu tiên trong hàm (chỉ đổi danh sách field,
không đổi gì khác trong hàm):

```python
        orders = gw.search_read("sale.order", [["name", "=", ref]],
                                ["id", "name", "partner_id", "amount_total", "state",
                                 "date_order", "delivery_status"], limit=2)
```

Không sửa `body`/dòng văn bản trả về (`f"Đơn {o['name']}..."`) — model đọc
được 2 field mới qua JSON đầy đủ của envelope (`tools.py::_json()` dump
nguyên vẹn `data.order`), không qua prose. `list_sale_orders` (hàm song
sinh, dòng 24-46) cũng KHÔNG đưa `date_order`/`delivery_status` vào prose —
chỉ nằm trong `rows` — đây là tiền lệ đã có, không phải ngoại lệ.

- [ ] **Step 5: Chạy lại test, xác nhận PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/erp_query/test_sales.py -v
```

Expected: TẤT CẢ pass, bao gồm `test_get_sale_order_detail_includes_dates`
mới VÀ `test_get_sale_order_detail_includes_state` cũ (không hồi quy).

- [ ] **Step 6: Sửa docstring tool trong `tools.py`**

Mở `backend/src/erp_query/tools.py`, xác nhận dòng 87-90 khớp CHÍNH XÁC:

```python
    @tool
    def get_sale_order_detail(ref: str) -> str:
        """Chi tiết dòng sản phẩm của một đơn bán theo mã (vd S00042)."""
        return _json(sales.get_sale_order_detail(ref))
```

Thay dòng docstring bằng:

```python
    @tool
    def get_sale_order_detail(ref: str) -> str:
        """Chi tiết đơn bán theo mã (vd S00042): dòng sản phẩm, ngày xác nhận (date_order), trạng thái giao (delivery_status)."""
        return _json(sales.get_sale_order_detail(ref))
```

Không đổi gì khác trong hàm.

- [ ] **Step 7: Viết test guard cho docstring mới**

Mở `backend/tests/erp_query/test_tools.py`. Xác nhận đầu file có
`from src.erp_query.tools import build_erp_query_tools` (dòng 4). Thêm hàm
test mới ở cuối file:

```python
def test_get_sale_order_detail_description_mentions_dates():
    tool = next(t for t in build_erp_query_tools()
                if t.name == "get_sale_order_detail")
    assert "ngày xác nhận" in tool.description
    assert "trạng thái giao" in tool.description
```

- [ ] **Step 8: Chạy test mới, xác nhận PASS**

```bash
.venv/Scripts/python.exe -m pytest tests/erp_query/test_tools.py::test_get_sale_order_detail_description_mentions_dates -v
```

Expected: PASS.

- [ ] **Step 9: Chạy toàn bộ test đơn vị của `erp_query`, xác nhận không hồi quy**

```bash
.venv/Scripts/python.exe -m pytest tests/erp_query/ -v
```

Expected: TẤT CẢ pass.

- [ ] **Step 10: Commit**

```bash
git add backend/src/erp_query/sales.py backend/src/erp_query/tools.py \
        backend/tests/erp_query/test_sales.py backend/tests/erp_query/test_tools.py
git commit -m "feat(erp_query): get_sale_order_detail đọc thêm date_order/delivery_status"
```

---

## Task 2: Bỏ quy tắc `GATHER_ERP_PROMPT`, sửa fixture, đo THẬT — có nhánh BLOCKED

**Chỉ thực hiện task này SAU khi Task 1 hoàn tất và review sạch.** Nếu Task 1
chưa xong, KHÔNG bắt đầu task này.

**Files:**
- Modify: `backend/src/agents/prompts.py:152` (`GATHER_ERP_PROMPT`)
- Modify: `backend/evals/cases.py:515-530` (2 case `GATHER_CASES`)
- Modify: `backend/tests/agents/test_fanout.py:52-60` (xoá 1 test)
- Create: `docs/superpowers/plans/2026-08-02-sale-order-detail-dates-report.md`

**Interfaces:**
- Consumes: `sales.get_sale_order_detail` đã có `date_order`/`delivery_status`
  (Task 1). `evals.run_eval.eval_gather`, `--set gather` (đã có sẵn, SP-2c).
- Produces: `GATHER_ERP_PROMPT` không còn quy tắc chọn tool đặc thù; 2 case
  `GATHER_CASES` phản ánh đúng khả năng thật; số đo thật (kỳ vọng PASS) ghi
  vào report.

- [ ] **Step 1: Đọc đúng vị trí cần sửa trong `prompts.py`**

Mở `backend/src/agents/prompts.py`, xác nhận `GATHER_ERP_PROMPT` khớp CHÍNH
XÁC (bản đã thêm quy tắc ở plan trước):

```python
GATHER_ERP_PROMPT = """Bạn là bộ phận THU THẬP DỮ KIỆN ERP. Nhiệm vụ duy nhất: dùng các tool đọc Odoo để lấy ra những dữ kiện liên quan đến câu hỏi của người dùng.

Quy tắc:
- Chỉ NÊU DỮ KIỆN, dạng gạch đầu dòng ngắn (mã đơn, ngày, số lượng, trạng thái, tên khách, tên sản phẩm...).
- Câu hỏi hỏi về SLA giao hàng, chính sách hoàn hàng, bảo hành, hoặc đổi trả trên MỘT đơn bán cụ thể (kể cả khi không nói thẳng chữ "ngày"/"trạng thái giao" — những câu hỏi này CẦN ngày giao thực tế để tính hạn): dùng `list_sale_orders` (lọc theo tên khách hàng hoặc điều kiện, tìm đúng dòng có mã đơn khớp trong kết quả) — KHÔNG dùng `get_sale_order_detail` cho việc này (tool đó chỉ có dòng sản phẩm, KHÔNG có ngày hay trạng thái giao). Quy tắc này KHÔNG áp dụng cho câu hỏi về thanh toán, hoá đơn, hay chiết khấu — với những câu hỏi đó chỉ dùng đúng tool tương ứng (ví dụ `get_overdue_invoices`, `get_product_price`), KHÔNG tự ý gọi thêm `list_sale_orders`.
- TUYỆT ĐỐI KHÔNG kết luận, không phán quyết câu hỏi của người dùng. Một bộ phận khác sẽ làm việc đó.
- KHÔNG viện dẫn chính sách/quy định/tài liệu nội bộ — bạn không có tài liệu trong tay, và một bộ phận khác đang lo phần đó.
- CHỈ dùng dữ kiện do tool trả về. Tuyệt đối không bịa số liệu.
- Nếu không lấy được dữ kiện nào liên quan, trả lời đúng một câu: Không tìm được dữ kiện ERP liên quan.
- KHÔNG thực hiện thao tác ghi/tạo/sửa/xác nhận. /no_think"""
```

Nếu KHÔNG khớp, DỪNG LẠI, báo cáo NEEDS_CONTEXT.

- [ ] **Step 2: Bỏ hẳn quy tắc — quay về bản trước plan trước**

Thay TOÀN BỘ khối trên bằng (xoá đúng 1 gạch đầu dòng, giữ nguyên mọi dòng
khác y hệt):

```python
GATHER_ERP_PROMPT = """Bạn là bộ phận THU THẬP DỮ KIỆN ERP. Nhiệm vụ duy nhất: dùng các tool đọc Odoo để lấy ra những dữ kiện liên quan đến câu hỏi của người dùng.

Quy tắc:
- Chỉ NÊU DỮ KIỆN, dạng gạch đầu dòng ngắn (mã đơn, ngày, số lượng, trạng thái, tên khách, tên sản phẩm...).
- TUYỆT ĐỐI KHÔNG kết luận, không phán quyết câu hỏi của người dùng. Một bộ phận khác sẽ làm việc đó.
- KHÔNG viện dẫn chính sách/quy định/tài liệu nội bộ — bạn không có tài liệu trong tay, và một bộ phận khác đang lo phần đó.
- CHỈ dùng dữ kiện do tool trả về. Tuyệt đối không bịa số liệu.
- Nếu không lấy được dữ kiện nào liên quan, trả lời đúng một câu: Không tìm được dữ kiện ERP liên quan.
- KHÔNG thực hiện thao tác ghi/tạo/sửa/xác nhận. /no_think"""
```

- [ ] **Step 3: Xoá test guard cho quy tắc đã bỏ**

Mở `backend/tests/agents/test_fanout.py`, xác nhận dòng 52-60 khớp CHÍNH
XÁC:

```python
def test_gather_erp_prompt_has_sla_return_tool_selection_rule():
    # Quy tắc chọn tool cuối cùng (Bước 2c, 2026-08-01
    # gather-erp-tool-selection-fix) — chốt bằng test này để không bị xoá
    # nhầm ở lần sửa prompt sau.
    from src.agents.prompts import GATHER_ERP_PROMPT
    assert "list_sale_orders" in GATHER_ERP_PROMPT
    assert "SLA giao hàng" in GATHER_ERP_PROMPT
    assert "chính sách hoàn hàng" in GATHER_ERP_PROMPT
    assert "KHÔNG áp dụng cho câu hỏi về thanh toán" in GATHER_ERP_PROMPT
```

XOÁ HẲN hàm này (cả dòng comment phía trên). Giữ nguyên
`test_gather_erp_prompt_forbids_concluding` và
`test_gather_erp_prompt_forbids_citing_documents` (2 hàm liền kề trước/sau).

- [ ] **Step 4: Chạy `test_fanout.py`, xác nhận sạch**

```bash
.venv/Scripts/python.exe -m pytest tests/agents/test_fanout.py -v
```

Expected: TẤT CẢ pass (không còn hàm vừa xoá trong danh sách test chạy).

- [ ] **Step 5: Đọc đúng vị trí cần sửa trong `cases.py`**

Mở `backend/evals/cases.py`, xác nhận `GATHER_CASES` (dòng 509-530) khớp
CHÍNH XÁC:

```python
GATHER_CASES = [
    # sla_giao_hang — SỬA sau điều tra 2026-08-01: dữ liệu ngày chuyển từ
    # get_sale_order_detail (KHÔNG có field ngày thật — sales.py:49-68) sang
    # list_sale_orders (CÓ date_order/delivery_status thật — sales.py:24-39,
    # xác nhận bằng gọi Odoo thật). get_sale_order_detail giữ fixture riêng
    # không có ngày, để nếu model lỡ gọi tool cũ thì case vẫn FAIL đúng.
    ("sla_giao_hang", "Đơn S00042 có đáp ứng SLA giao hàng không?",
     ("list_sale_orders",),
     ("18/07/2026", "20/07/2026"),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: sale (đã xác nhận)",
      "list_sale_orders":
      "S00042 | Azure Interior | sale | ngày xác nhận: 18/07/2026 | "
      "ngày giao dự kiến: 20/07/2026"}),
    # chinh_sach_hoan_hang — cùng lý do sửa như sla_giao_hang ở trên.
    ("chinh_sach_hoan_hang", "Đơn S00042 còn được hoàn hàng theo chính sách không?",
     ("list_sale_orders",),
     ("15/07/2026",),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: done (đã giao)",
      "list_sale_orders":
      "S00042 | Azure Interior | done | ngày giao thực tế: 15/07/2026"}),
```

(3 dòng `# chinh_sach_thanh_toan...` và `# bang_gia_chiet_khau...` phía sau
GIỮ NGUYÊN, không liệt kê lại ở đây — không đụng tới.)

Nếu KHÔNG khớp, DỪNG LẠI, báo cáo NEEDS_CONTEXT.

- [ ] **Step 6: Sửa 2 case — quay `required_tools` về `get_sale_order_detail`, dữ liệu ngày vào đúng tool**

Thay đúng khối trên bằng:

```python
GATHER_CASES = [
    # sla_giao_hang — SỬA sau điều tra tiếp theo (2026-08-02):
    # get_sale_order_detail giờ CÓ date_order/delivery_status thật (sửa ở
    # sales.py, xác nhận unit test + Odoo thật) — không cần list_sale_orders
    # cho câu hỏi chỉ nêu mã đơn nữa. Quy tắc GATHER_ERP_PROMPT dẫn dắt sang
    # list_sale_orders đã bị bỏ hẳn (chính nó là nguồn gây lỗ hổng tra cứu
    # trung gian — xem docs/superpowers/specs/2026-08-02-sale-order-detail-dates-design.md).
    ("sla_giao_hang", "Đơn S00042 có đáp ứng SLA giao hàng không?",
     ("get_sale_order_detail",),
     ("18/07/2026", "20/07/2026"),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: sale (đã xác nhận) | "
      "ngày xác nhận: 18/07/2026 | ngày giao dự kiến: 20/07/2026"}),
    # chinh_sach_hoan_hang — cùng lý do sửa như sla_giao_hang ở trên.
    ("chinh_sach_hoan_hang", "Đơn S00042 còn được hoàn hàng theo chính sách không?",
     ("get_sale_order_detail",),
     ("15/07/2026",),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: done (đã giao) | "
      "ngày giao thực tế: 15/07/2026"}),
```

Không đổi 2 case còn lại (`chinh_sach_thanh_toan`, `bang_gia_chiet_khau`).

- [ ] **Step 7: Chạy `test_eval_gather.py`, xác nhận vẫn xanh**

```bash
.venv/Scripts/python.exe -m pytest tests/jobs/test_eval_gather.py -v
```

Expected: TẤT CẢ pass — các test tự-nhất-quán hiện có
(`test_gather_cases_required_facts_exist_in_fixtures`,
`test_gather_cases_required_tools_are_real_erp_tool_names`,
`test_gather_cases_required_tools_have_fixtures`,
`test_gather_cases_facts_not_leaked_by_the_question`) tự động kiểm 2 case
sửa vì chúng lặp qua TOÀN BỘ `GATHER_CASES` — không cần viết test tự-nhất-
quán mới.

- [ ] **Step 8: Chạy full unit suite, xác nhận không hồi quy**

```bash
.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q
```

Expected: xanh, không giảm số lượng test so với TRƯỚC (trừ đúng 1 test bị
xoá ở Step 3, cộng 2 test mới ở Task 1 — net +1 so với baseline trước Task
1). Khôi phục 2 file fixture nhị phân nếu bị đổi (xem Global Constraints).

- [ ] **Step 9: Chạy `--set gather` THẬT — bước quyết định**

```bash
set -a && source ../.env && set +a
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set gather
```

Đọc log JSON job in ra đường dẫn (`logs/jobs/eval-gate-<timestamp>.json`).

**Kỳ vọng: CẢ 4 case PASS** (`"fails": []`, `tool_recall: 1.0`,
`fact_coverage: 1.0`) — đặc biệt `sla_giao_hang` và `chinh_sach_hoan_hang`
PASS MÀ KHÔNG CẦN quy tắc dẫn dắt nào trong prompt (đã bỏ ở Step 2).

**Nếu CẢ 4 case PASS**: đúng kỳ vọng. Chạy lại LẦN 2 để xác nhận tái lập
(không phải may rủi 1 lần):

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set gather
```

Nếu lần 2 cũng 4/4 PASS: ghi cả 2 lần đo vào report (Step 11), sang Step 10.

**Nếu MỘT trong hai case mục tiêu (`sla_giao_hang`, `chinh_sach_hoan_hang`)
KHÔNG PASS** (ở lần 1 hoặc lần 2): DỪNG LẠI. Ghi lại toàn bộ chi tiết case đó
(`called`, `erp_facts`, `tool_recall_ok`, `fact_coverage_ok`) vào report,
báo cáo trạng thái **BLOCKED**. KHÔNG tự ý thêm quy tắc mới vào
`GATHER_ERP_PROMPT` hay đoán cách sửa khác — nêu chính xác dữ liệu quan sát
được, để controller/người dùng quyết định.

**Nếu `chinh_sach_thanh_toan` hoặc `bang_gia_chiet_khau` (2 case KHÔNG bị
đụng) bất ngờ FAIL**: đây là tác dụng phụ ngoài dự kiến của việc BỎ quy tắc
(khó xảy ra về lý thuyết — bỏ quy tắc chỉ có thể làm giảm hành vi gọi thừa
tool, không tăng — nhưng vẫn phải báo cáo nếu quan sát được). Ghi chi tiết,
báo cáo BLOCKED, không tự sửa.

- [ ] **Step 10: Chẩn đoán trực tiếp qua Odoo thật (bypass MCP) — xác nhận 1 lệnh gọi là đủ**

**Chỉ làm bước này nếu Step 9 đạt CẢ 4 case PASS ở cả 2 lần đo.** Tạo file
tạm `backend/_diag_single_call.py` (KHÔNG commit, xoá sau khi xong):

```python
import asyncio
from dotenv import load_dotenv
load_dotenv("../.env")

from evals import run_eval
from src.agents.fanout import make_gather_erp_node
from src.erp_query.tools import build_erp_query_tools
from langchain_core.messages import HumanMessage

async def main():
    llm = run_eval._llm("gemini-3.1-flash-lite", role="fusion")
    called = []
    real_tools = build_erp_query_tools()
    for t in real_tools:
        orig_func = t.func
        def make_wrapper(name, fn):
            def wrapper(*args, **kwargs):
                called.append(name)
                return fn(*args, **kwargs)
            return wrapper
        t.func = make_wrapper(t.name, orig_func)
    node = make_gather_erp_node(llm, real_tools)
    out = await node({"messages": [HumanMessage(
        content="Đơn S00042 có đáp ứng SLA giao hàng không?")]})
    print("CALLED:", called)
    print("ERP_FACTS:", out.get("erp_facts"))

asyncio.run(main())
```

Chạy:

```bash
set -a && source ../.env && set +a
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe _diag_single_call.py
```

**Kỳ vọng**: `CALLED` chỉ chứa `['get_sale_order_detail']` (một lệnh gọi
duy nhất, KHÔNG cần `list_sale_orders`), `ERP_FACTS` chứa cả ngày xác nhận
lẫn ngày giao dự kiến (khớp `18/07/2026`, `20/07/2026`), KHÔNG phải thông
báo fallback của `verify_erp_grounding` ("Xin lỗi, tôi không chắc chắn...").

Ghi kết quả (nguyên văn `CALLED`, `ERP_FACTS`) vào report (Step 11). Xoá
file `_diag_single_call.py` sau khi xong — KHÔNG commit.

Nếu kết quả KHÔNG khớp kỳ vọng (vẫn gọi nhiều tool, hoặc vẫn rơi vào
fallback): ghi chi tiết, báo cáo DONE_WITH_CONCERNS (không phải BLOCKED —
`--set gather` đã PASS ở Step 9, đây là một lớp kiểm tra bổ sung phát hiện
thêm; không tự ý sửa thêm, để controller quyết định).

- [ ] **Step 11: Viết report**

Tạo `docs/superpowers/plans/2026-08-02-sale-order-detail-dates-report.md`:

```markdown
# Báo cáo — sửa lỗ hổng tra cứu trung gian (get_sale_order_detail có ngày)

Plan: `docs/superpowers/plans/2026-08-02-sale-order-detail-dates.md`
Spec: `docs/superpowers/specs/2026-08-02-sale-order-detail-dates-design.md`

## Task 1 — get_sale_order_detail đọc thêm date_order/delivery_status

Unit test: `<N passed>` (`tests/erp_query/`). Commit: `<hash>`.

## Task 2 — Bỏ quy tắc GATHER_ERP_PROMPT, sửa fixture, đo THẬT

### Bước 9 — đo `--set gather` (bước quyết định)

- Lần 1: `tool_recall`: `<số>`, `fact_coverage`: `<số>`, log:
  `logs/jobs/eval-gate-<timestamp>.json`
- Lần 2 (tái lập): `tool_recall`: `<số>`, `fact_coverage`: `<số>`, log:
  `logs/jobs/eval-gate-<timestamp>.json`
- Case `sla_giao_hang`: `<PASS | FAIL, chi tiết called/erp_facts>`
- Case `chinh_sach_hoan_hang`: `<PASS | FAIL, chi tiết called/erp_facts>`

**Kết luận Bước 9:** `<CẢ 4 case PASS 2/2 lần — tiếp tục Bước 10 | BLOCKED,
nêu rõ case nào không đạt>`

### Bước 10 — chẩn đoán trực tiếp qua Odoo thật (bypass MCP)

- `CALLED`: `<danh sách tool thật sự gọi>`
- `ERP_FACTS`: `<nguyên văn>`

**Kết luận Bước 10:** `<1 lệnh gọi get_sale_order_detail đủ trả lời, có cả
2 ngày, không rơi fallback — ĐẠT | không khớp kỳ vọng, nêu chi tiết>`
```

Thay mọi `<...>` bằng giá trị thật.

- [ ] **Step 12: Commit**

Nếu Step 9 và Step 10 ra đúng kỳ vọng:

```bash
git add backend/src/agents/prompts.py backend/evals/cases.py \
        backend/tests/agents/test_fanout.py \
        docs/superpowers/plans/2026-08-02-sale-order-detail-dates-report.md
git commit -m "fix(agents): bỏ quy tắc GATHER_ERP_PROMPT — get_sale_order_detail đã đủ dữ kiện, sửa fixture GATHER_CASES khớp khả năng thật"
```

Nếu Step 9 BLOCKED: vẫn commit đúng những gì đã sửa + report ghi rõ BLOCKED
(không xoá công đã làm), dừng, báo cáo cho controller — KHÔNG tự ý sang
Task 3.

---

## Task 3: Đo `multi_source` thật, full suite, đính chính report cũ, chốt báo cáo

**Chỉ thực hiện task này nếu Task 2 kết luận "đạt kỳ vọng ở cả Bước 9 và
Bước 10".** Nếu Task 2 BLOCKED, task này không được thực hiện.

**Không sửa code thêm** — chỉ đo và ghi nhận.

**Files:**
- Modify: `docs/superpowers/plans/2026-08-02-sale-order-detail-dates-report.md`
  (nối thêm, chốt kết luận cuối)
- Modify: `docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix-report.md`
  (đính chính mục "CẢNH BÁO QUAN TRỌNG")

**Interfaces:**
- Consumes: kết quả Task 1, Task 2.
- Produces: số đo `multi_source` SAU, kết luận cuối cùng của cả plan.

- [ ] **Step 1: Chạy `--set multi_source` thật**

```bash
cd backend
set -a && source ../.env && set +a
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m jobs run eval-gate --set multi_source
```

Ghi lại: verdict, `both_source_coverage`, `citation_validity`,
`fabricated_number`, log gốc.

**Kỳ vọng KHÔNG đổi** so với TRƯỚC (plan trước đo được `0.75`, log
`logs/jobs/eval-gate-20260801T235708.json`) — `eval_multi_source`
(`backend/evals/run_eval.py:590-615`) KHÔNG gọi `gather_erp`, dùng
`erp_block` viết tay cố định làm `erp_facts` cho `render_fuse_input()`. Đây
là kiến trúc đã xác nhận ở Task 3 plan trước (Finding A) — không có đường
dẫn cơ học nào để bản sửa `get_sale_order_detail`/`GATHER_ERP_PROMPT` ảnh
hưởng tới `both_source_coverage`. Nếu số đo THẬT SỰ khác `0.75` (tăng hoặc
giảm), ghi lại trung thực và KHÔNG tự suy diễn xa hơn số đo cho phép —
không có cơ chế nào giải thích một thay đổi, cần điều tra riêng nếu xảy ra.

- [ ] **Step 2: Chạy full suite cả 2 chế độ pytest**

```bash
.venv/Scripts/python.exe -m pytest -m "not integration and not live" -q
.venv/Scripts/python.exe -m pytest -m integration -q
```

Sau mỗi lượt, nếu 2 file fixture nhị phân bị đổi, khôi phục (xem Global
Constraints). Ghi lại số test passed mỗi chế độ.

- [ ] **Step 3: Đính chính report của plan trước**

Mở `docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix-report.md`.
Tìm mục bắt đầu bằng `**CẢNH BÁO QUAN TRỌNG — đọc trước khi xem 6 điều dưới
đây:**` (khoảng dòng 473). Thêm NGAY TRƯỚC dòng đó (không xoá/sửa nội dung
cũ):

```markdown
> **Đính chính (2026-08-02):** lỗ hổng mô tả trong cảnh báo dưới đây ĐÃ
> được vá — xem
> `docs/superpowers/plans/2026-08-02-sale-order-detail-dates-report.md`.
> `get_sale_order_detail` giờ đọc thêm `date_order`/`delivery_status`, và
> quy tắc `GATHER_ERP_PROMPT` mô tả bên dưới (khiến model tránh dùng
> `get_sale_order_detail` cho câu hỏi cần ngày) đã bị BỎ HẲN — không còn
> đúng ở prompt hiện tại. Đoạn dưới đây giữ nguyên làm hồ sơ lịch sử của
> phát hiện gốc.
```

Không xoá, không sửa nội dung "CẢNH BÁO QUAN TRỌNG" gốc phía sau — chỉ thêm
đoạn đính chính này ngay trước nó.

- [ ] **Step 4: Nối kết luận cuối vào report của plan này**

Nối vào `docs/superpowers/plans/2026-08-02-sale-order-detail-dates-report.md`:

```markdown
## Task 3 — multi_source thật (thước đo cuối cùng), full suite, đính chính

- verdict: `<PASS|FAIL>`
- `both_source_coverage`: `<số>` (TRƯỚC, plan trước: `0.75`)
- `citation_validity`: `<số>`
- `fabricated_number`: `<số>`
- log gốc: `logs/jobs/eval-gate-<timestamp>.json`

## Xác minh test

- Unit-only: `<N passed>`
- Integration: `<N passed>`

## Kết luận

Đối chiếu §"Xong nghĩa là" của spec
(`docs/superpowers/specs/2026-08-02-sale-order-detail-dates-design.md`):

1. `get_sale_order_detail` trả về `date_order`/`delivery_status`: `<ĐẠT,
   xem Task 1 | KHÔNG ĐẠT, nêu lý do>`
2. `GATHER_ERP_PROMPT` không còn quy tắc chọn tool đặc thù: `<ĐẠT | KHÔNG
   ĐẠT>`
3. Cả 2 case `GATHER_CASES` mục tiêu PASS thật, đo 2 lần độc lập, không cần
   quy tắc dẫn dắt: `<ĐẠT, xem Task 2 Bước 9 | BLOCKED>`
4. Chẩn đoán trực tiếp qua Odoo thật xác nhận 1 lệnh gọi tool đủ: `<ĐẠT, xem
   Task 2 Bước 10 | KHÔNG ĐẠT>`
5. `multi_source` đo lại, xác nhận không đổi: `<ĐẠT, số đo = 0.75 | SỐ ĐO
   KHÁC, nêu chi tiết — không suy diễn xa hơn>`
6. Toàn bộ test 2 chế độ xanh: `<ĐẠT>`
7. `graph.py`/`fanout.py`/`state.py` — 0 dòng thay đổi: `<ĐẠT, xác nhận bằng
   git diff --stat>`
8. Đính chính đúng 1 chỗ trong report của plan trước: `<ĐẠT, xem Step 3>`

**Tổng kết:** `<một đoạn ngắn, trung thực, không tô hồng — nói thẳng nếu có
điều gì không đạt hoàn toàn>`
```

Thay mọi `<...>` bằng nội dung thật.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-08-02-sale-order-detail-dates-report.md \
        docs/superpowers/plans/2026-08-01-gather-erp-tool-selection-fix-report.md
git commit -m "docs: chốt báo cáo sửa lỗ hổng tra cứu trung gian — multi_source SAU, đính chính report plan trước"
```

---

## Tự soát của tác giả plan

**Phủ spec:**

| Mục spec | Task |
|---|---|
| Kiến trúc — thêm field vào `get_sale_order_detail` | 1 |
| Kiến trúc — không cần sửa văn bản prose | 1 (Step 4 giải thích, không sửa `body`) |
| Thay đổi cụ thể #1-2 (`sales.py`, `tools.py`) | 1 |
| Thay đổi cụ thể #3 (bỏ hẳn quy tắc prompt) | 2 |
| Thay đổi cụ thể #4 (sửa `GATHER_CASES`) | 2 |
| Thay đổi cụ thể #5 (xoá test guard cũ) | 2 |
| Trình tự triển khai & xác minh bước 1-4 | 1, 2 (Step 1-8) |
| Trình tự bước 5 (đo `--set gather`, có nhánh BLOCKED) | 2 (Step 9) |
| Trình tự bước 6 (chẩn đoán Odoo thật) | 2 (Step 10) |
| Trình tự bước 7 (đo `multi_source`, không kỳ vọng đổi) | 3 (Step 1) |
| Trình tự bước 8 (full suite 2 chế độ) | 3 (Step 2) |
| Dọn dẹp tài liệu (đính chính report cũ) | 3 (Step 3) |
| Testing — test mới `test_sales.py` | 1 (Step 2) |
| Testing — test mới mô tả tool | 1 (Step 7) |
| Testing — tự-nhất-quán `GATHER_CASES` (không cần test mới) | 2 (Step 7, xác nhận) |
| Testing — xoá test guard | 2 (Step 3) |
| Phạm vi (không đụng `purchase.py`, `graph.py`/`fanout.py`/`state.py`) | Global Constraints, không task nào đụng các file đó |
| "Xong nghĩa là" điều 1-8 | 3 (Step 4, đối chiếu trực tiếp) |

**Placeholder scan:** không có `TBD`/`TODO` nào trong plan — mọi `<...>`
trong template report đều nằm trong khối markdown dành để implementer điền
số liệu thật khi viết report, không phải placeholder chưa quyết định trong
CHÍNH plan này.

**Type/interface consistency:** `sales.get_sale_order_detail(ref, *,
gw=None)` giữ nguyên chữ ký qua cả 3 task, chỉ đổi field đọc được. Tên tool
LangChain `get_sale_order_detail` không đổi tên/chữ ký, chỉ đổi docstring.
`GATHER_CASES` giữ đúng shape tuple 5 phần tử
`(topic, question, required_tools, required_facts, tool_fixtures)` xuyên
suốt — khớp với `evals/run_eval.py::eval_gather`'s `call()` (dòng 242).

**Điểm khác biệt cố ý so với plan trước:** Task 2 có 2 nhánh rẽ BLOCKED
(Step 9 cho việc đo `gather`, và một nhánh DONE_WITH_CONCERNS nhẹ hơn ở
Step 10 cho chẩn đoán Odoo thật bổ sung) — vì bản chất Task 2 vẫn là kiểm
tra giả thuyết (liệu bỏ quy tắc + sửa tool có đủ hay không), tiếp nối đúng
kỷ luật đã dùng ở plan trước.


