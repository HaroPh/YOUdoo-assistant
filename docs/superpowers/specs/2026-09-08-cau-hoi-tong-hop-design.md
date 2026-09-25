# Câu hỏi TỔNG HỢP trên đường tài liệu — thiết kế

**Ngày**: 2026-09-08. **Nhánh**: chưa tạo. **Trạng thái**: thiết kế, chưa viết code.

Nguồn: chủ dự án mang về một bài viết cộng đồng mô tả nhược điểm cố hữu của RAG top-k với
câu hỏi dạng "Tổng quan…", "Tóm tắt…", "Có bao nhiêu…", kèm 4 đóng góp từ người khác. Spec
này (a) xác nhận Youdoo có đúng nhược điểm đó bằng số đo, (b) đối chiếu 4 đóng góp với hạ
tầng thật, (c) chốt lộ trình.

---

## 1. Đề bài, đo được

Chạy `retrieve()` thật trên corpus production ngày 2026-09-08 (4.870 chunk / 18 tài liệu),
CHỈ tầng truy xuất, không gọi LLM sinh:

| loại câu hỏi | câu hỏi | kết quả truy xuất | `dense_max` | `passes_floor` |
|---|---|---|---|---|
| tra cứu điểm | thuế suất thuế GTGT là bao nhiêu? | đúng `Điều 9. Thuế suất` | 0,722 | ✅ đúng |
| tóm tắt, tài liệu nhỏ | tóm tắt chính sách hoàn hàng | **5/5** chunk của tài liệu | 0,672 | ✅ **may mắn** |
| tóm tắt, tài liệu lớn | tóm tắt luật doanh nghiệp | 6 chunk, **toàn Chương I** | 0,614 | ⚠️ **6/530 = 1,1%** |
| tổng quan | tổng quan các chính sách bán hàng của công ty | 3/6 chunk là **luật**, 1 chunk rác OCR | 0,542 | ⚠️ lạc đề |
| đếm trên corpus | có bao nhiêu quy trình kho trong tài liệu nội bộ? | trúng nhập+xuất kho | 0,586 | ✅ may mắn |
| liệt kê trọn corpus | liệt kê tất cả các chính sách của công ty | 4/6 chunk là **luật**, 2 chunk rác (`"49 GB"`, `"_—" P SN"`) | 0,507 | ⚠️ gần vô dụng |
| liệt kê trong 1 mục | các hình thức xử lý kỷ luật lao động gồm những gì? | đúng `Chương VIII › Mục 1` | 0,735 | ✅ đúng |

**Ba kết luận, theo thứ tự quan trọng:**

**1.1 — Hỏng KHÔNG PHẢI ở dạng từ chối, mà ở dạng TỰ TIN TRẢ LỜI THIẾU.** `passes_floor`
(`synthesis.py:233`, sàn cosine 0,35) **cho qua 7/7 câu**, kể cả câu tệ nhất (0,507). Và
`RAG_SYNTHESIS_PROMPT` còn ép: *"Nếu tài liệu CÓ đề cập đến chủ đề câu hỏi thì PHẢI trả
lời"*. Sáu chunk Chương I của Luật Doanh nghiệp **có** đề cập chủ đề ⇒ model buộc phải tóm
tắt ⇒ ra một bản "tóm tắt Luật Doanh nghiệp" thực chất chỉ là Chương I, kèm footer 📄 trích
dẫn trông rất đáng tin. **Không có chỗ nào trong thiết kế hiện tại nói được "tôi mới đọc
6/530 đoạn".**

**1.2 — Chỗ nó "chạy được" là do MAY.** Tài liệu nghiệp vụ có đúng 5 chunk ≤ `TOP_K = 6`
nên tóm tắt trọn vẹn. Thêm một chính sách dài hơn 6 chunk là gãy, **không có tín hiệu nào
báo**. Đây không phải năng lực, là trùng hợp về kích thước.

**1.3 — Bộ eval hiện tại MÙ với lớp câu hỏi này.** 64 ca `retrieval` + 28 ca
`synthesis_live` đều là tra cứu điểm. Các ca chứa chữ "bao nhiêu" đều là "bao nhiêu
%/ngày" — một con số nằm gọn trong MỘT chunk. **Không có một ca nào** chứa "tóm tắt" hay
"tổng quan". Điểm số đang xanh không nói gì về lớp này; đây là vùng mù, không phải vùng đã
kiểm.

## 2. Cơ chế, đã truy tới dòng

