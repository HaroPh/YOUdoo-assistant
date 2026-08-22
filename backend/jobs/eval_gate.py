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

from evals import role_config, run_eval
from jobs import registry
from jobs.registry import (GATE_FAIL, INFRA_ERROR, PASS, Job, JobResult,
                           register)
from src.agents import roles
from src.llm.catalog import chain_for, nhip_toi_thieu, spec_for

# Bộ nào so với baseline (khác cổng TUYỆT ĐỐI). chitchat và sop_select KHÔNG
# có mặt: chúng là cổng tuyệt đối (violations==0 / hijack==0), không phải phép
# đo tương đối — thêm baseline cho chúng là đổi ngữ nghĩa cổng.
BASELINE_SETS = frozenset({"intent", "confirm", "planner", "read",
                           "synthesis", "multi_source", "sop_select"})

# Model NEO của baseline — cố định, KHÔNG đổi theo model đang được ĐO (model
# catalog hiện hành hoặc --model candidate). "So ứng viên với chuẩn đã ghim"
# (xem docstring module) nghĩa là chuẩn phải đứng yên; 6 file baseline hiện có
# đều mang tên "qwen3-8b" dù catalog đã đổi model sống nhiều lần từ đó tới
# nay — đổi neo này sẽ làm hỏng mọi tham chiếu đang dùng (baseline chỉ đổi khi
# ai đó chủ động `run_eval.py --save-baseline` lại).
BASELINE_MODEL = "qwen3-8b"


def _baseline_for(set_name: str, model: str, role: str):
    """Đường dẫn baseline, hoặc None nếu bộ này là cổng tuyệt đối.

    Dùng LẠI run_eval.baseline_path — quy ước tên chỉ được sống ở một chỗ.
    """
    if set_name not in BASELINE_SETS:
        return None
    return run_eval.baseline_path(model, set_name, role)


ROLE_FOR_SET = {"intent": "router", "confirm": "evaluator", "chitchat": "chitchat",
                "planner": "planner", "read": "read", "synthesis": "synthesis",
                # role thật vẫn tên "fusion" trong catalog.py (CHAINS) —
                # "multi_source" chỉ là tên SET đo (trung tính, sống sót qua
                # đổi kiến trúc).
                "multi_source": "fusion", "sop_select": "router",
                # gather_erp và fuse_answer đều dùng role "fusion" — set này
                # chạy CẢ HAI nên vẫn đúng một role.
                "multi_source_gather": "fusion",
                "gather": "fusion",
                "localize": "evaluator",
                "language": "chitchat",
                "memory": "chitchat"}
EVAL_FN = {"intent": run_eval.eval_intent, "confirm": run_eval.eval_confirm,
           "chitchat": run_eval.eval_chitchat, "planner": run_eval.eval_planner,
           "read": run_eval.eval_read, "synthesis": run_eval.eval_synthesis,
           "multi_source": run_eval.eval_multi_source,
           "sop_select": run_eval.eval_sop_select,
           "gather": run_eval.eval_gather,
           "multi_source_gather": run_eval.eval_multi_source_gather,
           "localize": run_eval.eval_localize,
           "language": run_eval.eval_language,
           "memory": run_eval.eval_memory}


