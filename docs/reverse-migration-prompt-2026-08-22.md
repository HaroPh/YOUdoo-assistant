# Prompt: rà đợt 2 những gì đáng port từ D:\Youdoo về D:\Project

**Ngày soạn**: 2026-08-22 · Đợt 1 là 2026-08-07 (đã chạy, đã backport 2 fix).

Dán toàn bộ phần dưới dấu `---` vào một phiên Claude Code **mở tại `D:\Project`**.

---

Bạn đang ở `D:\Project`. Nhiệm vụ: **rà xem có gì trong `D:\Youdoo` đáng port về
đây không**, rồi viết một spec đề xuất. **Không viết code ở lượt này.**

## 0. Ràng buộc cứng của repo này — đọc trước khi nghĩ

- Chạy **`qwen3:8b` local** qua Ollama/LiteLLM. `CLOUD_ALLOWED = {"router",
  "evaluator", "chitchat"}` (`backend/src/agents/models.py`) — chỉ 3/7 vai được
  phép lên cloud; `read/planner/fusion/synthesis` **ghim cứng local trong mã**.
  Đây là quyết định kiến trúc có văn bản (ADR-009), **không phải thiếu sót**.
- ADR-008 đã **bác** multi-agent vì độ trễ: một lượt có thể tốn **8–12 lời gọi
  LLM tuần tự**. Mọi đề xuất làm tăng số lời gọi phải tự biện minh trước con số
  đó.
- ADR-010 chính là tài liệu đã **đẻ ra `D:\Youdoo`** như một nhánh riêng để thử
  kiến trúc cloud/đa-nhà-cung-cấp. Nghĩa là: Youdoo **không phải** một phiên bản
  tiến hoá hơn của repo này — nó là một nhánh cố ý đi hướng khác. Đừng mặc định
  "Youdoo mới hơn thì tốt hơn".

## 1. Đã backport ở đợt 1 — KHÔNG đề xuất lại

Ngày 2026-08-08, spec `docs/superpowers/specs/2026-08-08-youdoo-backport-safety-fixes-design.md`:

1. Cổng xác nhận **bước đụng tiền** trong auto-chain (`CONFIRM_IN_CHAIN`,
   coordinator cho `post_invoice`/`register_payment`).
2. Phân biệt **lỗi truy xuất/ERP thật** với **kết quả rỗng hợp lệ** trong fan-out.

Đợt đó cũng đã kết luận **KHÔNG port**: tầng cloud `backend/src/llm/`, Langfuse,
`routing.py`, write-suggestion. Giữ nguyên kết luận đó trừ khi bạn có bằng chứng
mới.

## 2. Cách làm — bắt buộc

1. **Đọc mã thật của CẢ HAI repo. Đừng tin danh sách ở mục 3 dưới đây**, kể cả
   những mục ghi "đã xác minh" — hãy tự xác minh lại. Danh sách này là **điểm
   khởi đầu**, không phải kết luận.
2. **`D:\Youdoo` là CHỈ ĐỌC**. Không sửa, không tạo tệp, không chạy/khởi động
   lại tiến trình nào bên đó. Nó có backend + 3 tiến trình MCP + Docker đang
   chạy thật.
3. Với mọi đề xuất **phụ thuộc model** (câu chữ prompt, hành vi định tuyến):
   Youdoo đo trên model cloud, repo này chạy **8B local**. Port **ý tưởng và
   phép đo**, không port câu chữ. Nêu rõ cần đo lại bộ nào.
4. Xếp mỗi đề xuất vào một trong ba nhóm: **đáng làm ngay** / **cần đo trước** /
   **không nên**. Nhóm thứ ba cũng phải viết ra kèm lý do — nó có giá trị ngang
   hai nhóm kia.
5. Ước lượng **giá trị kỳ vọng** và **rủi ro** cho từng mục. Đừng xếp theo thứ
   tự tôi liệt kê.

## 3. Ứng viên

### Nhóm A — đã xác minh có mặt trong mã của repo NÀY, không phụ thuộc model

**A1. `localhost` trong URL hạ tầng → phạt ~2 giây mỗi lời gọi trên Windows.**
Youdoo đo được: Docker bind IPv4-only, còn Windows phân giải `localhost` thử
`::1` **trước**, ăn trọn timeout rồi mới lùi về IPv4. Repo này dùng `localhost`
ở ít nhất: `backend/src/rag/config.py` (`OLLAMA_URL`, `DATABASE_URL`),
`backend/src/agents/models.py` (`LITELLM_URL`), `backend/src/agents/erp_agent.py`.

**Đây có thể là mục giá trị cao nhất của cả đợt**, vì ADR-008 nói một lượt tốn
8–12 lời gọi LLM tuần tự — nếu mỗi lời gọi ăn 2 giây phạt thì đó là **16–24
giây mỗi lượt** hoàn toàn lãng phí. Sửa = đổi `localhost` → `127.0.0.1`.
**Hãy ĐO trước và sau**, đừng chỉ sửa: con số này là thứ đáng đưa vào spec.

