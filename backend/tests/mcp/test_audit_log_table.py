"""Vệt kiểm toán MCP: bảng phải CÓ THẬT, và thiếu thì phải nổ to.

Bối cảnh: mcp_call_log chưa từng tồn tại trong database Youdoo, và
log_mcp_event nuốt mọi lỗi ghi nên cả cơ chế chết im lặng suốt. Lưới duy
nhất chặn được chuyện đó tái diễn là kiểm lúc khởi động."""
import importlib
import importlib.util
import sys
import threading
import time
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


# ─── Serialise đọc-tính-ghi giữa NHIỀU TIẾN TRÌNH ─────────────────────────
# start-dev.ps1 chạy BA tiến trình MCP ghi chung một bảng. _db_lock chỉ là
# threading.Lock (một tiến trình), và connection đặt autocommit=True nên
# SELECT đỉnh chuỗi và INSERT là hai giao dịch rời — hai tiến trình đọc cùng
# một đỉnh sẽ chained cùng prev_hash và verify_audit_chain báo "Chuỗi đứt"
# trên dữ liệu không ai giả mạo. Lỗi này nằm im chỉ vì bảng chưa tồn tại.


class _CursorGia:
    """Ghi lại mọi câu SQL đã chạy; trả (None,) cho SELECT đỉnh chuỗi."""

    def __init__(self, nhat_ky):
        self.nhat_ky = nhat_ky

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.nhat_ky.append((" ".join(sql.split()), params))

    def fetchone(self):
        return (None,)


class _ConnGia:
    closed = 0

    def __init__(self, no_khi_insert=False):
        self.autocommit = True
        self.nhat_ky = []
        self.su_kien = []
        self.no_khi_insert = no_khi_insert

    def cursor(self):
        if self.no_khi_insert:
            return _CursorNo(self.nhat_ky)
        return _CursorGia(self.nhat_ky)

    def commit(self):
        self.su_kien.append("commit")

    def rollback(self):
        self.su_kien.append("rollback")


class _CursorNo(_CursorGia):
    def execute(self, sql, params=None):
        super().execute(sql, params)
        if "INSERT" in sql:
            raise RuntimeError("ghi hỏng")


