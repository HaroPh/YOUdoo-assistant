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

# Dấu phân cách breadcrumb — phải trùng với chunking.chunk_text_blocks.
SEP = " › "



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


def label_matches(got: tuple[str, str], want: tuple[str, str]) -> bool:
    """Nhãn chunk `got` có thoả nhãn mong đợi `want` không.

    Khớp theo HẬU TỐ CĂN ĐOẠN chứ không phải bằng nhau tuyệt đối, từ
    2026-08-20 khi section_path của PDF luật trở thành phân cấp:

        want: "Điều 102. Hưởng bảo hiểm xã hội một lần"
        got:  "Chương VI  › BẢO HIỂM XÃ HỘI TỰ NGUYỆN  › Mục 2. ...  › Điều 102. ..."

    Vì sao hậu tố chứ không phải cắt lấy đoạn lá của cả hai bên: cắt lấy lá
    làm bộ đo MÙ với chính thứ nó vừa đi sửa — nếu breadcrumb dựng sai chương
    ("Chương V" cho Điều 102) thì cắt lá vẫn khớp và không ai biết. Với hậu
    tố, một fixture có thể ghim cả chương khi cần độ chính xác đó.

    Mọi fixture viết trước ngày này vẫn khớp nguyên: một chuỗi luôn là hậu tố
    của chính nó, và nhãn của tài liệu .docx (vốn đã phân cấp sẵn) không đổi.

    Ranh giới đoạn là bắt buộc: không có nó thì "Điều 2. ..." sẽ khớp nhầm
    vào "Điều 102. ...".
    """
    got_file, got_sec = got
    want_file, want_sec = want
    if got_file != want_file:
        return False
    return got_sec == want_sec or got_sec.endswith(SEP + want_sec)


def sql_section_suffix(section: str) -> tuple[str, str]:
    """Cặp tham số cho mệnh đề `(section_path = %s OR section_path LIKE %s)`.

    Bản SQL của `label_matches`. Đặt cạnh nhau CỐ Ý: dấu phân cách breadcrumb
    xuất hiện ở ba nơi (chunking dựng, matcher Python so, SQL của test hợp
    đồng so) và chép nó ra ba chỗ là cách chắc chắn để một chỗ trôi mà hai chỗ
    kia không biết.
    """
    return section, "%" + SEP + section


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
    hit_ranks = [i + 1 for i, lab in enumerate(ranked_labels)
                 if any(label_matches(lab, e) for e in expected)]

    def _recall(cut: int) -> float:
        # Đếm theo nhãn MONG ĐỢI đã được phủ, không theo nhãn trả về: một
        # nhãn mong đợi có thể được phủ bởi nhiều chunk (một Điều dài bị cắt
        # nhiều mảnh), và đếm nhầm chiều sẽ cho recall > 1.
        seen = {e for e in expected
                for lab in ranked_labels[:cut] if label_matches(lab, e)}
        return len(seen) / len(expected) if expected else 0.0

    return {
        "recall_at_pool": _recall(k_pool),
        "recall_at_final": _recall(k_final),
        "reciprocal_rank": 1.0 / hit_ranks[0] if hit_ranks else 0.0,
        "hit_ranks": hit_ranks,
    }
