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
import string
import sys
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.tools import StructuredTool
from pydantic import create_model

from .agentic_gate import REFUSED_MSG, _confirm_write, ask_human
from .skill_manifest import (MISSING_NEGATIVE_WARNING, SkillManifestError,
                             SkillSpec, parse_skill_md)
from .write_registry import WRITE_COORDINATORS
from ..erp_query.tools import build_erp_query_tools

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

# Đánh dấu vế loại trừ trong mô tả skill (chọn cụm nào tuỳ verb mở đầu).
NEGATIVE_CLAUSE_MARKERS = ("KHÔNG dùng khi", "KHÔNG chọn khi")


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
        if not any(marker in spec.description
                   for marker in NEGATIVE_CLAUSE_MARKERS):
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


def _param_names(mcp_tool) -> set[str]:
    """Tên tham số tool MCP. langchain-mcp-adapters đặt args_schema = chính
    JSON Schema (dict) của MCP inputSchema; tool @tool thuần Python thì
    args_schema là lớp pydantic. Đỡ cả hai."""
    schema = mcp_tool.args_schema
    if isinstance(schema, dict):
        return set((schema.get("properties") or {}).keys())
    return set(getattr(schema, "model_fields", {}).keys())


def _visible_schema(mcp_tool, fixed: dict):
    """Schema model NHÌN THẤY = schema tool MCP TRỪ các khoá fixed_args.

    Markdown không có quyền mô tả tham số của một tool ghi — schema chép từ
    chính tool MCP. Việc DUY NHẤT manifest được làm là GIẤU bớt tham số bằng
    cách ghim giá trị hằng cho nó (fixed_args); giấu đi thì model không đặt
    được, nên đây là thu hẹp thẩm quyền, không phải mở rộng.

    Đỡ CẢ HAI hình dạng args_schema, không phải để tổng quát hoá vu vơ mà vì
    hai đường đều xảy ra thật: langchain-mcp-adapters gán args_schema = chính
    JSON Schema (DICT) của MCP inputSchema (tools.py:531) — đường production;
    còn tool dựng bằng @tool trong test cho ra LỚP PYDANTIC."""
    schema = mcp_tool.args_schema
    if not fixed:
        return schema
    if isinstance(schema, dict):
        out = dict(schema)
        out["properties"] = {k: v for k, v in (out.get("properties") or {}).items()
                             if k not in fixed}
        required = [r for r in (out.get("required") or []) if r not in fixed]
        if required:
            out["required"] = required
        else:
            out.pop("required", None)
        return out
    kept = {n: (f.annotation, f) for n, f in schema.model_fields.items()
            if n not in fixed}
    return create_model(f"{mcp_tool.name}_visible_args", **kept)


def _make_gated_write_tool(mcp_tool, wspec):
    """Sinh wrapper CÙNG TÊN bọc _confirm_write quanh một tool ghi MCP.

    Đây là boilerplate mà 3 skill viết tay ở D:\\Project đang chép đi chép lại
    (lấy tool theo tên → bọc _confirm_write → ainvoke). Sinh tự động để không
    có đường nào quên gate: model KHÔNG BAO GIỜ thấy tool ghi thô (chỉ wrapper
    này được bind vào create_agent), nên không có đường vòng bỏ qua cổng."""

    async def _gated(**kwargs) -> str:
        # Giới hạn đã biết (2026-07-31, review Task 4): unknown_ph chỉ kiểm
        # placeholder nằm trong TẬP THAM SỐ của tool, không kiểm nó có
        # "required" không — nếu một SKILL.md tương lai viết confirm nội suy
        # tham số TÙY CHỌN mà model bỏ qua lúc gọi, dòng .format() dưới đây sẽ
        # KeyError thay vì lỗi rõ ràng. Không ảnh hưởng 3 skill hiện có (mọi
        # placeholder confirm đều trỏ tham số bắt buộc). Sửa đúng cần quyết
        # định hành vi khi thiếu tham số tùy chọn — để lại cho vòng sau.
        if not _confirm_write(wspec.confirm.format(**kwargs, **wspec.fixed_args)):
            return REFUSED_MSG
        return await mcp_tool.ainvoke({**kwargs, **wspec.fixed_args})

    return StructuredTool.from_function(
        func=None, coroutine=_gated, name=mcp_tool.name,
        description=mcp_tool.description,
        args_schema=_visible_schema(mcp_tool, wspec.fixed_args))


