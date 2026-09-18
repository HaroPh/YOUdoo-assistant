# Cấu hình sinh ra sáu JSON này

Sáu tệp trong thư mục này được sinh **TRƯỚC** khi `eval_retrieval` có hai khoá
`rerank_model` / `rerank_mode` (thêm sau, review whole-branch của nhánh
`so-sanh-reranker`) — bản thân các JSON **KHÔNG** tự khai được cấu hình đã
sinh ra chúng. Bảng dưới đây là ghi chú thủ công thay thế, khớp với lệnh chạy
ở `docs/superpowers/plans/2026-09-17-so-sanh-reranker.md` Task 4/5. **Không
chạy lại các chân này** — số liệu đã được dùng để ra kết luận ở
`docs/superpowers/specs/2026-09-17-so-sanh-reranker-design.md` §8 Task 6.

| tệp | `RERANK_MODEL` | `RAG_RERANK_MODE` | ghi chú |
|---|---|---|---|
| `no-rerank.json` | — | — | `RAG_RERANK_ENABLED=0` (đối chứng, reranker tắt hẳn) |
| `bge-v2-m3.json` | `BAAI/bge-reranker-v2-m3` | `blend` (mặc định) | mốc hiện tại, đo lại cùng ngày trên corpus mới |
| `qwen3-0.6b.json` | `Qwen/Qwen3-Reranker-0.6B` | `blend` (mặc định) | |
| `qwen3-4b.json` | `Qwen/Qwen3-Reranker-4B` | `blend` (mặc định) | `RERANK_DEVICE_MAP=auto RERANK_GPU_BUDGET=3GiB` — nạp tràn CPU RAM, `p50ms` KHÔNG đại diện triển khai thật (spec §3, §8 Task 4) |
| `qwen3-0.6b-override.json` | `Qwen/Qwen3-Reranker-0.6B` | `override` | |
| `qwen3-4b-override.json` | `Qwen/Qwen3-Reranker-4B` | `override` | cùng `RERANK_DEVICE_MAP=auto RERANK_GPU_BUDGET=3GiB` như trên |

Mọi chân đều cùng bộ `retrieval` (64 ca) và cùng corpus (không ingest xen
giữa các lần chạy — xem spec §8 Task 4 "Khó khăn"). Từ nay về sau, một JSON
mới sinh bởi `eval_retrieval` tự mang `rerank_model`/`rerank_mode` trong thân
kết quả — bảng này chỉ cần cho sáu tệp cũ.
