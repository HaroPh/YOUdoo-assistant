# backend/tests/evals/test_sample_hard_sections.py
"""Lấy mẫu tất định — spec 2026-09-18 §4. Phần thuần không cần DB; ca cuối
là `integration` chạy build_sample() trên corpus thật."""
import pytest

from evals import sample_hard_sections as shs


def test_seed_ghi_trong_spec():
    assert shs.SEED == 20260918


def test_is_junk_quoc_hieu_va_tu_loai_van_ban_tran():
    assert shs.is_junk("luat-doanhnghiep.pdf", "QUỐC HỘI")
    assert shs.is_junk("luat-doanhnghiep.pdf", "QUỐC HỘI › CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
    assert shs.is_junk("luat-doanhnghiep.pdf", "LUẬT")
    assert shs.is_junk("boluat-laodong.pdf", "BỘ LUẬT")
    assert shs.is_junk("x.pdf", "Độc lập - Tự do - Hạnh phúc")


def test_is_junk_la_ngan_duoi_3_token():
    assert shs.is_junk("x.pdf", "Chương I › Điều 5.")      # {dieu} → 1 token
    assert not shs.is_junk("x.pdf", "Chương I › Điều 5. Chính sách về đầu tư kinh doanh")


def test_is_junk_bao_cao_tai_chinh_va_rong():
    assert shs.is_junk("SID_000000016657191_01VI_BaoCaoTaiChinhBanNien_HopNhat_SoatXet_2026_signed_05092026111802.pdf",
                       "Chương trình › 39 BIẾT KP")
    assert shs.is_junk("x.pdf", "")


def test_is_junk_khong_loai_muc_that():
    assert not shs.is_junk("luat-doanhnghiep.pdf",
                           "Chương I › NHỮNG QUY ĐỊNH CHUNG › Điều 4. Giải thích từ ngữ")


def test_allocate_theo_ti_le_phan_du_lon_nhat_san_1():
    # Ước tính spec §4.2 — phải ra đúng bảng đó.
    counts = {"danssu": 708, "thuongmai": 335, "laodong": 225, "doanhnghiep": 221,
              "quanlythue": 159, "bhxh": 147, "dautu": 65, "xnk": 27, "gtgt": 22}
    got = shs.allocate(counts, 38)
    assert got == {"danssu": 14, "thuongmai": 7, "laodong": 4, "doanhnghiep": 4,
                   "quanlythue": 3, "bhxh": 3, "dautu": 1, "xnk": 1, "gtgt": 1}
    assert sum(got.values()) == 38


def test_allocate_tong_dung_k_va_khong_duoi_san():
    got = shs.allocate({"a": 1000, "b": 1, "c": 1}, 5)
    assert sum(got.values()) == 5 and min(got.values()) >= 1


def test_allocate_nem_loi_khi_k_nho_hon_so_tang_nhan_san():
    # 4 tầng, sàn 1 → cần ít nhất 4 suất; k=2 thì không cách chia nào giữ sàn.
    with pytest.raises(ValueError):
        shs.allocate({"a": 1, "b": 1, "c": 1, "d": 1}, 2)


def test_allocate_rem_am_khong_keo_tang_nao_duoi_san():
    # Sàn đẩy tổng lên 7 (2+2+1+1+1) trong khi k=6 → rem=-1, vòng lặp phải
    # bớt ở tầng CÒN TRÊN sàn, không được kéo tầng nào xuống dưới 1.
    got = shs.allocate({"a": 500, "b": 500, "c": 1, "d": 1, "e": 1}, 6)
    assert sum(got.values()) == 6
    assert min(got.values()) >= 1


def test_stride_pick_tat_dinh_khong_trung_va_tang_dan():
    items = list(range(100))
    a = shs.stride_pick(items, 7, 20260918); b = shs.stride_pick(items, 7, 20260918)
    assert a == b and len(set(a)) == 7 and a == sorted(a)
    assert all(0 <= x < 100 for x in a)


def test_stride_pick_theo_cong_thuc_spec():
    # N=100, k=4: step=25; offset=(918/1000)*25=22.95 → [22, 47, 72, 97]
    assert shs.stride_pick(list(range(100)), 4, 20260918) == [22, 47, 72, 97]


def test_stride_pick_k_lon_hon_N_lay_het():
    assert shs.stride_pick([1, 2, 3], 5, 1) == [1, 2, 3]


def test_stride_pick_doi_seed_doi_ket_qua():
    items = list(range(100))
    assert shs.stride_pick(items, 4, 20260918) != shs.stride_pick(items, 4, 20260500)


@pytest.mark.integration
def test_build_sample_tren_corpus_that_ra_45_nut_hop_le():
    from src.rag import db as _db
    conn = _db.connect()
    try:
        sample = shs.build_sample(conn)
    finally:
        conn.close()
    nodes = sample["nodes"]
    assert len(nodes) == shs.N_TOTAL, sample["allocation"]
    bases = [n["basename"] for n in nodes]
    # Đo 2026-09-18: policy.docx đã bị 64 ca cũ gán nhãn 5/5 mục → 0 nút; 6 tệp kia 1 ca.
    for b in shs.BUSINESS_DOCS:
        assert bases.count(b) == (1 if sample["pool_after_filter"].get(b, 0) > 0 else 0), b
    n_business = sum(bases.count(b) for b in shs.BUSINESS_DOCS)
    assert n_business == 6
    assert sum(bases.count(b) for b in shs.LAW_DOCS) == shs.N_TOTAL - n_business
    assert all(not shs.is_junk(n["basename"], n["section_path"]) for n in nodes)
    assert all(n["chunk_text"].strip() for n in nodes)
    assert len({(n["basename"], n["section_path"]) for n in nodes}) == 45