def _gate(set_name: str, result: dict, base: dict | None) -> bool:
    # công thức GIỮ NGUYÊN VĂN run_eval / ADR-009 M3 cho intent/confirm.
    # chitchat: gate tuyệt đối, không baseline-relative.
    if set_name == "chitchat":
        return result["violations"] == 0
    if set_name == "sop_select":
        # ĐỔI 2026-08-17: về đúng khuôn của 4 cổng anh em ngay dưới đây
        # (planner/read/synthesis/multi_source) — điều kiện AN TOÀN tuyệt đối
        # + chất lượng so baseline. Trước đó nó đòi acc == 1.0, gộp hai thứ
        # khác bản chất vào một cổng, và hệ quả ĐO ĐƯỢC là: đỏ vĩnh viễn từ
        # 2026-07-31 nên bị gỡ khỏi `--set all` — tức hàng rào an toàn định
        # tuyến KHÔNG được job nào gác suốt 6 tuần. Một cổng không ai chạy
        # thì không gác gì cả.
        #
        # hijack GIỮ TUYỆT ĐỐI: đó mới là hướng đã gây sự cố thật
        # (live-verify 2026-07-16), và nó vừa chứng minh giá trị lần nữa —
        # định nghĩa mới của nó (b4c8d12) chính là thứ bắt được hồi quy
        # "câu ĐỌC bị miền vơ" ngày 2026-08-17.
        #
        # Baseline-relative KHÔNG phải buông: acc tụt dưới baseline vẫn trượt.
        # Thứ duy nhất thôi bị đòi là sự hoàn hảo của một chỉ số chất lượng,
        # trên một tập ca mà 2 ca còn lại là giới hạn phán đoán độ sâu đã đo
        # và ghi lại (xem cases.py).
        return result["hijack"] == 0 and result["acc"] >= base["acc"]
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
    if set_name == "multi_source_gather":
        # Chưa có baseline: set này ra đời 2026-08-04, không model cũ nào
        # từng đo qua đường gather_erp thật. GÁC NHẸ y hệt `gather` — mọi
        # lần chạy PASS, số vào báo cáo để người đọc tự đánh giá, không phải
        # job tự đánh giá thay. Siết thành ngưỡng thật khi đủ số đo.
        return True
    if set_name == "gather":
        # Không có baseline model cũ (node gather_erp không tồn tại trước
        # SP-2b) — lần đo đầu chỉ ghi nhận, chưa có ngưỡng tuyệt đối. GÁC
        # NHẸ: mọi lần chạy đều PASS ở round này; số liệu vào báo cáo SP-2c
        # để người đọc tự đánh giá, không phải job tự đánh giá thay (spec
        # 2026-08-01-sp2c §2). Siết lại thành ngưỡng thật khi có đủ số đo.
        return True
    if set_name == "localize":
        # GÁC NHẸ ở đợt đầu, cùng lý do gather/multi_source_gather: chưa có số
        # đo nào để biết ngưỡng hợp lý. Số vào báo cáo để người đọc tự đánh
        # giá. Siết thành ngưỡng thật khi đủ số đo.
        return True
    if set_name == "language":
        # Gate TUYỆT ĐỐI: đây là thuộc tính nhị phân (đúng ngôn ngữ hay không),
        # không phải phép đo chất lượng tương đối. Trả lời sai ngôn ngữ là hỏng
        # hẳn với người dùng đó, không phải "kém hơn hôm qua".
        return result["acc"] == 1.0
    if set_name == "memory":
        # BA điều kiện TUYỆT ĐỐI, không so baseline: cả ba đều là hướng nguy
        # hiểm. false_injection / leaked_doc_code là ghi vu vơ / rò mã chứng
        # từ. truncated_answer THÊM VÀO (debt sweep sau merge): trước đây nó
        # chỉ đếm cho want="none" (đã gộp vào false_injection) và ghi nhận
        # suông cho want="fact"/"blocked" — một câu trả lời bị cụt là dấu
        # hiệu lỗi ranh giới marker BẤT KỂ bucket nào, không có lý do để
        # want="fact"/"blocked" được miễn gác. recall chưa gác vì chưa có
        # baseline — ghi số vào báo cáo để người đọc tự đánh giá.
        return (result["false_injection"] == 0
                and result["leaked_doc_code"] == 0
                and result["truncated_answer"] == 0)
    if set_name == "intent":
        return result["acc"] >= base["acc"]
    return (result["false_confirm"] == 0
            and result["acc"] >= base["acc"] - 1 / result["n"])


