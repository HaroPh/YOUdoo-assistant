# Odoo AI Agent (native) — nghiên cứu & đối chiếu với Youdoo

> **Ngày**: 2026-09-10
> **Câu hỏi gốc của chủ dự án**: Odoo đã có AI agent từ lâu — có nên đi tiếp
> project này không, hay chuyển sang model local, hay đổi sang ERP khác
> (SAP, ERPNext…) chưa có AI agent?
>
> **Nguồn phần B/C/D**: chủ dự án tổng hợp bằng NotebookLM từ playlist video
> Odoo AI + tài liệu chính thức Odoo 19.0. Giữ **nguyên văn**, không sửa.
>
> **Phần A là phần đo của tôi (Claude)** trên chính hạ tầng Youdoo ngày
> 2026-09-10 — vì phần B/C/D có vài chỗ **gán cho Youdoo năng lực Youdoo chưa
> có**, không đối chiếu thì sẽ ra quyết định sai.

---

## A. Đối chiếu với hiện trạng THẬT (đo 2026-09-10)

### A.1. Đính chính một khẳng định sai tôi đã nêu trước đó

Trong lượt trả lời đầu, tôi nói AI Agent của Odoo là tính năng của **Odoo 20**,
"chưa có, dự kiến 10-11/2026". **Sai.** Tôi rút kết luận đó từ một lượt web
search về roadmap Odoo 20, không kiểm chứng. Thực tế theo cả tài liệu chính
thức lẫn instance đang chạy: **AI Agent đã phát hành từ Odoo 19.0**. Sai lệch
này quan trọng vì nó biến "chuyện tương lai" thành "chuyện hiện tại".

### A.2. Đo trên chính instance Odoo mà Youdoo đang nói chuyện

`ODOO_URL` = `host.docker.internal:8069` (Odoo nằm ngoài compose của Youdoo).

| Phép đo | Kết quả |
|---|---|
| `POST /web/webclient/version_info` | `server_version` = `19.0-20260512` |
| `server_version_info` | `[19, 0, 0, 'final', 0, '']` — phần tử cuối **rỗng** ⇒ **Community** (Enterprise trả `'e'`) |
| `ir.module.module` where name like `ai` | **KHÔNG có** module nào tên `ai` hoặc `ai_*` trong danh mục |
| `ir.model` where model like `ai.` | **KHÔNG có** model `ai.*` nào ⇒ `ai.agent` không tồn tại |
| `ir.module.module` where `to_buy = True` | 21 — dấu hiệu Community đang hiển thị app Enterprise dạng "mua thêm" |

**Kết luận A.2 — dữ kiện quyết định nhất của cả nghiên cứu này:**

Toàn bộ năng lực mô tả ở phần B/C/D (`Ask AI`, `AI Fields`, `AI Live Chat`,
`AI Server Actions`, RAG native, `ai.agent`) **không dùng được** trên
deployment hiện tại. Không phải "chưa cài" — app AI **không có trong danh mục
addons của Community**. Muốn có, phải trả tiền: mua Odoo Enterprise
(tính theo user/tháng) hoặc chuyển lên Odoo Online.

Nghĩa là mệnh đề *"Odoo đã có AI agent rồi nên project này thừa"* **không đúng
với hoàn cảnh hiện tại của bạn**. Nó chỉ đúng nếu (và khi nào) bạn quyết định
mua Enterprise.

### A.3. Ba chỗ báo cáo cho Youdoo điểm mà Youdoo CHƯA có

Phần D (báo cáo quyết định) liệt kê các ưu điểm của "Phương án A — tiếp tục tự
xây". Ba trong số đó là **tiềm năng, không phải hiện trạng**:

| Báo cáo D nói | Hiện trạng Youdoo (đo được) |
|---|---|
| "Tự quản lý phân quyền RAG chi tiết theo cấp tài liệu/người dùng" | **CHƯA CÓ.** `rag_chunks.visibility` tồn tại trong `src/rag/schema.sql:30` nhưng **không ai đọc, không ai ghi**; toàn bộ chunk đều `'all'`. Mục 19b `trang-thai-chung.md` = **hoãn có điều kiện**, lỗ hổng còn nguyên. Đo sống: vai `warehouse` hỏi "chính sách chiết khấu" ⇒ nhận đủ bậc 5%/10%, cộng 2%, trần 15%. ⇒ Youdoo đang mắc **đúng cùng lỗ hổng** mà báo cáo tính là điểm yếu của Odoo. |
| "Chạy Local LLM để bảo mật hoàn toàn dữ liệu On-Premise" | **CHƯA CÓ.** `backend/src/llm/catalog.py` chỉ có `provider: google \| groq \| openrouter` — 4 model đều là API bên thứ 3. Ollama chỉ phục vụ **embedding** (`bge-m3`) và **reranker**. Sinh câu trả lời hiện **100% đi ra API ngoài**. |
| "Tránh nguy cơ dữ liệu nhạy cảm gửi sang API bên ngoài / tuân thủ GDPR" | Hệ quả của dòng trên: **không đúng hôm nay**. |

Điểm thứ tư trong báo cáo D — "Odoo không hỗ trợ MCP" — là **đúng nhưng không
liên quan**: Youdoo tự chạy MCP server riêng nói chuyện với Odoo qua XML-RPC,
không cần Odoo cung cấp MCP server.

### A.4. Chỗ Youdoo thật sự khác biệt (đối chiếu theo khung 5 tầng ở phần C)

Đây mới là phần đứng vững, và nó nằm **đúng vào hai tầng phần C chấm Odoo là
"thấp/đóng hộp"**:

