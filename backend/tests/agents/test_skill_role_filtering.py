# backend/tests/agents/test_skill_role_filtering.py
"""role-based-access, Task 8 (fix): skill SOP phải bị BỎ QUA khỏi graph của
một vai khi tool ghi nó cần bị bộ lọc vai (_filter_tools_for_role) loại bỏ,
KHÔNG được làm build_graph() crash — nhưng phải PHÂN BIỆT rõ với trường hợp
tool ghi thật sự không tồn tại ở đâu trong registry MCP (đó vẫn là lỗi cấu
hình, SkillManifestError vẫn phải ném như cũ).

Root cause của lỗi khởi động thật (logs/backend_err.log):
    SkillManifestError: skill 'nhap-kho': tool ghi 'flag_order_for_review'
    không có trong registry MCP
xảy ra vì ERPAgent.setup() build MỘT graph mỗi vai, lọc tool xuống tập vai
được phép TRƯỚC khi build_graph() nạp SOP — flag_order_for_review (và
deliver_order/create_quotation cho vai khác) bị lọc mất nên
skill_loader.build_skill_tools() coi như KHÔNG CÓ trong registry, ném lỗi y
hệt trường hợp gõ sai tên tool. Cơ chế mới (skill_loader.skill_role_gap,
gọi từ graph.py) tách hai trường hợp bằng cách so `tools` (đã lọc) với
`mcp_all_tools` (chưa lọc, plumb từ erp_agent.py qua build_graph)."""
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.tools import tool as lc_tool

from src.agents import roles
from src.agents.erp_agent import _filter_tools_for_role
from src.agents.graph import build_graph
from src.agents.skill_loader import load_skill_specs, skill_role_gap
from src.agents.skill_manifest import SkillManifestError, parse_skill_md


def _full_mcp_registry():
    """4 tool ghi mà 3 skill THẬT (backend/skills/) khai báo — mô phỏng
    registry MCP đầy đủ TRƯỚC khi erp_agent._filter_tools_for_role lọc theo
    vai (cùng bộ tool + schema với test_skill_loader.py's
    test_every_write_tool_in_a_skill_node_is_gated, tái dùng cho nhất quán).

    + 3 tool MAIL_DEPS (mail_write.py, Task 1 2026-08-12): registry MCP THẬT
    (erp_agent.py truyền raw_tools — mọi tool trước lọc vai) luôn có
    preview_template_email/send_prepared_email/discard_prepared_email, vì đó
    là tiền đề của chính lỗi Task 1 sửa. Thiếu chúng ở đây khiến
    tools_for_coordinator (write_registry.py) coi MỌI coordinator gửi mail —
    của MỌI vai, kể cả admin — là "dep không tồn tại ở đâu cả" (lỗi cấu
    hình thật) và raise, dù test file này không hề liên quan tới mail.

    + 1 tool find_my_activities (close-activity, Task 4 2026-08-14): CÙNG lý
    do trên — build_graph() (graph.py:92) lặp KHÔNG ĐIỀU KIỆN trên MỌI spec
    trong WRITE_COORDINATORS, kể cả close_activity, bất kể vai đang build có
    được cấp tool đó hay không. spec.deps={"find_my_activities"} mà thiếu ở
    registry đầy đủ này thì tools_for_coordinator coi là lỗi cấu hình thật và
    raise cho MỌI graph, dù test file này không hề liên quan tới close_activity."""
    @lc_tool("deliver_order")
    async def deliver_order(order_ref: str) -> str:
        """fake"""
        return "{}"

    @lc_tool("receive_order")
    async def receive_order(order_ref: str) -> str:
        """fake"""
        return "{}"

    @lc_tool("flag_order_for_review")
    async def flag_order_for_review(model: str, order_ref: str, note: str) -> str:
        """fake"""
        return "{}"

    @lc_tool("create_quotation")
    async def create_quotation(partner_id: int, lines: list) -> str:
        """fake"""
        return "{}"

    @lc_tool("preview_template_email")
    async def preview_template_email(template_name: str, res_model: str, ref: str) -> str:
        """fake"""
        return "{}"

    @lc_tool("send_prepared_email")
    async def send_prepared_email(mail_id: int) -> str:
        """fake"""
        return "{}"

    @lc_tool("discard_prepared_email")
    async def discard_prepared_email(mail_id: int) -> str:
        """fake"""
        return "{}"

    @lc_tool("find_my_activities")
    async def find_my_activities() -> str:
        """fake"""
        return "{}"

    return [deliver_order, receive_order, flag_order_for_review, create_quotation,
           preview_template_email, send_prepared_email, discard_prepared_email,
           find_my_activities]


