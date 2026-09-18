# So sánh ba reranker trên corpus thật — thiết kế

**Ngày**: 2026-09-17. **Nhánh**: chưa tạo. **Trạng thái**: thiết kế, chưa viết code.

Quyết định của chủ dự án 2026-09-17: dừng dự án D:\Project (đang giữ Ollama thứ hai
`ollama:11434` có GPU passthrough với `qwen3:8b` 5,2 GB), dồn hạ tầng GPU cho Youdoo, và
**đo cả ba**: `BAAI/bge-reranker-v2-m3` (đang chạy), `Qwen/Qwen3-Reranker-0.6B`,
`Qwen/Qwen3-Reranker-4B`.

---

## 1. Vì sao đáng đo — số đã có

> **Cập nhật sau khi đo (review whole-branch)**: `recall@20 = 1,0` bên dưới là số CŨ, đo
> trên corpus 2026-08-20. Corpus đã đổi từ đó (chân bỏ dấu 2026-09-10, ingest đa định dạng);
> cả SÁU chân đo của lượt này (Task 4 + Task 5, không phân biệt model/chế độ hoà) đều đo ra
> `recall@20 = 0,9766` trên corpus HIỆN TẠI — xem sáu JSON trong
> `backend/evals/results/reranker-2026-09-17/`. Tức pool 20 ứng viên KHÔNG còn chứa chunk
> đúng cho 100% câu hỏi; có một khoảng hụt `1,0 − 0,9766 = 0,0234` mà không reranker nào sửa
> được — nó nằm ở TẦNG TRUY XUẤT (dense/pool), trước cả khi reranker được gọi. Luận điểm
> "nút thắt duy nhất còn lại là chọn/xếp hạng" của phần dưới đây do đó không còn tuyệt đối,
> nhưng vẫn đúng ĐỦ để đo: 0,9766 là trần của `recall@6` (xem §8 Task 6, R24) — dư địa còn
> lại cho reranker vẫn là phần lớn nhất.

- `recall@20 = 1,0` trên bộ `retrieval` 64 ca: chunk đúng **luôn** nằm trong pool. Nút thắt
  duy nhất còn lại là **chọn/xếp hạng** — đúng việc của reranker.
- Reranker hiện tại chấm theo **trùng mặt chữ** (spec 2026-08-20, `retrieve.py:rerank`):
  câu *"một bên tự ý dừng hợp đồng giữa chừng thì hậu quả là gì?"* đẩy `Điều 309/311. HẬU
  QUẢ pháp lý…` lên hạng 1–2 (điểm dương), còn đáp án đúng `Điều 428. Đơn phương chấm dứt`
  tụt −2,87 và văng khỏi top-6. Vì thế nó đang bị hạ xuống **một lá phiếu 1:1** với RRF —
  tỉ lệ ấy được chọn *vì* reranker yếu.
- Mốc hiện tại (hoà 1:1): `recall@6 0,9766` · `hard mrr 0,6758` · `trap mrr 0,8562` ·
  rerank ~21 ms/lượt trên GPU.

Cái chưa biết, và **không bảng xếp hạng nào trả lời được vì không cái nào đo tiếng Việt**:
reranker hiểu ngữ nghĩa hơn có cứu được nhóm `hard` trên luật Việt Nam không.

## 2. Ba ứng viên — khác nhau ở GIAO DIỆN chấm điểm, không phải ở kích thước

| model | kiến trúc | cách ra điểm | giấy phép | trọng số fp16 |
|---|---|---|---|---|
| `bge-reranker-v2-m3` | encoder (XLM-R large, 568M) | `AutoModelForSequenceClassification` → 1 logit | MIT | ~1,1 GB |
| `Qwen3-Reranker-0.6B` | decoder (Qwen3-0.6B) | `AutoModelForCausalLM` → logit `yes`/`no` ở token cuối | Apache 2.0 | ~1,2 GB |
| `Qwen3-Reranker-4B` | decoder (Qwen3-4B) | như trên | Apache 2.0 | **~8,0 GB** |

Hai model Qwen dùng chung MỘT đường chấm điểm mới. Đổi sang bất kỳ bản nào cũng phải viết
đường đó; chọn 0.6B không tiết kiệm được công. Đây là lý do đo cả hai cùng lượt.

## 3. Ràng buộc phần cứng, đo 2026-09-17

RTX 5060 Ti **8 151 MiB**, capability `(12, 0)` — Blackwell. `torch 2.11.0+cu128`,
`transformers 5.15.0`. **Không có `bitsandbytes`, không có `accelerate`.** RAM 32 GB.

Chỗ dùng thật của Youdoo chỉ **~1,8 GB** (bge-m3 664 MB trong `youdoo-ollama` + reranker fp16
~1,1 GB). Phần còn lại của 3 GB đang bận là desktop + trình duyệt (máy dev kiêm máy demo).

