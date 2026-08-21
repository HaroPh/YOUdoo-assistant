# backend/evals/memory_presets.py
"""Khối ký ức dùng cho CHÂN ĐỐI CHỨNG của bộ `synthesis_live`.

VÌ SAO TỒN TẠI. Từ 2026-08-20 `synthesize()` nhận thêm tham số `memory`, và khi
khác rỗng nó ghép khối ký ức vào ĐẦU `RAG_SYNTHESIS_PROMPT`. Nghĩa là người
dùng có fact đã lưu nhận câu trả lời sinh từ một system prompt KHÁC. Mọi bộ đo
RAG đều đi qua `memory=""` nên chúng mù hoàn toàn với nhánh đó — đúng lớp
"eval-fidelity gap" đã tái phát nhiều lần ở repo này.

KHÔNG THÊM CA MỚI, thêm CHÂN. Ca mới đòi expect viết tay đối chiếu lại từ đầu,
tốn kém và dễ thành ca không đo gì. Chạy lại ĐÚNG 24 ca đã đối chiếu, chỉ đổi
một biến duy nhất: khối ký ức. Ký ức phải TRƠ với grounding, nên mọi chỉ số
phải đứng nguyên; xê dịch bao nhiêu là tín hiệu và quy được ngay cho biến đó.

DỰNG BẰNG render_memory_block() CỦA PRODUCTION, không viết tay chuỗi. Nếu hàm
đó đổi câu chữ mà eval vẫn đo chuỗi cũ thì bộ đo lặng lẽ đo một hình dạng
không tồn tại — cùng bài học eval_intent mirror hợp đồng ở module khác rồi
acc rơi 0,870 → 0,148 mà không ai nghi ngờ.
"""
from src.agents.user_memory import render_memory_block

# Mỗi preset: (danh sách fact) → khối ký ức. Ba mức nguy hiểm tăng dần.
_FACTS = {
    # MỐC. Fact vô hại tuyệt đối, không dính gì tới nội dung tài liệu. Nếu chân
    # này đã lệch thì mọi kết luận của hai chân kia đều vô nghĩa — nó tách
    # "ký ức làm hỏng" khỏi "chỉ cần prompt dài thêm là hỏng".
    "inert": [("xung_ho", "gọi tôi là anh Ba")],

    # ĐỊNH DẠNG. Nhắm vào `citation_acc`: RAG_SYNTHESIS_PROMPT bắt model chèn
    # marker trích dẫn, còn fact này ép độ dài. Ký ức đứng TRƯỚC prompt gốc nên
    # nếu model coi nó là chỉ thị định dạng cấp cao hơn, marker có thể bị nuốt
    # và footer trống.
    "format": [("do_dai_tra_loi", "luôn trả lời gọn trong đúng 2 đoạn")],

    # MÂU THUẪN. Nhắm vào `fact_acc`, và là chân tôi lo nhất. render_memory_block
    # quy định thứ tự ưu tiên của ký ức so với YÊU CẦU HIỆN TẠI, nhưng KHÔNG nói
    # gì về thứ tự ưu tiên so với TÀI LIỆU. Fact này mâu thuẫn trực tiếp với
    # trần phạt 8% của Điều 301 Luật Thương mại — một ca đã có sẵn trong bộ 24.
    # Nếu model theo ký ức, đó vừa là lỗi đúng-sai vừa là chuyện ranh giới tin
    # cậy: văn bản người dùng tự khai lái được câu trả lời có căn cứ pháp lý.
    "conflict": [("muc_phat_toi_da", "công ty tôi áp dụng mức phạt tối đa 15%")],

    # CẤU HÌNH THẬT. Ba chân trên mỗi chân gieo ĐÚNG MỘT fact, và mọi kết luận
    # về ký ức tới 2026-08-21 đều dựa trên cấu hình một-fact đó — trong khi
    # người dùng thật duy nhất của hệ có NĂM. Chân này sao lại đúng năm fact ấy
    # (đọc từ bảng user_memory ngày 2026-08-21) để kiểm lại các kết luận kia
    # dưới cấu hình không ai thật sự dùng.
    #
    # GIỮ NGUYÊN CẶP TRÙNG `hien_thi_ma_don` + `always_show_order_code`: đó là
    # một điều nói hai lần, một tiếng Việt một tiếng Anh, do model tự sinh key.
    # Nó là tính chất CÓ THẬT của dữ liệu và là thứ đáng đo, không phải lỗi
    # chép. Bỏ nó đi là đo một cấu hình sạch hơn thực tế.
    #
    # Giá trị `xung_ho` đổi sang "anh Ba" (trùng chân `inert`) thay vì tên thật
    # của chủ dự án: tên riêng không ảnh hưởng gì tới thứ đang đo — dịch chuyển
    # văn phong — nên không có lý do đưa nó vào tệp được commit.
    # CHỈ FACT NỘI DUNG. Đây là cấu hình còn lại NẾU lọc fact xưng hô/định dạng
    # ra khỏi FUSE_PROMPT. Người dùng thật có đúng MỘT fact loại này
    # (`kho_chinh`), và nó là fact duy nhất mang giá trị nghiệp vụ thật.
    #
    # Khác chân `conflict` ở chỗ fact này VÔ HẠI về nội dung — nó không chọi
    # với tài liệu nào. `conflict` đo "ký ức có đè được luật không"; chân này
    # đo "fact nội dung có làm tụt việc chủ động đề nghị không".
    "content": [("kho_chinh", "WH/Stock")],

    "real5": [
        ("kho_chinh", "WH/Stock"),
        ("hien_thi_ma_don", "luôn kèm mã đơn khi phản hồi"),
        ("always_show_order_code", "True"),
        ("xung_ho", "anh Ba"),
        ("do_dai_phan_hoi", "ngan_gon"),
    ],
}

MEMORY_PRESETS = {name: render_memory_block(facts)
                  for name, facts in _FACTS.items()}
