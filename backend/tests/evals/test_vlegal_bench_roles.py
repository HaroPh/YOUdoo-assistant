# backend/tests/evals/test_vlegal_bench_roles.py
"""Phân loại VLegal-Bench theo vai. Câu ví dụ TỰ VIẾT, không trích dataset
thật (CC BY-NC-ND 4.0 cấm derivative work) — xem evals/vlegal_bench_roles.py."""
import json

from evals import vlegal_bench_roles as vr


def test_khop_dung_1_vai_ke_toan():
    assert vr.classify("Doanh nghiệp phải nộp thuế thu nhập khi nào?") == "accounting"


def test_khop_dung_1_vai_ban_hang():
    assert vr.classify("Hợp đồng thương mại giữa hai bên cần điều khoản gì?") == "sales"


def test_khop_dung_1_vai_kho():
    assert vr.classify("Trách nhiệm khi hàng hóa hư hỏng trong kho hàng là gì?") == "warehouse"


def test_khong_khop_vai_hep_nao_la_chung():
    assert vr.classify("Thủ tục cấp giấy phép xây dựng gồm những bước nào?") == "chung"


def test_khop_2_vai_tro_thanh_mix():
    text = "Hóa đơn giao hàng cho khách hàng cần ghi thông tin kho hàng nào?"
    assert vr.classify(text) == "mix"


def test_khong_phan_biet_hoa_thuong():
    assert vr.classify("THUẾ và HÓA ĐƠN phải lưu bao lâu?") == "accounting"


def test_khong_co_vai_admin_rieng_trong_tu_khoa():
    # admin unrestricted=True (src/agents/roles.py) -- khong co mien hep rieng,
    # phai KHONG xuat hien trong ROLE_KEYWORDS.
    assert "admin" not in vr.ROLE_KEYWORDS


def test_record_text_gop_ca_3_truong():
    row = {"question": "Câu hỏi thuế", "answers": "A: có\nB: không",
           "instruction": "Chọn đáp án"}
    text = vr.record_text(row)
    assert "thuế" in text and "Chọn đáp án" in text


def test_iter_records_bo_qua_dong_rong_va_json_hong(tmp_path):
    task_dir = tmp_path / "1.1"
    task_dir.mkdir()
    (task_dir / "1_1.jsonl").write_text(
        '{"question": "câu 1"}\n'
        "\n"
        "khong-phai-json\n"
        '{"question": "câu 2"}\n',
        encoding="utf-8",
    )
    rows = list(vr.iter_records(str(tmp_path)))
    assert [r["question"] for r in rows] == ["câu 1", "câu 2"]


def test_summarize_dem_dung_va_admin_bang_tong(tmp_path):
    task_dir = tmp_path / "1.1"
    task_dir.mkdir()
    rows = [
        {"question": "Thuế thu nhập doanh nghiệp nộp khi nào?"},          # accounting
        {"question": "Hợp đồng thương mại cần điều khoản gì?"},           # sales
        {"question": "Kho hàng bảo quản hàng hóa ra sao?"},               # warehouse
        {"question": "Thủ tục hành chính cấp phép xây dựng?"},            # chung
        {"question": "Hóa đơn giao hàng ghi kho hàng nào?"},              # mix
    ]
    (task_dir / "1_1.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")

    counts = vr.summarize(str(tmp_path))
    assert counts["accounting"] == 1
    assert counts["sales"] == 1
    assert counts["warehouse"] == 1
    assert counts["chung"] == 1
    assert counts["mix"] == 1
    assert counts["admin"] == 5  # unrestricted = tong toan bo, khong loc


def test_summarize_thu_muc_rong_khong_sap(tmp_path):
    counts = vr.summarize(str(tmp_path))
    assert counts["admin"] == 0