| Tầng | Odoo native (theo phần C) | Youdoo (đo được) |
|---|---|---|
| **L4 Control & Security** | "Thấp/Giới hạn": 1 agent, tệp nguồn RAG **dùng chung, không áp record rule**; log ước tính token | **3 tiến trình MCP tách biệt theo vai** (8003/8004/8005) + **4 tài khoản Odoo AI riêng**; vệt kiểm toán `mcp_call_log` có **chuỗi hash** (`http_user` + `args_digest` + `args_keys` nằm trong hash, sửa là verify báo đứt) |
| **L5 Observability & Eval** | "Rất thấp / Đóng hộp": không có dashboard, không có bộ eval | Langfuse tracing (đã nối trace định tuyến về cùng trace hội thoại) + nhiều bộ eval có số đo: retrieval (recall@20), synthesis qua retrieval thật, `citation_acc` tất định |
| **L1 tiếng Việt** | Không có bằng chứng nào về tiếng Việt trong nguồn (chỉ có demo dịch tiếng Trung + việc Odoo hỗ trợ locale `VI`) | Chân bỏ dấu (migration 008): truy vấn không dấu **0,0156 → 0,6042** |

Ngược lại, chỗ Odoo native **thắng rõ** là các điểm chạm UI ngay trong Odoo
(`Ctrl+K`, nút AI trên form, AI Fields, Chatter) — thứ Youdoo không có và cũng
không nên đua, vì Youdoo đi qua Open WebUI.

### A.5. Khuyến nghị

**Đi tiếp** — nhưng vì lý do khác hẳn lý do tôi nêu lượt trước:

1. **Không có gì để "bị thay thế" hôm nay.** Odoo 19 Community không có app AI.
   So sánh Youdoo với Odoo AI Agent lúc này là so với thứ chưa tồn tại trên hạ
   tầng của bạn.
2. **Giá trị của Youdoo tập trung đúng vào 2 tầng Odoo đóng hộp** (L4 phân
   quyền/kiểm toán theo vai, L5 quan sát & đánh giá) cộng tiếng Việt. Kể cả khi
   sau này mua Enterprise, hai tầng đó vẫn không mua được.
3. **Đừng đổi ERP.** Lập luận "đổi sang SAP/ERPNext vì Odoo đã có AI" tự mâu
   thuẫn: SAP có Joule, ERPNext/Frappe cũng đang làm AI. Đổi ERP là vứt toàn bộ
   33 tool MCP + 4 tài khoản vai + vệt kiểm toán đang chạy, đổi lấy một tiền đề
   sai.
4. **"Chuyển sang model local" là trục riêng, và hiện là món nợ chứ không phải
   lợi thế.** Báo cáo D tính nó là ưu điểm sẵn có của Youdoo — không đúng.
   Nếu muốn biến nó thành lợi thế thật thì đó là một hạng mục phải làm, và cần
   cân với dữ kiện đã đo: RTX 5060 Ti 8GB **không đủ** cho model sinh đáng tin
   (xem `reference_youdoo_compute_and_model_capability`).
5. **Hai món nợ nên ưu tiên lại**, vì nghiên cứu này cho thấy chúng chính là
   phần khác biệt của sản phẩm: (a) mục 19b RBAC tầng RAG — hiện Youdoo và
   Odoo hở như nhau, đóng được thì Youdoo hơn hẳn; (b) giữ bộ eval/quan sát
   tiếp tục chạy, vì đó là thứ Odoo native không có.

### A.6. Nếu hỏi NotebookLM tiếp, ưu tiên 3 câu này

Danh sách "thiếu dữ liệu" ở phần D §III đã tốt. Ba câu sau **quyết định trực
tiếp** hơn cả, xếp trên đầu:

1. App AI của Odoo 19 có chạy trên **Community** không, hay bắt buộc
   **Enterprise**? (Đo trên máy cho thấy Community **không có** module `ai*` —
   cần tài liệu chính thức xác nhận đây là ranh giới license, không phải thiếu
   addons path.)
2. Nếu bắt buộc Enterprise: **giá per-user/tháng**, và AI có **tính phí thêm**
   ngoài giá Enterprise không? Hạn ngạch token đi kèm là bao nhiêu?
3. `Restrict to Sources` có kèm **phân quyền theo nhóm người dùng** cho tệp
   nguồn RAG không, hay chỉ giới hạn phạm vi trả lời? Có lộ trình vá lỗ hổng
   "ai truy cập agent cũng đọc được toàn bộ nguồn" không?

---

## B. Báo cáo 1 (NotebookLM) — Năng lực và kiến trúc Odoo AI Agent (Odoo 19.0)

Dưới đây là báo cáo phân tích kỹ thuật chuyên sâu về **Odoo AI Agent** được tổng hợp và hệ thống hóa strictly từ các nguồn tài liệu chính thức của Odoo 19.0 và danh sách phát video hướng dẫn Odoo AI.

### 1. Danh sách tính năng AI Agent cụ thể được đề cập

Các tính năng AI Agent được tích hợp sâu vào hệ thống Odoo để vừa hỗ trợ tương tác hội thoại, vừa thực thi tác vụ trực tiếp trên cơ sở dữ liệu:

| Tên tính năng | Mô tả chi tiết năng lực | Nguồn trích dẫn |
| :--- | :--- | :--- |
| **Ask AI Agent (Hỏi AI toàn hệ thống)** | Trợ lý thông minh mặc định truy cập qua phím tắt (`Ctrl + K`) hoặc nút AI góc màn hình. Hiểu ngôn ngữ tự nhiên, tìm kiếm bản ghi, mở giao diện (View), hiển thị biểu đồ/báo cáo pivot mà không làm thay đổi dữ liệu DB. | tài liệu *"AI — Odoo 19.0 documentation"*, video *"Odoo AI: Setup your own agents & RAG"* |
| **AI Live Chat Agent** | Agent hội thoại trực tuyến 24/7 trên Website/Portal, tra cứu tri thức RAG để giải đáp câu hỏi mở, thu thập thông tin khách hàng và tự động chuyển giao (escalate) cho nhân viên. | video *"AI Live Chat \| Odoo AI"*, tài liệu *"AI live chat — Odoo 19.0 documentation"* |
| **Custom AI Agents & RAG Setup** | Khả năng đóng gói các Agent tùy chỉnh theo vai trò chuyên biệt (như Odoo Compliance Assistant, Sales Advisor) gắn liền với tập tài liệu RAG riêng. | video *"Odoo AI: Build custom agents to streamline your operations."*, tài liệu *"AI agents — Odoo 19.0 documentation"* |
| **Create Leads Topic** | Topic xử lý tự động phân tích ngữ cảnh hội thoại chat để trích xuất tên, email, số điện thoại và tạo bản ghi Lead trong CRM. | video *"AI Agents \| Odoo AI"*, tài liệu *"AI agents — Odoo 19.0 documentation"* |
| **AI Server Actions / Automations** | Tự động hóa sự kiện nghiệp vụ (On Create / On Edit / State Change) để AI phân loại Ticket Helpdesk, gán công việc theo kỹ năng, phân loại chi phí kế toán, chuyển stage tuyển dụng. | video *"AI Helpdesk Ticket Routing \| Odoo AI"*, video *"Developing Odoo modules using AI: a practical guide"*, tài liệu *"AI in support workflows — Odoo 19.0 documentation"* |
| **AI Fields (Trường dữ liệu AI)** | Trường thông minh trên Form (thêm qua Studio) tự động điền/tính toán giá trị (tóm tắt, đánh giá Vibe/Sentiment, xếp hạng nhà cung cấp, đề xuất giá) qua prompt và dữ liệu bản ghi. | video *"Discover the new Odoo AI features"*, video *"Vibe Check CRM Leads using AI \| Odoo AI"*, tài liệu *"AI fields — Odoo 19.0 documentation"* |
| **AI Voice Transcription & Summarization** | Chuyển đổi giọng nói các cuộc gọi/cuộc họp thành văn bản (transcript) và tự động tóm tắt trích xuất thông tin hành động. | tài liệu *"AI voice transcription — Odoo 19.0 documentation"*, video *"Odoo and AI: A New Business Era"* |
| **AI Document Sorting & Processing** | Đọc, số hóa và tự động phân loại tài liệu/chứng từ (hóa đơn, hợp đồng) vào đúng thư mục hoặc tạo chứng từ kế toán tự động. | video *"Odoo AI: Process documents faster"*, video *"AI Document Sorting \| Odoo AI"* |
| **AI Email Templates** | Tích hợp prompt trực tiếp vào mẫu Email để hệ thống tự động sinh nội dung cá nhân hóa theo từng đối tượng trước khi gửi. | tài liệu *"AI in email templates — Odoo 19.0 documentation"* |
| **AI Website Copy & Import Tool** | Tự động biên tập/viết lại văn bản website chuẩn SEO và công cụ tái cấu trúc/import toàn bộ website từ nền tảng cũ sang Odoo. | video *"Website Copy Integration \| Odoo AI"*, video *"Website import tool: How AI can rebuild your website"* |

### 2. Kiến trúc kỹ thuật (Technical Architecture)

* **Vị trí thực thi**: AI Agent được tích hợp trực tiếp bên trong lõi hệ thống Odoo ("built directly into Odoo"), vận hành như một thành phần thuộc mô hình dữ liệu `ai.agent` [Nguồn: video *"AI Agents | Odoo AI"*, video *"Developing Odoo modules using AI: a practical guide"*].
* **Mô hình AI nền tảng (LLM Models)**: Odoo **không tự huấn luyện mô hình riêng** ("Odoo isn't training models. We are just consumers"). Hệ thống đóng vai trò kết nối và tích hợp các LLM thương mại hàng đầu thông qua API, hỗ trợ chính thức hai nhà cung cấp:
  1. **OpenAI** (ChatGPT, bao gồm các dòng model GPT-4, GPT-5) [Nguồn: tài liệu *"AI API keys — Odoo 19.0 documentation"*, video *"Developing Odoo modules using AI: a practical guide"*].
  2. **Google Gemini** [Nguồn: tài liệu *"AI API keys — Odoo 19.0 documentation"*, video *"Discover the new Odoo AI features"*].
* **Môi trường triển khai (Cloud vs On-Premise / Self-Host)**:
  * Hỗ trợ linh hoạt trên cả **Odoo Online (SaaS)**, **Odoo.sh** và **On-Premise (Self-host)** [Nguồn: tài liệu *"AI API keys — Odoo 19.0 documentation"*].
  * **Yêu cầu API Key**: Người dùng **Odoo Online** có thể sử dụng hạ tầng khóa API mặc định do Odoo quản lý (miễn phí) hoặc tự nhập khóa riêng. Người dùng triển khai **Odoo.sh** hoặc **On-Premise / Self-host** bắt buộc phải tự cấu hình API Key cá nhân từ OpenAI hoặc Google Gemini [Nguồn: tài liệu *"AI API keys — Odoo 19.0 documentation"*, video *"Odoo AI: Build custom agents to streamline your operations."*].
  * **Cơ sở dữ liệu Vector cho Self-Host**: Để vận hành RAG trên môi trường On-Premise, máy chủ cơ sở dữ liệu PostgreSQL cục bộ cần được cài đặt tiện ích mở rộng **PGVector** để lưu trữ các chuỗi Embedding [Nguồn: video *"Developing Odoo modules using AI: a practical guide"*].

### 3. Phạm vi dữ liệu & Quyền hạn (Data Scope & Permissions)

