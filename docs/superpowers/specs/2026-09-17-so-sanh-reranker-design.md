# So sánh ba reranker trên corpus thật — thiết kế

**Ngày**: 2026-09-17. **Nhánh**: chưa tạo. **Trạng thái**: thiết kế, chưa viết code.

Quyết định của chủ dự án 2026-09-17: dừng dự án D:\Project (đang giữ Ollama thứ hai
`ollama:11434` có GPU passthrough với `qwen3:8b` 5,2 GB), dồn hạ tầng GPU cho Youdoo, và
**đo cả ba**: `BAAI/bge-reranker-v2-m3` (đang chạy), `Qwen/Qwen3-Reranker-0.6B`,
`Qwen/Qwen3-Reranker-4B`.

---

## 1. Vì sao đáng đo — số đã có

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
