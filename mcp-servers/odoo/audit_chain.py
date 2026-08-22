"""Tính hash-chain (sha256 nối tiếp) cho mỗi dòng mcp_call_log — dùng chung
cho phía ghi (event_log.py) và phía kiểm tra (verify_audit_chain.py) để
công thức hash không bao giờ lệch nhau giữa 2 nơi. Xem docs/superpowers/
specs/2026-07-23-audit-trail-hash-chain-design.md."""
import hashlib
import json
from datetime import timezone

GENESIS_HASH = "0" * 64


# Trần đệ quy khi bóc khoá tham số. Payload Odoo lồng nhau vài tầng là bình
# thường (domain trong list trong list); sâu hơn thì gần như chắc chắn là dữ
# liệu chứ không phải cấu trúc, và một vệt kiểm toán không được để đầu vào của
# người dùng quyết định nó chạy bao lâu.
ARGS_DEPTH_MAX = 6
ARGS_KEYS_MAX = 40


def args_fingerprint(args, kwargs) -> tuple[str | None, list[str]]:
    """(digest, danh sách khoá) của tham số một lệnh gọi Odoo.

    Trả về sha256 (16 ký tự đầu) của args+kwargs đã chuẩn hoá, KÈM tên các
    khoá xuất hiện trong đó — **không kèm giá trị nào**. Quyết định 2026-08-22
    của chủ dự án: tham số mang tên khách, số tiền, công nợ; vệt kiểm toán
    không được thành nơi chứa dữ liệu khách hàng.

    Cặp này trả lời được "có phải cùng một lệnh gọi không", "bản ghi có bị sửa
    không", và "lệnh này động tới trường nào" — nhưng KHÔNG trả lời được "số
    tiền là bao nhiêu". Đó là đánh đổi đã chọn, không phải thiếu sót.

    Không bao giờ ném: một lỗi ở đây mà làm hỏng tool thì vệt kiểm toán trở
    thành nguồn sự cố thay vì công cụ điều tra.
    """
    try:
        canon = json.dumps([args, kwargs], ensure_ascii=False, sort_keys=True,
                           default=str)
        digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]
        khoa: set[str] = set()

        def _boc(x, sau: int) -> None:
            if sau > ARGS_DEPTH_MAX or len(khoa) >= ARGS_KEYS_MAX:
                return
            if isinstance(x, dict):
                for k, v in x.items():
                    khoa.add(str(k))
                    _boc(v, sau + 1)
            elif isinstance(x, (list, tuple)):
                for v in x:
                    _boc(v, sau + 1)

        _boc(args, 0)
        _boc(kwargs, 0)
        return digest, sorted(khoa)[:ARGS_KEYS_MAX]
    except Exception:                                       # noqa: BLE001
        return None, []


def compute_entry_hash(prev_hash, created_at, event_type, caller, tool_name,
                       model_name, operation, duration_ms, error_code,
                       error_message, http_user=None, args_digest=None,
                       args_keys=None) -> str:
    """sha256 của JSON-encode (tránh đụng hạng ranh giới field) prev_hash +
    các field của 1 dòng mcp_call_log. created_at LUÔN chuẩn hoá về UTC
    trước khi format — nếu không, giá trị đọc lại từ Postgres (TIMESTAMPTZ,
    có thể trả tzinfo khác lúc ghi dù CÙNG một thời điểm) sẽ cho ra chuỗi
    isoformat khác, khiến verify luôn báo sai dù không ai giả mạo gì."""
    ts = created_at.astimezone(timezone.utc).isoformat()
    # http_user/args_digest/args_keys PHẢI nằm trong chuỗi băm. Để chúng ngoài
    # thì đúng hai trường quý nhất của một cuộc điều tra — AI đã gọi và gọi
    # CÁI GÌ — sửa được mà verify vẫn báo xanh. Chủ dự án đã chọn phương án
    # "dọn rác test + khởi động chuỗi mới" (2026-08-22) chính là để trả giá
    # đứt chuỗi MỘT LẦN đổi lấy điều này.
    chain_data = json.dumps(
        [prev_hash, ts, event_type, caller, tool_name, model_name, operation,
         duration_ms, error_code, error_message,
         http_user, args_digest, list(args_keys) if args_keys else None],
        ensure_ascii=False)
    return hashlib.sha256(chain_data.encode("utf-8")).hexdigest()
