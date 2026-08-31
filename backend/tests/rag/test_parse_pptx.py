# backend/tests/rag/test_parse_pptx.py
"""Parser slide — spec 2026-08-29 mục 5.1.

Fixture tự dựng, đáp án chắc 100% (spec mục 6.1 tầng 1). Chưa có tệp .pptx
thật trong kho test; khi có thì thêm một test `live` đọc nó.
"""
import pytest

# KHÔNG dùng `pytest.importorskip("pptx")`. Đo được 2026-08-31: gỡ
# `python-pptx` khỏi môi trường thì TOÀN BỘ tính năng `.pptx` chết
# (`parse_pptx` ném ModuleNotFoundError từ trong ruột `_ingest_file`, sập
# trọn lượt nạp) mà suite VẪN XANH — 88 passed, mã thoát 0. Đó đúng nguyên
# văn cách reranker của dự án chết âm thầm 6 tuần vì một dependency thiếu mà
# bốn lớp test đều che. Thiếu dep thì test phải ĐỎ.
import pptx  # noqa: F401

from src.rag.parse import parse_pptx, _pptx_shape_blocks


def _make_deck(path):
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[1])
    s1.shapes.title.text = "Quy trình bán hàng"
    s1.placeholders[1].text = "Bước 1: tiếp nhận yêu cầu\nBước 2: báo giá"
    s1.notes_slide.notes_text_frame.text = "Nhấn mạnh thời hạn báo giá 24 giờ."

    s2 = prs.slides.add_slide(prs.slide_layouts[5])
    s2.shapes.title.text = "Định mức chiết khấu"
    tbl = s2.shapes.add_table(3, 2, Inches(1), Inches(2),
                              Inches(6), Inches(2)).table
    tbl.cell(0, 0).text = "Sản lượng"; tbl.cell(0, 1).text = "Chiết khấu"
    tbl.cell(1, 0).text = "dưới 100";  tbl.cell(1, 1).text = "5%"
    tbl.cell(2, 0).text = "từ 100";    tbl.cell(2, 1).text = "10%"
    prs.save(path)


def test_tieu_de_slide_thanh_heading(tmp_path):
    p = str(tmp_path / "deck.pptx"); _make_deck(p)
    blocks = parse_pptx(p)
    heads = [b["text"] for b in blocks if b["heading_level"]]
    assert "Quy trình bán hàng" in heads
    assert "Định mức chiết khấu" in heads


def test_so_slide_duoc_ghi_vao_page(tmp_path):
    p = str(tmp_path / "deck.pptx"); _make_deck(p)
    blocks = parse_pptx(p)
    assert {b["page"] for b in blocks} == {1, 2}


def test_bang_giu_duoc_rang_buoc_hang(tmp_path):
    """Lỗi 4 của spec là số bị tách khỏi nhãn của nó. Bảng trong slide phải
    ra một dòng một hàng, cột ngăn bằng dấu sổ đứng — như `parse_docx`."""
    p = str(tmp_path / "deck.pptx"); _make_deck(p)
    text = "\n".join(b["text"] for b in parse_pptx(p))
    assert "dưới 100 | 5%" in text
    assert "từ 100 | 10%" in text
    assert "Sản lượng | Chiết khấu" in text


def test_ghi_chu_thuyet_trinh_duoc_giu(tmp_path):
    p = str(tmp_path / "deck.pptx"); _make_deck(p)
    text = "\n".join(b["text"] for b in parse_pptx(p))
    assert "24 giờ" in text


def test_slide_rong_khong_sinh_block_rac(tmp_path):
    from pptx import Presentation
    p = str(tmp_path / "trong.pptx")
    prs = Presentation(); prs.slides.add_slide(prs.slide_layouts[6]); prs.save(p)
    assert parse_pptx(p) == []


def test_bang_trong_group_shape_khong_bi_bo_sot(tmp_path):
    """Vòng sửa 1 (reviewer). Group shape của PowerPoint có `has_table=False`
    và `has_text_frame=False` ở chính nó — bảng/textbox thật nằm trong
    `shape.shapes`. Không mở group ra thì cả hai biến mất im lặng, dù slide
    vẫn có tiêu đề nên báo cáo nạp vẫn "thành công"."""
    from pptx import Presentation
    from pptx.util import Inches

    p = str(tmp_path / "group.pptx")
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    table_shape = slide.shapes.add_table(3, 2, Inches(1), Inches(1), Inches(4), Inches(2))
    tbl = table_shape.table
    tbl.cell(0, 0).text = "Sản lượng"; tbl.cell(0, 1).text = "Chiết khấu"
    tbl.cell(1, 0).text = "dưới 100";  tbl.cell(1, 1).text = "5%"
    tbl.cell(2, 0).text = "từ 100";    tbl.cell(2, 1).text = "10%"

    textbox = slide.shapes.add_textbox(Inches(1), Inches(4), Inches(4), Inches(1))
    textbox.text_frame.text = "Ghi chú nằm trong group"

    slide.shapes.add_group_shape([table_shape, textbox])
    prs.save(p)

    text = "\n".join(b["text"] for b in parse_pptx(p))
    assert "dưới 100 | 5%" in text
    assert "Ghi chú nằm trong group" in text


