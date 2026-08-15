"""Kiểm tra tính toàn vẹn chuỗi hash trong mcp_call_log — chạy tay khi cần
điều tra: `python verify_audit_chain.py`. Xem docs/superpowers/specs/
2026-07-23-audit-trail-hash-chain-design.md."""
import audit_chain
from config import DATABASE_URL

_COLUMNS = ["id", "entry_hash", "prev_hash", "created_at", "event_type",
           "caller", "tool_name", "model_name", "operation", "duration_ms",
           "error_code", "error_message"]


def fetch_rows(conn) -> list[dict]:
    """Đọc mọi dòng đã hash-chain (entry_hash khác NULL) theo thứ tự id."""
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT {", ".join(_COLUMNS)}
            FROM mcp_call_log
            WHERE entry_hash IS NOT NULL
            ORDER BY id
        """)
        return [dict(zip(_COLUMNS, row)) for row in cur.fetchall()]


def verify(rows: list[dict]) -> tuple[bool, str]:
    """Duyệt các dòng đã hash-chain theo thứ tự id (rows PHẢI đã ORDER BY
    id), tính lại từng hash và so khớp entry_hash + liên kết prev_hash với
    dòng ngay trước.

    Trả (True, tóm tắt) khi chuỗi nguyên vẹn, (False, lý do) khi đứt.

    `rows` RỖNG trả (False, ...) — KHÔNG phải (True, "OK — 0 dòng") như bản
    trước 2026-08-15. Không có dòng nào để kiểm là "chưa kiểm được gì", không
    phải bằng chứng toàn vẹn; đúng trạng thái của mcp_call_log suốt thời gian
    bảng không tồn tại, và bản cũ báo OK trên đúng trạng thái đó.
    """
    if not rows:
        # Danh sách rỗng đi hết vòng lặp mà không kiểm gì, nên bản cũ trả
        # (True, "OK — 0 dòng") — công cụ kiểm toàn vẹn báo toàn vẹn trên
        # đúng trạng thái mcp_call_log chưa từng ghi được dòng nào.
        return False, ("Bảng rỗng — không có dòng nào đã hash-chain để kiểm. "
                       "Đây KHÔNG phải bằng chứng toàn vẹn.")
    prev = audit_chain.GENESIS_HASH
    for row in rows:
        if row["prev_hash"] != prev:
            return False, f"Chuỗi đứt tại id={row['id']}: prev_hash không khớp"
        expected = audit_chain.compute_entry_hash(
            prev, row["created_at"], row["event_type"], row["caller"],
            row["tool_name"], row["model_name"], row["operation"],
            row["duration_ms"], row["error_code"], row["error_message"])
        if expected != row["entry_hash"]:
            return False, f"Chuỗi đứt tại id={row['id']}: entry_hash không khớp"
        prev = row["entry_hash"]
    return True, f"OK — {len(rows)} dòng, chuỗi nguyên vẹn"


def main() -> None:
    import psycopg2  # nhập trễ: module này phải import được kể cả khi
                      # psycopg2 không có mặt (venv backend/ chạy test không
                      # có gói này, chỉ mcp-servers/odoo/.venv mới cần).
    conn = psycopg2.connect(DATABASE_URL)
    try:
        rows = fetch_rows(conn)
    finally:
        conn.close()
    ok, msg = verify(rows)
    print(msg)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
