# backend/evals/run_eval.py
"""Runner eval M3 — đo model THẬT qua RoutedChatModel/router (không mock,
không còn LiteLLM — proxy này đã bị gỡ bỏ hoàn toàn từ SP-1).

  python -m evals.run_eval --set intent --model gemma-4-26b --save-baseline
  python -m evals.run_eval --set intent --model gemini-flash-lite \
      --baseline evals/baseline-qwen3-8b-intent.json

Gate (ADR-009 M3): intent → acc(model) >= acc(baseline).
confirm → zero false-CONFIRM (kỳ vọng cancel/unclear mà đoán confirm) VÀ
acc >= baseline_acc - (1/len(cases)).
Exit 0 = đạt; 1 = trượt; 2 = lỗi hạ tầng.
Exit 2 khi có case lỗi sau retry (S2) — đo không trọn vẹn thì không gate/không lưu baseline.
"""
import argparse, asyncio, json, math, os, re, sys, time

from langchain_core.messages import HumanMessage, SystemMessage

from evals.cases import (CHITCHAT_CASES, CONFIRM_CASES, GATHER_CASES,
                         HALLUCINATION_MARKERS, INTENT_CASES,
                         MULTI_SOURCE_CASES, MULTI_SOURCE_DERIVED_DIGITS,
                         MULTI_SOURCE_GATHER_CASES,
                         PLANNER_CASES, READ_CASES, SOP_SELECT_CASES,
                         SYNTHESIS_CASES, WRITE_TOOL_NAMES)
from evals import fixtures
from src.agents.prompts import CHITCHAT_PROMPT
from src.agents.confirmation import _LLM_PROMPT
from src.agents.prompts import WRITE_PLANNER_PROMPT
from src.agents.prompts import SYSTEM_PROMPT
from src.agents.prompts import RAG_SYNTHESIS_PROMPT
from src.agents.prompts import FUSE_PROMPT
from src.agents.fanout import render_fuse_input
from src.agents.prompts import GATHER_ERP_PROMPT
from src.agents.fanout import make_gather_erp_node, _create_agent
from src.agents.erp_grounding import verify_erp_grounding
from src.agents.prompts import render_intent_router_prompt
from src.agents.synthesis import SENTINEL, _format_context, _MARKER_RE
from src.agents.nodes import _parse_plan_tiered
from src.agents.routing import parse_proposal, decide_route
from src.agents.skill_loader import load_skill_specs, render_worker_block
from src.erp_query.tools import build_erp_query_tools
from jobs.resilience import run_resilient


# Router dựng LƯỜI, dùng CHUNG cho mọi lượt gọi eval trong một tiến trình —
# không phải một router mới mỗi case. build_router() mở PostgresUsageStore
# (fail-loud nếu bảng llm_usage chưa migrate), nên dựng đúng một lần.
_router: "Router | None" = None


def _get_router() -> "Router":
    global _router
    if _router is None:
        from src.llm.router import build_router
        _router = build_router()
    return _router


def _llm(alias: str, role: str) -> "RoutedChatModel":
    """RoutedChatModel ghim vào ĐÚNG một model (spec §2.1): resolve() với pin
    bỏ qua toàn bộ chuỗi VÀ không đọc sổ ngân sách (router.py resolve()) —
    trạng thái ngân sách không ảnh hưởng phép đo. _finish() vẫn GHI lượng
    tiêu thụ thật vào sổ — eval tiêu hạn mức thật thì sổ phải biết cả hai
    chiều. role chỉ dùng để gắn nhãn/ContextVar cô lập, KHÔNG ảnh hưởng model
    được chọn khi đã ghim (xem router.py resolve(), nhánh pin is not None
    trả sớm trước khi đụng tới role)."""
    from src.llm.router import RoutedChatModel
    return RoutedChatModel(_get_router(), role, pin=alias)


def _percentiles(samples: list[float]) -> tuple[int, int]:
    """(p50, p95) theo ms, làm tròn int. Nearest-rank: phần tử thứ
    ceil(q*n) trên list đã sắp. Rỗng → (0, 0)."""
    if not samples:
        return 0, 0
    ordered = sorted(samples)
    n = len(ordered)

    def pick(q: float) -> int:
        idx = math.ceil(q * n) - 1
        return round(ordered[max(0, min(idx, n - 1))])

    return pick(0.50), pick(0.95)


async def _timed(coro) -> tuple[object, float]:
    """Chạy coro, trả (kết quả, latency ms)."""
    start = time.perf_counter()
    result = await coro
    return result, (time.perf_counter() - start) * 1000.0


def _norm(v) -> str:
    return str(v).strip().casefold()