**Hệ quả cho 4B:** fp16 8,0 GB **không vừa** card 8,15 GB kể cả desktop sạch. Ba đường:

| | cách | phán quyết cho LƯỢT ĐO NÀY |
|---|---|---|
| A | `bitsandbytes` INT8/NF4 trên GPU | **Không** — chưa cài, chưa xác nhận kernel cho sm_120 trên Windows. Rủi ro cài đặt không liên quan tới câu hỏi đang đo. |
| B | `accelerate` `device_map="auto"`, fp16, phần thừa tràn sang CPU RAM | **Chọn** — `accelerate` thuần Python, không kernel; đo được **chất lượng fp16 thật**; chậm nhưng lượt đo chỉ 64 × 20 = 1 280 cặp. |
| C | GGUF Q4 qua llama.cpp `--reranking` | **Hoãn** — thêm một tiến trình, một giao diện khác; chỉ đáng nếu 4B thắng và cần triển khai. |

**Điều phải nói thẳng:** đường B đo **chất lượng ở fp16**, không phải chất lượng sau lượng
tử hoá; và **độ trễ của 4B ở lượt này KHÔNG đại diện** cho triển khai. Nếu 4B thắng, phải có
một cổng thứ hai: đo lại ở dạng lượng tử hoá (A hoặc C) trước khi thay production. Spec này
**không** hứa cổng đó — nó chỉ trả lời "có đáng đi tiếp không".

## 4. Thiết kế đo — một biến đổi, mọi thứ khác giữ nguyên

Giữ nguyên: corpus, `TOP_N = 20`, `TOP_K = 6`, `RERANK_MAX_LENGTH = 512`, phép hoà 1:1 trong
`retrieve.rerank()`, bộ `retrieval` 64 ca, embedding `bge-m3`.

**`RERANK_MAX_LENGTH = 512` KHÔNG phải một ngân sách nội dung NGANG NHAU giữa hai họ model**
(ghi lại từ review whole-branch). `bge` (seq_cls) đưa `[query, doc]` thẳng vào tokenizer —
gần như toàn bộ 512 token dành cho query+doc. Hai chân Qwen3 phải trừ vào cùng ngân sách đó:
~55 token cho prefix/suffix cố định của model card (`_QWEN3_PREFIX`/`_QWEN3_SUFFIX`) cộng
~20 token cho phần `<Instruct>: {instruction}` tiếng Anh — tức tài liệu của Qwen3 bị CẮT
NGẮN sớm hơn khoảng 75 token so với bge, ở CÙNG một giới hạn 512. Đây là điều kiện đo BẤT
LỢI cho Qwen3, không phải thuận lợi — nên khi Qwen3 (đặc biệt `qwen3-4b-override`, §8 Task 6)
vẫn thắng dưới bất lợi này, kết luận "4B đáng đi tiếp" càng ĐƯỢC CỦNG CỐ chứ không bị suy yếu.

Biến đổi duy nhất: `RERANK_MODEL`, hiện là **hằng** trong `config.py` → trở thành đọc từ
env với mặc định cũ (cùng mẫu với `RERANK_DEVICE`). Mỗi model = một tiến trình eval riêng,
vì `_load()` cache một lần cho cả tiến trình.

Bốn chân đo:

```
1. --no-rerank                              (đối chứng, đã có sẵn)
2. RERANK_MODEL=BAAI/bge-reranker-v2-m3     (mốc hiện tại, đo lại cùng ngày)
3. RERANK_MODEL=Qwen/Qwen3-Reranker-0.6B
4. RERANK_MODEL=Qwen/Qwen3-Reranker-4B  +  RERANK_DEVICE_MAP=auto
```

Chân 2 **phải đo lại** chứ không lấy số cũ: corpus đã đổi (4 870 chunk, thêm chân bỏ dấu
2026-09-10), số 0,6758 là của corpus 2026-08-20.

Chỉ số quyết định, theo thứ tự: **`hard mrr`** (câu hỏi đặt ra), `recall@6` (không được
tụt), `trap mrr` (cái giá của lần đổi trước), ms/lượt và VRAM đỉnh (chỉ so 0.6B với bge —
4B không so được ở lượt này, xem §3).

### 4.1 Đường chấm điểm Qwen3 — theo model card chính thức

```
prefix  = "<|im_start|>system\nJudge whether the Document meets the requirements based on
           the Query and the Instruct provided. Note that the answer can only be \"yes\"
           or \"no\".<|im_end|>\n<|im_start|>user\n"
suffix  = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
body    = "<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}"
score   = softmax(logits[-1][[no_id, yes_id]])[yes]
```

