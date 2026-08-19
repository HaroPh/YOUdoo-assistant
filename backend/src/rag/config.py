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
RAG_DB_DSN = os.environ.get("DATABASE_URL",
                            "postgresql://admin:changeme@localhost:5433/ai_assistant")
RAG_SCHEMA = os.environ.get("RAG_SCHEMA", "public")

# Retrieval
TOP_N = 20      # candidates per retriever before fusion
TOP_K = 6       # final chunks returned
RRF_K = 60      # RRF constant

# Trần số chunk mỗi MỤC được vào kết quả cuối (spec 2026-08-19 §11.2).
# Đo trên golden set 56 câu: top-6 chỉ có 4,80/6 mục phân biệt, 20/56 câu có
# <=4 — tức ~20% ô ngữ cảnh gửi cho LLM là bản trùng của cùng một Điều.
#
# Vì sao 2 chứ không phải 1: chunk_span baseline = 2,39, tức câu trả lời đúng
# thường trải trên hơn 2 chunk cùng mục. cap=1 sẽ bỏ đói một Điều dài xuống
# còn một mảnh, và bộ đo hiện tại KHÔNG THẤY được mặt hại đó (recall/mrr chấm
# trên nhãn, mà nhãn không đổi khi bỏ bớt chunk trùng mục). Chọn thận trọng.
#
# <=0 hoặc giá trị lạ = tắt hẳn việc chặn trần, quay về cắt tiền tố như cũ.
RAG_SECTION_CAP = int(os.environ.get("RAG_SECTION_CAP", "2") or 2)

# Rerank (cross-encoder — spec 2026-07-12-rag-reranker; GPU 2026-08-19)
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
RERANK_MAX_LENGTH = 512
# "auto" = cuda nếu dò được, không thì cpu. Đặt "cpu" để đo đối chứng.
# Giá trị này chỉ là MẶC ĐỊNH — reranker._resolve_device() đọc env mỗi lần gọi.
RERANK_DEVICE = os.environ.get("RERANK_DEVICE", "auto")
