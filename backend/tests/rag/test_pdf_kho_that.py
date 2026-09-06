"""Nghiệm thu B4 (PDF bóc bảng) trên corpus PDF THẬT tại d:/Youdoo/tmp-docs.

Không phải test đơn vị với đáp án tay — đây là các phép TỰ KIỂM (số học,
checksum, không lẫn số) chạy trên tài liệu thật, đúng khuôn Tầng C spec gốc
§6. Xem docs/superpowers/specs/2026-08-31-tang-nap-tai-lieu-ghi-chu-thuc-thi.md
mục "B4" cho số liệu đo thật + diễn giải.
"""
import os
import re

import pytest

from src.rag.parse import parse_pdf
from src.rag.chunking import chunk_text_blocks

KHO = "d:/Youdoo/tmp-docs"
pytestmark = pytest.mark.live


def _hoa_don():
    if not os.path.isdir(KHO):
        return []
    return sorted(f for f in os.listdir(KHO) if f.startswith("invoice_") and f.endswith(".pdf"))


@pytest.mark.skipif(not _hoa_don(), reason="chưa có tmp-docs")
def test_hoa_don_tu_kiem_so_hoc_khong_chunk_nao_lan_hang_khac():
    """Số lượng × đơn giá = thành tiền — tự kiểm được không cần đáp án tay
    (đúng khuôn Tầng C spec gốc §6). Kiểm bằng cách đọc lại 3 con số TỪ
    CÙNG MỘT chunk-hàng: nếu bảng bị gắn số sang hàng bên cạnh, phép nhân
    sẽ KHÔNG khớp."""
    sai = []
    for ten in _hoa_don():
        blocks, _ = parse_pdf(os.path.join(KHO, ten))
        chunks = chunk_text_blocks(blocks, doc_id=ten, source_file=ten)
        for c in chunks:
            t = c["chunk_text"]
            m_sl = re.search(r"Qty:\s*([\d.,]+)", t)
            m_gia = re.search(r"Net Price:\s*([\d.,]+)", t)
            m_tien = re.search(r"Net Worth:\s*([\d.,]+)", t)
            if not (m_sl and m_gia and m_tien):
                continue
            sl = float(m_sl.group(1).replace(",", ""))
            gia = float(m_gia.group(1).replace(",", ""))
            tien = float(m_tien.group(1).replace(",", ""))
            if abs(sl * gia - tien) > 0.5:
                sai.append((ten, t))
    assert sai == [], f"{len(sai)} hàng tự kiểm sai: {sai[:5]}"


@pytest.mark.skipif(not os.path.isdir(KHO), reason="chưa có tmp-docs")
def test_ssc_bieumau_checksum_khong_dut_doan():
    _, warnings = parse_pdf(os.path.join(KHO, "ssc_bieumau.pdf"))
    dut_doan = [w for w in warnings if "đứt đoạn" in w[1]]
    assert dut_doan == [], f"checksum đứt đoạn không mong đợi: {dut_doan}"


@pytest.mark.skipif(not os.path.isdir(KHO), reason="chưa có tmp-docs")
def test_ssc_bieumau_do_hang_trung_lap_qua_trang(capsys):
    """Không phải test gate cứng — ĐO giới hạn đã biết + chấp nhận của B4:
    pdfplumber.find_tables() dò bảng RIÊNG trên TỪNG TRANG nên một bảng đánh
    số phân cấp trải nhiều trang có thể để hàng cuối trang N trùng hàng đầu
    trang N+1 (biến thể LẶP của cùng giới hạn "vỡ trang" — spec §3.4 đã chấp
    nhận biến thể MẤT hàng). Không vá trong B4; chỉ đo và ghi số thật."""
    blocks, _ = parse_pdf(os.path.join(KHO, "ssc_bieumau.pdf"))
    texts = [b["text"] for b in blocks if b.get("atomic")]
    trung = [t for t in set(texts) if texts.count(t) > 1]
    print(f"\n[B4] {len(trung)} hàng bảng TRÙNG LẶP trong ssc_bieumau.pdf: {trung[:3]}")


