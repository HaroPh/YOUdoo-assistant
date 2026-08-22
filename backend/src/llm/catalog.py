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
# Ngưỡng cho bất biến #3 — HẠ 12 000 → 8 000 ngày 2026-08-21.
#
# Con số 12 000 KHÔNG đến từ nhu cầu, nó đến từ nguồn cung: chú thích gốc ghi
# "một lượt synthesis có RAG tốn ~3–4K token input, và 12K là mức của
# llama-3.3-70b — mắt xích Groq duy nhất gánh nổi vai nặng". Ngày 2026-08-21
# Groq KHAI TỬ llama-3.3-70b ("model does not exist"), và cả ba model chat còn
# lại của họ đều tpm 8 000. Giữ 12 000 nghĩa là ngưỡng không còn bảo vệ gì, chỉ
# còn CẤM mọi ứng viên tồn tại.
#
# Ngưỡng này bảo vệ THÔNG LƯỢNG, không bảo vệ TÍNH ĐÚNG: ở 8 000 tpm một lượt
# nặng ~3–4K vẫn chạy lọt, chỉ còn ~2 lượt/phút thay vì ~3. Và mắt xích Groq
# nay là mắt xích CUỐI, chỉ chạy khi CẢ HAI model Gemini đã ngã.
HEAVY_TPM_FLOOR = 8_000

