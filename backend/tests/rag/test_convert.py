# backend/tests/rag/test_convert.py
"""Cầu chuyển đổi định dạng cũ — spec 2026-08-29 mục 5.1.

Test ở tệp này KHÔNG cần LibreOffice trừ hai test đánh dấu `live`. Lý do:
một cầu chuyển đổi chỉ chạy được trên máy có LibreOffice thì trên CI sẽ
không ai kiểm, và nó sẽ chết âm thầm — đúng lớp lỗi dự án đang đóng.
"""
import os
import pytest

from src.rag import convert


def test_moi_duoi_can_chuyen_deu_co_dich_den():
    for ext in (".doc", ".xls", ".ppt", ".rtf", ".odt", ".ods", ".odp"):
        assert ext in convert.TARGET_EXT, ext


def test_dich_den_deu_la_duoi_ma_ingest_nap_duoc():
    """Chống trôi: chuyển `.doc` sang một đuôi mà `_EXT` không nhận thì
    tài liệu vẫn biến mất, chỉ là chậm hơn một bước."""
    from src.rag.ingest import _EXT, DOCUMENT_EXT
    for src_ext, target in convert.TARGET_EXT.items():
        assert "." + target in _EXT or "." + target in DOCUMENT_EXT, src_ext


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
        out = os.path.join(outdir, "a.docx")
        with open(out, "wb") as fh:
            fh.write(b"converted")
        return out
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