* **Phạm vi đọc/ghi Module**: AI Agent có khả năng tương tác rộng khắp trên tất cả các module nghiệp vụ của Odoo như CRM, Bán hàng, Helpdesk, Kế toán, Kho bãi, Tuyển dụng, Nhân sự (Timesheet), Quản lý tài liệu (Documents), Knowledge, Website,... thông qua danh sách các Topics, Tools và AI Fields được cấp phép [Nguồn: tài liệu *"AI agents — Odoo 19.0 documentation"*, video *"Discover the new Odoo AI features"*].
* **Tôn trọng phân quyền Odoo (`ir.rule` / Record Rules & Access Rights)**:
  * **CÓ**. Các tác vụ truy vấn dữ liệu tự động (như `Information Retrieval` hoặc `Natural Language Search`) vận hành hoàn toàn dưới danh tính và quyền hạn của người dùng đang đăng nhập [Nguồn: video *"Discover the new Odoo AI features"*, video *"Odoo AI: Build custom agents to streamline your operations."*].
  * Ví dụ: Khi người dùng Portal thực hiện truy vấn, Agent chỉ tìm thấy và trả về thông tin các đơn hàng thuộc sở hữu của chính người dùng đó theo đúng quy tắc Record Rule (`ir.rule`) của Odoo [Nguồn: video *"Discover the new Odoo AI features"*].
* **Nhật ký theo dõi & Audit Trail**:
  * Hệ thống Odoo có lưu trữ nhật ký thực thi (logs) đối với các lệnh gọi công cụ (tool calls), bao gồm thời gian phản hồi và ước tính lượng Token tiêu thụ [Nguồn: video *"Developing Odoo modules using AI: a practical guide"*].
  * Đối với các hành động ghi/sửa dữ liệu thông qua Server Actions hoặc Chatter, người dùng có thể cấu hình bước kiểm duyệt hoặc ghi chú vết hoạt động trực tiếp vào Chatter để kiểm soát [Nguồn: tài liệu *"AI — Odoo 19.0 documentation"*, video *"Developing Odoo modules using AI: a practical guide"*].

### 4. Khả năng tuỳ biến (Customization Capabilities)

Odoo cung cấp khả năng tùy biến AI linh hoạt và sâu rộng cho từng khách hàng mà không bị giới hạn ở các tính năng đóng gói sẵn:

* **Tạo Custom Agent & Cấu hình Prompt**:
  * Cho phép tạo không giới hạn các **Custom AI Agents** mới trong ứng dụng AI [Nguồn: tài liệu *"AI agents — Odoo 19.0 documentation"*, video *"Odoo AI: Build custom agents to streamline your operations."*].
  * Cho phép tùy biến toàn bộ **System Prompt** (xác định định danh, vai trò, quy tắc ứng xử), **Topic Instructions** (hướng dẫn cụ thể theo ngữ cảnh) và **Default Prompts** (nút bấm và gợi ý câu lệnh xuất hiện theo từng Model/View) [Nguồn: tài liệu *"AI default prompts — Odoo 19.0 documentation"*, tài liệu *"AI agents — Odoo 19.0 documentation"*].
* **Custom Tools & Custom Business Logic**:
  * Người dùng và lập trình viên có thể bổ sung các **Tool tùy chỉnh** cho Agent bằng cách kết nối với các **Server Actions** (viết mã Python hoặc cấu hình qua Odoo Studio) [Nguồn: video *"AI Helpdesk Ticket Routing | Odoo AI"*, video *"Developing Odoo modules using AI: a practical guide"*, video *"Odoo AI: Build custom agents to streamline your operations."*].
  * Hỗ trợ định nghĩa cấu trúc đầu ra bằng **JSON Schema** để ép AI trả về dữ liệu đúng định dạng mong muốn cho logic phần mềm xử lý [Nguồn: video *"Developing Odoo modules using AI: a practical guide"*].
* **Custom RAG & Nguồn tri thức**:
  * Cho phép tải lên các tệp tin đính kèm (PDF, PPT, TXT), đường dẫn URL (hệ thống tự động crawl dữ liệu), tài liệu từ app Documents và các bài viết từ app Knowledge [Nguồn: tài liệu *"AI agents — Odoo 19.0 documentation"*, video *"AI Agents | Odoo AI"*, video *"Odoo AI: Setup your own agents & RAG"*].
  * Tính năng tùy chọn **`Restrict to Sources`**: Khi kích hoạt, Agent bắt buộc chỉ được sử dụng tri thức từ các nguồn đính kèm để trả lời, loại bỏ hoàn toàn việc suy diễn tự do từ mô hình bên ngoài [Nguồn: tài liệu *"AI agents — Odoo 19.0 documentation"*, video *"Odoo AI: Build custom agents to streamline your operations."*].

### 5. Ngôn ngữ & Thị trường (Language & Market Support)

* **Hỗ trợ Tiếng Việt**: Hệ thống tài liệu chính thức Odoo 19.0 công nhận hỗ trợ ngôn ngữ tiếng Việt (mã ngôn ngữ `VI`) trong danh mục ngôn ngữ ứng dụng và giao diện [Nguồn: tài liệu *"AI API keys — Odoo 19.0 documentation"*, tài liệu *"AI agents — Odoo 19.0 documentation"*].
* **Ví dụ thực tế ngoài tiếng Anh**:
  * Trong video *"Odoo AI: Automate your administrative tasks"*, diễn giả minh họa thực tế trường hợp Lead gửi từ Website bằng **Tiếng Trung Quốc (Chinese)**; người dùng chỉ cần yêu cầu AI tự động dịch trực tiếp nội dung sang tiếng Anh ngay trong Chatter mà không cần dùng công cụ bên ngoài [Nguồn: video *"Odoo AI: Automate your administrative tasks"*].
  * Do bản chất các mô hình LLM tích hợp (OpenAI/Gemini) là đa ngôn ngữ, người dùng có thể nhập prompt và giao tiếp với Agent bằng bất kỳ ngôn ngữ nào (bao gồm tiếng Việt) [Nguồn: video *"Odoo AI: Setup your own agents & RAG"*].