`retrieve()` (`retrieve.py:150-195`) là đúng sơ đồ bài viết mô tả: embed câu hỏi → top-20
ứng viên mỗi chân → RRF → rerank → **cắt còn `TOP_K = 6`** (`config.py:36`). Không nhánh
nào khác. Không aggregation, không map-reduce, không truy vấn metadata.

Router thì CÓ (`routing.py`), nhưng nó phân loại **NGUỒN** (`erp_read` / `erp_write` /
`rag` / `mixed` / `unknown`), **không phân loại KIỂU câu hỏi**. "Tóm tắt X" và "thuế suất X
là bao nhiêu" đi vào cùng một node `rag`, nhận cùng 6 chunk.

Số 6 là trần cứng cho MỌI câu hỏi tài liệu. Với câu tra cứu điểm nó thừa; với câu tổng hợp
nó thiếu hai đến ba bậc độ lớn.

## 3. Ràng buộc nền — vì sao không bê nguyên đóng góp vào được

| đóng góp giả định | Youdoo thực tế |
|---|---|
| RAGFlow | **Không có.** Pipeline tự viết trong `backend/src/rag/` |
| Elasticsearch (có sẵn trong RAGFlow) | **Không có.** Nhưng đã có `gin (ts_vector)` trong Postgres — chân FTS sẵn rồi, và đang chết vì lý do khác (`retrieve.py:_sparse` docstring) |
| vLLM Qwen3 chạy local | **Không có LLM sinh nào chạy local.** `ollama list` = chỉ `bge-m3` (embedding) |

Ràng buộc thứ ba chi phối mọi thứ. Mọi lời gọi sinh đi free tier cloud (`llm/catalog.py`):

| mắt xích | rpm | tpm | **rpd** |
|---|---|---|---|
| `gemini-3.1-flash-lite` | 15 | 250 000 | **500** |
| `groq/gpt-oss-120b` | 30 | 8 000 | **1 000** |
| openrouter (ví CHUNG cả tài khoản) | — | — | **50** |

Ví này **dùng chung với chính con chatbot đang phục vụ người dùng** (`RPD_SAN_PHUC_VU = 500`
là bất biến "đủ phục vụ trọn một ngày"). Bạn viết bài có vLLM nên "cho AI tóm tắt toàn bộ
trước khi nạp" với họ là miễn phí; với Youdoo đó là một khoản ngân sách tính bằng ngày, và
phải trả lại mỗi lần re-ingest.

## 4. Đối chiếu 4 đóng góp

### 4.1 — "3 luồng + Small-to-Big + LLM nhỏ temp=0"

Ý ba luồng **đúng**, khớp chẩn đoán mục 2. Hai chỗ phải sửa:

**(a) "Thêm 1 LLM nhỏ temp=0 phân loại intent" — Youdoo ĐÃ CÓ, và bê nguyên là nguy hiểm.**
`routing.py` đã đúng kiến trúc đó: lớp LLM đề xuất + **lớp veto tất định**. File đó ghi 3
bằng chứng độc lập rằng LLM phân loại đứng một mình thì sai — live-verify lỡ 3/3 lần, đổi
model không cứu, model *to hơn* còn tệ hơn (inverse scaling, McKenzie et al., TMLR 2023).
Việc cần làm là **mở rộng `VALID_INTENTS` của lớp đã có, kèm veto**, không phải dựng lớp
phân loại thứ hai.

**(b) Small-to-Big đúng ý tưởng nhưng SAI ĐƠN VỊ trên corpus này.** Đo cây `section_path`:

| cấp | số node (theo `doc_id`) | token trung vị | token TB | token max |
|---|---|---|---|---|
| lá (`Điều`/`Khoản`) | 2 045 | **258** | 445 | 21 547 |
| cấp 2 (`Chương › Mục`) | 351 | 668 | 2 595 | 51 393 |
| cấp 1 (`Chương`) | 89 | — | ~55 chunk | — |

Node lá có **trung vị 258 token — nhỏ hơn một chunk (`CHUNK_SIZE_TOKENS = 400`)**. Tóm tắt
lá = tóm tắt cái đã bé sẵn: tốn 2 045 lời gọi để mua gần như không gì.

Đơn vị đúng là **cấp 2 + cấp 1 = 351 + 89 = 440 node**. Với `rpd = 1 000` của Groq đó là
**một ngày ngân sách, một lần** — khả thi. Con số này là thứ đổi phán quyết của đóng góp
này từ "chắc không đủ quota" sang "làm được", nên nó phải nằm trong spec.