def _graph_for_role(role_name, profile="small-business"):
    cfg = roles.PROFILES[profile][role_name]
    raw = _full_mcp_registry()
    tools = _filter_tools_for_role(raw, cfg)
    graph = build_graph(MagicMock(), tools, checkpointer=None, role_cfg=cfg,
                        mcp_all_tools=raw)
    return graph, cfg


# ── Unit: skill_role_gap trực tiếp ──────────────────────────────────────────

def _giao_hang_spec(tmp_path):
    d = tmp_path / "giao-hang"
    d.mkdir()
    (d / "SKILL.md").write_text(
        '---\nname: giao-hang\n'
        'description: "Dùng khi THỰC HIỆN giao hàng. KHÔNG dùng khi: chỉ HỎI."\n'
        'tools:\n  write:\n    - name: deliver_order\n'
        '      confirm: "Xác nhận GIAO HÀNG cho đơn bán {order_ref}?"\n'
        '---\n\nBạn là trợ lý kho.\n', encoding="utf-8")
    return parse_skill_md(d / "SKILL.md")


def test_skill_role_gap_none_when_role_cfg_missing(tmp_path):
    spec = _giao_hang_spec(tmp_path)
    raw = _full_mcp_registry()
    filtered = [t for t in raw if t.name != "deliver_order"]
    # Không truyền role_cfg — hành vi CŨ (không phân biệt gì, luôn None ở đây;
    # caller sẽ tự đi tiếp và build_skill_tools mới là chỗ raise).
    assert skill_role_gap(spec, filtered, raw, None) is None


def test_skill_role_gap_none_for_admin_unrestricted(tmp_path):
    spec = _giao_hang_spec(tmp_path)
    raw = _full_mcp_registry()
    admin_cfg = roles.PROFILES["small-business"]["admin"]
    # Admin không lọc — dù `tools` (giả lập) thiếu deliver_order, admin không
    # bao giờ kích hoạt cơ chế bỏ-qua (allowed_tools() is None).
    filtered = [t for t in raw if t.name != "deliver_order"]
    assert skill_role_gap(spec, filtered, raw, admin_cfg) is None


def test_skill_role_gap_none_when_no_full_registry_reference(tmp_path):
    spec = _giao_hang_spec(tmp_path)
    raw = _full_mcp_registry()
    cfg = roles.PROFILES["small-business"]["accounting"]
    filtered = [t for t in raw if t.name != "deliver_order"]
    # mcp_all_tools=None (đường test cũ, build_graph gọi không kèm nó) — không
    # có khả năng phân biệt nên KHÔNG bỏ qua, giữ hành vi trước Task này.
    assert skill_role_gap(spec, filtered, None, cfg) is None


def test_skill_role_gap_skips_when_tool_exists_but_role_filtered(tmp_path):
    """Ca CHÍNH của fix: deliver_order CÓ trong registry đầy đủ nhưng vai
    accounting không được cấp (other_dept) — phải trả lý do bỏ qua, KHÔNG
    phải None (tức không được để build_skill_tools raise ở đây)."""
    spec = _giao_hang_spec(tmp_path)
    raw = _full_mcp_registry()
    cfg = roles.PROFILES["small-business"]["accounting"]
    filtered = _filter_tools_for_role(raw, cfg)
    assert "deliver_order" not in {t.name for t in filtered}   # xác nhận tiền đề
    reason = skill_role_gap(spec, filtered, raw, cfg)
    assert reason is not None
    assert "deliver_order" in reason


