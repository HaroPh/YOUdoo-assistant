# Đợt đánh bóng demo — mục 3, 21, 22, 24

**Ngày**: 2026-08-23. **Nhánh**: `main`.

Bốn mục nhỏ, chọn vì **đều đã đo được** và đều là thứ người xem demo chạm phải
trong mười phút đầu.

## 1. Mục 3 — "cái thứ 2" làm trợ lý trông như bị treo

**Đo sống trước khi sửa:** trợ lý đưa danh sách đánh số 5 sản phẩm; người dùng
gõ *"cái thứ 2"* ⇒ nó **lặp lại y nguyên danh sách trong 0,2s**. Không hiểu, và
cũng không nói là không hiểu. 0,2s vì nó thậm chí không gọi LLM — `parse_selection`
trả `None` và nút hỏi lại.

Nguyên nhân: parser chỉ nhận **số trần** (`"2"`), tên khớp chính xác, hoặc một
chuỗi con duy nhất. Tức nó chỉ nhận đúng MỘT cách gõ, trong khi danh sách đánh
số là thứ **chính trợ lý** đưa ra.

Nay nhận thêm: số nằm trong câu (*"cái thứ 2"*, *"số 2"*, *"mục 2"*, *"2 nhé"*),
chữ chỉ thứ tự tiếng Việt (*"đầu tiên"*, *"thứ nhì"*, *"cuối cùng"*), và tên gõ
thiếu sau phần số lượng (*"2 cái bàn học sinh"* → bóc *"2 cái"* → khớp tên).

**Đánh đổi đã chọn:** TÊN khớp trước, số thứ tự chỉ dùng khi không tên nào khớp
— *"2 cái bàn học sinh"* là nêu tên kèm số lượng, không phải chọn mục 2.
**KHÔNG đoán khi còn phân vân:** *"1 hoặc 2"* trả `None` để hỏi lại; chọn bừa
trong một luồng GHI tệ hơn hỏi thêm một câu.

Nghiệm thu: *"cái thứ 2"* → vào thẳng báo giá đúng sản phẩm, 0,5s.

## 2. Mục 21 — `draft`/`sale` hiện thô ra người dùng

Hỏi *"5 đơn bán gần nhất kèm trạng thái"* trả về `draft`, `sale` — chữ nội bộ
Odoo, vô nghĩa với người dùng Việt.

Khuôn đúng **đã tồn tại**: `mrp.py` có `_STATE_LABELS` từ trước. Nhưng chỉ phủ
lệnh sản xuất; bốn miền còn lại vẫn trả chữ thô. Gom về `state_labels.py` dùng
chung thay vì chép sang bốn module — bốn bản sao của một bảng là cách nó trôi.

Bảng tra theo **(model, state)**, không phẳng: cùng mã `done` là *"hoàn tất"*
với lệnh sản xuất, *"đã giao"* với phiếu kho, *"đã khóa"* với đơn bán. Mã lạ
**trả nguyên** chứ không nuốt thành rỗng — nó là tín hiệu để bổ sung bảng.

Kèm **rào chống trôi đọc trên mã nguồn**: bắt hình dạng đã gây lỗi — nội suy
thẳng `{...['state']}` vào f-string mà không qua `nhan_trang_thai`. Đã thử phá:
trả một chỗ về chữ thô ⇒ đỏ đúng module đó.

Nghiệm thu: `Nháp` / `Đã xác nhận`.

## 3. Mục 22 — ⚠️ nạp ấm MỘT nửa là chưa đủ, và tôi suýt tuyên bố xong

| trạng thái | câu hỏi tài liệu ĐẦU TIÊN sau restart |
|---|---|
| không nạp ấm | **15,8s** |
| chỉ nạp ấm reranker | **10,9s** ← tôi dự đoán ~5s |
| nạp ấm reranker **+ embedder** | **6,1s** |

Lượt ấm để so: 4,2–7,0s.

Vòng một tôi chỉ nạp ấm reranker, log in ra `✓ reranker đã nạp ấm`, và nếu dừng
ở đó thì đã báo cáo "xong" trên một cải thiện **chưa tới một nửa**. Chỉ biết vì
đo lại lượt đầu thay vì tin dòng log.

Phần còn lại: `OllamaEmbedder` gọi HTTP, và Ollama nạp model theo yêu cầu rồi tự
gỡ khỏi VRAM sau một lúc nhàn rỗi.

Cả hai hàm `nap_am()` đều **fail-open**: hỏng chỉ có nghĩa "vẫn nạp lười như
cũ", không được làm backend không khởi động được. Bản reranker cố ý **không đặt
sentinel hỏng** — đặt sẽ TẮT VĨNH VIỄN reranker cho cả tiến trình vì một lỗi có
thể chỉ nhất thời.

## 4. Mục 24 — lời từ chối nêu được tên bộ phận

5 tool Sản xuất (và 5 tool Mua hàng còn thiếu) nay có trong `DEPT_OF`. Trước:
*"không thuộc quyền hạn của bộ phận Kho"* rồi hết — người dùng không biết hỏi
ai. Nay: *"Vui lòng liên hệ bộ phận **Sản xuất**"*.

Kéo theo hai lưới đỡ đỏ lên, cả hai đều đúng việc:

* **`test_moi_tool_trong_DEPT_OF_deu_duoc_xep_loai`** — phải xếp 10 tool mới vào
  `HANDOFF_DOC_OF` (có `order_ref` ⇒ bàn giao được) hoặc `NO_DOCUMENT_TOOLS`
  (tạo mới, hoặc nhận ID nội bộ như `bom_id` mà người dùng không gõ được).
* **`test_moi_model_dich_trong_bang_deu_duoc_khai_o_it_nhat_mot_vai`** —
  docstring của nó dặn *"đo thật rồi thêm"*. Đo thật (tạo `mail.activity` trên
  bản ghi CÓ THẬT của từng model rồi xoá):

      ai-warehouse   sale.order, stock.picking
      ai-accounting  sale.order, purchase.order, account.move, stock.picking
      ai-sales       sale.order, account.move, stock.picking,
                     mrp.production, crm.lead     ← KHÔNG có purchase.order

  Hai dòng đầu khớp nguyên bảng cũ. Dòng thứ ba lộ ra một khoảng trống tôi tạo
  ra ở đợt trước: **vai `sales` chưa có mục nào trong `ACTIVITY_MODELS_OF`**,
  tức nó không bị lọc đích bàn giao gì cả.

  ⚠️ Phép đo ĐẦU dùng `res_id=1` và **không phân biệt được "cấm" với "bản ghi
  không tồn tại"** — phải đo lại bằng id thật mới ra bảng trên. Đã dọn 22
  activity probe sinh ra trong lúc đo.

## 5. Giới hạn còn lại

* `_TU_DON_VI` (cái/chiếc/con/bộ…) là danh sách gõ tay; đơn vị lạ sẽ không bóc
  được và câu rơi về nhánh số. Hỏng về phía an toàn (hỏi lại), không phải chọn sai.
* `state_labels.py` phủ 6 model. Model thứ bảy sẽ rơi về bảng chung
  (`draft`/`cancel`) và trả nguyên mã cho các state khác — hiện ra thô, đúng ý
  đồ, nhưng vẫn cần người thêm vào.
* Nạp ấm làm backend lên **chậm hơn vài giây**. Cố ý: thà thế còn hơn người hỏi
  tài liệu đầu tiên gánh ~10s.
