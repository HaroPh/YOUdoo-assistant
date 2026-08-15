"""Lưới cuối: KHÔNG cây nguồn nào được nội suy exception ra người dùng.

Quét theo LOẠI TRỪ, không theo liệt kê. Liệt kê thư mục nguồn chính là cơ
chế đã khiến nợ gốc chỉ đếm 21/89 chỗ — người viết liệt kê đúng những thư
mục mình đang nghĩ tới. Loại trừ thì cây nguồn mới tự động được phủ.

Hai lưới, bổ sung cho nhau (Ruling I) — xem docstring tests/leak_scan.py
cho lý do đầy đủ, tóm tắt ở đây để đọc tại chỗ:
  - RO_LOI/quet_file (regex) — bắt {e}/{exc}/{err} bất kể biến đó đến từ
    đâu (except-binding hay không). Bắt được mcp-servers/odoo/helpers.py,
    nơi biến là THAM SỐ hàm chứ không phải except-binding — AST không thấy.
  - quet_ast_file (AST) — bắt MỌI tên except-binding, không chỉ e/exc/err.
    Task 4 từng để lọt `except Exception as ex:` vì regex không biết tên
    `ex`; đây là lưới đóng đúng lỗ đó mà KHÔNG cần liệt kê thêm tên (thêm
    tên vào regex sẽ lặp lại chính lỗi thiết kế mà file này tồn tại để sửa).
Xoá một trong hai là mất một lớp phủ thật — không phải trùng lặp để dọn.

Phép thử phá bắt buộc (chạy tay khi sửa file này): thêm lại một chỗ rò vào
MỖI tầng trong bốn tầng — mcp-servers/odoo/tools/, backend/src/erp_query/,
backend/src/agents/, backend/skills/ — lưới phải ĐỎ ở cả bốn (Bước 1-4 kết
quả trong task-6-report.md). Thêm một phép thử phá thứ năm riêng cho AST:
tên biến regex không thấy được (vd `ex`) phải làm lưới AST đỏ trong khi
regex vẫn im lặng — bằng chứng thực nghiệm cho Ruling I."""
from pathlib import Path

from tests.leak_scan import quet_ast_file, quet_file

GOC = Path(__file__).resolve().parents[3]

# Nhỏ và ổn định. Mọi thứ KHÔNG nằm ở đây đều bị quét — kể cả cây nguồn chưa
# tồn tại lúc viết dòng này.
BO_QUA_THU_MUC = {
    ".git", ".venv", "__pycache__", "node_modules",
    ".worktrees", ".claude", ".superpowers",
    "docs", "logs", "migrations",
    "tests",      # test được phép nhắc {e} trong chuỗi kỳ vọng
    "spikes",     # mã thử nghiệm, không phục vụ người dùng
}

# Miễn trừ theo từng file — nhưng khoá bằng SỐ LƯỢNG, không phải bằng tên,
# và MỖI LƯỚI có cột riêng (regex, ast) vì hai lưới nhìn khác nhau.
#
# Miễn trừ cả file là đúng cái bẫy nó đi đóng: thêm một chỗ rò MỚI vào file
# đã được miễn trừ thì lưới im lặng. Ghim số dòng khớp mong đợi cho TỪNG
# lưới ⇒ chỗ rò thứ n+1 (ở lưới nào) làm lưới đó ĐỎ dù file nằm trong danh
# sách này — hai chiều: ít hơn ghim cũng đỏ (miễn trừ đã thành rác).
#
# Năm trong sáu hướng tới lập trình viên / người vận hành, không tới người
# dùng chat. File thứ sáu (helpers.py) là Ruling K — xem lý do riêng ở đó.
# Đo 2026-08-15.
MIEN_TRU = {
    "backend/src/agents/skill_manifest.py": (
        2, 2, "raise SkillManifestError lúc nạp SKILL.md — fail-loud cho lập "
              "trình viên, app không lên chứ không lên sai"),
    "backend/src/rag/embed.py": (
        1, 1, "raise EmbeddingError — lỗi hạ tầng lúc index, không ra người dùng"),
    "backend/evals/role_config.py": (
        1, 1, "RuntimeError nói rõ bộ đo thiếu biến môi trường nào — người chạy "
              "eval bằng CLI đọc, không phải người dùng chat"),
    "backend/evals/run_eval.py": (
        1, 1, "print('INFRA ERROR: …') ra console của người chạy eval"),
    "backend/jobs/resilience.py": (
        1, 1, "raise … from e trong job nền — đi vào log, không vào hội thoại"),
    "scripts/check_role_odoo_consistency.py": (
        1, 1, "script rà quyền chạy tay; nguyên văn lỗi Odoo CHÍNH LÀ kết quả "
              "cần đọc của nó"),
    # Ruling K (controller, 2026-08-15): dòng khớp nằm TRONG chính fail() —
    # cơ chế nhánh này dựng ra để giữ lỗi thô khỏi văn bản người dùng, xây
    # chuỗi detail cho logger tiến trình + bảng vệt kiểm toán, không bao giờ
    # tới người dùng. Plan gốc không biết vì fail() chưa tồn tại lúc viết
    # plan. `exc` ở đây là THAM SỐ của fail(tool_name, display, exc), không
    # phải except-binding — regex thấy (đúng vai trò của nó), AST không
    # thấy (đúng phạm vi của nó, xem docstring quet_ast_file).
    "mcp-servers/odoo/helpers.py": (
        1, 0, "dòng khớp nằm trong fail() — dựng detail cho logger tiến "
              "trình + vệt kiểm toán, không bao giờ ra người dùng "
              "(Ruling K, task-6)"),
}