def _grounded_match(expect: str | tuple[str, ...], body: str) -> bool:
    """eval_synthesis(): body coi là "khớp căn cứ" với `expect` nếu khớp
    NGUYÊN VĂN — hoặc, nếu `expect` là một tuple nhiều chuỗi, khớp NGUYÊN
    VĂN với BẤT KỲ chuỗi nào trong đó. Mỗi phương án trong tuple là một cách
    diễn giải THẬT đã quan sát được từ model (ghi nhận từng trường hợp cụ
    thể, có dẫn chứng), KHÔNG phải suy luận ngữ nghĩa/mờ chung chung.

    Lịch sử (SP-1C1, chạy gate thật): bản đầu của hàm này thử "nới lỏng
    chung" bằng khớp-theo-thứ-tự-từ có giới hạn khoảng cách chèn — review
    độc lập (2 vòng) liên tục tìm được câu trả lời SAI (đảo cực tính qua một
    mệnh đề rào đón ngắn kiểu "Không sao, ... vẫn được hoàn trả") vẫn lọt
    qua bất kể rào được siết chặt tới đâu, vì bản chất khớp-theo-thứ-tự
    không phân biệt được "không" thuộc về phủ định thật hay một mệnh đề phụ
    không liên quan đứng trước. Kết luận: một heuristic mờ áp dụng chung cho
    MỌI expect không phải hướng an toàn — thay bằng danh sách các phương án
    khớp NGUYÊN VĂN, chỉ áp dụng cho ĐÚNG case đã quan sát được diễn giải
    (xem `SYNTHESIS_CASES` trong cases.py: case "không được hoàn trả" có
    thêm phương án "không được áp dụng chính sách hoàn trả"). Mỗi phương án
    vẫn là so khớp nguyên văn — không có logic mờ nào. Tập chấp nhận CHỈ mở
    rộng đúng bằng các câu chứa nguyên văn phương án 2 (không mở rộng theo
    thứ tự/khoảng cách từ như 2 bản trước) — không có LOẠI bề mặt lọt sai
    mới nào so với hành vi CŨ, dù tập chấp nhận về mặt tập hợp có to hơn.

    Mất mát đã biết và chấp nhận: một diễn giải KHÁC (chưa từng quan sát,
    không nằm trong danh sách phương án) sẽ vẫn trượt — và vì gate synthesis
    so `grounded_acc >= 1.0` (baseline đã đạt 12/12), MỘT case trượt là gate
    ĐỎ ngay, không phải tín hiệu mềm. Cần thêm phương án mới nếu/khi diễn
    giải mới xuất hiện thật ở một lượt chạy gate sau, cùng cách xử lý Task 6
    đã áp dụng cho `multi_source` (ghi nhận từng trường hợp cụ thể có dẫn
    chứng, không đoán trước)."""
    alts = expect if isinstance(expect, tuple) else (expect,)
    b = _norm(body)
    return any(_norm(alt) in b for alt in alts)


# Chuẩn hoá 1 lần — dangerous_misroute phải khớp case/whitespace-insensitive
# giống hệt tool_ok (_norm), không phải so raw string (finding review round 1:
# model trả "Confirm_Purchase_Order" thay vì "confirm_purchase_order" vẫn
# phải tính là misroute, không được lọt lưới qua so sánh phân biệt hoa/thường).
_NORM_WRITE_TOOLS = {_norm(t) for t in WRITE_TOOL_NAMES}


def _args_match(expected: dict, got: dict) -> bool:
    """Mọi key trong `expected` phải có trong `got` và khớp. Key lạ trong
    `got` KHÔNG tính sai. Số so bằng float; chuỗi so bằng _norm; list-of-dict
    so đúng độ dài + từng key được khai báo trong dict kỳ vọng."""
    if not isinstance(got, dict):
        return False
    for key, exp in expected.items():
        if key not in got:
            return False
        act = got[key]
        if isinstance(exp, list):
            if not isinstance(act, list) or len(act) != len(exp):
                return False
            for exp_item, act_item in zip(exp, act):
                if not isinstance(act_item, dict):
                    return False
                if not _args_match(exp_item, act_item):
                    return False
            continue
        if isinstance(exp, (int, float)) and not isinstance(exp, bool):
            try:
                if float(act) != float(exp):
                    return False
            except (TypeError, ValueError):
                return False
            continue
        if _norm(act) != _norm(exp):
            return False
    return True


def _stub_erp_tools(tool_fixtures: dict, called: list) -> list:
    """Bọc TOÀN BỘ tool đọc thật (build_erp_query_tools()) — giữ nguyên
    name/description/args_schema (allow-list y hệt production), chỉ thay
    THÂN hàm bằng tra cứu fixture. KHÔNG rút gọn tập lựa chọn: độ khó
    chọn-đúng-tool giữa 25 tool phải giữ nguyên như production (spec
    2026-08-01-sp2c §1.1) — rút gọn làm bài dễ đi, số đo vô nghĩa.

    BẪY late-binding closure: t/fixture PHẢI chốt bằng default-argument
    (_name=t.name, _fixture=fixture), không phải đọc trực tiếp t/fixture
    trong thân hàm lồng trong vòng lặp — nếu không MỌI stub sẽ trả fixture
    của tool CUỐI CÙNG trong vòng lặp, im lặng sai.

    BẪY invoke vị trí: LangChain tool có thể được gọi bằng một chuỗi trần
    (tool.invoke("some string")) thay vì dict kwargs — nếu không có
    `*_args` chặn đầu, chuỗi đó sẽ khớp vị trí vào _name (tham số khai báo
    đầu tiên), âm thầm làm hỏng sổ `called`. Đường gọi thật (ReAct/ToolNode
    sản xuất) luôn truyền dict nên đây không phải lỗi đang hoạt động ở bất
    kỳ phép đo hiện tại nào — chỉ là một lớp phòng thủ một dòng, đóng luôn
    khe hở này."""
    tools = build_erp_query_tools()
    for t in tools:
        fixture = tool_fixtures.get(t.name, "Không có dữ liệu liên quan.")

        def _stub(*_args, _name=t.name, _fixture=fixture, **kwargs):
            called.append(_name)
            return _fixture

        t.func = _stub
    return tools


