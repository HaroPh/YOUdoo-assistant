import os
import re
import unicodedata

import tiktoken

from .config import (CHUNK_SIZE_TOKENS, CHUNK_OVERLAP_TOKENS, MIN_CHUNK_TOKENS,
                     TIKTOKEN_ENCODING)

_enc = tiktoken.get_encoding(TIKTOKEN_ENCODING)
_SENT_RE = re.compile(r"(?<=[.!?…])\s+")

# Bậc xuất xứ, tăng = kém tin cậy hơn. Thứ tự là CHÍNH SÁCH, chủ dự án xác
# nhận 2026-09-11 (spec OCR bậc 3 §"Xuất xứ"): `vision_verified` (VLM đọc số,
# số học đã kiểm) đứng DƯỚI mọi bậc Tesseract-thuần vì vẫn là LLM viết chữ số
# — thật về xuất xứ; `vision_unverified` (VLM đọc, không kiểm được) chỉ trên
# `vision_description` (mô tả hình, không có số để kiểm).
_XUAT_XU_RANK = {"text": 0, "ocr": 1, "ocr_repaired": 2, "vision_verified": 3,
                 "vision_unverified": 4, "vision_description": 5}


def fold_vi(text: str) -> str:
    """Bỏ dấu tiếng Việt: `Đầu tư` -> `dau tu`. Dùng ở CẢ ingest lẫn truy vấn.

    Vì sao cần: đo 2026-09-08 trên bộ vàng 64 ca — truy vấn gõ KHÔNG DẤU cho
    `recall@20 = 1/64 = 0,0156`, và không phải trả về rỗng mà trả về SAI HẲN.
    Người dùng thật của Youdoo CÓ gõ không dấu (chủ dự án xác nhận). Bỏ dấu cả
    hai phía làm phép khớp mặt chữ BẤT BIẾN với dấu: BM25 trên text bỏ dấu cho
    đúng 0,7188 ở cả ba dạng gõ (có dấu / nửa dấu / không dấu).

    `đ`/`Đ` phải map tay: chúng là CHỮ CÁI riêng (U+0111/U+0110), không phải
    `d` + dấu tổ hợp, nên `NFD` không tách chúng ra. Bỏ sót chỗ này thì
    `Đầu tư` thành `dau tu` ở một phía và `đau tu` ở phía kia — đã cắn một lần
    khi đo, làm phép đo báo 0/181 nhãn đọc đúng trong khi thật ra là 91,7%.

    KHÔNG dùng cho embedding: nhúng chính text bỏ dấu đã đo được là 0,4531 —
    tệ hơn cả BM25 — vì dấu tiếng Việt mang nghĩa và BGE-M3 dựa vào nó.
    """
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn").lower()
# Hạng của một `source_kind` LẠ (viết hoa nhầm "OCR", thừa dấu cách "ocr ",
# hay một bậc mới gõ sai) — phải là hạng KÉM TIN CẬY NHẤT hiện có, không phải
# hạng của "text" (0). `.get(k, 0)` từng lùi giá trị lạ về 0, tức về "text" —
# ĐẢO NGƯỢC đúng quy tắc hàm này tồn tại để làm tường minh: một giá trị không
# nhận ra được sẽ ÂM THẦM THĂNG HẠNG TIN CẬY thay vì hạ hạng. Trường này là
# chiều tin cậy cho retrieval và chống injection gián tiếp (spec
# 2026-09-04-tang-ocr §8) nên chiều sai duy nhất được phép là "kém tin cậy
# hơn thực tế", không bao giờ ngược lại.
_XUAT_XU_RANK_LA = max(_XUAT_XU_RANK.values())


