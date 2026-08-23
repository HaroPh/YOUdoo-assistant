"""Embedding — hai implementation sau một interface (spec SP-1B §3b).

OllamaEmbedder (bge-m3, 1024 chiều) BẬT mặc định; GeminiEmbedder viết sẵn
nhưng TẮT.

VÌ SAO KHÔNG BẬT GEMINI NGAY: corpus nhỏ (17 tài liệu, 8.2MB) nên re-index chỉ
tốn 30–60 phút — chi phí không phải rào cản. Rào cản là ĐO ĐẠC: SP-1 đã đổi LLM
từ qwen3:8b local sang cloud; đổi luôn embedding là đổi HAI biến cùng lúc, và
khi read/multi_source lệch đi thì không quy được cho biến nào. Sau khi eval-gate
của cú flip LLM đi qua (kế hoạch C), lật embedding là thí nghiệm THỨ HAI, đo
riêng.

Hai bên bất đối xứng khác nhau: bge-m3 đối xứng (câu hỏi và tài liệu nhúng như
nhau), Gemini bất đối xứng (task_type phân biệt RETRIEVAL_DOCUMENT với
RETRIEVAL_QUERY). Đó là lý do interface tách embed_texts() khỏi embed_query()
thay vì một hàm embed() dùng chung.
"""
import logging
import os
from typing import Protocol, runtime_checkable

import httpx

from .config import EMBED_DIM, EMBED_MODEL, OLLAMA_URL

logger = logging.getLogger(__name__)

GEMINI_EMBED_MODEL = "gemini-embedding-001"
GEMINI_EMBED_DIM = 3072


class EmbeddingError(RuntimeError):
    """Lỗi gọi embedding — OllamaEmbedder bọc lỗi HTTP/response thành loại này,
    để retrieve.py/ingest.py xử lý một loại lỗi duy nhất (retrieve.py/ingest.py
    port nguyên từ repo nguồn, vốn chỉ biết một implementation Ollama — giữ
    đúng hợp đồng cũ). GeminiEmbedder CHƯA bọc tương tự (để nguyên
    httpx.HTTPStatusError/RuntimeError thô) — bất đối xứng có chủ đích vì
    Gemini đang TẮT; cần bọc lại nếu sau này bật thật."""


