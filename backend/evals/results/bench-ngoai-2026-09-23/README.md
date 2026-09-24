# Benchmark retriever + reranker trên dataset NGOÀI (2026-09-23)

> ⚠️ **Số tuyệt đối ở đây đo trên mã CHƯA có khoá phá hoà** (trước `a2b07be`).
> `ORDER BY score DESC LIMIT` dùng top-N heapsort — không ổn định — nên khi hoà
> điểm, hàng nào lọt vào pool là tuỳ ý; chính bảng dưới ghi 117/200 câu TVPL hoà
> `ts_rank`. **Pool cache của lượt này không tái lập được bằng mã hôm nay**;
> nó được giữ nguyên ở `bench-cache/*-pools.PRE-TIEBREAK-20260923.json`.
>
> Đo lại hai chân trên mã đã tất định: [`../bench-ngoai-2026-09-24-tiebreak/`](../bench-ngoai-2026-09-24-tiebreak/README.md)
> — r@20 TVPL 0,9150 → 0,9193, Zalo 0,9277 → 0,9365, không hồi quy ở chân nào.
>
> Kết luận **tương đối** của Pha A (bge thắng Qwen3-0.6B; override thắng blend)
> **KHÔNG bị ảnh hưởng**: mọi chân chấm trên cùng một pool, nên chênh lệch giữa
> chúng không phụ thuộc pool ấy được dựng ra sao.

Mã: `evals/bench_ngoai.py`, `evals/bench_ngoai_legs.sh`, test `tests/evals/test_bench_ngoai.py`.

## Dữ liệu

| bộ | nguồn (Hugging Face) | license | corpus | câu đo | qrels |
|---|---|---|---:|---:|---|
| `tvpl` | `GreenNode/TVPL-Retrieval-VN` | CC-BY-SA-4.0 | 10.576 đoạn → 18.731 chunk | 1.000 (mẫu seed 20260923 từ 9.985) | 1–8 đoạn đúng/câu |
| `zalo` | `GreenNode/zalo-ai-legal-text-retrieval-vn` (gốc Zalo AI Challenge 2021 Legal Text Retrieval) | MIT | 61.425 Điều luật → 140.948 chunk | 788 (mọi câu test có qrels) | 1–2 Điều đúng/câu |

Ghi nguồn: TVPL-Retrieval-VN và Zalo AI Legal Text Retrieval qua bộ sưu tập VN-MTEB của GreenNode.
Dữ liệu thô nằm ở `evals/external-data/` (gitignore). TVPL chỉ có parquet — đã đổi sang jsonl cạnh
tệp gốc bằng một venv tạm có `pyarrow` (không thêm dependency vào venv dự án).

357 Điều của Zalo có `text` rỗng (nội dung nằm trong tiêu đề) → bộ cắt không sinh chunk, giống
hành vi ingest thật. Không Điều nào trong số đó là đáp án của câu nào; corpus chỉ mất 0,6% distractor.

## Cách đo — đo hệ thống thật, không đo bản sao

- **Nạp**: mỗi passage đi qua CHÍNH `_split_section_text` (400 token, overlap 60), `title` →
  `section_path`, embed/`ts_vector`/`ts_vector_fold` qua đúng biến đổi của `ingest._ingest_known`.
  43% passage Zalo và 34% passage TVPL dài hơn 512 token — nạp nguyên passage sẽ đo một hệ không tồn
  tại. `doc_id = corpus-id`: một câu **trúng** khi bất kỳ chunk nào của passage đúng lọt top-k.
  Schema riêng `bench_tvpl`, `bench_zalo`; không đụng `public`.
- **Pool (pha A)**: `retrieve()` thật với `k=TOP_N`, rerank tắt, `visibility=UNRESTRICTED` → 20 ứng
  viên theo thứ tự RRF, dựng MỘT lần, lưu cache. Mọi chân rerank chấm trên đúng pool đó ⇒ chênh lệch
  chỉ đến từ reranker/chế độ. Mỗi chân một tiến trình.
- **Chỉ số**: `recall@20` (pool), `recall@6` (top-k production), MRR, nDCG@10 (chunk trùng passage chỉ
  tính lần đầu). Kiểm định ghép cặp `evals/retrieval_stats.py` (nhãn exact/MC in kèm).
- **Cổng hợp lệ**: `errors = 0` (reranker không fail-open lần nào) và cổng R12 — `recall@6` nửa SAU
  theo thứ tự chạy của mỗi chân có reranker ≥ chân tắt rerank. **Mọi chân đều đạt cả hai.**

## Pha A — reranker