### 6. Giá & Giấy phép (Pricing, Licensing & Release)

* **Chi phí sử dụng**:
  * **Odoo Online (SaaS)**: Tính năng AI được cung cấp sẵn trong gói đăng ký Odoo SaaS (sử dụng API Key mặc định của Odoo không tốn thêm phí) [Nguồn: video *"Developing Odoo modules using AI: a practical guide"*, video *"Odoo AI: Build custom agents to streamline your operations."*].
  * **Odoo.sh & On-Premise**: Người dùng trả phí tiêu thụ Token trực tiếp cho nhà cung cấp AI (OpenAI hoặc Google) theo bảng giá API của các nhà cung cấp đó [Nguồn: tài liệu *"AI API keys — Odoo 19.0 documentation"*, video *"Developing Odoo modules using AI: a practical guide"*].
* **Phân hạng gói Odoo (Community vs Enterprise)**:
  * Hầu hết các công cụ cấu hình nâng cao như **AI App**, **Studio AI Fields**, **AI Server Actions**, **Website Import Tool** thuộc bản quyền **Odoo Enterprise** và yêu cầu cài đặt ứng dụng Studio [Nguồn: tài liệu *"AI fields — Odoo 19.0 documentation"*, video *"Website import tool: How AI can rebuild your website"*].
* **Timeline phát hành chính thức**: Các tính năng AI Agent được công bố và phát hành chính thức bắt đầu từ phiên bản **Odoo 19.0** (và các bản SaaS cập nhật liên quan) [Nguồn: tài liệu *"AI — Odoo 19.0 documentation"*, video *"Discover the new Odoo AI features"*, video *"Developing Odoo modules using AI: a practical guide"*].

### 7. Giới hạn / Nhược điểm được Odoo thừa nhận

Trong các buổi trình bày kỹ thuật và tài liệu, các chuyên gia R&D của Odoo đã chỉ ra các giới hạn và lưu ý kỹ thuật sau:

1. **Tính xác suất & Rủi ro sai lệch (Probabilistic Nature & Hallucinations)**:
   * AI mang tính xác suất, có thể trả về kết quả không đồng nhất hoặc khó dự đoán trước. Odoo nhấn mạnh "không bao giờ tin tưởng AI tuyệt đối" mà luôn cần thiết lập một lớp xác minh từ con người (Human-in-the-loop) đối với các tác vụ quan trọng [Nguồn: video *"Developing Odoo modules using AI: a practical guide"*, video *"Odoo AI: Setup your own agents & RAG"*].
2. **Hạn chế về khả năng tính toán số học phức tạp**:
   * Bản chất các LLM không tự thực hiện các phép tính số học phức tạp một cách chính xác tuyệt đối mà chủ yếu tuân theo hướng dẫn văn bản và ngữ cảnh [Nguồn: video *"Target-Margin Auto Pricing | Odoo AI"*].
3. **AI có thể bỏ qua Tool hoặc JSON Schema**:
   * Tùy thuộc vào dòng mô hình (OpenAI vs Gemini) và cách viết prompt, AI đôi khi không tuân thủ hoàn toàn JSON Schema được cung cấp hoặc tự ý thực thi Tool theo thứ tự tuần tự thay vì thực thi hàng loạt (batching execution) gây tốn thời gian gọi API [Nguồn: video *"Developing Odoo modules using AI: a practical guide"*].
4. **Thời gian phản hồi & Độ trễ**:
   * Quá trình đọc, trích xuất văn bản và xử lý nhiều tệp tài liệu cùng lúc qua API bên ngoài có thể gây ra độ trễ (mất vài giây đến vài chục giây) [Nguồn: video *"Odoo AI: Process documents faster"*, video *"Odoo AI: Setup your own agents & RAG"*].
5. **Chưa hỗ trợ Agent-to-Agent Interaction**:
   * Hiện tại các AI Agent trong Odoo chưa thể tự động giao tiếp hoặc phối hợp trực tiếp với nhau (Agent tương tác với Agent) [Nguồn: video *"Developing Odoo modules using AI: a practical guide"*].
6. **Yêu cầu Re-index khi cập nhật tri thức RAG**:
   * Khi tài liệu nguồn (như bài viết Knowledge) bị thay đổi nội dung, hệ thống không tự động cập nhật ngay lập tức mà cần người dùng thực hiện re-index lại để RAG ghi nhận dữ liệu mới [Nguồn: video *"Discover the new Odoo AI features"*].
7. **Rủi ro an toàn dữ liệu từ nguồn tĩnh (RAG Data Security)**:
   * Mặc dù AI tuân thủ phân quyền người dùng khi tìm kiếm dữ liệu động (Search Tools), nhưng đối với các tệp nguồn tĩnh (Sources) đính kèm trực tiếp vào Agent, bất kỳ ai có quyền tương tác với Agent đó đều có thể truy xuất thông tin từ tệp nguồn. Odoo cảnh báo người dùng không được đính kèm các tài liệu chứa thông tin quá nhạy cảm vào Agent dùng chung [Nguồn: video *"Odoo AI: Build custom agents to streamline your operations."*].

---

## C. Báo cáo 2 (NotebookLM) — Đối chiếu với khung kiến trúc 5 tầng

Dưới đây là bảng đối chiếu kiến trúc **Odoo AI Agent (native)** với **Khung kiến trúc AI Chatbot Chuẩn Doanh Nghiệp 5 tầng**, được tổng hợp và trích dẫn strictly từ các nguồn tài liệu chính thức Odoo 19.0 và danh sách phát video Odoo AI.

### BẢNG ĐỐI CHIẾU KIẾN TRÚC ODOO AI AGENT

