"""Không cấu hình nào của Youdoo được trỏ sang cổng DB của D:\Project.

Bối cảnh đo 2026-08-23: hai dự án chạy trên CÙNG máy dev, mỗi bên một
container postgres riêng — nhưng **cùng tên database** `ai_assistant`:

    D:\Project   container `postgres`          host 5433   3 300 rag_chunks
    D:\Youdoo    container `youdoo-postgres`   host 5434   3 151 rag_chunks

Giá trị mặc định của `DATABASE_URL` trong hai tệp nguồn từng trỏ vào **5433**.
Thiếu biến môi trường ⇒ Youdoo lặng lẽ nói chuyện với corpus của dự án kia.
Thứ DUY NHẤT chặn lại là mật khẩu `changeme` sai — một lớp bảo vệ TÌNH CỜ:
đặt hai mật khẩu giống nhau một ngày nào đó là mất luôn nó.

Volume của hai container hoàn toàn tách biệt
(`youdoo_youdoo_postgres_data` vs `project_postgres_data`), nên đây là rủi ro
CẤU HÌNH, không phải rủi ro hạ tầng — và cấu hình thì test gác được.
"""
import re
from pathlib import Path

import pytest

GOC = Path(__file__).resolve().parents[1]
CONG_ANH_EM = "5433"

# Nơi được phép nhắc 5433: tài liệu giải thích vì sao tránh nó.
CHO_PHEP = {"docker-compose.yml"}


def _tep_nguon():
    for thu_muc in ("src", "jobs", "evals"):
        yield from (GOC / thu_muc).rglob("*.py")


@pytest.mark.parametrize("p", sorted(_tep_nguon()), ids=lambda p: p.name)
def test_khong_tep_nguon_nao_MAC_DINH_ve_cong_5433(p):
    """Nhắc 5433 trong CHÚ THÍCH thì được (giải thích vì sao tránh); dùng nó
    trong một chuỗi DSN thì không."""
    xau = []
    for i, dong in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if CONG_ANH_EM not in dong:
            continue
        if dong.lstrip().startswith("#"):
            continue
        if re.search(r"postgres(ql)?://[^\"']*:" + CONG_ANH_EM, dong):
            xau.append(f"{p.name}:{i}: {dong.strip()}")
    assert not xau, (
        "DSN trỏ sang cổng 5433 — đó là postgres của D:\Project, cùng tên "
        f"database `ai_assistant`:\n  " + "\n  ".join(xau))


def test_ca_doi_chung_regex_that_su_bat_duoc():
    """Nếu regex không bắt được gì thì ca trên xanh vô nghĩa."""
    mau = 'X = os.environ.get("DATABASE_URL", "postgresql://admin:x@localhost:5433/ai_assistant")'
    assert re.search(r"postgres(ql)?://[^\"']*:" + CONG_ANH_EM, mau)
    assert not re.search(r"postgres(ql)?://[^\"']*:" + CONG_ANH_EM,
                         'X = "postgresql://admin:x@localhost:5434/ai_assistant"')
