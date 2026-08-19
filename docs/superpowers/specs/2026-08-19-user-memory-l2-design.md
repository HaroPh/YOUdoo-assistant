# Ký ức xuyên phiên — tầng fact bền (L2) — thiết kế

**Ngày:** 2026-08-19
**Trạng thái:** đã brainstorm và chốt từng phần, chờ duyệt để viết implementation plan
**Xuất phát từ:** yêu cầu của chủ dự án — dựng nền ký ức xuyên phiên để mở rộng về sau

---

## 1. Đề bài

Youdoo hôm nay **không nhớ gì xuyên phiên**. Cần phân biệt rõ ba thứ hay bị gộp
chung dưới chữ "memory", vì hai trong ba đã có sẵn:

| | Trạng thái hôm nay |
|---|---|
| State xuyên lượt trong **một** hội thoại (luồng xác nhận ghi) | ✅ `AsyncPostgresSaver`, khoá theo `thread_id` |
| Lịch sử hội thoại hiện tại | ✅ do Open WebUI giữ và gửi lại mỗi lượt |
| Hiểu biết về người dùng **xuyên các phiên khác nhau** | ❌ **không tồn tại** — đề bài của đợt này |

Lưu ý kỹ thuật quan trọng: `_invoke_fresh` **xoá sạch** channel messages mỗi lượt
(`RemoveMessage(REMOVE_ALL_MESSAGES)`) rồi thay bằng đúng những gì client gửi.
Nên checkpointer **không** đóng vai bộ nhớ hội thoại — nó giữ state
interrupt/resume. Ai thiết kế dựa trên giả định ngược lại sẽ sai ngay từ đầu.

**Ghi nhận quyết định:** chưa có phép đo nào chứng minh Youdoo đang hỏng vì
quên. Tôi đã nêu "nên đo trước"; chủ dự án cân nhắc và vẫn quyết làm để có nền
mở rộng. Đây là quyết định đã xác nhận, không phải thiếu sót — nhưng nó là lý do
§8 bắt buộc phải đo false-injection ngay từ v1.

## 2. Đã cân nhắc và LOẠI BỎ

### 2.1 Memori (MemoriLabs) — hữu ích làm tham chiếu, không làm dependency

Dự án thật và tử tế (16.1k sao, Apache 2.0, 630 commit). Nhưng vướng bốn chỗ,
mỗi chỗ là một quyết định kiến trúc Youdoo đã trả giá để có:

| Memori | Youdoo |
|---|---|
| BYODB tài liệu hoá cho **TiDB**; Postgres không được nhắc | Toàn bộ trên Postgres: checkpointer, pgvector RAG, sổ `llm_usage` |
| Tích hợp: LangChain, Agno, Pydantic AI — **không có LangGraph** | LangGraph-native, graph riêng theo từng vai |
| "Advanced Augmentation" tự gọi LLM nền | **Mọi** lượt LLM đi qua `Router`, có ví ngân sách theo vai + ghi sổ Postgres |
| Scoping kiểu entity/process attribution | Cô lập theo vai cưỡng chế tận `ir.rule` của Odoo |

Chỗ thứ ba nghiêm trọng nhất: một thư viện tự gọi LLM **đi vòng qua sổ ngân
sách** — thứ đã tốn nhiều đợt để dựng. Bản Cloud thì đồng nghĩa dữ liệu ERP thật
rời khỏi hệ thống.

**Giữ lại từ Memori:** bộ từ vựng phân loại (facts / preferences / rules /
relationships / skills) — cách chia tốt, dùng lại khi đặt tên.

### 2.2 ConversationBufferMemory / BufferWindowMemory — đi lùi

Abstraction LangChain 0.x đã bị LangGraph thay thế, và **thừa** vì client đã gửi
lại lịch sử. Nếu context phình gây tốn token thì cách đúng là `trim_messages` ở
rìa, không phải dựng hệ memory mới.

### 2.3 Ghi nhớ "việc đang dở" — CẮT

