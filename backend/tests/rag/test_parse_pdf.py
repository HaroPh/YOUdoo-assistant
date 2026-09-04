class _FakePlumberPage:
    """Giả trang `pdfplumber` KHÔNG có bảng nào — `find_tables()` rỗng."""
    def find_tables(self, table_settings=None):
        return []


class _FakePlumberPDF:
    def __init__(self, n_pages):
        self.pages = [_FakePlumberPage() for _ in range(n_pages)]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _khong_bang(monkeypatch, n_pages=1):
    """Monkeypatch `pdfplumber.open` để MỌI trang báo 'không có bảng' — dùng
    cho các test hiện có, vốn chỉ kiểm logic heading/furniture trên pypdf,
    không liên quan gì tới bảng."""
    import pdfplumber
    monkeypatch.setattr(pdfplumber, "open",
                        lambda path: _FakePlumberPDF(n_pages))


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
    _khong_bang(monkeypatch)

    blocks, warnings = parse.parse_pdf("irrelevant.pdf")

    assert warnings == []
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
    _khong_bang(monkeypatch)
    blocks, warnings = parse.parse_pdf("x.pdf")
    assert warnings == []
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
    _khong_bang(monkeypatch)
    blocks, warnings = parse.parse_pdf("x.pdf")
    assert warnings == []
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
    _khong_bang(monkeypatch)
    blocks, warnings = parse.parse_pdf("x.pdf")
    assert warnings == []
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


# ── B4: pdfplumber cho trang có bảng (spec 2026-09-04-b4-pdf-bang) ───────────
import os

KHO = "d:/Youdoo/tmp-docs"


@pytest.mark.live
@pytest.mark.skipif(not os.path.isdir(KHO), reason="chưa có tmp-docs")
def test_parse_pdf_bang_that_moi_hang_la_mot_block_atomic():
    from src.rag.parse import parse_pdf
    blocks, warnings = parse_pdf(os.path.join(KHO, "ssc_bieumau.pdf"))
    bang_blocks = [b for b in blocks if b.get("atomic")]
    assert bang_blocks, "phải có ít nhất 1 block bảng atomic"
    # Mỗi block bảng tự mang tên cột — không phải chỉ số/giá trị trần.
    assert any(":" in b["text"] for b in bang_blocks)
    assert all(b["heading_level"] is None for b in bang_blocks)
    # Đo thật 2026-09-04 (find_tables() từng trang, xem ghi chú thực thi):
    # trang 1 có bảng TT đếm 1..4 liên mạch; trang 2-8 có bảng khác đánh số
    # PHÂN CẤP ("1", "1.1", "1.2"...) — cột đầu KHÔNG toàn chữ số thuần nên
    # checksum_gap() không áp dụng (im lặng đúng, không phải lỗ hổng). CẢ
    # HAI trường hợp đã đo đều không sinh cảnh báo, nên warnings==[] đúng
    # với 2 file mẫu đã đo — nếu implementer đo ra khác, SỬA assertion theo
    # số thật, đừng ép về [] cho khớp dòng này.
    #
    # CẬP NHẬT 2026-09-04 (fix wave sau review toàn nhánh), làm đúng lời dặn
    # trên: file này giờ sinh 3 cảnh báo LOẠI MỚI "bất đồng số cột" (6 vs 4,
    # trang 1-3) — cảnh báo CỐ Ý của Critical #1, không phải hồi quy. Ý định
    # gốc của dòng assert là "không có cảnh báo CHECKSUM", nên thu hẹp đúng
    # vào đó thay vì nới lỏng thành assert rỗng.
    assert [w for w in warnings if "đứt đoạn" in w[1]] == []
    assert all("bất đồng số cột" in w[1] for w in warnings), warnings


class _FakeBangToanTrang:
    """Một 'bảng' giả có bbox = TOÀN TRANG, không hàng nào — đủ để buộc
    parse_pdf rẽ sang nhánh 'trang có bảng', không cần mô phỏng đúng cấu
    trúc bảng thật (đã kiểm bằng file thật ở Step 5)."""
    def __init__(self, w, h):
        self.bbox = (0, 0, w, h)

    def extract(self):
        return []


