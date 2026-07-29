# ADR-011: SP-1 Foundation — Quyết định giữ lại sau khi spec/plan hết hạn dùng

Spec (`docs/superpowers/specs/2026-07-28-sp1-foundation-design.md`) và plan
(`docs/superpowers/plans/2026-07-28-sp1a-llm-gateway.md`) mô tả **làm thế
nào** — chúng đúng lúc viết ra rồi cũ dần khi code đổi. File này ghi **đã
quyết gì và vì sao**, phần phải sống lâu hơn cả hai. Một phiên tương lai clone
repo về phải đọc được file này một mình, không cần mở lại spec hay plan.

## 1. SP-1 thay thế QĐ M2 của ADR-009 có chủ đích

ADR-009 (QĐ M2) khoá 4 vai (Read/Planner/Fusion/Synthesis) chạy model local
vì lý do riêng tư dữ liệu. SP-1 bỏ Ollama hoàn toàn khỏi đường chat, nên 4 vai
đó không còn chỗ nào để chạy ngoài các provider cloud — đây là một sự thay
thế có chủ đích cho QĐ M2, không phải một trôi dạt ngoài ý muốn. Lý do chấp
nhận: dữ liệu Odoo trong dự án này là dữ liệu demo, và bản thân project là
demo/portfolio — chủ dự án đã xác nhận điều này ngày 2026-07-28. Kèm theo một
dữ kiện củng cố: tier trả phí của Anthropic/OpenAI mặc định không dùng dữ
liệu gọi API để huấn luyện, trong khi free tier của Google AI Studio thì có
dùng — vì vậy ranh giới "free cho demo bây giờ, trả phí khi dùng thật sau"
là ranh giới đúng chỗ để vẽ, không phải một thoả hiệp tạm bợ.

## 2. Bỏ LiteLLM

Phép đo ngày 2026-07-28 xác nhận cả ba nhà cung cấp (Google, Groq,
OpenRouter) đều OpenAI-compatible và giữ được tool-calling tiếng Việt qua
chuẩn đó. Giá trị "hợp nhất giao thức" mà LiteLLM mang lại vì vậy bốc hơi —
không còn sự khác biệt giao thức nào đáng để một lớp trung gian giải quyết.
Bài toán thật của SP-1 là kế toán hạn mức free-tier theo ngày trên nhiều
provider cùng lúc, và đó đúng là chỗ LiteLLM yếu nhất, nên việc tự viết
`catalog.py` + `budget.py` thay vì dựa vào LiteLLM là lựa chọn đúng hướng.

## 3. Langfuse self-host, không dùng Langfuse Cloud

Trace không phải một lời gọi API thoáng qua rồi biến mất — nó là kho lưu
trữ tập trung, tìm kiếm được, tồn tại lâu dài, nên mang loại rủi ro dữ liệu
khác hẳn so với một request chat đơn lẻ. Ngoài ra hạn mức observation của
bản Cloud sẽ chạm trần đúng vào lúc SP-3 chạy tải fan-out — tự host tránh
được cả hai vấn đề cùng lúc.

## 4. Loại NVIDIA NeMo Guardrails

Rail của NeMo Guardrails hoạt động bằng cách gọi thêm một LLM khác để kiểm
tra, tức là nhân ba mức tiêu thụ đúng tài nguyên khan hiếm nhất của kiến
trúc này (lượt gọi free-tier). Nó cũng chỉ chặn theo xác suất, trong khi
`agentic_gate` của repo đã làm việc đó bằng một tool ghi có tính **bất khả
đạt** (không thể vòng qua bằng prompt). Khoảng trống thật cần lấp — prompt
injection ở input người dùng và ở chunk RAG — giao cho SP-2 xử lý bằng
`meta-llama/llama-prompt-guard-2-*` chạy trên Groq, không cần thêm một
framework guardrail riêng.

## 5. Guard nào co được, guard nào không

Có hai loại guard khác bản chất trong hệ thống. Guard bù cho sự kém cỏi của
model (ví dụ `max_tokens=4096` của planner, hay timeout điều chỉnh theo
`is_qwen`) là guard **co được** — khi model mạnh hơn, guard này có thể nới
hoặc bỏ. Guard ràng buộc thẩm quyền (`write_gate`, `agentic_gate`, denylist ở
gateway) thì **không co được** dù model có mạnh tới đâu, vì mục đích của nó
không phải bù năng lực mà là giữ ranh giới quyền hạn. Nguyên tắc chung: model
mạnh hơn là model giỏi hơn trong việc tìm ra một đường đi chưa ai lường tới,
nên đúng những guard thẩm quyền lại càng cần giữ nguyên khi model nâng cấp.

## 6. `fusion` giữ qua SP-1, bỏ ở SP-2

Theo nguyên tắc một-biến (đổi một thứ mỗi lần để còn biết cái gì gây ra kết
quả gì), SP-1 giữ nguyên vai `fusion` chạy `multi_source` hai lượt như thiết
kế cũ, không gộp nó vào orchestrator ngay. Việc quyết định có gộp nhánh
`fusion` vào cơ chế fan-out mới hay không được để lại cho SP-2, dựa trên số
liệu đo được từ orchestrator thật thay vì đoán trước.

## 7. Đính chính ADR-010

ADR-010 viết rằng "summarization cho meeting agent giao Groq (nhanh với văn
bản dài)". Đo thực tế ở SP-1 cho thấy giả định đó sai: với trần 8K TPM của
Groq, một transcript cuộc họp dài không lọt nổi trong một request, nên Groq
không phù hợp cho việc này như đã nghĩ. Đây là việc của SP-4 chứ không phải
SP-1, nhưng ghi lại ngay ở đây để các phiên sau không tiếp tục đi theo giả
định sai đó. Ghi kèm một dữ kiện bù lại: Groq có sẵn model host
`whisper-large-v3`, nghĩa là có thể bỏ luôn nhu cầu GPU cục bộ cho việc
transcribe của meeting agent.
