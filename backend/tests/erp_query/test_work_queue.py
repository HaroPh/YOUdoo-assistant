"""Bản tin việc cần xử lý — quét nhiều hàng đợi, gom số đếm.

Lớp lỗi nguy hiểm nhất của tính năng này: một hàng đợi HỎNG trông giống hệt
một hàng đợi RỖNG nếu chỉ đọc data rồi len(). Lúc đó bản tin nói "không có
việc" trong khi sự thật là "không hỏi được" — đúng con bug tính năng này sinh
ra để diệt, tái sinh bên trong chính nó. Mọi test dưới đây xoay quanh chỗ đó."""
import pytest

from src.agents import roles as roles_mod
from src.erp_query import work_queue


def _ok(data):
    return {"status": "success", "data": data, "display": "x"}


def _loi():
    return {"status": "error", "data": None, "display": "hỏng", "error": "hỏng"}


@pytest.fixture
def gia_hang_doi(monkeypatch):
    """Thay cả 5 hàm hàng đợi bằng bản giả.

    ⚠️ TRẢ VỀ CHÍNH dict mà work_queue đọc, không phải một bản sao. Test sửa
    `gia_hang_doi["x"] = ...` là sửa thẳng vào đó. Nếu fixture trả về một dict
    cục bộ thì mọi test sửa hàng đợi sẽ XANH GIẢ — chúng đo bản sao chứ không
    đo thứ hàm thật đọc.
    """
    ban = {
        "list_my_activities": _ok({"rows": []}),
        "list_late_deliveries": _ok({"rows": [1] * 15, "count": 29}),
        "get_overdue_invoices": _ok({"rows": [1] * 22, "count": 22}),
        "list_reorder_needed": _ok({"rows": [1, 1], "count": 2}),
        "list_po_mismatches": _ok({"rows": [], "count": 0}),
    }
    monkeypatch.setattr(work_queue, "_FAKE_QUEUES", ban)
    return work_queue._FAKE_QUEUES


def test_fixture_that_su_lai_duoc_hang_doi(gia_hang_doi):
    """Đối chứng cho chính fixture: sửa qua nó phải đổi được kết quả. Không có
    test này thì một fixture trả bản sao sẽ làm mọi test hàng-đợi-hỏng xanh
    giả mà không ai biết."""
    gia_hang_doi["list_reorder_needed"] = _ok({"rows": [], "count": 0})
    res = work_queue.list_pending_work()
    so = {c["queue"]: c["count"] for c in res["data"]["checked"]}
    assert so["list_reorder_needed"] == 0


def test_lay_count_chu_khong_phai_len_rows(gia_hang_doi):
    """list_late_deliveries chặn rows ở 15 nhưng count thật là 29. Đếm theo
    len(rows) là báo sai MỘT NỬA ngay ở con số tiêu đề."""
    res = work_queue.list_pending_work()
    so = {c["queue"]: c["count"] for c in res["data"]["checked"]}
    assert so["list_late_deliveries"] == 29, "đếm theo rows thay vì count"


def test_thieu_khoa_count_thi_lui_ve_len_rows(gia_hang_doi):
    """list_my_activities KHÔNG có khoá count — phải lùi về len(rows), không
    được nổ và không được bỏ qua hàng đợi."""
    gia_hang_doi["list_my_activities"] = _ok({"rows": [1, 1, 1]})
    res = work_queue.list_pending_work()
    so = {c["queue"]: c["count"] for c in res["data"]["checked"]}
    assert so["list_my_activities"] == 3


def test_envelope_loi_vao_failed_khong_dem_thanh_0(gia_hang_doi):
    """CA QUAN TRỌNG NHẤT. Hàng đợi trả status=error không được xuất hiện
    trong checked với count=0 — như thế là nói dối rằng đã kiểm và không có
    việc."""
    gia_hang_doi["list_po_mismatches"] = _loi()
    res = work_queue.list_pending_work()
    da_kiem = {c["queue"] for c in res["data"]["checked"]}
    hong = {f["queue"] for f in res["data"]["failed"]}
    assert "list_po_mismatches" not in da_kiem
    assert "list_po_mismatches" in hong


def test_exception_cung_vao_failed(gia_hang_doi, monkeypatch):
    """Hỏng cũng có thể là exception chứ không phải envelope lỗi."""
    def _no(*a, **k):
        raise ValueError("Youdoo AI / Read Only")
    monkeypatch.setitem(work_queue._FAKE_QUEUES, "list_reorder_needed", _no)
    res = work_queue.list_pending_work()
    hong = {f["queue"] for f in res["data"]["failed"]}
    assert "list_reorder_needed" in hong
    assert "Youdoo AI" not in res["display"], "nguyên văn lỗi rò ra người dùng"


def test_mot_hang_doi_hong_khong_giet_ca_ban_tin(gia_hang_doi):
    """Kế toán trục trặc không được che mất 29 phiếu kho trễ."""
    gia_hang_doi["get_overdue_invoices"] = _loi()
    res = work_queue.list_pending_work()
    so = {c["queue"]: c["count"] for c in res["data"]["checked"]}
    assert so["list_late_deliveries"] == 29


