"""Contract test — CẦN MẠNG và API key thật.

Chạy:  pytest tests/llm/test_live_providers.py -m live -v
Bỏ:    pytest -m "not live"

Đây là các phép đo tay ngày 2026-07-28 được đóng gói để chạy lại được. Chúng
bắt thứ nằm ngoài tầm kiểm soát của repo: nhà cung cấp khai tử model free
(thường lặng lẽ), hoặc đổi hình dạng response.

TIÊU HAO HẠN MỨC: mỗi lần chạy tốn vài lượt gọi thật. Gemini Flash không-Lite
chỉ có 20 lượt/ngày, nên KHÔNG thêm test nào chạm vào nhóm đó.
"""
import json
import os

import httpx
import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from src.llm.catalog import CATALOG
from src.llm.providers import BASE_URLS, ENV_KEYS, client_for

pytestmark = pytest.mark.live


@tool
def get_stock(product: str) -> str:
    """Tra tồn kho theo tên sản phẩm."""
    return json.dumps({"product": product, "on_hand": 42}, ensure_ascii=False)


def _skip_neu_thieu_key(provider: str) -> None:
    if not os.environ.get(ENV_KEYS[provider]):
        pytest.skip(f"chưa đặt {ENV_KEYS[provider]}")


# ─── Tool-calling qua cả ba nhà ─────────────────────────────────────────────

@pytest.mark.parametrize("alias", [
    "gemini-3.5-flash-lite", "groq-gpt-oss-20b", "or-nemotron",
])
def test_tool_calling_hoat_dong_voi_tieng_viet(alias):
    spec = CATALOG[alias]
    _skip_neu_thieu_key(spec.provider)
    response = client_for(spec).bind_tools([get_stock]).invoke(
        [HumanMessage("Tồn kho sản phẩm ABC còn bao nhiêu?")])
    assert response.tool_calls, f"{alias} không gọi tool"
    assert response.tool_calls[0]["name"] == "get_stock"


# ─── Vòng lặp tool 2 lượt qua Google (canh gác thought_signature) ────────────

def test_vong_lap_tool_hai_luot_qua_google_van_hoi_tu():
    """Canh gác hồi quy cho rủi ro §12. Nếu test này đỏ, đọc lại
    docs/spikes/2026-07-28-thought-signature.md — có thể phải đổi client Google
    sang langchain-google-genai."""
    _skip_neu_thieu_key("google")
    spec = CATALOG["gemini-3.5-flash-lite"]
    bound = client_for(spec).bind_tools([get_stock])
    messages = [HumanMessage("Tồn kho sản phẩm ABC còn bao nhiêu?")]

    ai = bound.invoke(messages)
    assert ai.tool_calls
    messages.append(ai)
    for tc in ai.tool_calls:
        messages.append(ToolMessage(content=get_stock.invoke(tc["args"]),
                                    tool_call_id=tc["id"]))

    cuoi = bound.invoke(messages)
    assert not cuoi.tool_calls, "không hội tụ — vẫn còn đòi gọi tool"
    assert "42" in (cuoi.content or ""), "không dùng kết quả tool trong câu trả lời"


# ─── Lý do tồn tại của strip_thought vẫn còn đúng ───────────────────────────

def test_gemma_van_nha_thought_vao_content():
    """Nếu Google sửa endpoint để tách thinking ra, test này đỏ — và đó là tin
    TỐT: lúc đó strip_thought() thành thừa và nên gỡ bỏ, chứ không phải để lại
    một cú scrub không ai hiểu vì sao còn ở đó.

    Phép đo gốc 2026-07-28 chạy TRƯỚC khi Task 7 đổi client Google sang
    ChatGoogleGenerativeAI. Nếu test này đỏ, kiểm tra trước xem có phải do đổi
    CLIENT (không phải đổi provider/model) gây ra, trước khi kết luận Gemma đã
    ngừng nhả <thought> — content vẫn là string thường qua cả hai client nên
    kết quả không lẽ ra phải đổi, nhưng đáng kiểm chứng lại nếu bất ngờ đỏ."""
    _skip_neu_thieu_key("google")
    spec = CATALOG["gemma-4-26b"]
    response = client_for(spec).invoke([HumanMessage("Xin chào, bạn khoẻ không?")])
    assert "<thought>" in (response.content or ""), (
        "Gemma không còn nhả <thought> — cân nhắc gỡ strip_thought() và cờ "
        "emits_thought_tags")


def test_gemma_van_co_thought_token_rieng_trong_usage_metadata():
    """Lý do tồn tại của quy tắc 'total_tokens là con số có thẩm quyền'.

    Phép đo gốc 2026-07-28 (p=11, c=36, total=337) được lấy qua endpoint
    OpenAI-compat cũ của Google, đọc response_metadata["token_usage"]. Task 7
    đổi client Google sang ChatGoogleGenerativeAI (spike thought_signature) —
    client này KHÔNG BAO GIỜ set response_metadata["token_usage"], usage chỉ
    nằm ở response.usage_metadata (UsageMetadata TypedDict), và output_tokens
    ở đó đã CỘNG SẴN thought_tokens vào, nên tỉ lệ total > (p+c)*2 không còn
    áp dụng theo cách cũ. Test này giờ kiểm trực tiếp trường accounting riêng
    của SDK cho token "thinking" — output_token_details["reasoning"] — thay vì
    suy luận gián tiếp qua chênh lệch tổng, vì đó là cách chính xác hơn để xác
    nhận Gemma vẫn còn token thinking ẩn."""
    _skip_neu_thieu_key("google")
    spec = CATALOG["gemma-4-26b"]
    response = client_for(spec).invoke([HumanMessage("Xin chào, bạn khoẻ không?")])
    usage = response.usage_metadata
    reasoning = (usage.get("output_token_details") or {}).get("reasoning") or 0
    assert reasoning > 0, (
        f"usage_metadata không còn output_token_details.reasoning > 0 "
        f"(usage={usage!r}) — cân nhắc xem lại quy tắc total_tokens trong "
        "budget.py, có thể Gemma đã ngừng ẩn token thinking")


# ─── Catalog không trôi khỏi thực tế ────────────────────────────────────────

def _ids_google() -> set[str]:
    r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models",
                  params={"key": os.environ["GOOGLE_API_KEY"], "pageSize": 300},
                  timeout=30)
    r.raise_for_status()
    return {m["name"].removeprefix("models/") for m in r.json()["models"]}


def _ids_openai_compat(provider: str) -> set[str]:
    r = httpx.get(f"{BASE_URLS[provider].rstrip('/')}/models",
                  headers={"Authorization":
                           f"Bearer {os.environ[ENV_KEYS[provider]]}"},
                  timeout=30)
    r.raise_for_status()
    return {m["id"] for m in r.json()["data"]}


@pytest.mark.parametrize("provider", ["google", "groq", "openrouter"])
def test_moi_model_id_trong_catalog_van_con_ton_tai(provider):
    """Bắt được lúc nhà cung cấp khai tử một model free — thường lặng lẽ."""
    _skip_neu_thieu_key(provider)
    thuc_te = (_ids_google() if provider == "google"
               else _ids_openai_compat(provider))
    thieu = [s.model_id for s in CATALOG.values()
             if s.provider == provider and s.model_id not in thuc_te]
    assert not thieu, (
        f"{provider} không còn các model sau: {thieu} — cập nhật catalog.py "
        f"VÀ docs/provider-quotas.md")