| Tầng kiến trúc | Odoo AI Agent (native) làm được gì ở tầng này (theo nguồn) | Mức độ tuỳ biến cho bên thứ 3 | Ghi chú/giới hạn |
| :--- | :--- | :--- | :--- |
| **1. Data & Knowledge Plane** | • Hỗ trợ kiến trúc RAG (Retrieval-Augmented Generation).<br>• Nạp tài liệu từ nhiều định dạng: tệp đính kèm (PDF, PPT, TXT), đường dẫn URL (tự động crawl), tệp từ ứng dụng Documents, bài viết từ ứng dụng Knowledge.<br>• Chạy background cron job để tự động chunking, tạo vector embedding và lưu trữ vào DB (dùng `PGVector` khi cài đặt On-Premise).<br>• Sử dụng checksum hashing để tránh tạo lại embedding trùng lặp. Trích xuất top 5 chunks tương tự nhất để làm ngữ cảnh cho LLM. | **Cao**:<br>• Cho phép tạo không giới hạn Custom Agents và quản lý/thêm bớt tệp nguồn (Sources).<br>• Cho phép bật tính năng `Restrict to Sources` để ép AI chỉ trả lời từ tài liệu đính kèm. | • Chưa hỗ trợ tự động đồng bộ thời gian thực khi bài viết Knowledge hoặc tệp trong thư mục thay đổi (cần re-index thủ công).<br>• Định dạng CSV chưa được hỗ trợ làm nguồn RAG trong bản hiện tại (đang được phát triển). |
| **2. Inference Plane** | • Tích hợp và gọi API trực tiếp đến các mô hình LLM thương mại bên ngoài: OpenAI (ChatGPT, GPT-4, GPT-5) và Google Gemini.<br>• Odoo đóng vai trò kết nối, không tự huấn luyện hay fine-tune mô hình riêng. | **Trung bình**:<br>• Cho phép chọn nhà cung cấp (OpenAI / Gemini) và phiên bản Model trong giao diện cấu hình Agent.<br>• Trên Odoo.sh / On-Premise bắt buộc tự nhập API Key cá nhân; trên Odoo Online có thể dùng key miễn phí của Odoo hoặc tự nhập key riêng. | • Không hỗ trợ tích hợp mô hình mã nguồn mở (Open-source LLMs) hoặc các nhà cung cấp khác ngoài OpenAI và Gemini.<br>• Không hỗ trợ Fine-tuning mô hình.<br>• Chưa hỗ trợ cơ chế caching cho nội dung tĩnh. |
| **3. Agentic Brain & Orchestration** | • Cấu trúc Agent gồm System Prompt, Topics (với Instructions riêng) và Tools.<br>• Cung cấp các Topics mặc định: Natural Language Search, Information Retrieval, Create Leads.<br>• Kích hoạt qua Ask AI, AI Fields, AI Live Chat, AI Server Actions.<br>• Vận hành vòng lặp xử lý `requestLLM` trên server để thực thi các tool call do LLM yêu cầu. | **Cao**:<br>• Cho phép tạo Custom Agents không giới hạn.<br>• Cho phép tùy biến System Prompt, Topic Instructions và Default Prompts.<br>• Tùy biến Tools bằng cách liên kết với Python Server Actions, quy định tham số qua JSON Schema hoặc định dạng bảng HTML. | • Chưa hỗ trợ tương tác đa đại lý (Agent-to-Agent interaction).<br>• AI đôi khi không tuân thủ hoàn toàn JSON Schema hoặc bỏ qua tool calls.<br>• Các tool calls được xử lý tuần tự từng tác vụ một, chưa hỗ trợ xử lý hàng loạt (batching). |
| **4. Control Plane & Security** | • Tích hợp hệ thống phân quyền mặc định của Odoo — các công cụ truy vấn/tìm kiếm tự động vận hành dưới danh tính và quyền hạn của người dùng đang đăng nhập (áp dụng Record Rules `ir.rule` và Access Rights). | **Thấp / Giới hạn**:<br>• Cho phép bật `Restrict to Sources` để giới hạn phạm vi trả lời của Agent.<br>• Phụ thuộc hoàn toàn vào cấu hình phân quyền tiêu chuẩn Odoo. | • Tệp nguồn (Sources) đính kèm trực tiếp vào Agent **không áp dụng Record Rule theo từng người dùng** — bất kỳ ai có quyền tương tác với Agent đó đều truy cập được tri thức từ tệp đính kèm (Odoo cảnh báo không đính kèm dữ liệu nhạy cảm).<br>• Dữ liệu người dùng/khách hàng khi tương tác bắt buộc gửi sang API bên ngoài (OpenAI/Gemini) gây ra rủi ro tuân thủ GDPR. |
| **5. Observability & Evaluation Plane** | • Hệ thống Odoo ghi log nội bộ cho các lượt gọi tool call, bao gồm thời gian thực thi và ước tính lượng Token tiêu thụ.<br>• Ghi vết hoạt động tự động vào Chatter đối với Server Actions. | **Rất thấp / Đóng hộp**:<br>• Người dùng/Bên thứ 3 không có công cụ tùy biến dashboard giám sát hay thiết lập tiêu chí đánh giá (evaluation metrics) riêng. | • Báo cáo token tiêu thụ chỉ ở dạng ước tính (estimates).<br>• Không có công cụ hay bộ framework đánh giá tự động (Auto-evaluation / Benchmark suite) tích hợp sẵn. |

### NHẬN XÉT ĐÁNH GIÁ TỔNG QUAN

1. **Các tầng Odoo AI phủ tốt & cho phép tùy biến linh hoạt**:
   * **Tầng 1 (Data & Knowledge Plane)** và **Tầng 3 (Agentic Brain & Orchestration)** là hai tầng Odoo làm tốt nhất. Bên thứ 3 có thể dễ dàng mở rộng tri thức RAG (nạp PDF, URLs, Knowledge) và tùy biến linh hoạt tư duy/hành động của Agent thông qua System Prompt, Topic Instructions và việc gắn **Python Server Actions** làm Custom Tools.

