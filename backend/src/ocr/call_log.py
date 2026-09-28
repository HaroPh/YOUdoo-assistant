"""Nhật ký MỌI lượt gọi VLM — bảng `vlm_call_log` (migration 010).

Vì sao có bảng này khi đã có `llm_usage`: chủ dự án chấp nhận VLM dùng CHUNG
ví Gemini với chatbot (2026-09-28; đo cùng ngày: 3/3 khoá `YOUDOO_VLM_API_KEY*`
trùng `GOOGLE_API_KEY*`), với điều kiện mọi lượt gọi đều được ghi. `llm_usage`
chỉ ghi lượt THÀNH CÔNG — lượt 429, lỗi mạng, hết khoá không để lại dấu vết
nào sống qua tiến trình. Không ghi chúng vào `llm_usage` vì bộ kiểm hạn mức
(`usage_since`) đếm DÒNG ở đó: chèn lượt 429 vào là sổ ngân sách đếm sai.

Một dòng = một lần bấm gọi API. Lượt bị chặn TRƯỚC khi gọi (VLM tắt, chạm trần)
không có dòng — chúng không tiêu hạn mức.

Ghi là TƯ VẤN, fail-open: `VisionReader._log_call` bọc mọi lỗi thành cảnh báo.
Nhật ký hỏng không được giết lượt đọc của người dùng.
"""
from __future__ import annotations

import re

OUTCOMES = ("ok", "bad_response", "rate_limited", "error")
ERROR_MAX_CHARS = 200

# Khoá Google API: `AIza` + 35 ký tự. Che cả những khoá KHÔNG nằm trong cấu
# hình hiện tại (vd khoá cũ còn trong URL SDK trả về).
_GOOGLE_KEY = re.compile(r"AIza[0-9A-Za-z_\-]{35}")


def redact_error(exc: BaseException, *, secrets) -> str:
    """`<LớpLỗi>: <thông điệp>` đã che khoá, cắt còn `ERROR_MAX_CHARS` ký tự.

    Thông điệp lỗi của SDK có thể mang URL `?key=...`. Che theo GIÁ TRỊ khoá
    đang cấu hình (chắc chắn) cộng mẫu khoá Google (bắt khoá lạ)."""
    msg = f"{type(exc).__name__}: {exc}"
    for s in sorted((s for s in secrets if s), key=len, reverse=True):
        msg = msg.replace(s, "***")
    msg = _GOOGLE_KEY.sub("***", msg)
    return msg[:ERROR_MAX_CHARS]


class InMemoryVlmCallLog:
    """Bản trong bộ nhớ — cho test (rào conftest) và cho người gọi muốn tự đọc."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def record(self, **row) -> None:
        self.rows.append(row)


class PostgresVlmCallLog:
    """Bản bền. Cùng khuôn `PostgresUsageStore`: pool timeout ngắn, kiểm bảng
    NGAY lúc dựng để "quên chạy migration 010" nổ to một lần (thành cảnh báo
    ở `_log_call`) chứ không lặng lẽ mất từng dòng."""

    _COLUMNS = ("ts", "source", "page", "mode", "model", "prompt_version",
                "key_index", "outcome", "latency_ms", "prompt_tokens",
                "completion_tokens", "total_tokens", "error")

    def __init__(self, dsn: str | None = None) -> None:
        import os

        from psycopg_pool import ConnectionPool

        self._pool = ConnectionPool(dsn or os.environ["DATABASE_URL"],
                                    min_size=1, max_size=2, open=True,
                                    timeout=2.0, kwargs={"connect_timeout": 2})
        try:
            with self._pool.connection() as conn:
                conn.execute("SELECT 1 FROM vlm_call_log LIMIT 0")
        except Exception as exc:
            self._pool.close()
            raise RuntimeError(
                "bảng vlm_call_log không tồn tại hoặc Postgres không truy cập "
                "được — chạy backend/migrations/010_vlm_call_log.sql") from exc

    def close(self) -> None:
        self._pool.close()

    def record(self, **row) -> None:
        cols = ", ".join(self._COLUMNS)
        marks = ", ".join(["%s"] * len(self._COLUMNS))
        with self._pool.connection() as conn:
            conn.execute(f"INSERT INTO vlm_call_log ({cols}) VALUES ({marks})",
                         tuple(row[c] for c in self._COLUMNS))


class DefaultVlmCallLog:
    """Nhật ký MẶC ĐỊNH của `VisionReader` — mở kết nối MUỘN, MỘT LẦN mỗi tiến trình.

    Cùng lý do với `vision._SoVlm`: ghi là bất biến của LỚP (dựng
    `VisionReader()` ở đâu cũng có nhật ký), mở ở `record()` để test/parse_pdf
    không có khoá VLM không chạm Postgres, và `_tried` để Postgres sập không
    thành mấy chục lần thử (timeout 2s) trong cùng một tài liệu.

    Dựng hỏng thì NHỚ lỗi và ném lại ở MỌI lượt sau (rẻ, không chạm mạng):
    `_SoVlm` im lặng từ lượt thứ hai, nhưng nhật ký này tồn tại để không lượt
    nào mất mà không ai biết — mỗi dòng mất phải là một cảnh báo.

    KHÔNG bắt exception: `VisionReader._log_call` đã bọc → fail-open.
    """

    _store = None
    _tried = False
    _failure: Exception | None = None

    def record(self, **row) -> None:
        cls = DefaultVlmCallLog
        if not cls._tried:
            cls._tried = True
            try:
                cls._store = PostgresVlmCallLog()
            except Exception as e:
                cls._failure = e
                raise
        if cls._store is None:
            raise RuntimeError(f"vlm_call_log không khả dụng từ lần dựng đầu: {cls._failure}")
        cls._store.record(**row)
