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
