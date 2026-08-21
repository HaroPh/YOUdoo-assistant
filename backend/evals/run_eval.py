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
                         LANGUAGE_CASES, LOCALIZE_CASES, MEMORY_CASES, MULTI_SOURCE_CASES, MULTI_SOURCE_DERIVED_DIGITS,
                         MULTI_SOURCE_GATHER_CASES,
                         PLANNER_CASES, READ_CASES, SOP_SELECT_CASES,
                         SYNTHESIS_CASES, WRITE_TOOL_NAMES)
from evals import fixtures
from evals.matching import _norm, _grounded_match
from evals.retrieval_cases import RETRIEVAL_CASES
from evals.retrieval_score import label_of, score_one
from evals.multiturn_cases import MULTITURN_CASES
from evals.synthesis_live_cases import SYNTHESIS_LIVE_CASES
from evals.memory_presets import MEMORY_PRESETS
from evals.write_suggest_cases import WRITE_SUGGEST_CASES
from evals.write_suggest_oracle import oracle_proposes_write
from evals.synthesis_live_score import score_answer
from src.agents.synthesis import synthesize as _synthesize
from src.rag.retrieve import retrieve as _retrieve
from src.rag.config import TOP_N as _TOP_N, TOP_K as _TOP_K
from src.agents import roles
from src.agents.prompts import CHITCHAT_PROMPT
from src.agents.confirmation import _LLM_PROMPT
from src.agents.prompts import SYSTEM_PROMPT
from src.agents.prompts import RAG_SYNTHESIS_PROMPT
from src.agents.prompts import FUSE_PROMPT
from src.agents.fanout import render_fuse_input
from src.agents.prompts import GATHER_ERP_PROMPT
from src.agents.fanout import make_gather_erp_node, _create_agent
from src.agents.erp_grounding import verify_erp_grounding
from src.agents.synthesis import (SENTINEL, _format_context, _MARKER_RE,
                                  extract_write_suggestion)
from src.agents.nodes import _parse_plan_tiered
from src.agents.routing import parse_proposal, decide_route
from src.agents.language import _EN_WORDS, _WORD as _EN_WORD_RE
from src.agents.user_memory import extract_memory_markers, is_document_code
from src.erp_query.tools import build_erp_query_tools
from jobs.resilience import run_resilient
from evals import role_config


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


def baseline_path(model: str, set_name: str, role: str = "admin") -> str:
    """Đường dẫn file baseline. MỘT nguồn sự thật cho quy ước tên — eval_gate
    import lại hàm này thay vì tự ghép chuỗi.

    Vai admin KHÔNG có hậu tố: 6 file baseline đang có mang đúng tên đó, và đổi
    tên chúng là làm hỏng mọi lệnh lẫn mọi tham chiếu đang dùng. Nói cách khác:
    không hậu tố NGHĨA LÀ admin.

    Và hậu tố vai CHỈ tồn tại với bộ nhạy vai. Bộ như `confirm`/`read`/
    `synthesis`/`multi_source` không nhận tham số `role` (hàm đo của chúng
    không có tham số đó), nên đo chúng ở vai kế toán cho ra kết quả y hệt vai
    admin — một file `baseline-…-confirm-accounting.json` sẽ chỉ là bản sao
    mang tên gây hiểu nhầm, và KHÔNG AI TỪNG GHI nó ra. Không chuẩn hoá ở đây
    thì `--set both` (mặc định của job) với bất kỳ vai non-admin nào là hỏng
    vĩnh viễn: cổng đi tìm bốn file không tồn tại → INFRA_ERROR.

    Chuẩn hoá đặt ở ĐÂY chứ không ở hai chỗ gọi, vì đây là nơi giữ quy ước tên —
    để hai nơi tự nhớ "nhớ hạ role về admin" là đúng cách nó trôi lệch.
    """
    if set_name not in role_config.ROLE_SENSITIVE_SETS:
        role = "admin"
    here = os.path.dirname(__file__)
    stem = f"baseline-{model.replace(':', '-')}-{set_name}"
    if role != "admin":
        stem = f"{stem}-{role}"
    return os.path.join(here, f"{stem}.json")


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


async def eval_planner(llm, pace: float = 0.0, checkpoint_path=None,
                       role: str = "admin"):
    """Đo QUYẾT ĐỊNH của write-planner bằng MỘT lời gọi (spec §4.0a).
    Dùng _parse_plan_tiered (thuần) — KHÔNG dùng _plan_json vì nó ghi
    friction log production. Không corrective-retry: đo chất lượng lần đầu;
    lần parse thất bại được ghi riêng vào parse_fail."""
    # Prompt phải là prompt VAI NÀY thật sự chạy — dựng MỘT LẦN trước vòng
    # lặp (gọi role_config.planner_prompt 25 lần cho 25 ca là lãng phí).
    prompt = role_config.planner_prompt(role)
    lat: list[float] = []

    async def call(case):
        text, exp_tool, exp_args = case
        resp, ms = await _timed(llm.ainvoke(
            [SystemMessage(content=prompt),
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


async def eval_read(llm, pace: float = 0.0, checkpoint_path=None,
                    memory: str | None = None):
    """Đo QUYẾT ĐỊNH chọn tool đọc bằng MỘT lời gọi có bind_tools — KHÔNG
    thực thi tool, không cần Odoo sống (spec §4.0a). Mirror SYSTEM_PROMPT
    thật; không chạy verify_erp_grounding (đo riêng ở multi_source)."""
    # Ghep khoi ky uc Y HET erp_node (nodes.py:49-51): memory + "\n\n" + prompt.
    #
    # VI SAO PHAI DO DUONG NAY. Ky uc song o BA cho, va day la cho DUY NHAT
    # chua tung do — dong thoi la duong THAO TAC GHI that su chay. Ba do khac
    # cho ket qua khong dong nhat (RAG: hai, phai cat; fuse: hon hop), nen suy
    # doan cho nay tu hai cho kia la khong co co so.
    system = ((MEMORY_PRESETS[memory] + "\n\n" + SYSTEM_PROMPT)
              if memory else SYSTEM_PROMPT)
    bound = llm.bind_tools(build_erp_query_tools())
    lat: list[float] = []

    async def call(case):
        text, exp_tool, exp_args, entity_keys = case
        resp, ms = await _timed(bound.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=text)]))
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
            "memory_preset": memory or "none",
            "tool_acc": (measured - tool_wrong) / n if n else 0.0,
            "param_acc": (measured - len(fails)) / n if n else 0.0,
            "fabricated_param": fabricated_param,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


