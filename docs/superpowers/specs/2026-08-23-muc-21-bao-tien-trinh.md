# Mục 21 (phần streaming) — báo tiến trình từng chặng

**Ngày**: 2026-08-22/23. **Nhánh**: `main`.

## 1. Đề bài, và vì sao nó bị đặt sai tên

Bản kiểm toán ghi: *"không có streaming (màn hình trắng 5–20s)"*.

Triệu chứng đúng. Nguyên nhân **sai**. Đo trước khi viết một dòng nào:

| loại lượt | tổng | số ký tự trả về |
|---|---|---|
| tán gẫu | 1,94s | 139 |
| ERP đọc | 9,95s | **74** |
| tài liệu (RAG) | 15,8s | 1 346 |

Lượt ERP mất gần 10 giây để sinh ra **74 ký tự**. Streaming token sẽ giao 74 ký
tự đó trong nửa giây cuối — người dùng vẫn ngồi trắng màn hình ~9,4 giây. Cái
họ thiếu là **biết hệ đang làm gì**, không phải chữ hiện sớm hơn.

Quyết định của chủ dự án: **báo tiến trình từng chặng**, không streaming token.

## 2. Cách làm

* `src/agents/tien_trinh.py` — module riêng (không nằm trong `erp_agent.py` vì
  `nodes.py` cũng cần, mà erp_agent → graph → nodes là một vòng nhập).
* `BaoTienTrinh(AsyncCallbackHandler)` gắn vào `config["callbacks"]`, **chỉ khi
  có người lắng nghe**. Dùng callback chứ không đổi `ainvoke` → `astream`: ba
  chỗ gọi graph trong `_chat_inner` có cả đường `Command(resume=…)` của
  interrupt, đổi kiểu gọi ở đó là đổi hành vi cổng xác nhận ghi.
* `main.py` chạy đường tính câu trả lời như một **task** và vừa chạy vừa rút
  hàng đợi. Tiến trình đi trong khối `<think>…</think>`.

**Vì sao `<think>`:** đọc mã Open WebUI đang chạy
(`utils/middleware.py`, `DEFAULT_REASONING_TAGS`) — thẻ này được dựng thành
panel suy nghĩ **tách khỏi** câu trả lời, nên chữ tiến trình không nằm lại
trong nội dung người dùng lưu.

**Hậu kỳ KHÔNG bị đụng.** `chat()` bóc marker ký ức / chèn dòng báo fallback /
dịch trên câu **hoàn chỉnh**; câu trả lời vẫn đi ra nguyên khối sau `</think>`.
Đây là lý do chọn hướng này thay vì stream chữ thô — stream thô sẽ để **marker
ký ức lọt ra màn hình**, đúng lỗi mà đợt `write-suggest marker trailing-fix` đã
đóng.

## 3. Kết quả đo (thời điểm từng chunk tới)

    === Tồn kho sản phẩm ABC còn bao nhiêu? ===
       0.56s  <think> + "Đang xác định yêu cầu…"
       2.30s  "Đang tra dữ liệu trên hệ thống…"
       4.44s  "Đang soạn câu trả lời…"
       5.56s  "Đang kiểm chứng số liệu…"
       6.58s  [câu trả lời đầy đủ]

Phản hồi đầu tiên: **9,9s → 0,56s**.

## 4. ⚠️ Số đo lật lại kết luận của chính tôi — HAI LẦN

### 4.1 "Độ trễ là ~4 lời gọi LLM nối tiếp" — SAI

Tôi đo từng chặng rời và kết luận như vậy, trong đó có dòng
`tool Odoo THAT (get_stock) 0.01s`. **Lời gọi đó hỏng ngay vì sai tham số.**

Khi thanh tiến trình chạy thật, `on_tool_start` → `on_tool_end` cho thấy **lời
gọi tool mất 6,45 giây** — chặng đắt nhất của cả lượt, gấp ba bất kỳ lời gọi
LLM nào. Chính công cụ hiển thị vừa dựng đã bắt được điều mà phép đo rời bỏ sót.