Bắt buộc **left padding** (`tokenizer.padding_side = "left"`) — nếu không, vị trí "token
cuối" của các cặp ngắn là pad, và điểm đọc ra là rác **mà không ném lỗi**. Đây là chỗ dễ sai
im lặng nhất của cả spec; test đơn vị phải gác nó.

Instruction để **mặc định tiếng Anh của model card** ở lượt này. Instruction tiếng Việt là
một nút riêng; đổi hai thứ cùng lúc thì không quy được kết quả.

### 4.2 Fail-open giữ nguyên

`score_pairs` trả `None` khi hỏng, `_state["model"] = False` không thử lại — hợp đồng cũ.
Đường Qwen3 sống **bên trong** cùng `try` đó. Một model Qwen tải hỏng giữa lượt eval phải
làm chân đó hiện ra là `method="dense-rrf"` chứ không phải điểm rác.

## 5. Điều CỐ Ý không làm ở lượt này

- **Không đổi production.** `RERANK_MODEL` mặc định vẫn là `bge-reranker-v2-m3` cho tới
  khi có bảng số và quyết định riêng.
- **Không đo lượng tử hoá.** Xem §3.
- **Không mở lại tỉ lệ hoà 1:1** trong cùng lượt — nhưng Kế hoạch có một task tuỳ chọn thêm
  công tắc `RAG_RERANK_MODE=override` để đo NGAY SAU khi biết model thắng, vì câu hỏi "1:1
  được chọn cho reranker yếu, còn đúng với reranker mạnh không" là câu hỏi mở ghi sẵn trong
  `retrieve.py`.
- **Không đổi instruction.** Xem §4.1.

## 6. Ràng buộc thứ tự với Kế hoạch A (câu hỏi tổng hợp)

Kế hoạch A Task 3 lấy **mốc nền** bộ `aggregate`. Mốc đó phải đo với reranker **đã chốt**.
Nên: lượt này xong và ra quyết định → rồi mới chạy Kế hoạch A. Trong lúc đo, production
không đổi, nên hai việc không giẫm nhau — miễn là không merge thay đổi `RERANK_MODEL` mặc
định vào `main` giữa chừng.

## 7. Rủi ro đã biết

- **Tải 4B ~8 GB** từ HF một lần; HF cache hiện 2,7 GB.
- **`accelerate` offload chậm** — ước 1–3 s/cặp trên CPU, 1 280 cặp ≈ 20–60 phút cho chân 4.
  Chấp nhận; chạy nền.
- **`_load()` trên đường `device_map`** không được gọi `.to(device)` nữa; input phải đi tới
  `model.device`. Trộn hai cách là lỗi "Expected all tensors to be on the same device" — và
  fail-open sẽ **nuốt** nó thành một chân eval `dense-rrf` trông như "model không hiệu quả".
  Đọc `method` trong kết quả của MỌI chân trước khi tin số.
- **Ollama thứ hai** vẫn có GPU passthrough dù D:\Project đã dừng. Trước khi đo, xác nhận
  `docker exec ollama ollama ps` rỗng.

## 8. Ghi chép thực thi

### Task 1

- **Khó khăn**: không có gì bất ngờ khi cài; tên tham số `dtype=` (không phải
  `torch_dtype=`) của `from_pretrained` được kiểm là đúng ở transformers 5.15.0
  (`modeling_utils.py:185`).
- **Hướng chọn**: hai đường chấm điểm tách riêng `_score_seq_cls`/`_score_qwen3`, chọn theo
  tên model; hai lỗi im lặng (mất suffix khi cắt ngắn, right padding) được gác bằng test với
  model giả.
- **Giới hạn còn lại**: nhánh `device_map` của `_instantiate` chưa có test ở Task 1; hai
  điểm nhỏ để lại: khối chuyển thiết bị lặp ở hai hàm chấm, prefix/suffix mã hoá lại mỗi
  lượt gọi.

### Task 2

- **Khó khăn**: venv của worktree là venv DÙNG CHUNG với cây chính và mang
  `torch==2.11.0+cu128`; một lần pip giải phụ thuộc chạm torch sẽ thay nó bằng bản CPU và
  làm reranker GPU chết lặng. Worktree ban đầu thiếu `.env` ở gốc nên suite nền ra 21 failed
  / 65 errors (conftest.py:26 nạp `.env` gốc repo); chép `.env` vào (bị gitignore) thì về
  đúng 2707 passed.
- **Hướng chọn**: cài `accelerate==1.15.0` kèm tệp ràng buộc ghim torch/transformers;
  dry-run trước chỉ thêm accelerate + psutil; kiểm lại in ra `2.11.0+cu128 5.15.0 1.15.0
  True`.
- **Giới hạn còn lại**: test device_map không kiểm `dtype=float16` hay `max_memory["cpu"]`.

### Task 3

