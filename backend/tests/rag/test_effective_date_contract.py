# backend/tests/rag/test_effective_date_contract.py
"""Ngày hiệu lực trong DB thật ↔ corpus thật.

Vì sao cần một test CHẠM DB chứ không chỉ unit test regex: unit test chứng
minh regex đọc được một chuỗi cho sẵn, nó KHÔNG chứng minh chuỗi đó sống sót
qua parse + chunk + ghi DB. Đúng khoảng cách đó từng để reranker chết im lặng
6 tuần với bốn lớp test xanh.

Bản thân bộ số dưới đây là lý do thứ hai: ước lượng ban đầu của tôi là 8/9 và
nó SAI. Phép đo đầu tìm mục mang tên "Hiệu lực thi hành", nên bỏ sót
luat-doanhnghiep.pdf (đặt tên mục là "Điều khoản thi hành") dù câu cần tìm nằm
ngay trong đó. Chỉ khi ingest thật rồi đọc DB mới lòi ra 9/9.
"""
import os

import pytest

from src.rag import db as _db

# Đối chiếu thủ công 2026-08-20: cả 9 khớp đều là câu "Luật này/Bộ luật này có
# hiệu lực thi hành từ ngày ..." nằm trong điều khoản thi hành cuối văn bản,
# không có ca nào bắt nhầm sang hiệu lực của HỢP ĐỒNG.
EXPECTED_LAWS = {
    "boluat-danssu.pdf": "2017-01-01",
    "boluat-laodong.pdf": "2021-01-01",
    "boluat-thuongmai.pdf": "2006-01-01",
    "luat-baohiemxahoi.pdf": "2025-07-01",
    "luat-dautu.pdf": "2026-03-01",
    "luat-doanhnghiep.pdf": "2021-01-01",
    "luat-quanlythue.pdf": "2020-07-01",
    "luat-thuegtgt.pdf": "2025-07-01",
    "luat-thuexuatnhapkhau.pdf": "2016-09-01",
}


def _dates_by_basename():
    conn = _db.connect()
    try:
        rows = conn.execute(
            "SELECT source_file, effective_date FROM rag_documents").fetchall()
    finally:
        conn.close()
    return {os.path.basename(f.replace("\\", "/")): (d.isoformat() if d else None)
            for f, d in rows}


@pytest.mark.integration
def test_moi_pdf_luat_co_dung_ngay_hieu_luc():
    """Chốt cứng TỪNG ngày, không chỉ đếm.

    Chỉ đếm "9 tệp có ngày" thì một cú regress đọc nhầm sang ngày hiệu lực của
    HỢP ĐỒNG vẫn cho đủ 9 và test vẫn xanh — bản đầu của regex mắc đúng lỗi đó
    trên 8/9 tệp."""
    actual = _dates_by_basename()
    wrong = {name: {"cho_doi": want, "thuc_te": actual.get(name)}
             for name, want in EXPECTED_LAWS.items() if actual.get(name) != want}
    assert not wrong, f"ngày hiệu lực sai/thiếu: {wrong}"


@pytest.mark.integration
def test_tai_lieu_nghiep_vu_de_null():
    """Nửa còn lại của hợp đồng: cái gì phải NULL thì phải NULL.

    Không có test này thì một lần nới regex làm mọi tài liệu bỗng có ngày vẫn
    đi lọt, vì test trên chỉ nhìn 9 tệp luật."""
    actual = _dates_by_basename()
    dinh_ngay = {name: d for name, d in actual.items()
                 if name not in EXPECTED_LAWS and d is not None}
    assert not dinh_ngay, (
        f"tài liệu không phải văn bản quy phạm mà có ngày hiệu lực: {dinh_ngay}")


@pytest.mark.integration
def test_khong_co_pdf_luat_nao_bi_bo_sot():
    """Corpus mọc thêm một PDF luật mà không ai cập nhật bảng trên → đỏ.

    Đây là cái chốt chống trôi: nếu chỉ có hai test trên, thêm luật thứ 10 vào
    corpus sẽ đi qua im lặng và không ai đo ngày của nó bao giờ."""
    actual = _dates_by_basename()
    conn = _db.connect()
    try:
        rows = conn.execute("SELECT source_file FROM rag_documents").fetchall()
    finally:
        conn.close()
    luat = {os.path.basename(f.replace("\\", "/")) for (f,) in rows
            if "/law/" in f.replace("\\", "/")}
    assert luat == set(EXPECTED_LAWS), (
        f"thừa/thiếu so với bảng chốt: thừa={luat - set(EXPECTED_LAWS)}, "
        f"thiếu={set(EXPECTED_LAWS) - luat}; actual={actual}")
