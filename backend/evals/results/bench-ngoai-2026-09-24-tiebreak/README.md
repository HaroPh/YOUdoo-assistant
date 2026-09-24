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

## Ba chân còn lại CHƯA đo lại

`bge-override`, `qwen06-blend`, `qwen06-override` vẫn là số ngày 23/09.

Kết luận **tương đối** của chúng (bge thắng Qwen3-0.6B; override thắng blend về
MRR) **vẫn nguyên giá trị**: thiết kế của bench là mọi chân chấm trên CÙNG một
pool, nên chênh lệch giữa các chân không phụ thuộc pool ấy được dựng ra sao.
Chỉ con số **tuyệt đối** r@20 = 0,9150/0,9277 của bản cũ là một lần rút thăm —
nay thay bằng 0,9193/0,9365.

Muốn bảng Pha A hoàn toàn cùng một lượt thì chạy nốt ba chân
(`bash evals/bench_ngoai_legs.sh <ds> <thư-mục>` chạy cả năm, ~1 giờ cho hai bộ).

## Chạy lại

```bash
cd backend
export DATABASE_URL=...  OLLAMA_URL=http://127.0.0.1:11435   # KHÔNG dùng OLLAMA_URL trong .env
.venv/Scripts/python.exe -m evals.bench_ngoai pools tvpl     # ~11 phút; zalo ~37 phút
RERANK_MODEL=BAAI/bge-reranker-v2-m3 RAG_RERANK_MODE=blend \
  .venv/Scripts/python.exe -m evals.bench_ngoai leg tvpl --leg bge-blend --out <...>
```
