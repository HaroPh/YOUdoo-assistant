# backend/jobs/eval_gate.py
"""Job eval-gate — tự động hóa cổng M3 (ADR-009 khóa #10; đóng R5/F10).

Mặc định đo config ĐANG SỐNG: intent-set trên chain_for("router")[0], confirm-set
trên chain_for("evaluator")[0] — đầu chuỗi catalog tĩnh (src/llm/catalog.py),
nên lịch đêm trả lời đúng câu hỏi "config production hiện tại còn khỏe so với
baseline không".
--model đo candidate trước khi flip; --set đo riêng 1 set khi xét flip 1 role
(bài học Task 6 Phase A: candidate pass intent nhưng fail confirm → flip router-only).
Pacing auto suy từ catalog: (60/rpm)*1.2 — chậm hơn mức RPM cho phép 20% để có biên.
S2: mỗi case retry bounded (resilience.py); case lỗi sau retry → INFRA_ERROR
(đo không trọn vẹn), circuit-breaker dừng sớm khi lỗi hệ thống.
"""
import asyncio
import json
from pathlib import Path

from evals import run_eval
from jobs import registry
from jobs.registry import (GATE_FAIL, INFRA_ERROR, PASS, Job, JobResult,
                           register)
from src.llm.catalog import chain_for

EVALS_DIR = Path(run_eval.__file__).resolve().parent

BASELINES = {
    "intent": EVALS_DIR / "baseline-qwen3-8b-intent.json",
    "confirm": EVALS_DIR / "baseline-qwen3-8b-confirm.json",
    "planner": EVALS_DIR / "baseline-qwen3-8b-planner.json",
    "read": EVALS_DIR / "baseline-qwen3-8b-read.json",
    "synthesis": EVALS_DIR / "baseline-qwen3-8b-synthesis.json",
    "multi_source": EVALS_DIR / "baseline-qwen3-8b-multi_source.json",
    # "chitchat": KHÔNG có entry — gate tuyệt đối (violations==0), không
    # baseline-relative (không có "câu trả lời đúng" cho chit-chat tự do).
}
ROLE_FOR_SET = {"intent": "router", "confirm": "evaluator", "chitchat": "chitchat",
                "planner": "planner", "read": "read", "synthesis": "synthesis",
                # role thật vẫn tên "fusion" trong catalog.py (CHAINS) —
                # "multi_source" chỉ là tên SET đo (trung tính, sống sót qua
                # đổi kiến trúc).
                "multi_source": "fusion", "sop_select": "router",
                "gather": "fusion"}
EVAL_FN = {"intent": run_eval.eval_intent, "confirm": run_eval.eval_confirm,
           "chitchat": run_eval.eval_chitchat, "planner": run_eval.eval_planner,
           "read": run_eval.eval_read, "synthesis": run_eval.eval_synthesis,
           "multi_source": run_eval.eval_multi_source,
           "sop_select": run_eval.eval_sop_select,
           "gather": run_eval.eval_gather}