2. **Các tầng bị đóng hộp hoặc hạn chế tùy biến**:
   * **Tầng 2 (Inference Plane)**: Rất đóng hộp khi Odoo chỉ mở cổng kết nối với hai nhà cung cấp thương mại cố định (OpenAI & Gemini), hoàn toàn không cho phép tích hợp các mô hình Open-Source self-host khác hay thực hiện Fine-tuning.
   * **Tầng 4 (Control Plane & Security)**: Mặc dù thừa hưởng cơ chế `ir.rule` cho các tác vụ truy vấn dữ liệu Odoo, nhưng đối với các tài liệu RAG đính kèm lại xuất hiện lỗ hổng phân quyền (không áp dụng theo nhóm người dùng), đồng thời bắt buộc gửi dữ liệu ra API bên ngoài.
   * **Tầng 5 (Observability & Evaluation Plane)**: Đóng hộp hoàn toàn. Nguồn tài liệu xác nhận không có tài liệu hướng dẫn chuyên sâu hay công cụ tích hợp sẵn cho việc tuỳ biến đánh giá chất lượng phản hồi AI, benchmark hay dashboard giám sát nâng cao ngoài các nhật ký log cơ bản của Odoo.

---

## D. Báo cáo 3 (NotebookLM) — Báo cáo quyết định build vs buy

### BÁO CÁO PHÂN TÍCH QUYẾT ĐỊNH: LỰA CHỌN KIẾN TRÚC AI CHATBOT CHO DOANH NGHIỆP

#### I. BỐI CẢNH VÀ MỤC TIÊU

Đội ngũ kỹ thuật hiện đang tự phát triển hệ thống AI Chatbot tùy biến với các năng lực: RAG, phân quyền theo vai trò (RBAC), tích hợp Odoo qua công cụ MCP (Model Context Protocol), hỗ trợ tiếng Việt, và linh hoạt chạy cả LLM cục bộ (Local) lẫn API thương mại.

Báo cáo này phân tích khách quan trade-off của **3 phương án kiến trúc** dựa trên sự so sánh với năng lực thực tế của **Odoo AI Agent (Native trong Odoo 19.0)** được xác nhận từ các nguồn tài liệu chính thức.

#### II. PHÂN TÍCH TRADE-OFF THEO 3 PHƯƠNG ÁN

##### 1. Phương án A: Tiếp tục tự xây và duy trì hệ thống hiện tại

* **Ưu điểm (Pros)**:
  * **Linh hoạt lựa chọn Model**: Cho phép sử dụng các mô hình mã nguồn mở (Open-source LLMs) chạy Local để bảo mật hoàn toàn dữ liệu On-Premise. Ngược lại, Odoo AI Agent native không hỗ trợ Local LLM do chỉ tích hợp cố định OpenAI và Google Gemini.
  * **Kiểm soát Bảo mật & Tùy biến RAG**: Tự quản lý phân quyền RAG chi tiết theo cấp tài liệu/người dùng. Với Odoo AI Agent native, các tệp nguồn RAG đính kèm hiện không áp dụng Record Rules theo từng người dùng (bất kỳ ai có quyền tương tác với Agent đều truy cập được nguồn RAG đó).
  * **Tuân thủ GDPR & Bảo mật dữ liệu**: Tránh nguy cơ dữ liệu doanh nghiệp nhạy cảm bị tự động gửi sang API bên ngoài của bên thứ ba.
  * **Khả năng mở rộng giao thức kết nối**: Tự do phát triển các giao thức mở như MCP (Model Context Protocol) hoặc phối hợp đa đại lý (Agent-to-Agent interaction).

* **Rủi ro (Risks)**:
  * **Chi phí vận hành & Tốn nguồn lực**: Phải tự gánh vác hạ tầng RAG, cơ sở dữ liệu Vector, pipeline đồng bộ dữ liệu và bảo trì các MCP tools kết nối với Odoo.
  * **Rủi ro gãy kết nối khi Odoo nâng cấp**: Khi Odoo thay đổi cấu trúc ORM hoặc API nội bộ, các tool MCP tự xây có thể bị lỗi, đòi hỏi chi phí bảo trì (refactor) liên tục.
  * **Bỏ lỡ trải nghiệm người dùng native**: Không tận dụng được các điểm chạm giao diện tích hợp sâu sẵn có trên Odoo UI như phím tắt `Ask AI`, nút bấm AI trên Form view, AI Fields hay AI Live Chat.

##### 2. Phương án B: Chuyển sang dùng hoàn toàn AI Agent native của Odoo

* **Ưu điểm (Pros)**:
  * **Tích hợp sâu sẵn có trong UI/UX**: AI Agent vận hành trực tiếp trong hệ sinh thái Odoo qua Ask AI, Chatter, AI Fields, AI Live Chat và AI Server Actions mà không cần thiết lập giao diện hay middleware bên ngoài.
  * **Thực thi tác vụ trực tiếp (Native Tool Calling)**: Agent được đóng gói sẵn các Topics/Tools để mở View, truy vấn dữ liệu, tạo Lead CRM, định tuyến Ticket Helpdesk, gán task và cập nhật bản ghi trực tiếp trên server.
  * **Tôn trọng phân quyền DB tiêu chuẩn**: Các tác vụ truy vấn/tìm kiếm tự động bằng ngôn ngữ tự nhiên vận hành dưới danh tính người dùng đăng nhập và áp dụng đúng quy tắc Record Rule (`ir.rule`) của Odoo.
  * **Hạ tầng sẵn có trên SaaS**: Miễn phí sử dụng chìa khóa API mặc định do Odoo quản lý khi triển khai trên Odoo Online (SaaS).