def test_skill_role_gap_none_when_tool_genuinely_missing_everywhere(tmp_path):
    """Ca PHẢI KHÔNG bị nuốt: deliver_order không có ở CẢ registry đầy đủ lẫn
    registry đã lọc — đây là lỗi cấu hình thật (gõ sai tên/MCP chưa deploy
    tool), không phải chuyện phân quyền. skill_role_gap phải trả None để
    caller đi tiếp vào build_skill_tools() và ăn SkillManifestError."""
    spec = _giao_hang_spec(tmp_path)
    raw = [t for t in _full_mcp_registry() if t.name != "deliver_order"]
    cfg = roles.PROFILES["small-business"]["warehouse"]
    filtered = _filter_tools_for_role(raw, cfg)
    assert skill_role_gap(spec, filtered, raw, cfg) is None


def test_skill_role_gap_entry_based_skip_when_underlying_tool_role_filtered(tmp_path):
    """bao-gia-chiet-khau (entry: logic.py) không khai tên tool MCP gốc
    (create_quotation) trong declares_tools — chỉ khai tên WRAPPER
    (create_discount_quote) — nên skill_role_gap phải dựng thử build_tools()
    với cả hai registry để phát hiện gap, không so tên trực tiếp được."""
    d = tmp_path / "bao-gia"
    d.mkdir()
    (d / "SKILL.md").write_text(
        '---\nname: bao-gia\n'
        'description: "Dùng khi X. KHÔNG dùng khi: Y."\n'
        'entry: logic.py\ndeclares_tools: [create_discount_quote]\n'
        '---\n\nBạn là trợ lý bán hàng.\n', encoding="utf-8")
    (d / "logic.py").write_text(
        "from langchain_core.tools import tool\n"
        "def build_tools(mcp_tools):\n"
        "    by_name = {t.name: t for t in mcp_tools}\n"
        "    tools = []\n"
        "    if by_name.get('create_quotation') is not None:\n"
        "        @tool('create_discount_quote')\n"
        "        async def t(customer: str) -> str:\n"
        "            '''fake'''\n"
        "            return 'ok'\n"
        "        tools.append(t)\n"
        "    return tools\n", encoding="utf-8")
    spec = parse_skill_md(d / "SKILL.md")

    raw = _full_mcp_registry()               # CÓ create_quotation
    cfg = roles.PROFILES["small-business"]["warehouse"]
    filtered = _filter_tools_for_role(raw, cfg)   # KHÔNG có (other_dept)
    assert "create_quotation" not in {t.name for t in filtered}

    reason = skill_role_gap(spec, filtered, raw, cfg)
    assert reason is not None
    assert "create_discount_quote" in reason


def test_skill_role_gap_entry_based_none_when_role_has_the_tool(tmp_path):
    d = tmp_path / "bao-gia"
    d.mkdir()
    (d / "SKILL.md").write_text(
        '---\nname: bao-gia\n'
        'description: "Dùng khi X. KHÔNG dùng khi: Y."\n'
        'entry: logic.py\ndeclares_tools: [create_discount_quote]\n'
        '---\n\nBạn là trợ lý bán hàng.\n', encoding="utf-8")
    (d / "logic.py").write_text(
        "from langchain_core.tools import tool\n"
        "def build_tools(mcp_tools):\n"
        "    by_name = {t.name: t for t in mcp_tools}\n"
        "    tools = []\n"
        "    if by_name.get('create_quotation') is not None:\n"
        "        @tool('create_discount_quote')\n"
        "        async def t(customer: str) -> str:\n"
        "            '''fake'''\n"
        "            return 'ok'\n"
        "        tools.append(t)\n"
        "    return tools\n", encoding="utf-8")
    spec = parse_skill_md(d / "SKILL.md")

    raw = _full_mcp_registry()
    admin_cfg = roles.PROFILES["small-business"]["admin"]
    filtered = _filter_tools_for_role(raw, admin_cfg)   # admin: không lọc
    assert skill_role_gap(spec, filtered, raw, admin_cfg) is None


# ── Test 1 (yêu cầu task): vai thiếu tool ghi → không có node đó, build OK ──

def test_accounting_role_does_not_get_giao_hang_node_and_build_succeeds():
    graph, _ = _graph_for_role("accounting")
    assert graph is not None
    assert "giao-hang" not in set(graph.get_graph().nodes)


def test_accounting_role_does_not_get_nhap_kho_node():
    graph, _ = _graph_for_role("accounting")
    assert "nhap-kho" not in set(graph.get_graph().nodes)


