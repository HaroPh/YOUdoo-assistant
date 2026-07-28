"""Bảng model — nguồn sự thật duy nhất cho tầng LLM (spec SP-1 §2).

Mọi con số hạn mức ở đây phải khớp docs/provider-quotas.md. Sửa một nơi thì
sửa cả hai; test contract (Task 11) đối chiếu model_id với /models thật.

KHÔNG có khoá API nào trong file này.
"""
from dataclasses import dataclass


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
    "gemma-4-31b": ModelSpec(
        alias="gemma-4-31b", provider="google",
        model_id="gemma-4-31b-it", upstream="google",
        quota_scope="model", rpm=30, tpm=16_000, rpd=14_400,
        token_multiplier=1.0, max_output_tokens=2048, timeout_s=60,
        supports_tools=True, emits_thought_tags=True),

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
    "router":    ("gemma-4-26b", "groq-gpt-oss-20b", "or-ling"),
    "chitchat":  ("gemma-4-31b", "groq-gpt-oss-20b"),
    "evaluator": ("groq-gpt-oss-20b", "gemma-4-26b"),
    "planner":   ("gemini-3.5-flash-lite", "groq-gpt-oss-120b", "or-nemotron"),
    "read":      ("gemini-3.5-flash-lite", "groq-llama-3.3-70b", "or-nemotron"),
    "fusion":    ("gemini-3.1-flash-lite", "groq-llama-3.3-70b"),
    "synthesis": ("gemini-3.1-flash-lite", "groq-llama-3.3-70b", "or-nemotron"),
}


def spec_for(alias: str) -> ModelSpec:
    """Ném KeyError nếu alias lạ — cấu hình sai phải chết sớm, không đoán."""
    return CATALOG[alias]


def chain_for(role: str) -> tuple[ModelSpec, ...]:
    return tuple(CATALOG[a] for a in CHAINS[role])