@runtime_checkable
class Embedder(Protocol):
    """Hợp đồng chung. Ai thêm provider mới chỉ cần thoả bốn thứ này."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    @property
    def model_name(self) -> str: ...
    @property
    def dim(self) -> int: ...


class OllamaEmbedder:
    """bge-m3 qua Ollama — ĐỐI XỨNG, câu hỏi và tài liệu nhúng như nhau.

    Gọi batch /api/embed (không phải /api/embeddings từng-cái-một) — đúng API
    thật mà bản gốc D:\\Project\\backend\\src\\rag\\embed.py dùng."""

    def __init__(self, url: str | None = None) -> None:
        self._url = (url or OLLAMA_URL).rstrip("/")

    @property
    def model_name(self) -> str:
        return EMBED_MODEL

    @property
    def dim(self) -> int:
        return EMBED_DIM

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed một batch qua Ollama /api/embed (bge-m3, 1024 chiều)."""
        if not texts:
            return []
        try:
            resp = httpx.post(f"{self._url}/api/embed",
                              json={"model": EMBED_MODEL, "input": texts},
                              timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            raise EmbeddingError(f"embedding request failed: {e}") from e
        vectors = data.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingError(f"unexpected embedding response: {data!r}")
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


class GeminiEmbedder:
    """gemini-embedding-001 — BẤT ĐỐI XỨNG, task_type phân biệt tài liệu/câu hỏi.

    TẮT ở SP-1 (xem docstring module). Viết sẵn để cú lật sau này là đổi một
    biến môi trường chứ không phải viết code mới dưới áp lực.

    Model ID đã xác nhận tồn tại qua GET /v1beta/models ngày 2026-07-28:
    gemini-embedding-001, gemini-embedding-2-preview, gemini-embedding-2.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")

    @property
    def model_name(self) -> str:
        return GEMINI_EMBED_MODEL

    @property
    def dim(self) -> int:
        return GEMINI_EMBED_DIM

    def _goi(self, text: str, task_type: str) -> list[float]:
        if not self._api_key:
            raise RuntimeError(
                "thiếu GOOGLE_API_KEY — cần cho GeminiEmbedder. Xem .env.example.")
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_EMBED_MODEL}:embedContent",
            params={"key": self._api_key},
            json={"content": {"parts": [{"text": text}]}, "taskType": task_type},
            timeout=60)
        r.raise_for_status()
        return r.json()["embedding"]["values"]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._goi(t, "RETRIEVAL_DOCUMENT") for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._goi(text, "RETRIEVAL_QUERY")


def get_embedder() -> Embedder:
    """Provider đang bật. Mặc định Ollama — xem docstring module về một-biến."""
    ten = os.environ.get("RAG_EMBED_PROVIDER", "ollama").lower()
    if ten == "gemini":
        return GeminiEmbedder()
    return OllamaEmbedder()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Hàm module-level giữ đúng hợp đồng cũ mà ingest.py đã import
    (`from .embed import EmbeddingError, embed_texts`, port nguyên ở Task 4,
    không sửa được nữa). Uỷ quyền cho get_embedder() — chỗ thật sự chọn
    Ollama hay Gemini."""
    return get_embedder().embed_texts(texts)


def embed_query(text: str) -> list[float]:
    """Hàm module-level giữ đúng hợp đồng cũ mà retrieve.py đã import
    (`from .embed import embed_query`, port nguyên ở Task 4). Uỷ quyền cho
    get_embedder()."""
    return get_embedder().embed_query(text)


def assert_embedding_marker(conn) -> None:
    """Provider đang bật lệch với marker trong DB → CHẾT LỚN TIẾNG lúc khởi động.

    Vector nhúng bằng bge-m3 (1024 chiều, đối xứng) và bằng gemini-embedding-001
    (3072 chiều, bất đối xứng) nằm trong hai không gian KHÁC NHAU. Truy vấn
    không gian này bằng vector của không gian kia không báo lỗi — nó chỉ trả về
    kết quả rác, xếp hạng theo một độ tương đồng vô nghĩa. Retrieval rác một
    cách IM LẶNG tệ hơn nhiều so với app không lên: cái thứ hai ai cũng thấy
    ngay, cái thứ nhất đi thẳng vào câu trả lời cho người dùng.

    Cùng triết lý fail-loud với PostgresUsageStore kiểm bảng llm_usage lúc dựng
    (kế hoạch A) — cấu hình lệch phải chết sớm, không đợi tới lúc dùng.

    DB trống (chưa index gì) KHÔNG phải lệch: chưa có gì để lệch.
    """
    row = conn.execute(
        "SELECT embedding_model, dim FROM rag_embedding_marker LIMIT 1").fetchone()
    if row is None:
        return
    trong_db, dim_db = row[0], row[1]
    dang_bat = get_embedder()
    if trong_db != dang_bat.model_name or dim_db != dang_bat.dim:
        raise RuntimeError(
            f"lệch embedding: DB đã index bằng {trong_db!r} ({dim_db} chiều) "
            f"nhưng provider đang bật là {dang_bat.model_name!r} "
            f"({dang_bat.dim} chiều). Vector hai bên nằm ở hai không gian khác "
            f"nhau — truy vấn chéo trả kết quả rác mà KHÔNG báo lỗi. "
            f"Hoặc đổi RAG_EMBED_PROVIDER về đúng, hoặc re-index toàn bộ.")


def nap_am() -> bool:
    """Gọi MỘT lượt nhúng lúc khởi động để Ollama nạp sẵn model vào VRAM.

    Vì sao cần (mục 22, đo 2026-08-23): nạp ấm riêng reranker chỉ kéo câu hỏi
    tài liệu đầu tiên từ 15,8s xuống **10,9s**, trong khi lượt ấm là 4,2–7,0s.
    Phần còn lại nằm ở đây — `OllamaEmbedder` gọi HTTP, và Ollama nạp model
    theo yêu cầu rồi tự gỡ khỏi VRAM sau một lúc nhàn rỗi.

    KHÔNG ném: Ollama chưa lên thì backend vẫn phải khởi động được. Hỏng ở đây
    chỉ có nghĩa "lượt hỏi tài liệu đầu tiên vẫn chậm như cũ".
    """
    try:
        embed_query("khởi động")
        return True
    except Exception:                                       # noqa: BLE001
        logger.warning("Không nạp ấm được embedder — lượt truy xuất đầu tiên "
                       "sẽ chậm hơn", exc_info=True)
        return False