def run(args) -> JobResult:
    if args.set == "both":
        sets = ["intent", "confirm"]
    elif args.set == "all":
        # sop_select ĐÃ QUAY LẠI "all" (2026-08-17). Nó bị loại 2026-07-31 vì
        # gate tuyệt đối (acc == 1.0) biết trước FAIL 16/17 nên sẽ đỏ vĩnh
        # viễn và che tín hiệu các gate khác. Lý do đó HẾT: gate nay theo
        # khuôn chung (hijack==0 + acc>=baseline, xem _gate), nên nó báo động
        # khi có thứ THỰC SỰ tụt chứ không kêu suốt. Để nó ngoài "all" thêm
        # nữa nghĩa là hàng rào an toàn định tuyến tiếp tục không ai gác.
        # gather CŨNG cố ý không nằm trong "all" (spec 2026-08-01-sp2c §2):
        # chưa có baseline/ngưỡng tuyệt đối nào được xác nhận — để trong
        # "all" sẽ luôn PASS giả (gate trả True vô điều kiện) và làm loãng
        # tín hiệu của job hàng đêm mà không cảnh báo được gì thật. Theo dõi
        # riêng qua `--set gather` cho tới khi có đủ số đo để siết ngưỡng.
        # multi_source_gather CŨNG bị loại, cùng lý do với gather: gate trả
        # True vô điều kiện nên để trong "all" chỉ tạo PASS giả.
        # localize CŨNG bị loại, cùng lý do: gate trả True vô điều kiện nên để trong
        # "all" sẽ chỉ tạo PASS giả mà không đo được gì thật.
        # language ĐÃ QUAY LẠI "all" (final review, 2026-08-18): lý do loại ban
        # đầu ("gate tuyệt đối = PASS/FAIL giả") tự mâu thuẫn với chitchat (cũng
        # tuyệt đối, vẫn nằm trong "all"), và loại nó khỏi job đêm nghĩa là
        # KHÔNG AI gác 4 prompt vừa sửa khỏi hồi quy tiếng Anh — đúng cái mà
        # chính Task 6 viết set này để bắt. An toàn để đưa lại vì eval_language's
        # "en" giờ đòi bằng chứng dương (fix cùng đợt), không còn suy từ thiếu
        # bằng chứng tiếng Việt nữa.
        sets = [s for s in EVAL_FN
                if s not in ("gather", "multi_source_gather", "localize")]
    else:
        sets = [args.set]
    detail, any_fail = {}, False
    for set_name in sets:
        role = ROLE_FOR_SET[set_name]
        model = args.model if args.model is not None else chain_for(role)[0].alias
        # Nhịp suy từ MODEL ĐANG THẬT SỰ CHẠY, không phải từ mắt xích đầu của
        # chuỗi. Bản trước lấy `chain_for(role)[0]` KỂ CẢ khi có `--model X`,
        # nên đo một model ứng viên lại chạy theo trần của một model khác —
        # đúng cách sinh ra một lượt đo hỏng mà không ai nghi ngờ.
        #
        # Công thức nằm ở catalog.nhip_toi_thieu (xét CẢ rpm LẪN tpm) — xem
        # docstring của nó để biết vì sao chỉ xét rpm là sai với Groq.
        try:
            spec = spec_for(model)
        except KeyError:
            # `--model` có thể là tên ứng viên chưa vào catalog (vd
            # "candidate-x" trong test). Không đoán trần của nó; rơi về mắt
            # xích đầu như cũ, và người chạy vẫn đặt `--pace` tay được.
            spec = chain_for(role)[0]
        pace = args.pace if args.pace is not None else nhip_toi_thieu(spec)
        try:
            # Đọc baseline TRƯỚC khi chạy eval thật (tốn call LLM, có pacing suy
            # từ rpm catalog) — baseline thiếu/hỏng thì fail nhanh, không đốt
            # call vô ích. chitchat KHÔNG có baseline (base ở lại None).
            base = None
            bpath = _baseline_for(set_name, args.baseline_model, args.role)
            if bpath is not None:
                with open(bpath, encoding="utf-8") as f:
                    base = json.load(f)
            checkpoint = registry.LOGS_DIR / f"_checkpoint-eval-gate-{set_name}.json"
            try:
                kwargs = {"pace": pace, "checkpoint_path": checkpoint}
                if set_name in role_config.ROLE_SENSITIVE_SETS:
                    kwargs["role"] = args.role
                result = asyncio.run(EVAL_FN[set_name](
                    run_eval._llm(model, role=role), **kwargs))
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
                         # sop_select: hai khoá này KHÔNG có ở danh sách trên
                         # và nhánh không-baseline cũ mới là chỗ ghi chúng —
                         # chuyển set sang nhánh này mà quên là tái lập đúng
                         # lỗi "danh sách khoá viết tay trôi lệch" vừa vá.
                         hijack=result.get("hijack"),
                         depth_acc=result.get("depth_acc"),
                         lat_p50=result.get("lat_p50"),
                         lat_p95=result.get("lat_p95"))
            extra = ("" if result.get("hijack") is None
                     else f" hijack={result['hijack']}"
                          f" depth_acc={result.get('depth_acc')}")
            print(f"[{set_name}] model={model} pace={pace}s "
                  f"{acc_key}={result[acc_key]:.3f} "
                  f"baseline={base[acc_key]:.3f}{extra} "
                  f"→ {'PASS' if ok else 'FAIL'}")
        else:
            # base is None: chitchat (violations), sop_select (acc + hijack),
            # gather (tool_recall + fact_coverage), hoặc multi_source_gather
            # (both_source_coverage + citation_validity) — không set nào có
            # ngưỡng tuyệt đối, xem _gate()
            if set_name == "sop_select":
                entry["acc"] = result.get("acc")
                entry["hijack"] = result.get("hijack")
                # depth_acc KHÔNG vào công thức gate (acc đã đòi cả hai vế
                # đúng) nhưng phải nằm trong entry: nó là thứ duy nhất nói cho
                # người đọc biết một lượt trượt là trượt MIỀN hay trượt ĐỘ SÂU.
                entry["depth_acc"] = result.get("depth_acc")
                entry.update(lat_p50=result.get("lat_p50"),
                             lat_p95=result.get("lat_p95"))
                print(f"[{set_name}] model={model} pace={pace}s "
                      f"acc={result.get('acc')} "
                      f"depth_acc={result.get('depth_acc')} "
                      f"hijack={result.get('hijack')} "
                      f"→ {'PASS' if ok else 'FAIL'}")
            elif set_name == "gather":
                entry["tool_recall"] = result.get("tool_recall")
                entry["fact_coverage"] = result.get("fact_coverage")
                entry["branch"] = result.get("branch")
                entry.update(lat_p50=result.get("lat_p50"),
                             lat_p95=result.get("lat_p95"))
                print(f"[{set_name}] model={model} pace={pace}s "
                      f"tool_recall={result.get('tool_recall')} "
                      f"fact_coverage={result.get('fact_coverage')} "
                      f"→ {'PASS' if ok else 'FAIL'}")
            elif set_name == "multi_source_gather":
                entry.update(
                    both_source_coverage=result.get("both_source_coverage"),
                    citation_validity=result.get("citation_validity"),
                    fabricated_number=result.get("fabricated_number"),
                    lat_p50=result.get("lat_p50"),
                    lat_p95=result.get("lat_p95"))
                print(f"[{set_name}] model={model} pace={pace}s "
                      f"both_source_coverage="
                      f"{result.get('both_source_coverage'):.3f} "
                      f"citation_validity={result.get('citation_validity'):.3f} "
                      f"fabricated_number={result.get('fabricated_number')} "
                      f"→ {'PASS' if ok else 'FAIL'}")
            elif set_name == "language":
                # Nhánh này thiếu từ khi "language" ra đời (Task 6) — chưa lộ
                # ra vì set này chưa từng chạy dưới nhánh base=None của report
                # (không có test standalone `--set language`, và bị loại khỏi
                # "all"). Đưa lại vào "all" (fix cùng đợt) chạy thẳng vào
                # nhánh else phía dưới vốn viết CỨNG cho chitchat
                # (`result["violations"]`) → KeyError vì kết quả language
                # không có khoá đó. Thêm nhánh riêng, cùng khuôn sop_select/
                # gather/multi_source_gather ở trên.
                entry["acc"] = result.get("acc")
                entry.update(lat_p50=result.get("lat_p50"),
                             lat_p95=result.get("lat_p95"))
                print(f"[{set_name}] model={model} pace={pace}s "
                      f"acc={result.get('acc')} → {'PASS' if ok else 'FAIL'}")
            elif set_name == "memory":
                entry.update(false_injection=result.get("false_injection"),
                             leaked_doc_code=result.get("leaked_doc_code"),
                             truncated_answer=result.get("truncated_answer"),
                             recall=result.get("recall"),
                             lat_p50=result.get("lat_p50"),
                             lat_p95=result.get("lat_p95"))
                print(f"[{set_name}] model={model} pace={pace}s "
                      f"false_injection={result.get('false_injection')} "
                      f"leaked_doc_code={result.get('leaked_doc_code')} "
                      f"truncated_answer={result.get('truncated_answer')} "
                      f"recall={result.get('recall')} → {'PASS' if ok else 'FAIL'}")
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
                            "multi_source_gather", "sop_select", "gather"],
                   default="both")
    p.add_argument("--pace", type=float, default=None,
                   help="giây/call (mặc định auto: (60/rpm)*1.2 suy từ catalog)")
    p.add_argument("--role", default="admin",
                   choices=sorted(roles.load_profile()),
                   help="vai để dựng prompt (chỉ có tác dụng với "
                        "intent/sop_select/planner)")
    # Model của BỘ BASELINE, KHÔNG phải model đang đo. Hai thứ đó tách rời:
    # `--model` chọn ứng viên để đo, cờ này chọn cái chuẩn để so.
    #
    # Vì sao cần cờ: `run_eval --save-baseline` đặt tên file theo model ĐÃ ĐO
    # (`baseline-{model}-{set}[-{role}].json`), còn cổng đọc theo neo cố định.
    # Với vai admin hai bên trùng nhau vì 6 file hiện có đều mang neo. Nhưng
    # baseline của một vai MỚI được đo hôm nay sẽ mang tên model hôm nay, và
    # không có cờ này thì cổng không bao giờ tìm thấy nó — một đường chấm cổng
    # hỏng câm. Không đổi tên file thành neo được: nội dung baseline KHÔNG ghi
    # model bên trong, nên tên file là nơi DUY NHẤT mang provenance.
    p.add_argument("--baseline-model", default=BASELINE_MODEL,
                   help=f"model của BỘ BASELINE để so (mặc định "
                        f"{BASELINE_MODEL!r}); khác với --model là model đang đo")


register(Job("eval-gate", run,
             "M3 gate: intent+confirm vs baseline + chitchat anti-hallucination "
             "(mặc định đo config sống)",
             schedulable=True, add_args=add_args))
