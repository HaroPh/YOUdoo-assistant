"""Spike: ChatOpenAI có giữ được thought_signature của Gemini 3 qua vòng lặp
tool 2 lượt không?

Bối cảnh: gọi thô bằng curl ngày 2026-07-28 cho thấy Google trả
extra_content.google.thought_signature BÊN TRONG tool_calls. Trường này không
thuộc schema OpenAI, nên ChatOpenAI có thể vứt nó đi. Agent ERP sống bằng vòng
lặp tool nhiều lượt (spec §12).

Chạy:  python -m spikes.spike_thought_signature
"""
import json
import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

load_dotenv()

GOOGLE_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"


@tool
def get_stock(product: str) -> str:
    """Tra tồn kho theo tên sản phẩm."""
    return json.dumps({"product": product, "on_hand": 42, "uom": "cái"},
                      ensure_ascii=False)


@tool
def get_price(product: str) -> str:
    """Tra đơn giá bán theo tên sản phẩm."""
    return json.dumps({"product": product, "price": 1500000, "currency": "VND"},
                      ensure_ascii=False)


def main() -> None:
    llm = ChatOpenAI(model="gemini-3.5-flash-lite", base_url=GOOGLE_BASE,
                     api_key=os.environ["GOOGLE_API_KEY"], temperature=0,
                     timeout=60)
    bound = llm.bind_tools([get_stock, get_price])
    tools = {"get_stock": get_stock, "get_price": get_price}

    messages = [HumanMessage(
        "Sản phẩm ABC còn bao nhiêu hàng, và đơn giá bao nhiêu?")]

    for turn in range(1, 4):
        ai = bound.invoke(messages)
        messages.append(ai)
        print(f"\n─── Lượt {turn} ───")
        print("  tool_calls        :", [tc["name"] for tc in ai.tool_calls])
        print("  additional_kwargs :", json.dumps(
            ai.additional_kwargs, ensure_ascii=False, default=str)[:400])
        print("  response_metadata :", json.dumps(
            ai.response_metadata, ensure_ascii=False, default=str)[:400])
        blob = json.dumps({"ak": ai.additional_kwargs,
                           "rm": ai.response_metadata,
                           "tc": ai.tool_calls}, default=str)
        print("  CÓ thought_signature:", "thought_signature" in blob)

        if not ai.tool_calls:
            print("\n─── Câu trả lời cuối ───")
            print(ai.content)
            return
        for tc in ai.tool_calls:
            out = tools[tc["name"]].invoke(tc["args"])
            messages.append(ToolMessage(content=out, tool_call_id=tc["id"]))

    print("\nKHÔNG hội tụ sau 3 lượt — vòng lặp tool có vấn đề.")


if __name__ == "__main__":
    main()
