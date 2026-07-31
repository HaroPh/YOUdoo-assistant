from pathlib import Path

import pytest

from src.agents.skill_manifest import (DEFAULT_MAX_STEPS, SkillManifestError,
                                       parse_skill_md)


def _write_skill(root: Path, name: str, frontmatter: str,
                 prose: str = "Bạn là trợ lý kho.") -> Path:
    """Dựng một thư mục skill giả trong tmp_path. Trả về đường dẫn SKILL.md."""
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    p = d / "SKILL.md"
    p.write_text(f"---\n{frontmatter}\n---\n\n{prose}\n", encoding="utf-8")
    return p


def test_parse_minimal_declarative_skill(tmp_path):
    p = _write_skill(tmp_path, "giao-hang", """
name: giao-hang
description: >-
  Dùng khi người dùng muốn THỰC HIỆN quy trình giao hàng.
  KHÔNG dùng khi: người dùng chỉ HỎI về quy trình.
tools:
  read: [get_sale_order_detail]
  write:
    - name: deliver_order
      confirm: "Xác nhận GIAO HÀNG cho đơn bán {order_ref}?"
""".strip(), prose="Bạn là trợ lý kho.\nQuy trình: 1. ...")
    spec = parse_skill_md(p)
    assert spec.name == "giao-hang"
    assert "KHÔNG dùng khi" in spec.description
    assert spec.prose.startswith("Bạn là trợ lý kho.")
    assert spec.read_tools == ("get_sale_order_detail",)
    assert len(spec.write_tools) == 1
    assert spec.write_tools[0].name == "deliver_order"
    assert spec.write_tools[0].confirm == "Xác nhận GIAO HÀNG cho đơn bán {order_ref}?"
    assert spec.write_tools[0].fixed_args == {}
    assert spec.entry is None
    assert spec.max_steps == DEFAULT_MAX_STEPS
    assert spec.dir == p.parent


def test_reject_missing_name(tmp_path):
    p = _write_skill(tmp_path, "x", 'description: "Dùng khi X. KHÔNG dùng khi: Y."')
    with pytest.raises(SkillManifestError, match="thiếu 'name'"):
        parse_skill_md(p)


def test_reject_missing_description(tmp_path):
    p = _write_skill(tmp_path, "x", "name: x")
    with pytest.raises(SkillManifestError, match="thiếu 'description'"):
        parse_skill_md(p)


def test_reject_name_not_matching_directory(tmp_path):
    p = _write_skill(tmp_path, "giao-hang", "name: nhap-kho\ndescription: Dùng khi X.")
    with pytest.raises(SkillManifestError, match="phải khớp tên thư mục"):
        parse_skill_md(p)


def test_reject_name_not_kebab_case(tmp_path):
    p = _write_skill(tmp_path, "Giao_Hang", "name: Giao_Hang\ndescription: Dùng khi X.")
    with pytest.raises(SkillManifestError, match="kebab-case"):
        parse_skill_md(p)


def test_reject_both_write_and_entry(tmp_path):
    p = _write_skill(tmp_path, "x", """
name: x
description: Dùng khi X.
entry: logic.py
declares_tools: [t]
tools:
  write:
    - name: deliver_order
      confirm: "Xác nhận {order_ref}?"
""".strip())
    with pytest.raises(SkillManifestError, match="hai đường sinh tool"):
        parse_skill_md(p)


def test_reject_entry_without_declares_tools(tmp_path):
    p = _write_skill(tmp_path, "x", "name: x\ndescription: Dùng khi X.\nentry: logic.py")
    with pytest.raises(SkillManifestError, match="phải đi CÙNG NHAU"):
        parse_skill_md(p)


def test_reject_declares_tools_without_entry(tmp_path):
    p = _write_skill(tmp_path, "x",
                     "name: x\ndescription: Dùng khi X.\ndeclares_tools: [t]")
    with pytest.raises(SkillManifestError, match="phải đi CÙNG NHAU"):
        parse_skill_md(p)


def test_reject_max_steps_above_cap(tmp_path):
    p = _write_skill(tmp_path, "x", "name: x\ndescription: Dùng khi X.\nmax_steps: 26")
    with pytest.raises(SkillManifestError, match="vượt trần cứng 25"):
        parse_skill_md(p)


def test_accept_max_steps_at_cap(tmp_path):
    p = _write_skill(tmp_path, "x", "name: x\ndescription: Dùng khi X.\nmax_steps: 25")
    assert parse_skill_md(p).max_steps == 25


def test_reject_write_tool_missing_confirm(tmp_path):
    p = _write_skill(tmp_path, "x", """
name: x
description: Dùng khi X.
tools:
  write:
    - name: deliver_order
""".strip())
    with pytest.raises(SkillManifestError, match="thiếu 'confirm'"):
        parse_skill_md(p)


def test_reject_confirm_with_positional_placeholder(tmp_path):
    p = _write_skill(tmp_path, "x", """
name: x
description: Dùng khi X.
tools:
  write:
    - name: deliver_order
      confirm: "Xác nhận {}?"
""".strip())
    with pytest.raises(SkillManifestError, match="placeholder không tên"):
        parse_skill_md(p)


def test_reject_confirm_with_attribute_access(tmp_path):
    p = _write_skill(tmp_path, "x", """
name: x
description: Dùng khi X.
tools:
  write:
    - name: deliver_order
      confirm: "Xác nhận {order.ref}?"
""".strip())
    with pytest.raises(SkillManifestError, match="chỉ được nội suy TÊN tham số"):
        parse_skill_md(p)


def test_reject_missing_frontmatter(tmp_path):
    d = tmp_path / "x"
    d.mkdir()
    p = d / "SKILL.md"
    p.write_text("Bạn là trợ lý kho.\n", encoding="utf-8")
    with pytest.raises(SkillManifestError, match="thiếu frontmatter"):
        parse_skill_md(p)


def test_reject_empty_prose(tmp_path):
    p = _write_skill(tmp_path, "x", "name: x\ndescription: Dùng khi X.", prose="")
    with pytest.raises(SkillManifestError, match="thiếu phần prose"):
        parse_skill_md(p)


def test_fixed_args_parsed(tmp_path):
    p = _write_skill(tmp_path, "nhap-kho", """
name: nhap-kho
description: "Dùng khi X. KHÔNG dùng khi: Y."
tools:
  write:
    - name: flag_order_for_review
      confirm: 'Xác nhận GHI CHÚ lên đơn mua {order_ref}: "{note}"?'
      fixed_args:
        model: purchase.order
""".strip())
    spec = parse_skill_md(p)
    assert spec.write_tools[0].fixed_args == {"model": "purchase.order"}
