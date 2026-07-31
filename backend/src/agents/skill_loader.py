# backend/src/agents/skill_loader.py
"""Nạp SOP skill dạng thư mục (backend/skills/<tên>/SKILL.md) thành node graph.

Biên giới thẩm quyền — toàn bộ mô hình trong một câu:

    Sửa SKILL.md chỉ có thể thay đổi THỨ TỰ và ĐIỀU KIỆN gọi những tool đã
    được gate sẵn — không bao giờ thêm được thẩm quyền mới.

Cụ thể: markdown KHÔNG BAO GIỜ định nghĩa tool mới. Tool ghi luôn là wrapper do
chính file này sinh, luôn bọc _confirm_write, và schema tham số CHÉP TỪ tool
MCP thật chứ không do markdown khai. Prose bảo model "bỏ qua xác nhận" là vô
hiệu — gate nằm trong Python, không nằm trong prose.

Chạy đúng MỘT LẦN lúc build_graph()."""
import importlib.util
import logging
import sys
from pathlib import Path

from .skill_manifest import (MISSING_NEGATIVE_WARNING, SkillManifestError,
                             SkillSpec, parse_skill_md)
from .write_registry import WRITE_COORDINATORS

logger = logging.getLogger(__name__)

# Suy từ __file__ (backend/src/agents/skill_loader.py → backend/skills), KHÔNG
# từ cwd: run.py chạy với cwd=backend/, nhưng `python -m jobs run ...` có thể
# chạy từ gốc repo.
SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

# Tên node SOP không được trùng bất kỳ node tier-1 nào (5 intent + các node
# hạ tầng + coordinator ghi). Trùng là lỗi cấu hình làm hỏng bảng định tuyến,
# không phải chuyện thẩm mỹ.
RESERVED_NODE_NAMES = frozenset({
    "intent_router", "erp_read", "erp_write", "rag", "mixed", "unknown",
    "erp_write_planner", "erp_write_executor", "respond_unknown",
    "write_continuation", "agentic_context_sync",
}) | {spec.node for spec in WRITE_COORDINATORS.values()}


def load_skill_specs(skills_dir: Path | None = None) -> list[SkillSpec]:
    """Quét <skills_dir>/*/SKILL.md → list[SkillSpec] đã validate, sắp theo name.

    Thư mục không tồn tại / rỗng → []. Mọi vi phạm THẨM QUYỀN hoặc cấu trúc →
    SkillManifestError (app không lên). Ngoại lệ duy nhất: description thiếu vế
    "KHÔNG dùng khi" chỉ log WARNING và vẫn nạp — xem docstring skill_manifest."""
    root = Path(skills_dir) if skills_dir is not None else SKILLS_DIR
    if not root.is_dir():
        return []

    specs: list[SkillSpec] = []
    seen: dict[str, Path] = {}
    for md in sorted(root.glob("*/SKILL.md")):
        spec = parse_skill_md(md)
        if spec.name in RESERVED_NODE_NAMES:
            raise SkillManifestError(
                f"{md}: skill {spec.name!r} trùng tên node tier-1 — "
                "bảng định tuyến không phân biệt được")
        if spec.name in seen:
            raise SkillManifestError(
                f"{md}: skill {spec.name!r} trùng tên với {seen[spec.name]}")
        if spec.entry and not (spec.dir / spec.entry).is_file():
            raise SkillManifestError(
                f"{md}: entry {spec.entry!r} không tồn tại trong {spec.dir}")
        if "KHÔNG dùng khi" not in spec.description:
            logger.warning(MISSING_NEGATIVE_WARNING, spec.name)
        seen[spec.name] = md
        specs.append(spec)

    specs.sort(key=lambda s: s.name)
    return specs


def render_worker_block(specs) -> str:
    """Khối mô tả worker TRUNG LẬP (hợp đồng §8 với SP-2b).

    SP-2a: intent_router tiêu thụ khối này (nối vào cuối prompt).
    SP-2b: supervisor tiêu thụ CÙNG khối đó; intent_router bị hấp thụ.
    Khối cố ý không nhắc gì tới 'intent' hay 'router' để 5 intent tier-1 sau
    này khai báo được cùng dạng — nếu không, SP-2b sẽ phải gộp hai danh sách
    worker."""
    if not specs:
        return ""
    entries = "\n\n".join(f"worker: {s.name}\nmô tả: {s.description}" for s in specs)
    return f"Danh sách worker quy trình nghiệp vụ (SOP):\n\n{entries}"
