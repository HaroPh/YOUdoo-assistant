from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    chunk_id: int
    doc_id: str
    source_file: str
    doc_title: str
    section_path: str | None   # text docs
    page: int | None           # text docs
    sheet: str | None          # xlsx
    row_range: str | None      # xlsx
    text: str
    dense_score: float | None  # cosine similarity (None if only a sparse hit)
    sparse_score: float | None # ts_rank (None if only a dense hit)
    rrf_score: float           # fused score (RRF) — luôn giữ, kể cả sau rerank
    rank: int                  # 0-based position in FINAL result order
    rerank_score: float | None = None  # cross-encoder score (None nếu tắt/hỏng)
    # Ngày hiệu lực của VĂN BẢN NGUỒN (rag_documents), không phải của chunk.
    # None hợp lệ và là ca THƯỜNG GẶP: 8/17 tài liệu trong corpus là tài liệu
    # nghiệp vụ (.docx/.xlsx), không phải văn bản quy phạm.
    #
    # Kiểu là CHUỖI ISO chứ không phải datetime.date, dù psycopg trả về date:
    # chunk_to_dict() đổ asdict(self) thẳng vào state LangGraph, và state phải
    # là JSON thuần (bất biến ghi ở fanout.py). Một datetime.date sẽ đi lọt
    # mọi unit test dùng checkpointer giả rồi hỏng đúng lúc gặp Postgres thật.
    effective_date: str | None = None


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    query_used: str
    chunks: list[Chunk]
    top_score: float
    total_candidates: int
    method: str = "hybrid-rrf"

    def is_empty(self) -> bool:
        return not self.chunks
