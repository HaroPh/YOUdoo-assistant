"""Câu từ chối khi tài liệu bị chặn theo vai (spec 2026-09-21 §4).

Tầng: rag_access → roles → visibility, không chiều ngược. Tên phòng ban SUY
từ `RoleCfg.rag_visibility` — thêm vai/lớp mới thì tự đúng, không có bảng khai
tay để trôi khỏi sự thật (lớp lỗi README gọi tên).
"""
from .roles import load_profile
from src.rag.visibility import UNRESTRICTED

DENIED_MARKER = "không được xem"   # probe sống + eval bắt marker này, không bắt số %


def departments_for(classes: frozenset, profile: dict | None = None) -> list[str]:
    """Tên hiển thị của các vai được xem ít nhất một lớp trong `classes`, theo
    thứ tự khai trong profile. Admin là UNRESTRICTED (không phải tập) → tự loại."""
    profile = load_profile() if profile is None else profile
    names: list[str] = []
    for cfg in profile.values():
        vis = cfg.rag_visibility
        if vis is UNRESTRICTED:
            continue
        if classes & vis and cfg.label not in names:
            names.append(cfg.label)
    return names


def denied_message(role_cfg, classes: frozenset, profile: dict | None = None) -> str:
    """Chuỗi TẤT ĐỊNH — không LLM, không footer trích dẫn (spec §5)."""
    role_label = f"vai {role_cfg.label}" if role_cfg is not None else "vai hiện tại"
    depts = departments_for(classes, profile)
    if not depts:
        return f"{role_label[0].upper()}{role_label[1:]} {DENIED_MARKER} tài liệu về việc này."
    scope = " / ".join(depts)
    ask = " hoặc ".join(depts)
    return (f"Tài liệu về việc này thuộc phạm vi {scope}; {role_label} {DENIED_MARKER}. "
            f"Bạn có thể hỏi trực tiếp phòng {ask}.")