# Ngưỡng cho bất biến #5: HAI mắt xích đầu của mọi chuỗi phải đủ hạn mức phục
# vụ TRỌN một ngày. 500 = rpd của flash-lite, mức thấp nhất đã dùng thật cho
# một mắt xích phục vụ.
#
# Vì sao chỉ hai mắt xích đầu, không phải cả chuỗi: `or-ling`/`or-nemotron`
# (rpd=50, ví CHUNG cả tài khoản OpenRouter) là lưới đỡ khẩn cấp ở đuôi, cố ý
# mỏng. Hai vị trí đầu thì khác — `chain_for(prefer=…)` đẩy mắt xích 1 cũ xuống
# vị trí 2, nên vị trí 2 là chỗ MỌI cú tụt đều đi qua.
#
# Bất biến này sinh ra từ một lỗi thật (2026-08-21): `gemini-3.5-flash` rpd=20
# nằm ở mắt xích 1 của `chitchat` với lý lẽ "vai này thưa nên chấp nhận được".
# Lý lẽ đó chết lúc `prefer` ra đời mà không ai sửa lại, và không luật nào bắt
# được. Nay có.
RPD_SAN_PHUC_VU = 500

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
    # HỌ GEMINI-3.x KHÔNG DÙNG THINKING trên tải của hệ này — đo 2026-08-21
    # bằng API trần, cả câu ngắn lẫn prompt router thật (2855 ký tự):
    # `thoughtsTokenCount` = 0 ở MỌI cấu hình, kể cả mặc định.
    #
    # `thinkingConfig.thinkingBudget` CÓ được free tier chấp nhận cho
    # gemini-3.1-flash-lite (cả 0 lẫn 512); gemini-3.5-flash-lite TỪ CHỐI
    # budget=0 (HTTP 400) nhưng nhận 512. Nhưng vặn nút đó KHÔNG đổi gì, vì
    # không có thinking nào đang chạy để tắt. Đừng mất công tối ưu ở đây.
    #
    # Độ trễ: 3.1-flash-lite chậm hơn 3.5-flash-lite khoảng 2 LẦN ở trung vị
    # (2000ms vs 951ms, prompt router thật, 4 lượt mỗi model). Con số p95
    # 11 220ms từng đo được trong bộ eval là do VÀI LƯỢT NGOẠI LAI trong 54
    # lượt, không phải đặc tính thường trực — đừng trích nó như chênh lệch
    # điển hình.

    # ─── gemma-4-26b ĐÃ XOÁ 2026-08-21 ──────────────────────────────────────
    # Nó từng là mắt xích 1 của `evaluator` nhờ MỘT phép đo 2026-08-13 trên bộ
    # `confirm` (0,7917 so với 0,6250 của groq-gpt-oss-20b). Phép đo đó chỉ đặt
    # nó cạnh Groq, CHƯA BAO GIỜ đặt cạnh Gemini. Đo lại đối đầu 2026-08-21,
    # cùng phiên cùng prompt, bộ `confirm` n=24 (false_confirm = 0 ở CẢ NĂM):
    #
    #   gemini-3.5-flash-lite   0,9583   699ms
    #   gemini-3.1-flash-lite   0,9167   719ms
    #   groq-gpt-oss-120b       0,8333   611ms
    #   gemma-4-26b             0,7917  6062ms   ← đang giữ chỗ
    #   groq-gpt-oss-20b        0,6250   577ms
    #
    # Gemma thua mọi ứng viên và CHẬM GẤP 8. Lý lẽ "ví lớn" (rpd 14 400) không
    # cứu được: đường LLM của cổng này HIẾM khi chạy (bộ lọc từ khoá nuốt hết
    # "có"/"không"/"ok"/"huỷ"), tức ví lớn đặt đúng chỗ ít dùng nhất. Kèm hai
    # dằm vận hành riêng: nhả thẻ <thought> vào content, và có bề mặt "cạn
    # ngân sách token suy luận" — chính cái từng khiến nó TRẢ RỖNG thật và buộc
    # đợt router-empty-response dựng cả một lưới đỡ.

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
    # groq-gpt-oss-20b XOÁ 2026-08-21: kém nhất trong năm model đo trên bộ
    # `confirm` (0,6250) và max_output_tokens chỉ 2048. Cùng ví hạn mức hạng
    # với 120b (tpm 8 000, rpd 1 000) nên giữ nó không mua thêm dung lượng gì.
    "groq-gpt-oss-120b": ModelSpec(
        alias="groq-gpt-oss-120b", provider="groq",
        model_id="openai/gpt-oss-120b", upstream="groq",
        quota_scope="model", rpm=30, tpm=8_000, rpd=1_000,
        token_multiplier=2.3, max_output_tokens=4096, timeout_s=30,
        supports_tools=True, emits_thought_tags=False),
    # groq-llama-3.3-70b CHẾT 2026-08-21: Groq trả "The model
    # `llama-3.3-70b-versatile` does not exist or you do not have access to
    # it." Nó là mắt xích 2 của read/fusion/synthesis, nên `fusion` khi đó thực
    # tế CHỈ CÒN MỘT mắt xích sống. Nó cũng là model Groq duy nhất từng đạt
    # HEAVY_TPM_FLOOR cũ (12 000) — mất nó là lý do ngưỡng đó phải hạ.

    # ─── OpenRouter XOÁ HẲN 2026-08-21 ──────────────────────────────────────
    # `or-ling` CHẾT: OpenRouter gỡ slug `:free` ("This model is unavailable for
    # free. The paid version is available now"). `or-nemotron` vẫn SỐNG, nhưng
    # bị bỏ cùng cả tầng vì lý do cấu trúc: free tier của OpenRouter là ~50
    # lượt/ngày DÙNG CHUNG cho mọi model (quota_scope="account"), tức nó chưa
    # bao giờ là dung lượng thật — chỉ là một mắt xích trông cho yên tâm.
    #
    # Ghi rõ để đời sau không "khôi phục" nhầm: hai model google/gemma-*:free
    # trên OpenRouter BỊ CẤM quay lại (chú thích OPENROUTER phía trên) vì chúng
    # proxy ngược về Google.
}

