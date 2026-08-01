# SP-2c: bộ đo cho bước thu thập ERP — thiết kế

**Mục tiêu:** Trước khi quyết định có tuần tự hoá fan-out (SP-2b) hay không,
đo THẬT xem `gather_erp` có lấy đủ dữ kiện ERP mà một chính sách đòi hỏi hay
không — điều mà bộ eval `multi_source` hiện tại **không đo được** vì nó đóng
băng `erp_block` viết tay.

**Bối cảnh:** SP-2b (fan-out đường đọc, khai tử node `fusion`) đã xong, merge
vào `main`. §7 của spec SP-2b để lại một câu hỏi mở cho giai đoạn sau: một
supervisor LLM có được phép thay lớp phủ quyết định tuyến tất định hay không.
Trước khi trả lời câu đó, có một câu hỏi RẺ HỚN và NẰM TRÊN ĐƯỜNG TỚI HẠN hơn
xuất hiện khi đọc lại 2 ca `multi_source` còn FAIL sau SP-2b (cả hai fail từ
trước SP-2b, không phải hồi quy): cả hai đều có hình dạng "model biết đúng
mình thiếu field gì, và từ chối kết luận" — chứ không phải bịa. Giả thuyết:
`gather_erp` (chạy song song với `gather_docs`, không thấy chính sách) không
biết cần lấy field nào. Spec này KHÔNG sửa giả thuyết đó — nó CHỈ đo, để biết
giả thuyết đúng hay sai trước khi tiêu tiền sửa.

---

## §0. Vị trí trong lộ trình và phạm vi

| SP | Nội dung | Trạng thái |
|---|---|---|
| SP-2a / SP-2b | SOP skill + fan-out đường đọc | **xong, đã merge** |
| **SP-2c** | *(spec này)* Bộ đo cho bước thu thập ERP | brainstorm xong |
| SP-2d | Sửa thu thập ERP (tuần tự hoá fan-out, hoặc vòng thu thập bổ sung có điều kiện) — CHỈ làm nếu số đo SP-2c xác nhận cần | sau, chờ số |
| (chưa đặt tên) | Supervisor thay/đứng trước lớp phủ quyết tất định | sau, chờ research của chủ dự án về độ tin cậy router-LLM |

### Vì sao đây là SP-2c, không phải "làm supervisor luôn"

