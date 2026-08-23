"""Nhãn tiếng Việt cho trường `state` của Odoo — nguồn dùng chung.

Vì sao tồn tại (mục 21, đo sống 2026-08-23): hỏi "5 đơn bán gần nhất kèm
trạng thái" thì trợ lý trả về `draft` và `sale` — chữ nội bộ của Odoo, vô
nghĩa với người dùng Việt không biết hệ thống.

Khuôn này ĐÃ CÓ ở `mrp.py` từ trước (`_STATE_LABELS`) nhưng chỉ phủ lệnh sản
xuất; đơn bán, đơn mua, hóa đơn và phiếu kho vẫn trả chữ thô. Gom về một chỗ
thay vì chép sang bốn module: bốn bản sao của cùng một bảng là cách nó trôi.

CÙNG một mã `state` mang nghĩa KHÁC nhau tuỳ model — `sale` là "đã xác nhận"
với đơn bán nhưng không tồn tại ở hóa đơn; `done` là "hoàn tất" ở lệnh sản
xuất nhưng là "đã giao" ở phiếu kho. Nên bảng tra theo (model, state), và
`nhan_trang_thai` NHẬN model làm tham số bắt buộc.

Không dịch được thì TRẢ NGUYÊN mã: một mã lạ hiện ra thô còn hơn bị nuốt
thành chuỗi rỗng, và nó là tín hiệu để bổ sung bảng này.
"""

_CHUNG = {"draft": "nháp", "cancel": "đã hủy", "cancelled": "đã hủy"}

_THEO_MODEL: dict[str, dict[str, str]] = {
    "sale.order": {**_CHUNG, "sent": "đã gửi báo giá",
                   "sale": "đã xác nhận", "done": "đã khóa"},
    "purchase.order": {**_CHUNG, "sent": "đã gửi hỏi giá",
                       "to approve": "chờ duyệt", "purchase": "đã xác nhận",
                       "done": "đã khóa"},
    "account.move": {**_CHUNG, "posted": "đã phát hành"},
    "account.payment": {**_CHUNG, "posted": "đã ghi sổ",
                        "in_process": "đang xử lý", "paid": "đã thanh toán"},
    "stock.picking": {**_CHUNG, "waiting": "chờ hàng khác",
                      "confirmed": "chờ hàng", "assigned": "sẵn sàng",
                      "done": "đã giao"},
    "mrp.production": {**_CHUNG, "confirmed": "đã xác nhận",
                       "progress": "đang sản xuất", "to_close": "chờ đóng",
                       "done": "hoàn tất"},
}


def nhan_trang_thai(model: str, state) -> str:
    """Nhãn tiếng Việt của `state` trong `model`. Không biết ⇒ trả nguyên mã."""
    if not state:
        return ""
    return _THEO_MODEL.get(model, _CHUNG).get(str(state), str(state))