def _score_gather(erp_facts: str, called: list,
                  required_tools: tuple, required_facts: tuple) -> tuple[bool, bool]:
    """Tách riêng khỏi vòng lặp async để test được KHÔNG cần mock LLM/agent
    — cùng kỷ luật _grounded_match/_args_match/_digits. required_tools là
    TẬP CON của called (model gọi thêm tool khác không bị tính lỗi)."""
    tool_recall_ok = set(required_tools) <= set(called)
    low = _norm(erp_facts)
    fact_coverage_ok = all(_norm(f) in low for f in required_facts)
    return tool_recall_ok, fact_coverage_ok


async def _run_gather_with_prompt(llm, tools, system_prompt: str, messages: list) -> dict:
    """CHỈ dùng cho branch="policy" của eval_gather — production CHƯA CÓ
    nhánh này (spec 2026-08-01-sp2c §1.3), không có node thật để gọi. Cố ý
    mirror thân make_gather_erp_node (fanout.py) NHƯNG với system_prompt
    khác — một thí nghiệm có kiểm soát, KHÔNG phải hợp đồng phải chống trôi
    như branch="base" (không gate, không được coi là "khớp production")."""
    try:
        agent = _create_agent(llm, tools, system_prompt=system_prompt)
        result = await agent.ainvoke({"messages": messages})
        msgs = result["messages"]
        facts = (msgs[-1].content or "").strip() if msgs else ""
        tool_outputs = [m.content for m in msgs if m.type == "tool"]
        if facts and tool_outputs:
            facts = await verify_erp_grounding(facts, tool_outputs, llm)
    except Exception:
        facts = ""
    return {"erp_facts": facts}