### 4.2 — "Thêm lớp graph + Query Understanding"

Sát nhất về chẩn đoán. Nhưng **phần lớn thứ nó đề nghị xây thì đã có**: cây
`Chương › Mục › Điều › Khoản` đã được materialize trong cột `section_path`, sâu tới 4 cấp
(đợt P3b). Không cần graph DB, không cần đổi chunking. Thiếu đúng 3 thứ nhỏ: không có
`parent_id`, không có index tiền tố, không có rollup summary.

Kiểm chứng cây là THẬT chứ không phải rác — 6 node cấp 2 lớn nhất đều là chương luật hợp lệ
(`Chương V › CÔNG TY CỔ PHẦN` 174 chunk, `Chương V › BẢO HIỂM XÃ HỘI BẮT BUỘC` 128 chunk…).

**Hai cảnh báo:**

- **Cây chỉ tin được ở 9 PDF luật.** Với báo cáo tài chính và tài liệu công ty, `section_path`
  đo ra là rác: `"Chương trình › 39 BIẾT KP"`, `"_—" P SN"`. Nhánh graph phải giới hạn ở
  corpus có phân cấp thật, không áp toàn bộ.
- **"Query Understanding thay vì phân loại" là chống chỉ định Ở ĐÂY** — không vì sai lý
  thuyết (lập luận "ranh giới giữa 10 intent là mỏng" đúng), mà vì nó đổi 1 lời gọi LLM lấy
  N lời gọi **cho mỗi câu hỏi**, trong khi ví là 500–1 000 req/NGÀY dùng chung với chatbot.
  Với Youdoo, "MVP phân loại là đủ" không phải thoả hiệp — nó là lựa chọn đúng theo ngân sách.

### 4.3 — "Dùng RAGFlow agent để phân loại"

Không áp dụng: không có RAGFlow. Phần ý tưởng trùng 4.1(a).

### 4.4 — "Trích metadata ra bảng Postgres riêng, dạng đếm chuyển thành SQL"

**Rẻ nhất, đúng nhất cho Youdoo, và gần như đã có sẵn**: bảng `rag_documents` đã tồn tại,
đã có `doc_id` làm khoá ngoại từ `rag_chunks`. Chỉ thiếu cột.

Nhưng nó **bị chặn** bởi một lỗi đo được ngày 2026-09-08: **8/9 PDF luật có
`doc_title = "QUỐC HỘI"`** (bộ thứ 9, `luat-doanhnghiep.pdf`, có
`"QUỐC HỘI CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"`). Câu SQL đếm/lọc theo tên tài liệu sẽ trả
số sai một cách IM LẶNG. Xem mục 6.

## 5. Chỗ CẢ BỐN đóng góp bỏ sót

Không đóng góp nào nói tới kết luận 1.1: **cổng an toàn cho qua 7/7 câu tổng hợp**. Kể cả
khi dựng xong 3 luồng, một câu tổng quan bị phân loại nhầm về luồng 1 vẫn sẽ được trả lời
tự tin và thiếu, **y như hiện nay**.

Mọi thiết kế "phân loại rồi rẽ luồng" đều đặt single point of failure ở bộ phân loại — chính
đóng góp 4.2 đã nói điều đó. Nhưng lời giải của họ (Query Understanding) thì Youdoo không
trả nổi. **Lời giải rẻ hơn và hợp với kiến trúc sẵn có: một tín hiệu ĐỘ PHỦ tất định, độc
lập hoàn toàn với việc phân loại đúng hay sai.** Nếu truy xuất chỉ chạm 6/530 đoạn của một
tài liệu, con số đó phải đi cùng kết quả — bất kể câu hỏi được phân vào luồng nào.

Đây đúng tinh thần "veto tất định" mà `routing.py` đã chọn và đã bảo vệ bằng 3 bằng chứng.

## 6. Quyết định — `doc_title` và cổng trùng tên

Nguồn lỗi, đã truy tới dòng (`chunking.py:83`):

```python
doc_title = next((b["text"] for b in blocks if b["heading_level"]),
                 os.path.basename(source_file))
```

Heading ĐẦU TIÊN của một PDF luật là **dòng quốc hiệu**, không phải tên luật. Đầu
`luat-doanhnghiep.pdf` thực tế:

```
chunk 0  [QUỐC HỘI CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM]  ------- Độc lập - Tự do - Hạnh phúc ...
chunk 1  [LUẬT]                                          DOANH NGHIỆP Căn cứ Hiến pháp ...
```