def _moi_file_nguon():
    for path in GOC.rglob("*.py"):
        if any(phan in BO_QUA_THU_MUC for phan in path.relative_to(GOC).parts):
            continue
        yield path


def _khoa(path: Path) -> str:
    return path.relative_to(GOC).as_posix()


def test_khong_cay_nguon_nao_ro_exception():
    ro = []
    for path in sorted(_moi_file_nguon()):
        khoa = _khoa(path)
        if khoa in MIEN_TRU:
            continue
        ro.extend(quet_file(path, nhan=khoa))
        ro.extend(quet_ast_file(path, nhan=khoa))
    assert ro == [], "còn rò exception ra người dùng:\n" + "\n".join(ro)


def test_luoi_that_su_quet_du_bon_tang():
    """Đối chứng cho chính bộ lọc: nếu BO_QUA_THU_MUC nuốt nhầm một cây
    nguồn, test trên xanh giả mà không ai biết. Khẳng định cả bốn tầng đều
    thật sự có file được quét."""
    da_quet = {_khoa(p) for p in _moi_file_nguon()}
    for tien_to in ("mcp-servers/odoo/tools/",
                    "backend/src/erp_query/",
                    "backend/src/agents/",
                    "backend/skills/"):
        assert any(k.startswith(tien_to) for k in da_quet), \
            f"không file nào dưới {tien_to} được quét — bộ lọc nuốt nhầm"


def test_moi_mien_tru_dung_so_luong():
    """Khoá danh sách miễn trừ theo SỐ LƯỢNG, hai chiều, MỖI LƯỚI một cột.

    Ít hơn mong đợi ⇒ miễn trừ đã thành rác, gỡ đi (để nó nằm lại là dựng
    sẵn chỗ núp cho một chỗ rò mới trong cùng file).
    Nhiều hơn ⇒ có chỗ rò MỚI trong file được miễn trừ — đúng lỗ hổng mà
    miễn trừ-cả-file gây ra, và là lý do test này đếm thay vì chỉ kiểm tồn
    tại. Đếm riêng cho từng lưới vì regex và AST nhìn khác nhau (Ruling I)
    — gộp một cột sẽ để một lưới trôi im lặng dưới bóng lưới kia.
    """
    lech = []
    for khoa, (mong_doi_regex, mong_doi_ast, ly_do) in MIEN_TRU.items():
        path = GOC / khoa
        if not path.exists():
            lech.append(f"{khoa}: file không còn tồn tại")
            continue
        that_regex = len(quet_file(path))
        that_ast = len(quet_ast_file(path))
        if that_regex != mong_doi_regex:
            lech.append(f"{khoa}: regex khớp {that_regex} dòng, "
                        f"ghim {mong_doi_regex} ({ly_do})")
        if that_ast != mong_doi_ast:
            lech.append(f"{khoa}: AST khớp {that_ast} chỗ, "
                        f"ghim {mong_doi_ast} ({ly_do})")
    assert lech == [], "miễn trừ lệch thực tế:\n" + "\n".join(lech)