- **Khó khăn**: bảng khói ba model — `bge-reranker-v2-m3` thứ tự `[2, 1, 3]` (18,1 ms/lượt,
  VRAM đỉnh 1097 MiB), `Qwen3-Reranker-0.6B` thứ tự `[1, 2, 3]` (106,1 ms/lượt, VRAM đỉnh
  1314 MiB), `Qwen3-Reranker-4B` thứ tự `[1, 2, 3]` (1782,5 ms/lượt, VRAM đỉnh 3050 MiB).
  `bge` xếp bẫy Điều 309 trên đáp án đúng Điều 428 ngay trên ca ví dụ của §1. 4B ở ngân sách
  mặc định `RERANK_GPU_BUDGET=5GiB` SEGFAULT (exit 139) khi VRAM trống lúc đó chỉ ~3040 MiB;
  segfault đi vòng qua fail-open `except Exception` của `score_pairs` — không có traceback
  Python, tiến trình chết thẳng. VRAM trống dao động 3040–6301 MiB trong suốt lượt đo do các
  ứng dụng desktop (trình duyệt, VS Code, Docker Desktop, một game) không liên quan tới tác
  vụ này.
- **Hướng chọn**: chạy lại 4B với `RERANK_GPU_BUDGET=3GiB` — thành công, không sửa code
  (đây là ca hết bộ nhớ đã có sẵn đường lùi trong brief, không phải lỗi trong
  `reranker.py`).
- **Giới hạn còn lại**: số đo của 4B là `device_map=auto` + offload một phần sang CPU nên
  KHÔNG so ngang VRAM/ms được với bge/0.6B (chạy toàn GPU); "nạp + lượt 1" gồm cả thời gian
  tải trọng số lần đầu (0.6B 179082 ms ≈ 97% là tải, không phải chi phí suy luận); đây là
  phép thử định tính 3 cặp, không phải số đo chất lượng — bảng chỉ số quyết định thật
  (`hard mrr`, `recall@6`, `trap mrr`) còn chờ Task 4.

### Task 4

**Bảng bốn chân (bộ `retrieval`, 64 ca, cùng corpus):**

| chân       |    r@6 |    mrr |   easy |   hard |   trap | p50ms |
|------------|-------:|-------:|-------:|-------:|-------:|------:|
| no-rerank  | 0.8958 | 0.7072 | 0.7673 | 0.5403 | 0.7682 |   593 |
| bge-v2-m3  | 0.9688 | 0.8091 | 0.8968 | 0.5755 | 0.8875 |   954 |
| qwen3-0.6b | 0.9479 | 0.7974 | 0.8807 | 0.6196 | 0.8250 |  2088 |
| qwen3-4b   | 0.9688 | 0.8317 | 0.8836 | 0.6814 | 0.8906 |  4590 |

**Đối đầu từng ca trên nhóm `hard` (n=17), reciprocal_rank:**

| câu hỏi | bge | 0.6B | 4B |
|---|---:|---:|---:|
| nhà cung cấp giao trễ thì bị xử lý ra sao? | 0.500 | 0.500 | 0.500 |
| khách nợ quá hạn mức thì làm gì? | 1.000 | 0.500 | 0.500 |
| mua nhiều thì có được giảm thêm không? | 0.250 | 0.500 | 0.500 |
| kho báo thiếu hàng khi soạn đơn thì xử lý thế nào? | 1.000 | 1.000 | 1.000 |
| khách đổi ý sau khi đã chốt đơn thì sao? | 1.000 | 1.000 | 1.000 |
| hàng về kho có khớp với đơn đặt mua không thì ai kiểm? | 0.167 | 0.500 | 0.500 |
| bên bán phải đóng gói hàng ra sao trước khi chuyển đi? | 0.250 | 0.167 | 0.333 |
| công ty muốn cho nhân viên nghỉ việc thì cần căn cứ gì? | 0.333 | 0.500 | 0.500 |
| làm ca đêm thì được trả thêm bao nhiêu phần trăm? | 1.000 | 1.000 | 1.000 |
| bảo hiểm xã hội bắt buộc thì người lao động đóng bao nhiêu? | 0.333 | 0.333 | 1.000 |
| bên mua chưa trả tiền đúng hẹn thì luật thương mại nói gì? | 0.200 | 0.200 | 0.250 |
| hai bên ký hợp đồng giả để che giấu giao dịch khác thì hợp đồng có hiệu lực không? | 1.000 | 1.000 | 1.000 |
| một bên tự ý dừng hợp đồng giữa chừng thì hậu quả là gì? | 0.250 | 0.333 | 0.500 |
| ai là người được ký hợp đồng thay mặt cho công ty? | 0.000 | 0.000 | 0.000 |
| nộp thuế trễ thì bị tính tiền phạt ra sao? | 0.500 | 1.000 | 1.000 |
| khi nào thì xác định được thời điểm tính thuế GTGT? | 1.000 | 1.000 | 1.000 |
| nhà đầu tư nước ngoài muốn góp vốn mua cổ phần thì theo hình thức nào? | 1.000 | 1.000 | 1.000 |