**Nguyên nhân: `ODOO_URL=http://localhost:8069`.** Đo trực tiếp, 3 lượt mỗi bên:

| địa chỉ | min / trung bình / max |
|---|---|
| `localhost` | 5,141s / 5,188s / 5,234s |
| `127.0.0.1` | 1,062s / 1,073s / 1,094s |

Windows phân giải `::1` trước, còn container bind IPv4. **~4,1 giây lãng phí mỗi
lời gọi ERP.** Postgres không dính (0,015s cả hai chiều).

Sửa một dòng `.env` ⇒ lượt ERP **11,27s → 6,58s**.

Ghi chú repo đã có sẵn về bẫy này (`reference_youdoo_localhost_ipv6_penalty`)
nhưng chỉ áp cho đường RAG; `ODOO_URL` chưa bao giờ được sửa.

### 4.2 "RAG tốn 15,8s" — SAI, đó là lượt NGUỘI

15,8s là **lượt tài liệu đầu tiên sau mỗi lần khởi động lại**: reranker
`BAAI/bge-reranker-v2-m3` nạp trọng số lúc đó. Lượt ấm: **4,9–5,2s**, trong đó
truy xuất chỉ ~1s.

Nói cách khác cả hai con số tôi trích ở §1 cho đường RAG đều là số nguội. Chi
phí thường trực nhỏ hơn ba lần.

**Nợ mới, chưa làm:** nạp ấm reranker lúc khởi động — người hỏi tài liệu đầu
tiên sau mỗi lần restart đang trả ~10s thay cho cả hệ.

## 5. Khó khăn / hướng đã chọn / giới hạn còn lại

**Khó khăn 1 — callback bắn cả cho chain con.** Đo bằng graph dựng riêng: mọi
chain con chạy BÊN TRONG một nút **thừa kế `metadata.langgraph_node` của nút
đó** nhưng mang tag `seq:step:N` chứ không phải `graph:step:N`. Không lọc thì
mỗi lời gọi LLM/tool bên trong `erp_read` lại phát lại nhãn của `erp_read`.
*Hướng đã chọn*: lọc theo tag `graph:step:`.
*Giới hạn*: phụ thuộc chi tiết nội bộ của LangGraph; nếu tag đổi tên thì tiến
trình im lặng biến mất. Test đối chứng dùng đúng hình dạng đã đo nên sẽ đỏ.

**Khó khăn 2 — ca đối chứng đầu tiên KHÔNG đo gì.** Bản đầu dùng
`name="LangGraph"` / `"RunnableSequence"`, hai tên không có trong bảng nhãn nên
phép tra nhãn đã tự loại chúng: **gỡ hẳn bộ lọc đi test vẫn xanh**. Chỉ phát
hiện vì chạy phép thử phá. Bản sửa dùng hình dạng thật (`seq:step:1` +
`langgraph_node="erp_read"`) và đỏ đúng khi gỡ bộ lọc.

**Khó khăn 3 — khử trùng lặp giấu mất chỗ tốn thời gian.** Bản đầu khử theo
NHÃN, đo ra một khoảng 6,9s panel đứng im. Đổi sang khử theo **thời gian**
(`LAP_NHAN_TOI_THIEU_S = 2,0`): lặp lại nhãn sau vài giây không thừa — nó là
bằng chứng hệ vẫn đang chạy.

**Giới hạn còn lại:** chỉ nút và tool có mốc; các chặng con khác vẫn nằm trong
khoảng im lặng. Với cấu hình hôm nay khoảng lớn nhất còn ~2,1s (tra dữ liệu),
chấp nhận được. Và toàn bộ cơ chế này chỉ chạy khi `stream=true`; lượt gọi API
thẳng không đổi gì.
