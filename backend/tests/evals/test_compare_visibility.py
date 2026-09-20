# backend/tests/evals/test_compare_visibility.py
"""Cổng ÂM: vai bị chặn phải MẤT SẠCH ca thương mại và KHÔNG KÉM ca khác."""
import pytest

from evals import compare_visibility as cv

CASES = [
    ("chiết khấu bậc mấy?", frozenset({("discount_policy.docx", "Điều 1")}), "easy"),
    ("SLA giao hàng?", frozenset({("sla.docx", "Mục 2")}), "hard"),
    ("thuế suất GTGT?", frozenset({("luat-thuegtgt.pdf", "Điều 9")}), "easy"),
]


def _run(rows):
    return {"per_case": [{"question": q, "recall_at_pool": p, "recall_at_final": f,
                          "reciprocal_rank": r} for q, p, f, r in rows]}


def test_qua_khi_thuong_mai_ve_0_va_ca_khac_khong_kem():
    admin = _run([("chiết khấu bậc mấy?", 1.0, 1.0, 1.0), ("SLA giao hàng?", 1.0, 1.0, 0.5),
                  ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    kho = _run([("chiết khấu bậc mấy?", 0.0, 0.0, 0.0), ("SLA giao hàng?", 0.0, 0.0, 0.0),
                ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    ra = cv.compare(admin, kho, cases=CASES)
    assert ra["ok"] is True
    assert ra["n_commercial"] == 2 and ra["n_other"] == 1
    assert ra["commercial_leaked"] == [] and ra["regressed"] == []


def test_truot_khi_mot_ca_thuong_mai_van_lo():
    admin = _run([("chiết khấu bậc mấy?", 1.0, 1.0, 1.0), ("SLA giao hàng?", 1.0, 1.0, 1.0),
                  ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    kho = _run([("chiết khấu bậc mấy?", 0.0, 0.0, 0.0), ("SLA giao hàng?", 0.5, 0.0, 0.0),
                ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    ra = cv.compare(admin, kho, cases=CASES)
    assert ra["ok"] is False
    assert [x["question"] for x in ra["commercial_leaked"]] == ["SLA giao hàng?"]


def test_truot_khi_ca_khac_kem_di():
    admin = _run([("chiết khấu bậc mấy?", 1.0, 1.0, 1.0), ("SLA giao hàng?", 1.0, 1.0, 1.0),
                  ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    kho = _run([("chiết khấu bậc mấy?", 0.0, 0.0, 0.0), ("SLA giao hàng?", 0.0, 0.0, 0.0),
                ("thuế suất GTGT?", 0.5, 0.5, 0.5)])
    ra = cv.compare(admin, kho, cases=CASES)
    assert ra["ok"] is False
    assert [x["question"] for x in ra["regressed"]] == ["thuế suất GTGT?"]


def test_ca_lan_bi_tu_choi_to_tieng():
    """Ca có nhãn từ CẢ tệp thương mại lẫn tệp khác không xếp được vào bên nào —
    hôm nay không có ca nào như thế (0/109), nếu xuất hiện phải báo, không đoán."""
    lan = [("hỏi lẫn", frozenset({("sla.docx", "Mục 1"), ("policy.docx", "Điều 2")}), "hard")]
    with pytest.raises(ValueError, match="lẫn"):
        cv.compare(_run([("hỏi lẫn", 1, 1, 1)]), _run([("hỏi lẫn", 0, 0, 0)]), cases=lan)


def test_thieu_ca_o_mot_ben_la_loi():
    admin = _run([("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    with pytest.raises(ValueError, match="thiếu"):
        cv.compare(admin, _run([]), cases=CASES[2:])


# ── Tự-rà (yêu cầu ngoài brief): cổng phải THẬT SỰ sập nếu bộ lọc bị tắt ──

def test_neu_bo_loc_bi_tat_cong_phai_that_bai():
    """Nếu vai bị chặn thấy y hệt admin (bộ lọc coi như không tồn tại), cổng
    KHÔNG được xanh: ca thương mại lộ ra (recall_at_pool != 0), commercial_leaked
    khớp đúng câu thương mại, ok=False, và (qua CLI) exit code phải khác 0."""
    admin = _run([("chiết khấu bậc mấy?", 1.0, 1.0, 1.0), ("SLA giao hàng?", 1.0, 1.0, 1.0),
                  ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    kho_khong_loc = _run([("chiết khấu bậc mấy?", 1.0, 1.0, 1.0),
                          ("SLA giao hàng?", 1.0, 1.0, 1.0),
                          ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    ra = cv.compare(admin, kho_khong_loc, cases=CASES)
    assert ra["ok"] is False
    assert {x["question"] for x in ra["commercial_leaked"]} == {"chiết khấu bậc mấy?",
                                                                  "SLA giao hàng?"}
    assert ra["regressed"] == []  # ca khác không kém — chỉ ca thương mại lộ


def test_cli_exit_khac_0_khi_that_bai(tmp_path, monkeypatch):
    """main() phải trả về mã khác 0 khi ok=False, và 0 khi ok=True — một cổng
    in ra vấn đề rồi exit 0 không phải là cổng. Chỉ đè `compare` (mock), giữ
    nguyên đường đọc JSON và mã thoát thật của main(); tránh phụ thuộc toàn
    bộ RETRIEVAL_CASES thật (109 ca) chỉ để lắp dây exit code."""
    admin_path = tmp_path / "admin.json"
    kho_path = tmp_path / "kho.json"
    admin_path.write_text('{"per_case": []}', encoding="utf-8")
    kho_path.write_text('{"per_case": []}', encoding="utf-8")

    monkeypatch.setattr(cv, "compare", lambda admin, restricted: {
        "ok": True, "n_commercial": 0, "n_other": 0,
        "commercial_leaked": [], "regressed": []})
    assert cv.main([str(admin_path), str(kho_path)]) == 0

    monkeypatch.setattr(cv, "compare", lambda admin, restricted: {
        "ok": False, "n_commercial": 1, "n_other": 0,
        "commercial_leaked": [{"question": "x", "recall_at_pool": 1.0}], "regressed": []})
    assert cv.main([str(admin_path), str(kho_path)]) != 0


def test_hai_luot_kho_that_bai():
    """Hai lượt CÙNG vai (ở đây: hai lượt `warehouse`) không chứng minh được
    gì — cổng phải từ chối NGAY vì vế đầu không phải vai admin, trước khi so
    bất kỳ ca nào."""
    kho1 = _run([("chiết khấu bậc mấy?", 0.0, 0.0, 0.0), ("SLA giao hàng?", 0.0, 0.0, 0.0),
                ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    kho1["role"] = "warehouse"
    kho2 = _run([("chiết khấu bậc mấy?", 0.0, 0.0, 0.0), ("SLA giao hàng?", 0.0, 0.0, 0.0),
                ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    kho2["role"] = "warehouse"
    with pytest.raises(ValueError, match="admin"):
        cv.compare(kho1, kho2, cases=CASES)


def test_cung_tep_hai_lan_that_bai():
    """Truyền đúng MỘT tệp (vd admin.json) hai lần — hai vế cùng khai
    role='admin', cổng phải từ chối vì không so hai vai KHÁC nhau."""
    admin = _run([("chiết khấu bậc mấy?", 1.0, 1.0, 1.0), ("SLA giao hàng?", 1.0, 1.0, 1.0),
                  ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    admin["role"] = "admin"
    admin_lai = dict(admin)
    with pytest.raises(ValueError, match="cùng vai"):
        cv.compare(admin, admin_lai, cases=CASES)


def test_admin_khong_thay_thuong_mai_bi_tu_choi():
    """Vế 'admin' mà recall_at_pool = 0 trên MỌI ca thương mại không giống
    một lượt đo không-lọc thật — có thể chính nó cũng đang bị chặn, hoặc nạp
    nhầm tệp. Cổng không được coi đó là bằng chứng cho vế còn lại."""
    admin_gia = _run([("chiết khấu bậc mấy?", 0.0, 0.0, 0.0), ("SLA giao hàng?", 0.0, 0.0, 0.0),
                      ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    kho = _run([("chiết khấu bậc mấy?", 0.0, 0.0, 0.0), ("SLA giao hàng?", 0.0, 0.0, 0.0),
                ("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    kho["role"] = "warehouse"
    with pytest.raises(ValueError, match="thương mại"):
        cv.compare(admin_gia, kho, cases=CASES)


def test_thieu_khoa_trong_mot_ca_bao_loi_ngay_khong_lang_le():
    """per_case thiếu khoá recall_at_pool → KeyError ngay lập tức, không bỏ
    qua ca đó trong im lặng. Quyết định có chủ đích: một cổng phủ định
    (negative gate) mà bỏ sót một ca là cổng ngừng đo, không phải cổng qua."""
    admin = _run([("thuế suất GTGT?", 1.0, 1.0, 1.0)])
    thieu_khoa = {"per_case": [{"question": "thuế suất GTGT?"}]}  # thiếu recall_at_pool
    with pytest.raises(KeyError):
        cv.compare(admin, thieu_khoa, cases=CASES[2:])
