"""Bảng model — nguồn sự thật duy nhất cho tầng LLM (spec SP-1 §2).

Mọi con số hạn mức ở đây phải khớp docs/provider-quotas.md. Sửa một nơi thì
sửa cả hai; test contract (Task 11) đối chiếu model_id với /models thật.

KHÔNG có khoá API nào trong file này.
"""
from dataclasses import dataclass
from contextvars import ContextVar


@dataclass(frozen=True)
class ModelSpec:
    alias: str
    provider: str            # google | groq | openrouter
    model_id: str            # ID gốc phía provider
    upstream: str            # MIỀN LỖI THẬT — xem CHÚ THÍCH OPENROUTER bên dưới
    quota_scope: str         # "model" (Google, Groq) | "account" (OpenRouter)
    rpm: int | None
    tpm: int | None          # None = không có trần token công bố
    rpd: int | None
    token_multiplier: float  # hiệu chỉnh ước lượng token theo provider
    max_output_tokens: int | None
    timeout_s: int
    supports_tools: bool
    emits_thought_tags: bool  # họ Gemma nhả <thought> vào content


# Ngưỡng cho bất biến #3. Chọn theo số đo: một lượt synthesis có RAG tốn ~3–4K
# token input, và 12K là mức của llama-3.3-70b — mắt xích Groq duy nhất gánh
# nổi vai nặng. gpt-oss-* ở 8K bị loại khỏi vai nặng đúng bởi ngưỡng này.
HEAVY_TPM_FLOOR = 12_000

ROLES = frozenset({"router", "chitchat", "evaluator", "planner",
                   "read", "fusion", "synthesis"})
HEAVY_ROLES = frozenset({"read", "fusion", "synthesis"})
TOOL_ROLES = frozenset({"read", "planner", "fusion", "synthesis"})

# ─── CHÚ THÍCH OPENROUTER (quyết định 2026-07-28, KHÔNG lật lại) ─────────────
# google/gemma-4-31b-it:free CỐ Ý không có mặt trong catalog. Đo được: nó trả
# 429 kèm provider_name "Google AI Studio" — OpenRouter proxy ngược về chính
# Google, dùng chung hồ hạn mức. Xếp nó sau Gemini trong một chuỗi fallback là
# tự lừa mình. Chỉ model OpenRouter có upstream THẬT SỰ khác mới được vào:
# ling-3.0-flash → Novita, nemotron-3-super → Nvidia (cả hai đã xác nhận
# tool-call bình thường).
# ────────────────────────────────────────────────────────────────────────────