class _FakePlumberPageCoBang:
    width, height = 100, 100

    def find_tables(self, table_settings=None):
        # Chế độ mặc định (table_settings=None) thấy 1 bảng phủ hết trang;
        # chế độ text không thấy gì — không cần khớp nhau cho test này.
        return [_FakeBangToanTrang(self.width, self.height)] if table_settings is None else []

    def within_bbox(self, bbox, relative=False):
        return self

    def extract_text(self):
        return ""


class _FakePlumberPDFCoBang:
    def __init__(self):
        self.pages = [_FakePlumberPageCoBang()]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_trang_co_bang_phu_het_thi_dong_van_xuoi_pypdf_bien_mat(monkeypatch):
    import pypdf
    import pdfplumber
    from src.rag import parse
    fake = _FakeReader(["Điều 1. Nội dung không liên quan bảng."])
    monkeypatch.setattr(pypdf, "PdfReader", lambda path: fake)
    monkeypatch.setattr(pdfplumber, "open", lambda path: _FakePlumberPDFCoBang())

    blocks, _ = parse.parse_pdf("x.pdf")
    van_xuoi = [b for b in blocks if not b.get("atomic")]
    assert van_xuoi == [], (
        "trang có bảng phủ hết trang vẫn còn dòng văn xuôi từ pypdf — "
        "gate 'chỉ chạm trang có bảng' không có tác dụng đo được")


# ── Fix review: detect_page_furniture không được lệch bởi tài liệu HỖN HỢP ───
# Finding (Important, controller xác nhận thật): trước fix, `pages` truyền vào
# detect_page_furniture() dùng dải-text pdfplumber cho trang có bảng nhưng
# pypdf cho trang không bảng — hai đường tách dòng khác nhau đủ để một dòng
# furniture thật (header/footer lặp lại) bị đếm lệch tần suất/vị-trí-rìa, đổi
# TẬP FURNITURE CỦA CẢ TÀI LIỆU, kể cả ảnh hưởng tới trang KHÔNG bảng — dù bản
# thân trang đó không đổi gì trong đường trích của chính nó. Test `_khong_bang`
# (toàn tài liệu 0 bảng) không bắt được vì nó không bao giờ tạo `pages` KHÔNG
# ĐỒNG NHẤT. Test này dựng đúng tình huống đó: tài liệu vừa có trang bảng vừa
# có trang văn xuôi thuần (dạng bieumau_bctc_hopnhat.pdf).
class _FakeBangNho:
    """Bảng giả NHỎ, bbox chỉ chiếm dải trên cùng trang (không phủ hết) — mô
    phỏng trang bảng THẬT trong tài liệu hỗn hợp, khác _FakeBangToanTrang."""
    def __init__(self, bbox):
        self.bbox = bbox

    def extract(self):
        return []


class _FakePlumberPageHonHop:
    """Trang giả CÓ bảng nhỏ ở đầu trang — dải-text (dùng để BUILD BLOCK) chỉ
    trả dòng nội dung, CHỦ Ý không mang dòng furniture, mô phỏng đúng lệch trích
    giữa pypdf và pdfplumber đã gây ra finding: nếu detect_page_furniture nhận
    nhầm dải-text này thay vì pypdf toàn trang, dòng furniture sẽ KHÔNG được
    đếm trên các trang này, tụt dưới ngưỡng page_ratio và mất tác dụng lọc
    trên CẢ các trang không bảng."""
    width, height = 100, 100

    def __init__(self, dong_noi_dung):
        self._dong_noi_dung = dong_noi_dung
        self._bang = _FakeBangNho((10, 0, 90, 20))  # dải bảng: y 0..20

    def find_tables(self, table_settings=None):
        return [self._bang] if table_settings is None else []

    def within_bbox(self, bbox, relative=False):
        return self

    def extract_text(self):
        # Dùng chung cho MỌI within_bbox() (kể cả bbox của chính bảng khi
        # _trich_mot_bang gọi) lẫn dải y=20..100 khi parse_pdf dựng dai_lines
        # — chỉ dải DƯỚI bảng (y>20) mới sinh ra dòng khác rỗng trong thực tế
        # (dải TRÊN bảng, y=0..0, bị loại vì y1>y0 sai ở parse_pdf), nên fake
        # đơn giản hoá: luôn trả về ĐÚNG nội dung không-furniture.
        return self._dong_noi_dung


