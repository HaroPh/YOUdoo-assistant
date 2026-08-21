# backend/tests/evals/test_memory_presets.py
"""Hợp đồng của CHÂN ĐỐI CHỨNG ký ức cho bộ synthesis_live."""
import pytest

from evals.memory_presets import MEMORY_PRESETS


def test_du_ba_chan_va_dung_ten():
    assert set(MEMORY_PRESETS) == {"inert", "format", "conflict", "real5"}


def test_moi_chan_mang_dung_hinh_dang_production():
    """Khối phải do render_memory_block() sinh ra, không phải chuỗi viết tay.

    Nếu ai đó thay bằng chuỗi tự viết, bộ đo sẽ đo một hình dạng prompt mà
    production không bao giờ tạo ra — đúng lỗi eval_intent mirror hợp đồng ở
    module khác rồi acc rơi 0,870 → 0,148 mà không ai nghi ngờ."""
    from src.agents.user_memory import render_memory_block
    mau = render_memory_block([("k", "v")])
    dau = mau.split("\n")[0]
    cuoi = mau.split("\n")[-1]
    for ten, khoi in MEMORY_PRESETS.items():
        assert khoi.startswith(dau), f"chân {ten} không mang dòng mở đầu thật"
        assert khoi.endswith(cuoi), f"chân {ten} không mang dòng kết thật"


def test_khong_chan_nao_rong():
    """Khối rỗng làm chân đối chứng biến thành chân gốc — nó sẽ XANH mãi mãi
    và không đo gì. Đây là cách một bộ đo chết mà vẫn báo cáo số đẹp."""
    for ten, khoi in MEMORY_PRESETS.items():
        assert khoi.strip(), f"chân {ten} rỗng"


def test_chan_conflict_thuc_su_mau_thuan_voi_mot_ca_co_that():
    """Chân `conflict` phải chọi vào một ca ĐANG CÓ trong bộ 24, nếu không nó
    chỉ là chữ thừa ở đầu prompt và không đo được gì.

    Ca đối chứng: trần phạt 8% của Điều 301 Luật Thương mại."""
    from evals.synthesis_live_cases import SYNTHESIS_LIVE_CASES
    khoi = MEMORY_PRESETS["conflict"]
    assert "15%" in khoi
    co_ca_8_phan_tram = any(
        "8%" in (c.expect if isinstance(c.expect, str) else " ".join(c.expect))
        for c in SYNTHESIS_LIVE_CASES)
    assert co_ca_8_phan_tram, (
        "bộ 24 ca không còn ca nào kỳ vọng 8% — chân `conflict` mất đối tượng "
        "để chọi, phải chọn lại fact mâu thuẫn khác")


def test_chan_inert_khong_dinh_gi_toi_noi_dung_tai_lieu():
    """Chân mốc phải VÔ HẠI thật. Nếu nó lỡ chứa từ khoá nghiệp vụ thì nó
    không còn tách được 'ký ức làm hỏng' khỏi 'chỉ cần prompt dài là hỏng'."""
    khoi = MEMORY_PRESETS["inert"].lower()
    for tu in ("phạt", "thuế", "%", "hợp đồng", "bảo hiểm", "ngày"):
        assert tu not in khoi.split("áp dụng khi phù hợp")[0].split(":", 1)[1], \
            f"chân inert chứa từ nghiệp vụ {tu!r}"


def test_chan_real5_sao_dung_cau_hinh_that():
    """Chân `real5` phải giữ ĐÚNG những tính chất khiến nó đáng đo.

    Không có test này thì ai đó "dọn cho gọn" (bỏ cặp trùng, rút còn 3 fact) sẽ
    biến nó thành một chân sạch hơn thực tế, và bộ đo lặng lẽ mất đúng thứ nó
    được dựng ra để kiểm."""
    khoi = MEMORY_PRESETS["real5"]
    assert khoi.count("\n- ") == 5, "phải đúng NĂM fact"
    # Cặp trùng: một điều nói hai lần, một Việt một Anh.
    assert "hien_thi_ma_don" in khoi and "always_show_order_code" in khoi, (
        "cặp key trùng là tính chất CÓ THẬT của dữ liệu, không được dọn")
    # Đủ cả ba loại đã đo riêng, để chân này thật sự là phép cộng dồn.
    assert "kho_chinh" in khoi                    # nội dung
    assert "xung_ho" in khoi                      # xưng hô
    assert "do_dai_phan_hoi" in khoi              # định dạng