# MỘT hình dạng chuỗi cho MỌI vai (gom 2026-08-21, spec catalog-consolidation):
#
#     [model người dùng chọn] → [Gemini còn lại] → groq-gpt-oss-120b
#
# Bảng dưới chỉ ghi hình dạng TĨNH; mắt xích "Gemini còn lại" do
# `chain_for(prefer=…)` chèn vào — xem docstring của nó.
#
# VÌ SAO ĐỒNG BỘ. Trước đợt này mỗi vai một chuỗi riêng, tổng cộng 9 model. Hệ
# quả đo được ngày 2026-08-21: HAI model đã chết mà không ai biết
# (groq-llama-3.3-70b, or-ling), `fusion` thực tế chỉ còn MỘT mắt xích, và vai
# `evaluator` chạy suốt từ 2026-08-13 bằng model KÉM NHẤT trong nhóm — vì phép
# so sánh hồi đó chỉ đặt gemma cạnh Groq, chưa bao giờ đặt cạnh Gemini. Ít model
# hơn = ít thứ phải đo, và ít thứ trôi lệch âm thầm.
#
# VÌ SAO GIỮ MỘT MẮT XÍCH GROQ. Ba khoá API (xem spec api-key-rotation) chữa
# HẠN MỨC, không chữa SỰ CỐ NHÀ CUNG CẤP — chúng là ba ví trên cùng một hệ
# thống Google. `groq-gpt-oss-120b` là đường duy nhất ra khỏi Google, và bất
# biến #1 tồn tại đúng cho kiểu hỏng đó.
#
# SỐ ĐO CÒN GIÁ TRỊ TỪ CÁC ĐỢT TRƯỚC (model đã xoá vẫn ghi để không ai đo lại):
#
#   bộ `confirm` n=24, false_confirm = 0 ở CẢ NĂM (2026-08-21, cùng phiên):
#     gemini-3.5-flash-lite 0,9583 | gemini-3.1-flash-lite 0,9167
#     groq-gpt-oss-120b     0,8333 | gemma-4-26b           0,7917 (6062ms)
#     groq-gpt-oss-20b      0,6250
#
#   bộ `intent` n=54 + `sop_select` n=17, hijack = 0 ở cả hai (2026-08-13):
#     gemini-3.1-flash-lite  acc 0,9630  p50 1008ms
#     gemma-4-26b            acc 0,9444  p50 6103ms  (trả 300-2045 token suy
#       luận cho một việc phân loại ra ĐÚNG MỘT TỪ — lý do nó rời chuỗi router)
#
#   bộ `chitchat` n=16, violations = 0 ở cả ba (2026-08-13):
#     gemini-3.5-flash 3271ms | gemini-3.6-flash 5048ms | gemma-4-31b 13103ms
#
# `gemini-3.5-flash` (rpd=20) CỐ Ý không có mặt: nó chết sau ~20 tin nhắn/ngày.
# Entry của nó ở lại CATALOG chỉ để `--model gemini-3.5-flash` ghim đo được, và
# bất biến #5 chặn nó quay lại chuỗi.
CHAINS: dict[str, tuple[str, ...]] = {
    role: ("gemini-3.1-flash-lite", "groq-gpt-oss-120b")
    for role in ("router", "chitchat", "evaluator", "planner",
                 "read", "fusion", "synthesis")
}


# Ước lượng token MỖI LƯỢT GỌI của một ca eval, dùng để suy nhịp từ TPM.
# Đo 2026-08-22 trên groq-gpt-oss-120b: bộ `intent` 857 token/lượt, bộ `confirm`
# 283–539. Lấy 1000 làm mức trần thận trọng — nhịp sai theo hướng CHẬM chỉ tốn
# thời gian, còn sai theo hướng NHANH thì hỏng cả lượt đo.
TOKEN_MOI_LUOT_UOC = 1_000


def nhip_toi_thieu(spec: ModelSpec) -> float:
    """Giây giãn cách tối thiểu giữa hai lượt gọi eval cho `spec`.

    Xét CẢ HAI trần, không chỉ RPM. Trước 2026-08-22 công thức là
    `(60/rpm)*1.2` — đúng với Gemini (rpm 15, tpm 250 000: rpm là ràng buộc
    thật) nhưng SAI HẲN với Groq (rpm 30, tpm 8 000: tpm mới là ràng buộc).
    Hệ quả đo được: bộ `intent` trên groq-gpt-oss-120b chạy ở nhịp suy từ rpm
    = 25 lượt/phút trong khi trần cho phép ~9 ⇒ **23/54 ca lỗi**, và con số
    acc thu được (0,5556) hoàn toàn vô nghĩa. Chạy lại đúng nhịp: 0,9630, 0 lỗi.

    Biên 20%: trần là trần cứng, chạm sát nó là đứng ngay mép vực.
    """
    nhip_rpm = (60.0 / spec.rpm) if spec.rpm else 0.0
    nhip_tpm = (60.0 / (spec.tpm / TOKEN_MOI_LUOT_UOC)) if spec.tpm else 0.0
    return max(nhip_rpm, nhip_tpm) * 1.2


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