| bộ | chân | n | errors | r@20 | r@6 | MRR | nDCG@10 | p50 rerank ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| tvpl | no-rerank | 1000 | 0 | 0,9150 | 0,8298 | 0,6868 | 0,7217 | — |
| tvpl | **bge-blend** (production) | 1000 | 0 | 0,9150 | 0,8777 | 0,7709 | 0,7955 | 233 |
| tvpl | **bge-override** | 1000 | 0 | 0,9150 | **0,8898** | **0,8091** | **0,8256** | 232 |
| tvpl | qwen06-blend | 1000 | 0 | 0,9150 | 0,8753 | 0,7588 | 0,7852 | 843 |
| tvpl | qwen06-override | 1000 | 0 | 0,9150 | 0,8838 | 0,7867 | 0,8059 | 806 |
| zalo | no-rerank | 788 | 0 | 0,9277 | 0,8617 | 0,6836 | 0,7343 | — |
| zalo | **bge-blend** (production) | 788 | 0 | 0,9277 | 0,9067 | 0,7523 | 0,7933 | 189 |
| zalo | **bge-override** | 788 | 0 | 0,9277 | **0,9093** | **0,7980** | **0,8278** | 189 |
| zalo | qwen06-blend | 788 | 0 | 0,9277 | 0,9042 | 0,7391 | 0,7832 | 690 |
| zalo | qwen06-override | 788 | 0 | 0,9277 | 0,8972 | 0,7376 | 0,7802 | 708 |

`p50` đo trong lúc GPU bị chia với lượt nạp/embedding song song — chỉ đọc tương đối.

Kiểm định ghép cặp (chênh TB, CI95 bootstrap, p hoán vị; thắng/hoà/thua):

| phép so | bộ | MRR | recall@6 |
|---|---|---|---|
| bge-blend vs no-rerank | tvpl | +0,084 [+0,072;+0,096] p<0,0001, 274/705/21 | — |
| | zalo | +0,069 [+0,054;+0,084] p<0,0001, 208/539/41 | +0,045 p<0,0001, 38/748/2 |
| **bge-override vs bge-blend** | tvpl | **+0,038 [+0,025;+0,051] p<0,0001**, 169/762/69 | +0,012 [+0,002;+0,023] p=0,023, 27/961/12 |
| | zalo | **+0,046 [+0,028;+0,064] p<0,0001**, 154/549/85 | +0,0025 [−0,006;+0,011] p=0,77 (exact), 7/776/5 |
| qwen06-blend vs bge-blend | tvpl | −0,012 [−0,021;−0,003] p=0,007 | −0,002 p=0,61 (exact) |
| | zalo | −0,013 [−0,025;−0,001] p=0,032 | −0,0025 p=0,69 (exact) |
| qwen06-override vs bge-override | tvpl | −0,022 [−0,036;−0,009] p=0,001 | −0,006 p=0,21 (exact) |
| | zalo | **−0,060 [−0,078;−0,043] p<0,0001** | −0,012 [−0,023;−0,002] p=0,031 (exact) |

### Kết luận pha A

1. **Qwen3-Reranker-0.6B KHÔNG thay được bge-reranker-v2-m3.** Cùng chế độ thì thua ở cả hai bộ
   (MRR −0,012 … −0,060), recall@6 hoà hoặc thua, chậm ~3,5 lần. Điều này **đảo** ấn tượng từ bộ nội
   bộ 109 ca (0.6B-override +0,107 so bge-blend trên hard-62): phần lợi đó là của **chế độ override**,
   không của model — khi cùng override, bge hơn. Lưu ý thiên lệch còn lại: `RERANK_MAX_LENGTH=512` làm
   Qwen3 thiệt ~75 token cho prompt; và họ bge có thể đã gặp dữ liệu pháp luật tiếng Việt khi huấn luyện
   (chưa kiểm được).
2. **Override > blend với bge — nhưng chỉ ở THỨ TỰ bên trong top-6.** MRR +0,038/+0,046 với p<0,0001
   trên CẢ HAI bộ; recall@6 không tụt (TVPL +0,012 p=0,023; Zalo +0,0025 không ý nghĩa). Vẫn có câu
   recall@6 giảm (TVPL 12, trong đó 9 văng hẳn khỏi top-6; Zalo 5, cả 5 văng hẳn) nhưng số câu tăng
   nhiều hơn (27, 7). Lý do chọn blend ngày
   2026-08-20 (override trên bge THUA cả tắt rerank, bộ 64 ca, corpus cũ) không tái lập ở đây.
3. **Chỗ mất lớn nhất nằm TRƯỚC reranker**: 7–8,5% đáp án không vào pool 20 (r@20 0,915/0,928);
   reranker tốt nhất đạt r@6 0,890/0,909 trên trần 0,915/0,928.
4. 4B chưa đo trên bộ ngoài (cần `device_map` tràn CPU, ~2 giờ/chân). Từ đợt dọn
   Docker 2026-09-23, `Qwen/Qwen3-Reranker-4B` đã bị **xoá khỏi cache HF** — đo
   lại sẽ tải về ~7,5 GB trước khi chạy. `bge-reranker-v2-m3` (mặc định
   production) và `Qwen3-Reranker-0.6B` vẫn còn trong cache.

## Pha B — vai (nhãn GIẢ LẬP)