Tên thật (`LUẬT DOANH NGHIỆP`) bị **cắt đôi**: `LUẬT` thành heading, `DOANH NGHIỆP` rơi
xuống body.

**Bốn phương án đã cân nhắc:**

| | cách | phán quyết |
|---|---|---|
| A | Bỏ qua heading khớp danh sách quốc hiệu/tiêu ngữ, lấy heading kế | **Không đủ** — với `luat-doanhnghiep` cho ra `"LUẬT"`, vẫn vô nghĩa |
| B | Như A, **cộng thêm**: nếu heading còn lại là một từ loại văn bản trần (`LUẬT`, `BỘ LUẬT`, `NGHỊ ĐỊNH`, `THÔNG TƯ`) thì nối dòng body đầu tiên | **Chọn** — cho `"LUẬT DOANH NGHIỆP"`, tất định, không tốn LLM |
| C | Bảng ánh xạ tay `source_file → title` | **Loại làm cơ chế chính** — 18 tệp thì rẻ, nhưng ingest multi-format đã xong nên tài liệu tải lên tuỳ ý là kịch bản thật. Giữ làm đường đè tay cho ca cứng đầu |
| D | Cho LLM trích tên lúc ingest (18 lời gọi) | **Loại** — rẻ về quota nhưng không tất định, và phải chạy lại mỗi lần re-ingest |

**Điều quan trọng hơn cả việc chọn A/B/C/D:** heuristic nào rồi cũng sẽ sai ở một tài liệu
nào đó. Thứ KHÔNG được phép lặp lại là **sai một cách im lặng**. Nên bắt buộc kèm:

> **Cổng trùng tên**: khi một lượt nạp làm hai `doc_id` khác nhau mang cùng `doc_title`,
> phát một `Warning` của `ingest_report` (`path`, `where`, `reason`). Tệp vẫn `ingested` —
> đúng hợp đồng ba trạng thái ở `ingest_report.py`; nhưng chỗ đáng ngờ **được gọi tên**.

Cổng này rẻ, tất định, và nó — chứ không phải heuristic — mới là thứ đảm bảo lỗi hôm nay
không sống thêm 6 tuần nữa như lần trước.

## 7. Quyết định — thước đo cho câu hỏi tổng hợp

Bộ `retrieval` hiện tại chấm bằng "≥1 nhãn đúng lọt top-k". **Với câu tổng hợp thước đó
sai về bản chất**: câu "tóm tắt Luật Doanh nghiệp" thì việc lọt được 1 chunk đúng tài liệu
là chuyện hiển nhiên và vô nghĩa — cái thiếu là **ĐỘ PHỦ**.

Nên bộ mới đo hai đại lượng, **cả hai đều tất định, không cần LLM**:

- `doc_coverage` = |tài liệu mong đợi bị chạm| / |tài liệu mong đợi| — cho câu đếm/liệt kê
  trọn corpus ("liệt kê tất cả chính sách" phải chạm ĐỦ 7 tệp `.docx` nghiệp vụ).
- `section_coverage` = |node cấp 1 của tài liệu đích bị chạm| / |node cấp 1 của tài liệu đó|
  — cho câu tóm tắt một tài liệu ("tóm tắt Luật Doanh nghiệp" hiện chạm 1/… chương).

Neo nhãn theo **basename tệp** và **node cấp 1**, cùng quy ước với `retrieval_score.label_of()`
(chunk_id là bigserial, re-index đổi sạch).

Mốc nền dự kiến rất thấp — đó là điểm: **không sửa được thứ chưa đo được**, và mốc thấp là
thứ chứng minh bước 3–5 có tác dụng hay không.

## 8. Lộ trình — và vì sao chia hai plan

| bước | việc | tốn LLM? | plan |
|---|---|---|---|
| 1 | Bộ eval `aggregate` + hai thước độ phủ | **không** | A |
| 2 | Sửa `doc_title` (phương án B) + cổng trùng tên | **không** | A |
| 3a | `retrieve()` tính và trả tín hiệu độ phủ | **không** | A |
| 3b | Đưa tín hiệu độ phủ vào `RAG_SYNTHESIS_PROMPT` | **có** (A/B `synthesis_live`) | B |
| 4 | Luồng THỐNG KÊ: intent mới + node SQL trên `rag_documents` | ít (intent eval) | B |
| 5 | Rollup summary cấp Chương (440 node) + luồng TỔNG QUAN | **nhiều** (440 + eval) | B |

