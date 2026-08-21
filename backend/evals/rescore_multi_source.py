"""Chấm lại baseline-qwen3-8b-multi_source.json sau khi sửa bug scanner
fabricated_number (spec §3, run_eval.py eval_multi_source()) và sau khi thêm
số suy ra được thủ công cho case ngày-tháng (cases.py
MULTI_SOURCE_DERIVED_DIGITS, quyết định lại ở SP-1C1 sau 2 lần chạy gate).

KHÔNG chạy lại qwen3:8b — dùng đúng `fabricated` đã lưu trong `fails` của
baseline gốc (tính trên VĂN BẢN ĐẦY ĐỦ khi baseline được chụp), rồi lọc lại
theo allowed_new bằng đại số tập hợp:

    fabricated_new = fabricated_old \\ allowed_new

Đúng vì allowed_new ⊇ allowed_old ở CẢ HAI lần mở rộng: _format_context
chứa nguyên c.text cộng thêm [i] và nhãn mục; MULTI_SOURCE_DERIVED_DIGITS
chỉ CỘNG THÊM số cho đúng (topic, question) đã ghi nhận, không bớt gì —
allowed chỉ TO RA, không bao giờ nhỏ đi. KHÔNG dùng trường "response" trong
bản ghi — nó bị CẮT CỤT ở 300 ký tự (run_eval.py dòng "response":
body[:300]), quét lại đoạn cắt sẽ đếm thiếu và sai lặng lẽ.

Chạy: cd backend && .venv/Scripts/python.exe -m evals.rescore_multi_source
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from evals import fixtures
from evals.cases import MULTI_SOURCE_CASES, MULTI_SOURCE_DERIVED_DIGITS
from evals.run_eval import _digits
from src.agents.synthesis import _format_context
from src.cli_console import use_utf8_streams

_PATH = Path(__file__).resolve().parent / "baseline-qwen3-8b-multi_source.json"


def _allowed_new(topic: str, erp_block: str, question: str) -> set[str]:
    chunks = fixtures.load_chunks(topic)
    allowed = _digits(erp_block) | _digits(_format_context(chunks))
    return allowed | MULTI_SOURCE_DERIVED_DIGITS.get((topic, question), frozenset())


def rescore() -> dict:
    data = json.loads(_PATH.read_text(encoding="utf-8"))
    original = data["fabricated_number"]

    # Map topic -> erp_block từ chính MULTI_SOURCE_CASES (bản ghi baseline
    # không lưu erp_block, chỉ lưu topic/question/response).
    by_topic_question = {(t, q): erp for t, erp, q, _doc, _erp_fact
                         in MULTI_SOURCE_CASES}

    new_fails = []
    for f in data["fails"]:
        erp_block = by_topic_question.get((f["topic"], f["question"]))
        if erp_block is None:
            raise KeyError(
                f"không khớp lại được case gốc cho {f['topic']!r}/"
                f"{f['question']!r} — MULTI_SOURCE_CASES đã đổi so với lúc "
                "chụp baseline, không chấm lại an toàn được")
        allowed_new = _allowed_new(f["topic"], erp_block, f["question"])
        fabricated_new = sorted(set(f["fabricated"]) - allowed_new)
        f2 = dict(f, fabricated=fabricated_new)
        new_fails.append(f2)

    fabricated_number_new = sum(1 for f in new_fails if f["fabricated"])

    data["fails"] = new_fails
    data["fabricated_number"] = fabricated_number_new
    # setdefault, KHÔNG gán thẳng: `original` đọc từ TRẠNG THÁI HIỆN TẠI của
    # file mỗi lần script chạy. Idempotency (Task 6 Bước 7 yêu cầu chạy lại
    # để xác nhận không đổi) có nghĩa script này chạy ≥2 lần trên cùng file —
    # gán thẳng ở lần chạy thứ 2 sẽ ghi đè provenance thật (4) bằng kết quả
    # rescore lần đầu (1), xóa mất lịch sử gốc. setdefault chỉ ghi lần ĐẦU
    # TIÊN khi field chưa tồn tại, giữ nguyên giá trị đã có ở mọi lần sau.
    data.setdefault("original_fabricated_number", original)
    data["rescored_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return data


if __name__ == "__main__":
    use_utf8_streams()
    result = rescore()
    print(f"fabricated_number: {result['original_fabricated_number']} -> "
         f"{result['fabricated_number']}")
    if result["fabricated_number"] != 0:
        print("CẢNH BÁO: baseline hiệu chỉnh KHÔNG tự đạt gate của chính nó "
             "(fabricated_number != 0) — bản sửa scanner có thể chưa đủ, "
             "hoặc qwen3:8b bịa thật. DỪNG, điều tra trước khi chạy gate "
             "thật (Task 7).")