CATALOG: dict[str, ModelSpec] = {
    # ─── Google AI Studio ───────────────────────────────────────────────────
    "gemini-3.5-flash-lite": ModelSpec(
        alias="gemini-3.5-flash-lite", provider="google",
        model_id="gemini-3.5-flash-lite", upstream="google",
        quota_scope="model", rpm=15, tpm=250_000, rpd=500,
        token_multiplier=1.0, max_output_tokens=8192, timeout_s=60,
        supports_tools=True, emits_thought_tags=False),
    "gemini-3.1-flash-lite": ModelSpec(
        alias="gemini-3.1-flash-lite", provider="google",
        model_id="gemini-3.1-flash-lite", upstream="google",
        quota_scope="model", rpm=15, tpm=250_000, rpd=500,
        token_multiplier=1.0, max_output_tokens=8192, timeout_s=60,
        supports_tools=True, emits_thought_tags=False),
    # Gemma: RPD khổng lồ (14.4K) nhưng TPM thấp (16K) và KHÔNG tắt được
    # thinking (reasoning_effort → 400 "Thinking budget is not supported").
    # 26b và 31b có HAI ví hạn mức riêng biệt — vai router và chitchat cố ý
    # tách ra hai model để tiêu hai ví thay vì một.
    "gemma-4-26b": ModelSpec(
        alias="gemma-4-26b", provider="google",
        model_id="gemma-4-26b-a4b-it", upstream="google",
        quota_scope="model", rpm=30, tpm=16_000, rpd=14_400,
        token_multiplier=1.0, max_output_tokens=2048, timeout_s=60,
        supports_tools=True, emits_thought_tags=True),

    # Hai model chủ dự án cấp 2026-08-13. SỐ LIỆU DƯỚI ĐÂY LÀ ĐO THẬT, không
    # phỏng đoán: probe xác nhận model_id gọi được, supports_tools=True (gọi
    # thật get_stock, trả 1 tool_call), và text KHÔNG chứa thẻ <thought> inline
    # nên emits_thought_tags=False (khác gemma — client native tách reasoning ra
    # usage_metadata thay vì nối vào content).
    #
    # Chúng VẪN đốt token suy luận (đo: 183 và 152 token cho một việc phân loại
    # một từ) — ít hơn gemma (300-2045) rất nhiều nhưng KHÔNG bằng không như
    # flash-lite. Bề mặt lỗi "cạn ngân sách suy luận" vẫn tồn tại, chỉ là biên
    # rộng hơn; max_output_tokens=8192 để biên đó thật sự rộng.
    #
    # rpd=20 LÀ RÀNG BUỘC CHÍNH: nhỏ hơn n=24 của bộ eval `confirm`, nên KHÔNG
    # đo trọn được bộ đó trong một ngày ⇒ không đủ điều kiện gate ADR-009 M3 cho
    # vai `evaluator`. Bộ `chitchat` (n=16) thì vừa. Đây là lý do chúng chỉ được
    # cân nhắc cho `chitchat`, không cho cổng xác nhận ghi.
    #
    # Hai model KHÁC chủ dự án nêu KHÔNG tồn tại, đã probe: "gemini-3-flash" trả
    # 404 NOT_FOUND, "gemini-2.5-flash" trả 404 "no longer available to new
    # users". Ghi lại để đời sau không thử lại.
    #
    # "gemini-3.6-flash" CÓ thật và đã được đo (bộ chitchat: violations=0, p50
    # 5048ms nhưng một lượt 43.9s) — THUA gemini-3.5-flash nên không giữ entry.
    # Số đo ở bảng trong chú thích chuỗi `chitchat` bên dưới. Muốn dùng lại thì
    # thêm entry mới và đo lại với n lớn hơn 16 trước, vì p95 ở cỡ mẫu đó chỉ
    # là ~1 mẫu.
    "gemini-3.5-flash": ModelSpec(
        alias="gemini-3.5-flash", provider="google",
        model_id="gemini-3.5-flash", upstream="google",
        quota_scope="model", rpm=5, tpm=250_000, rpd=20,
        token_multiplier=1.0, max_output_tokens=8192, timeout_s=60,
        supports_tools=True, emits_thought_tags=False),

    # ─── Groq ───────────────────────────────────────────────────────────────
    # token_multiplier=2.3: đo được Groq tính 133 prompt_tokens cho payload mà
    # Google tính 57. Với trần 8K TPM, ước lượng lệch 2.3× là gọi thẳng vào 429.
    "groq-gpt-oss-20b": ModelSpec(
        alias="groq-gpt-oss-20b", provider="groq",
        model_id="openai/gpt-oss-20b", upstream="groq",
        quota_scope="model", rpm=30, tpm=8_000, rpd=1_000,
        token_multiplier=2.3, max_output_tokens=2048, timeout_s=30,
        supports_tools=True, emits_thought_tags=False),
    "groq-gpt-oss-120b": ModelSpec(
        alias="groq-gpt-oss-120b", provider="groq",
        model_id="openai/gpt-oss-120b", upstream="groq",
        quota_scope="model", rpm=30, tpm=8_000, rpd=1_000,
        token_multiplier=2.3, max_output_tokens=4096, timeout_s=30,
        supports_tools=True, emits_thought_tags=False),
    "groq-llama-3.3-70b": ModelSpec(
        alias="groq-llama-3.3-70b", provider="groq",
        model_id="llama-3.3-70b-versatile", upstream="groq",
        quota_scope="model", rpm=30, tpm=12_000, rpd=1_000,
        token_multiplier=2.3, max_output_tokens=4096, timeout_s=30,
        supports_tools=True, emits_thought_tags=False),

    # ─── OpenRouter (khan hiếm — ~50 lượt/ngày CHUNG cho mọi model free) ────
    "or-ling": ModelSpec(
        alias="or-ling", provider="openrouter",
        model_id="inclusionai/ling-3.0-flash:free", upstream="novita",
        quota_scope="account", rpm=None, tpm=None, rpd=50,
        token_multiplier=1.5, max_output_tokens=2048, timeout_s=60,
        supports_tools=True, emits_thought_tags=False),
    "or-nemotron": ModelSpec(
        alias="or-nemotron", provider="openrouter",
        model_id="nvidia/nemotron-3-super-120b-a12b:free", upstream="nvidia",
        quota_scope="account", rpm=None, tpm=None, rpd=50,
        token_multiplier=1.5, max_output_tokens=4096, timeout_s=60,
        supports_tools=True, emits_thought_tags=False),
}

