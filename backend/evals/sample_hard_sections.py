# backend/evals/sample_hard_sections.py
"""Lấy mẫu 45 nút cho HARD_EXPANSION_CASES — tất định, phân tầng, tái lập được.

Spec 2026-09-18 §4. Vì sao không chọn tay: tiền lệ trong dự án — 7 trang tự
chọn để dựng cổng đạt 1,000, 21 trang còn lại của CÙNG tài liệu chỉ 0,537.
Luật lọc rác và phép chọn nằm ở ĐÂY, chạy lại là ra đúng bộ đó.

    python -m evals.sample_hard_sections > evals/hard_expansion_sample.json
"""
import json
import math
import os
import re
import sys

from evals.hard_gate import SEP, leaf, tokens
from src.rag.chunking import fold_vi

SEED = 20260918

BUSINESS_DOCS = ("policy.docx", "discount_policy.docx", "payment_policy.docx",
                 "sla.docx", "sop.docx", "sales_process.docx", "warehouse_outbound.docx")
LAW_DOCS = ("boluat-danssu.pdf", "boluat-thuongmai.pdf", "boluat-laodong.pdf",
            "luat-doanhnghiep.pdf", "luat-quanlythue.pdf", "luat-baohiemxahoi.pdf",
            "luat-dautu.pdf", "luat-thuexuatnhapkhau.pdf", "luat-thuegtgt.pdf")
N_TOTAL = 45
N_BUSINESS_PER_DOC = 1        # mỗi tệp nghiệp vụ CÒN nút chưa gán nhãn; hết nút → 0

# Lá là quốc hiệu/tiêu ngữ/từ loại văn bản trần → không phải mục có nội dung.
_BOILERPLATE = frozenset({
    "quoc hoi", "cong hoa xa hoi chu nghia viet nam",
    "quoc hoi cong hoa xa hoi chu nghia viet nam",
    "doc lap tu do hanh phuc", "chu tich quoc hoi",
    "luat", "bo luat", "nghi dinh", "thong tu",
})
_FINANCIAL_REPORT_RE = re.compile(r"BaoCaoTaiChinh", re.IGNORECASE)


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", fold_vi(text).lower()).split())


def is_junk(basename: str, section_path: str) -> bool:
    """Luật lọc §4.1 — mọi điều kiện đều tất định, không có phán đoán."""
    if not section_path or not section_path.strip():
        return True
    if _FINANCIAL_REPORT_RE.search(basename):
        return True
    lf = leaf(section_path)
    if _norm(lf) in _BOILERPLATE:
        return True
    if len(tokens(lf)) < 3:
        return True
    return False


def allocate(counts: dict[str, int], k: int, floor: int = 1) -> dict[str, int]:
    """Chia k theo tỉ lệ counts, phần dư lớn nhất, mỗi tầng ≥ floor."""
    if k < len(counts) * floor:
        raise ValueError(
            f"k={k} nhỏ hơn số tầng ({len(counts)}) nhân sàn ({floor}) — "
            f"không có cách chia nào giữ được sàn ở mọi tầng.")
    total = sum(counts.values())
    quota = {d: counts[d] / total * k for d in counts}
    out = {d: max(floor, math.floor(quota[d])) for d in counts}
    rem = k - sum(out.values())
    if rem > 0:
        order = sorted(counts, key=lambda d: quota[d] - math.floor(quota[d]), reverse=True)
        for d in order:
            if rem == 0:
                break
            if math.floor(quota[d]) >= floor:      # tầng đã nhận sàn thì không cộng thêm
                out[d] += 1; rem -= 1
    while rem < 0:
        # Chỉ bớt ở tầng CÒN TRÊN sàn; nhờ điều kiện k >= len(counts)*floor ở
        # đầu hàm, tầng như vậy luôn tồn tại khi rem < 0.
        d = max((x for x in out if out[x] > floor), key=lambda x: (out[x], quota[x]))
        out[d] -= 1; rem += 1
    return out