class _FakePlumberPDFHonHop:
    def __init__(self, plumber_pages):
        self.pages = plumber_pages

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_trang_khong_bang_van_duoc_loc_furniture_dung_trong_tai_lieu_hon_hop(monkeypatch):
    import pypdf
    import pdfplumber
    from src.rag import parse

    FURNITURE = "CONFIDENTIAL - Internal Use Only"
    # QUAN TRỌNG: nội dung mỗi trang phải khác nhau ở CHỮ, không chỉ ở CHỮ SỐ —
    # _normalize_digits() gộp "Điều 1. ..." và "Điều 2. ..." thành cùng một
    # khoá "Điều #. ..." nếu chỉ số khác nhau, khiến chính nội dung thân bài
    # cũng bị hiểu nhầm là furniture (giả dương tính riêng của fixture, không
    # phải lỗi cần test ở đây) — dùng câu khác hẳn nhau cho mỗi trang.
    NOI_DUNG = {
        1: "Nội dung mở đầu của trang một.",
        2: "Thông tin chi tiết trang hai.",
        3: "Đoạn văn kết thúc trang ba.",
        4: "Diễn giải số liệu trang bốn.",
        5: "Ghi chú bổ sung trang năm.",
        6: "Kết luận cuối trang sáu.",
    }
    n_pages = 6
    # Trang 1-3: KHÔNG bảng. Trang 4-6: CÓ bảng nhỏ ở đầu trang.
    pypdf_texts = [f"{FURNITURE}\n{NOI_DUNG[i]}" for i in range(1, n_pages + 1)]
    fake_reader = _FakeReader(pypdf_texts)
    plumber_pages = (
        [_FakePlumberPage() for _ in range(3)]
        + [_FakePlumberPageHonHop(NOI_DUNG[i]) for i in range(4, n_pages + 1)])
    monkeypatch.setattr(pypdf, "PdfReader", lambda path: fake_reader)
    monkeypatch.setattr(pdfplumber, "open",
                        lambda path: _FakePlumberPDFHonHop(plumber_pages))

    blocks, _ = parse.parse_pdf("hon_hop.pdf")

    khong_bang_texts = [b["text"] for b in blocks if b["page"] in (1, 2, 3)]
    assert FURNITURE not in khong_bang_texts, (
        "dòng furniture lặp lại vẫn còn trong output của trang KHÔNG bảng — "
        "tập furniture bị trang CÓ bảng trong cùng tài liệu làm lệch "
        "(detect_page_furniture nhận nhầm đầu vào dải-text thay vì pypdf "
        "toàn trang cho trang có bảng)")
    # Sanity: nội dung thật của các trang không bảng vẫn còn nguyên, không bị
    # lọc oan theo furniture.
    assert NOI_DUNG[1] in khong_bang_texts
    assert NOI_DUNG[2] in khong_bang_texts
    assert NOI_DUNG[3] in khong_bang_texts


# ── Fix wave sau review toàn nhánh (2026-09-04) ──────────────────────────────


class _FakeBangCoLuoi:
    """Bảng giả TRẢ VỀ LƯỚI THẬT qua `extract()` — khác _FakeBang* ở trên
    (chúng trả [] vì chỉ cần buộc parse_pdf rẽ nhánh). Dùng để kiểm nội dung
    block do `_khoi_bang` phát ra."""
    def __init__(self, rows, bbox=(0, 0, 100, 100)):
        self.bbox = bbox
        self._rows = rows

    def extract(self):
        return self._rows