def test_skipped_skill_has_no_route_edge_either():
    """'Bỏ qua SILENTLY ở tầng graph: không node, không route' — kiểm cả
    cạnh, không chỉ node, để một cạnh mồ côi trỏ vào node không tồn tại không
    lọt qua bài test chỉ nhìn node."""
    graph, _ = _graph_for_role("accounting")
    edges = [(e.source, e.target) for e in graph.get_graph().edges]
    assert not any(target in ("giao-hang", "nhap-kho") for _, target in edges)


def test_warehouse_role_gets_its_own_two_skills_but_not_sales_quote():
    """Sau Part 2 (flag_order_for_review → _WH_OWN): vai kho có ĐỦ cả 2 tool
    nhap-kho cần (receive_order + flag_order_for_review) và tool giao-hang
    cần (deliver_order) — cả hai skill phải nạp. bao-gia-chiet-khau (SOP báo
    giá — nghiệp vụ bán hàng, other_dept với vai kho) thì KHÔNG."""
    graph, cfg = _graph_for_role("warehouse")
    nodes = set(graph.get_graph().nodes)
    assert "giao-hang" in nodes
    assert "nhap-kho" in nodes
    assert "bao-gia-chiet-khau" not in nodes
    # Xác nhận tiền đề Part 2 thật sự có hiệu lực (không chỉ đúng ngẫu nhiên):
    assert "flag_order_for_review" in cfg.allowed_tools()
    assert "receive_order" in cfg.allowed_tools()


def test_accounting_role_gets_neither_warehouse_skill_nor_sales_quote():
    graph, _ = _graph_for_role("accounting")
    nodes = set(graph.get_graph().nodes)
    assert "giao-hang" not in nodes
    assert "nhap-kho" not in nodes
    assert "bao-gia-chiet-khau" not in nodes


# ── Test 2 (yêu cầu task): admin vẫn có MỌI skill node ──────────────────────

def test_admin_role_gets_every_skill_node():
    graph, _ = _graph_for_role("admin")
    nodes = set(graph.get_graph().nodes)
    specs = load_skill_specs()
    assert specs, "không có skill thật nào trong backend/skills/ — test vô nghĩa"
    for spec in specs:
        assert spec.name in nodes


def test_admin_role_unaffected_even_with_mcp_all_tools_passed():
    """role_cfg admin (unrestricted) TẮT cơ chế bỏ qua vô điều kiện — dù
    mcp_all_tools được truyền, hành vi phải giống HỆT trước Task này (không
    truyền role_cfg/mcp_all_tools chút nào)."""
    admin_cfg = roles.PROFILES["small-business"]["admin"]
    raw = _full_mcp_registry()
    tools = _filter_tools_for_role(raw, admin_cfg)
    assert len(tools) == len(raw)          # admin: filter là no-op

    with_role = build_graph(MagicMock(), tools, checkpointer=None,
                            role_cfg=admin_cfg, mcp_all_tools=raw)
    without_role = build_graph(MagicMock(), tools, checkpointer=None)
    assert (set(with_role.get_graph().nodes)
            == set(without_role.get_graph().nodes))


# ── Test 3 (yêu cầu task): SkillManifestError vẫn ném cho tool THẬT SỰ không
# tồn tại — chứng minh BẰNG CONSTRUCTION (không chỉ đường happy-path) ────────