def _gate(set_name: str, result: dict, base: dict | None) -> bool:
    # công thức GIỮ NGUYÊN VĂN run_eval / ADR-009 M3 cho intent/confirm.
    # chitchat: gate tuyệt đối, không baseline-relative.
    if set_name == "chitchat":
        return result["violations"] == 0
    if set_name == "sop_select":
        # Gate TUYỆT ĐỐI (§5.3 điều kiện 1: "xanh toàn bộ"), không
        # baseline-relative: đây là hàng rào an toàn định tuyến, không phải phép
        # đo chất lượng tương đối. hijack==0 là hệ quả của acc==1.0 nhưng vẫn
        # kiểm riêng — nó là hướng lỗi đã xảy ra THẬT (live-verify 2026-07-16)
        # và phải nổi rõ trong báo cáo khi gate trượt.
        return result["hijack"] == 0 and result["acc"] == 1.0
    if set_name == "planner":
        return (result["dangerous_misroute"] == 0
                and result["tool_acc"] >= base["tool_acc"])
    if set_name == "read":
        return (result["fabricated_param"] == 0
                and result["tool_acc"] >= base["tool_acc"])
    if set_name == "synthesis":
        return (result["false_answer"] == 0
                and result["grounded_acc"] >= base["grounded_acc"])
    if set_name == "multi_source":
        # Baseline qwen3:8b hiện fabricated_number=0 (đã chấm lại ở Task 6 —
        # gốc 4 → 1 sửa basis-mismatch; rồi ở SP-1C1 sau khi chạy gate live 2
        # lần đều fail cùng 1 ca ngày-tháng → 1 → 0 bằng
        # MULTI_SOURCE_DERIVED_DIGITS, số suy ra được ghi nhận thủ công cho
        # đúng case đó). Lý do đầy đủ + lịch sử quyết định (bao gồm vì sao
        # quyết định "chấp nhận, không mở rộng" ban đầu của Task 6 bị xem lại):
        # xem comment trên MULTI_SOURCE_CASES trong cases.py (dòng ~316-360).
        return (result["citation_validity"] == 1.0
                and result["fabricated_number"] == 0
                and result["both_source_coverage"] >= base["both_source_coverage"])
    if set_name == "gather":
        # Không có baseline model cũ (node gather_erp không tồn tại trước
        # SP-2b) — lần đo đầu chỉ ghi nhận, chưa có ngưỡng tuyệt đối. GÁC
        # NHẸ: mọi lần chạy đều PASS ở round này; số liệu vào báo cáo SP-2c
        # để người đọc tự đánh giá, không phải job tự đánh giá thay (spec
        # 2026-08-01-sp2c §2). Siết lại thành ngưỡng thật khi có đủ số đo.
        return True
    if set_name == "intent":
        return result["acc"] >= base["acc"]
    return (result["false_confirm"] == 0
            and result["acc"] >= base["acc"] - 1 / result["n"])


