import os
import re

import tiktoken

from .config import (CHUNK_SIZE_TOKENS, CHUNK_OVERLAP_TOKENS, MIN_CHUNK_TOKENS,
                     TIKTOKEN_ENCODING)

_enc = tiktoken.get_encoding(TIKTOKEN_ENCODING)
_SENT_RE = re.compile(r"(?<=[.!?…])\s+")

_XUAT_XU_RANK = {"text": 0, "ocr": 1, "vision_description": 2}


def _gop_bi_quan(items: list[tuple[str, str, float | None]]) -> tuple[str, float | None]:
    """Bậc xuất xứ THẤP TIN CẬY NHẤT + `ocr_conf` NHỎ NHẤT trong nhóm.

    Ghi thành hàm riêng vì đây đúng loại quyết định hay bị quyết ngầm và quyết
    sai: trộn một câu đọc-từ-ảnh vào một chunk văn bản sạch thì cả chunk chỉ
    đáng tin bằng phần yếu nhất (spec 2026-09-04-tang-ocr §8)."""
    kind = "text"
    for _text, k, _conf in items:
        if _XUAT_XU_RANK.get(k, 0) > _XUAT_XU_RANK[kind]:
            kind = k
    confs = [c for _text, _k, c in items if c is not None]
    return kind, (min(confs) if confs else None)


def count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def _split_section_text(text: str) -> list[str]:
    """Token-bounded windows over sentences, with overlap; never splits a sentence."""
    sentences = [s for s in _SENT_RE.split(text.strip()) if s]
    chunks: list[str] = []
    cur: list[str] = []
    cur_tok = 0
    for sent in sentences:
        st = count_tokens(sent)
        if cur and cur_tok + st > CHUNK_SIZE_TOKENS:
            chunks.append(" ".join(cur))
            # overlap: keep trailing sentences up to CHUNK_OVERLAP_TOKENS
            keep, ktok = [], 0
            for s in reversed(cur):
                kt = count_tokens(s)
                if ktok + kt > CHUNK_OVERLAP_TOKENS:
                    break
                keep.insert(0, s)
                ktok += kt
            cur, cur_tok = keep[:], ktok
        cur.append(sent)
        cur_tok += st
    if cur:
        chunks.append(" ".join(cur))
    return chunks or ([text.strip()] if text.strip() else [])


def index_text(section_path: str | None, chunk_text: str) -> str:
    """Chuỗi để embed/ts_vector/rerank — crumb + body, cho phép tìm theo
    heading (vd 'Điều 124'). chunk_text lưu DB giữ nguyên body-only
    (hiển thị/citation không đổi). Dùng ở đúng 3 nơi: ingest (embedding,
    ts_vector) và retrieve (rerank pairs) — spec 2026-07-15 §3C."""
    return " ".join(x for x in (section_path, chunk_text) if x)


