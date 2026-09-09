"""Điền `chunk_text_fold` cho chunk đã có sau khi chạy migration 008.

VÌ SAO CẦN: `chunk_text_fold` được ghi lúc INGEST, nên corpus có sẵn từ trước
migration sẽ để cột đó NULL. Chân từ vựng bỏ dấu khi ấy **im lặng không làm
gì** trên đúng những chunk đó — đúng lớp lỗi "thành phần âm thầm không làm
điều tên nó nói" mà dự án này đã trả giá bốn lần.

VÌ SAO KHÔNG BẢO "xoá rag_documents rồi nạp lại": nạp lại phải nhúng lại toàn
bộ corpus (hàng phút GPU) và tốn hạn mức nếu dùng embedder trả phí, trong khi
việc cần làm chỉ là điền MỘT cột dẫn xuất từ `chunk_text` đã có sẵn. Đo trên
corpus 4.870 chunk: script này chạy ~17 giây.

Dùng ĐÚNG hàm mà ingest dùng (`fold_vi(index_text(...))`) — không chép lại
công thức, vì hai bản chép tay sẽ lệch nhau.

Chạy:  python -m tools.backfill_chunk_text_fold [--tat-ca]
       --tat-ca  ghi đè CẢ chunk đã có giá trị (dùng khi đổi `fold_vi`)
"""
import sys
import time

from src.rag import db as _db
from src.rag.chunking import fold_vi, index_text
from src.rag.config import RAG_SCHEMA


def main(argv: list[str]) -> None:
    tat_ca = "--tat-ca" in argv
    dieu_kien = "" if tat_ca else " WHERE chunk_text_fold IS NULL"
    conn = _db.connect()
    try:
        _db.ensure_schema(conn, RAG_SCHEMA)
        rows = conn.execute(
            f"SELECT id, section_path, chunk_text FROM rag_chunks{dieu_kien}"
        ).fetchall()
        if not rows:
            print("không chunk nào cần điền — xong.")
            return
        print(f"điền {len(rows)} chunk"
              f"{' (GHI ĐÈ tất cả)' if tat_ca else ''}...", flush=True)
        t0 = time.time()
        for cid, section_path, chunk_text in rows:
            conn.execute("UPDATE rag_chunks SET chunk_text_fold=%s WHERE id=%s",
                         (fold_vi(index_text(section_path, chunk_text)), cid))
        conn.commit()
        con_thieu = conn.execute(
            "SELECT count(*) FROM rag_chunks WHERE chunk_text_fold IS NULL"
        ).fetchone()[0]
        print(f"xong {len(rows)} chunk trong {time.time() - t0:.0f}s; "
              f"còn NULL: {con_thieu}")
        # To tiếng khi vẫn còn sót: im lặng ở đây nghĩa là chân bỏ dấu chạy
        # một nửa corpus mà không ai biết.
        if con_thieu:
            print(f"LỖI  vẫn còn {con_thieu} chunk NULL sau khi điền")
            sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main(sys.argv)