def _chay_ghi(event_log_mod, monkeypatch, conn):
    monkeypatch.setattr(event_log_mod, "DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(event_log_mod, "_get_db", lambda: conn)
    event_log_mod.log_mcp_event("tool_error", tool_name="t", error_code="E500")


def test_khoa_advisory_duoc_phat_truoc_khi_doc_dinh_chuoi(event_log_mod,
                                                          monkeypatch):
    """Câu khoá phải là câu ĐẦU TIÊN trong giao dịch — phát sau khi đã đọc
    đỉnh chuỗi thì vô nghĩa, hai bên vẫn kịp đọc cùng một đỉnh."""
    conn = _ConnGia()
    _chay_ghi(event_log_mod, monkeypatch, conn)

    cau = [sql for sql, _ in conn.nhat_ky]
    assert "SELECT pg_advisory_xact_lock(%s)" in cau[0], cau
    assert conn.nhat_ky[0][1] == (event_log_mod.CHAIN_LOCK_KEY,)
    assert "SELECT entry_hash FROM mcp_call_log" in cau[1], cau
    assert cau[2].startswith("INSERT INTO mcp_call_log"), cau


def test_doc_va_ghi_nam_trong_MOT_giao_dich(event_log_mod, monkeypatch):
    """autocommit phải TẮT trong lúc chạy (nếu không, khoá xact nhả ngay sau
    câu SELECT), có đúng một commit, và autocommit được trả lại sau đó."""
    conn = _ConnGia()

    trang_thai = []
    goc = _ConnGia.cursor

    def cursor_ghi_nhan(self):
        trang_thai.append(self.autocommit)
        return goc(self)

    monkeypatch.setattr(_ConnGia, "cursor", cursor_ghi_nhan)
    _chay_ghi(event_log_mod, monkeypatch, conn)

    assert trang_thai == [False], "giao dịch không được mở với autocommit=False"
    assert conn.su_kien == ["commit"]
    assert conn.autocommit is True, "không trả lại autocommit cho lượt sau"


def test_loi_ghi_van_bi_nuot_va_ep_reconnect(event_log_mod, monkeypatch):
    """Hợp đồng KHÔNG đổi sau khi thêm giao dịch: log hỏng không được làm
    hỏng tool, và connection hỏng phải bị vứt để lượt sau reconnect."""
    conn = _ConnGia(no_khi_insert=True)
    monkeypatch.setattr(event_log_mod, "_db_conn", conn)
    _chay_ghi(event_log_mod, monkeypatch, conn)          # không được ném

    assert conn.su_kien == ["rollback"], \
        "giao dịch dở phải được rollback, không để lại trạng thái aborted"
    assert event_log_mod._db_conn is None, "không ép reconnect lượt sau"


def test_khong_co_conn_thi_khong_dung_toi_giao_dich(event_log_mod, monkeypatch):
    """Đối chứng: nhánh 'không cấu hình DB' không được đụng vào autocommit."""
    monkeypatch.setattr(event_log_mod, "DATABASE_URL", None)
    monkeypatch.setattr(event_log_mod, "_get_db", lambda: None)
    event_log_mod.log_mcp_event("tool_error", tool_name="t")   # không được ném


# ─── caller mang danh tính vai (mục 5) ────────────────────────────────────

def test_caller_mac_dinh_mang_ten_tai_khoan_odoo(event_log_mod):
    """Ba tiến trình MCP đăng nhập Odoo bằng ba tài khoản khác nhau nhưng ghi
    chung một bảng. caller là hằng 'mcp-odoo' ⇒ dòng permission_denied không
    quy được về AI nào — trong khi cách ly theo vai là biện pháp an ninh
    chính của hệ thống."""
    from config import ODOO_USER

    assert event_log_mod.DEFAULT_CALLER == f"mcp-odoo/{ODOO_USER}"
    assert event_log_mod.DEFAULT_CALLER != "mcp-odoo"


def test_caller_mac_dinh_di_ra_toi_cau_insert(event_log_mod, monkeypatch):
    """Hằng đúng mà không được INSERT thì vô nghĩa — kiểm giá trị THẬT trong
    tham số của câu INSERT (cột thứ 2 = caller)."""
    conn = _ConnGia()
    _chay_ghi(event_log_mod, monkeypatch, conn)
    sql_insert, params = conn.nhat_ky[2]
    assert sql_insert.startswith("INSERT INTO mcp_call_log")
    assert params[1] == event_log_mod.DEFAULT_CALLER


def test_caller_truyen_tay_van_duoc_ton_trong(event_log_mod, monkeypatch):
    conn = _ConnGia()
    monkeypatch.setattr(event_log_mod, "DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(event_log_mod, "_get_db", lambda: conn)
    event_log_mod.log_mcp_event("tool_error", tool_name="t", caller="khac")
    assert conn.nhat_ky[2][1][1] == "khac"


# ─── Postgres chưa lên: retry + thông báo phân biệt được (mục 6) ──────────

def test_khong_ket_noi_duoc_thi_bao_ro_va_khong_lo_mat_khau(event_log_mod,
                                                            monkeypatch):
    """Trước bản này, Postgres lạnh làm psycopg2.OperationalError xuyên thẳng
    ra và giết tiến trình MCP — trái với đúng những gì tài liệu hứa người vận
    hành sẽ thấy, và không phân biệt được với 'thiếu bảng'."""
    dsn = "postgresql://admin:sieu_bi_mat@localhost:5434/ai_assistant"
    monkeypatch.setattr(event_log_mod, "DATABASE_URL", dsn)
    monkeypatch.setattr(event_log_mod.time, "sleep", lambda *_: None)

    def khong_ket_noi_duoc():
        raise OSError("connection refused")

    monkeypatch.setattr(event_log_mod, "_get_db", khong_ket_noi_duoc)

    with pytest.raises(RuntimeError) as e:
        event_log_mod.assert_log_table_ready()

    msg = str(e.value)
    assert "localhost:5434" in msg, msg
    assert "sieu_bi_mat" not in msg, "thông báo lộ mật khẩu"
    assert "002_mcp_call_log.sql" not in msg, \
        "nhầm 'không tới được database' thành 'thiếu bảng'"


def test_thu_lai_co_backoff_roi_moi_bo_cuoc(event_log_mod, monkeypatch):
    """`docker compose up -d` trả về khi container đã ĐƯỢC TẠO, không phải
    khi Postgres nhận kết nối — nên phải thử lại, có giãn cách."""
    ngu = []
    monkeypatch.setattr(event_log_mod, "DATABASE_URL", "postgresql://h:1/d")
    monkeypatch.setattr(event_log_mod.time, "sleep", ngu.append)

    so_lan = []

    def luon_hong():
        so_lan.append(1)
        raise OSError("connection refused")

    monkeypatch.setattr(event_log_mod, "_get_db", luon_hong)
    with pytest.raises(RuntimeError):
        event_log_mod.assert_log_table_ready()

    assert len(so_lan) == event_log_mod.CONNECT_RETRIES
    assert len(ngu) == event_log_mod.CONNECT_RETRIES - 1, \
        "không được ngủ sau lần thử cuối"
    assert ngu == sorted(ngu) and ngu[0] < ngu[-1], f"không có backoff: {ngu}"
    assert sum(ngu) < 30, f"chặn khởi động quá lâu: {sum(ngu)}s"


def test_postgres_len_muon_van_khoi_dong_duoc(event_log_mod, monkeypatch):
    """Đối chứng: nếu retry chỉ là trang trí (bỏ cuộc ngay lần đầu) thì test
    này đỏ."""
    class FakeCursor:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a): pass
        def fetchone(self): return (True,)

    class FakeConn:
        def cursor(self): return FakeCursor()

    lan = {"n": 0}

    def len_o_lan_thu_ba():
        lan["n"] += 1
        if lan["n"] < 3:
            raise OSError("connection refused")
        return FakeConn()

    monkeypatch.setattr(event_log_mod, "DATABASE_URL", "postgresql://h:1/d")
    monkeypatch.setattr(event_log_mod.time, "sleep", lambda *_: None)
    monkeypatch.setattr(event_log_mod, "_get_db", len_o_lan_thu_ba)

    event_log_mod.assert_log_table_ready()          # không được ném
    assert lan["n"] == 3


@pytest.mark.integration
def test_ghi_roi_doc_lai_duoc(event_log_mod):
    """Test DUY NHẤT chứng minh vòng ghi khép kín: gọi log_mcp_event rồi ĐỌC
    LẠI dòng vừa ghi và tính lại hash.

    Đây chính là thứ đã vắng mặt suốt và là lý do cả cơ chế chết mà không ai
    biết — mọi test khác chỉ khẳng định hàm ĐƯỢC GỌI, không khẳng định có
    dòng nào ra tới database.

    Cần DATABASE_URL thật và migration 002 đã chạy. Chạy riêng:
        pytest tests/mcp/test_audit_log_table.py -m integration

    KHÔNG dọn dẹp dòng probe, và đó là CHỦ ĐÍCH: mỗi dòng chained vào hash
    của dòng ngay trước, nên DELETE một dòng giữa chuỗi làm đứt liên kết
    prev_hash vĩnh viễn và verify_audit_chain.py sẽ báo "Chuỗi đứt" mãi mãi
    trên dữ liệu không ai giả mạo. Đừng "dọn cho sạch".
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


def _nap_event_log_doc_lap(ten: str):
    """Nạp event_log thành một module ĐỘC LẬP (state riêng: _db_conn,
    _db_lock). Đây là bản mô phỏng trung thực nhất của "hai TIẾN TRÌNH MCP"
    mà một bộ test đơn tiến trình làm được — dùng hai thread trên cùng module
    sẽ chỉ đo lại threading.Lock sẵn có và không chạm tới vấn đề thật."""
    spec = importlib.util.spec_from_file_location(ten, MCP_DIR / "event_log.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _CursorTre:
    """Cursor thật, có ngủ NGAY SAU khi đọc đỉnh chuỗi — mở đúng cửa sổ mà
    bên ghi thứ hai từng chen vào được."""

    def __init__(self, cur, tre):
        self._cur, self._tre = cur, tre

    def __enter__(self):
        self._cur.__enter__()
        return self

    def __exit__(self, *a):
        return self._cur.__exit__(*a)

    def execute(self, sql, params=None):
        r = self._cur.execute(sql) if params is None else self._cur.execute(sql, params)
        if "entry_hash FROM mcp_call_log" in sql:
            time.sleep(self._tre)
        return r

    def fetchone(self):
        return self._cur.fetchone()


class _ConnTre:
    closed = 0

    def __init__(self, conn, tre):
        self._c, self._tre = conn, tre

    @property
    def autocommit(self):
        return self._c.autocommit

    @autocommit.setter
    def autocommit(self, v):
        self._c.autocommit = v

    def cursor(self):
        return _CursorTre(self._c.cursor(), self._tre)

    def commit(self):
        return self._c.commit()

    def rollback(self):
        return self._c.rollback()


@pytest.mark.integration
def test_hai_ket_noi_ghi_chong_nhau_chuoi_van_lien():
    """Hai bên ghi ĐỘC LẬP (hai module, hai connection = hai tiến trình) cố ý
    chồng lấn nhau; chuỗi hash phải vẫn liên kết.

    Cách dựng làm nó XÁC ĐỊNH, không phải xác suất: bên A ngủ 2s NGAY SAU khi
    đọc đỉnh chuỗi, còn trong giao dịch. Bên B bắt đầu sau 0.5s. Nếu khoá
    advisory thật sự giữ tới hết giao dịch, B phải BỊ CHẶN (đo bằng thời gian
    nó chạy) và chained vào dòng của A. Không có khoá, B đọc đúng đỉnh cũ mà
    A vừa đọc, hai dòng cùng prev_hash ⇒ khẳng định liên kết bên dưới đỏ.

    KHÔNG xoá hai dòng probe — xem test_ghi_roi_doc_lai_duoc.
    """
    psycopg2 = pytest.importorskip("psycopg2")
    sys.path.insert(0, str(MCP_DIR))
    try:
        mod_a = _nap_event_log_doc_lap("event_log_a")
        mod_b = _nap_event_log_doc_lap("event_log_b")
        if not mod_a.DATABASE_URL:
            pytest.skip("cần DATABASE_URL")

        doc = psycopg2.connect(mod_a.DATABASE_URL)
        try:
            with doc.cursor() as cur:
                cur.execute("SELECT COALESCE(MAX(id), 0) FROM mcp_call_log")
                id_truoc = cur.fetchone()[0]

            mod_a._db_conn = _ConnTre(mod_a._get_db(), 2.0)

            def ghi_a():
                mod_a.log_mcp_event("tool_error", tool_name="probe-song-song-A",
                                    error_code="E500", error_message="A")

            luong_a = threading.Thread(target=ghi_a)
            luong_a.start()
            time.sleep(0.5)                 # để A kịp giữ khoá
            bat_dau = time.monotonic()
            mod_b.log_mcp_event("tool_error", tool_name="probe-song-song-B",
                                error_code="E500", error_message="B")
            keo_dai = time.monotonic() - bat_dau
            luong_a.join(timeout=30)

            with doc.cursor() as cur:
                cur.execute(
                    "SELECT id, tool_name, entry_hash, prev_hash"
                    " FROM mcp_call_log WHERE id > %s ORDER BY id", (id_truoc,))
                moi = cur.fetchall()
                cur.execute("SELECT entry_hash FROM mcp_call_log"
                            " WHERE id = %s", (id_truoc,))
                dau_cu = cur.fetchone()
        finally:
            doc.close()

        assert keo_dai > 1.0, (
            f"bên ghi thứ hai chỉ mất {keo_dai:.2f}s — nó KHÔNG bị chặn, tức "
            "khoá advisory không giữ qua cả giao dịch")
        assert [r[1] for r in moi] == ["probe-song-song-A", "probe-song-song-B"]

        import audit_chain
        dinh_truoc = (dau_cu[0] if dau_cu and dau_cu[0]
                      else audit_chain.GENESIS_HASH)
        assert moi[0][3] == dinh_truoc
        assert moi[1][3] == moi[0][2], (
            "hai dòng KHÔNG nối vào nhau — cả hai bên ghi đã đọc cùng một "
            "đỉnh chuỗi; verify_audit_chain sẽ báo 'Chuỗi đứt' trên dữ liệu "
            "không ai giả mạo")
    finally:
        sys.path.remove(str(MCP_DIR))
        for ten in ("event_log_a", "event_log_b"):
            sys.modules.pop(ten, None)


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