def _load_entry_module(spec: SkillSpec):
    path = spec.dir / spec.entry
    # Phòng thủ lớp 2 (review Finding 1, 2026-07-31): layer 1
    # (skill_manifest.parse_skill_md) đã chặn '/', '\\', '..' trong entry —
    # đây là lưới đỡ ĐỘC LẬP phòng khi một SkillSpec tới đây KHÔNG đi qua
    # parse_skill_md (vd construct thủ công, bug tương lai khác). resolve()
    # rồi so sánh parent — chỉ chấp nhận file NẰM THẲNG trong spec.dir.
    resolved = path.resolve()
    if resolved.parent != spec.dir.resolve():
        raise SkillManifestError(
            f"{path}: entry phải resolve về một file NẰM TRONG {spec.dir} — "
            "chặn thực thi module Python ngoài thư mục skill")
    mod_name = f"youdoo_skill_{spec.name.replace('-', '_')}"
    mod_spec = importlib.util.spec_from_file_location(mod_name, resolved)
    if mod_spec is None or mod_spec.loader is None:
        raise SkillManifestError(f"{path}: không nạp được entry module")
    module = importlib.util.module_from_spec(mod_spec)
    sys.modules[mod_name] = module
    mod_spec.loader.exec_module(module)
    if not callable(getattr(module, "build_tools", None)):
        raise SkillManifestError(
            f"{path}: entry phải cung cấp hàm build_tools(mcp_tools) -> list[BaseTool]")
    return module


def build_skill_tools(spec: SkillSpec, mcp_tools) -> list:
    """Tool của một node SOP: ask_human + tool đọc + (wrapper ghi ĐÃ GATE
    HOẶC tool do entry sinh). ask_human luôn được cấp, không cần khai — mọi SOP
    đều cần, bắt khai chỉ tạo chỗ để quên.

    registry MCP RỖNG = đường test (build_graph(tools=[])), không phải đường
    production: ERPAgent.setup() gọi await client.get_tools() TRƯỚC build_graph
    và lệnh đó ném lỗi nếu MCP sập, nên production không bao giờ tới đây với
    registry rỗng. Rỗng → không có hợp đồng MCP để đối chiếu, bỏ qua kiểm tra
    tồn tại, dựng node chỉ-đọc. KHÔNG rỗng mà thiếu tool đã khai → fail-loud."""
    by_name = {t.name: t for t in mcp_tools}
    read_by_name = {t.name: t for t in build_erp_query_tools()}

    tools = [ask_human]
    for rname in spec.read_tools:
        if rname not in read_by_name:
            raise SkillManifestError(
                f"skill {spec.name!r}: tool đọc {rname!r} không có trong "
                "build_erp_query_tools()")
        tools.append(read_by_name[rname])

    if spec.entry:
        module = _load_entry_module(spec)
        produced = list(module.build_tools(mcp_tools))
        allowed = set(spec.declares_tools) | {"ask_human"}
        extra = sorted({t.name for t in produced} - allowed)
        # Chỉ chặn chiều LEO THANG (trả tool KHÔNG khai). Chiều thiếu là hợp lệ:
        # registry MCP rỗng thì build_tools() không dựng được tool ghi nào.
        if extra:
            raise SkillManifestError(
                f"skill {spec.name!r}: entry {spec.entry!r} trả tool không khai "
                f"trong declares_tools: {extra}")
        tools.extend(t for t in produced if t.name != "ask_human")
        return tools

    for wspec in spec.write_tools:
        mcp_tool = by_name.get(wspec.name)
        if mcp_tool is None:
            if not by_name:
                continue          # registry rỗng — xem docstring
            raise SkillManifestError(
                f"skill {spec.name!r}: tool ghi {wspec.name!r} không có trong "
                "registry MCP")
        params = _param_names(mcp_tool)
        unknown_fixed = sorted(set(wspec.fixed_args) - params)
        if unknown_fixed:
            raise SkillManifestError(
                f"skill {spec.name!r}/{wspec.name}: fixed_args {unknown_fixed} "
                f"không phải tham số của tool đó (tham số hợp lệ: {sorted(params)})")
        placeholders = {f for _l, f, _s, _c in string.Formatter().parse(wspec.confirm)
                        if f}
        unknown_ph = sorted(placeholders - params)
        if unknown_ph:
            raise SkillManifestError(
                f"skill {spec.name!r}/{wspec.name}: confirm nội suy {unknown_ph} "
                f"không phải tham số của tool đó (tham số hợp lệ: {sorted(params)})")
        tools.append(_make_gated_write_tool(mcp_tool, wspec))

    return tools