def run(args) -> JobResult:
    if args.set == "both":
        sets = ["intent", "confirm"]
    elif args.set == "all":
        # sop_select CỐ Ý không nằm trong "all" (quyết định người dùng, final
        # review fix wave 2026-07-31, Finding 5): gate tuyệt đối biết trước
        # FAIL 16/17 (ca hồi quy 2026-07-16, xem docs/superpowers/plans/
        # 2026-07-31-sp2a-sop-skills-report.md §2) — để nó trong "all" sẽ làm
        # job hàng đêm đỏ VĨNH VIỄN, che tín hiệu 7 gate khác đang khỏe. Vẫn
        # đăng ký đầy đủ trong EVAL_FN/add_args choices — theo dõi riêng qua
        # `--set sop_select`.
        # gather CŨNG cố ý không nằm trong "all" (spec 2026-08-01-sp2c §2):
        # chưa có baseline/ngưỡng tuyệt đối nào được xác nhận — để trong
        # "all" sẽ luôn PASS giả (gate trả True vô điều kiện) và làm loãng
        # tín hiệu của job hàng đêm mà không cảnh báo được gì thật. Theo dõi
        # riêng qua `--set gather` cho tới khi có đủ số đo để siết ngưỡng.
        sets = [s for s in EVAL_FN if s not in ("sop_select", "gather")]
    else:
        sets = [args.set]
    detail, any_fail = {}, False
    for set_name in sets:
        role = ROLE_FOR_SET[set_name]
        spec = chain_for(role)[0]
        model = args.model if args.model is not None else spec.alias
        # (60/rpm)*1.2: chậm hơn mức RPM cho phép 20% để có biên — suy trực
        # tiếp từ catalog, không còn khái niệm "local thì 0s" (không còn
        # model local nào trong catalog kể từ SP-1).
        pace = args.pace if args.pace is not None else (60.0 / spec.rpm) * 1.2
        try:
            # Đọc baseline TRƯỚC khi chạy eval thật (tốn call LLM, có pacing suy
            # từ rpm catalog) — baseline thiếu/hỏng thì fail nhanh, không đốt
            # call vô ích. chitchat KHÔNG có baseline (base ở lại None).
            base = None
            if set_name in BASELINES:
                base = json.loads(BASELINES[set_name].read_text(encoding="utf-8"))
            checkpoint = registry.LOGS_DIR / f"_checkpoint-eval-gate-{set_name}.json"
            try:
                result = asyncio.run(EVAL_FN[set_name](
                    run_eval._llm(model, role=role), pace=pace, checkpoint_path=checkpoint))
            finally:
                # Mỗi set chạy trong MỘT asyncio.run() riêng → một event loop
                # MỚI mỗi lần qua vòng lặp này. run_eval._router (và bên trong
                # nó, Router._clients) là cache CẢ TIẾN TRÌNH — client async
                # (ChatOpenAI/ChatGoogleGenerativeAI) bám vào loop đã tạo ra
                # nó, nên router dựng ở set trước mang theo client CHẾT khi
                # set sau chạy trên loop mới ("Event loop is closed", đã thấy
                # thật ở Task 7). Reset ở ĐÂY (resource lifecycle, không phải
                # cosmetic, không đụng công thức _gate()) để _get_router() bắt
                # buộc dựng lại router+client MỚI cho set kế tiếp — đặt trong
                # finally để chạy cả khi set này raise.
                run_eval._router = None
        except Exception as e:  # noqa: BLE001 — hạ tầng LLM sập (key/model/baseline hỏng)
            detail[set_name] = {"model": model, "error": str(e)}
            return JobResult("eval-gate", INFRA_ERROR, "ERROR", detail)
        # S2 spec §3: có case lỗi sau retry = đo không trọn vẹn → INFRA_ERROR,
        # không có quyền PASS/FAIL (exit 1 phải luôn nghĩa "model kém").
        # CircuitBreakerOpen thì nổi từ asyncio.run vào except ở trên.
        if result.get("errors"):
            detail[set_name] = {"model": model, "pace": pace,
                                "errors": result["errors"],
                                "fails": result["fails"]}
            print(f"[{set_name}] model={model} INFRA ERROR: "
                  f"{len(result['errors'])} case lỗi sau retry — đo không trọn vẹn")
            return JobResult("eval-gate", INFRA_ERROR, "ERROR", detail)
        ok = _gate(set_name, result, base)
        any_fail |= not ok
        entry = {"model": model, "pace": pace, "gate": "PASS" if ok else "FAIL",
                 "fails": result["fails"]}
        if base is not None:
            acc_key = ("tool_acc" if set_name in ("planner", "read")
                       else "grounded_acc" if set_name == "synthesis"
                       else "both_source_coverage" if set_name == "multi_source"
                       else "acc")
            entry.update(**{acc_key: result[acc_key]},
                         baseline_acc=base[acc_key],
                         false_confirm=result.get("false_confirm"),
                         dangerous_misroute=result.get("dangerous_misroute"),
                         fabricated_param=result.get("fabricated_param"),
                         false_answer=result.get("false_answer"),
                         citation_validity=result.get("citation_validity"),
                         fabricated_number=result.get("fabricated_number"),
                         lat_p50=result.get("lat_p50"),
                         lat_p95=result.get("lat_p95"))
            print(f"[{set_name}] model={model} pace={pace}s "
                  f"{acc_key}={result[acc_key]:.3f} "
                  f"baseline={base[acc_key]:.3f} → {'PASS' if ok else 'FAIL'}")
        else:
            # base is None: chitchat (violations) hoặc sop_select (acc + hijack)
            if set_name == "sop_select":
                entry["acc"] = result.get("acc")
                entry["hijack"] = result.get("hijack")
                entry.update(lat_p50=result.get("lat_p50"),
                             lat_p95=result.get("lat_p95"))
                print(f"[{set_name}] model={model} pace={pace}s "
                      f"acc={result.get('acc')} hijack={result.get('hijack')} "
                      f"→ {'PASS' if ok else 'FAIL'}")
            else:
                # chitchat
                entry["violations"] = result["violations"]
                entry.update(lat_p50=result.get("lat_p50"),
                             lat_p95=result.get("lat_p95"))
                print(f"[{set_name}] model={model} pace={pace}s "
                      f"violations={result['violations']} → {'PASS' if ok else 'FAIL'}")
        detail[set_name] = entry
    verdict = "FAIL" if any_fail else "PASS"
    return JobResult("eval-gate", GATE_FAIL if any_fail else PASS, verdict, detail)


def add_args(p):
    p.add_argument("--model", default=None,
                   help="candidate model (mặc định: đầu chuỗi chain_for(role) trong catalog)")
    p.add_argument("--set",
                   choices=["both", "all", "intent", "confirm", "chitchat",
                            "planner", "read", "synthesis", "multi_source",
                            "sop_select", "gather"],
                   default="both")
    p.add_argument("--pace", type=float, default=None,
                   help="giây/call (mặc định auto: (60/rpm)*1.2 suy từ catalog)")


register(Job("eval-gate", run,
             "M3 gate: intent+confirm vs baseline + chitchat anti-hallucination "
             "(mặc định đo config sống)",
             schedulable=True, add_args=add_args))