- 0.6B thắng bge trên 5 ca: "mua nhiều thì có được giảm thêm không?", "hàng về kho có khớp
  với đơn đặt mua không thì ai kiểm?", "công ty muốn cho nhân viên nghỉ việc thì cần căn cứ
  gì?", "một bên tự ý dừng hợp đồng giữa chừng thì hậu quả là gì?", "nộp thuế trễ thì bị
  tính tiền phạt ra sao?". 0.6B thua bge trên 2 ca: "khách nợ quá hạn mức thì làm gì?", "bên
  bán phải đóng gói hàng ra sao trước khi chuyển đi?".
- 4B thắng bge trên 8 ca (5 ca trên của 0.6B, cộng "bên bán phải đóng gói hàng ra sao trước
  khi chuyển đi?", "bảo hiểm xã hội bắt buộc thì người lao động đóng bao nhiêu?", "bên mua
  chưa trả tiền đúng hẹn thì luật thương mại nói gì?"). 4B thua bge trên 1 ca duy nhất:
  "khách nợ quá hạn mức thì làm gì?".
- **Văng khỏi top-6 (`recall_at_final = 0`) trên `hard`**: cả ba chân có rerank (bge, 0.6B,
  4B) đều văng ĐÚNG MỘT ca giống nhau — "ai là người được ký hợp đồng thay mặt cho công
  ty?" — không chân Qwen nào văng thêm ca nào mà bge còn giữ được. `no-rerank` văng tới 3 ca
  (thêm "hàng về kho có khớp với đơn đặt mua không thì ai kiểm?" và "bên mua chưa trả tiền
  đúng hẹn thì luật thương mại nói gì?").
- **Văng khỏi top-6 trên `trap` (n=16)**: cả ba chân có rerank đều KHÔNG văng ca nào
  (0/16). Chỉ `no-rerank` văng 1 ca ("hàng hoá nhập khẩu có thuộc đối tượng chịu thuế giá
  trị gia tăng không?").
- **Khó khăn**: lượt đo này bị tạm dừng và tiếp tục hai lần để trả GPU cho chủ dự án — chân
  1–2 (no-rerank, bge) chạy trước, dừng giữa chân 3 (0.6B); tiếp tục xong chân 3, dừng giữa
  chân 4 (4B, dừng agent kéo theo tắt luôn tiến trình nền không để lại traceback); tiếp tục
  lần hai chạy trọn chân 4. Cả bốn chân cùng corpus, chân 1–3 đo ngày 2026-09-17, chân 4 đo
  ngày 2026-09-18 — không có ingest hay thay đổi corpus xen giữa các lần dừng.
- **Hướng chọn**: chân 4 dùng `RERANK_GPU_BUDGET=3GiB` ngay từ lần thử đầu của lượt tiếp tục
  này và THÀNH CÔNG không cần lùi xuống 2GiB/1GiB — khớp với quan sát Task 3 rằng 3GiB là
  ngân sách ổn định cho 4B trên GPU 8GB này.
- **Giới hạn còn lại**: `p50ms` của `qwen3-4b` (4590 ms) đi qua đường `device_map=auto` với
  một phần lớp offload sang CPU — đây KHÔNG phải độ trễ đại diện cho triển khai thật (một
  4B chạy trọn GPU hoặc lượng tử hoá sẽ nhanh hơn nhiều); con số này chỉ dùng để so chất
  lượng (r@6/mrr/hard/trap), không dùng để so tốc độ triển khai. Việc chọn chân nào để dùng
  thật (adopt/keep) là quyết định của một mục việc sau, không phải mục này.

### Task 5

Công tắc `RAG_RERANK_MODE` ∈ {`blend` (mặc định, hoà 1:1 với RRF — hành vi cũ), `override`
(xếp thuần theo điểm cross-encoder)}, đọc mỗi lượt gọi `rerank()`, giá trị lạ lùi về `blend`
không ném. Đo `override` cho cả hai model Qwen3 (không chỉ model thắng — 4B còn phải qua một
cổng lượng tử hoá riêng mới biết có triển khai được không, xem §3).

**Bảng sáu chân (bộ `retrieval`, 64 ca, cùng corpus; bốn dòng đầu lặp lại Task 4):**

| chân           |    r@6 |    mrr |   easy |   hard |   trap | p50ms |
|----------------|-------:|-------:|-------:|-------:|-------:|------:|
| no-rerank      | 0.8958 | 0.7072 | 0.7673 | 0.5403 | 0.7682 |   593 |
| bge-v2-m3      | 0.9688 | 0.8091 | 0.8968 | 0.5755 | 0.8875 |   954 |
| qwen3-0.6b     | 0.9479 | 0.7974 | 0.8807 | 0.6196 | 0.8250 |  2088 |
| qwen3-4b       | 0.9688 | 0.8317 | 0.8836 | 0.6814 | 0.8906 |  4590 |
| qwen3-0.6b-ov  | 0.9609 | 0.8421 | 0.9258 | 0.7173 | 0.8125 |  1026 |
| qwen3-4b-ov    | 0.9766 | 0.8977 | 0.9382 | 0.8255 | 0.8958 |  4591 |

(`-ov` = `RAG_RERANK_MODE=override`, cùng `RERANK_MODEL` với dòng blend tương ứng.)

**Override so với blend của CHÍNH model đó:**

- `qwen3-0.6b`: `hard mrr` 0,6196 → 0,7173 (+0,0977), `recall@6` 0,9479 → 0,9609 (+0,0130),
  `trap mrr` 0,8250 → 0,8125 (−0,0125 — cái giá duy nhất đo được ở chân này).
- `qwen3-4b`: `hard mrr` 0,6814 → 0,8255 (+0,1441 — mức tăng lớn nhất trong cả bảng),
  `recall@6` 0,9688 → 0,9766 (+0,0078), `trap mrr` 0,8906 → 0,8958 (+0,0052 — không giảm).
- Cả hai chân override đều THẮNG chân blend cùng model trên cả ba chỉ số quyết định
  (`hard mrr`, `recall@6`, và không tệ đi ở `trap`) — ngược hẳn với bge cũ, nơi override thua
  cả tắt-hẳn (xem docstring `rerank()`, đo 2026-08-20). `p50ms` gần như không đổi giữa blend
  và override CÙNG model (0.6b: 2088→1026 — chênh lệch này là nhiễu đo giữa hai tiến trình
  chứ không phải chi phí phép hoà, vì đổi `order` chỉ là sắp xếp lại chỉ số, không gọi thêm
  cross-encoder; 4b: 4590→4591, đúng như dự kiến).

**Câu hỏi văng khỏi top-6 (`recall_at_final = 0`) — soát CẢ BA mức khó, không chỉ hard/trap:**

- `qwen3-0.6b`: override làm VĂNG 1 câu mà blend còn giữ — "bên bán phải đóng gói hàng ra sao
  trước khi chuyển đi?" (`hard`, blend giữ được recall_at_final=1,0, override=0,0). Ngược lại,
  override CỨU 2 câu mà blend đã văng, cả hai đều `easy`: "quy trình giao hàng gồm những bước
  nào?" và "dự án nào phải xin chấp thuận chủ trương đầu tư?". Không có câu `trap` nào đổi ở
  chân này theo hướng nào.
- `qwen3-4b`: override KHÔNG làm văng câu nào mà blend còn giữ (0 câu, ở cả ba mức khó).
  Override cứu 1 câu blend đã văng: "quy trình giao hàng gồm những bước nào?" (`easy`, cùng
  câu mà 0.6b cũng cứu được).
- Tức là ở `qwen3-4b`, đổi sang override không có mặt trái nào đo được trên tập 64 ca này;
  ở `qwen3-0.6b` có đúng một câu `hard` bị đổi hướng xấu, bù lại bằng hai câu `easy` được cứu
  — không phải một chiều thắng tuyệt đối.

- **Khó khăn**: bảng Task 4 đã có sẵn nên chân 5–6 chỉ cần một biến môi trường thêm
  (`RAG_RERANK_MODE=override`), không có bất ngờ hạ tầng; GPU rảnh đủ (6,6 GB free lúc dispatch)
  nên không phải lặp lại kịch bản hạ `RERANK_GPU_BUDGET` của Task 3/4 cho chân 4B.
- **Hướng chọn**: đo override cho CẢ HAI model Qwen thay vì chỉ "model thắng" (phán quyết
  R19) — vì 4B còn một cổng lượng tử hoá riêng mới biết có triển khai được, nên 0.6B vẫn là
  ứng viên sống nếu 4B rớt ở cổng đó; giữ nguyên default `RRF_K`, `TOP_N`, `TOP_K`, corpus,
  không đổi gì khác ngoài đúng công tắc đang đo (spec §4).
  Đi ĐÚNG bài học 2026-08-20: không dừng ở mrr trung bình, soát từng câu văng khỏi top-6 trên
  CẢ BA mức khó (không chỉ hard/trap) trước khi kết luận override "tốt hơn".
- **Giới hạn còn lại**: đây vẫn là đo CHẤT LƯỢNG, không phải quyết định triển khai — `qwen3-4b`
  còn nợ cổng lượng tử hoá (§3) trước khi so được tốc độ thật; công tắc `RAG_RERANK_MODE` mặc
  định vẫn là `blend`, chưa đổi production. Việc có chuyển default sang `override` hay không,
  và chọn model nào, là quyết định của một mục việc sau — mục này không kết luận adopt/keep.

### Task 6 — Kết luận

Áp thứ tự cổng của spec §4 (**`hard mrr`** trước, rồi `recall@6` không được tụt, rồi
`trap mrr`) lên bảng sáu chân đầy đủ (Task 4 + Task 5, cùng bộ `retrieval` 64 ca, cùng
corpus, `errors = 0` và `methods_seen` đúng trên cả sáu chân):

| chân                          |    r@6 |    mrr |   easy |   hard |   trap | p50ms |
|-------------------------------|-------:|-------:|-------:|-------:|-------:|------:|
| no-rerank                     | 0.8958 | 0.7072 | 0.7673 | 0.5403 | 0.7682 |   593 |
| bge-v2-m3 (production, blend) | 0.9688 | 0.8091 | 0.8968 | 0.5755 | 0.8875 |   954 |
| qwen3-0.6b blend               | 0.9479 | 0.7974 | 0.8807 | 0.6196 | 0.8250 |  2088 |
| qwen3-4b blend                 | 0.9688 | 0.8317 | 0.8836 | 0.6814 | 0.8906 |  4590 |
| qwen3-0.6b override             | 0.9609 | 0.8421 | 0.9258 | 0.7173 | 0.8125 |  1026 |
| qwen3-4b override               | 0.9766 | 0.8977 | 0.9382 | 0.8255 | 0.8958 |  4591 |

**`qwen3-0.6b-override` — thắng `hard mrr` (0,5755 → 0,7173) nhưng RỚT ở cổng 2.** `recall@6`
tụt 0,9688 → 0,9609 VÀ `trap mrr` tụt 0,8875 → 0,8125 — cả hai chỉ số "không được tụt" cùng
tụt. Cụ thể hơn con số trung bình: chân này văng khỏi top-6 đúng một câu `hard` mà bge
production còn giữ nguyên — *"bên bán phải đóng gói hàng ra sao trước khi chuyển đi?"*
(`recall_at_final`: bge/blend = 1,0 → 0.6b-override = 0,0). Thắng `hard` không đủ khi cái giá
là mất một câu đang trả lời đúng. **⇒ 0.6B override KHÔNG được nhận.**

**`qwen3-4b-override` — qua cả ba cổng, không làm rớt câu nào production đang giữ.**
`hard mrr` 0,5755 → 0,8255 (mức tăng lớn nhất bảng), `recall@6` 0,9688 → 0,9766 (tăng, không
tụt), `trap mrr` 0,8875 → 0,8958 (tăng, không tụt). Soát từng câu (Task 5): 0 câu bị văng khỏi
top-6 ở bất kỳ mức khó nào so với bge/blend — chân này chỉ CỨU thêm, không mất gì đo được trên
64 ca. Đây là chân tốt nhất trên dữ liệu.

**Ruling R24 (kiểm chứng độc lập, review whole-branch): `qwen3-4b-override` đạt `recall@6 =
0,9766`, ĐÚNG BẰNG `recall@20 = 0,9766` của corpus này (§1, sáu chân đều đo ra cùng số).**
Tức trên bộ 64 ca này, chân tốt nhất đã đóng HẾT khoảng cách chọn/xếp hạng: không reranker
nào — dù mạnh đến đâu — có thể đẩy `recall@6` lên cao hơn `recall@6 = 0,9766` này, vì đó là
TRẦN của chính pool 20 ứng viên (chunk đúng vắng mặt trong pool ở 0,0234 số ca còn lại, một
vấn đề của tầng truy xuất trước reranker, không phải của xếp hạng). Hệ quả trực tiếp: cổng
lượng tử hoá đang treo cho 4B (§3, §5 giới hạn còn lại) từ nay là một câu hỏi về ĐỘ TRỄ và về
việc lượng tử hoá có làm hỏng `trap mrr`/`mrr` hay không — KHÔNG còn là câu hỏi về `recall@6`,
vì recall đã chạm trần trên tập đo này.

**Nhưng con số của 4B không phải số triển khai được.** Chân `qwen3-4b` (cả blend lẫn
override) chạy qua đường `device_map=auto` của `accelerate`, offload một phần lớp sang CPU
RAM (§3, đường B) — vì trọng số fp16 ~8,0 GB không vừa card 8 151 MiB kể cả khi desktop sạch.
`p50ms = 4591` là độ trễ CPU-offload, không phải độ trễ chạy trọn GPU hay chạy lượng tử hoá;
so nó với `954 ms` của bge production là so sai đường.

**⇒ Kết luận nêu tên: "4B đáng đi tiếp" (lựa chọn thứ ba trong ba lựa chọn của spec §4),
CÓ ĐIỀU KIỆN qua một cổng thứ hai chưa chạy** — đo lại `qwen3-4b` ở dạng lượng tử hoá
(`bitsandbytes` trên sm_120, hoặc GGUF Q4 qua `llama.cpp --reranking`, xem spec §3 đường A/C)
để biết chất lượng và độ trễ SAU lượng tử hoá, trước khi nó được phép thay production. Cho
tới khi cổng đó chạy và qua, **production giữ nguyên** `RERANK_MODEL=BAAI/bge-reranker-v2-m3`
mặc định và `RAG_RERANK_MODE=blend` mặc định — không đổi gì trong nhánh này.

**Phát hiện tách rời được: override thắng blend độc lập với việc chọn model, và là hiệu ứng
đơn lẻ lớn nhất trong cả bảng.** Trên CÙNG một model, đổi `blend` → `override` một mình đã
kéo `hard mrr` lên: 0.6B +0,0977 (0,6196→0,7173), 4B +0,1441 (0,6814→0,8255, mức tăng lớn nhất
bảng) — lớn hơn cả khoảng cách giữa hai model ở cùng chế độ hoà. **Nhưng phát hiện này KHÔNG
được đem ra dùng một mình trên `bge` hiện tại**: không chân `bge` + `override` nào từng được
đo trong lượt này (Task 4/5 chỉ đo override trên hai model Qwen), và phép đo 2026-08-20 —
chính phép đo đã chọn ra tỉ lệ hoà 1:1 đang chạy production — từng đo `override` trên `bge`
**thua cả tắt-hẳn reranker** (docstring `retrieve.rerank()`; nguyên nhân: `bge` chấm theo
trùng mặt chữ, thấy 2 điều luật có tên gần giống là chấm điểm dương sai hướng — xem spec §1).
Đem override đi thẳng lên bge sản xuất mà không đo lại sẽ lặp lại chính xác sai lầm đó.

**Ba khoản rủi ro/mất mát đo được, không được để thất lạc:**

1. **Override tách rời khỏi việc chọn model, và KHÔNG được ship một mình trên bge chưa đo**
   — chi tiết ở đoạn trên; đây là phát hiện độc lập, chờ một lượt đo `bge` + `override` riêng
   trước khi cân nhắc bật `override` cho bất kỳ model nào production đang chạy.
2. **`qwen3-0.6b` ở chế độ `blend` cũng văng một câu `easy` mà bge giữ được** —
   *"dự án nào phải xin chấp thuận chủ trương đầu tư?"* — điều này KHÔNG có trong Task 4 vì
   Task 4 chỉ soát văng-khỏi-top-6 ở `hard`/`trap`, chưa soát `easy`. Ghi lại ở đây để không
   mất dấu: bất kỳ ai cân nhắc 0.6B (kể cả nếu 4B rớt cổng lượng tử hoá) phải biết cái giá này.
3. **Chế độ hỏng của 4B không có đường lùi cấp tiến trình.** Ở `RERANK_GPU_BUDGET=5GiB`, việc
   nạp 4B SEGFAULT (exit 139, Task 3) — một segfault đi vòng qua hẳn khối `except Exception`
   mà `score_pairs` dùng để fail-open. Không có traceback Python, không có "chân đó hiện ra là
   `dense-rrf`" như hợp đồng cũ hứa (spec §4.2) — tiến trình backend chết thẳng. Bất kỳ ai
   triển khai 4B (kể cả sau khi lượng tử hoá) phải tính lại ngân sách VRAM này ở tầng giám sát
   tiến trình, không thể trông chờ fail-open trong Python.

- **Khó khăn**: mục này không đo gì — rủi ro chính là DIỄN GIẢI LẠI dữ liệu Task 4/5 thay vì
  chép đúng phán quyết đã có (R21); đối chiếu từng con số trong bảng với chính văn bản Task 4/5
  ở trên để không lệch số khi gõ lại.
- **Hướng chọn**: chép nguyên phán quyết của controller, không tự suy luận lại; giữ đúng thứ
  tự cổng của spec §4 khi trình bày lý do loại 0.6B override, thay vì chỉ nói "recall tụt" mà
  không trỏ tới câu `hard` cụ thể bị văng.
- **Giới hạn còn lại**: cổng lượng tử hoá cho 4B (§3 đường A/C) và lượt đo `bge` + `override`
  đều CHƯA chạy trong nhánh này — cả hai chặn quyết định adopt/keep cuối cùng; 5 khoản vá nhỏ
  hoãn lại từ review Task 1–5 (khối chuyển thiết bị lặp, prefix/suffix mã hoá lại mỗi lượt,
  test `device_map` thiếu hai khẳng định, số 4B không so ngang được, thời gian "nạp + lượt 1"
  lẫn thời gian tải) còn chờ soát trước khi merge — xem `docs/trang-thai-chung.md`.