def skill_role_gap(spec: SkillSpec, tools, all_tools, role_cfg) -> str | None:
    """None nếu skill `spec` phải được nạp bình thường cho vai hiện tại; nếu
    không, trả một lý do ngắn (để log) — skill này phải bị BỎ QUA khỏi graph,
    KHÔNG phải lỗi cấu hình.

    Phân biệt hai trường hợp một tool ghi mà skill cần không có mặt trong
    `tools` (danh sách ĐÃ LỌC theo vai, xem erp_agent._filter_tools_for_role):

      (a) tool đó TỒN TẠI trong `all_tools` (registry MCP ĐẦY ĐỦ, chưa lọc) —
          nghĩa là vai này không được cấp tool đó theo chính sách (roles.py).
          Đây là chỗ ĐÚNG để bỏ qua: một skill cần quyền vai không có thì
          không nên hiện ra cho vai đó (vd kho không được offer SOP báo giá
          chiết khấu, vì create_quotation không nằm trong
          RoleCfg.allowed_tools() của vai kho — suy từ roles.DEPT_OF qua
          RoleCfg.other_dept, xem roles.py).
      (b) tool đó KHÔNG có trong `all_tools` — nghĩa là SKILL.md khai một tool
          không tồn tại ở BẤT KỲ ĐÂU trong registry MCP: lỗi cấu hình thật.
          KHÔNG được nuốt ở đây — để build_skill_tools() ném SkillManifestError
          như cũ (gọi hàm này KHÔNG tự nó gọi build_skill_tools; caller vẫn
          phải gọi build_skill_node()/build_skill_tools() bình thường khi hàm
          này trả None, và exception đó vẫn xuyên ra ngoài).

    role_cfg is None, role_cfg.allowed_tools() is None (vai admin — không
    lọc), hoặc all_tools is None (không có tham chiếu registry đầy đủ, vd
    test cũ gọi build_graph() không truyền role_cfg/mcp_all_tools) → luôn trả
    None, giữ NGUYÊN hành vi trước Task này (admin/test không đổi gì)."""
    if role_cfg is None or role_cfg.allowed_tools() is None or all_tools is None:
        return None

    filtered_names = {t.name for t in tools}
    all_names = {t.name for t in all_tools}

    if spec.entry:
        # Skill dựng tool qua entry (bao-gia-chiet-khau/logic.py): manifest
        # không khai tên tool MCP GỐC skill đó cần (declares_tools là tên
        # WRAPPER, vd create_discount_quote, khác create_quotation) — nên
        # không so tên trực tiếp được. Thay vào đó, dựng thử build_tools() với
        # CẢ HAI registry rồi so KẾT QUẢ: nếu registry đầy đủ dựng được trọn
        # declares_tools mà registry đã lọc theo vai thì KHÔNG, gap đó là do
        # bộ lọc vai (case a) → bỏ qua cả skill. Nếu registry đầy đủ CŨNG
        # không dựng được đủ, gap không phải do vai — giữ nguyên hành vi cũ
        # (nạp node, thiếu tool ghi thì entry tự bớt, không raise — xem
        # docstring build_skill_tools/logic.py).
        declared = set(spec.declares_tools)
        produced_filtered = {t.name for t in build_skill_tools(spec, tools)
                             if t.name != "ask_human"}
        if declared <= produced_filtered:
            return None
        produced_full = {t.name for t in build_skill_tools(spec, all_tools)
                         if t.name != "ask_human"}
        if declared <= produced_full:
            missing = sorted(declared - produced_filtered)
            return (f"entry dựng thiếu tool {missing} khi dùng registry đã lọc "
                     f"theo vai {role_cfg.name!r} nhưng dựng ĐỦ với registry đầy "
                     "đủ — tool MCP gốc mà entry phụ thuộc bị lọc vì chính sách vai")
        return None

    missing_for_role = sorted(
        w.name for w in spec.write_tools
        if w.name not in filtered_names and w.name in all_names)
    if missing_for_role:
        return (f"tool ghi {missing_for_role} có trong registry MCP nhưng vai "
                f"{role_cfg.name!r} không có quyền")
    return None


def build_skill_node(spec: SkillSpec, llm, mcp_tools):
    """Node SOP = CompiledStateGraph của create_agent, TRẢ VỀ TRỰC TIẾP.

    Node này PHẢI được add_node thẳng vào graph ngoài — không bao giờ bọc trong
    một hàm async viết tay. Đó là điều kiện để interrupt() bên trong tool của nó
    (ask_human / _confirm_write) compose đúng với checkpointer của graph ngoài.

    .with_config áp TẠI ĐÂY (wiring), không trong create_agent: spike v10 chứng
    minh binding giữ nguyên interrupt/resume; spike v10b chứng minh KHÔNG có nó
    thì subgraph chạy không giới hạn (mặc định 25 của LangGraph không truyền
    vào subgraph-as-node, chỉ giá trị tường minh trong config mới kế thừa)."""
    agent = create_agent(llm, build_skill_tools(spec, mcp_tools),
                         system_prompt=spec.prose)
    return agent.with_config({"recursion_limit": spec.max_steps})


def specs_for_role(specs, tools, all_tools, role_cfg, logger=None) -> list:
    """Các skill được nạp cho vai hiện tại — GIỮ NGUYÊN thứ tự của `specs`.

    Trích từ vòng lặp vốn nằm trong graph.py để bộ đo eval gọi được ĐÚNG phép
    lọc mà production dùng. Viết lại phép lọc ở nơi thứ hai là cách nó trôi
    lệch: một phép tái lập bằng tay (write_tools ⊆ allowed_tools) đã cho 1/3
    skill trong khi hàm thật cho 0/3, vì nhánh declares_tools không được tái
    lập.

    Thứ tự có ý nghĩa: nó quyết định thứ tự dòng trong render_worker_block,
    mà khối đó đi thẳng vào prompt router.
    """
    kept = []
    for spec in specs:
        reason = skill_role_gap(spec, tools, all_tools, role_cfg)
        if reason:
            if logger is not None:
                logger.info("skill %r bỏ qua cho vai %r: %s", spec.name,
                            getattr(role_cfg, "name", None), reason)
            continue
        kept.append(spec)
    return kept
