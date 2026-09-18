# Kết quả 6 chân đo trên bộ `retrieval` MỞ RỘNG (109 ca, `n_hard = 62`)

Spec: `docs/superpowers/specs/2026-09-18-mo-rong-hard-set-design.md`. Golden set đóng băng tại
commit `0398c04` (17 ca `hard` cũ + 45 ca mới do agent mù viết từ mẫu tất định seed 20260918).
Corpus, `TOP_N = 20`, `TOP_K = 6`, `RERANK_MAX_LENGTH = 512`, embedding `bge-m3` — không đổi so
với vòng `reranker-2026-09-17/`. Mọi JSON đều mang `rerank_model` và `rerank_mode`.

| tệp | `RERANK_MODEL` | `RAG_RERANK_MODE` | env thêm | ngày chạy |
|---|---|---|---|---|
| `no-rerank.json` | (bge, không dùng) | blend | `RAG_RERANK_ENABLED=0` (cờ `--no-rerank`) | 2026-09-18 |
| `bge-v2-m3.json` | `BAAI/bge-reranker-v2-m3` | blend | — | 2026-09-18 |
| `qwen3-0.6b.json` | `Qwen/Qwen3-Reranker-0.6B` | blend | — | 2026-09-18 |
| `qwen3-0.6b-override.json` | `Qwen/Qwen3-Reranker-0.6B` | override | — | 2026-09-18 |
| `qwen3-4b.json` | `Qwen/Qwen3-Reranker-4B` | blend | `RERANK_DEVICE_MAP=auto RERANK_GPU_BUDGET=4GiB` | 2026-09-18 (chạy LẠI, xem dưới) |
| `qwen3-4b-override.json` | `Qwen/Qwen3-Reranker-4B` | override | `RERANK_DEVICE_MAP=auto RERANK_GPU_BUDGET=3GiB` | 2026-09-18 |

`p50` của hai chân 4B là đường `device_map` tràn CPU — **không đại diện triển khai**. Hai chân
4B dùng ngân sách GPU khác nhau (4GiB / 3GiB): chỉ đổi *chỗ đặt* trọng số, không đổi phép toán —
bảng (b) dưới đây chứng minh (cùng một chân tái tạo y hệt kết quả cũ dưới cả hai ngân sách).
4GiB làm GPU đầy 7,6/8,15 GB và **chậm gấp ~3,5 lần** (50 phút, p50 24 s) mà không lợi gì.

## (a) Hợp lệ

| chân | n | errors | methods_seen |
|---|---:|---:|---|
| no-rerank | 109 | 0 | `dense+fold-rrf` |
| bge-v2-m3 | 109 | 0 | `dense+fold-rrf+rerank` |
| qwen3-0.6b | 109 | 0 | `dense+fold-rrf+rerank` |
| qwen3-4b | 109 | 0 | `dense+fold-rrf+rerank` |
| qwen3-0.6b-override | 109 | 0 | `dense+fold-rrf+rerank` |
| qwen3-4b-override | 109 | 0 | `dense+fold-rrf+rerank` |

## (b) Đối chứng hạ tầng `old-64` — spec §7

Mỗi chân so `per_case` với chân cùng tên trong `reranker-2026-09-17/` trên 64 câu cũ.

| chân | n | ca `recall_at_final` khác | `hard17 mrr` cũ | mới | lệch |
|---|---:|---:|---:|---:|---:|
| no-rerank | 64 | 0 | 0,5403 | 0,5403 | 0,0000 |
| bge-v2-m3 | 64 | 0 | 0,5755 | 0,5755 | 0,0000 |
| qwen3-0.6b | 64 | 0 | 0,6196 | 0,6196 | 0,0000 |
| qwen3-4b | 64 | 0 | 0,6814 | 0,6814 | 0,0000 |
| qwen3-0.6b-override | 64 | 0 | 0,7173 | 0,7173 | 0,0000 |
| qwen3-4b-override | 64 | 0 | 0,8255 | 0,8255 | 0,0000 |

Hạ tầng truy xuất **không trôi** giữa hai vòng đo: kết quả trên 64 câu cũ trùng khít từng ca.

## (c) Cổng R12 — `recall@6` trên 45 câu MỚI không được dưới chân tắt rerank

Vì sao cần cổng này: bộ eval chạy 64 ca cũ TRƯỚC rồi 45 ca mới SAU, nên cổng (b) chỉ soi phần
chạy đầu. Lượt chạy `qwen3-4b` đầu tiên (ngay sau chân `0.6B override` xong 16:35, trước lần
máy reset) qua (a) và (b) hoàn hảo nhưng sụp trên 45 ca sau: `r@6 new45 = 0,6444` — **tệ hơn
tắt reranker** (0,8667) — do máy cạn RAM giữa lượt (chân này tràn ~5 GB trọng số sang CPU).
Lượt đó bị LOẠI và chạy lại; lượt chạy lại bắt đầu 17:19–17:20 (mtime `qwen3-4b.stderr.log`),
xong 18:10, và **ghi đè** lên JSON của lượt bị loại — lượt đó không còn kiểm toán được.

| chân | `r@6` new45 | `mrr` new45 | |
|---|---:|---:|---|
| no-rerank | 0,8667 | 0,5809 | mốc |
| bge-v2-m3 | 0,9556 | 0,8010 | đạt |
| qwen3-0.6b | 0,9333 | 0,8196 | đạt |
| qwen3-4b (chạy lại) | 0,9333 | 0,7847 | đạt |
| qwen3-0.6b-override | 0,9556 | 0,8946 | đạt |
| qwen3-4b-override | 0,9556 | 0,8843 | đạt |

## Bảng 6 chân trên 109 ca

| chân | r@6 | r@20 | mrr | easy | **hard62** | trap | p50 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| no-rerank | 0,8838 | 0,9771 | 0,6551 | 0,7673 | 0,5697 | 0,7682 | 497 |
| bge-v2-m3 | 0,9633 | 0,9771 | 0,8058 | 0,8968 | 0,7392 | 0,8875 | 712 |
| qwen3-0.6b | 0,9419 | 0,9771 | 0,8066 | 0,8807 | 0,7647 | 0,8250 | 1182 |
| qwen3-4b | 0,9541 | 0,9771 | 0,8123 | 0,8836 | 0,7563 | 0,8906 | 23946 |
| qwen3-0.6b-override | 0,9587 | 0,9771 | 0,8638 | 0,9258 | 0,8460 | 0,8125 | 1154 |
| qwen3-4b-override | 0,9679 | 0,9771 | 0,8921 | 0,9382 | 0,8681 | 0,8958 | 4568 |

Kiểm định ghép cặp và kết luận theo quy tắc đăng ký trước (spec §8): xem spec §10–§11 (Task 7).

`baseline-bge-m3-retrieval.json` được sinh lại từ chân `bge-v2-m3` trên 109 ca (thay bản 64 ca).