async def eval_intent(llm, pace: float = 0.0, checkpoint_path=None,
                      role: str = "admin"):
    """Đo trên ĐÚNG hợp đồng router thật (SP-2a Task 8): INTENT_ROUTER_PROMPT
    giờ đòi 2 dòng "intent:"/"sop:", không còn 1 từ trần — parse bằng
    parse_proposal CHUNG với node thật (routing.py) và eval_sop_select,
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
    hưởng phân loại).

    role (2026-08-14): Prompt phải là prompt VAI NÀY thật sự chạy, không phải
    tập skill đầy đủ. Đo 2026-08-14: vai kế toán chạy worker block RỖNG (0/3
    skill) trong khi bộ đo cũ luôn đo 3/3 — nên số cũ chỉ nói về vai admin."""
    prompt = role_config.intent_prompt(role)
    valid_sops = role_config.valid_sops(role)
    lat: list[float] = []

    async def call(case):
        text, expected = case
        resp, ms = await _timed(llm.ainvoke(
            [SystemMessage(content=prompt),
             HumanMessage(content=text)]))
        lat.append(ms)
        got, _sop, _depth = parse_proposal(resp.content, valid_sops)
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


# Kỳ vọng KHÔNG phải yêu cầu làm việc: tra cứu tài liệu / đọc dữ liệu. Ca kỳ
# vọng `clarify_depth` CỐ Ý không có mặt — đó vẫn là yêu cầu làm việc, chỉ chưa
# rõ độ sâu.
NON_WORK_EXPECTATIONS = frozenset({"rag", "erp_read", "mixed", "unknown"})


def _is_hijack(expected: str, sop: str | None) -> bool:
    """Hướng NGUY HIỂM: một câu KHÔNG phải yêu cầu làm việc mà bị router gán
    cho một miền nghiệp vụ.

    Công thức cũ (`expected not in valid_sops and got in valid_sops`) hỏng hai
    đầu, cả hai đo được 2026-08-17:
    - DƯƠNG TÍNH GIẢ: ca kỳ vọng `clarify_depth` chạy thẳng SOP của đúng miền
      đó bị đếm là hijack, dù không có gì bị chiếm quyền.
    - ĐIỂM MÙ: câu tra cứu bị điền `sop` rồi đi `erp_write` (depth=one_step)
      thì `got` không phải tên node SOP nên không được đếm — đúng lúc đợt tách
      miền/độ sâu làm `sop` được điền nhiều hơn hẳn.

    Chấm trên `sop` THÔ của router, không trên đích cuối: lớp phủ quyết tất
    định có cứu được lượt đó hay không là chuyện khác — router đã nhận nhầm
    miền thì vẫn phải nổi lên.
    """
    return expected in NON_WORK_EXPECTATIONS and sop is not None


