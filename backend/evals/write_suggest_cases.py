# backend/evals/write_suggest_cases.py
"""Bộ ca đo marker `ĐỀ_XUẤT_GHI` trên đường `fuse_answer`.

VÌ SAO TỒN TẠI. `ĐỀ_XUẤT_GHI` là thứ ARM cơ chế xác nhận ghi: `fuse_answer`
tách nó ra thành `state["suggested_write"]` (fanout.py:217), và
`replying_to_write_suggestion` chỉ cho lượt "ok" của người dùng đi vào đường
GHI khi cờ đó bật. Marker tịt ⇒ người dùng gật mà không có gì xảy ra. Marker
bật oan ⇒ một câu hỏi làm rõ bình thường biến lượt sau thành lệnh ghi.

Marker này đã HỎNG IM LẶNG HAI LẦN: một lần cơ chế chết hoàn toàn trên
production qua 6 vòng review, một lần regex chỉ khớp đầu dòng trong khi model
dán nó vào cuối câu. Nay nó nằm SAU khối ký ức do người dùng tự khai — thứ đã
đo được là đủ sức lấn một chỉ thị định dạng cứng — mà chưa phép đo nào chạm tới.

CÙNG HÌNH DẠNG với `MULTI_SOURCE_CASES` và dùng CHÍNH `render_fuse_input` +
`FUSE_PROMPT` của production, vì đây là điều kiện để mirror không trôi (bài học
SP-2a: eval_intent dựng lại hợp đồng ở module riêng, hợp đồng đổi mà eval không
đổi theo, acc rơi 0,870 → 0,148 và trông y hệt lỗi chất lượng model).

`erp_block` lấy nguyên từ `MULTI_SOURCE_CASES` — cùng dữ kiện ERP thật, chỉ đổi
câu hỏi. Nhờ vậy khác biệt đo được quy về ĐÚNG một biến: câu hỏi có yêu cầu một
thao tác ghi hay không.

BỐN CA ÂM đều là "suýt trúng" có chủ đích: chúng mang từ vựng ghi (xác nhận,
hoàn tiền, quy trình tạo đơn) nhưng KHÔNG yêu cầu hành động. Bộ ca chỉ toàn ca
âm hiển nhiên sẽ xanh mãi mãi mà không chứng minh được gì.

CA DƯƠNG PHẢI TỰ ĐỦ DỮ KIỆN — bài học từ chính bản đầu của tệp này. Bản đầu
dùng lại nguyên `erp_block` của MULTI_SOURCE_CASES và hỏi "nếu trễ SLA thì lập
phiếu bồi thường giúp tôi". Đo ra 3/4 ca dương KHÔNG phát marker, và đọc câu
trả lời thật thì model ĐÚNG: erp_block không có ngày giao nên nó không kết luận
được là trễ, nên nó hỏi thêm thông tin — mà FUSE_PROMPT ghi rõ "câu hỏi làm rõ
thông thường thì KHÔNG thêm marker". Nhãn "phải phát marker" là tiền đề BẤT KHẢ
THI, không phải model hỏng.

Nên mỗi ca dương nay mang đủ dữ kiện để việc DUY NHẤT còn lại là thao tác ghi.
Phép hiệu chỉnh: chân KHÔNG ký ức phải đạt marker_acc gần tuyệt đối. Nếu nó
không sạch thì bộ ca đang đo chính nó chứ không đo ảnh hưởng của ký ức.
"""
from typing import NamedTuple


class WriteSuggestCase(NamedTuple):
    topic: str          # fixture tài liệu, phải có trong evals/fixtures
    erp_block: str      # dữ kiện ERP thô, đóng vai erp_facts
    question: str
    expect_marker: bool  # câu trả lời có PHẢI mang ĐỀ_XUẤT_GHI không


_SLA = "sla_giao_hang"
_HOAN = "chinh_sach_hoan_hang"
_TT = "chinh_sach_thanh_toan"
_CK = "bang_gia_chiet_khau"

WRITE_SUGGEST_CASES = [
    # ── DƯƠNG: yêu cầu một thao tác ghi cụ thể, chờ người dùng đồng ý ──────
    WriteSuggestCase(
        _SLA,
        "Đơn S00042 | Azure Interior | cam kết giao 15/07/2026 | "
        "giao thực tế 20/07/2026 | trễ 5 ngày | giá trị 1.500.000",
        "Đơn S00042 trễ 5 ngày rồi, lập phiếu bồi thường theo SLA giúp tôi",
        True),
    WriteSuggestCase(
        _HOAN,
        "Hóa đơn INV/2026/00017 | Azure Interior | đã thanh toán | "
        "mua 10/07/2026 | hàng nguyên tem mác, chưa qua sử dụng | đã có phiếu RMA",
        "Hóa đơn INV/2026/00017 đủ điều kiện hoàn rồi, làm hoàn tiền giúp tôi",
        True),
    WriteSuggestCase(
        _TT, "Đơn S00050 | Khách Gemini Furniture | quá hạn thanh toán 32 ngày",
        "Đơn S00050 quá hạn rồi, khoá công nợ khách này lại giúp tôi",
        True),
    WriteSuggestCase(
        _CK,
        "Khách Azure Interior | cấp Thân thiết | đặt 50 Large Cabinet | "
        "đơn giá 320.000 | tổng 16.000.000",
        "Áp chiết khấu đúng cấp cho đơn này rồi xác nhận đơn giúp tôi",
        True),

    # ── ÂM: mang từ vựng ghi nhưng KHÔNG yêu cầu hành động ────────────────
    WriteSuggestCase(
        _SLA, "Đơn S00042 | Azure Interior | trạng thái sale | 1.500.000",
        "Đơn S00042 có đáp ứng SLA giao hàng không?",
        False),
    WriteSuggestCase(
        _HOAN, "Đơn S00042 | Azure Interior | đã giao 15/07/2026",
        # "hoàn hàng" là từ vựng ghi, nhưng đây là câu hỏi TRA CỨU điều kiện.
        "Đơn S00042 còn được hoàn hàng theo chính sách không?",
        False),
    WriteSuggestCase(
        _TT, "Hóa đơn INV/2026/00020 | Khách Wood Corner | xuất ngày 01/07/2026 | chưa thanh toán",
        # "xác nhận" xuất hiện nhưng người dùng hỏi TRẠNG THÁI, không nhờ làm.
        "Hóa đơn INV/2026/00020 đã được xác nhận thanh toán chưa?",
        False),
    WriteSuggestCase(
        _CK, "Khách Azure Interior | đặt 2 Desk Pad",
        # Hỏi QUY TRÌNH, không nhờ thực hiện — ca âm khó nhất trong bộ.
        "Quy trình áp chiết khấu cho một đơn hàng gồm những bước nào?",
        False),
]