* **Rủi ro (Risks)**:
  * **Phụ thuộc API bên ngoài & Chi phí chìa khóa**: Chỉ hỗ trợ gọi API sang OpenAI và Google Gemini. Khi chạy On-Premise hoặc Odoo.sh, doanh nghiệp bắt buộc phải tự mua API Key và trả phí token trực tiếp cho nhà cung cấp.
  * **Lỗ hổng phân quyền RAG nội bộ**: Bất kỳ người dùng nào truy cập được Agent đều đọc được toàn bộ tài liệu RAG đính kèm, do tệp nguồn RAG chưa áp dụng phân quyền theo cấp độ người dùng.
  * **Không hỗ trợ MCP & Open API**: Odoo chính thức xác nhận **chưa có kế hoạch** cung cấp MCP Server hay Open API mở rộng cho AI bên ngoài truy cập.
  * **Giới hạn kỹ thuật**: AI mang tính xác suất, có thể phản hồi không ổn định, bỏ qua JSON Schema, chưa hỗ trợ xử lý hàng loạt (batching) hay tương tác đa Agent.

##### 3. Phương án C: Kết hợp (Hybrid) — Giữ hệ thống tự xây cho nghiệp vụ đặc thù, dùng Odoo AI Agent native cho tác vụ chung

* **Ưu điểm (Pros)**:
  * **Tối ưu hóa thế mạnh hai bên**: Dùng Odoo Native AI Agent cho các tác vụ ngay trên UI Odoo (tìm kiếm bản ghi, xem báo cáo, tạo Lead, tóm tắt Chatter, gán task), đồng thời giữ hệ thống tự xây cho các quy trình RAG nhạy cảm, tra cứu tri thức bảo mật hoặc chạy Local LLM.
  * **Giảm tải khối lượng phát triển**: Không phải tốn công tự phát triển lại các tính năng UI/UX AI đơn giản đã được Odoo đóng gói sẵn.
  * **Linh hoạt thử nghiệm**: Giúp doanh nghiệp kiểm chứng độ hiệu quả của Odoo AI Agent native trước khi quyết định dừng hẳn hay mở rộng hệ thống tự xây.

* **Rủi ro (Risks)**:
  * **Trải nghiệm phân mảnh**: Người dùng phải tương tác qua hai giao diện AI khác nhau (Chatbot riêng vs Ask AI/Chatter của Odoo).
  * **Chi phí duy trì kép**: Phải quản lý đồng thời hai hạ tầng (Hạ tầng Server AI tự xây + Chi phí API OpenAI/Gemini của Odoo).
  * **Thiếu khả năng kết nối giữa 2 Agent**: Odoo AI Agent hiện chưa hỗ trợ cơ chế Agent-to-Agent interaction, do đó hệ thống tự xây và Odoo AI Agent không thể tự giao tiếp hay gọi lẫn nhau.

#### III. DANH SÁCH CÂU HỎI CÒN THIẾU DỮ LIỆU (MISSING DATA CHECKLIST)

Để đưa ra quyết định cuối cùng, đội ngũ cần làm rõ các điểm mà tài liệu và video chính thức của Odoo **chưa cung cấp hoặc chưa có câu trả lời rõ ràng**:

1. **Hiệu năng & Độ trễ thực tế (Latency & Performance)**:
   * *Hiện trạng nguồn*: Nguồn chỉ nêu quá trình xử lý/số hóa tài liệu tốn vài giây đến vài chục giây, nhưng **chưa có số liệu benchmark chính thức** về độ trễ trung bình khi gọi RAG hoặc Tool execution trên cơ sở dữ liệu lớn.
2. **Khả năng hỗ trợ Tiếng Việt thực tế trong RAG & Tool Calling**:
   * *Hiện trạng nguồn*: Nguồn xác nhận Odoo 19.0 có tùy chọn ngôn ngữ Tiếng Việt (`VI`) trong tài liệu và có demo tự động dịch tiếng Trung, nhưng **chưa có đánh giá về độ chính xác khi phân tích ngữ cảnh/ngữ pháp tiếng Việt phức tạp** để trigger chính xác Server Actions / Tools.
3. **Chi phí cụ thể & Chính sách API lâu dài**:
   * *Hiện trạng nguồn*: Odoo xác nhận SaaS hiện miễn phí key nhưng lưu ý "chưa biết khi nào sẽ bắt đầu tính phí", đồng thời yêu cầu On-Premise/Odoo.sh tự trả phí cho OpenAI/Gemini. **Chưa có bảng giá hạn ngạch (quota/rate limit) cụ thể** từ Odoo.
4. **Hỗ trợ MCP (Model Context Protocol)**:
   * *Hiện trạng nguồn*: Nguồn tuyên bố Odoo **chưa có kế hoạch** phát triển MCP server hay Open API mở rộng.
5. **Khả năng phân quyền chi tiết cho RAG Sources (Document-level Security)**:
   * *Hiện trạng nguồn*: Odoo thừa nhận hiện chưa áp dụng Record Rule lên tệp nguồn RAG của Agent. **Chưa có lộ trình cụ thể** khi nào Odoo bổ sung tính năng phân quyền nhóm (user groups) cho RAG sources.
6. **Cơ chế Audit Log & Giám sát chi tiết**:
   * *Hiện trạng nguồn*: Odoo có lưu log thực thi và ước tính token, nhưng **chưa có tài liệu hướng dẫn về Dashboard giám sát chi tiết, vết hội thoại đầy đủ hay công cụ đánh giá tự động (Auto-eval)**.
7. **Đồng bộ dữ liệu RAG tự động (Real-time Sync)**:
   * *Hiện trạng nguồn*: Odoo xác nhận khi tài liệu Knowledge hay Documents thay đổi, hệ thống **chưa tự động đồng bộ (sync)** mà phải Re-index thủ công.