def test_group_long_nhieu_tang_van_lay_duoc(tmp_path):
    """Bắt lỗi 'chỉ mở một tầng': group chứa group, textbox mang chuỗi nhận
    dạng riêng nằm ở tầng trong cùng. Đệ quy đúng thì xanh; mở một tầng rồi
    dừng thì đỏ."""
    from pptx import Presentation
    from pptx.util import Inches

    p = str(tmp_path / "nested_group.pptx")
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    marker = "CHUOI_NHAN_DANG_RIENG_LONG_SAU_HAI_TANG_GROUP"
    inner_textbox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    inner_textbox.text_frame.text = marker
    inner_group = slide.shapes.add_group_shape([inner_textbox])

    other_textbox = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(4), Inches(1))
    other_textbox.text_frame.text = "shape khác ở tầng ngoài"
    slide.shapes.add_group_shape([inner_group, other_textbox])
    prs.save(p)

    text = "\n".join(b["text"] for b in parse_pptx(p))
    assert marker in text


def _shape_la_khong_nhan_dang_duoc(slide, tmp_path, ten_tep):
    """Dựng một `<p:sp>` mà `Shape.shape_type` NÉM NotImplementedError.

    python-pptx quyết loại shape theo thứ tự: placeholder → custGeom →
    prstGeom (auto shape) → cờ `txBox` (text box) → NÉM. Gỡ `prstGeom` và cờ
    `txBox` khỏi một textbox hợp lệ thì không nhánh nào khớp. Đây KHÔNG phải
    ca bịa: công cụ ngoài PowerPoint sinh ra đúng loại shape này, kể cả
    LibreOffice — tức chính cầu chuyển đổi `.ppt → .pptx` của nhánh này.
    """
    from pptx.util import Inches
    tb = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(4), Inches(1))
    tb.text_frame.text = "Nội dung của shape lạ"
    spPr = tb._element.spPr
    for child in list(spPr):
        if child.tag.endswith("}prstGeom"):
            spPr.remove(child)
    nv = tb._element.nvSpPr.cNvSpPr
    nv.attrib.pop("txBox", None)
    return tb


def test_shape_type_nem_NotImplementedError_thi_parse_pptx_KHONG_SAP(tmp_path):
    """C2(a) review toàn nhánh 2026-08-31.

    `Shape.shape_type` ném `NotImplementedError` với shape do công cụ ngoài
    PowerPoint sinh. Không ai bắt loại lỗi đó nên nó sập TRỌN `ingest_path` và
    mất báo cáo của mọi tệp đã xử lý trước đó. Parser phải đọc `shape_type`
    phòng thủ, và các block khác của slide vẫn phải ra đủ."""
    from pptx import Presentation

    p = str(tmp_path / "shape_la.pptx")
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Slide có shape lạ"
    _shape_la_khong_nhan_dang_duoc(slide, tmp_path, p)
    prs.save(p)

    # Tiền đề của test: shape ĐÚNG LÀ loại ném lỗi sau khi lưu và nạp lại.
    reloaded = Presentation(p)
    la = [sh for sh in reloaded.slides[0].shapes if sh.name.startswith("TextBox")]
    assert la, "không dựng được shape lạ"
    with pytest.raises(NotImplementedError):
        _ = la[0].shape_type

    blocks = parse_pptx(p)                     # KHÔNG được ném
    text = "\n".join(b["text"] for b in blocks)
    assert "Slide có shape lạ" in text          # block khác của slide vẫn còn
    assert "Nội dung của shape lạ" in text      # và chữ trong shape lạ cũng lấy được


class _ShapeKhongNhanDangDuoc:
    """Đứng thay một GraphicFrame chứa SmartArt.

    Sự thật của python-pptx: `GraphicFrame.shape_type` trả **None** (không
    ném) khi graphicData không phải table/chart/OLE — SmartArt rơi đúng vào
    đó. Nó cũng có `has_table=False` và `has_text_frame=False`, nên vòng lặp
    cũ bỏ qua nó KHÔNG MỘT LỜI NÀO: y hệt lỗi group shape, chỉ khác loại
    shape. Dùng vật giả vì python-pptx KHÔNG dựng được SmartArt để làm
    fixture thật."""
    shape_type = None
    has_table = False
    has_text_frame = False
    name = "Diagram 3"
    element = None


def test_shape_khong_nhan_dang_duoc_KHONG_bien_mat_im_lang():
    """C2(b): SmartArt phải để lại dấu vết QUAN SÁT ĐƯỢC.

    Parser chưa đọc được part sơ đồ của SmartArt — chấp nhận được. Điều KHÔNG
    chấp nhận được là nó biến mất mà báo cáo nạp vẫn "thành công"."""
    blocks = _pptx_shape_blocks(_ShapeKhongNhanDangDuoc(), page=4, title_shape=None)
    assert blocks, "shape không nhận ra mà không sinh block nào = MẤT IM LẶNG"
    assert "Diagram 3" in blocks[0]["text"]
    assert blocks[0]["page"] == 4