**A2. Cổng xác nhận ghi in TÊN TOOL ra người dùng — mâu thuẫn với chính
`tool_leak_guard.py` của repo này.** Đã xác minh: `backend/src/agents/nodes.py`
dòng ~267 in `({plan.get('tool')}: {args_line})`, trong khi
`backend/src/agents/tool_leak_guard.py` tồn tại và cấm đúng chuyện đó.

Youdoo sửa ngày 2026-08-22: **bỏ tên tool, giữ args**. Lý do: mục đích của bất
biến "hiện dữ liệu tất định" là để người dùng thấy **ref thật** trước khi bấm
"có", mà ref nằm ở `args` chứ không nằm ở tên tool — tên tool là định danh nội
bộ, người dùng không làm gì được với nó. Bỏ nó thì **cả hai bất biến cùng
đúng**. Xem `D:\Youdoo\docs\superpowers\specs\2026-08-22-muc-9-12-13.md` §1 và
`backend/tests/agents/test_confirm_khong_lo_ten_tool.py` (test khoá cả hai
chiều, kiểm từng marker chứ không riêng một cái).

**A3. Chân sparse của hybrid retrieval có thể đã CHẾT từ đầu.** Đã xác minh repo
này dùng `plainto_tsquery` (`backend/src/rag/retrieve.py:25-26`). Youdoo đo:
`plainto_tsquery` nối mọi từ bằng **AND**, nên câu hỏi tự nhiên nhiều từ trả
**0/64** kết quả — hệ thực tế chạy dense-only trong khi tưởng là hybrid.

⚠️ **Nhưng đừng vội sửa**: Youdoo hồi sinh chân sparse rồi đo lại thì recall@20
**TỆ ĐI** (1,0 → 0,9766). Nên việc cần làm là **ĐO xem chân sparse của repo này
có đang trả kết quả không**, rồi mới quyết định. Có thể kết luận đúng là "xoá
cho gọn" chứ không phải "sửa".

**A4. Reranker.** Repo này có reranker CPU (`backend/src/rag/config.py`). Youdoo
tìm ra **hai** thứ độc lập: (a) reranker của nó **chết im lặng 6 tuần** vì thiếu
một dependency, và **bốn lớp test đều che mất**; (b) dùng cross-encoder làm **kẻ
ghi đè** thì hại nhóm câu hỏi khó, đổi sang **một lá phiếu** (hoà hạng với RRF)
thì tốt hơn. Kiểm (a) trước — nó rẻ và có thể đang đúng ở đây.

**A5. CLI chết vì cp1252 khi output bị chuyển hướng ra tệp.** Repo này có
`backend/jobs/` với nhiều cửa vào CLI nhưng **không có** `cli_console.py`.
Youdoo: khi Task Scheduler chạy `>> log 2>&1`, Windows dùng ANSI codepage thay
vì UTF-8, và một dòng in tiếng Việt có dấu **ném `UnicodeEncodeError`** — nuốt
mất verdict thật và phá hợp đồng exit 0/1/2. Console tương tác **không** dính,
nên nó ẩn qua mọi lần thử tay.

**A6. SDK tự thử lại làm hỏng chẩn đoán và đốt hạn mức.** Không tìm thấy
`max_retries` ở `backend/src/` của repo này. Youdoo: client mặc định
`max_retries=6`, nên một lượt hỏng mất **33,4 giây** thay vì 0,4 giây, và ba lớp
thử lại chồng nhau mà lớp SDK là lớp duy nhất không ai nhìn thấy. Với repo local
thì hạn mức không phải vấn đề, nhưng **độ trễ thì có** — xem ADR-008.

### Nhóm B — lớp lỗi về PHÉP ĐO, không phải về tính năng

Đây là nhóm Youdoo trả giá nhiều nhất và có thể áp thẳng vào bộ eval của repo
này. Hãy tự soi bộ eval ở đây theo từng câu hỏi:

- **Bộ đo có đang đo đúng cấu hình mà production chạy không?** Youdoo phát hiện
  ba cổng chấm điểm chạy trên một prompt **không vai nào dùng**.
- **Test có đo gì không?** Nhiều lần Youdoo tìm ra test xanh vì hai nhánh nó so
  sánh đã trở nên **giống hệt nhau**, hoặc vì nó lặp trên **tập rỗng**. Cách
  chống: mọi rào mới phải **thử phá** (gỡ bản sửa ra, xác nhận test đỏ), và mọi
  test dựa vào "hai thứ khác nhau" phải **khẳng định chúng khác nhau**.
- **Fixture có làm bẩn dữ liệu sống không?** Youdoo có một test tích hợp chạy
  `DROP TABLE` trên database **thật** (xoá sổ ngân sách mỗi lượt chạy), và một
  fixture ghi đè tệp đã commit. Cách chữa: schema riêng qua `search_path`.
