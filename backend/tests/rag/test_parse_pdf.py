class _FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class _FakeReader:
    def __init__(self, pages_text):
        self.pages = [_FakePage(t) for t in pages_text]


def test_parse_pdf_strips_nul_bytes_from_unmapped_glyphs(monkeypatch):
    # pypdf maps some unrecognized glyphs (e.g. a custom bullet-point font) to
    # U+0000 instead of dropping them. Postgres text columns reject NUL bytes
    # outright, so any block still carrying one would crash ingest for the
    # whole file. parse_pdf must sanitize this at the source.
    import pypdf
    from src.rag import parse

    fake = _FakeReader(["\x00 Verify the delivered supplies against the PO."])
    monkeypatch.setattr(pypdf, "PdfReader", lambda path: fake)

    blocks = parse.parse_pdf("irrelevant.pdf")

    assert len(blocks) == 1
    assert "\x00" not in blocks[0]["text"]
    assert blocks[0]["text"] == "Verify the delivered supplies against the PO."


def test_khoan_single_level_number_is_not_heading(monkeypatch):
    # Bug 2026-07-15: khoản luật 1 cấp ("1. ...") bị nhận nhầm heading →
    # chunking nuốt 3212 khoản khỏi index (Điều 124 khoản 1 "quá 90 ngày"
    # biến mất, agent trả lời sai ngưỡng cưỡng chế nợ thuế).
    import pypdf
    from src.rag import parse
    fake = _FakeReader([
        "Điều 124. Trường hợp bị cưỡng chế thi hành quyết định hành chính về quản lý thuế\n"
        "1. Người nộp thuế có tiền thuế nợ quá 90 ngày kể từ ngày hết thời hạn nộp theo quy định."
    ])
    monkeypatch.setattr(pypdf, "PdfReader", lambda path: fake)
    blocks = parse.parse_pdf("x.pdf")
    # Cấp 4 = "Điều" trong thang phân cấp (2026-08-20). Ghim số cụ thể
    # chứ không chỉ "is not None": đổi thang mà không ai hay thì
    # breadcrumb dựng sai âm thầm — đúng lớp lỗi thang phẳng đã gây ra.
    assert blocks[0]["heading_level"] == 4          # "Điều ..." vẫn là heading
    assert blocks[1]["heading_level"] is None       # khoản 1 cấp = NỘI DUNG


def test_multilevel_numeric_heading_still_detected(monkeypatch):
    # Khóa hành vi giữ lại: numbering đa cấp ("1.1", "3.2.1") vẫn là heading
    # (tài liệu kỹ thuật tương lai).
    import pypdf
    from src.rag import parse
    fake = _FakeReader(["1.1 Giới thiệu hệ thống\n3.2.1. Cấu hình chi tiết"])
    monkeypatch.setattr(pypdf, "PdfReader", lambda path: fake)
    blocks = parse.parse_pdf("x.pdf")
    # Cấp 5 = sâu nhất: numbering đa cấp là mục con của Điều,
    # không phải anh em với nó.
    assert blocks[0]["heading_level"] == 5
    assert blocks[1]["heading_level"] == 5


def test_money_and_hs_code_lines_are_not_headings(monkeypatch):
    # False positive thật tìm thấy trong corpus: số tiền VN (chấm phân cách
    # nghìn) và mã HS trong phụ lục luật đầu tư.
    import pypdf
    from src.rag import parse
    fake = _FakeReader(["5.000.000.000 đồng.\n2931.9080 77-81-6"])
    monkeypatch.setattr(pypdf, "PdfReader", lambda path: fake)
    blocks = parse.parse_pdf("x.pdf")
    assert all(b["heading_level"] is None for b in blocks)


# ── Lọc rác header/footer trang (spec 2026-08-19 §3) ─────────────────────────
# 727/3256 chunk PDF (22%) đang mang chuỗi kiểu
# "22:47 13/7/26 about:blank about:blank 1/164" NẰM GIỮA nội dung — nó đi vào
# embedding, ts_vector, cặp cho reranker và ngữ cảnh gửi LLM.
from src.rag.parse import _normalize_digits, detect_page_furniture


def _fake_pages(n, *, header=True, footer=True, middle_table=False):
    """n trang: [header] + 5 dòng thân + [footer].

    Thân PHẢI đủ 5 dòng. Với edge=2 tính từ CẢ HAI đầu, một trang 3 dòng thì
    mọi dòng đều nằm ở rìa và "khác." sẽ bị nhận nhầm là rác."""
    pages = []
    for i in range(1, n + 1):
        body = [f"Điều {i}. Nội dung riêng của trang {i}",
                "Câu mở đoạn không lặp lại.",
                "khác.",                       # lặp mọi trang, nhưng ở GIỮA
                "Câu tiếp theo cũng không lặp.",
                f"Đoạn kết riêng của trang {i}."]
        if middle_table:
            body.insert(2, f"{i} {i}.{i}")     # hàng bảng, cũng ở GIỮA
        lines = (["22:47 13/7/26 about:blank"] if header else []) + body
        if footer:
            lines.append(f"about:blank {i}/{n}")
        pages.append(lines)
    return pages