def chunk_text_blocks(blocks: list[dict], *, doc_id: str, source_file: str) -> list[dict]:
    """Structure-aware: group body under its heading path, chunk within a leaf section only."""
    # `doc_title` lùi về TÊN TỆP, không phải đường dẫn đầy đủ và cũng không
    # phải rỗng: nó là cột metadata cho hiển thị/trích dẫn (`schema.sql`,
    # `retrieve.py` SELECT ra), KHÔNG đi vào `index_text()` lẫn `ts_vector`.
    # Giữ một nhãn đọc được thì có ích; giữ nguyên đường dẫn thì không.
    doc_title = next((b["text"] for b in blocks if b["heading_level"]),
                     os.path.basename(source_file))
    # Build (section_path, page, body) leaf sections in order. `body` mang
    # theo cờ atomic per-block (text, atomic) để giai đoạn sau tách RUN.
    path_stack: list[tuple[int, str]] = []  # (level, text)
    sections: list[tuple[str, int | None, list[tuple[str, bool, str, float | None]]]] = []
    cur_body: list[tuple[str, bool, str, float | None]] = []
    cur_page: int | None = None

    def _flush():
        if cur_body:
            # KHÔNG lùi về `doc_title`: `crumb` là thứ `index_text()` nối vào
            # chuỗi đem đi EMBED và vào `ts_vector`. Trước 2026-09-04 nó lùi
            # về `doc_title` (khi đó đang là `source_file`), nên đường dẫn
            # Windows bị nhúng vào vector của MỌI chunk trong tài liệu, giống
            # hệt nhau — vừa vô nghĩa vừa làm GIẢM khả năng phân biệt giữa
            # chính các chunk đó (spec 2026-08-29 mục 1.1). Không có phân cấp
            # thì breadcrumb phải RỖNG: "không biết" phải trông như không
            # biết. Lỗi này CHUNG cho mọi định dạng, không riêng .docx.
            crumb = " › ".join(t for _, t in path_stack)
            sections.append((crumb, cur_page, cur_body[:]))

    for b in blocks:
        atomic = bool(b.get("atomic"))
        xuat_xu = b.get("source_kind", "text")
        conf = b.get("ocr_conf")
        if b["heading_level"]:
            lvl = b["heading_level"]
            if not cur_body and path_stack and path_stack[-1][0] >= lvl:
                # Heading trước chưa có body mà đã bị heading cùng/cao cấp
                # ghi đè — dấu hiệu heading-detection sai (vd khoản luật bị
                # nhận nhầm) hoặc chuỗi tiêu đề sát nhau (Chương → tiêu đề IN
                # HOA). Giữ làm body: không bao giờ mất nội dung âm thầm
                # (spec 2026-07-15 §3B).
                if cur_page is None:
                    cur_page = b["page"]
                cur_body.append((b["text"], atomic, xuat_xu, conf))
                continue
            _flush()
            cur_body.clear()
            while path_stack and path_stack[-1][0] >= lvl:
                path_stack.pop()
            path_stack.append((lvl, b["text"]))
            cur_page = b["page"]
        else:
            if cur_page is None:
                cur_page = b["page"]
            cur_body.append((b["text"], atomic, xuat_xu, conf))
    _flush()

    out: list[dict] = []
    idx = 0
    for section_path, page, body in sections:
        # Tách thành các RUN: văn xuôi liên tục (không atomic) hoặc một
        # block atomic đứng riêng — atomic KHÔNG được gộp với run liền kề dù
        # cộng dồn vẫn dưới CHUNK_SIZE_TOKENS (spec 2026-09-04-b4 §3.5).
        # (text, source_kind, ocr_conf) cho từng mảnh sắp phát ra.
        pieces: list[tuple[str, str, float | None]] = []
        run: list[tuple[str, str, float | None]] = []

        def _xa_run():
            if not run:
                return
            joined = " ".join(t for t, _k, _c in run).strip()
            if joined:
                kind, conf = _gop_bi_quan(run)
                manh = ([joined] if count_tokens(joined) <= MIN_CHUNK_TOKENS
                        else _split_section_text(joined))
                # Mọi mảnh cắt ra từ cùng một run thừa hưởng cùng xuất xứ: run
                # là MỘT khối văn bản liền, cắt nó không làm phần nào sạch hơn.
                pieces.extend((m, kind, conf) for m in manh)
            run.clear()

        for text, atomic, xuat_xu, conf in body:
            if atomic:
                _xa_run()
                pieces.append((text, xuat_xu, conf))
            else:
                run.append((text, xuat_xu, conf))
        _xa_run()

        for piece, kind, conf in pieces:
            out.append({
                "doc_id": doc_id, "source_file": source_file, "doc_title": doc_title,
                "section_path": section_path, "page": page,
                "sheet": None, "row_range": None, "columns": None,
                "chunk_index": idx, "token_count": count_tokens(piece),
                "chunk_text": piece,
                "source_kind": kind, "ocr_conf": conf,
            })
            idx += 1
    return out


def chunk_xlsx_sheets(sheets: list[dict], *, doc_id: str, source_file: str) -> list[dict]:
    out: list[dict] = []
    idx = 0
    for sh in sheets:
        sheet, columns = sh["sheet"], sh["columns"]

        def _emit(text: str, row_range: str):
            nonlocal idx
            out.append({
                "doc_id": doc_id, "source_file": source_file, "doc_title": sheet,
                "section_path": None, "page": None,
                "sheet": sheet, "row_range": row_range, "columns": columns,
                "chunk_index": idx, "token_count": count_tokens(text),
                "chunk_text": text,
            })
            idx += 1

        _emit(f"[{sheet}] Bảng có các cột: {', '.join(columns)}.", "schema")
        for i, row in enumerate(sh["rows"], start=1):
            pairs = " | ".join(f"{col}: {val}" for col, val in zip(columns, row)
                               if val is not None)
            _emit(f"[{sheet}] {pairs}", f"row {i}")
    return out
