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
    một cú scrub không ai hiểu vì sao còn ở đó."""
    _skip_neu_thieu_key("google")
    spec = CATALOG["gemma-4-26b"]
    response = client_for(spec).invoke([HumanMessage("Xin chào, bạn khoẻ không?")])
    assert "<thought>" in (response.content or ""), (
        "Gemma không còn nhả <thought> — cân nhắc gỡ strip_thought() và cờ "
        "emits_thought_tags")


def test_gemma_van_dem_thieu_token_neu_cong_prompt_va_completion():
    """Lý do tồn tại của quy tắc 'total_tokens là con số có thẩm quyền'."""
    _skip_neu_thieu_key("google")
    spec = CATALOG["gemma-4-26b"]
    response = client_for(spec).invoke([HumanMessage("Xin chào, bạn khoẻ không?")])
    usage = response.response_metadata["token_usage"]
    tong_phan = usage["prompt_tokens"] + usage["completion_tokens"]
    assert usage["total_tokens"] > tong_phan * 2, (
        f"total={usage['total_tokens']} không còn lớn hơn hẳn p+c={tong_phan} "
        "— cân nhắc xem lại quy tắc total_tokens trong budget.py")


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
