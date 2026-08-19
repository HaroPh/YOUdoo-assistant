# backend/tests/evals/test_retrieval_score.py
"""Bộ chấm truy xuất — unit thuần, KHÔNG cần Postgres/Ollama/GPU."""
import pytest

from evals.retrieval_score import label_of, score_one


class _Chunk:
    """Đủ field mà label_of() đọc — không dựng src.rag.types.Chunk thật
    (14 tham số bắt buộc, phần lớn vô nghĩa với bài test này)."""

    def __init__(self, source_file, section_path=None, sheet=None):
        self.source_file = source_file
        self.section_path = section_path
        self.sheet = sheet


def test_label_of_uses_basename_not_full_path():
    # doc_id/source_file là đường dẫn tuyệt đối phụ thuộc máy; nhãn viết tay
    # thì không thể mang đường dẫn đó. Quy về basename ở ĐÚNG một chỗ.
    c = _Chunk(r"D:/Youdoo/backend/src/rag/seed/policy.docx", "Mục 2")
    assert label_of(c) == ("policy.docx", "Mục 2")


def test_label_of_falls_back_to_sheet_for_xlsx():
    c = _Chunk("/x/bang_gia.xlsx", None, "Bảng giá")
    assert label_of(c) == ("bang_gia.xlsx", "Bảng giá")


def test_label_of_empty_string_when_no_section_or_sheet():
    c = _Chunk("/x/a.pdf")
    assert label_of(c) == ("a.pdf", "")


def test_score_one_perfect_hit_at_rank_one():
    ranked = [("a.pdf", "Điều 1"), ("b.pdf", "Điều 9")]
    got = score_one(ranked, {("a.pdf", "Điều 1")}, k_pool=20, k_final=6)
    assert got["recall_at_pool"] == 1.0
    assert got["recall_at_final"] == 1.0
    assert got["reciprocal_rank"] == 1.0
    assert got["hit_ranks"] == [1]


def test_score_one_miss_gives_zero_reciprocal_rank():
    ranked = [("b.pdf", "Điều 9")]
    got = score_one(ranked, {("a.pdf", "Điều 1")}, k_pool=20, k_final=6)
    assert got["recall_at_pool"] == 0.0
    assert got["reciprocal_rank"] == 0.0
    assert got["hit_ranks"] == []


def test_score_one_partial_recall_with_two_expected_labels():
    ranked = [("a.pdf", "Điều 1"), ("c.pdf", "Điều 3")]
    expected = {("a.pdf", "Điều 1"), ("b.pdf", "Điều 2")}
    got = score_one(ranked, expected, k_pool=20, k_final=6)
    assert got["recall_at_pool"] == pytest.approx(0.5)


def test_score_one_final_cut_is_narrower_than_pool():
    # Nhãn đúng nằm ở hạng 8 — trong pool 20 nhưng NGOÀI top-6. Đây chính là
    # ca phân biệt hai số đo; gộp chúng làm một là mù trước tác dụng rerank.
    ranked = [("x.pdf", f"E{i}") for i in range(7)] + [("a.pdf", "Điều 1")]
    got = score_one(ranked, {("a.pdf", "Điều 1")}, k_pool=20, k_final=6)
    assert got["recall_at_pool"] == 1.0
    assert got["recall_at_final"] == 0.0
    assert got["reciprocal_rank"] == pytest.approx(1 / 8)


def test_score_one_duplicate_labels_count_once():
    # Nhiều chunk cùng một mục quy về CÙNG một nhãn (đánh đổi đã chấp nhận ở
    # spec §4). Recall không được vượt 1.0 vì trúng lặp.
    ranked = [("a.pdf", "Điều 1"), ("a.pdf", "Điều 1")]
    got = score_one(ranked, {("a.pdf", "Điều 1")}, k_pool=20, k_final=6)
    assert got["recall_at_pool"] == 1.0


def test_score_one_empty_ranked_list_is_total_miss():
    got = score_one([], {("a.pdf", "Điều 1")}, k_pool=20, k_final=6)
    assert got["recall_at_pool"] == 0.0
    assert got["reciprocal_rank"] == 0.0


def test_score_one_reciprocal_rank_uses_first_hit_only():
    ranked = [("z.pdf", "E0"), ("a.pdf", "Điều 1"), ("b.pdf", "Điều 2")]
    expected = {("a.pdf", "Điều 1"), ("b.pdf", "Điều 2")}
    got = score_one(ranked, expected, k_pool=20, k_final=6)
    assert got["reciprocal_rank"] == pytest.approx(1 / 2)
    assert got["hit_ranks"] == [2, 3]
