# Mục 16 — dựng lại mắt xích dự phòng ngoài Google

**Ngày**: 2026-08-22. **Nhánh**: `main`.

## 1. Đề bài

Bản kiểm toán (`docs/kiem-toan-2026-08-22.md`) nêu FM-3: hội thoại dài làm chết
hẳn khả năng trả lời. Chủ dự án chọn **phương án A** — khôi phục một model
OpenRouter làm mắt xích dự phòng.

## 2. Việc đã làm

1. Đưa lại `or-nemotron` (`nvidia/nemotron-3-super-120b-a12b:free`) vào
   `CATALOG`, và vào `CHAINS` của cả bảy vai ⇒ chuỗi thành ba mắt xích:
   `gemini-3.1-flash-lite → groq-gpt-oss-120b → or-nemotron`.
2. Xoá `test_ba_bat_bien_duoi_day_HIEN_RONG_CHU_THE` — test tự-hết-hạn theo
   thiết kế, docstring của chính nó dặn xoá khi tình trạng rỗng chấm dứt.
3. Thêm **bất biến #6**: mọi vai bind tool phải có ≥1 mắt xích `upstream !=
   "google"` và `supports_tools`. Kèm phép thử phá.
4. Gỡ 6 test bám cứng vào **độ dài chuỗi**, chuyển sang suy từ `CHAINS`.
5. Cập nhật `docs/provider-quotas.md`.

## 3. ⚠️ Tiền đề ban đầu của mục này ĐÃ BỊ SỐ ĐO BÁC BỎ

Tôi trình bày lý do khôi phục là: *"`groq-gpt-oss-120b` (tpm 8 000) trả HTTP 413
cho vai admin ngay từ lượt đầu, nên sau đợt gom catalog 2026-08-21 bốn vai bind
tool không còn dự phòng nào dùng được — một hồi quy do chính tôi gây ra."*

**Phép đo đó bind cả 35 tool MCP vào LLM. Production không gửi hình dạng đó.**

`erp_read` bind `build_erp_query_tools(role_cfg)` = **28 tool `erp_query`**
(`graph.py:68`). Tool MCP chỉ đi tới `erp_write_executor` — nút **chạy** tool
(`by_name = {t.name: t for t in tools}`), không bind chúng vào model nào.

Đo lại đúng hình dạng, vai admin, lượt `read`:

| lịch sử | Groq đếm | Gemini đếm |
|---|---|---|
| 0 lượt | 2 762 | 3 119 |
| 20 lượt | 3 542 | — |

≈ 39 token/lượt ⇒ cần ~134 lượt mới chạm 8 000. **Groq không hỏng trong
production, và FM-3 không xảy ra ở đây.**

Đã nghiệm thu qua **cổng vào thật** (`POST /v1/chat/completions`, port 8002, có
`x-openwebui-user-id` của vai admin): HTTP 200 trong 10,2s, trường `model` báo
`gemini-3.1-flash-lite` — tức mắt xích 1 phục vụ bình thường, không tụt.

### 3.1 Nghiệm thu chuỗi tụt (payload production, 28 tool)

| tình huống | mắt xích phục vụ | depth | tool_calls | token |
|---|---|---|---|---|
| không ép | `gemini-3.1-flash-lite` | 0 | 1 | 3 136 |
| ép 2 mắt xích đầu vào cooldown | `or-nemotron` | 2 | 1 | 4 175 |

Và qua **cổng vào production** (`POST /v1/chat/completions`, có
`x-openwebui-user-id`): chọn `gemini-3.5-flash-lite` ⇒ HTTP 200 trong 6,7s,
trường `model` báo đúng model đó, trả về **dữ liệu Odoo thật** (S00188/S00187/
S00186).

## 4. Vì sao vẫn giữ `or-nemotron`

Hai lý do khác, đo được, và cả hai đều đúng từ trước:

1. **Miền lỗi thứ ba.** Google → Groq chỉ có hai đường thoát. `upstream =
   "nvidia"` thêm đường thứ ba. Đây là nội dung bất biến #6.
2. **Thông lượng.** 8 000 tpm của Groq tính trên **cả phút**, mọi lời gọi đồng
   thời cộng dồn ⇒ ~3 lượt có tool trong một phút là 429 — gặp thật lúc đo
   (`Requested=6858`). `tpm = None` không có trần đó.

**Loại `gemini-3.5-flash`** (chủ dự án đề xuất): `upstream = "google"` nên nó
không mua được lý do 1. Với ba khoá ví Gemini đã ~3 000 lượt/ngày, 20 lượt là
nhiễu; và kịch bản mà dự phòng THẬT SỰ cứu được thì nó chết cùng lúc.

## 5. Khó khăn / hướng đã chọn / giới hạn còn lại

**Khó khăn 1 — đo sai hình dạng payload.** Tôi lấy 35 tool MCP vì đó là con số
`erp_agent` in ra, mà không kiểm nó có tới LLM nào không. Hai lỗi thu được (413
của Groq, 400 của Gemini) đều THẬT nhưng đều không chạm production. *Hướng đã
chọn*: nghiệm thu lại qua đúng cổng vào production trước khi kết luận, và giữ
lại cả hai lập luận trong doc thay vì xoá cái sai. *Giới hạn*: chưa có test nào
canh "payload đo được phải là payload production gửi" — nếu đo lại kiểu này lần
nữa thì vẫn không có gì báo.

**Khó khăn 2 — test bám cứng độ dài chuỗi.** Chuỗi đổi độ dài hai lần trong hai
ngày; lần nào cũng làm đỏ 6 test không liên quan tới thay đổi. Một trong số đó
(`test_resolve_skip_het_chuoi_thi_nem_ChainExhausted`) liệt kê `or-ling` — model
đã xoá hôm trước — mà vẫn **xanh**, vì skip một alias không tồn tại là vô hại.
*Hướng đã chọn*: mọi ca "cạn cả chuỗi" nay suy từ `CHAINS`; `_router()` có tham
số `mac_dinh` cho ca "mọi mắt xích cùng hỏng", và **cố ý giữ KeyError** khi
không truyền `mac_dinh`, để ca "phải tụt đúng tới mắt xích 2" không im lặng
nuốt một mắt xích thứ ba. *Giới hạn*: `_fill(r, alias, spec_for(alias).rpd)`
giả định mọi mắt xích đều có `rpd`; mắt xích `rpd=None` sẽ làm ca đó hỏng ồn ào
(chấp nhận được — hỏng ồn ào, không xanh giả).

**Khó khăn 3 — bất biến #3 không bảo vệ thứ tên nó gợi ý.** `HEAVY_TPM_FLOOR`
nói về vai NẶNG, không nói về vai CÓ TOOL. Tôi suýt đóng đinh con số 8 040 (rút
từ phép đo sai) thành luật. *Hướng đã chọn*: bất biến #6 chỉ khẳng định thứ
đo được và đúng — đa dạng upstream — và **không** mang ngưỡng token nào.
*Giới hạn*: trần thông lượng của Groq (429 khi ~3 lượt/phút) hiện **không có
bất biến nào canh**; nó là đặc tính vận hành, không phải hằng số trong bảng.

**Khó khăn 4 — lệnh xoá test cắt tới cuối tệp.** Script xoá
`test_ba_bat_bien_duoi_day_HIEN_RONG_CHU_THE` dùng `s = s[:i]`, nên nó nuốt luôn
**3 test phía sau** (`test_nhip_lay_tran_CHAT_HON_giua_rpm_va_tpm`,
`test_nhip_cua_gemini_KHONG_doi_sau_ban_sua`,
`test_nhip_khop_voi_so_DO_THAT_tren_groq`) — đúng nhóm canh `nhip_toi_thieu`,
hàm vừa sửa cùng ngày. Bộ test vẫn **xanh** (2015 passed) vì mất test thì không
có gì đỏ. *Cái bắt được*: đối chiếu tổng số ca với lượt chạy trước (2018 → 2015)
rồi `git diff | grep "^-def "`. *Hướng đã chọn*: lấy lại từ `git show HEAD:`.
*Giới hạn*: không có cổng nào canh "số ca giảm" — đối chiếu vẫn là việc của mắt
người.

**Phát hiện ngoài phạm vi (chưa sửa):** 10 tham số kiểu `list` **trần** trong
`mcp-servers/odoo/tools/*.py` (`lines`, `ops`, `components`, `changes`,
`partner_ids`, `vendor_names`) sinh JSON-Schema thiếu `items`, thứ Gemini **từ
chối** bằng HTTP 400. Vô hại hôm nay vì các tool đó không bind vào LLM nào; sẽ
thành chặn đường nếu có ai nối registry MCP thẳng vào một model Gemini.
