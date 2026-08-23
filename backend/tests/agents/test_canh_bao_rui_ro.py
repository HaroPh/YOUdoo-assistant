"""Mục 21 — cảnh báo rủi ro TRƯỚC khi xác nhận (thay cho Undo)."""
import re
from pathlib import Path

import pytest

from src.agents.prompts import (RUI_RO_CUA_TOOL, WRITE_CONFIRM_SUFFIX,
                                canh_bao_rui_ro)
from src.agents.write_registry import COORDINATED_TOOLS

SRC = Path(__file__).resolve().parents[2] / "src" / "agents"


def test_tool_an_toan_KHONG_co_canh_bao():
    """Quan trọng ngang các ca dưới: cảnh báo mọi thứ thì chẳng còn gì là cảnh
    báo — người dùng sẽ học cách lướt qua cả những dòng thật sự quan trọng."""
    for tool in ("create_quotation", "create_rfq", "create_lead", "create_bom",
                 "create_manufacturing_order", "log_activity"):
        assert canh_bao_rui_ro(tool) == "", tool
    assert canh_bao_rui_ro(None) == ""
    assert canh_bao_rui_ro("tool_khong_ton_tai") == ""


def test_tool_rui_ro_CO_canh_bao_va_co_dau_hieu_nhin_thay():
    got = canh_bao_rui_ro("post_invoice")
    assert "⚠️" in got
    assert "credit memo" in got
    assert got.startswith("\n") and got.endswith("\n"), (
        "phải kèm sẵn xuống dòng để chỗ gọi không phải nhớ định dạng")


@pytest.mark.parametrize("tool", sorted(RUI_RO_CUA_TOOL))
def test_moi_canh_bao_deu_NOI_HAU_QUA_chu_khong_chi_canh_bao_suong(tool):
    """Một dòng "thao tác này rủi ro" không giúp gì. Người dùng cần biết CHUYỆN
    GÌ xảy ra và nếu lỡ thì làm sao — đó là toàn bộ lý do chọn hướng này thay
    vì Undo thật."""
    loi = RUI_RO_CUA_TOOL[tool]
    assert len(loi) > 40, f"{tool}: cảnh báo quá ngắn để nói được hậu quả"
    # So KHÔNG phân biệt hoa thường: "Không hoàn tác được" (K hoa, phần sau
    # thường) là cách viết hợp lệ, và bản đầu của test này đỏ vì nó liệt kê
    # "KHÔNG"/"không" mà quên dạng đó — test cứng, không phải cảnh báo sai.
    thap = loi.lower()
    dau_hieu = ("không", "phải ", "muốn")
    assert any(d in thap for d in dau_hieu), (
        f"{tool}: cảnh báo không nói hậu quả hay cách xử lý: {loi!r}")


@pytest.mark.parametrize("tool", sorted(RUI_RO_CUA_TOOL))
def test_moi_tool_rui_ro_deu_TOI_DUOC_mot_cong_xac_nhan(tool):
    """Rào chống trôi — chiều dễ hỏng nhất.

    Viết bảng cảnh báo mà quên nối vào chỗ dựng câu xác nhận thì cảnh báo
    KHÔNG BAO GIỜ hiện ra, và không có gì đỏ. Đây đúng lớp lỗi "khai báo một
    đằng, hành vi một nẻo" mà repo này gặp nhiều lần.

    Tool có coordinator riêng ⇒ tệp coordinator đó phải gọi canh_bao_rui_ro.
    Tool KHÔNG có coordinator ⇒ đi qua cổng planner ở nodes.py, chỗ đó gọi
    canh_bao_rui_ro(plan.get("tool")) nên phủ mọi tool cùng lúc.
    """
    if tool not in COORDINATED_TOOLS:
        src = (SRC / "nodes.py").read_text(encoding="utf-8")
        assert 'canh_bao_rui_ro(plan.get("tool"))' in src, (
            f"{tool} đi qua cổng planner nhưng cổng đó không gọi canh_bao_rui_ro")
        return
    # có coordinator: phải có MỘT tệp nào đó vừa nhắc tên tool vừa gọi hàm
    ung_vien = []
    for f in SRC.glob("*_write.py"):
        src = f.read_text(encoding="utf-8")
        if "canh_bao_rui_ro" in src and (tool in src or "cfg.tool_name" in src):
            ung_vien.append(f.name)
    assert ung_vien, (
        f"{tool} có coordinator riêng nhưng không tệp *_write.py nào vừa gọi "
        "canh_bao_rui_ro vừa nhắc tới nó — cảnh báo sẽ không bao giờ hiện ra")


def test_canh_bao_dung_TRUOC_cau_chot():
    """Sau câu chốt thì người dùng đã đọc xong và gõ "có" rồi."""
    for f in ("inventory_write.py", "returns_write.py", "mail_write.py",
              "invoice_write.py", "nodes.py"):
        src = (SRC / f).read_text(encoding="utf-8")
        for m in re.finditer(r"canh_bao_rui_ro\([^)]*\)", src):
            sau = src[m.end():m.end() + 400]
            assert "WRITE_CONFIRM_SUFFIX" in sau, (
                f"{f}: canh_bao_rui_ro không nằm trước WRITE_CONFIRM_SUFFIX")
