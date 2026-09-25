# Đo lại bench ngoài sau KHOÁ PHÁ HOÀ (2026-09-24)

Chạy lại trên cùng hai bộ của [`../bench-ngoai-2026-09-23/`](../bench-ngoai-2026-09-23/README.md),
sau commit `a2b07be` (thêm `, c.id` vào `ORDER BY` của cả ba chân truy xuất).

## Vì sao phải đo lại

Số ngày 23/09 đo trên mã **chưa có khoá phá hoà**. `ORDER BY score DESC LIMIT`
của Postgres dùng top-N heapsort, mà heapsort **không ổn định** — khi nhiều hàng
cùng điểm, hàng nào lọt vào pool và xếp ở đâu là tuỳ ý. Chân bỏ dấu có 117/200
câu TVPL hoà `ts_rank` trong top-20, nên đây không phải chuyện lý thuyết.

Hệ quả: **pool cache ngày 23/09 không tái lập được bằng mã hôm nay.** Nó được
giữ lại nguyên vẹn (`bench-cache/*-pools.PRE-TIEBREAK-20260923.json`) để kiểm
toán, không bị đè.

Bench là **một lượt** nên `aux_queries` rỗng ⇒ bản sửa truy vấn rerank
(`f30422b`) KHÔNG có tác dụng theo cấu trúc. Chỉ còn khoá phá hoà trong phương
trình — phép đo cô lập sạch.

## Kết quả

Pool dựng lại: TVPL ~11 phút, Zalo ~37 phút. Hai chân mỗi bộ, `errors = 0` cả bốn.

| bộ | chân | n | r@20 | r@6 | MRR | nDCG@10 |
|---|---|---:|---:|---:|---:|---:|
| tvpl | no-rerank | 1000 | 0,9150 → **0,9193** | 0,8298 → 0,8312 | 0,6868 → 0,6863 | 0,7217 → 0,7219 |
| tvpl | bge-blend | 1000 | 0,9150 → **0,9193** | 0,8777 → **0,8805** | 0,7709 → 0,7705 | 0,7955 → 0,7960 |
| zalo | no-rerank | 788 | 0,9277 → **0,9365** | 0,8617 → 0,8680 | 0,6836 → 0,6857 | 0,7343 → 0,7388 |
| zalo | bge-blend | 788 | 0,9277 → **0,9365** | 0,9067 → **0,9131** | 0,7523 → 0,7484 | 0,7933 → 0,7922 |

Đếm theo TỪNG câu (r@6), không chỉ nhìn trung bình:

| bộ / chân | tốt lên | kém đi | không đổi |
|---|---:|---:|---:|
| tvpl / no-rerank | 6 | 5 | 989 |
| tvpl / bge-blend | 7 | 3 | 990 |
| zalo / no-rerank | 8 | 3 | 777 |
| zalo / bge-blend | 7 | 2 | 779 |

## Kết luận — và chỗ KHÔNG được kết luận

**Khẳng định được: không có hồi quy.** r@20 và r@6 tăng ở cả bốn chân, trên hai
bộ độc lập với qrels do người ngoài viết, n = 1 788. Đây là bằng chứng mạnh hơn
hẳn 109 ca nội bộ (ở đó 1 ca = 0,92%, quá thô để thấy hiệu ứng nhỏ).

**KHÔNG khẳng định: `, c.id` làm chất lượng tốt hơn.** "Id nhỏ nhất thắng" là
quy tắc tuỳ ý, không có lý do nào liên quan tới độ liên quan. Mức tăng
+0,004/+0,009 nhiều khả năng chỉ là chênh giữa một lựa chọn tất định và một lần
rút thăm của heapsort không ổn định. Bằng chứng phụ: trên bộ nội bộ, đo thêm
`c.id DESC` cho kết quả **không cùng chiều** (nửa dấu DESC tốt hơn ASC, không
dấu ASC tốt hơn DESC) — không có chiều hệ thống nào.

**Giá trị thật của bản sửa là TÍNH TÁI LẬP**, không phải chất lượng: từ nay hai
lượt chạy cùng mã trên cùng dữ liệu cho cùng số, nên một cổng dựa trên recall
không còn đỏ/xanh vì lý do giả.

## Pha A đủ năm chân (đo 2026-09-25, trên cùng pool tất định)

Ba chân còn lại chạy tuần tự trên đúng pool đã dựng lại ở trên — 46 phút cho sáu
lượt, `errors = 0` mọi chân, **cổng R12 ĐẠT mọi chân** (recall@6 nửa SAU theo thứ
tự chạy ≥ chân tắt rerank, bắt suy giảm giữa lượt mà cổng tổng không thấy).

