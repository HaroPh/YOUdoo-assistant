import os

# Chunking
CHUNK_SIZE_TOKENS = 400
CHUNK_OVERLAP_TOKENS = 60
MIN_CHUNK_TOKENS = 80
TIKTOKEN_ENCODING = "cl100k_base"

# Embedding (external, via Ollama)
EMBED_MODEL = "bge-m3"
EMBED_DIM = 1024
# 127.0.0.1 CHỨ KHÔNG PHẢI localhost — khác biệt đo được, không phải khẩu vị.
# docker-compose bind cổng ở "127.0.0.1:11435:11434", tức CHỈ IPv4. Trên
# Windows "localhost" phân giải ra ::1 trước, httpx thử IPv6 rồi mới lùi về
# IPv4 — mỗi lời gọi embed trả giá ~2 GIÂY cho cú thử hỏng đó.
# Đo 2026-08-19, cùng payload, 3 lượt mỗi bên:
#     http://localhost:11435  → 2498 / 2300 / 2312 ms
#     http://127.0.0.1:11435  →  271 /  291 /  269 ms
# Giá này áp lên MỌI truy vấn RAG (rag_node và gather_docs đều gọi retrieve()
# → embed_query), và nó lớn gấp ~30 lần toàn bộ chi phí rerank trên GPU.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11435")

# Store
# ⚠️ 5434 là cổng của Youdoo, KHÔNG phải 5433 (container postgres của
# D:\Project, cùng máy dev, CÙNG tên db `ai_assistant`). Xem chú thích đầy
# đủ ở agents/erp_agent.py cạnh PG_CONN.
RAG_DB_DSN = os.environ.get("DATABASE_URL",
                            "postgresql://admin:changeme@localhost:5434/ai_assistant")
RAG_SCHEMA = os.environ.get("RAG_SCHEMA", "public")

# Retrieval
TOP_N = 20      # candidates per retriever before fusion
TOP_K = 6       # final chunks returned
RRF_K = 60      # RRF constant

# Rerank (cross-encoder — spec 2026-07-12-rag-reranker; GPU 2026-08-19)
# Đọc từ env để bộ eval đổi model theo TIẾN TRÌNH mà không sửa mã (spec
# 2026-09-17 §4: mỗi chân đo là một tiến trình vì _load() cache một lần).
# Mặc định KHÔNG đổi — thay production là quyết định riêng sau khi có bảng số.
RERANK_MODEL = os.environ.get("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_MAX_LENGTH = 512
# Rỗng = nạp kiểu cũ (.half().to(device)). "auto" = accelerate đặt lớp lên
# GPU tới ngân sách rồi tràn sang CPU RAM — CHỈ cho lượt đo 4B (fp16 8 GB
# không vừa card 8,15 GB). Độ trễ trên đường này KHÔNG đại diện triển khai.
RERANK_DEVICE_MAP = os.environ.get("RERANK_DEVICE_MAP", "")
RERANK_GPU_BUDGET = os.environ.get("RERANK_GPU_BUDGET", "5GiB")
# "auto" = cuda nếu dò được, không thì cpu. Đặt "cpu" để đo đối chứng.
# Giá trị này chỉ là MẶC ĐỊNH — reranker._resolve_device() đọc env mỗi lần gọi.
RERANK_DEVICE = os.environ.get("RERANK_DEVICE", "auto")
