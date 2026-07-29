"""Mặt tiền LLM cho tầng agents — mỏng, chỉ chuyển tiếp sang llm/router.py.

Toàn bộ trí tuệ chọn model nằm ở src/llm/ (kế hoạch A): catalog hạn mức thật,
sổ ngân sách cửa sổ trượt, tụt mắt xích khi cạn hoặc lỗi. File này chỉ giữ đúng
hai cái tên mà agents/ đã gọi từ trước, để port sang không phải sửa chỗ gọi nào.

─── QĐ M2 CỦA ADR-009 BỊ THAY THẾ CÓ CHỦ ĐÍCH, KHÔNG PHẢI BỊ QUÊN ─────────────

Bản cũ của file này có CLOUD_ALLOWED = frozenset({"router", "evaluator",
"chitchat"}) và ép nó ở ngay tầng thực thi: bốn vai mang dữ liệu nghiệp vụ
(read, planner, fusion, synthesis — tên khách, đơn hàng, tồn kho, tài liệu nội
bộ) LUÔN chạy model local, env override cho chúng bị bỏ qua có chủ đích.

SP-1 bỏ Ollama khỏi đường chat, nên bốn vai đó không còn chỗ nào ngoài cloud.
Đây là thay thế một quyết định đã khoá, và nó được chấp nhận vì: dữ liệu Odoo
trong hệ này là dữ liệu demo, và project là demo/portfolio (chủ dự án xác nhận
2026-07-28).

Dữ kiện đi kèm, để phiên sau không phải đoán lại: tier TRẢ PHÍ của
Anthropic/OpenAI mặc định không dùng dữ liệu API để huấn luyện, còn free tier
của Google AI Studio thì CÓ. Nên ranh giới đúng không phải "cloud hay local" mà
là "free demo bây giờ / trả phí thật về sau" — và khi hệ này mang dữ liệu thật,
đường đi là chuyển sang tier trả phí, không phải quay lại local.

Lý do đầy đủ: docs/ADR-011-sp1-foundation.md mục 1.

─── HAI HẰNG SỐ HIỆU CHỈNH CHO qwen3:8b ĐÃ THÀNH DỮ LIỆU CATALOG ─────────────

Bản cũ có max_tokens=4096 cho vai planner — circuit breaker cho vòng sinh không
dừng đã xác nhận của qwen3:8b (quan sát 7000+ token), hiệu chỉnh riêng cho model
đó: ~3.3 lần nhu cầu hợp lệ cao nhất đo được (1250 token), ở tốc độ ~65
token/giây. Và timeout = 120 if is_qwen(name) else 30.

Cả hai giả định — token "thinking" vô hình và tốc độ sinh — đều không còn đúng
với Gemini hay Groq. Chúng vẫn là lưới an toàn THẬT, nên không bỏ đi: chúng
thành spec.max_output_tokens và spec.timeout_s trong llm/catalog.py, tức ngưỡng
theo từng model thay vì một hằng số ghim cho một model đã rời hệ thống.
"""
from ..llm.catalog import ROLES
from ..llm.router import RoutedChatModel, build_router
from ..llm.router import make_llms as _make_llms_router


def make_llms() -> dict[str, RoutedChatModel]:
    """dict vai → model. KHÔNG tham số — giữ đúng hợp đồng cũ của erp_agent.py.

    Khác với llm.router.make_llms(router, pins=None) vốn cần router: hàm này tự
    dựng router cho đường chạy thật (sổ ngân sách Postgres).
    """
    return _make_llms_router(build_router())


def llms_from_single(llm) -> dict:
    """Back-compat cho test/caller cũ: mọi vai dùng chung 1 llm.

    graph.py chuẩn hoá tham số llm qua hàm này (nhận dict thì dùng luôn, nhận
    một object thì trải ra mọi vai), nên nó phải sống sót qua cú port.
    """
    return {role: llm for role in ROLES}