Ba lý do:
1. `list_pending_work` / bản tin việc cần xử lý **đã suy ra** việc đang dở thẳng
   từ Odoo. Khuôn đúng, đã ship.
2. Trong ERP, việc-đang-dở *chính là* bản ghi Odoo (báo giá nháp là `sale.order`
   state=`draft`). Nhớ riêng = tạo nguồn sự thật thứ hai.
3. Rủi ro lệch bất đối xứng: nếu memory nói "bạn đang làm báo giá X" mà X đã bị
   xác nhận/xoá trong giao diện Odoo, trợ lý **nói sai một cách tự tin về bản ghi
   nghiệp vụ thật**.

Phần Odoo không chứa (ý định chưa thành bản ghi) nằm trong tóm tắt phiên — tầng
L1, ngoài phạm vi v1.

### 2.4 Ghi bằng tool call giữa lượt — KHÔNG KHẢ THI ở kiến trúc này

Đây là lời khuyên phổ biến và **đúng với agent một-vòng-lặp**, nhưng Youdoo là
graph định tuyến nhiều node, và **tool chỉ tồn tại ở một số node**. Đã kiểm bằng
code:

| Node | Tool loop | Ngữ cảnh |
|---|---|---|
| `erp_read` (`nodes.py:38`) | ✅ ReAct thật, `_create_agent(llm, tools)` | lịch sử đầy đủ |
| `respond_unknown` (`nodes.py:107-122`) | ❌ `llm.ainvoke` trần, **không bind tool nào** | ❌ **cố ý chỉ gửi tin nhắn user cuối** |

Dòng thứ hai là chỗ chặn: chitchat bị bỏ đói ngữ cảnh **có chủ đích vì bảo mật**
(M5/ADR-009 — chạy cloud nên không được forward dữ liệu ERP từ lượt assistant
trước). Mà các câu khai sở thích ("gọi tôi là anh Hào", "trả lời ngắn thôi") rơi
đúng vào node này.

⇒ Đường ghi bằng tool call **không dùng được ở chính nơi fact xuất hiện**, và
muốn dùng thì phải phá một quyết định bảo mật đã ghi thành ADR.

## 3. Phạm vi v1: chỉ tầng fact bền

Thiết kế theo ba tầng (L1 tóm tắt / L2 fact bền / L3 retrieval). **v1 làm đúng
L2**, các tầng khác ở §9.

Nội dung được nhớ, và **chỉ** những thứ này:
- **Sở thích tương tác** — "trả lời ngắn gọn", "luôn hiện mã đơn"
- **Từ vựng/quy ước riêng** — "đơn khẩn với tôi = giao trong 24h", "kho chính = WH/Stock"

Nguyên tắc bao trùm: **memory chỉ giữ thứ Odoo KHÔNG chứa.** Sự thật nghiệp vụ
đã ở Odoo và truy vấn được; chép sang memory là tạo nguồn sự thật thứ hai sẽ
trôi lệch.

Đường sửa lỗi/dạy lại ("không, kho chính là WH/Stock chứ không phải WH2") **không
phải loại riêng** — về lưu trữ nó chính là một mục từ vựng, chỉ khác ở cách bắt
được.

## 4. Lưu trữ

Bảng mới, **append-only**, khoá theo `user_id`.
`backend/migrations/003_user_memory.sql` — migration **chạy tay** theo đúng khuôn
đã có (`docs/getting-started.md:123-143`), nên tài liệu đó **phải được cập nhật
cùng đợt**, nếu không người dựng máy tiếp theo sẽ thiếu bảng.

```sql
CREATE TABLE user_memory (
    id            bigserial PRIMARY KEY,
    user_id       text        NOT NULL,
    fact_key      text        NOT NULL,   -- CHUẨN HOÁ: chữ thường, BỎ DẤU, khoảng trắng → gạch dưới
    fact_value    text        NOT NULL,
    thread_id     text,                   -- vệt kiểm toán: học được ở đâu
    created_at    timestamptz NOT NULL DEFAULT now(),
    superseded_by bigint      REFERENCES user_memory(id),
    superseded_at timestamptz
);
CREATE INDEX user_memory_active ON user_memory (user_id) WHERE superseded_by IS NULL;
```