Vai trong Youdoo chạm RAG ở đúng một chỗ: cột `visibility` (lọc SQL) + lượt bóng `hidden_classes`.
Nhãn là thuộc tính TÀI LIỆU nên gán cho passage bằng bộ từ khoá `evals/vlegal_bench_roles.py`
(chạm miền kế toán/bán hàng → `commercial`, còn lại `all`); câu hỏi mang lớp của passage đáp án.
`retrieve()` đầu-cuối, cấu hình production (bge-blend), `rag_visibility` lấy từ `src/agents/roles.py`.

Mật độ `commercial`: TVPL 23,8% passage / 27,4% chunk; Zalo 27,8% passage / **40,0% chunk** — so với
production 4 tệp / ~4.870 chunk. **Đây là stress test cơ chế, không phải dự báo con số production.**

| bộ | vai | lớp đáp án | n | r@6 | báo "bị chặn" | từ chối oan (đã tìm đúng) | rò rỉ |
|---|---|---|---:|---:|---:|---:|---:|
| tvpl | admin | all / commercial | 727 / 273 | 0,875 / 0,888 | 0 / 0 | — | 0 |
| tvpl | kho | all | 727 | 0,889 | 321 (44,2%) | **295 (40,6%)** | 0 |
| tvpl | kho | commercial | 273 | 0,016 | 262 (96,0%) | — | 0 |
| zalo | admin | all / commercial | 631 / 157 | 0,906 / 0,908 | 0 / 0 | — | 0 |
| zalo | kho | all | 631 | 0,927 | 300 (47,5%) | **274 (43,4%)** | 0 |
| zalo | kho | commercial | 157 | 0,000 | 154 (98,1%) | — | 0 |

- **Bất biến đạt**: `accounting` trùng `admin` TỪNG CÂU (1000/1000, 788/788) — cùng tập thấy được thì
  cùng thứ hạng. `sales` có cùng `rag_visibility` với `accounting` (test khoá giả định này).
- **Lọc SQL chặn tuyệt đối**: 0 rò rỉ trên 1.788 câu × vai kho.
- **Tín hiệu "bị chặn" bắt đúng 96–98%** câu có đáp án bị giấu (trước đây chỉ kiểm trên 10 câu).
- **Nhưng luật top-3 từ chối oan 40–43%** câu mà kho ĐÃ tìm đúng đáp án (TVPL: 235 câu đúng ngay hạng
  1). `hidden_classes` khác rỗng ⇒ `nodes.py`/`fanout.py` THAY câu trả lời bằng lời từ chối, bỏ cả chunk
  thấy được. Luật không hỏi "phần thấy được đã đủ trả lời chưa", nên tỉ lệ báo oan **tăng theo mật độ
  nội dung bị giấu** — production đo 0/990 vì mật độ thấp; sẽ không còn đúng khi điều kiện mở lại 19b
  ("corpus có nhiều tài liệu nội bộ") thành thật.
- Lọc làm r@6 của câu `all` **tăng** (TVPL +0,014, Zalo +0,021): bớt distractor thương mại.

## Phát hiện phụ (production)

- **Thứ hạng truy xuất không tất định khi bảng bị tổ chức lại vật lý.** Chân FTS (`_sparse`,
  `_lexical_fold`) `ORDER BY score DESC LIMIT` không có khoá phá hoà; 117/200 câu TVPL có điểm
  `ts_rank` hoà trong top-20 chân bỏ dấu. Sau `UPDATE visibility`, 21/1.000 câu đổi thứ tự top-6 (admin
  pha B vs bge-blend pha A, cùng tập pool). Embedding (Ollama) và HNSW đã kiểm là tất định, HNSW khớp
  quét chính xác 200/200. Sửa rẻ: thêm `, c.id` vào `ORDER BY` các chân FTS — CHƯA sửa.
- **Ingest ghi từng dòng tốn 46 ms/dòng** (21,5 chunk/s, round-trip); `executemany` + vector numpy nhị
  phân đạt 312 chunk/s. `ingest._ingest_known` production vẫn ghi từng dòng — CHƯA sửa.

## Chạy lại

```bash
cd backend
export DATABASE_URL=...  OLLAMA_URL=http://127.0.0.1:11435   # KHÔNG dùng OLLAMA_URL trong .env (sai cổng)
.venv/Scripts/python.exe -m evals.bench_ngoai ingest tvpl     # nối tiếp được, bỏ qua passage đã có
.venv/Scripts/python.exe -m evals.bench_ngoai pools tvpl
bash evals/bench_ngoai_legs.sh tvpl evals/results/<thư-mục>
.venv/Scripts/python.exe -m evals.bench_ngoai label tvpl      # pha B: gán nhãn visibility giả lập
.venv/Scripts/python.exe -m evals.bench_ngoai role tvpl --role warehouse --out ...
```

Thời gian trên máy dev (RTX 5060 Ti 8 GB): nạp TVPL ~7 phút, Zalo ~85 phút (tranh GPU); pool ~12 phút;
chân bge ~4 phút, chân Qwen3-0.6B ~15 phút; mỗi vai pha B ~10–15 phút.
