"""Mục 21 — không để chữ `state` của Odoo lọt ra người dùng."""
import re
from pathlib import Path

import pytest

from src.erp_query.state_labels import _THEO_MODEL, nhan_trang_thai

SRC = Path(__file__).resolve().parents[2] / "src" / "erp_query"


def test_cung_ma_state_khac_nghia_theo_model():
    """Lý do bảng tra theo (model, state) chứ không chỉ theo state.

    Nếu ai đó rút gọn thành một bảng phẳng, ca này đỏ."""
    assert nhan_trang_thai("mrp.production", "done") == "hoàn tất"
    assert nhan_trang_thai("stock.picking", "done") == "đã giao"
    assert nhan_trang_thai("sale.order", "done") == "đã khóa"


def test_ma_la_thi_TRA_NGUYEN_khong_nuot():
    """Mã lạ hiện ra thô còn hơn bị nuốt thành chuỗi rỗng — nó là tín hiệu để
    bổ sung bảng. Nuốt thì không ai biết bảng đã thiếu."""
    assert nhan_trang_thai("sale.order", "trang_thai_moi") == "trang_thai_moi"
    assert nhan_trang_thai("model.la", "draft") == "nháp"     # rơi về bảng chung
    assert nhan_trang_thai("sale.order", None) == ""


def test_moi_model_deu_dich_duoc_draft_va_cancel():
    for model, bang in _THEO_MODEL.items():
        assert bang.get("draft") == "nháp", model
        assert bang.get("cancel") == "đã hủy", model


@pytest.mark.parametrize("ten_tep", ["sales.py", "purchase.py", "inventory.py",
                                     "accounting.py", "mrp.py"])
def test_khong_module_nao_noi_state_TRAN_vao_chuoi_nguoi_dung_doc(ten_tep):
    """Rào chống trôi, chiều quan trọng nhất.

    Đo sống 2026-08-23: hỏi "5 đơn bán gần nhất kèm trạng thái" ⇒ trợ lý trả
    `draft` và `sale`. Bốn miền trả chữ Odoo thô trong khi `mrp.py` đã có bảng
    nhãn từ trước — tức khuôn đúng đã tồn tại và không ai áp sang.

    Ca này bắt đúng hình dạng đã gây lỗi: nội suy thẳng `r['state']` (hoặc
    `inv['state']`, `p['state']`…) vào một f-string. So khớp trên văn bản
    nguồn vì hành vi thật cần Odoo, mà bộ mặc định không có Odoo.
    """
    src = (SRC / ten_tep).read_text(encoding="utf-8")
    xau = []
    for i, dong in enumerate(src.splitlines(), 1):
        if not dong.lstrip().startswith(("f\"", "f'", "\"", "'")) and "f\"" not in dong:
            continue
        # nội suy state TRẦN: {...['state']} không nằm trong nhan_trang_thai(...)
        for m in re.finditer(r"\{[^{}]*\['state'\][^{}]*\}", dong):
            if "nhan_trang_thai" not in m.group(0):
                xau.append(f"{ten_tep}:{i}: {m.group(0)}")
    assert not xau, (
        "chữ `state` của Odoo nội suy TRẦN vào chuỗi người dùng đọc — bọc qua "
        f"nhan_trang_thai(model, ...):\n  " + "\n  ".join(xau))