**Bất biến: không bao giờ `UPDATE fact_value`, không bao giờ `DELETE`.** Sửa và
gỡ đều là *chèn dòng mới + đánh dấu dòng cũ superseded*. Nhờ vậy mọi ký ức sai
đều gỡ được và vẫn còn vệt kiểm toán.

- Fact đang hiệu lực: `WHERE user_id = ? AND superseded_by IS NULL`
- Khai lại cùng `fact_key` ⇒ supersede tự động (chống trùng)

**Vì sao BỎ DẤU trong `fact_key`:** người Việt gõ cả có dấu lẫn không dấu, và
chính đợt đa ngôn ngữ vừa rồi đã đo được tiếng Việt không dấu là kiểu gõ phổ
biến thật. Nếu giữ dấu thì `kho_chính` và `kho_chinh` thành hai fact khác nhau và
cơ chế supersede **im lặng ngừng hoạt động** — người dùng sửa một fact mà bản cũ
vẫn còn hiệu lực. Bỏ dấu là điều kiện để chống trùng chạy đúng.
- **Trần 50 fact/người**; vượt trần thì supersede cái cũ nhất (không mất gì, vì
  append-only)

**Phạm vi: tất cả riêng tư theo `user_id`.** Không có bảng dùng chung, không có
luật hiển thị chéo, không có bề mặt rò rỉ giữa người/vai. `user_id` là **chuỗi
mờ** từ header Open WebUI — name/email là PII và bị cấm đọc (`roles.py:186-203`),
nên memory khoá theo chuỗi mờ là hợp sẵn với quyết định đó.

## 5. Đường ghi — marker, không phải tool call

Youdoo **đã có sẵn** khuôn "model phát tín hiệu có cấu trúc mà không tốn thêm
request": marker trong chính câu trả lời, code tất định bóc ra
(`ĐỀ_XUẤT_GHI:` → `extract_write_suggestion()`, `NGUỒN_DÙNG:` →
`extract_used_citations()`).

```
GHI_NHỚ: kho chính = WH/Stock
QUÊN: kho chính
```

Model được phép viết key tự nhiên (có dấu, có khoảng trắng); **code chuẩn hoá**
thành `kho_chinh` trước khi ghi và trước khi so khớp supersede. Model không phải
nhớ quy tắc chuẩn hoá — đó là việc của code.

**Chi phí LLM: 0 lượt gọi thêm.** Marker tốn ~20 token output, chỉ khi bắn.

⚠️ **Regex phải bắt CẢ HAI dạng: đầu dòng VÀ dán dính cuối câu.** Không phải
phòng xa — lỗi này đã xảy ra thật với `ĐỀ_XUẤT_GHI` (model dán marker ngay sau
dấu hỏi thay vì xuống dòng như prompt yêu cầu) và phải sửa bằng một pattern thứ
hai (`synthesis.py`, `_WRITE_SUGGEST_RE`).

**Bóc ở một chốt duy nhất: `ERPAgent.chat()`** (`erp_agent.py:189`). Lý do chọn
chốt thay vì vá từng node: lớp lỗi "danh sách khai báo thiếu âm thầm" đã **tái
phát 5 lần** trong repo này, và `chat()` vừa được chứng minh là chốt đúng ở đợt
đa ngôn ngữ.

**Thứ tự bắt buộc trong `chat()`:**

```
_chat_inner() → bóc marker → chuẩn hoá key → cổng phủ quyết (§6.1) → ghi DB → chèn dòng công bố (§7) → localize()
```

Bóc **trước** `localize()` để bản dịch không làm hỏng marker; chèn công bố
**trước** `localize()` để người dùng tiếng Anh nhận câu công bố bằng tiếng Anh.

## 6. Đường đọc, và cổng phủ quyết bắt buộc