# Gán provider theo TRỌNG LƯỢNG TOKEN của vai, không theo chuỗi "primary →
# fallback" chung chung. Ràng buộc thật của Groq là TPM chứ không phải RPM:
# ở 8K TPM chỉ chạy được ~2 request/phút với ngữ cảnh RAG, trong khi RPM 30
# còn chưa dùng tới 1/15. Ai thiết kế theo RPM sẽ bị TPM đánh úp.
CHAINS: dict[str, tuple[str, ...]] = {
    # router: gemini-3.1-flash-lite THAY gemma-4-26b ở mắt xích 1 (2026-08-13).
    # Đo thật, n=54 bộ `intent` và n=17 bộ `sop_select`, mỗi model ghim một lượt:
    #
    #   model                   intent acc   intent p50   sop acc   hijack   sop p95
    #   gemma-4-26b               0.9444       6103ms     0.9412      0      21031ms
    #   gemini-3.1-flash-lite     0.9630       1008ms     0.9412      0       2861ms
    #
    # Chất lượng: 2 ca sai của gemini là TẬP CON THẬT SỰ của 3 ca sai gemma;
    # cả hai sai đúng một ca giống nhau ở sop_select (ca "quy trình nhập kho cho
    # đơn mua P00021" — chính ca mà lớp phủ quyết tất định tồn tại để bắt, xem
    # agents/routing.py). hijack = 0 ở CẢ HAI: cổng an toàn không thụt.
    #
    # Vì sao đáng đổi: router chạy trên MỌI tin nhắn trước khi bất cứ việc gì
    # khác bắt đầu, và gemma trả "thuế suy luận" 300-2045 token cho một việc
    # phân loại ra đúng MỘT TỪ. gemini-*-flash-lite có emits_thought_tags=False
    # và max_output_tokens=8192 nên không trả thuế đó.
    #
    # gemma-4-26b RỜI HẲN chuỗi này, KHÔNG xuống làm mắt xích 2. Bản nháp đầu
    # định giữ nó ở vị trí 2 (ví rpd=14_400 làm lưới đỡ khi flash-lite cạn
    # rpd=500) — SAI, và test_khong_hai_mat_xich_nao_trong_mot_chuoi_chung_upstream
    # bắt được: cả hai đều upstream="google", nên rơi từ cái này xuống cái kia
    # là rơi vào lại chính miền lỗi vừa ngã. Bất biến #1 thắng lý lẽ hạn mức.
    # gemma-4-26b vẫn phục vụ vai `evaluator` (mắt xích 2).
    #
    # Chọn 3.1-flash-lite chứ không phải 3.5: 3.5 ĐÃ gánh planner+read, còn 3.1
    # chỉ gánh fusion+synthesis (hai vai chỉ chạy ở nhánh mixed, thưa hơn) —
    # chia tải qua hai ví thay vì chất đống lên một.
    "router":    ("gemini-3.1-flash-lite", "groq-gpt-oss-20b", "or-ling"),
    # chitchat: gemini-3.5-flash THAY gemma-4-31b ở mắt xích 1 (2026-08-13).
    # Đo bộ `chitchat` (n=16), mỗi model ghim một lượt:
    #
    #   model               violations   p50        p95
    #   gemma-4-31b              0     13103ms    21090ms
    #   gemini-3.5-flash         0      3271ms     3940ms
    #   gemini-3.6-flash         0      5048ms    43891ms
    #
    # Gate của bộ này là `violations` (tuyệt đối, không so baseline) — CẢ BA
    # đều 0, tức chất lượng hoà. Khác biệt duy nhất là độ trễ, và 3.5-flash
    # thắng cả về p50 lẫn độ ỔN ĐỊNH (p95 gần p50). Không chọn 3.6-flash vì
    # một lượt 43.9s; ở n=16 thì p95 chỉ ~1 mẫu nên không đọc quá nặng, nhưng
    # lượt đó có thật.
    #
    # rpd=20 chấp nhận được ở ĐÂY (khác router): chitchat chỉ chạy khi intent =
    # `unknown` — chào hỏi, tán gẫu, rất thưa. Cạn hạn mức thì tụt xuống
    # groq-gpt-oss-20b, suy giảm chấp nhận được.
    #
    # gemma-4-31b RỜI chuỗi, không xuống mắt xích 3: nó cùng upstream="google"
    # với 3.5-flash nên bất biến #1 cấm (xem chuỗi `router` phía trên, cùng lý
    # do). Entry của nó ĐÃ XOÁ khỏi CATALOG luôn — không chuỗi nào dùng nữa, và
    # một entry chết là cấu hình chờ trôi lệch. Số đo của nó ở lại ngay bảng
    # trên, đó mới là chỗ nó có ích.
    "chitchat":  ("gemini-3.5-flash", "groq-gpt-oss-20b"),
    # evaluator: ĐẢO thứ tự 2026-08-13. Trước: groq-gpt-oss-20b → gemma-4-26b.
    # Đo bộ `confirm` (n=24) trên CẢ HAI mắt xích, mỗi model ghim một lượt:
    #
    #   model               acc      false_confirm   p50
    #   groq-gpt-oss-20b    0.6250        0          577ms
    #   gemma-4-26b         0.7917        0         6075ms
    #   (baseline qwen3-8b  0.6250        0         4048ms)
    #
    # Mắt xích 2 TỐT HƠN mắt xích 1 rõ rệt (19/24 so với 15/24), và 5 ca sai của
    # gemma là TẬP CON THẬT SỰ của 9 ca sai groq. Cụ thể groq không hiểu "chốt
    # đơn giùm mình" / "lên đơn đi bạn" là đồng ý; gemma hiểu.
    #
    # false_confirm = 0 ở CẢ HAI — mọi ca sai đều theo hướng AN TOÀN (đáng lẽ
    # confirm/cancel thì trả unclear, tức HỎI LẠI chứ không thực thi). Đây là
    # điều kiện gate tuyệt đối của bộ confirm, và đảo thứ tự không đụng tới nó.
    #
    # Giá phải trả: p50 577ms → 6075ms. Chấp nhận được vì đường LLM của cổng này
    # HIẾM khi chạy — classify_keyword đã nuốt hết "có"/"không"/"ok"/"huỷ", LLM
    # chỉ vào cuộc với câu mơ hồ kiểu "chắc để lúc khác đi".
    #
    # gemma-4-26b có bề mặt "cạn ngân sách token suy luận" (xem chú thích khối
    # Gemma bên trên). Nếu nó trả rỗng, Router nay TỤT xuống groq-gpt-oss-20b —
    # đúng lưới đỡ dựng ở đợt router-empty-response (2026-08-13).
    "evaluator": ("gemma-4-26b", "groq-gpt-oss-20b"),
    "planner":   ("gemini-3.5-flash-lite", "groq-gpt-oss-120b", "or-nemotron"),
    "read":      ("gemini-3.5-flash-lite", "groq-llama-3.3-70b", "or-nemotron"),
    # SP-2b (2026-08-01): node `fusion` trong graph đã bị XOÁ (thay bằng fan-out
    # mixed → gather_docs ‖ gather_erp → fuse_answer, xem agents/fanout.py).
    # VAI model tên "fusion" thì SỐNG NGUYÊN: gather_erp và fuse_answer đều dùng
    # nó. Đổi tên vai sẽ lan sang models.py, router.py, main.py và
    # eval_gate.py:ROLE_FOR_SET — và QĐ M3 (ADR-009) cấm đổi model/prompt khi
    # chưa qua eval gate. Tên set đo đã là "multi_source" (trung tính) chính vì
    # lường trước việc này.
    "fusion":    ("gemini-3.1-flash-lite", "groq-llama-3.3-70b"),
    "synthesis": ("gemini-3.1-flash-lite", "groq-llama-3.3-70b", "or-nemotron"),
}