Kiểm kê lại động cơ ban đầu cho "SP-2c" trong roadmap cũ (ADR-010: "điều phối
nhiều bước", "kiến trúc rõ/portfolio"): "điều phối nhiều bước" đã có — SOP
skill tự chạy ReAct loop, không ai cần điều phối nó (SP-2a §8). "Kiến trúc
rõ/portfolio" là động cơ duy nhất còn lại và **không đo được**. Trong khi đó,
2 ca `multi_source` FAIL thật lại chỉ thẳng vào một khoảng trống đo được, rẻ
hơn, và không đụng lớp định tuyến — đúng thứ mà bằng chứng hiện có (sự cố
2026-07-16, thí nghiệm model 2026-07-31) đang khuyên đừng vội đụng vào.

### Trong phạm vi

- Bộ ca `GATHER_CASES` trong `evals/cases.py`, tái dùng fixture chính sách
  của `MULTI_SOURCE_CASES`.
- `eval_gather(llm, tools, branch)` gọi **node `make_gather_erp_node` thật**.
- Đăng ký `--set gather` trong `eval_gate.py`, loại khỏi `--set all`.
- Chạy thật, viết báo cáo số đo.

### Ngoài phạm vi — cố ý

| Hạng mục | Vì sao không làm ở đây |
|---|---|
| Sửa `gather_erp`/tuần tự hoá fan-out | SP-2d — chỉ làm nếu số đo ở đây xác nhận cần |
| Supervisor / đổi lớp định tuyến | Treo, chờ research độc lập của chủ dự án về độ tin cậy router-LLM (câu hỏi để ngỏ từ SP-2b §7) |
| Đo qua Odoo thật | Fixture eval và Odoo thật đã lệch nhau (S00042 fixture ghi "trạng thái sale", Odoo thật trả "nháp, chưa giao" — xác nhận lúc live-verify SP-2b). Dựng lại dữ liệu Odoo khớp kịch bản là một việc riêng, không nhỏ |
| Sửa `MULTI_SOURCE_CASES`/`multi_source` | Bộ đó đo đúng việc nó đo (tổng hợp trên fixture đóng băng) — không phải nó sai, chỉ là nó không đo bước thu thập |

---

## §1. Kiến trúc và luồng đo

### 1.1 Node thật, tool giả

`eval_gather` gọi **`make_gather_erp_node` thật** — cùng `GATHER_ERP_PROMPT`,
cùng vòng ReAct, cùng lời gọi `verify_erp_grounding` bên trong nó. Thứ duy
nhất bị thay là tầng tool.

**Stub phải giữ nguyên độ khó chọn tool.** Không bọc riêng vài tool liên quan
rồi đưa model chọn trong một tập nhỏ — như vậy là làm bài dễ đi, số đo vô
nghĩa. Bọc **cả 25** tool từ `build_erp_query_tools()`, giữ nguyên
`name`/`description`/`args_schema` thật (allow-list y hệt production), chỉ
thay THÂN hàm bằng tra cứu fixture: tool liên quan tới ca trả dữ liệu giàu
field; 20+ tool còn lại trả "không có dữ liệu liên quan". Model vẫn phải
chọn đúng trong 25, y như production.

### 1.2 Hình dạng ca đo

```python
GATHER_CASES = [
    # (topic, question, required_tools, required_facts)
    ("sla_giao_hang", "Đơn S00042 có đáp ứng SLA giao hàng không?",
     frozenset({"get_sale_order_detail"}),
     ("ngày xác nhận", "ngày giao", "khẩn cấp")),  # ví dụ minh hoạ, plan chốt thật
    ...
]
```

- `topic` nạp chính sách qua `fixtures.load_chunks(topic)` — **dùng lại
  đúng fixture đang phục vụ `MULTI_SOURCE_CASES`**, để hai bộ đo không kể
  hai câu chuyện khác nhau về cùng một chính sách.
- `required_tools`: frozenset tên tool bắt buộc phải được gọi ít nhất một
  lần trong vòng ReAct.
- `required_facts`: chuỗi khớp NGUYÊN VĂN, hand-verified từ dữ liệu fixture
  thật — cùng kỷ luật `_grounded_match`/`MULTI_SOURCE_DERIVED_DIGITS` đã áp
  dụng trong `multi_source`. Không heuristic mờ.

Dữ liệu fixture cho mỗi tool-stub (field ngày xác nhận, ngày giao, loại đơn,
nhóm sản phẩm...) viết tay, đủ để `required_facts` có thể được thoả nếu
model gọi đúng tool.

### 1.3 Hai nhánh, cùng bộ ca

| Nhánh | Prompt | Vai trò |
|---|---|---|
| `base` | `GATHER_ERP_PROMPT` + câu hỏi — **đúng production hôm nay** | Số được GÁC (chống hồi quy) |
| `policy` | thêm `_format_context(chunks)` (chính sách) vào prompt | Chỉ GHI NHẬN — đầu vào quyết định SP-2d, không gác |

`eval_gather(llm, tools, branch: Literal["base", "policy"])` — tham số
`branch` chọn có ghép chính sách vào input hay không. **Không tạo hai hàm
riêng** — cùng một hàm, một tham số, để không có hai bản logic đo trôi khỏi
nhau (đúng bài học `render_fuse_input` của SP-2b).

Hiệu số `policy − base` là câu trả lời trực tiếp cho "tuần tự hoá có đáng
không", lấy được mà **không sửa một dòng production nào**.

### 1.4 Hai trục đo, tách bạch có chủ đích

- **`tool_recall`**: tỷ lệ ca gọi đủ `required_tools` (lỗi CHỌN sai/thiếu tool).
- **`fact_coverage`**: tỷ lệ ca mà TOÀN BỘ `required_facts` xuất hiện nguyên
  văn trong `erp_facts` cuối cùng (lỗi TRUYỀN ĐẠT — gồm cả trường hợp
  `verify_erp_grounding` cắt nhầm một dữ kiện có thật khỏi câu trả lời).

Tách vì hai trục hỏng theo hai cơ chế khác nhau, cần hai cách sửa khác nhau:
`tool_recall` thấp → vấn đề ở việc chọn tool/mô tả tool; `fact_coverage`
thấp mà `tool_recall` cao → vấn đề ở việc `gather_erp` tóm tắt/lọc quá tay,
hoặc `verify_erp_grounding` quá nghiêm. Gộp thành một điểm sẽ giấu mất sự
khác biệt này.

---

## §2. Cổng đo

`gather` **không có baseline model cũ** — node `make_gather_erp_node` không
tồn tại trước SP-2b, nên không có số qwen3:8b để so baseline-relative kiểu
`intent`/`planner`.

**Quyết định**: đăng ký `--set gather` trong `eval_gate.py`, **loại khỏi
`--set all` ngay từ đầu** — cùng cách đã xử lý `sop_select` ở SP-2a. Không
đợi phát hiện vấn đề rồi mới loại (như đã xảy ra với `sop_select`); loại từ
đầu vì lý do đã biết trước: chưa có gate tuyệt đối nào được xác nhận là sàn
hợp lý cho tới khi có số đo lần đầu.

`--set gather` chạy riêng, tường minh, có comment tại chỗ trong `eval_gate.py`
giải thích lý do loại (theo lệ Phụ lục A).

Nhánh `base` là số **quan sát có gác nhẹ**: nếu `tool_recall`/`fact_coverage`
tụt so với lần đo trước trên CÙNG model, đó là hồi quy thật đáng điều tra —
nhưng không có ngưỡng PASS/FAIL tuyệt đối áp cho lần đo đầu tiên này.

Nhánh `policy` **không có gate nào** — nó đo một thiết kế (tuần tự hoá) chưa
tồn tại trong production, mục đích duy nhất là cung cấp số cho quyết định
SP-2d.

---

## §3. "SP-2c xong" nghĩa là

1. `backend/evals/cases.py` có `GATHER_CASES`, tái dùng
   `fixtures.load_chunks()` của `multi_source`, mỗi ca có `required_tools`/
   `required_facts` hand-verified.
2. `backend/evals/run_eval.py` có `eval_gather(llm, tools, branch)` gọi
   **`make_gather_erp_node` thật** — không dựng lại logic thu thập.
3. `backend/jobs/eval_gate.py` đăng ký `--set gather`, loại khỏi
   `--set all`, có comment tại chỗ giải thích.
4. Chạy thật cả hai nhánh (`base`, `policy`) trên model đang chạy (đầu chuỗi
   catalog vai `fusion`).
5. Báo cáo `docs/superpowers/specs/2026-08-01-sp2c-gather-eval-report.md`
   ghi: `tool_recall`/`fact_coverage` từng nhánh, hiệu số `policy − base`,
   log gốc, và một khuyến nghị rõ ràng (đáng làm SP-2d hay không) — đây là
   SẢN PHẨM CHÍNH của SP-2c, không phải code.
6. `graph.py`, `fanout.py`, `_route_by_intent`, `intent_targets` — **0 dòng
   thay đổi**.
7. Toàn bộ test xanh ở chế độ unit-only (`pytest -m "not integration and not live"`).

**Chưa làm được sau SP-2c:** chưa biết `gather_erp` có thật sự cần sửa hay
không — đó là kết luận của báo cáo, không phải điều spec này giả định trước.
Chưa đụng gì tới câu hỏi supervisor.

---

## Phụ lục A — Quyết định phải có comment tại chỗ

| Quyết định | File |
|---|---|
| `gather` loại khỏi `--set all` ngay từ đầu, không đợi phát hiện vấn đề | `eval_gate.py`, cạnh dict loại trừ |
| Stub tool phải bọc đủ 25 tool (không rút gọn tập lựa chọn) — rút gọn làm bài dễ đi, số đo vô nghĩa | `run_eval.py`, tại `eval_gather` |
| Một hàm `eval_gather(branch=...)`, không hai hàm riêng cho `base`/`policy` — tránh hai bản logic đo trôi khỏi nhau | `run_eval.py`, tại `eval_gather` |
