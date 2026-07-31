import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.tools import tool as lc_tool

from src.agents.agentic_gate import REFUSED_MSG
from src.agents.skill_manifest import SkillManifestError, parse_skill_md
from src.agents.skill_loader import (RESERVED_NODE_NAMES, SKILLS_DIR,
                                     build_skill_tools, load_skill_specs,
                                     render_worker_block)


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


def _fake_mcp_tools():
    """Fake tool MCP có ghi nhận lệnh gọi — schema khai TRÙNG tool thật
    (deliver_order(order_ref), flag_order_for_review(model, order_ref, note))."""
    calls = {"deliver": [], "flag": []}

    @lc_tool("deliver_order")
    async def deliver_order(order_ref: str) -> str:
        """Xác nhận giao hàng vào Odoo cho một đơn bán ĐÃ XÁC NHẬN."""
        calls["deliver"].append({"order_ref": order_ref})
        return json.dumps({"ok": True, "display": "Đã giao hàng."}, ensure_ascii=False)

    @lc_tool("flag_order_for_review")
    async def flag_order_for_review(model: str, order_ref: str, note: str) -> str:
        """Ghi chú nội bộ lên đơn."""
        calls["flag"].append({"model": model, "order_ref": order_ref, "note": note})
        return json.dumps({"ok": True, "display": "Đã ghi chú."}, ensure_ascii=False)

    return [deliver_order, flag_order_for_review], calls


_GIAO_HANG = """
name: giao-hang
description: "Dùng khi THỰC HIỆN giao hàng. KHÔNG dùng khi: chỉ HỎI về quy trình."
tools:
  read: [get_sale_order_detail]
  write:
    - name: deliver_order
      confirm: "Xác nhận GIAO HÀNG cho đơn bán {order_ref}?"
""".strip()


def _spec(tmp_path, name, frontmatter):
    return parse_skill_md(_write_skill(tmp_path, name, frontmatter) / "SKILL.md")


@pytest.mark.asyncio
async def test_generated_wrapper_asks_exact_confirm_then_writes_once(tmp_path):
    spec = _spec(tmp_path, "giao-hang", _GIAO_HANG)
    mcp, calls = _fake_mcp_tools()
    tools = {t.name: t for t in build_skill_tools(spec, mcp)}
    assert set(tools) == {"ask_human", "get_sale_order_detail", "deliver_order"}

    asked = []

    def _yes(question):
        asked.append(question)
        return True

    with patch("src.agents.skill_loader._confirm_write", _yes):
        out = await tools["deliver_order"].ainvoke({"order_ref": "S00012"})

    assert asked == ["Xác nhận GIAO HÀNG cho đơn bán S00012?"]
    assert calls["deliver"] == [{"order_ref": "S00012"}]
    assert "Đã giao hàng." in out


@pytest.mark.asyncio
async def test_generated_wrapper_refuses_without_calling_mcp(tmp_path):
    spec = _spec(tmp_path, "giao-hang", _GIAO_HANG)
    mcp, calls = _fake_mcp_tools()
    tools = {t.name: t for t in build_skill_tools(spec, mcp)}

    with patch("src.agents.skill_loader._confirm_write", lambda q: False):
        out = await tools["deliver_order"].ainvoke({"order_ref": "S00012"})

    assert out == REFUSED_MSG
    assert calls["deliver"] == []       # KHÔNG một lệnh ghi nào chạm MCP


@pytest.mark.asyncio
async def test_fixed_args_merged_into_payload_and_hidden_from_model(tmp_path):
    spec = _spec(tmp_path, "nhap-kho", """
name: nhap-kho
description: "Dùng khi THỰC HIỆN nhập kho. KHÔNG dùng khi: chỉ HỎI về quy trình."
tools:
  write:
    - name: flag_order_for_review
      confirm: 'Xác nhận GHI CHÚ lên đơn mua {order_ref}: "{note}"?'
      fixed_args:
        model: purchase.order
""".strip())
    mcp, calls = _fake_mcp_tools()
    tools = {t.name: t for t in build_skill_tools(spec, mcp)}
    flag = tools["flag_order_for_review"]

    # model KHÔNG nằm trong schema model nhìn thấy. Dùng .args (không
    # .args_schema): .args trả dict properties cho CẢ hai hình dạng schema
    # (dict của tool MCP thật, và lớp pydantic của @tool trong test này).
    assert set(flag.args) == {"order_ref", "note"}

    asked = []
    with patch("src.agents.skill_loader._confirm_write",
               lambda q: (asked.append(q), True)[1]):
        await flag.ainvoke({"order_ref": "P00021", "note": "thiếu 2 cái"})

    # ...nhưng VẪN đi vào payload gửi MCP
    assert calls["flag"] == [{"model": "purchase.order", "order_ref": "P00021",
                              "note": "thiếu 2 cái"}]
    assert asked == ['Xác nhận GHI CHÚ lên đơn mua P00021: "thiếu 2 cái"?']


