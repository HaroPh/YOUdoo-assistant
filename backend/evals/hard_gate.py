# backend/evals/hard_gate.py
"""Thước "hard" tất định — spec 2026-09-18 §3.

overlap = |tokens(câu hỏi) ∩ tokens(lá tiêu đề)| / |tokens(lá)|. Đo trên 64 ca
cũ (2026-09-18): easy trung vị 0,67 / p25 0,60; hard trung vị 0,33 / p75 0,50.
Ngưỡng 0,40 loại 28/31 ca easy. Cổng CHỈ áp lên ca mới (HARD_EXPANSION_CASES):
vài ca hard cũ được gán bằng ngữ nghĩa, overlap tới 0,83.

Dùng ở hai nơi và PHẢI là cùng một hàm: agent viết câu tự kiểm, và test hợp
đồng gác lại. Đổi định nghĩa token/lá là đổi thước — số hiệu chỉnh phải đo lại.
"""
import re

from src.rag.chunking import fold_vi

SEP = " › "
HARD_MAX_OVERLAP = 0.40
_TOKEN_RE = re.compile(r"\w+")


def tokens(text: str) -> set[str]:
    """Tập token bỏ dấu, lower, bỏ token một ký tự (dấu câu, số điều lẻ)."""
    return {t for t in _TOKEN_RE.findall(fold_vi(text).lower()) if len(t) > 1}


def leaf(section_path: str) -> str:
    """Phần sau dấu › cuối — tiêu đề mục đích, không phải cả breadcrumb."""
    return section_path.split("›")[-1].strip()


def overlap(question: str, section_paths) -> float:
    """Max overlap của câu hỏi với lá của từng nhãn; 0.0 khi không có lá nào."""
    q = tokens(question)
    best = 0.0
    for sp in section_paths:
        lt = tokens(leaf(sp))
        if lt:
            best = max(best, len(q & lt) / len(lt))
    return best