| bộ | chân | r@20 | r@6 | MRR | nDCG@10 | p50 rerank |
|---|---|---:|---:|---:|---:|---:|
| tvpl | no-rerank | 0,9193 | 0,8312 | 0,6863 | 0,7219 | — |
| tvpl | bge-blend (production) | 0,9193 | 0,8805 | 0,7705 | 0,7960 | 189 ms |
| tvpl | **bge-override** | 0,9193 | **0,8942** | **0,8124** | **0,8291** | 189 ms |
| tvpl | qwen06-blend | 0,9193 | 0,8787 | 0,7621 | 0,7877 | 652 ms |
| tvpl | qwen06-override | 0,9193 | 0,8887 | 0,7921 | 0,8107 | 653 ms |
| zalo | no-rerank | 0,9365 | 0,8680 | 0,6857 | 0,7388 | — |
| zalo | bge-blend (production) | 0,9365 | 0,9131 | 0,7484 | 0,7922 | 191 ms |
| zalo | **bge-override** | 0,9365 | **0,9207** | **0,7960** | **0,8286** | 203 ms |
| zalo | qwen06-blend | 0,9365 | 0,9105 | 0,7338 | 0,7807 | 665 ms |
| zalo | qwen06-override | 0,9365 | 0,9061 | 0,7344 | 0,7801 | 662 ms |

`p50` lần này đo khi GPU **không** bị chia với lượt nạp song song (bản 23/09 có),
nên Qwen3-0.6B đo ra 652 ms thay vì 843 ms — tỉ lệ chậm hơn bge nay là **3,4×**.

### Kiểm định ghép cặp — so với bản 23/09

Chênh TB, CI95 bootstrap, p hoán vị; thắng/hoà/thua theo từng câu.

| phép so | bộ | MRR (pool tất định) | MRR (23/09) |
|---|---|---|---|
| bge-blend vs no-rerank | tvpl | +0,084 [+0,072;+0,096] p<0,0001 | +0,084 p<0,0001 |
| | zalo | +0,063 [+0,048;+0,078] p<0,0001 | +0,069 p<0,0001 |
| **bge-override vs bge-blend** | tvpl | **+0,042 [+0,029;+0,055] p<0,0001**, 174/759/67 | +0,038 p<0,0001 |
| | zalo | **+0,048 [+0,030;+0,066] p<0,0001**, 160/545/83 | +0,046 p<0,0001 |
| qwen06-blend vs bge-blend | tvpl | **−0,008 [−0,017;+0,000] p≈0,06** | −0,012 p=0,007 |
| | zalo | −0,015 [−0,027;−0,003] p≈0,016 | −0,013 p=0,032 |
| qwen06-override vs bge-override | tvpl | −0,020 [−0,034;−0,007] p=0,003 | −0,022 p=0,001 |
| | zalo | −0,062 [−0,079;−0,044] p<0,0001 | −0,060 p<0,0001 |

recall@6 của override vs blend: TVPL +0,014 [+0,003;+0,025] p=0,013 (exact),
Zalo +0,008 p=0,18 (exact) — override **không** làm tụt recall, nhích nhẹ ở TVPL.

Hai p sát ngưỡng (0,06 và 0,016) tính bằng Monte Carlo vì DP vượt trần trạng thái
(173 và 167 chênh ≠ 0). Đã kiểm lại với n_mc = 100 000 và ba seed khác nhau:
TVPL 0,0601 / 0,0615 / 0,0623 — luôn trên 0,05; Zalo 0,0166 / 0,0160 / 0,0168 —
luôn giữa 0,01 và 0,05. Không phải chuyện sai số MC.

### Một khẳng định trước đó SAI — sửa lại

Bản trước của README này (và ghi chú đầu README 23/09, và mô tả PR #1) viết:
*"kết luận tương đối vẫn nguyên giá trị vì mọi chân chấm trên CÙNG một pool,
nên chênh lệch giữa các chân không phụ thuộc pool ấy được dựng ra sao"*.

**Số đo bác một phần:** 7/8 phép so MRR giữ nguyên chiều và mức ý nghĩa, nhưng
`qwen06-blend vs bge-blend` trên TVPL rơi từ p = 0,007 xuống p ≈ 0,06 — cùng
chiều, không còn đủ bằng chứng.

Lập luận sai ở chỗ nhập **công bằng** với **bất biến**. Cùng một pool bảo đảm hai
chân được so trên đầu vào giống hệt nhau — phép so CÔNG BẰNG. Nhưng pool chính là
MẪU các cặp (câu hỏi, tập ứng viên) được đem ra so; đổi pool là đổi mẫu, và không
có lý do gì để kết quả BẤT BIẾN.

**Không quyết định nào đổi:**

- **override > blend** — chắc hơn trước: +0,042/+0,048 p < 0,0001 trên cả hai bộ,
  nay trên pool tất định nên tái lập được. Đây là phép so đứng sau quyết định có
  chuyển production sang `RAG_RERANK_MODE=override` hay không.
- **Qwen3-Reranker-0.6B không thay được bge-reranker-v2-m3** — vẫn đứng: thua có ý
  nghĩa ở 3/4 phép so MRR, **không thắng ở phép nào**, chậm hơn 3,4×. Chỉ là dựa
  trên 3 phép so thay vì 4.

## Chạy lại

```bash
cd backend
export DATABASE_URL=...  OLLAMA_URL=http://127.0.0.1:11435   # KHÔNG dùng OLLAMA_URL trong .env
.venv/Scripts/python.exe -m evals.bench_ngoai pools tvpl     # ~11 phút; zalo ~37 phút
RERANK_MODEL=BAAI/bge-reranker-v2-m3 RAG_RERANK_MODE=blend \
  .venv/Scripts/python.exe -m evals.bench_ngoai leg tvpl --leg bge-blend --out <...>
```