def test_normalize_digits_gop_cac_bien_the_so_trang():
    # Mấu chốt: "about:blank 5/164" và "about:blank 6/164" là hai chuỗi khác
    # nhau; đếm trần thì mỗi cái chỉ 1 trang và bộ lọc bỏ sót hoàn toàn.
    assert _normalize_digits("about:blank 5/164") == _normalize_digits("about:blank 6/164")
    assert _normalize_digits("about:blank 5/164") == "about:blank #/#"


def test_detect_bat_duoc_ca_header_lan_footer():
    got = detect_page_furniture(_fake_pages(20))
    assert _normalize_digits("about:blank 1/20") in got
    assert _normalize_digits("22:47 13/7/26 about:blank") in got


def test_detect_khong_an_dong_than_bai_lap_lai():
    # "khác." lặp ở MỌI trang nhưng nằm giữa → không phải rác trang.
    got = detect_page_furniture(_fake_pages(20))
    assert "khác." not in got


def test_detect_khong_an_hang_bang_o_giua_trang():
    # Ca dương-tính-giả THẬT đã đo được: "# #.#" là hàng bảng mã HS trong phụ
    # lục luat-thuexuatnhapkhau.pdf — nhiều hàng KHÁC NHAU bị chuẩn hoá gộp
    # chung, đẩy tần suất lên 48%. Chỉ điều kiện vị-trí-rìa mới loại được nó.
    got = detect_page_furniture(_fake_pages(20, middle_table=True))
    assert "# #.#" not in got


def test_detect_bo_qua_tai_lieu_qua_ngan():
    # Tài liệu 2 trang: một dòng hợp lệ lặp ở cả hai trang đã là 100%.
    assert detect_page_furniture(_fake_pages(2)) == set()


def test_detect_khong_an_dong_chi_o_ria_mot_vai_trang():
    # Xuất hiện ở rìa nhưng chỉ trên 3/20 trang → dưới ngưỡng tần suất.
    pages = _fake_pages(20, header=False, footer=False)
    for i in range(3):
        pages[i].append("Ghi chú cuối trang hiếm gặp.")
    assert "Ghi chú cuối trang hiếm gặp." not in detect_page_furniture(pages)


def test_detect_tra_ve_dang_da_chuan_hoa():
    # Hợp đồng đầu ra: caller so bằng _normalize_digits(line), nên tập trả về
    # phải là dạng ĐÃ chuẩn hoá — không còn chữ số nào.
    got = detect_page_furniture(_fake_pages(20))
    assert got, "phải bắt được ít nhất một dòng rác"
    assert not any(ch.isdigit() for g in got for ch in g)


# ── _HEADING_RE không được khớp tham chiếu giữa câu (spec §4) ────────────────
# 15 "mục" trong rag_chunks thực chất là mảnh câu tham chiếu chéo, mỗi mảnh
# CẮT ĐÔI một Điều thật. Đây là lỗi DUY NHẤT đã chứng minh gây hại đo được:
# chuỗi "Điều ước quốc tế mà Cộng hòa..." chiếm hạng 1 của một câu hỏi thật.
import pytest

from src.rag.parse import _HEADING_RE


@pytest.mark.parametrize("line", [
    "Điều 113. Nghỉ hằng năm",
    "Điều 5. Đối tượng không chịu thuế",
    "Chương I",
    "Mục 2. CHẾ ĐỘ THAI SẢN",
    "1.1 Phạm vi",
])
def test_heading_that_van_duoc_nhan(line):
    assert _HEADING_RE.match(line), f"{line!r} phải là heading"


@pytest.mark.parametrize("line", [
    "Điều 11 của Luật này quy định.",
    "Điều 133 của Bộ luật này.",
    "Điều 14 của Luật này;",
    "Điều 20 của Luật này được giải quyết thông qua một trong những cơ quan sau đây:",
    "Điều 228 của Bộ luật này.",
    "Điều ước quốc tế mà Cộng hòa xã hội chủ nghĩa Việt Nam là thành viên.",
])
def test_tham_chieu_giua_cau_khong_phai_heading(line):
    assert not _HEADING_RE.match(line), f"{line!r} KHÔNG được là heading"