`main.py` đã đọc `x-openwebui-user-id` nhưng hiện chỉ dùng suy ra vai — `chat()`
cần nhận thêm `user_id`.

Nạp fact đang hiệu lực **một lần** ở `chat()`, đặt vào `ERPAgentState`, mỗi node
ghép vào đầu system prompt của mình — **theo đúng tiền lệ đã có** ở `erp_read`
(`nodes.py:44-46`, `render_working_context(wc) + "\n\n" + SYSTEM_PROMPT`).

Bốn chỗ ghép ⇒ **bắt buộc có test dựng graph THẬT** khẳng định cả 4 node đều
nạp, đúng khuôn `test_prompt_language_rule.py`. Đây là lưới chống đúng lớp lỗi
"khai báo thiếu âm thầm" nêu ở §5.

### 6.1 Xung đột với M5/ADR-009 và cách đóng

`chitchat` cố ý không nhận lịch sử vì chạy cloud và không được forward dữ liệu
ERP từ lượt assistant trước. Nhét memory vào đó là đi vào đúng ranh giới ấy.

Lập luận cho phép: memory chứa thứ **người dùng tự khai**, gần với "tin nhắn của
chính người dùng" hơn là "dữ liệu assistant fetch về".

Nhưng lập luận đó **chỉ đúng nếu có gì đó cưỡng chế**. Marker do LLM phát ra, mà
ở `erp_read` model đang nhìn thấy dữ liệu ERP thật — không có gì ngăn nó ghi
`GHI_NHỚ: đơn_mới_nhất = S00165`, rồi fact đó rò sang cloud ở lượt chitchat sau.

⇒ **Cổng phủ quyết tất định: từ chối mọi fact có hình dạng mã chứng từ cụ thể**
(mã chữ+số: `P00003`, `S00012`, `INV/2026/00004`, `WH/OUT/00001`).

Ranh giới kiểm được: fact nói về *loại/quy ước* thì cho (`kho_chinh = WH/Stock` —
không có chữ số); fact trỏ *một bản ghi cụ thể* thì chặn. Tái dùng đúng họ regex
`_FACT` đã tôi luyện ở `localize.py`.

Cổng này chặn **`fact_value`**; `fact_key` đã qua chuẩn hoá nên không mang mã.

Lại đúng khuôn quen: **model đề xuất, code phủ quyết** — như `decide_route`,
`verify_erp_grounding`, `facts_survived`.

### 6.2 Bán kính cổng eval

| Prompt | Injection | Marker ghi | Cổng chạy lại |
|---|---|---|---|
| `SYSTEM_PROMPT` | ✅ | ✅ | `read` |
| `CHITCHAT_PROMPT` | ✅ | ✅ | `chitchat` |
| `RAG_SYNTHESIS_PROMPT` | ✅ | ❌ | `synthesis` |
| `FUSE_PROMPT` | ✅ | ❌ | `multi_source` |

Marker ghi chỉ đặt ở 2 prompt người dùng thật sự trò chuyện — đặt khắp nơi chỉ
tăng nguy cơ bắn marker vu vơ.

**KHÔNG đụng:** `INTENT_ROUTER_PROMPT` (bất biến byte-for-byte mà một plan khác
đang canh), `WRITE_PLANNER_PROMPT`, `GATHER_ERP_PROMPT`. Phải kiểm bằng grep trên
diff, không tin tuyên bố.

Chi phí prompt: trần 50 fact ≈ 750 token/lượt — không đáng kể với TPM 250k của
các model đang phục vụ 4 vai này.

## 7. Công bố — do CODE làm, không phải model

Quyết định: **ghi ngay + nói rõ + dễ gỡ** (không dùng interrupt — bị chặn luồng
mỗi lần lỡ khai một sở thích là quá phiền, và cơ chế interrupt đã có lịch sử bug
nghiêm trọng).

Nếu để model tự công bố thì sẽ có lượt nó quên, mà **ghi âm thầm là đúng thứ cần
tránh**. Nên sau khi bóc marker, code **tự chèn** dòng tất định:

> 📝 Đã ghi nhớ: kho_chinh = WH/Stock — nói "quên đi" nếu sai.

(Hiển thị đúng key **đã chuẩn hoá** như nó nằm trong DB, để người dùng gỡ được
bằng chính chuỗi họ nhìn thấy.)

Cùng khuôn `build_citations()` (`synthesis.py:89`) đang dùng cho chân trang trích
dẫn: model không được phép quên, vì không phải việc của model.

**Xem ký ức: không cần cơ chế mới.** Fact đã nằm trong prompt nên "bạn nhớ gì về
tôi?" model tự trả lời được.

## 8. Đo lường — bộ eval `memory`

Trả lời trực tiếp cho rủi ro "ghi càng thường xuyên, nhớ nhầm càng nhiều — mà ký
ức sai **không báo lỗi**, nó chỉ âm thầm làm mọi câu trả lời sau tệ đi".

| Nhóm ca | Đo | Cổng |
|---|---|---|
| Hội thoại **không có** fact bền | Marker **không** bắn | `false_injection == 0` — **tuyệt đối** |
| Hội thoại có sở thích rõ ràng | Marker bắn, đúng key/value | ghi nhận, chưa gác (chưa có baseline) |
| Hội thoại có dữ liệu ERP thật | Cổng §6.1 chặn mã chứng từ | `leaked_doc_code == 0` — **tuyệt đối** |

`false_injection` là hướng nguy hiểm nên gác tuyệt đối, đúng khuôn `violations`
của `chitchat` và `fabricated_param` của `read`.

⚠️ **Đăng ký đủ 5 chỗ**: `EVAL_FN`, `ROLE_FOR_SET`, `_gate`, `--set all`, **và**
`choices`/`_FN` của `run_eval.py::main()`. Chỗ cuối chính là cái plan đa ngôn ngữ
bỏ sót và chỉ lộ ra khi chạy thật.

Bộ này **nằm trong `--set all`** vì có điều kiện an toàn tuyệt đối — đúng tiền lệ
`chitchat`, và đúng cách vừa sửa cho `language`.

**Bốn cổng ở §6.2 phải chạy lại và không được thụt.**

### 8.1 Nghiệm thu sống (bắt buộc, TRƯỚC merge)

Test đơn vị **không chứng minh được gì** về ký ức xuyên phiên. Phải qua HTTP thật:

1. Phiên A: khai một sở thích → xác nhận có dòng công bố
2. **Phiên B khác hẳn** (thread_id khác): xác nhận sở thích được áp dụng
3. "quên đi" → xác nhận hết áp dụng, và dòng cũ vẫn còn trong DB (superseded, không xoá)
4. Khai một fact chứa mã chứng từ → xác nhận cổng §6.1 chặn

## 9. Ngoài phạm vi v1

- **L1 — tóm tắt phiên**, cron gộp, watermark `last_summarized_message_id`. Đợt
  sau, và chỉ sau khi đo xem bao nhiêu % nhu cầu thật rơi ra ngoài L2. Khi làm:
  giữ transcript gốc làm nguồn sự thật để mọi tầng re-derive được khi đổi
  summarizer — cùng bài học đã buộc RAG phải dựng `rag_embedding_marker`.
- **L3 — retrieval toàn lịch sử.** Chỉ chính đáng khi memory không nhét vừa
  prompt. Khi làm: expose dạng **tool**, đừng gate bằng router (thêm nhánh ý định
  là phải đo lại `intent`/`sop_select` và bất biến `hijack==0`); index ở mức
  fact/chủ đề chứ đừng index nguyên bản tóm tắt phiên; bắt buộc kèm lọc thời gian.
- **Chia sẻ giữa người dùng / từ vựng chung toàn công ty** — đã chốt: tất cả riêng tư.
- **Phát hiện hai fact mâu thuẫn KHÁC key** (`kho_chinh` vs `kho_mac_dinh`) —
  giới hạn đã biết của v1, không xử lý; thuộc về tầng gộp (cron) ở đợt sau.