- **Nhịp gọi eval suy từ đâu?** Youdoo có ba khiếm khuyết chồng nhau: công thức
  chỉ xét `rpm` mà bỏ `tpm`; nhịp suy từ **đầu chuỗi** thay vì model đang ghim
  đo; và `--pace` mặc định `0.0` trong khi dòng trợ giúp nói ngược lại. Hậu quả:
  một lượt đo cho `acc 0,5556` **trông như thật** trong khi 23/54 ca lỗi.
  ⇒ **Luôn đọc số ca LỖI trước khi đọc `acc`.**
- **Danh sách khai báo có ai gác không?** Lớp lỗi tái phát nhiều nhất ở Youdoo:
  một danh sách (tool đã đăng ký, bộ eval, model trong chuỗi) lệch khỏi thực tế
  mà không test nào thấy. Cách chống: đối chiếu **hai chiều**, suy từ nguồn sự
  thật thay vì viết tay.

### Nhóm C — tính năng thật, nhưng phải đo lại trên 8B trước

Xếp theo giá trị tôi ước lượng, **bạn tự đánh giá lại**:

- **Phân quyền theo vai** — Youdoo dựng 4 tài khoản Odoo riêng + **3 tiến trình
  MCP cô lập**, mỗi tiến trình chỉ nắm credential của vai mình. Repo này không
  có gì tương đương (`grep` không thấy role map). Giá trị: bug định tuyến vai
  chỉ gây "sai bộ tool", **không leo thang quyền**. Bài học kèm theo: Youdoo có
  **ba** khuyết điểm chỉ lộ ra ở nghiệm thu sống trong khi 1254 test vẫn xanh.
- **Bàn giao chéo bộ phận + `log_activity` + đóng activity** — vòng
  tạo→đọc→đóng việc.
- **Công cụ mail** (4 điểm kích hoạt: xác nhận đơn, RFQ, báo giá, hoá đơn) — kèm
  hai bẫy Odoo: `auto_delete` **xoá bản ghi khi gửi THÀNH CÔNG** (nên "không
  thấy bản ghi" ≠ "không gửi"), và `ir.rule` trên `mail.template` đặt theo **tên**
  thì làm chết `send_mail`, đặt theo **model** thì chạy.
- **Đa ngôn ngữ Việt–Anh** — phụ thuộc model nặng, 8B có thể không kham.
- **Ký ức người dùng xuyên phiên** — tính năng lớn; Youdoo đo được rằng ký ức
  **KHÔNG** nên vào prompt tổng hợp RAG (mọi loại fact đều không có lợi, một
  loại làm mất 8,3% độ chính xác). Nếu port thì port **kèm kết luận đó**.
- **Ngày hiệu lực văn bản + `commitment_date`/`effective_date` của đơn** — tầng
  schema, không phụ thuộc model, an toàn nếu Odoo bên này có các trường đó.

### Nhóm D — KHÔNG nên port, đã có lý do

- Toàn bộ tầng `backend/src/llm/` của Youdoo (catalog, router đa nhà cung cấp,
  xoay khoá API, dropdown chọn model, gom catalog): **xung đột trực tiếp** với
  ADR-009 `CLOUD_ALLOWED`. Repo này chạy một model local.
- Langfuse, `routing.py` ngữ nghĩa: ADR-010 đã **cố ý** loại chúng khỏi đây.
- Cơ chế write-suggestion bằng marker của Youdoo: cơ chế `interrupt()` +
  `confirmation.py` của repo này **chín hơn** — nó tránh được cả lớp lỗi mà
  Youdoo phải sửa hai vòng. Đây là **điểm mạnh của repo này**, không phải thiếu
  sót.

## 4. Đầu ra mong muốn

Một spec ở `docs/superpowers/specs/YYYY-MM-DD-<chủ-đề>-design.md`, gồm:

1. **Cái gì bạn đã tự xác minh** trong mã của cả hai repo, kèm đường dẫn + số
   dòng. Ghi rõ mục nào trong danh sách trên **sai** khi bạn kiểm lại — đợt 1 đã
   có tiền lệ: giả định "Youdoo đi trước" bị bác ở bốn điểm.
2. **Ba nhóm** (đáng làm ngay / cần đo trước / không nên), mỗi mục kèm giá trị
   kỳ vọng và rủi ro.
3. Với mục cần đo: **đo cái gì, bằng bộ nào, ngưỡng đạt là bao nhiêu** — nêu
   trước khi chạy, không phải sau.
4. **Thứ tự đề nghị** và lý do.

Xong spec thì **dừng lại hỏi** trước khi viết plan hay code.

## 5. Một điều tôi tự nhận

Danh sách mục 3 do một phiên làm việc **ở phía Youdoo** soạn. Nó thiên vị theo
hướng "thứ Youdoo vừa sửa thì đáng port" — đó là thiên kiến của người vừa làm
xong việc. Đợt 1 đã có bốn chỗ giả định sai bị chính việc đọc mã bác bỏ. **Hãy
đối xử với mục 3 như một giả thuyết cần kiểm, và nói thẳng khi nó sai.**