@pytest.mark.skipif(not os.path.isdir(KHO), reason="chưa có tmp-docs")
def test_bctc_khong_chunk_nao_lan_ma_cot_dau_hang_khac():
    blocks, _ = parse_pdf(os.path.join(KHO, "bieumau_bctc_hopnhat.pdf"))
    chunks = chunk_text_blocks(blocks, doc_id="bctc", source_file="bctc.pdf")
    ma_dau_re = re.compile(r"^[^:]+:\s*([^|]+)")
    # CHỈ tính là "hàng bảng" khi có " | " — dấu phân cách CỘT THẬT mà
    # row_to_text() luôn dùng (pdf_table.py). Đo lần đầu dùng thêm điều kiện
    # OR ": " theo đúng mẫu brief, nhưng đó bắt luôn văn xuôi thường (đoạn
    # "Ghi chú: (1)...", các đoạn "Nguyên tắc kế toán...") vì bất kỳ câu nào
    # có dấu hai chấm cũng khớp — lỗi THƯỚC ĐO, không phải bug, đã sửa.
    hang_bang = [c for c in chunks
                if " | " in c["chunk_text"]
                and ma_dau_re.match(c["chunk_text"])]
    # Mỗi chunk-hàng tự đủ nghĩa: đúng MỘT giá trị cột đầu, không phải danh
    # sách nhiều giá trị (dấu hiệu lẫn hàng nếu ô đầu chứa nhiều số/mã cách
    # nhau bởi khoảng trắng kép hoặc dấu phẩy nối). Loại BỎ số TRONG NGOẶC
    # trước đếm — các hàng TỔNG CỘNG hợp lệ có công thức tham chiếu như
    # "(280 = 100 + 200)" trong nhãn; chúng không phải "lẫn hàng khác" mà là
    # cấu trúc tài chính chuẩn Việt Nam.
    lan = [c["chunk_text"] for c in hang_bang
          if len(re.findall(r"\d[\d.,]{2,}",
                            re.sub(r"\([^)]*\)", "",
                                   ma_dau_re.match(c["chunk_text"]).group(1)))) > 1]
    assert lan == [], f"{len(lan)} chunk nghi lẫn số hàng khác: {lan[:5]}"


# ── Fix wave sau review toàn nhánh (2026-09-04): Critical #1 ─────────────────
KHO_LUAT = "d:/Documents"
LUAT_THUE = os.path.join(KHO_LUAT, "luat-thuexuatnhapkhau.pdf")
_MUC_THUE_RE = re.compile(r"\b\d{1,3}\s*-\s*\d{1,3}\b")


@pytest.mark.skipif(not os.path.isfile(LUAT_THUE), reason="chưa có kho luật")
def test_luat_thue_khong_mat_cot_khung_thue_suat():
    """B4 KHÔNG được làm mất cột "Khung thuế suất" của biểu thuế (trang 12-25).

    Thước đo TỰ ĐỐI CHIẾU: đếm số dòng mang mẫu mức thuế suất ("0-10",
    "15-25") ở `pypdf` thô — đường xử lý CŨ, trước B4 — rồi so với số dòng
    tương ứng trong output của `parse_pdf`. Không chốt cứng con số tuyệt đối
    (nó phụ thuộc phiên bản pypdf/pdfplumber), chốt TỈ LỆ GIỮ LẠI.

    Đo thật 2026-09-04: pypdf thô 247 dòng; B4 trước fix 14 (5.7% — cột thứ 4
    gần như biến mất vì `_trich_mot_bang` dò lại bảng trong chính bbox của nó
    và ra lưới 2 cột nghèo hơn); sau fix 240 (97.2%). Ngưỡng 0.80 nằm giữa
    hai chế độ đó với biên rộng cả hai phía — phần thiếu còn lại là hàng vắt
    trang ở trang 14/24/25, giới hạn "vỡ trang" spec §3.4 đã chấp nhận."""
    import pypdf
    reader = pypdf.PdfReader(LUAT_THUE)
    goc = 0
    for i in range(11, 25):
        for dong in (reader.pages[i].extract_text() or "").splitlines():
            if _MUC_THUE_RE.search(dong):
                goc += 1
    assert goc > 100, f"thước đo hỏng: pypdf thô chỉ thấy {goc} dòng mức thuế"

    blocks, _ = parse_pdf(LUAT_THUE)
    con_lai = sum(1 for b in blocks
                  if b.get("page") and 12 <= b["page"] <= 25
                  and _MUC_THUE_RE.search(b["text"]))
    assert con_lai / goc >= 0.80, (
        f"mất phần lớn mức thuế suất: {con_lai}/{goc} = {con_lai / goc:.1%} "
        "(cột 'Khung thuế suất' bị rơi khỏi lưới bảng?)")


@pytest.mark.skipif(not os.path.isfile(LUAT_THUE), reason="chưa có kho luật")
def test_luat_thue_co_canh_bao_bat_dong_so_cot():
    """Bỏ chế độ `text` là một QUYẾT ĐỊNH MẤT DỮ LIỆU TIỀM TÀNG (hàng vắt
    trang chỉ chế độ text thấy) — phải LỚN TIẾNG, không im lặng."""
    _, warnings = parse_pdf(LUAT_THUE)
    bat_dong = [w for w in warnings if "bất đồng số cột" in w[1]]
    assert bat_dong, "không có cảnh báo nào dù đã bỏ chế độ text trên 13 trang"