def test_skill_manifest_error_still_raises_for_genuinely_unknown_tool(
        tmp_path, monkeypatch):
    """Dựng một skill khai tool ghi KHÔNG TỒN TẠI Ở ĐÂU (kể cả registry đầy
    đủ chưa lọc theo vai) rồi build_graph() qua đúng đường sản xuất (role_cfg
    + mcp_all_tools) — cơ chế bỏ-qua-theo-vai mới thêm KHÔNG được nuốt lỗi
    cấu hình thật này. Đây chính là loại lỗi mà SkillManifestError tồn tại để
    bắt (gõ sai tên tool / tool chưa deploy trên MCP), phân biệt với
    'tool có tồn tại nhưng vai không được cấp' mà Task này mới thêm cơ chế
    bỏ qua."""
    import src.agents.skill_loader as loader_mod

    d = tmp_path / "vo-danh"
    d.mkdir()
    (d / "SKILL.md").write_text(
        '---\nname: vo-danh\n'
        'description: "Dùng khi X. KHÔNG dùng khi: Y."\n'
        'tools:\n  write:\n    - name: tool_khong_ton_tai_o_dau_ca\n'
        '      confirm: "Xác nhận {order_ref}?"\n'
        '---\n\nBạn là trợ lý.\n', encoding="utf-8")
    monkeypatch.setattr(loader_mod, "SKILLS_DIR", tmp_path)

    cfg = roles.PROFILES["small-business"]["warehouse"]
    raw = _full_mcp_registry()                # KHÔNG có tool_khong_ton_tai...
    tools = _filter_tools_for_role(raw, cfg)

    with pytest.raises(SkillManifestError, match="tool_khong_ton_tai_o_dau_ca"):
        build_graph(MagicMock(), tools, checkpointer=None, role_cfg=cfg,
                   mcp_all_tools=raw)


def test_skill_manifest_error_still_raises_via_monkeypatched_spec(monkeypatch):
    """Cùng bất biến, dựng bằng cách khác (monkeypatch spec thay vì file tạm)
    — theo đúng gợi ý của brief, để không phụ thuộc riêng vào MỘT cách dựng."""
    import src.agents.graph as graph_mod
    from src.agents.skill_manifest import SkillSpec, WriteToolSpec

    bogus = SkillSpec(
        name="gia-lap", description="Dùng khi X. KHÔNG dùng khi: Y.", prose="Bạn là trợ lý.",
        dir=Path(graph_mod.__file__),  # không dùng (không có entry) — chỉ cần tồn tại
        write_tools=(WriteToolSpec("tool_hoan_toan_bia", "Xác nhận {order_ref}?"),))
    monkeypatch.setattr(graph_mod, "load_skill_specs", lambda: [bogus])

    cfg = roles.PROFILES["small-business"]["warehouse"]
    raw = _full_mcp_registry()
    tools = _filter_tools_for_role(raw, cfg)

    with pytest.raises(SkillManifestError, match="tool_hoan_toan_bia"):
        build_graph(MagicMock(), tools, checkpointer=None, role_cfg=cfg,
                   mcp_all_tools=raw)


# ── specs_for_role: một nguồn sự thật cho phép lọc skill ───────────────────

from src.agents.skill_loader import load_skill_specs, specs_for_role  # noqa: E402


def _specs_kept(role_name, profile="small-business"):
    """Tên skill còn lại sau khi lọc theo vai, dùng ĐÚNG đường production đi."""
    cfg = roles.PROFILES[profile][role_name]
    raw = _full_mcp_registry()
    tools = _filter_tools_for_role(raw, cfg)
    return [s.name for s in specs_for_role(load_skill_specs(), tools, raw, cfg)]


def test_specs_for_role_khop_so_do_that():
    """Đo 2026-08-14 bằng chính skill_role_gap. Nêu SỐ và TÊN cụ thể để nếu ai
    đó đổi chính sách vai, test đỏ vì đúng lý do — không phải vì một khẳng định
    chung chung."""
    assert _specs_kept("admin") == ["bao-gia-chiet-khau", "giao-hang", "nhap-kho"]
    assert _specs_kept("warehouse") == ["giao-hang", "nhap-kho"]
    assert _specs_kept("accounting") == []
    assert _specs_kept("warehouse", "enterprise") == ["giao-hang"]
    assert _specs_kept("accounting", "enterprise") == []


def test_specs_for_role_giu_nguyen_thu_tu():
    """Thứ tự quyết định thứ tự dòng trong worker block, mà worker block đi
    thẳng vào prompt — đảo thứ tự là đổi prompt."""
    goc = [s.name for s in load_skill_specs()]
    giu = _specs_kept("admin")
    assert giu == [n for n in goc if n in giu]


def test_specs_for_role_vai_admin_khong_lo_gi():
    """Bất biến của cả đợt: vai admin KHÔNG đổi hành vi, nếu không 5 baseline
    hiện có mất nghĩa."""
    assert _specs_kept("admin") == [s.name for s in load_skill_specs()]