def test_tat_ca_rong_van_khong_noi_het_viec(gia_hang_doi):
    """Ràng buộc cứng của spec §4: nói ĐÃ KIỂM GÌ, không nói KHÔNG CÒN GÌ."""
    for ten in gia_hang_doi:
        gia_hang_doi[ten] = _ok({"rows": [], "count": 0})
    res = work_queue.list_pending_work()
    d = res["display"]
    assert "đã kiểm" in d.lower()
    for cam in ("không còn việc", "hết việc", "không có việc nào"):
        assert cam not in d.lower(), f"khẳng định đã quét hết: {cam!r}"


def test_tat_ca_hang_doi_hong_khong_noi_da_kiem_0(gia_hang_doi):
    """Khi tất cả hàng đợi hỏng (checked trống), không nói "Đã kiểm 0 hàng đợi"
    hay "Đã kiểm: ." — chỉ "Không kiểm được" là đủ để nói sự thật."""
    for ten in gia_hang_doi:
        gia_hang_doi[ten] = _loi()
    res = work_queue.list_pending_work()
    d = res["display"]
    assert "đã kiểm 0" not in d.lower()
    assert not d.strip().endswith("Đã kiểm: .")


def test_not_checked_mang_dung_tang_hai(gia_hang_doi):
    """Câu "còn gì nữa không" phải có nguyên liệu tất định để trả lời."""
    res = work_queue.list_pending_work()
    assert set(res["data"]["not_checked"]) == set(work_queue.TIER_TWO)
    assert len(work_queue.TIER_TWO) >= 5


def test_suy_bo_phan_tu_tool_so_huu():
    """Suy ra, KHÔNG khai bảng thứ hai. Ghim kết quả vì nó dựa một phần vào
    giá trị mà roles.py tự nhận là TUỲ TIỆN (log_activity/close_activity =
    "Kho"); nếu đa số đổi chiều, test này phải đỏ để có người xem lại."""
    assert work_queue.dept_for_role("warehouse") == "Kho"
    assert work_queue.dept_for_role("accounting") == "Kế toán"
    assert work_queue.dept_for_role("admin") is None      # unrestricted
    assert work_queue.dept_for_role("khong-ton-tai") is None


def test_viec_dich_danh_luon_dung_dau(gia_hang_doi):
    """Bất kể vai nào — việc giao đích danh không xếp theo bộ phận."""
    for vai in ("warehouse", "accounting", None):
        res = work_queue.list_pending_work(vai)
        assert res["data"]["checked"][0]["queue"] == "list_my_activities"


def test_hang_doi_bo_phan_cua_vai_len_truoc(gia_hang_doi):
    """Sau việc đích danh, hàng đợi thuộc bộ phận của vai đứng trước."""
    kho = [c["queue"] for c in
           work_queue.list_pending_work("warehouse")["data"]["checked"]]
    assert kho[1] == "list_late_deliveries"                 # Kho

    kt = [c["queue"] for c in
          work_queue.list_pending_work("accounting")["data"]["checked"]]
    assert kt[1] == "get_overdue_invoices"                  # Kế toán


def test_vai_khong_ro_bo_phan_giu_thu_tu_khai(gia_hang_doi):
    """admin (unrestricted) không suy ra được bộ phận ⇒ giữ nguyên thứ tự."""
    ad = [c["queue"] for c in
          work_queue.list_pending_work("admin")["data"]["checked"]]
    assert ad == [t[0] for t in work_queue.TIER_ONE]


def test_bang_bo_phan_hang_doi_ghim_hai_chieu():
    """TIER_ONE là nguồn sự thật THỨ HAI (DEPT_OF chỉ phủ tool ghi). Ghim cả
    hai chiều: thiếu dòng nào, hoặc thêm bộ phận lạ, đều phải đỏ."""
    that = {ten: bo_phan for ten, _, bo_phan, _ in work_queue.TIER_ONE}
    assert that == {
        "list_my_activities": None,
        "list_late_deliveries": "Kho",
        "get_overdue_invoices": "Kế toán",
        "list_reorder_needed": "Mua hàng",
        "list_po_mismatches": "Mua hàng",
    }
    hop_le = set(roles_mod.DEPT_OF.values()) | {None}
    assert set(that.values()) <= hop_le, "bộ phận không có trong DEPT_OF"


def test_moi_truong_profile_sai_khong_lam_sap_ban_tin(gia_hang_doi, monkeypatch):
    """load_profile() có thể KeyError nếu YOUDOO_POLICY_PROFILE gõ sai — phải
    trả None (giữ thứ tự khai), không được làm sập cả bản tin."""
    monkeypatch.setenv("YOUDOO_POLICY_PROFILE", "khong-ton-tai")
    assert work_queue.dept_for_role("warehouse") is None
    res = work_queue.list_pending_work("warehouse")
    assert res["status"] == "success"
