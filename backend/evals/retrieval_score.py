# backend/evals/retrieval_score.py
"""Chấm điểm truy xuất — THUẦN, không chạm DB/Ollama/LLM.

Tách khỏi run_eval.py có chủ đích: nhờ vậy toàn bộ logic chấm chạy trong
chế độ pytest mặc định, không cần dựng hạ tầng. Bài học từ eval_synthesis —
logic chấm nằm chung với logic gọi model thì không ai test được nó.

Nhãn là CẶP (basename tệp, section_path) chứ không phải chunk_id: chunk_id
là bigserial, re-index đổi sạch, mà re-index chính là việc bắt buộc khi thử
embedding mới (spec 2026-08-19 §4).
"""
import os


def label_of(chunk) -> tuple[str, str]:
    """Quy một chunk về nhãn so sánh được.

    basename chứ không phải đường dẫn đầy đủ: source_file trong DB là đường
    dẫn tuyệt đối phụ thuộc máy đã ingest, còn nhãn viết tay thì không thể
    mang đường dẫn đó. Quy đổi ở ĐÚNG một chỗ này.

    sheet đỡ cho chunk xlsx (section_path của chúng luôn None); "" khi không
    có cả hai — vẫn là nhãn hợp lệ, chỉ là thô.
    """
    base = os.path.basename(str(chunk.source_file).replace("\\", "/"))
    section = chunk.section_path or chunk.sheet or ""
    return (base, section)


def score_one(ranked_labels: list[tuple[str, str]],
              expected: set[tuple[str, str]],
              k_pool: int, k_final: int) -> dict:
    """Số đo cho MỘT câu hỏi.

    ranked_labels: nhãn theo đúng thứ tự retrieve() trả về (hạng 1 trước).
    expected: tập nhãn đúng (>=1 phần tử).

    recall_at_pool đo trên k_pool đầu, recall_at_final trên k_final đầu —
    tách đôi vì reranker CHỈ sắp xếp lại, không thêm ứng viên: pool là trần
    mà rerank không bao giờ vượt được, final là thứ LLM thật sự nhìn thấy.
    Gộp hai số này làm một là mù trước tác dụng của rerank (spec §5).

    reciprocal_rank lấy hạng của nhãn đúng ĐẦU TIÊN, tính trên toàn danh
    sách (không cắt) — cắt rồi mới tính sẽ biến "hạng 8" thành "trượt", làm
    mất đúng tín hiệu cần để thấy rerank kéo nó lên.
    """
    hit_ranks = [i + 1 for i, lab in enumerate(ranked_labels) if lab in expected]

    def _recall(cut: int) -> float:
        seen = set(ranked_labels[:cut]) & expected
        return len(seen) / len(expected) if expected else 0.0

    return {
        "recall_at_pool": _recall(k_pool),
        "recall_at_final": _recall(k_final),
        "reciprocal_rank": 1.0 / hit_ranks[0] if hit_ranks else 0.0,
        "hit_ranks": hit_ranks,
    }
