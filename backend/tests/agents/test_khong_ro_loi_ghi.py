"""Tầng điều phối ghi không được nội suy exception vào tin nhắn trả về.

Miễn trừ có chủ ý: skill_manifest.py raise SkillManifestError(f"...{e}") là
fail-loud lúc NẠP CẤU HÌNH, hướng tới lập trình viên, không đi ra người dùng.
Miễn trừ ghi tường minh ở đây chứ không im lặng bỏ qua.

RO_LOI/quet_file dùng chung từ tests.leak_scan (Ruling D, task-3) — không
khai báo lại ở đây."""
from pathlib import Path

from tests.leak_scan import RO_LOI, quet_file

AGENTS_DIR = Path(__file__).resolve().parents[2] / "src" / "agents"
SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

MIEN_TRU = {
    "skill_manifest.py": "raise SkillManifestError lúc nạp SKILL.md — "
                         "fail-loud cho lập trình viên, không ra người dùng",
}


def _cho_ro(path: Path):
    if path.name in MIEN_TRU:
        return []
    return quet_file(path)


def test_khong_coordinator_nao_ro_exception():
    ro = [m for p in sorted(AGENTS_DIR.glob("*.py")) for m in _cho_ro(p)]
    ro += [m for p in sorted(SKILLS_DIR.rglob("*.py")) for m in _cho_ro(p)]
    assert ro == [], "còn rò exception ra người dùng:\n" + "\n".join(ro)


def test_mien_tru_van_con_that(monkeypatch):
    """Đối chứng cho danh sách miễn trừ: nếu skill_manifest.py hết chỗ khớp
    thì miễn trừ đã thành rác và phải gỡ, không để nó âm thầm che file khác
    trùng tên về sau."""
    src = (AGENTS_DIR / "skill_manifest.py").read_text(encoding="utf-8")
    assert RO_LOI.search(src), \
        "skill_manifest.py không còn chỗ nào khớp — gỡ khỏi MIEN_TRU"


def test_fail_write_sach_va_co_log(monkeypatch):
    """Câu trả về phải sạch, VÀ nguyên văn lỗi phải tới logger — không chỉ
    "có gọi", mà phải MANG nguyên văn (Ruling G). Chỉ kiểm `da_log` khác rỗng
    thì vẫn xanh dù detail rỗng/thiếu — nửa vệt kiểm toán mà fail_write hứa sẽ
    không được đo."""
    from src.agents import create_order as co

    da_log = []
    monkeypatch.setattr(co.logger, "exception", lambda *a, **k: da_log.append(a))

    exc = ValueError("Youdoo AI / Read Only")
    res = co.fail_write("tao_don", "Lỗi khi tạo đơn — thao tác chưa được "
                                   "thực hiện.", exc)
    noi_dung = res["messages"][-1].content

    assert "Youdoo AI" not in noi_dung
    assert "ValueError" not in noi_dung
    assert da_log, "không ghi log — bản sửa chỉ giấu lỗi đi"
    # logger.exception("%s thất bại: %s: %s", where, type(exc).__name__, exc)
    # — exc (đối tượng exception) là đối số cuối trong tuple positional args
    # đã bắt được. Chỉ "có gọi" thôi không đủ: phải kiểm nguyên văn lỗi thật
    # sự có mặt, không thì detail rỗng/thiếu vẫn qua được assert trên.
    assert "Youdoo AI / Read Only" in str(da_log[0][-1]), \
        "logger có được gọi nhưng KHÔNG mang nguyên văn lỗi — nửa vệt " \
        "kiểm toán này vô giá trị"