def spec_for(alias: str) -> ModelSpec:
    """Ném KeyError nếu alias lạ — cấu hình sai phải chết sớm, không đoán."""
    return CATALOG[alias]


# Model người dùng chọn ở dropdown Open WebUI, đặt tại ranh giới HTTP mỗi lượt.
# ContextVar chứ không phải tham số xuyên tầng: lựa chọn phải tới được resolve()
# của Router, mà giữa hai chỗ đó là erp_agent + LangGraph + RoutedChatModel —
# luồn thêm một tham số qua cả bốn tầng là bốn chỗ có thể quên. Cùng cơ chế mà
# router đã dùng cho `_QUYET_DINH`.
MODEL_NGUOI_DUNG_CHON: ContextVar[str | None] = ContextVar(
    "MODEL_NGUOI_DUNG_CHON", default=None)

# Model cho người dùng chọn. CHỈ những model đủ hạn mức gánh cả ngày:
#   gemini-3.5-flash-lite  rpd 500
#   gemini-3.1-flash-lite  rpd 500
# CỐ Ý KHÔNG có `gemini-3.5-flash` (rpd=20 — chết sau ~20 tin nhắn/ngày, mời
# người dùng chọn một thứ hỏng sau hai chục lượt là mời họ thất vọng) và
# `gemma-4-26b` (rpd 14400, dư sức gánh cả hệ, nhưng CHƯA ĐO trên các vai này —
# xem docs/trang-thai-chung.md).
MODEL_CHON_DUOC: tuple[str, ...] = ("gemini-3.5-flash-lite",
                                    "gemini-3.1-flash-lite")

