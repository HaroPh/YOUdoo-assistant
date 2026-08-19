# backend/evals/matching.py
"""Khớp nguyên văn dùng chung cho các bộ eval — DI CHUYỂN THUẦN từ run_eval.py
ngày 2026-08-19, không đổi một dòng logic nào.

Vì sao tách: synthesis_live_score.py cần _grounded_match, mà nó không thể
import run_eval (chính run_eval import nó — vòng lặp import). Sao chép hàm
sang file thứ hai là cách chắc chắn nhất để hai bản trôi lệch khỏi nhau.

Tên giữ nguyên dấu gạch dưới đầu để mọi chỗ gọi trong run_eval.py không phải
sửa gì.
"""


def _norm(v) -> str:
    return str(v).strip().casefold()


def _grounded_match(expect: str | tuple[str, ...], body: str) -> bool:
    """eval_synthesis(): body coi là "khớp căn cứ" với `expect` nếu khớp
    NGUYÊN VĂN — hoặc, nếu `expect` là một tuple nhiều chuỗi, khớp NGUYÊN
    VĂN với BẤT KỲ chuỗi nào trong đó. Mỗi phương án trong tuple là một cách
    diễn giải THẬT đã quan sát được từ model (ghi nhận từng trường hợp cụ
    thể, có dẫn chứng), KHÔNG phải suy luận ngữ nghĩa/mờ chung chung.

    Lịch sử (SP-1C1, chạy gate thật): bản đầu của hàm này thử "nới lỏng
    chung" bằng khớp-theo-thứ-tự-từ có giới hạn khoảng cách chèn — review
    độc lập (2 vòng) liên tục tìm được câu trả lời SAI (đảo cực tính qua một
    mệnh đề rào đón ngắn kiểu "Không sao, ... vẫn được hoàn trả") vẫn lọt
    qua bất kể rào được siết chặt tới đâu, vì bản chất khớp-theo-thứ-tự
    không phân biệt được "không" thuộc về phủ định thật hay một mệnh đề phụ
    không liên quan đứng trước. Kết luận: một heuristic mờ áp dụng chung cho
    MỌI expect không phải hướng an toàn — thay bằng danh sách các phương án
    khớp NGUYÊN VĂN, chỉ áp dụng cho ĐÚNG case đã quan sát được diễn giải
    (xem `SYNTHESIS_CASES` trong cases.py: case "không được hoàn trả" có
    thêm phương án "không được áp dụng chính sách hoàn trả"). Mỗi phương án
    vẫn là so khớp nguyên văn — không có logic mờ nào. Tập chấp nhận CHỈ mở
    rộng đúng bằng các câu chứa nguyên văn phương án 2 (không mở rộng theo
    thứ tự/khoảng cách từ như 2 bản trước) — không có LOẠI bề mặt lọt sai
    mới nào so với hành vi CŨ, dù tập chấp nhận về mặt tập hợp có to hơn.

    Mất mát đã biết và chấp nhận: một diễn giải KHÁC (chưa từng quan sát,
    không nằm trong danh sách phương án) sẽ vẫn trượt — và vì gate synthesis
    so `grounded_acc >= 1.0` (baseline đã đạt 12/12), MỘT case trượt là gate
    ĐỎ ngay, không phải tín hiệu mềm. Cần thêm phương án mới nếu/khi diễn
    giải mới xuất hiện thật ở một lượt chạy gate sau, cùng cách xử lý Task 6
    đã áp dụng cho `multi_source` (ghi nhận từng trường hợp cụ thể có dẫn
    chứng, không đoán trước)."""
    alts = expect if isinstance(expect, tuple) else (expect,)
    b = _norm(body)
    return any(_norm(alt) in b for alt in alts)