# Thứ tự vai SINH RA câu trả lời người dùng đọc, ưu tiên giảm dần. Một lượt đi
# qua nhiều vai (router phân loại, planner lập kế, read gọi tool…) nhưng chỉ
# MỘT vai viết ra văn bản cuối:
#
#   fusion    — nhánh `mixed`, node fuse_answer là chỗ hợp nhất cuối cùng
#   synthesis — nhánh `rag`
#   read      — nhánh `erp_read`
#   chitchat  — nhánh `unknown`
#
# `evaluator` KHÔNG có trong danh sách dù nó chạy SAU CÙNG (localize): nó dịch
# lại văn bản đã có chứ không sinh nội dung. `router`/`planner` cũng vậy.
# Nói cách khác thứ tự này là thứ tự ƯU TIÊN theo vai trò, không phải thứ tự
# thời gian — lấy "lời gọi LLM cuối cùng" sẽ trả về evaluator, tức sai.
VAI_TRA_LOI: tuple[str, ...] = ("fusion", "synthesis", "read", "chitchat")


def model_tra_loi(da_dung: dict[str, str] | None, mac_dinh: str) -> str:
    """Model đã sinh ra câu trả lời người dùng đọc.

    Trả `mac_dinh` khi không xác định được — lượt hỏng trước khi tới vai sinh
    câu trả lời (trả ERROR_MSG), hoặc thùng chưa được cha đặt. Trường `model`
    của phản hồi là dữ liệu hiển thị, không phải cổng an toàn: đoán sai một
    nhãn thì tệ hơn nhiều nếu vì thế mà cả lượt chat nổ.
    """
    for vai in VAI_TRA_LOI:
        if da_dung and vai in da_dung:
            return da_dung[vai]
    return mac_dinh


def chain_for(role: str, prefer: str | None = None) -> tuple[ModelSpec, ...]:
    """Chuỗi mắt xích cho một vai, model `prefer` được đưa lên ĐẦU.

    `prefer` KHÁC `pin` của Router: pin bỏ qua toàn bộ chuỗi và chỉ thử một lần
    (eval dùng để quy kết quả cho đúng model). `prefer` chỉ ĐỔI THỨ TỰ — mọi
    mắt xích dự phòng của vai vẫn nằm phía sau. Nhầm hai thứ này là mất fallback
    mà không có gì báo.

    Model đã có sẵn trong chuỗi thì được NHẤC LÊN chứ không nhân đôi: thử cùng
    một model hai lần trong một lượt là đốt hạn mức cho một kết quả đã biết.

    MỌI MODEL TRONG `MODEL_CHON_DUOC` ĐỀU CÓ MẶT (sửa 2026-08-21, mục 8 bảng
    trạng thái). Trước bản này `prefer` CHỈ chèn lên đầu, nên model vốn đã đứng
    đầu thì nó không thêm gì — người chọn 3.5 nhận chuỗi NGẮN HƠN người chọn
    3.1:

        read, prefer=3.1 → 3.1-lite, 3.5-lite, groq-llama, or-nemotron   (4)
        read, prefer=3.5 → 3.5-lite, groq-llama, or-nemotron             (3)

    Gặp thật: hỏi tồn kho khi chọn 3.5 → `ChainExhausted` trong khi 3.1 vẫn còn
    hạn mức nhưng KHÔNG nằm trong chuỗi. Nay hai lựa chọn đối xứng nhau.

    Hệ quả có chủ đích: hai mắt xích đầu cùng upstream="google". Bất biến #1
    (không hai mắt xích chung upstream) chỉ kiểm bảng CHAINS TĨNH, và đó là
    đúng phạm vi của nó — nó tồn tại để tránh rơi từ một miền lỗi vào lại chính
    nó, còn hai model Gemini là hai VÍ HẠN MỨC riêng. Đo được 2026-08-21:
    3.5-flash-lite cạn hạn mức ngày trong khi 3.1-flash-lite vẫn trả 200.
    """
    aliases = list(CHAINS[role])
    if prefer and prefer in CATALOG:
        aliases = [prefer] + [a for a in aliases if a != prefer]
        # Chèn ngay SAU mắt xích đầu, không phải cuối: đây là dự phòng gần
        # nhất, phải đứng trước khi tụt sang upstream khác.
        for khac in reversed(MODEL_CHON_DUOC):
            if khac != prefer and khac not in aliases:
                aliases.insert(1, khac)
    return tuple(CATALOG[a] for a in aliases)
