# backend/spikes/spike_reranker_smoke.py
"""Khói reranker: 3 cặp cố định, in điểm + VRAM đỉnh + ms — cho MỘT model.

Chạy mỗi model bằng một tiến trình riêng (env RERANK_MODEL), vì _load()
cache một lần. Không phải eval — chỉ để chắc model tải được, chấm ra số
có nghĩa, và biết chi phí trước khi đốt 64 × 20 cặp.

    RERANK_MODEL=Qwen/Qwen3-Reranker-0.6B python -m spikes.spike_reranker_smoke
    RERANK_MODEL=Qwen/Qwen3-Reranker-4B RERANK_DEVICE_MAP=auto python -m spikes.spike_reranker_smoke
"""
import sys
import time

sys.path.insert(0, ".")
from src.rag import reranker  # noqa: E402

QUERY = "một bên tự ý dừng hợp đồng giữa chừng thì hậu quả là gì?"
# Cặp 1 là đáp án đúng (Điều 428), cặp 2 là bẫy trùng mặt chữ (Điều 309),
# cặp 3 lạc đề hẳn. Reranker tốt phải xếp 1 > 2 > 3.
DOCS = [
    "Điều 428. Đơn phương chấm dứt thực hiện hợp đồng. Một bên có quyền đơn "
    "phương chấm dứt thực hiện hợp đồng và không phải bồi thường thiệt hại khi "
    "bên kia vi phạm nghiêm trọng nghĩa vụ trong hợp đồng.",
    "Điều 309. Hậu quả pháp lý của việc tạm ngừng thực hiện hợp đồng. Khi hợp "
    "đồng bị tạm ngừng thực hiện thì hợp đồng vẫn còn hiệu lực.",
    "Điều 9. Thuế suất. Mức thuế suất 0% áp dụng đối với hàng hóa, dịch vụ "
    "xuất khẩu.",
]


def main() -> None:
    import torch
    print(f"model       : {reranker.RERANK_MODEL}  ({reranker._family()})")
    print(f"device_map  : {reranker.RERANK_DEVICE_MAP or '(kiểu cũ)'}")
    t0 = time.perf_counter()
    scores = reranker.score_pairs(QUERY, DOCS)
    load_ms = (time.perf_counter() - t0) * 1000
    if scores is None:
        print("HỎNG: score_pairs trả None — đọc warning ở trên.")
        sys.exit(1)
    # Lượt 2 mới là chi phí thật/lượt (lượt 1 gánh cả nạp model).
    t1 = time.perf_counter()
    for _ in range(5):
        reranker.score_pairs(QUERY, DOCS)
    per_call_ms = (time.perf_counter() - t1) * 1000 / 5
    order = sorted(range(3), key=lambda i: scores[i], reverse=True)
    print(f"điểm        : {[round(s, 4) for s in scores]}")
    print(f"thứ tự      : {[i + 1 for i in order]}   (mong đợi [1, 2, 3])")
    print(f"nạp + lượt 1: {load_ms:.0f} ms")
    print(f"ms/lượt (3 cặp, TB 5 lượt): {per_call_ms:.1f}")
    if torch.cuda.is_available():
        print(f"VRAM đỉnh   : {torch.cuda.max_memory_allocated() / 2**20:.0f} MiB")


if __name__ == "__main__":
    main()