def test_reject_write_tool_absent_from_nonempty_mcp_registry(tmp_path):
    spec = _spec(tmp_path, "giao-hang", _GIAO_HANG)
    mcp, _ = _fake_mcp_tools()
    other = [t for t in mcp if t.name != "deliver_order"]
    with pytest.raises(SkillManifestError, match="deliver_order"):
        build_skill_tools(spec, other)


def test_empty_mcp_registry_builds_read_only_node(tmp_path):
    # Đường TEST (build_graph(tools=[])): không có hợp đồng MCP để đối chiếu →
    # không có tool ghi nào, và KHÔNG raise.
    spec = _spec(tmp_path, "giao-hang", _GIAO_HANG)
    names = {t.name for t in build_skill_tools(spec, [])}
    assert names == {"ask_human", "get_sale_order_detail"}


def test_reject_unknown_read_tool(tmp_path):
    spec = _spec(tmp_path, "giao-hang", """
name: giao-hang
description: "Dùng khi X. KHÔNG dùng khi: Y."
tools:
  read: [khong_co_tool_nay]
""".strip())
    with pytest.raises(SkillManifestError, match="khong_co_tool_nay"):
        build_skill_tools(spec, [])


def test_reject_confirm_placeholder_not_a_tool_param(tmp_path):
    spec = _spec(tmp_path, "giao-hang", """
name: giao-hang
description: "Dùng khi X. KHÔNG dùng khi: Y."
tools:
  write:
    - name: deliver_order
      confirm: "Xác nhận cho {khach_hang}?"
""".strip())
    mcp, _ = _fake_mcp_tools()
    with pytest.raises(SkillManifestError, match="khach_hang"):
        build_skill_tools(spec, mcp)


def test_reject_fixed_arg_not_a_tool_param(tmp_path):
    spec = _spec(tmp_path, "giao-hang", """
name: giao-hang
description: "Dùng khi X. KHÔNG dùng khi: Y."
tools:
  write:
    - name: deliver_order
      confirm: "Xác nhận {order_ref}?"
      fixed_args:
        khong_co: 1
""".strip())
    mcp, _ = _fake_mcp_tools()
    with pytest.raises(SkillManifestError, match="khong_co"):
        build_skill_tools(spec, mcp)


def test_entry_logic_py_tools_loaded(tmp_path):
    d = _write_skill(tmp_path, "bao-gia", """
name: bao-gia
description: "Dùng khi X. KHÔNG dùng khi: Y."
entry: logic.py
declares_tools: [create_discount_quote]
""".strip())
    (d / "logic.py").write_text(
        "from langchain_core.tools import tool\n"
        "def build_tools(mcp_tools):\n"
        "    @tool('create_discount_quote')\n"
        "    async def t(customer: str) -> str:\n"
        "        '''fake'''\n"
        "        return 'ok'\n"
        "    return [t]\n", encoding="utf-8")
    spec = parse_skill_md(d / "SKILL.md")
    names = {t.name for t in build_skill_tools(spec, [])}
    assert names == {"ask_human", "create_discount_quote"}


def test_reject_logic_py_returning_undeclared_tool(tmp_path):
    d = _write_skill(tmp_path, "bao-gia", """
name: bao-gia
description: "Dùng khi X. KHÔNG dùng khi: Y."
entry: logic.py
declares_tools: [create_discount_quote]
""".strip())
    (d / "logic.py").write_text(
        "from langchain_core.tools import tool\n"
        "def build_tools(mcp_tools):\n"
        "    @tool('create_discount_quote')\n"
        "    async def a(customer: str) -> str:\n"
        "        '''fake'''\n"
        "        return 'ok'\n"
        "    @tool('xoa_sach_don_hang')\n"
        "    async def b(x: str) -> str:\n"
        "        '''tool KHÔNG khai trong frontmatter'''\n"
        "        return 'ok'\n"
        "    return [a, b]\n", encoding="utf-8")
    spec = parse_skill_md(d / "SKILL.md")
    with pytest.raises(SkillManifestError, match="xoa_sach_don_hang"):
        build_skill_tools(spec, [])


def test_reject_logic_py_without_build_tools(tmp_path):
    d = _write_skill(tmp_path, "bao-gia", """
name: bao-gia
description: "Dùng khi X. KHÔNG dùng khi: Y."
entry: logic.py
declares_tools: [create_discount_quote]
""".strip())
    (d / "logic.py").write_text("X = 1\n", encoding="utf-8")
    spec = parse_skill_md(d / "SKILL.md")
    with pytest.raises(SkillManifestError, match="build_tools"):
        build_skill_tools(spec, [])
