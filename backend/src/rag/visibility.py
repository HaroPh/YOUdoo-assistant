"""Lớp hiển thị của chunk RAG và cách vai mở/đóng lớp (spec 2026-09-20 §3).

Nhãn trong DB là LỚP ('all' | 'commercial'), không phải danh sách vai — thêm
vai mới là sửa code (RoleCfg), không backfill DB. Vai biết lớp, lớp không
biết vai: module này KHÔNG import src.agents.
"""
import re

VISIBILITY_CLASSES = frozenset({"all", "commercial"})
DEFAULT_VISIBILITY = frozenset({"all"})

# Khoá theo BASENAME — cùng cách retrieval_cases.py neo nhãn. Tệp không có ở
# đây → 'all'. Migration 009 lặp lại bốn tên này trong SQL; test hợp đồng
# (tests/rag/test_migration_009_contract.py) giữ hai nguồn không trôi.
DOC_VISIBILITY = {
    "discount_policy.docx": "commercial",
    "bang_gia.xlsx": "commercial",
    "payment_policy.docx": "commercial",
    "sla.docx": "commercial",
}


class _Unrestricted:
    """Sentinel 'không lọc'. KHÔNG phải None: None là 'mất vai' → fail-closed.
    Một caller lỡ viết `visibility=cfg.rag_visibility if cfg else None` phải
    rơi về THẤY ÍT NHẤT — đúng chiều ngược với lỗ mục 17b."""
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNRESTRICTED"


UNRESTRICTED = _Unrestricted()

_SEP = re.compile(r"[\\/]")


def basename(source_file: str) -> str:
    """Tách trên CẢ '/' lẫn '\\' — source_file trong DB lẫn hai dấu, và
    os.path.basename trên Linux không hiểu '\\'."""
    return _SEP.split(source_file)[-1]


def class_for(source_file: str) -> str:
    return DOC_VISIBILITY.get(basename(source_file), "all")


def resolve(visibility) -> frozenset | _Unrestricted:
    """None/rỗng → DEFAULT_VISIBILITY. Chỉ đúng đối tượng UNRESTRICTED mới mở."""
    if visibility is UNRESTRICTED:
        return UNRESTRICTED
    if isinstance(visibility, _Unrestricted):
        return DEFAULT_VISIBILITY
    return frozenset(visibility) if visibility else DEFAULT_VISIBILITY