Kế hoạch A đã viết: `docs/superpowers/plans/2026-09-08-cau-hoi-tong-hop-do-va-nen.md`.

**Plan A = bước 1, 2, 3a.** Đó là một hệ con hoàn chỉnh: nó *đo được* lỗi, *sửa* lỗi tất
định đang chặn hai hướng sau, và *phơi* tín hiệu độ phủ — không đổi một bit hành vi trả lời,
nên không cần hạn mức LLM và không có rủi ro hồi quy trên đường đang chạy.

**Plan B = bước 3b, 4, 5**, viết SAU khi bước 1 cho mốc nền, vì:

- 3b đổi `RAG_SYNTHESIS_PROMPT`, và **đường này đã có tiền sự**: đợt `memory-synthesis-eval`
  (2026-08-20) đo được rằng thêm cả một fact vô hại vào prompt cũng phá hợp đồng guard
  (`refusal_acc` 1,0 → 0,9643) và ép định dạng làm `fact_acc` tụt 8,3%. Không đổi prompt mà
  không có A/B `synthesis_live`.
- 4 thêm intent mới vào `VALID_INTENTS`, tức chạm đúng chỗ `routing.py` bảo vệ bằng 3 bằng
  chứng. Cần eval `intent` riêng, và cần bước 2 xong trước (SQL đếm theo tên tài liệu).
- 5 là bước duy nhất tốn ngân sách thật, và **thiết kế của nó phụ thuộc con số bước 1 trả
  về**. Viết plan cho nó bây giờ là đoán.

## 9. Rủi ro đã biết, chưa đóng

- **`content_hash` không mang dấu vân tay của parser.** Re-ingest là NO-OP nếu không xoá
  `rag_documents` trước. Bước 2 đổi `doc_title` ⇒ **phải xoá và nạp lại corpus** thì giá trị
  mới mới vào DB. Bước 5 (nếu làm) còn nặng hơn: summary sẽ lệch corpus một cách im lặng
  nếu không xử lý chuyện này.
- **47 chunk có nội dung đúng `"1."`** còn nằm trong index (4 870 chunk / 4 785 nội dung
  phân biệt). Rác sót sau đợt P3a. Nhỏ, nhưng nó chiếm chỗ trong pool 20 và đã thấy lọt vào
  kết quả câu "liệt kê tất cả chính sách". **KHÔNG nằm trong phạm vi Plan A** — ghi ở đây để
  không ai tưởng đã xử lý.
- **8 chunk có `section_path` rỗng** — thước `section_coverage` phải xử lý được, không được
  chia cho 0.
- **Đo ở spec này chỉ tới tầng TRUY XUẤT.** Chưa chạy tầng sinh (tốn hạn mức), nên "câu trả
  lời cuối trông thế nào" là suy ra từ prompt + chunk, chưa phải đo. Bước 3b sẽ đo.
- **Chưa xác nhận router đưa câu `"có bao nhiêu…"` vào `rag`** chứ không lạc sang `erp_read`.
  Cần một lời gọi LLM thật; để bước 4.

## 10. Giả thuyết ĐÃ BỊ BÁC — đừng đề xuất lại

- ~~"Thêm một LLM nhỏ phân loại intent là việc mới"~~ — đã có `routing.py`, và LLM phân loại
  đứng một mình đã bị bác bằng 3 bằng chứng độc lập (mục 4.1a).
- ~~"Small-to-Big nên tóm tắt ở node lá"~~ — lá trung vị 258 token, nhỏ hơn một chunk. Tốn
  gấp 5 lần để mua gần như không gì (mục 4.1b).
- ~~"Cần thêm graph DB / đổi chunking để có phân cấp"~~ — cây đã materialize sẵn trong
  `section_path`, sâu 4 cấp, đã kiểm là thật (mục 4.2).
- ~~"Cần Elasticsearch để lọc theo tag"~~ — đã có `gin (ts_vector)` + Postgres; mà câu thống
  kê cần **SQL**, không cần text search.
- ~~"Query Understanding đa bước thay cho phân loại"~~ — đúng lý thuyết, không trả nổi theo
  ngân sách rpd hiện tại (mục 4.2).
- ~~"Nâng `TOP_K` lên cho câu tổng hợp là đủ"~~ — chưa thử, nhưng số đo mục 4.1b cho thấy
  giới hạn: tóm tắt trọn `Chương V › CÔNG TY CỔ PHẦN` cần 174 chunk / 51 393 token. Không
  phải bài toán nới `k`.
