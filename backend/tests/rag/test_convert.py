# backend/tests/rag/test_convert.py
"""Cầu chuyển đổi định dạng cũ — spec 2026-08-29 mục 5.1.

Test ở tệp này KHÔNG cần LibreOffice trừ hai test đánh dấu `live`. Lý do:
một cầu chuyển đổi chỉ chạy được trên máy có LibreOffice thì trên CI sẽ
không ai kiểm, và nó sẽ chết âm thầm — đúng lớp lỗi dự án đang đóng.
"""
import os
import subprocess
import zipfile

import pytest

from src.rag import convert


def _ghi_ooxml_hop_le(path: str) -> str:
    """Gói OOXML nhỏ nhất mà `zipfile` mở được — đủ cho cổng kiểm sản phẩm
    của `convert_file`. Không dùng b"converted" nữa: một chuỗi bảy byte KHÔNG
    phải tệp .docx, và cầu chuyển đổi có quyền từ chối nó."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<document/>")
    return path


def _ghi_ooxml_cut_dau(path: str) -> str:
    """Tệp bị ghi DỞ: có phần đầu của một zip nhưng không có central
    directory — đúng hình dạng soffice để lại khi bị giết giữa chừng."""
    with open(path, "wb") as fh:
        fh.write(b"PK\x03\x04" + b"\x00" * 200)
    return path


def _outdir_tu_argv(args) -> str:
    argv = args[0]
    return argv[argv.index("--outdir") + 1]


class _FakeCompletedProcess:
    """Đứng thay `subprocess.CompletedProcess` — chỉ cần `.returncode`."""
    def __init__(self, returncode: int):
        self.returncode = returncode


def test_moi_duoi_can_chuyen_deu_co_dich_den():
    for ext in (".doc", ".xls", ".ppt", ".rtf", ".odt", ".ods", ".odp"):
        assert ext in convert.TARGET_EXT, ext


def test_dich_den_deu_la_duoi_ma_ingest_nap_duoc():
    """Chống trôi: chuyển `.doc` sang một đuôi mà `_EXT` không nhận thì
    tài liệu vẫn biến mất, chỉ là chậm hơn một bước.

    CHỈ `_EXT`, KHÔNG có vế `or ... in DOCUMENT_EXT`. Bản trước có vế đó, và
    vì `DOCUMENT_EXT` khi ấy chứa trọn `_EXT` nên vế `or` nuốt vế đầu: đo
    2026-08-31, đổi `TARGET_EXT[".rtf"]` sang `"odt"` — đúng kịch bản
    docstring nói phải đỏ — thì test VẪN XANH. Đích chuyển đổi phải là đuôi
    nạp được TRỰC TIẾP; "được coi là tài liệu" chỉ nghĩa là sẽ bị TỪ CHỐI CÓ
    TÊN, tức tài liệu vẫn vắng mặt khỏi corpus."""
    from src.rag.ingest import _EXT
    for src_ext, target in convert.TARGET_EXT.items():
        assert "." + target in _EXT, src_ext


def test_khong_co_soffice_thi_nem_ConverterMissing(monkeypatch, tmp_path):
    monkeypatch.setattr(convert, "soffice_path", lambda: None)
    f = tmp_path / "a.doc"
    f.write_bytes(b"fake")
    with pytest.raises(convert.ConverterMissing) as e:
        convert.convert_file(str(f), "hash123")
    assert convert.SOFFICE_ENV in str(e.value)


def test_cache_dir_doc_duoc_tu_bien_moi_truong(monkeypatch, tmp_path):
    monkeypatch.setenv(convert.CONVERT_CACHE_ENV, str(tmp_path / "kho"))
    assert convert.cache_dir() == str(tmp_path / "kho")
    assert os.path.isdir(convert.cache_dir())


def test_dung_lai_ban_da_chuyen_khi_hash_trung(monkeypatch, tmp_path):
    """Không gọi lại LibreOffice cho tệp không đổi: mỗi lượt gọi tốn ~5 giây."""
    monkeypatch.setenv(convert.CONVERT_CACHE_ENV, str(tmp_path / "kho"))
    monkeypatch.setattr(convert, "soffice_path", lambda: "/gia/soffice")
    src = tmp_path / "a.doc"
    src.write_bytes(b"fake")

    goi = []
    def _fake_run(soffice, path, target, outdir):
        goi.append(path)
        return _ghi_ooxml_hop_le(os.path.join(outdir, "a.docx"))
    monkeypatch.setattr(convert, "_run_soffice", _fake_run)

    p1 = convert.convert_file(str(src), "hash-abc")
    p2 = convert.convert_file(str(src), "hash-abc")
    assert p1 == p2
    assert len(goi) == 1, "lượt thứ hai phải dùng cache, không gọi lại soffice"


def test_soffice_chay_xong_ma_khong_co_tep_thi_nem_ConvertFailed(monkeypatch, tmp_path):
    """Bài học 2026-08-30: trong một đợt cài có BA mã thoát nói dối. Cầu
    chuyển đổi phải kiểm TỆP ĐẦU RA, không kiểm mã thoát."""
    monkeypatch.setenv(convert.CONVERT_CACHE_ENV, str(tmp_path / "kho"))
    monkeypatch.setattr(convert, "soffice_path", lambda: "/gia/soffice")
    monkeypatch.setattr(convert, "_run_soffice",
                        lambda soffice, path, target, outdir: None)
    src = tmp_path / "a.doc"
    src.write_bytes(b"fake")
    with pytest.raises(convert.ConvertFailed):
        convert.convert_file(str(src), "hash-xyz")


def test_run_soffice_tra_None_khi_khong_co_tep_dau_ra(monkeypatch, tmp_path):
    """Ca thật 2026-08-30: mã thoát 0 (BÁO THÀNH CÔNG) nhưng không sinh tệp.
    `_run_soffice` phải KHÔNG tin mã thoát — chỉ tin sự tồn tại của tệp."""
    def _fake_subprocess_run(*args, **kwargs):
        return _FakeCompletedProcess(returncode=0)
    monkeypatch.setattr(convert.subprocess, "run", _fake_subprocess_run)

    src = tmp_path / "a.doc"
    src.write_bytes(b"fake")
    outdir = tmp_path / "out"
    outdir.mkdir()

    out = convert._run_soffice("/gia/soffice", str(src), "docx", str(outdir))
    assert out is None


def test_run_soffice_tra_duong_dan_khi_CO_tep_dau_ra_du_ma_thoat_khac_0(monkeypatch, tmp_path):
    """Ca thật 2026-08-30: scoop báo lỗi 1603/"Failed to extract files" nhưng
    đã bung đủ tệp và soffice chạy được. Mã thoát khác 0 KHÔNG được phép chặn
    một lượt chuyển đã thực sự thành công."""
    outdir = tmp_path / "out"
    outdir.mkdir()

    def _fake_subprocess_run(*args, **kwargs):
        _ghi_ooxml_hop_le(str(outdir / "a.docx"))
        return _FakeCompletedProcess(returncode=1)
    monkeypatch.setattr(convert.subprocess, "run", _fake_subprocess_run)

    src = tmp_path / "a.doc"
    src.write_bytes(b"fake")

    out = convert._run_soffice("/gia/soffice", str(src), "docx", str(outdir))
    assert out == str(outdir / "a.docx")


def test_soffice_treo_thi_nem_ConvertFailed_khong_lot_TimeoutExpired(monkeypatch, tmp_path):
    """Vòng sửa 2: soffice treo quá CONVERT_TIMEOUT_S ném TimeoutExpired.
    Không ai bắt loại lỗi đó phía trên (_ingest_convertible chỉ bắt
    ConverterMissing/ConvertFailed, vòng lặp ingest_path không có lá chắn) —
    một tệp .doc treo sẽ sập TRỌN lượt nạp và mất báo cáo của mọi tệp đã xử
    lý trước đó. convert_file phải biến nó thành ConvertFailed CÓ TÊN."""
    monkeypatch.setenv(convert.CONVERT_CACHE_ENV, str(tmp_path / "kho"))
    monkeypatch.setattr(convert, "soffice_path", lambda: "/gia/soffice")

    def _fake_subprocess_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="soffice", timeout=180)
    monkeypatch.setattr(convert.subprocess, "run", _fake_subprocess_run)

    src = tmp_path / "a.doc"
    src.write_bytes(b"fake")
    with pytest.raises(convert.ConvertFailed) as e:
        convert.convert_file(str(src), "hash-treo")
    assert "180" in str(e.value)


@pytest.mark.live
def test_chuyen_that_mot_tep_doc(tmp_path):
    """Cần LibreOffice thật. Dùng tệp mẫu trong tmp-docs nếu có."""
    src = "d:/Youdoo/tmp-docs/quyche_taichinh.doc"
    if convert.soffice_path() is None or not os.path.isfile(src):
        pytest.skip("cần LibreOffice và tmp-docs/quyche_taichinh.doc")
    os.environ[convert.CONVERT_CACHE_ENV] = str(tmp_path / "kho")
    out = convert.convert_file(src, "live-hash")
    assert out.endswith(".docx") and os.path.getsize(out) > 5000
    from src.rag.parse import parse_docx
    blocks = parse_docx(out)
    assert len(blocks) > 20
    assert any("CHƯƠNG" in b["text"] for b in blocks)


def test_luot_bi_CAT_NGANG_khong_de_lai_tep_cut_trong_cache(monkeypatch, tmp_path):
    """C3 (review toàn nhánh 2026-08-31).

    Trước bản sửa, soffice ghi THẲNG vào thư mục cache. Một lượt bị cắt ngang
    (timeout giết tiến trình con, Ctrl-C, đầy đĩa) để lại tệp CỤT ĐẦU ở đúng
    vị trí cache; lượt sau `os.path.isfile(cached)` trả nguyên nó mà không
    kiểm gì. Khoá cache là hash của tệp GỐC nên nội dung không đổi thì hash
    không đổi — BẨN VĨNH VIỄN, không bao giờ tự lành, và `parse_docx` ném
    PackageNotFoundError làm sập trọn lượt nạp.

    Giả lập ở BIÊN NGOÀI (`subprocess.run`), không giả `_run_soffice`: cần đi
    qua đúng đoạn code quyết định ghi vào đâu."""
    monkeypatch.setenv(convert.CONVERT_CACHE_ENV, str(tmp_path / "kho"))
    monkeypatch.setattr(convert, "soffice_path", lambda: "/gia/soffice")
    src = tmp_path / "a.doc"
    src.write_bytes(b"fake")

    def _bi_giet(*args, **kwargs):
        # soffice đã ghi được nửa tệp rồi bị giết vì quá hạn.
        _ghi_ooxml_cut_dau(os.path.join(_outdir_tu_argv(args), "a.docx"))
        raise subprocess.TimeoutExpired(cmd="soffice", timeout=180)
    monkeypatch.setattr(convert.subprocess, "run", _bi_giet)

    with pytest.raises(convert.ConvertFailed):
        convert.convert_file(str(src), "hash-cat-ngang")

    # LƯỢT KẾ TIẾP: soffice chạy bình thường. Phải ra tệp DÙNG ĐƯỢC.
    def _chay_tot(*args, **kwargs):
        _ghi_ooxml_hop_le(os.path.join(_outdir_tu_argv(args), "a.docx"))
        return _FakeCompletedProcess(returncode=0)
    monkeypatch.setattr(convert.subprocess, "run", _chay_tot)

    out = convert.convert_file(str(src), "hash-cat-ngang")
    assert convert._ooxml_mo_duoc(out), "cache trả về tệp cụt của lượt trước"


def test_tep_dau_ra_khong_mo_duoc_thi_KHONG_vao_cache(monkeypatch, tmp_path):
    """Biến thể không có ngoại lệ nào: soffice thoát 0 và ĐỂ LẠI một tệp cụt
    (đầy đĩa). Không có phép kiểm sản phẩm thì tệp cụt vào thẳng cache."""
    monkeypatch.setenv(convert.CONVERT_CACHE_ENV, str(tmp_path / "kho"))
    monkeypatch.setattr(convert, "soffice_path", lambda: "/gia/soffice")
    src = tmp_path / "a.doc"
    src.write_bytes(b"fake")

    def _thoat_0_nhung_tep_cut(*args, **kwargs):
        _ghi_ooxml_cut_dau(os.path.join(_outdir_tu_argv(args), "a.docx"))
        return _FakeCompletedProcess(returncode=0)
    monkeypatch.setattr(convert.subprocess, "run", _thoat_0_nhung_tep_cut)

    with pytest.raises(convert.ConvertFailed):
        convert.convert_file(str(src), "hash-cut-thoat-0")

    def _chay_tot(*args, **kwargs):
        _ghi_ooxml_hop_le(os.path.join(_outdir_tu_argv(args), "a.docx"))
        return _FakeCompletedProcess(returncode=0)
    monkeypatch.setattr(convert.subprocess, "run", _chay_tot)

    out = convert.convert_file(str(src), "hash-cut-thoat-0")
    assert convert._ooxml_mo_duoc(out)
