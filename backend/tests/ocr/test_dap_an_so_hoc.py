"""Cổng số học trên ĐÁP ÁN — canh chính bộ đáp án mà cổng bảng tin tuyệt đối.

ĐỌC KỸ MỘT DÒNG NÀY: tệp này kiểm **đáp án**, KHÔNG kiểm đường OCR. Nó không
đọc ảnh, không gọi tesseract (`kiem_so_hoc.py` chỉ import `json` và `sys`), nên
nó **KHÔNG phát hiện được hồi quy PSM/DPI/parser**. Xanh ở đây không nói gì về
chất lượng đọc — đừng đọc nó như bằng chứng về tầng OCR.

Vì sao tồn tại: `test_table_gate_scan.py` lát 1 tin tuyệt đối vào bảy tệp JSON
trong `tests/fixtures/ocr_bang_that/`, mà kiểm tự động duy nhất hôm nay là
`assert d["trang_thai"] == "DA_DUYET"`. Sửa một con số trong fixture là cách rẻ
nhất để lát 1 xanh, và cám dỗ đó lớn nhất đúng lúc đang có cổng đỏ.

`kiem_so_hoc.py` chạy được như CLI từ 2026-09-06 nhưng chưa test nào gọi nó, nên
nó chưa bao giờ chặn được gì. Commit này nối nó vào suite.
"""
import importlib.util
import json
import os

import pytest

_THU_MUC = os.path.join(os.path.dirname(__file__), "..", "fixtures",
                        "ocr_bang_that")
DAP_AN = sorted(
    os.path.join(_THU_MUC, f"SCID_2026H1_tr{n}.json") for n in range(12, 19))

# Số ràng buộc đo được 2026-09-06: 41 ràng buộc số học × 2 cột giá trị + 3 liên
# báo cáo = 85. Assert sàn này theo lệ `assert total >= 100` / `assert tong >=
# 1000` của các cổng khác: một cổng đo ÍT ĐI thì phải đỏ, không được âm thầm
# xanh vì fixture bị xoá bớt ràng buộc.
TOI_THIEU_RANG_BUOC = 85


def _nap_kiem_so_hoc():
    """`tests/fixtures/ocr_bang_that/` không có `__init__.py` nên nạp theo đường
    dẫn tệp, không import theo tên gói."""
    duong = os.path.join(_THU_MUC, "kiem_so_hoc.py")
    spec = importlib.util.spec_from_file_location("kiem_so_hoc", duong)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(not all(os.path.isfile(p) for p in DAP_AN),
                    reason="thiếu bộ đáp án ocr_bang_that")
def test_dap_an_thoa_moi_rang_buoc_so_hoc():
    ks = _nap_kiem_so_hoc()

    toan_cuc = {}
    for duong in DAP_AN:
        d = json.load(open(duong, encoding="utf-8"))
        for h in d["hang"]:
            if h.get("ma_so"):
                toan_cuc[(d.get("nhom"), h["ma_so"])] = h

    tong_rang_buoc = 0
    loi = []
    for duong in DAP_AN:
        d = json.load(open(duong, encoding="utf-8"))
        loi += ks.kiem(duong, toan_cuc)
        n_lbc, loi_lbc = ks.kiem_lien_bao_cao(duong, toan_cuc)
        loi += loi_lbc
        tong_rang_buoc += len(d["rang_buoc_so_hoc"]) * len(ks.cot_gia_tri(d))
        tong_rang_buoc += n_lbc

    print(f"\n[dap an so hoc] {tong_rang_buoc - len(loi)}/{tong_rang_buoc} "
          f"rang buoc THOA tren {len(DAP_AN)} trang")
    assert tong_rang_buoc >= TOI_THIEU_RANG_BUOC, (
        f"chỉ còn {tong_rang_buoc} ràng buộc (< {TOI_THIEU_RANG_BUOC}) — "
        f"bộ đáp án đang đo ÍT ĐI so với lúc duyệt")
    assert not loi, f"{len(loi)} ràng buộc không thoả: {loi[:3]}"