def _gop_bi_quan(items: list[tuple[str, str, float | None]]) -> tuple[str, float | None]:
    """Bậc xuất xứ THẤP TIN CẬY NHẤT + `ocr_conf` NHỎ NHẤT trong nhóm.

    Ghi thành hàm riêng vì đây đúng loại quyết định hay bị quyết ngầm và quyết
    sai: trộn một câu đọc-từ-ảnh vào một chunk văn bản sạch thì cả chunk chỉ
    đáng tin bằng phần yếu nhất (spec 2026-09-04-tang-ocr §8)."""
    kind = "text"
    kind_rank = _XUAT_XU_RANK["text"]
    for _text, k, _conf in items:
        k_rank = _XUAT_XU_RANK.get(k, _XUAT_XU_RANK_LA)
        if k_rank > kind_rank:
            kind, kind_rank = k, k_rank
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
    # `path_stack` mang theo XUẤT XỨ của chính dòng tiêu đề (level, text,
    # source_kind, ocr_conf) — không chỉ (level, text) như trước 2026-09-05.
    # Lý do: `crumb` dựng từ stack này thành `section_path`, và
    # `index_text()` nối `section_path` vào CHUỖI ĐEM ĐI EMBED/`ts_vector`
    # của MỌI chunk trong mục — nên nếu chữ tiêu đề đọc được bằng ảnh (trang
    # scan mang tiêu đề, thân ở trang khác có lớp text), độ tin cậy của nó
    # phải lan vào từng chunk của mục, không được vứt đi (review toàn nhánh
    # A4, spec 2026-09-04-tang-ocr §8).
    path_stack: list[tuple[int, str, str, float | None]] = []
    sections: list[tuple[str, int | None, list[tuple[str, float | None]],
                         list[tuple[str, bool, str, float | None]]]] = []
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
            crumb = " › ".join(t for _, t, _, _ in path_stack)
            heading_xuat_xu = [(xx, c) for _, _, xx, c in path_stack]
            sections.append((crumb, cur_page, heading_xuat_xu, cur_body[:]))

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
            path_stack.append((lvl, b["text"], xuat_xu, conf))
            cur_page = b["page"]
        else:
            if cur_page is None:
                cur_page = b["page"]
            cur_body.append((b["text"], atomic, xuat_xu, conf))
    _flush()

    out: list[dict] = []
    idx = 0
    for section_path, page, heading_xuat_xu, body in sections:
        # Tách thành các RUN: văn xuôi liên tục (không atomic) hoặc một
        # block atomic đứng riêng — atomic KHÔNG được gộp với run liền kề dù
        # cộng dồn vẫn dưới CHUNK_SIZE_TOKENS (spec 2026-09-04-b4 §3.5).
        # (text, source_kind, ocr_conf) cho từng mảnh sắp phát ra.
        pieces: list[tuple[str, str, float | None]] = []
        run: list[tuple[str, str, float | None]] = []
        # Xuất xứ của các tiêu đề bao quanh mục (crumb rỗng nếu không có
        # tiêu đề nào) — "" làm text vì `_gop_bi_quan` chỉ đọc kind/conf.
        # Trộn vào MỌI run/atomic của mục: `section_path` đi vào
        # `index_text()` cùng từng mảnh, nên độ tin cậy phải bi quan theo cả
        # tiêu đề, không chỉ theo thân (review toàn nhánh A4).
        heading_items = [("", xx, c) for xx, c in heading_xuat_xu]

        def _xa_run():
            if not run:
                return
            joined = " ".join(t for t, _k, _c in run).strip()
            if joined:
                kind, conf = _gop_bi_quan(run + heading_items)
                manh = ([joined] if count_tokens(joined) <= MIN_CHUNK_TOKENS
                        else _split_section_text(joined))
                # Mọi mảnh cắt ra từ cùng một run thừa hưởng cùng xuất xứ: run
                # là MỘT khối văn bản liền, cắt nó không làm phần nào sạch hơn.
                pieces.extend((m, kind, conf) for m in manh)
            run.clear()

        for text, atomic, xuat_xu, conf in body:
            if atomic:
                _xa_run()
                kind, mconf = _gop_bi_quan([(text, xuat_xu, conf)] + heading_items)
                pieces.append((text, kind, mconf))
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