def stride_pick(items: list, k: int, seed: int) -> list:
    """k phần tử tại floor(offset + i·N/k), offset = ((seed mod 1000)/1000)·N/k."""
    n = len(items)
    if k >= n:
        return list(items)
    step = n / k
    offset = ((seed % 1000) / 1000) * step
    return [items[math.floor(offset + i * step)] for i in range(k)]


def _basename(source_file: str) -> str:
    return os.path.basename(str(source_file).replace("\\", "/"))


# R1 (phán quyết controller 2026-09-18): KHÔNG dùng LIKE '%\' + basename để dò
# ngược ra source_file — dấu gạch chéo ngược là ký tự thoát mặc định của LIKE
# trong PostgreSQL, nên khớp được chỉ là trùng hợp. Thay vào đó, load_nodes()
# nạp sẵn ánh xạ basename → source_file ĐẦY ĐỦ (từ chính các dòng DISTINCT nó
# đã đọc), và load_chunk_text() truy vấn bằng so khớp CHÍNH XÁC (=). Chữ ký
# công khai load_chunk_text(conn, basename, section_path) giữ nguyên như đặc
# tả — module giữ ánh xạ này ở biến cấp module.
_SOURCE_FILE_BY_BASENAME: dict[str, str] = {}


def load_nodes(conn) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT DISTINCT source_file, section_path FROM rag_chunks "
        "WHERE section_path IS NOT NULL AND section_path <> ''").fetchall()
    for sf, _sp in rows:
        _SOURCE_FILE_BY_BASENAME[_basename(sf)] = sf
    return sorted({(_basename(sf), sp) for sf, sp in rows})


def load_chunk_text(conn, basename: str, section_path: str) -> str:
    source_file = _SOURCE_FILE_BY_BASENAME[basename]
    rows = conn.execute(
        "SELECT chunk_text FROM rag_chunks WHERE source_file = %s "
        "AND section_path = %s ORDER BY chunk_index",
        (source_file, section_path)).fetchall()
    return "\n".join(r[0] for r in rows)


def _labelled() -> set[tuple[str, str]]:
    # _CORE, KHÔNG phải RETRIEVAL_CASES: sau khi nối bộ mở rộng, 45 nút mới cũng
    # "đã có nhãn" và chạy lại script sẽ ra bộ KHÁC — mất tính tái lập.
    from evals.retrieval_cases import _CORE
    return {(f, s) for _q, exp, _d in _CORE for f, s in exp}


def build_sample(conn, seed: int = SEED) -> dict:
    used = _labelled()
    nodes = [(b, s) for b, s in load_nodes(conn)
             if not is_junk(b, s) and (b, s) not in used]
    by_doc: dict[str, list] = {}
    for b, s in nodes:
        by_doc.setdefault(b, []).append((b, s))
    picked: list[tuple[str, str]] = []
    allocation: dict[str, int] = {}
    for b in BUSINESS_DOCS:
        chosen = stride_pick(sorted(by_doc.get(b, [])), N_BUSINESS_PER_DOC, seed)
        picked += chosen; allocation[b] = len(chosen)
    law_counts = {b: len(by_doc.get(b, [])) for b in LAW_DOCS}
    law_alloc = allocate(law_counts, N_TOTAL - len(picked))
    for b in LAW_DOCS:
        chosen = stride_pick(sorted(by_doc.get(b, [])), law_alloc[b], seed)
        picked += chosen; allocation[b] = len(chosen)
    pool = {**{b: len(by_doc.get(b, [])) for b in BUSINESS_DOCS}, **law_counts}
    return {"seed": seed, "allocation": allocation, "pool_after_filter": pool,
            "nodes": [{"basename": b, "section_path": s,
                       "chunk_text": load_chunk_text(conn, b, s)} for b, s in picked]}


def main() -> None:
    from src.rag import db as _db
    conn = _db.connect()
    try:
        sample = build_sample(conn)
    finally:
        conn.close()
    for b, k in sample["allocation"].items():
        print(f"{b:<32} {k:>3}  (pool {sample['pool_after_filter'].get(b, '-')})", file=sys.stderr)
    print(f"tong {len(sample['nodes'])}", file=sys.stderr)
    print(json.dumps(sample, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