# Mặc định. Đo 2026-08-21 trên `read`/`planner`/`intent`, mỗi bộ 2 lượt:
#
#                        intent acc        intent p95
#   3.1-flash-lite    0,9444 · 0,9444   11 220 · 7 900ms
#   3.5-flash-lite    0,9074 · 0,8889    1 058 · 1 073ms
#   (read/planner: CẢ HAI đạt 1,0 — hai bộ đó bão hoà, không phân biệt được)
#
# Chọn 3.1 dù nó CHẬM HƠN 7-10 lần ở đuôi, vì hai kiểu hỏng không cùng hạng:
#   - chậm là hỏng LỚN TIẾNG — người dùng thấy, tự biết chờ, không nhận thông
#     tin sai;
#   - định tuyến nhầm là hỏng IM LẶNG — câu `mixed` bị phân thành nguồn đơn nên
#     câu trả lời thiếu hẳn nửa tài liệu, mà người dùng KHÔNG BIẾT là thiếu.
# Mặc định phục vụ người không bao giờ đổi lựa chọn; với họ, thiếu âm thầm tệ
# hơn chậm.
#
# Ai ưu tiên tốc độ thì đổi sang 3.5-flash-lite ngay ở dropdown — đó chính là
# lý do tính năng này tồn tại.
MODEL_MAC_DINH = "gemini-3.1-flash-lite"


def chain_for(role: str, prefer: str | None = None) -> tuple[ModelSpec, ...]:
    """Chuỗi mắt xích cho một vai, model `prefer` được đưa lên ĐẦU.

    `prefer` KHÁC `pin` của Router: pin bỏ qua toàn bộ chuỗi và chỉ thử một lần
    (eval dùng để quy kết quả cho đúng model). `prefer` chỉ ĐỔI THỨ TỰ — mọi
    mắt xích dự phòng của vai vẫn nằm phía sau. Nhầm hai thứ này là mất fallback
    mà không có gì báo.

    Model đã có sẵn trong chuỗi thì được NHẤC LÊN chứ không nhân đôi: thử cùng
    một model hai lần trong một lượt là đốt hạn mức cho một kết quả đã biết.
    """
    aliases = list(CHAINS[role])
    if prefer and prefer in CATALOG:
        aliases = [prefer] + [a for a in aliases if a != prefer]
    return tuple(CATALOG[a] for a in aliases)