async def eval_gather(llm, pace: float = 0.0, checkpoint_path=None, branch: str = "base"):
    """Đo bước THU THẬP của gather_erp — multi_source đo bước TỔNG HỢP trên
    erp_block viết tay, KHÔNG đo được liệu gather_erp thật có lấy đủ field
    hay không (spec 2026-08-01-sp2c). branch="base": gọi make_gather_erp_node
    THẬT — số này được gate GÁC (không có baseline model cũ, gate tuyệt đối
    trả True ở lượt đầu, xem eval_gate.py). branch="policy": ghép thêm
    _format_context(chunks) vào prompt trước khi hỏi — KHÔNG gọi node thật
    (production chưa có nhánh này), chỉ GHI NHẬN, không gate."""
    assert branch in ("base", "policy")
    lat: list[float] = []

    async def call(case):
        topic, question, required_tools, required_facts, tool_fixtures = case
        called: list = []
        tools = _stub_erp_tools(tool_fixtures, called)
        messages = [HumanMessage(content=question)]
        if branch == "base":
            node = make_gather_erp_node(llm, tools)
            out, ms = await _timed(node({"messages": messages}))
        else:
            chunks = fixtures.load_chunks(topic)
            policy_prompt = (GATHER_ERP_PROMPT
                            + "\n\nCHÍNH SÁCH LIÊN QUAN:\n"
                            + _format_context(chunks))
            out, ms = await _timed(_run_gather_with_prompt(
                llm, tools, policy_prompt, messages))
        lat.append(ms)
        erp_facts = out.get("erp_facts") or ""
        tool_recall_ok, fact_coverage_ok = _score_gather(
            erp_facts, called, required_tools, required_facts)
        if tool_recall_ok and fact_coverage_ok:
            return None
        return {"topic": topic, "question": question, "called": called,
                "required_tools": list(required_tools),
                "erp_facts": erp_facts[:300],
                "tool_recall_ok": tool_recall_ok,
                "fact_coverage_ok": fact_coverage_ok}
    fails, errors = await run_resilient(GATHER_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(GATHER_CASES)
    measured = n - len(errors)
    tool_recall_bad = sum(1 for f in fails if not f["tool_recall_ok"])
    fact_bad = sum(1 for f in fails if not f["fact_coverage_ok"])
    p50, p95 = _percentiles(lat)
    return {"set": "gather", "branch": branch, "n": n,
            "tool_recall": (measured - tool_recall_bad) / n if n else 0.0,
            "fact_coverage": (measured - fact_bad) / n if n else 0.0,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


async def eval_planner(llm, pace: float = 0.0, checkpoint_path=None):
    """Đo QUYẾT ĐỊNH của write-planner bằng MỘT lời gọi (spec §4.0a).
    Dùng _parse_plan_tiered (thuần) — KHÔNG dùng _plan_json vì nó ghi
    friction log production. Không corrective-retry: đo chất lượng lần đầu;
    lần parse thất bại được ghi riêng vào parse_fail."""
    lat: list[float] = []

    async def call(case):
        text, exp_tool, exp_args = case
        resp, ms = await _timed(llm.ainvoke(
            [SystemMessage(content=WRITE_PLANNER_PROMPT),
             HumanMessage(content=text)]))
        lat.append(ms)
        plan, _tier = _parse_plan_tiered(resp.content)
        if plan is None:
            return {"text": text, "expected_tool": exp_tool,
                    "got_tool": None, "parse_fail": True}
        got_tool = plan.get("tool")
        got_args = plan.get("args") or {}
        tool_ok = _norm(got_tool) == _norm(exp_tool)
        args_ok = tool_ok and _args_match(exp_args, got_args)
        if tool_ok and args_ok:
            return None
        return {"text": text, "expected_tool": exp_tool, "got_tool": got_tool,
                "expected_args": exp_args, "got_args": got_args,
                "tool_ok": tool_ok, "parse_fail": False}
    fails, errors = await run_resilient(PLANNER_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(PLANNER_CASES)
    parse_fail = sum(1 for f in fails if f.get("parse_fail"))
    tool_wrong = [f for f in fails if not f.get("parse_fail") and not f["tool_ok"]]
    # hướng NGUY HIỂM: chọn một write tool KHÁC (ghi sai dữ liệu vào ERP).
    # "other"/None = "không biết" → an toàn, KHÔNG tính. Chỉ đếm từ fails.
    dangerous_misroute = sum(1 for f in tool_wrong
                             if _norm(f["got_tool"]) in _NORM_WRITE_TOOLS)
    args_wrong = sum(1 for f in fails
                     if not f.get("parse_fail") and f["tool_ok"])
    measured = n - len(errors)
    p50, p95 = _percentiles(lat)
    return {"set": "planner", "n": n,
            "tool_acc": (measured - len(tool_wrong) - parse_fail) / n if n else 0.0,
            "args_acc": (measured - len(tool_wrong) - parse_fail - args_wrong) / n if n else 0.0,
            "dangerous_misroute": dangerous_misroute,
            "parse_fail": parse_fail,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


async def eval_read(llm, pace: float = 0.0, checkpoint_path=None):
    """Đo QUYẾT ĐỊNH chọn tool đọc bằng MỘT lời gọi có bind_tools — KHÔNG
    thực thi tool, không cần Odoo sống (spec §4.0a). Mirror SYSTEM_PROMPT
    thật; không chạy verify_erp_grounding (đo riêng ở multi_source)."""
    bound = llm.bind_tools(build_erp_query_tools())
    lat: list[float] = []

    async def call(case):
        text, exp_tool, exp_args, entity_keys = case
        resp, ms = await _timed(bound.ainvoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=text)]))
        lat.append(ms)
        tool_calls = getattr(resp, "tool_calls", None) or []
        if not tool_calls:
            return {"text": text, "expected_tool": exp_tool, "got_tool": None,
                    "tool_ok": False, "fabricated": []}
        first = tool_calls[0]
        got_tool = first.get("name")
        got_args = first.get("args") or {}
        tool_ok = _norm(got_tool) == _norm(exp_tool)
        # bịa = giá trị thực thể KHÔNG xuất hiện trong câu hỏi
        haystack = _norm(text)
        fabricated = [k for k in entity_keys
                      if k in got_args and _norm(got_args[k]) not in haystack]
        params_ok = tool_ok and not fabricated and _args_match(exp_args, got_args)
        if tool_ok and params_ok:
            return None
        return {"text": text, "expected_tool": exp_tool, "got_tool": got_tool,
                "expected_args": exp_args, "got_args": got_args,
                "tool_ok": tool_ok, "fabricated": fabricated}
    fails, errors = await run_resilient(READ_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(READ_CASES)
    tool_wrong = sum(1 for f in fails if not f["tool_ok"])
    # CHỈ đếm từ fails — lỗi API không bao giờ là bịa tham số
    fabricated_param = sum(1 for f in fails if f["fabricated"])
    measured = n - len(errors)
    p50, p95 = _percentiles(lat)
    return {"set": "read", "n": n,
            "tool_acc": (measured - tool_wrong) / n if n else 0.0,
            "param_acc": (measured - len(fails)) / n if n else 0.0,
            "fabricated_param": fabricated_param,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


async def eval_intent(llm, pace: float = 0.0, checkpoint_path=None):
    """Đo trên ĐÚNG hợp đồng router thật (SP-2a Task 8): INTENT_ROUTER_PROMPT
    giờ đòi 2 dòng "intent:"/"sop:", không còn 1 từ trần — parse bằng
    _parse_router_output CHUNG với node thật (nodes.py) và eval_sop_select,
    không tự viết lại logic parse ở đây.

    Lỗi thật bắt được lúc xác nhận sống (Task 11, 2026-07-31): bản cũ của
    hàm này làm got = resp.content.strip().lower() rồi so trực tiếp với
    VALID_INTENTS — đúng khi router trả 1 từ trần, nhưng SAI HOÀN TOÀN sau
    khi Task 8 đổi INTENT_ROUTER_PROMPT sang 2 dòng: cả chuỗi 2 dòng không
    bao giờ khớp VALID_INTENTS nên MỌI case rơi về "unknown" (đo thật:
    acc 0.870 → 0.148). Unit test không bắt được vì không gọi LLM thật —
    đúng loại lỗi bước xác nhận sống này tồn tại để bắt.

    Sửa lần 2 (final review fix wave, 2026-07-31, Finding 4): SystemMessage
    trước đó dùng INTENT_ROUTER_PROMPT TRẦN, không nối worker block — khác
    với hợp đồng production thật (nodes.py.make_intent_router_node LUÔN gọi
    render_intent_router_prompt(worker_block), worker_block mô tả ~40 dòng
    của 3 skill SOP hiện có). eval_sop_select đã dựng prompt đúng cách này từ
    đầu; eval_intent giờ dùng LẠI đúng cách dựng đó (load_skill_specs +
    render_worker_block + render_intent_router_prompt) — một nguồn sự thật
    duy nhất, không tự viết lại. Trước fix này, điều kiện "bộ intent cũ
    không được thụt" (spec §5.3 điều kiện 2) đo trên một cấu hình prompt
    KHÔNG PHẢI production thật (ngắn hơn, thiếu phần mô tả SOP có thể ảnh
    hưởng phân loại)."""
    specs = load_skill_specs()
    prompt = render_intent_router_prompt(render_worker_block(specs))
    valid_sops = frozenset(s.name for s in specs)
    lat: list[float] = []

    async def call(case):
        text, expected = case
        resp, ms = await _timed(llm.ainvoke(
            [SystemMessage(content=prompt),
             HumanMessage(content=text)]))
        lat.append(ms)
        got, _sop = parse_proposal(resp.content, valid_sops)
        if got != expected:
            return {"text": text, "expected": expected, "got": got}
        return None
    fails, errors = await run_resilient(INTENT_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(INTENT_CASES)
    p50, p95 = _percentiles(lat)
    return {"set": "intent", "n": n,
            "acc": (n - len(fails) - len(errors)) / n,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


async def eval_sop_select(llm, pace: float = 0.0, checkpoint_path=None):
    """Đo việc CHỌN SOP end-to-end: gọi router thật với prompt thật (đã nối
    khối mô tả worker), parse bằng chính _parse_router_output của node, rồi áp
    chính _route_by_intent của graph. Đo cả chuỗi vì lớp phủ quyết tất định LÀ
    một phần của cơ chế — đo riêng đầu ra thô của model sẽ không nói lên điều
    gì về hành vi thật.

    Gate TUYỆT ĐỐI (giống chitchat, không baseline-relative): đây là hàng rào
    an toàn định tuyến, không phải phép đo chất lượng tương đối. Hướng nguy
    hiểm được đếm riêng: `hijack` = ca kỳ vọng KHÔNG phải SOP mà lại rơi vào
    SOP — đúng lỗi đã xảy ra thật."""
    specs = load_skill_specs()
    prompt = render_intent_router_prompt(render_worker_block(specs))
    valid_sops = frozenset(s.name for s in specs)
    lat: list[float] = []

    async def call(case):
        text, expected = case
        resp, ms = await _timed(llm.ainvoke(
            [SystemMessage(content=prompt), HumanMessage(content=text)]))
        lat.append(ms)
        intent, sop = parse_proposal(resp.content, valid_sops)
        got = decide_route({"messages": [HumanMessage(content=text)],
                            "intent": intent, "sop": sop})
        if got != expected:
            return {"text": text, "expected": expected, "got": got,
                    "raw_intent": intent, "raw_sop": sop,
                    "hijack": expected not in valid_sops and got in valid_sops}
        return None

    fails, errors = await run_resilient(SOP_SELECT_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(SOP_SELECT_CASES)
    # CHỈ đếm từ fails (phép đo thành công) — lỗi API không bao giờ là hijack.
    hijack = sum(1 for f in fails if f["hijack"])
    p50, p95 = _percentiles(lat)
    return {"set": "sop_select", "n": n,
            "acc": (n - len(fails) - len(errors)) / n if n else 0.0,
            "hijack": hijack,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


async def eval_confirm(llm, pace: float = 0.0, checkpoint_path=None):
    lat: list[float] = []

    async def call(case):
        text, expected = case
        resp, ms = await _timed(llm.ainvoke(
            [SystemMessage(content=_LLM_PROMPT), HumanMessage(content=text)]))
        lat.append(ms)
        v = resp.content.strip().upper()
        got = "confirm" if "CONFIRM" in v else "cancel" if "CANCEL" in v else "unclear"
        if got != expected:
            return {"text": text, "expected": expected, "got": got}
        return None
    fails, errors = await run_resilient(CONFIRM_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(CONFIRM_CASES)
    # hướng nguy hiểm: đoán CONFIRM khi không phải. CHỈ đếm từ fails (phép đo
    # thành công) — lỗi API (errors) không bao giờ là false_confirm.
    false_confirm = sum(1 for f in fails if f["got"] == "confirm")
    p50, p95 = _percentiles(lat)
    return {"set": "confirm", "n": n,
            "acc": (n - len(fails) - len(errors)) / n,
            "false_confirm": false_confirm,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


async def eval_chitchat(llm, pace: float = 0.0, checkpoint_path=None):
    """Chống bịa hành động đã xảy ra — chitchat (respond_unknown) không bind
    tool nào, nên bất kỳ khẳng định 'đã làm X' đều là bịa. Gate tuyệt đối
    (violations phải = 0), KHÔNG so baseline (không có 'câu trả lời đúng' cho
    chit-chat tự do). Gọi LLM giống hệt respond_unknown thật: SystemMessage(CHITCHAT_PROMPT)
    + HumanMessage — mirror persona production (khóa #10)."""
    lat: list[float] = []

    async def call(text):
        resp, ms = await _timed(llm.ainvoke(
            [SystemMessage(content=CHITCHAT_PROMPT), HumanMessage(content=text)]))
        lat.append(ms)
        content_lower = resp.content.lower()
        matched = [m for m in HALLUCINATION_MARKERS if m in content_lower]
        if matched:
            return {"text": text, "response": resp.content,
                    "matched_markers": matched}
        return None
    fails, errors = await run_resilient(CHITCHAT_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    p50, p95 = _percentiles(lat)
    return {"set": "chitchat", "n": len(CHITCHAT_CASES),
            "violations": len(fails),
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


async def eval_synthesis(llm, pace: float = 0.0, checkpoint_path=None):
    """Đo trả lời-chỉ-dựa-tài-liệu trên fixture đóng băng. Mirror ĐÚNG hình
    dạng prompt của synthesize(): SystemMessage(RAG_SYNTHESIS_PROMPT) +
    'TÀI LIỆU:\\n{_format_context(chunks)}\\n\\nCÂU HỎI: {query}'."""
    lat: list[float] = []

    async def call(case):
        topic, question, kind, expect = case
        chunks = fixtures.load_chunks(topic)
        resp, ms = await _timed(llm.ainvoke([
            SystemMessage(content=RAG_SYNTHESIS_PROMPT),
            HumanMessage(content=f"TÀI LIỆU:\n{_format_context(chunks)}"
                                 f"\n\nCÂU HỎI: {question}"),
        ]))
        lat.append(ms)
        body = (resp.content or "").strip()
        refused = SENTINEL in body
        if kind == "insufficient":
            if refused:
                return None
            return {"topic": topic, "question": question, "kind": kind,
                    "response": body[:300], "false_answer": True,
                    "false_insufficient": False}
        # answerable
        if refused:
            return {"topic": topic, "question": question, "kind": kind,
                    "response": body[:300], "false_answer": False,
                    "false_insufficient": True}
        if _grounded_match(expect, body):
            return None
        return {"topic": topic, "question": question, "kind": kind,
                "expect": expect, "response": body[:300],
                "false_answer": False, "false_insufficient": False}
    fails, errors = await run_resilient(SYNTHESIS_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(SYNTHESIS_CASES)
    # CHỈ đếm từ fails — lỗi API không bao giờ là bịa nội dung tài liệu
    false_answer = sum(1 for f in fails if f.get("false_answer"))
    false_insufficient = sum(1 for f in fails if f.get("false_insufficient"))
    p50, p95 = _percentiles(lat)
    return {"set": "synthesis", "n": n,
            "grounded_acc": (n - len(fails) - len(errors)) / n if n else 0.0,
            "false_answer": false_answer,
            "false_insufficient": false_insufficient,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


_NUM_RE = re.compile(r"\d[\d.,]*")


def _cited_indices(body: str) -> set[int]:
    """Index chunk mà LLM tự khai đã dùng, parse bằng CHÍNH _MARKER_RE của
    production. KHÔNG dùng extract_used_citations() — hàm đó fallback về TOÀN
    BỘ chunk khi marker thiếu/sai, nên không phân biệt được trích dẫn hợp lệ
    với trích dẫn sai."""
    m = _MARKER_RE.search(body)
    if not m:
        return set()
    return {int(x) for x in re.findall(r"\d+", m.group(1))}


def _digits(s: str) -> set[str]:
    """Các chuỗi số trong s, đã bỏ dấu phân cách — để so 1.500.000 với
    1500000."""
    return {re.sub(r"[.,]", "", tok) for tok in _NUM_RE.findall(s)}


def _score_fusion(body: str, chunks, erp_text: str, doc_fact, erp_fact,
                  topic: str, question: str,
                  allowed_extra_text: str = "") -> dict:
    """Chấm một câu trả lời tổng hợp 2 nguồn — DÙNG CHUNG cho
    eval_multi_source (ERP = erp_block viết tay) và eval_multi_source_gather
    (ERP = tool_fixtures mà gather_erp thật đi lấy).

    Tách ra vì đoạn này có lịch sử lỗi riêng đáng kể: `allowed` từng dựng
    sai basis (model nhìn thấy _format_context(chunks) nhưng allowed chỉ
    dựng từ c.text trần → số trong nhãn mục bị quy oan là "bịa"), và
    MULTI_SOURCE_DERIVED_DIGITS ra đời từ 2 lượt gate fail thật. Chép lại
    công thức này sang hàm thứ hai là mời đúng lớp lỗi đó quay lại.

    `erp_text` là NGUỒN SỰ THẬT của phía ERP, không phải văn bản model sinh
    ra: ở set gather nó là tool_fixtures ghép lại, KHÔNG phải erp_facts —
    lấy erp_facts làm basis sẽ tự hợp thức hóa số do chính tầng gather bịa.

    `allowed_extra_text` (mặc định "" = không đổi gì) cho phép whitelist
    thêm một nguồn số hợp lệ. eval_multi_source KHÔNG dùng — giữ nguyên
    công thức của một set đang GÁC thật. Xem spec §5.
    """
    both = _grounded_match(doc_fact, body) and _grounded_match(erp_fact, body)
    cited = _cited_indices(body)
    citation_ok = all(1 <= i <= len(chunks) for i in cited)
    allowed = (_digits(erp_text) | _digits(_format_context(chunks))
               | _digits(allowed_extra_text))
    allowed |= MULTI_SOURCE_DERIVED_DIGITS.get((topic, question), frozenset())
    # bỏ marker trước khi soi số, tránh coi chính index trích dẫn là số bịa
    m = _MARKER_RE.search(body)
    prose = body[:m.start()] if m else body
    fabricated = sorted(_digits(prose) - allowed)
    return {"both": both, "citation_ok": citation_ok, "fabricated": fabricated}


async def eval_multi_source(llm, pace: float = 0.0, checkpoint_path=None):
    """Đo tổng hợp 2 nguồn trên fixture đóng băng — mirror node fuse_answer.

    Prompt VÀ hình dạng input đều lấy từ production (FUSE_PROMPT,
    render_fuse_input) — KHÔNG dựng lại bằng tay. Đây là điều kiện để mirror
    không trôi khỏi node thật: ở SP-2a, eval_intent() dựng lại cách parse đầu
    ra router ở module riêng, hợp đồng đổi mà eval không đổi theo, acc rơi
    0.870 → 0.148 và trông y hệt lỗi chất lượng model.

    erp_block của fixture đóng vai erp_facts — cả hai đều là văn bản dữ kiện
    ERP thô do chân gather_erp nộp lên, không phải câu trả lời.

    Chấm điểm nằm ở _score_fusion (dùng chung với eval_multi_source_gather);
    set này không dùng whitelist số hợp lệ ngoài để giữ nguyên công thức đang gác.
    """
    lat: list[float] = []

    async def call(case):
        topic, erp_block, question, doc_fact, erp_fact = case
        chunks = fixtures.load_chunks(topic)
        resp, ms = await _timed(llm.ainvoke([
            SystemMessage(content=FUSE_PROMPT),
            HumanMessage(content=render_fuse_input(chunks, erp_block, question)),
        ]))
        lat.append(ms)
        body = (resp.content or "").strip()
        score = _score_fusion(body, chunks, erp_block, doc_fact, erp_fact,
                              topic, question)
        if score["both"] and score["citation_ok"] and not score["fabricated"]:
            return None
        return {"topic": topic, "question": question, "response": body[:300],
                **score}
    fails, errors = await run_resilient(MULTI_SOURCE_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(MULTI_SOURCE_CASES)
    measured = n - len(errors)
    # CHỈ đếm từ fails — lỗi API không bao giờ là trích dẫn sai / số bịa
    bad_cite = sum(1 for f in fails if not f["citation_ok"])
    no_both = sum(1 for f in fails if not f["both"])
    fabricated_number = sum(1 for f in fails if f["fabricated"])
    p50, p95 = _percentiles(lat)
    # Mọi tỷ lệ chia cho n (không phải measured) để nhất quán với các set
    # khác. Khi có errors thì eval_gate trả INFRA_ERROR trước khi gate chạy
    # (bất biến Global Constraints), nên 2 cách chia tương đương trong thực tế.
    return {"set": "multi_source", "n": n,
            "both_source_coverage": (measured - no_both) / n if n else 0.0,
            "citation_validity": (measured - bad_cite) / n if n else 0.0,
            "fabricated_number": fabricated_number,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


async def eval_multi_source_gather(llm, pace: float = 0.0, checkpoint_path=None):
    """Đo TOÀN CHUỖI nhánh mixed: gather_erp THẬT (make_gather_erp_node trên
    tool giả lập từ tool_fixtures) → fuse_answer, trên CÙNG bộ câu
    hỏi/doc_fact/erp_fact của multi_source.

    Khác eval_multi_source ở ĐÚNG một biến: erp_facts do node thật tự đi
    lấy, thay vì erp_block viết tay nạp sẵn. Nhờ vậy set này đo được thứ
    multi_source mù về mặt kiến trúc — năng lực THU THẬP ERP — mà vẫn dùng
    chung thước đo (_score_fusion) nên hai bộ số so sánh được.

    KHÔNG GATE (spec 2026-08-04 §3): chưa có baseline, _gate() trả True vô
    điều kiện, và set bị loại khỏi `--set all`. Số liệu vào báo cáo để người
    đọc tự đánh giá.

    Tool giả lập chứ không phải Odoo thật — cùng kỷ luật eval_gather: đo
    phải lặp lại được. Chẩn đoán khi viết spec cho thấy đúng rủi ro của lựa
    chọn ngược lại: đơn S00042 (mốc tham chiếu của 3 plan trước) nay ở trạng
    thái draft với mọi field ngày rỗng, nên đo trên Odoo thật sẽ trôi theo
    dữ liệu demo chứ không theo chất lượng model.
    """
    lat: list[float] = []

    async def call(case):
        topic, tool_fixtures, question, doc_fact, erp_fact = case
        called: list = []
        tools = _stub_erp_tools(tool_fixtures, called)
        node = make_gather_erp_node(llm, tools)
        chunks = fixtures.load_chunks(topic)

        async def _chain():
            out = await node({"messages": [HumanMessage(content=question)]})
            erp_facts = out.get("erp_facts") or ""
            resp = await llm.ainvoke([
                SystemMessage(content=FUSE_PROMPT),
                HumanMessage(content=render_fuse_input(chunks, erp_facts,
                                                       question)),
            ])
            return erp_facts, resp

        # Đo THỜI GIAN CẢ CHUỖI (gather + fuse) — latency của set này không
        # so trực tiếp được với multi_source (chỉ đo fuse), có chủ đích.
        (erp_facts, resp), ms = await _timed(_chain())
        lat.append(ms)
        body = (resp.content or "").strip()
        score = _score_fusion(body, chunks, "\n".join(tool_fixtures.values()),
                              doc_fact, erp_fact, topic, question,
                              allowed_extra_text=question)
        if score["both"] and score["citation_ok"] and not score["fabricated"]:
            return None
        return {"topic": topic, "question": question, "called": called,
                "erp_facts": erp_facts[:300], "response": body[:300], **score}

    fails, errors = await run_resilient(MULTI_SOURCE_GATHER_CASES, call,
                                        pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(MULTI_SOURCE_GATHER_CASES)
    measured = n - len(errors)
    # CHỈ đếm từ fails — lỗi API không bao giờ là trích dẫn sai / số bịa
    bad_cite = sum(1 for f in fails if not f["citation_ok"])
    no_both = sum(1 for f in fails if not f["both"])
    fabricated_number = sum(1 for f in fails if f["fabricated"])
    p50, p95 = _percentiles(lat)
    return {"set": "multi_source_gather", "n": n,
            "both_source_coverage": (measured - no_both) / n if n else 0.0,
            "citation_validity": (measured - bad_cite) / n if n else 0.0,
            "fabricated_number": fabricated_number,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


async def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--set",
                    choices=["intent", "confirm", "chitchat", "planner", "read",
                             "synthesis", "multi_source", "sop_select"],
                    required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--save-baseline", action="store_true")
    ap.add_argument("--baseline")
    ap.add_argument("--pace", type=float, default=0.0,
                    help="giây giãn cách giữa 2 call (suy từ catalog: "
                         "(60/rpm)*1.2 cho model đang ghim — vd rpm=15 → ~4.8)")
    args = ap.parse_args(argv)

    try:
        _FN = {"intent": eval_intent, "confirm": eval_confirm,
               "chitchat": eval_chitchat, "planner": eval_planner,
               "read": eval_read, "synthesis": eval_synthesis,
               "multi_source": eval_multi_source, "sop_select": eval_sop_select}
        result = await _FN[args.set](_llm(args.model, role=args.set), pace=args.pace)
    except Exception as e:   # noqa: BLE001 — hạ tầng LLM sập (key/model/router hỏng)
        print(f"INFRA ERROR: {e}"); sys.exit(2)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    # S2 spec §3: đo không trọn vẹn → exit 2 TRƯỚC mọi nhánh baseline —
    # baseline khuyết tật sẽ đầu độc mọi gate về sau.
    if result["errors"]:
        print(f"INFRA ERROR: {len(result['errors'])} case lỗi sau retry — "
              "không đủ điều kiện gate/baseline")
        sys.exit(2)

    here = os.path.dirname(__file__)
    if args.save_baseline:
        path = os.path.join(here, f"baseline-{args.model.replace(':','-')}-{args.set}.json")
        json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"baseline saved: {path}"); sys.exit(0)

    if args.baseline:
        base = json.load(open(args.baseline, encoding="utf-8"))
        # Import CỤC BỘ trong hàm có chủ đích — KHÔNG chuyển lên module level:
        # eval_gate.py đã `from evals import run_eval`, nên import ngược ở
        # module level sẽ tạo circular import. Giữ 1 nguồn sự thật cho công
        # thức gate thay vì chép lại logic ở 2 chỗ.
        from jobs.eval_gate import _gate
        ok = _gate(args.set, result, base)
        key = ("tool_acc" if args.set in ("planner", "read")
               else "grounded_acc" if args.set == "synthesis"
               else "both_source_coverage" if args.set == "multi_source"
               else "acc")
        print(f"GATE {'PASS' if ok else 'FAIL'} — "
              f"model={result[key]:.3f} baseline={base[key]:.3f}")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
