import logging
from pathlib import Path

import pytest

from src.agents.skill_manifest import SkillManifestError
from src.agents.skill_loader import (RESERVED_NODE_NAMES, SKILLS_DIR,
                                     load_skill_specs, render_worker_block)


def _write_skill(root: Path, name: str, frontmatter: str,
                 prose: str = "Bạn là trợ lý kho.") -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n{prose}\n",
                                encoding="utf-8")
    return d


_OK = 'name: {n}\ndescription: "Dùng khi THỰC HIỆN {n}. KHÔNG dùng khi: chỉ HỎI về {n}."'


def test_skills_dir_is_backend_skills_and_cwd_independent():
    # Suy từ __file__ chứ KHÔNG từ cwd: run.py chạy với cwd=backend/, pytest
    # chạy với cwd=backend/, nhưng jobs/CLI có thể chạy từ gốc repo.
    assert SKILLS_DIR.name == "skills"
    assert SKILLS_DIR.parent.name == "backend"


def test_load_returns_specs_sorted_by_name(tmp_path):
    _write_skill(tmp_path, "nhap-kho", _OK.format(n="nhap-kho"))
    _write_skill(tmp_path, "giao-hang", _OK.format(n="giao-hang"))
    specs = load_skill_specs(tmp_path)
    assert [s.name for s in specs] == ["giao-hang", "nhap-kho"]


def test_load_empty_dir_returns_empty(tmp_path):
    assert load_skill_specs(tmp_path) == []


def test_load_missing_dir_returns_empty(tmp_path):
    assert load_skill_specs(tmp_path / "khong-ton-tai") == []


def test_reject_name_colliding_with_tier1_node(tmp_path):
    _write_skill(tmp_path, "erp_read", "name: erp_read\ndescription: Dùng khi X.")
    with pytest.raises(SkillManifestError, match="kebab-case"):
        load_skill_specs(tmp_path)


def test_reject_name_in_reserved_set(tmp_path):
    # "mixed" là kebab-case hợp lệ NHƯNG trùng tên một node tier-1.
    _write_skill(tmp_path, "mixed", "name: mixed\ndescription: Dùng khi X.")
    with pytest.raises(SkillManifestError, match="trùng tên node tier-1"):
        load_skill_specs(tmp_path)


def test_reserved_set_covers_every_tier1_node():
    from src.agents.write_registry import WRITE_COORDINATORS
    assert {"intent_router", "erp_read", "erp_write", "rag", "mixed", "unknown",
            "erp_write_planner", "erp_write_executor", "respond_unknown",
            "write_continuation", "agentic_context_sync"} <= RESERVED_NODE_NAMES
    assert {s.node for s in WRITE_COORDINATORS.values()} <= RESERVED_NODE_NAMES


def test_reject_entry_file_missing(tmp_path):
    _write_skill(tmp_path, "bao-gia", """
name: bao-gia
description: "Dùng khi X. KHÔNG dùng khi: Y."
entry: logic.py
declares_tools: [create_discount_quote]
""".strip())
    with pytest.raises(SkillManifestError, match="entry 'logic.py' không tồn tại"):
        load_skill_specs(tmp_path)


def test_warns_but_loads_when_description_lacks_negative_clause(tmp_path, caplog):
    _write_skill(tmp_path, "giao-hang",
                 "name: giao-hang\ndescription: Dùng khi giao hàng.")
    with caplog.at_level(logging.WARNING):
        specs = load_skill_specs(tmp_path)
    assert [s.name for s in specs] == ["giao-hang"]      # VẪN NẠP
    assert "KHÔNG dùng khi" in caplog.text               # nhưng có cảnh báo


def test_render_worker_block_shape(tmp_path):
    _write_skill(tmp_path, "giao-hang", _OK.format(n="giao-hang"))
    _write_skill(tmp_path, "nhap-kho", _OK.format(n="nhap-kho"))
    block = render_worker_block(load_skill_specs(tmp_path))
    assert "worker: giao-hang" in block
    assert "worker: nhap-kho" in block
    assert "mô tả: Dùng khi THỰC HIỆN giao-hang." in block
    # thứ tự tất định — cùng thứ tự với load_skill_specs
    assert block.index("worker: giao-hang") < block.index("worker: nhap-kho")


def test_render_worker_block_empty_when_no_skills():
    assert render_worker_block([]) == ""
