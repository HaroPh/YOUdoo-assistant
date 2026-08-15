"""Vệt kiểm toán MCP: bảng phải CÓ THẬT, và thiếu thì phải nổ to.

Bối cảnh: mcp_call_log chưa từng tồn tại trong database Youdoo, và
log_mcp_event nuốt mọi lỗi ghi nên cả cơ chế chết im lặng suốt. Lưới duy
nhất chặn được chuyện đó tái diễn là kiểm lúc khởi động."""
import importlib
import sys
from pathlib import Path

import pytest

MCP_DIR = Path(__file__).resolve().parents[3] / "mcp-servers" / "odoo"


@pytest.fixture(autouse=True)
def _skip_khong_co_mcp():
    if not MCP_DIR.exists():
        pytest.skip("chưa có mcp-servers/odoo")


@pytest.fixture
def event_log_mod():
    sys.path.insert(0, str(MCP_DIR))
    try:
        import event_log
        yield importlib.reload(event_log)
    finally:
        sys.path.remove(str(MCP_DIR))


def test_khong_co_dsn_thi_im_lang(event_log_mod, monkeypatch):
    """Không cấu hình DATABASE_URL = tắt log, là thiết kế có chủ ý của
    event_log. Không được biến nó thành lỗi khởi động."""
    monkeypatch.setattr(event_log_mod, "DATABASE_URL", None)
    event_log_mod.assert_log_table_ready()          # không được ném


def test_co_dsn_ma_thieu_bang_thi_nem(event_log_mod, monkeypatch):
    """Đúng trạng thái thật của hệ thống trước đợt này."""
    class FakeCursor:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a): pass
        def fetchone(self): return (False,)

    class FakeConn:
        def cursor(self): return FakeCursor()

    monkeypatch.setattr(event_log_mod, "DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(event_log_mod, "_get_db", lambda: FakeConn())
    with pytest.raises(RuntimeError, match="002_mcp_call_log.sql"):
        event_log_mod.assert_log_table_ready()


def test_co_dsn_va_co_bang_thi_qua(event_log_mod, monkeypatch):
    """Đối chứng: nếu hàm ném vô điều kiện thì test trên vẫn xanh giả."""
    class FakeCursor:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a): pass
        def fetchone(self): return (True,)

    class FakeConn:
        def cursor(self): return FakeCursor()

    monkeypatch.setattr(event_log_mod, "DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(event_log_mod, "_get_db", lambda: FakeConn())
    event_log_mod.assert_log_table_ready()          # không được ném


def test_server_goi_kiem_bang_va_chi_trong_main():
    """Hai khẳng định, mỗi cái chặn một hướng hỏng khác nhau.

    (1) Gỡ lời gọi khỏi server.py ⇒ ĐỎ. Không có nó thì hàm trên có thể đúng
        hoàn toàn mà chẳng ai gọi.
    (2) Lời gọi phải nằm SAU `if __name__ == "__main__":`. Ở cấp module nó
        làm 8 file test + evals/role_config.py — những chỗ `import server`
        chỉ để đọc registry tool — nổ khi chưa chạy migration, tức đúng
        trạng thái của mọi lần checkout mới."""
    src = (MCP_DIR / "server.py").read_text(encoding="utf-8")
    assert "assert_log_table_ready()" in src

    vi_tri_main = src.index('if __name__ == "__main__":')
    vi_tri_goi = src.index("assert_log_table_ready()")
    assert vi_tri_goi > vi_tri_main, \
        "lời gọi nằm ở cấp module — sẽ làm mọi `import server` nổ khi chưa " \
        "chạy migration"


@pytest.fixture
def verify_mod():
    sys.path.insert(0, str(MCP_DIR))
    try:
        import verify_audit_chain
        yield importlib.reload(verify_audit_chain)
    finally:
        sys.path.remove(str(MCP_DIR))


def test_bang_rong_khong_phai_nguyen_ven(verify_mod):
    """Bảng rỗng là "chưa có gì để kiểm", KHÔNG phải bằng chứng toàn vẹn.
    Trước bản sửa này verify([]) trả (True, "... chuỗi nguyên vẹn") và main()
    thoát 0 — tức công cụ báo OK trên đúng trạng thái hỏng."""
    ok, msg = verify_mod.verify([])
    assert ok is False
    assert "rỗng" in msg or "không có dòng" in msg


@pytest.mark.integration
def test_ghi_roi_doc_lai_duoc(event_log_mod):
    """Test DUY NHẤT chứng minh vòng ghi khép kín: gọi log_mcp_event rồi ĐỌC
    LẠI dòng vừa ghi và tính lại hash.

    Đây chính là thứ đã vắng mặt suốt và là lý do cả cơ chế chết mà không ai
    biết — mọi test khác chỉ khẳng định hàm ĐƯỢC GỌI, không khẳng định có
    dòng nào ra tới database.

    Cần DATABASE_URL thật và migration 002 đã chạy. Chạy riêng:
        pytest tests/mcp/test_audit_log_table.py -m integration
    """
    psycopg2 = pytest.importorskip("psycopg2")

    import audit_chain

    if not event_log_mod.DATABASE_URL:
        pytest.skip("cần DATABASE_URL")

    dau = "test-ghi-doc-lai"
    event_log_mod.log_mcp_event("tool_error", tool_name=dau,
                                error_code="E500", error_message="probe")

    conn = psycopg2.connect(event_log_mod.DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT created_at, event_type, caller, tool_name, model_name,"
                " operation, duration_ms, error_code, error_message,"
                " entry_hash, prev_hash FROM mcp_call_log"
                " WHERE tool_name = %s ORDER BY id DESC LIMIT 1", (dau,))
            row = cur.fetchone()
    finally:
        conn.close()

    assert row is not None, "không có dòng nào ra tới database"
    (created_at, event_type, caller, tool_name, model_name, operation,
     duration_ms, error_code, error_message, entry_hash, prev_hash) = row
    assert error_message == "probe"
    assert audit_chain.compute_entry_hash(
        prev_hash, created_at, event_type, caller, tool_name, model_name,
        operation, duration_ms, error_code, error_message) == entry_hash


def test_import_server_khong_can_bang(monkeypatch):
    """Đối chứng bằng hành vi, không bằng vị trí văn bản: `import server`
    phải chạy được kể cả khi bảng chưa có. Đây là hồi quy thật — 8 file test
    hiện hành phụ thuộc vào nó.

    Giới hạn: nếu `server` đã nằm trong sys.modules do một test KHÁC chạy
    trước import nó rồi, dòng `import server` dưới đây là no-op và test này
    không đo được gì (không tái nhập, không gọi lại code cấp module). Lưới
    THẬT chặn hồi quy vị trí là test_server_goi_kiem_bang_va_chi_trong_main
    ở trên — nó kiểm bằng vị trí văn bản, không phụ thuộc trạng thái
    sys.modules. Test này chỉ là smoke check bổ sung."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://khong-ton-tai/x")
    sys.path.insert(0, str(MCP_DIR))
    try:
        import server
        assert server.mcp._tool_manager._tools, "registry rỗng — import hỏng"
    finally:
        sys.path.remove(str(MCP_DIR))