async def eval_sop_select(llm, pace: float = 0.0, checkpoint_path=None,
                          role: str = "admin"):
    """Đo việc CHỌN SOP end-to-end: gọi router thật với prompt thật (đã nối
    khối mô tả worker), parse bằng chính parse_proposal của node, rồi áp
    chính decide_route của routing. Đo cả chuỗi vì lớp phủ quyết tất định LÀ
    một phần của cơ chế — đo riêng đầu ra thô của model sẽ không nói lên điều
    gì về hành vi thật.

    Gate TUYỆT ĐỐI (giống chitchat, không baseline-relative): đây là hàng rào
    an toàn định tuyến, không phải phép đo chất lượng tương đối. Hướng nguy
    hiểm được đếm riêng: `hijack` = ca kỳ vọng KHÔNG phải SOP mà lại rơi vào
    SOP — đúng lỗi đã xảy ra thật.

    role (2026-08-14): prompt VAI NÀY thật sự chạy — cùng nguồn dựng với
    eval_intent (role_config), không tự dựng lại."""
    prompt = role_config.intent_prompt(role)
    valid_sops = role_config.valid_sops(role)
    lat: list[float] = []

    async def call(case):
        text, expected, expected_depth = case
        resp, ms = await _timed(llm.ainvoke(
            [SystemMessage(content=prompt), HumanMessage(content=text)]))
        lat.append(ms)
        intent, sop, depth = parse_proposal(resp.content, valid_sops)
        got = decide_route({"messages": [HumanMessage(content=text)],
                            "intent": intent, "sop": sop, "depth": depth})
        depth_ok = depth == expected_depth
        if got == expected and depth_ok:
            return None
        return {"text": text, "expected": expected, "got": got,
                "expected_depth": expected_depth, "got_depth": depth,
                "depth_ok": depth_ok,
                "raw_intent": intent, "raw_sop": sop,
                "hijack": _is_hijack(expected, sop)}

    fails, errors = await run_resilient(SOP_SELECT_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(SOP_SELECT_CASES)
    # CHỈ đếm từ fails (phép đo thành công) — lỗi API không bao giờ là hijack.
    hijack = sum(1 for f in fails if f["hijack"])
    depth_wrong = sum(1 for f in fails if not f["depth_ok"])
    p50, p95 = _percentiles(lat)
    return {"set": "sop_select", "n": n,
            "acc": (n - len(fails) - len(errors)) / n if n else 0.0,
            "depth_acc": (n - depth_wrong - len(errors)) / n if n else 0.0,
            "hijack": hijack,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


async def eval_localize(llm, pace: float = 0.0, checkpoint_path=None):
    """Đo lớp dịch chuỗi điều phối: BẢN DỊCH GIỮ ĐỦ SỰ VIỆC hay không.

    `acc` = tỉ lệ ca trả về BẢN DỊCH (tức đã qua lớp phủ quyết).
    `fact_loss` = số ca lớp phủ quyết phải chặn (bản dịch làm mất/đổi sự
    việc). fact_loss > 0 KHÔNG phải lỗi hệ thống — đó là cổng làm đúng việc;
    nhưng nó đo được model dịch tệ tới đâu, nên phải nổi lên trong báo cáo.
    """
    from src.agents.localize import facts_survived, localize
    lat: list[float] = []

    async def call(case):
        text, lang = case
        out, ms = await _timed(localize(text, lang, llm))
        lat.append(ms)
        if out != text:
            return None                    # đã dịch và qua lớp phủ quyết
        return {"text": text[:80], "lang": lang,
                "reason": "roi_ve_ban_goc"}

    fails, errors = await run_resilient(LOCALIZE_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(LOCALIZE_CASES)
    p50, p95 = _percentiles(lat)
    return {"set": "localize", "n": n,
            "acc": (n - len(fails) - len(errors)) / n if n else 0.0,
            "fact_loss": len(fails),
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


# Hư từ tiếng Việt. CỐ Ý không dùng dấu thanh: tên tài liệu/sản phẩm/đối tác
# tiếng Việt được phép (và phải) giữ nguyên trong câu trả lời tiếng Anh — đếm
# dấu thanh làm bộ dò báo động giả trên chính phần trích dẫn nguồn (đo được ở
# spike 2026-08-18).
#
# GIỚI HẠN: "từ" vừa có nghĩa giới từ (from/of) vừa là âm tiết đầu từ ghép
# "từ điển" (dictionary) hoặc tên riêng "Từ Liêm". Ranh giới từ `\b` không phân
# biệt được hai trường hợp — cần NER thật để tách riêng. Giới hạn này KHÔNG
# kích hoạt với 6 ca LANGUAGE_CASES hiện có (không ca nào chứa ngữ cảnh RAG hay
# trích dẫn tài liệu thật). Sẽ giải quyết nếu sau này detect false-positive ở
# vấn đề này.
_VI_FUNCTION_WORDS = re.compile(
    r"\b(của|và|là|cho|không|được|với|các|những|này|tôi|bạn|mình|hãy|"
    r"nếu|theo|khi|đã|sẽ|có thể|vui lòng|từ)\b", re.IGNORECASE)


def looks_vietnamese(text: str) -> bool:
    """Câu trả lời được VIẾT bằng tiếng Việt?

    Chấm trên HƯ TỪ chứ không trên dấu thanh: một câu tiếng Anh trích tên tài
    liệu "Quy trình nhập kho" là ĐÚNG, không phải lỗi.
    """
    return bool(_VI_FUNCTION_WORDS.search(text or ""))


def _has_english_evidence(text: str) -> bool:
    """Câu trả lời có BẰNG CHỨNG DƯƠNG là tiếng Anh không (không chỉ vì thiếu
    tiếng Việt)?

    Dùng chung bộ hư từ tiếng Anh của src.agents.language.detect_lang (Fix 1)
    thay vì tự chép lại danh sách — cùng lý do reuse của render_fuse_input:
    hai bản sao trôi lệch nhau là nguồn lỗi. Đây là chiều phụ thuộc ĐÚNG (eval
    infra → src), khác với localize._has_vietnamese_prose phải tự chứa vì
    chiều ngược lại (src → evals) sẽ đảo layering.
    """
    words = set(_EN_WORD_RE.findall((text or "").lower()))
    return len(words & _EN_WORDS) >= 2


async def eval_language(llm, pace: float = 0.0, checkpoint_path=None):
    """Câu trả lời có theo ngôn ngữ người dùng không — đo tầng PROMPT.

    Gọi thẳng từng prompt với một câu hỏi, không dựng graph: thứ đang đo là
    khối LANGUAGE_RULE, không phải định tuyến.

    RAG_SYNTHESIS_PROMPT là NGOẠI LỆ bắt buộc: gọi bare (không TÀI LIỆU) thì
    prompt LUÔN trả đúng một hằng số SENTINEL ("KHÔNG_ĐỦ_THÔNG_TIN", xem
    synthesis.py) bất kể câu hỏi ngôn ngữ nào — không phải văn xuôi, không có
    "ngôn ngữ" để đo, và trước khi `looks_vietnamese()` có ranh giới `\\b`
    (Task 6 fix round 1), ca "vi" tình cờ khớp ĐÚNG chỉ vì "không" là chuỗi
    con thô của "KHÔNG_ĐỦ..." — không phải model thật sự viết tiếng Việt.
    Bơm TÀI LIỆU thật (đúng hình dạng synthesize(), cùng topic
    chinh_sach_hoan_hang mà 2 câu hỏi LANGUAGE_CASES đã nhắm tới) để model có
    nội dung thật để trả lời bằng văn xuôi — đây cũng chính là ca thật sự
    kiểm được rủi ro trích dẫn danh từ riêng tiếng Việt mà spec §2.4 nói tới.

    FUSE_PROMPT nhận cùng cách xử lý (final review, 2026-08-18): gọi bare
    (không TÀI LIỆU + DỮ LIỆU ERP) thì không tái tạo được đúng lỗi gốc mà spec
    §2.3 ghi lại — luật ngôn ngữ bị SỨC NẶNG của ngữ cảnh tiếng Việt thật (tài
    liệu + khối ERP) lấn át, một lượt gọi trơ trụi không mang sức nặng đó. Bơm
    qua `render_fuse_input` (đúng hàm production dùng, topic sla_giao_hang —
    cùng topic 2 câu hỏi LANGUAGE_CASES của FUSE_PROMPT nhắm tới) để ca eval
    này thật sự kiểm được lỗi nó được viết ra để bắt.
    """
    from src.agents import prompts as prompts_mod
    lat: list[float] = []

    async def call(case):
        prompt_name, question, want = case
        system = getattr(prompts_mod, prompt_name)
        if prompt_name == "RAG_SYNTHESIS_PROMPT":
            chunks = fixtures.load_chunks("chinh_sach_hoan_hang")
            human = (f"TÀI LIỆU:\n{_format_context(chunks)}"
                     f"\n\nCÂU HỎI: {question}")
        elif prompt_name == "FUSE_PROMPT":
            chunks = fixtures.load_chunks("sla_giao_hang")
            erp_block = "Đơn S00165 | Azure Interior | trạng thái sale | 1.500.000"
            human = render_fuse_input(chunks, erp_block, question)
        else:
            human = question
        resp, ms = await _timed(llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=human)]))
        lat.append(ms)
        body = (resp.content or "").strip()
        if not body:
            return {"prompt": prompt_name, "question": question,
                    "want": want, "got": "EMPTY", "body": ""}
        if looks_vietnamese(body):
            got = "vi"
        elif _has_english_evidence(body):
            got = "en"
        else:
            return {"prompt": prompt_name, "question": question,
                    "want": want, "got": "INCONCLUSIVE", "body": body[:160]}
        if got == want:
            return None
        return {"prompt": prompt_name, "question": question,
                "want": want, "got": got, "body": body[:160]}

    fails, errors = await run_resilient(LANGUAGE_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(LANGUAGE_CASES)
    p50, p95 = _percentiles(lat)
    return {"set": "language", "n": n,
            "acc": (n - len(fails) - len(errors)) / n if n else 0.0,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


async def eval_memory(llm, pace: float = 0.0, checkpoint_path=None,
                      memory: str | None = None):
    """Ký ức có bị ghi vu vơ không — đo tầng PROMPT + cổng phủ quyết.

    BA chỉ số gác TUYỆT ĐỐI vì đều là hướng nguy hiểm:
      false_injection — ghi HOẶC XOÁ một fact người dùng không hề khai (một
        GHI_NHỚ hoặc QUÊN bịa ra — final review: chiều QUÊN vốn bị bỏ sót,
        nguy hiểm hơn cả GHI_NHỚ vì nó XOÁ ký ức thật). Ký ức sai KHÔNG báo
        lỗi, nó chỉ âm thầm làm mọi câu trả lời sau tệ đi. Với want="none",
        một câu trả lời bị CỤT cũng tính vào chỉ số này (xem `truncated` bên
        dưới) — cụt ở bucket này luôn đi kèm marker giả hoặc marker thật bị
        cắt lem, cùng họ lỗi với ghi vu vơ.
      leaked_doc_code — mã chứng từ lọt vào ký ức, rồi rò sang cloud chitchat
        ở lượt sau (M5/ADR-009).
      truncated_answer — câu trả lời bị marker CẮT CỤT (`extract_memory_markers`
        nuốt luôn một phần văn bản dành cho người dùng) ở want="fact"/"blocked"
        (want="none" đã gộp vào false_injection ở trên, không đếm trùng ở đây).
        Debt sweep sau merge: trước đó chỉ số này ghi nhận suông, không gác —
        cụt câu trả lời là dấu hiệu lỗi ranh giới marker bất kể bucket nào,
        không có lý do để miễn gác riêng hai bucket này.
    `recall` chỉ ghi nhận, chưa gác tuyệt đối vì chưa có baseline.

    CHÂN ĐỐI CHỨNG `--memory`: cả 7 ca vốn chạy với khối ký ức RỖNG (một lượt,
    không fact có sẵn), trong khi production từ lượt thứ hai trở đi LUÔN có
    khối khác rỗng ghép vào đầu prompt (nodes.py:51, :139). Sau khi cắt ký ức
    khỏi đường RAG, hai hợp đồng token chính xác còn lại — `GHI_NHỚ:`/`QUÊN:`
    và `ĐỀ_XUẤT_GHI` — đều nằm SAU khối đó, tức chính cơ chế mà tính năng ký
    ức sống nhờ. Bộ synthesis_live đã đo được khối ký ức ĐỦ SỨC lấn một chỉ
    thị định dạng cứng (model bỏ phát KHÔNG_ĐỦ_THÔNG_TIN), nên rủi ro "càng
    nhiều fact thì marker càng dễ tịt" là thật và chưa từng được đo. Chân này
    đo nó: cùng 7 ca, đổi ĐÚNG một biến.
    """
    from src.agents import prompts as prompts_mod
    lat: list[float] = []
    memory_block = MEMORY_PRESETS[memory] if memory else ""

    async def call(case):
        prompt_name, question, want = case
        system = getattr(prompts_mod, prompt_name)
        # Ghép ĐÚNG như production: erp_node/chitchat làm
        # `prompt = memory + "\n\n" + prompt` (nodes.py:51, :139).
        if memory_block:
            system = memory_block + "\n\n" + system
        resp, ms = await _timed(llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=question)]))
        lat.append(ms)
        body = (resp.content or "").strip()
        clean, saves, forgets = extract_memory_markers(body)
        stored = [(k, v) for k, v in saves if not is_document_code(v)]
        # Final review, Finding 5: một QUÊN bịa ra (chiều Finding 1) XOÁ một
        # ký ức thật — nguy hiểm hơn cả false_injection (ghi vu vơ), nhưng
        # nhánh cũ chỉ đếm `saves`, bỏ hẳn `forgets`. Đồng thời một marker
        # rỗng-giá-trị vẫn CẮT khỏi `body` mà không lọt vào saves LẪN forgets
        # (xem extract_memory_markers) — bỏ hẳn `clean` như bản cũ
        # (`_clean, saves, _forgets = ...`) nghĩa là không cổng nào thấy câu
        # trả lời bị cụt. `truncated` bắt CHÍNH triệu chứng đó.
        truncated = bool(body) and not clean
        if want == "none" and (saves or forgets or truncated):
            return {"case": question, "want": want, "got_saves": saves,
                    "got_forgets": forgets, "truncated": truncated,
                    "kind": "false_injection"}
        if want == "fact" and not stored:
            return {"case": question, "want": want, "got": saves,
                    "kind": "missed"}
        if want == "blocked" and stored:
            return {"case": question, "want": want, "got": stored,
                    "kind": "leaked_doc_code"}
        if truncated:
            return {"case": question, "want": want, "got_saves": saves,
                    "got_forgets": forgets, "kind": "truncated_answer"}
        return None

    fails, errors = await run_resilient(MEMORY_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(MEMORY_CASES)
    p50, p95 = _percentiles(lat)
    want_fact = sum(1 for c in MEMORY_CASES if c[2] == "fact")
    missed = sum(1 for f in fails if f["kind"] == "missed")
    return {"set": "memory", "memory_preset": memory or "none",
            "n": n,
            "false_injection": sum(1 for f in fails if f["kind"] == "false_injection"),
            "leaked_doc_code": sum(1 for f in fails if f["kind"] == "leaked_doc_code"),
            "truncated_answer": sum(1 for f in fails if f["kind"] == "truncated_answer"),
            "recall": (want_fact - missed) / want_fact if want_fact else 0.0,
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


def _strip_write_marker(content) -> str:
    """Thân câu trả lời fuse ĐÚNG NHƯ production nhìn thấy nó.

    fuse_answer (fanout.py) LUÔN gọi extract_write_suggestion() cắt dòng
    ĐỀ_XUẤT_GHI trước khi làm bất cứ việc gì khác với câu trả lời, nên chấm
    điểm trên resp.content thô là chấm một chuỗi mà production không bao giờ
    dùng — đúng loại trôi lệch prod/eval mà docstring eval_multi_source ghi là
    đã một lần làm acc rơi 0.870 → 0.148 (SP-2a). Boolean trả về bị bỏ: eval
    chỉ cần văn bản sạch, không cần tín hiệu định tuyến.
    """
    body, _ = extract_write_suggestion((content or "").strip())
    return body


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


async def eval_multi_source(llm, pace: float = 0.0, checkpoint_path=None,
                           memory: str | None = None):
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
    # Ghep khoi ky uc Y HET production: fanout.py:202-204 lam
    # `system = memory + "\n\n" + FUSE_PROMPT`. Dung lai chinh cong thuc do,
    # khong dung lai bang tay — day la dieu kien de mirror khong troi.
    #
    # VI SAO PHAI DO DUONG NAY. Ky uc da bi CAT khoi rag_node (ce2704b) sau khi
    # do ra ba loai fact deu khong duong tren duong tai lieu. Nhung fuse_answer
    # VAN nhan khoi ky uc, va no cung sinh cau tra loi co can cu tai lieu: cung
    # hop dong NGUON_DUNG:, cung cite_and_verify. Nguoi dung THAT dang mang san
    # fact `do_dai_phan_hoi = ngan_gon` — dung loai fact da do duoc lam mat 8,3%
    # fact_acc tren duong RAG.
    system = ((MEMORY_PRESETS[memory] + "\n\n" + FUSE_PROMPT)
              if memory else FUSE_PROMPT)
    lat: list[float] = []

    async def call(case):
        topic, erp_block, question, doc_fact, erp_fact = case
        chunks = fixtures.load_chunks(topic)
        resp, ms = await _timed(llm.ainvoke([
            SystemMessage(content=system),
            HumanMessage(content=render_fuse_input(chunks, erp_block, question)),
        ]))
        lat.append(ms)
        body = _strip_write_marker(resp.content)
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
            "memory_preset": memory or "none",
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
        body = _strip_write_marker(resp.content)
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


async def eval_retrieval(pace: float = 0.0, checkpoint_path=None,
                         rerank: bool = True):
    """Đo TẦNG TRUY XUẤT trên corpus thật — KHÔNG gọi LLM lần nào.

    Khác mọi bộ eval khác ở đúng điểm này: `synthesis` và `multi_source` nạp
    fixtures.load_chunks(), tức retriever bị bypass và chúng đo LLM trên ngữ
    cảnh hoàn hảo. Đó là lý do reranker chết 6 tuần mà không số đo nào nhúc
    nhích. Bộ này gọi retrieve() thật.

    rerank=False đặt RAG_RERANK_ENABLED=0 cho cả lượt chạy — chân đối chứng
    của rerank_delta (spec §6).
    """
    lat: list[float] = []
    per_case: list[dict] = []
    prev = os.environ.get("RAG_RERANK_ENABLED")
    os.environ["RAG_RERANK_ENABLED"] = "1" if rerank else "0"

    async def call(case):
        question, expected, difficulty = case
        # k=_TOP_N, KHÔNG phải mặc định _TOP_K: retrieve() cắt còn k TRƯỚC khi
        # trả về (retrieve.py compress()), nên gọi mặc định thì result.chunks
        # chỉ có 6 phần tử và "recall@20" sẽ chấm trên đúng 6 chunk đó — là
        # recall@6 dưới một cái tên khác. Ban đầu tự định nghĩa sai chỗ này;
        # phép kiểm bất biến bắt được (recall@20 đổi khi bật/tắt rerank, điều
        # không thể xảy ra nếu đo đúng pool).
        #
        # An toàn vì compress() chỉ là phép cắt tiền tố: 6 chunk đầu của lượt
        # k=20 giống HỆT production k=6. Không đổi một dòng production nào.
        result, ms = await _timed(
            asyncio.to_thread(_retrieve, question, _TOP_N))
        lat.append(ms)
        ranked = [label_of(c) for c in result.chunks]
        score = score_one(ranked, {tuple(x) for x in expected},
                          k_pool=_TOP_N, k_final=_TOP_K)
        per_case.append({"question": question, "difficulty": difficulty,
                         "method": result.method, **score})
        if score["recall_at_pool"] > 0:
            return None
        return {"question": question, "difficulty": difficulty,
                "expected": [list(x) for x in expected], "got": ranked[:6],
                "method": result.method}

    try:
        fails, errors = await run_resilient(
            [(q, [list(x) for x in sorted(e)], d) for q, e, d in RETRIEVAL_CASES],
            call, pace=pace, checkpoint_path=checkpoint_path)
    finally:
        if prev is None:
            os.environ.pop("RAG_RERANK_ENABLED", None)
        else:
            os.environ["RAG_RERANK_ENABLED"] = prev

    n = len(RETRIEVAL_CASES)
    m = len(per_case) or 1

    def _avg(key: str, rows=None) -> float:
        rows = per_case if rows is None else rows
        return sum(r[key] for r in rows) / len(rows) if rows else 0.0

    by_difficulty = {}
    for d in ("easy", "hard", "trap"):
        rows = [r for r in per_case if r["difficulty"] == d]
        by_difficulty[d] = {"n": len(rows),
                            "recall_at_20": round(_avg("recall_at_pool", rows), 4),
                            "mrr": round(_avg("reciprocal_rank", rows), 4)}

    # chunk_span: nhãn phủ trung bình bao nhiêu chunk trong KẾT QUẢ. Tăng lên
    # nghĩa là neo (tệp, mục) đang mất sức phân giải (spec §4).
    span = sum(len(r["hit_ranks"]) for r in per_case) / m

    p50, p95 = _percentiles(lat)
    return {"set": "retrieval", "n": n, "rerank": rerank,
            "methods_seen": sorted({r["method"] for r in per_case}),
            "recall_at_20": round(_avg("recall_at_pool"), 4),
            "recall_at_6": round(_avg("recall_at_final"), 4),
            "mrr": round(_avg("reciprocal_rank"), 4),
            "chunk_span": round(span, 2),
            "by_difficulty": by_difficulty,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


async def eval_synthesis_live(llm, pace: float = 0.0, checkpoint_path=None,
                              memory: str | None = None):
    """Đo chuỗi TRẢ LỜI TÀI LIỆU đầu-cuối: retrieve() thật → synthesize() thật.

    Khác `synthesis` ở đúng một điểm, và đó là điểm quan trọng nhất:
    `synthesis` nạp fixtures.load_chunks() nên retriever bị bypass, còn bộ này
    gọi retrieve() thật trên corpus thật. Đó là lý do reranker chết 6 tuần mà
    không số đo nào nhúc nhích (spec 2026-08-19 §1).

    Gọi ĐÚNG synthesize() của production, không mirror hình dạng prompt. Bài
    học SP-2a: eval_intent mirror hợp đồng ở module khác, hợp đồng đổi, acc rơi
    0,870 → 0,148 và không ai nghi ngờ vì lỗi trông y hệt lỗi chất lượng model.
    """
    # `memory` là TÊN chân, không phải khối chữ: kết quả tự mang tên chân nên
    # một lượt chạy có ký ức không bao giờ bị đọc nhầm thành số của chân gốc.
    memory_block = MEMORY_PRESETS[memory] if memory else ""
    lat: list[float] = []
    per_case: list[dict] = []

    async def call(case):
        question, kind, expect, source = case[0], case[1], case[2], case[3]
        expect = tuple(expect) if isinstance(expect, list) else expect
        result = await asyncio.to_thread(_retrieve, question)
        # CẢNH BÁO — từ 2026-08-20 đây KHÔNG còn là đường production.
        # Chính số đo của ba chân này dẫn tới quyết định CẮT dây nối ký ức ở
        # rag_node (xem nodes.py::rag_node), nên production chạy `memory=""`.
        # Ba chân giữ lại làm DÂY BẪY: nếu ai nối ký ức vào đường tài liệu
        # lần nữa, chạy lại chỗ này là thấy ngay thiệt hại. Đừng đọc số của
        # chân khác rỗng như số của production.
        answer, ms = await _timed(
            _synthesize(question, result, llm, memory=memory_block))
        lat.append(ms)
        score = score_answer(answer, kind, expect, source)
        per_case.append({"kind": kind, **score})
        if all(v is not False for v in score.values()):
            return None
        return {"question": question, "kind": kind, "expect": expect,
                "expect_source": source, "answer": answer[:400], **score}

    # Chỉ 4 trường đầu của Case đi vào phép đo; `section`/`rival` là dữ liệu
    # cho test hợp đồng, không thuộc bài toán chấm điểm. expect dạng tuple →
    # list cho JSON-serializable, vì run_resilient ghi item vào error-record
    # và checkpoint.
    items = [[c.question, c.kind,
              list(c.expect) if isinstance(c.expect, tuple) else c.expect,
              c.source] for c in SYNTHESIS_LIVE_CASES]
    fails, errors = await run_resilient(items, call, pace=pace,
                                        checkpoint_path=checkpoint_path)

    def _acc(key: str, rows):
        """None = KHÔNG ÁP DỤNG cho nhóm này, không phải "trượt sạch".

        Trả 0.0 ở đây từng làm by_kind["insufficient"] in fact_acc=0.0 — đọc
        y hệt một nhóm hỏng hoàn toàn, trong khi nhóm đó vốn không có sự kiện
        nào để chấm."""
        vals = [r[key] for r in rows if r[key] is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    by_kind = {}
    for k in ("deep_chunk", "distractor", "insufficient"):
        rows = [r for r in per_case if r["kind"] == k]
        by_kind[k] = {"n": len(rows), "fact_acc": _acc("fact_ok", rows),
                      "refusal_acc": _acc("refusal_ok", rows),
                      "citation_acc": _acc("citation_ok", rows)}

    p50, p95 = _percentiles(lat)
    return {"set": "synthesis_live", "n": len(SYNTHESIS_LIVE_CASES),
            # Tên chân đi vào kết quả để một lượt chạy có ký ức không bao giờ
            # bị đọc nhầm thành số của chân gốc.
            "memory_preset": memory or "none",
            "fact_acc": _acc("fact_ok", per_case),
            "refusal_acc": _acc("refusal_ok", per_case),
            "citation_acc": _acc("citation_ok", per_case),
            "by_kind": by_kind,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


async def eval_multiturn(pace: float = 0.0, checkpoint_path=None):
    """Đo GIẢI CHIẾU ở câu hỏi nối tiếp — KHÔNG gọi LLM lần nào.

    `rag_node` lấy duy nhất tin nhắn cuối (`query = last_human.content`) cho cả
    truy xuất lẫn sinh; lịch sử hội thoại bị bỏ hoàn toàn. Cả 12 bộ eval trước
    đều một-lượt nên chỗ này chưa bao giờ được đo.

    Mỗi ca chạy HAI lần trong cùng lượt: không ngữ cảnh (đúng hành vi
    production hiện tại) và có ngữ cảnh (lượt trước đưa vào `aux_queries`).
    Đo cả hai trong một lượt là bắt buộc, không phải tiện tay — nhóm
    `independent` chỉ có nghĩa khi so được hai chiều, và nó là nửa duy nhất
    bắt được MẶT HẠI của việc trộn hai truy vấn vào cùng pool 20.
    """
    per_case: list[dict] = []

    async def call(case):
        prev, question, expect, kind = case[0], case[1], case[2], case[3]
        want = {tuple(x) for x in expect}
        no_ctx = await asyncio.to_thread(_retrieve, question, _TOP_N)
        with_ctx = await asyncio.to_thread(_retrieve, question, _TOP_N,
                                           None, (prev,))
        row = {"question": question, "kind": kind}
        for tag, res in (("no_ctx", no_ctx), ("with_ctx", with_ctx)):
            ranked = [label_of(c) for c in res.chunks]
            sc = score_one(ranked, want, k_pool=_TOP_N, k_final=_TOP_K)
            row[tag] = sc
        per_case.append(row)
        # Ca hỏng = có ngữ cảnh mà VẪN không tìm ra trong top-6.
        if row["with_ctx"]["recall_at_final"] > 0:
            return None
        return {"question": question, "kind": kind,
                "rank_no_ctx": row["no_ctx"]["hit_ranks"][:1],
                "rank_with_ctx": row["with_ctx"]["hit_ranks"][:1]}

    items = [[c.prev_turn, c.question, [list(x) for x in sorted(c.expect)], c.kind]
             for c in MULTITURN_CASES]
    fails, errors = await run_resilient(items, call, pace=pace,
                                        checkpoint_path=checkpoint_path)

    def _avg(tag: str, key: str, rows) -> float:
        return round(sum(r[tag][key] for r in rows) / len(rows), 4) if rows else 0.0

    by_kind = {}
    for k in ("elliptical", "independent"):
        rows = [r for r in per_case if r["kind"] == k]
        by_kind[k] = {
            "n": len(rows),
            "recall_at_6_no_ctx": _avg("no_ctx", "recall_at_final", rows),
            "recall_at_6_with_ctx": _avg("with_ctx", "recall_at_final", rows),
            "mrr_no_ctx": _avg("no_ctx", "reciprocal_rank", rows),
            "mrr_with_ctx": _avg("with_ctx", "reciprocal_rank", rows),
        }

    return {"set": "multiturn", "n": len(MULTITURN_CASES),
            "recall_at_6_no_ctx": _avg("no_ctx", "recall_at_final", per_case),
            "recall_at_6_with_ctx": _avg("with_ctx", "recall_at_final", per_case),
            "recall_at_20_no_ctx": _avg("no_ctx", "recall_at_pool", per_case),
            "recall_at_20_with_ctx": _avg("with_ctx", "recall_at_pool", per_case),
            "mrr_no_ctx": _avg("no_ctx", "reciprocal_rank", per_case),
            "mrr_with_ctx": _avg("with_ctx", "reciprocal_rank", per_case),
            "by_kind": by_kind,
            "fails": fails, "errors": errors}



async def eval_write_suggest(llm, pace: float = 0.0, checkpoint_path=None,
                             memory: str | None = None):
    """Marker `ĐỀ_XUẤT_GHI` có nói ĐÚNG về việc câu trả lời đang làm không?

    ĐO ĐỘ KHỚP, KHÔNG ĐO KỲ VỌNG. Bản đầu chấm marker so với nhãn tay
    `expect_marker` — tức khẳng định model NÊN quyết định gì. Model được phép
    chọn đề xuất, từ chối, hay hỏi làm rõ; cả ba đều hợp lệ, nên nhãn tay biến
    mọi thay đổi cách xử sự thành "hỏng". Đã trả giá hai lần cho sai lầm đó
    (xem docstring evals/write_suggest_oracle.py).

    Hợp đồng THẬT chỉ có một điều: **marker phải khớp với thứ câu trả lời thật
    sự làm** — hệ không được nói dối về việc nó có đang đề xuất hay không. Thẩm
    định độc lập (không thấy khối ký ức) phán, rồi so với marker.

    `expect_marker` GIỮ LẠI nhưng chỉ để báo cáo `proposed_rate`: trong 4 ca
    được thiết kế để mời một thao tác ghi, model thật sự đề xuất bao nhiêu lần.
    Đó là số đo HÀNH VI, không phải cổng đúng/sai — nó cho thấy khối ký ức đổi
    cách xử sự của trợ lý, chuyện hoàn toàn khác với việc phá hợp đồng marker.
    """
    system = ((MEMORY_PRESETS[memory] + "\n\n" + FUSE_PROMPT)
              if memory else FUSE_PROMPT)
    lat: list[float] = []
    per_case: list[dict] = []

    async def call(case):
        topic, erp_block, question, designed = case
        chunks = fixtures.load_chunks(topic)
        resp, ms = await _timed(llm.ainvoke([
            SystemMessage(content=system),
            HumanMessage(content=render_fuse_input(chunks, erp_block, question)),
        ]))
        lat.append(ms)
        raw = resp.content or ""
        clean, marker = extract_write_suggestion(raw)
        # Thẩm định KHÔNG thấy khối ký ức, và đọc bản ĐÃ BỎ marker để không
        # bị chính marker mớm đáp án.
        thuc_te = await oracle_proposes_write(clean, llm)
        per_case.append({"question": question, "designed": designed,
                         "marker": marker, "oracle": thuc_te})
        if thuc_te is None or marker == thuc_te:
            return None
        return {"question": question, "marker": marker, "oracle": thuc_te,
                "kind": "marker_noi_du" if marker else "marker_noi_thieu",
                "response_tail": raw[-300:]}

    items = [list(c) for c in WRITE_SUGGEST_CASES]
    fails, errors = await run_resilient(items, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(WRITE_SUGGEST_CASES)
    khong_phan_duoc = sum(1 for r in per_case if r["oracle"] is None)
    cham_duoc = len(per_case) - khong_phan_duoc
    moi_ghi = [r for r in per_case if r["designed"]]
    p50, p95 = _percentiles(lat)
    return {"set": "write_suggest", "n": n,
            "memory_preset": memory or "none",
            # Cổng THẬT: marker có khớp thực tế không.
            "agreement": (cham_duoc - len(fails)) / cham_duoc if cham_duoc else 0.0,
            "khong_phan_duoc": khong_phan_duoc,
            # Số đo HÀNH VI, không phải cổng: trong các ca mời thao tác ghi,
            # model thật sự đề xuất bao nhiêu lần.
            "proposed_rate": (sum(1 for r in moi_ghi if r["oracle"] is True)
                              / len(moi_ghi) if moi_ghi else 0.0),
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}


async def main(argv=None):
    # Console Windows mặc định cp1252: một thông điệp lỗi có dấu tiếng Việt
    # làm CHÍNH dòng in lỗi ném UnicodeEncodeError, nuốt mất chẩn đoán và đổi
    # exit 2 (INFRA ERROR đọc được) thành exit 1 trống rỗng. Gặp thật khi đo
    # chân --memory: lỗi thật là "cạn chuỗi ... =cooldown" nhưng không ai thấy.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--set",
                    choices=["intent", "confirm", "chitchat", "planner", "read",
                             "synthesis", "multi_source", "sop_select",
                             "language", "localize", "retrieval",
                             "synthesis_live", "multiturn", "memory",
                             "write_suggest"],
                    required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--role", default="admin",
                    choices=sorted(roles.load_profile()),
                    help="vai để dựng prompt (chỉ có tác dụng với "
                         "intent/sop_select/planner; các bộ khác bỏ qua)")
    ap.add_argument("--save-baseline", action="store_true")
    ap.add_argument("--baseline")
    ap.add_argument("--pace", type=float, default=0.0,
                    help="giây giãn cách giữa 2 call (suy từ catalog: "
                         "(60/rpm)*1.2 cho model đang ghim — vd rpm=15 → ~4.8)")
    ap.add_argument("--memory", choices=sorted(MEMORY_PRESETS),
                    help="voi --set synthesis_live hoac --set memory: chay "
                         "CHAN DOI CHUNG voi mot khoi ky uc khac rong")
    ap.add_argument("--no-rerank", action="store_true",
                    help="chi voi --set retrieval: chay chan doi chung "
                         "RAG_RERANK_ENABLED=0 de tinh rerank_delta")
    args = ap.parse_args(argv)

    _BO_NHAN_MEMORY = ("synthesis_live", "memory", "multi_source",
                       "write_suggest", "read")
    if args.memory and args.set not in _BO_NHAN_MEMORY:
        ap.error("--memory chỉ dùng được với --set "
                 + " / ".join(_BO_NHAN_MEMORY))
        # Baseline của synthesis_live LÀ chân memory="" — ghi đè nó bằng
        # số của một chân ký ức là tự tay xoá mốc so sánh, và lượt chạy
        # sau sẽ so chân gốc với một baseline không phải của nó. Chặn
        # cứng thay vì tin vào kỷ luật người chạy.
        ap.error("--memory không đi cùng --save-baseline: baseline của "
                 "synthesis_live là chân KHÔNG ký ức, ghi đè bằng số của "
                 "chân có ký ức sẽ xoá mốc so sánh")

    try:
        _FN = {"intent": eval_intent, "confirm": eval_confirm,
               "chitchat": eval_chitchat, "planner": eval_planner,
               "read": eval_read, "synthesis": eval_synthesis,
               "multi_source": eval_multi_source, "sop_select": eval_sop_select,
               "language": eval_language, "localize": eval_localize,
               "retrieval": eval_retrieval,
               "synthesis_live": eval_synthesis_live,
               "multiturn": eval_multiturn, "memory": eval_memory,
               "write_suggest": eval_write_suggest}
        kwargs = {"pace": args.pace}
        if args.set in ("memory", "multi_source", "write_suggest",
                        "read"):
            kwargs["memory"] = args.memory
        if args.set in role_config.ROLE_SENSITIVE_SETS:
            kwargs["role"] = args.role
        if args.set in ("retrieval", "multiturn"):
            # KHÔNG dựng LLM: bộ này thuần truy xuất. _llm() gọi
            # chain_for("retrieval") mà "retrieval" không nằm trong
            # catalog.ROLES → nổ ngay nếu đi đường chung.
            # KHÔNG dựng LLM: cả hai bộ này thuần truy xuất.
            if args.set == "retrieval":
                kwargs["rerank"] = not args.no_rerank
            result = await _FN[args.set](**kwargs)
        elif args.set == "synthesis_live":
            # "synthesis_live" KHÔNG nằm trong catalog.ROLES; production chạy
            # rag_node bằng llms["synthesis"], nên dùng đúng vai đó.
            result = await eval_synthesis_live(_llm(args.model, role="synthesis"),
                                               memory=args.memory, **kwargs)
        else:
            result = await _FN[args.set](_llm(args.model, role=args.set), **kwargs)
    except Exception as e:   # noqa: BLE001 — hạ tầng LLM sập (key/model/router hỏng)
        print(f"INFRA ERROR: {e}"); sys.exit(2)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    # S2 spec §3: đo không trọn vẹn → exit 2 TRƯỚC mọi nhánh baseline —
    # baseline khuyết tật sẽ đầu độc mọi gate về sau.
    if result["errors"]:
        print(f"INFRA ERROR: {len(result['errors'])} case lỗi sau retry — "
              "không đủ điều kiện gate/baseline")
        sys.exit(2)

    if args.save_baseline:
        path = baseline_path(args.model, args.set, args.role)
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