class _FakeTrangChoKhoiBang:
    """`within_bbox()` trả về chính nó; chế độ `text` KHÔNG dò được bảng nào
    (mô phỏng bảng có đường kẻ rõ, chỉ chế độ mặc định thấy)."""
    width, height = 100, 100

    def __init__(self, bang_text=None):
        self._bang_text = bang_text

    def within_bbox(self, bbox, relative=False):
        return self

    def find_tables(self, table_settings=None):
        if table_settings is None:
            return []
        return [self._bang_text] if self._bang_text is not None else []

    def extract_text(self):
        return ""


def test_khoi_bang_bo_qua_hang_khong_mang_gia_tri_nao():
    """Important #3: hàng mà MỌI ô đều rỗng chỉ dựng được khung "Cột X:" —
    không phát block. Hàng có ít nhất một giá trị VẪN phát bình thường."""
    from src.rag import parse
    rows = [
        ["TT", "Chỉ tiêu", "Mã số"],      # header
        ["1", "Tiền mặt", "111"],          # thân, có giá trị
        [None, "", "   "],                 # thân, RỖNG hoàn toàn
        ["2", "Tiền gửi", "112"],          # thân, có giá trị
    ]
    page = _FakeTrangChoKhoiBang()
    blocks, warnings = parse._khoi_bang(page, _FakeBangCoLuoi(rows), 7)
    assert len(blocks) == 2, f"phải bỏ đúng hàng rỗng, còn: {[b['text'] for b in blocks]}"
    assert all("Tiền" in b["text"] for b in blocks)
    assert all(b["atomic"] and b["page"] == 7 for b in blocks)


def test_khoi_bang_lech_so_cot_thi_bo_che_do_text_va_canh_bao():
    """Critical #1: chế độ mặc định 4 cột, chế độ `text` 2 cột → bỏ hẳn chế độ
    `text`, giữ đủ 4 cột, và PHẢI có cảnh báo (hỏng lớn tiếng còn hơn thiếu
    âm thầm)."""
    from src.rag import parse
    mac_dinh = [["STT", "Nhóm hàng", "Mô tả", "Khung thuế suất"],
                ["1", "03.03", "Cá, đông lạnh", "0-10"],
                ["2", "03.04", "Phi-lê cá", "15-25"]]
    theo_text = _FakeBangCoLuoi([["03.03", "Cá, đông lạnh"],
                                 ["03.04", "Phi-lê cá"],
                                 ["03.05", "Cá khô"]])
    page = _FakeTrangChoKhoiBang(bang_text=theo_text)
    blocks, warnings = parse._khoi_bang(page, _FakeBangCoLuoi(mac_dinh), 13)
    assert [w for w in warnings if "bất đồng số cột" in w[1]], warnings
    assert any("0-10" in b["text"] for b in blocks), (
        f"mức thuế suất ở cột 4 biến mất: {[b['text'] for b in blocks]}")
    assert any("15-25" in b["text"] for b in blocks)


def test_khoi_bang_khop_so_cot_thi_van_gop_hai_che_do():
    """Phép thử phá cho cổng trên: KHỚP số cột thì hàng thừa của chế độ `text`
    (hàng vắt trang mà chế độ mặc định làm mất) VẪN phải được gộp vào — cổng
    chống lệch cột không được biến thành cổng chặn luôn chế độ `text`."""
    from src.rag import parse
    mac_dinh = [["STT", "Mã", "Thuế"], ["1", "03.03", "0-10"], ["3", "03.05", "5-20"]]
    theo_text = _FakeBangCoLuoi([["1", "03.03", "0-10"],
                                 ["2", "03.04", "10-15"],
                                 ["3", "03.05", "5-20"]])
    page = _FakeTrangChoKhoiBang(bang_text=theo_text)
    blocks, warnings = parse._khoi_bang(page, _FakeBangCoLuoi(mac_dinh), 4)
    assert [w for w in warnings if "bất đồng số cột" in w[1]] == []
    assert any("10-15" in b["text"] for b in blocks), (
        f"hàng chỉ chế độ text thấy đã bị mất: {[b['text'] for b in blocks]}")
