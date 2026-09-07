"""Thước chấm điểm bậc 2 — MỘT bản duy nhất cho cả cổng A lẫn bộ hiệu chỉnh.

Vì sao module này tồn tại: `_score`, `_words_in_bbox` và `_tokens` từng có HAI
bản — một trong `backend/tools/calibrate_table.py`, một trong
`backend/tests/ocr/test_table_gate_vector.py` — và hai bản ĐÃ LỆCH NHAU: bản
cổng A xử lý ô XUỐNG DÒNG (loại khỏi vế `kept`), bản hiệu chỉnh thì không.
Nghĩa là bảng số đo dùng để chốt `GAP_FACTOR`/`SUPPORT_RATIO` được sinh bởi
một cái thước KHÁC cái thước cổng A đang gác — hai con số không cùng thang.
Đúng lớp lỗi "đường code thứ hai phải giữ đồng bộ" mà spec §3 cấm.

Module LÁ: chỉ nhận lưới `list[list[str]]` + đáp án + text phẳng, không biết
gì về pytest, pdfplumber hay đường dẫn tệp.
"""
import re

MIN_TOKEN_LEN = 3


def words_in_bbox(words, bbox, scale):
    """Chỉ giữ từ nằm trong khung bảng.

    `bbox` theo ĐIỂM (pdfplumber), toạ độ từ theo PIXEL ảnh — nhân `scale`
    = DPI/72 để đưa về cùng hệ.
    """
    x0, top, x1, bot = (v * scale for v in bbox)
    return [w for w in words
            if x0 <= w.left and w.left + w.width <= x1
            and top <= w.top and w.top + w.height <= bot]


def tokens(cell) -> list[str]:
    """Token đủ dài để tìm trong text phẳng mà không khớp bừa."""
    return [t for t in (cell or "").split() if len(t) >= MIN_TOKEN_LEN]


def score(answer: list[list], grid: list[list[str]], flat_text: str):
    """(kept, keep_total, split, split_total, unreadable, wrapped).

    ĐỐI XỨNG, và đó là điểm mấu chốt:
      vế 1 KHÔNG TÁCH NHẦM — mọi token của MỘT ô đáp án nằm trong CÙNG MỘT ô
                             lưới;
      vế 2 KHÔNG GỘP NHẦM  — HAI ô KHÁC NHAU trong cùng một hàng đáp án KHÔNG
                             được rơi chung một ô lưới.

    Chỉ có vế 1 thì một lưới MỘT CỘT đạt điểm tuyệt đối miễn phí — đo được:
    `gap_factor=1000` vẫn đạt 0,9706 trên `luat-thuexuatnhapkhau.pdf` tr.14.
    Chỉ có vế 2 thì tách vụn từng từ lại thắng tuyệt đối. Điểm cuối lấy MIN
    của hai vế nên cả hai hướng suy biến đều bị phạt.

    Ô nào tầng đọc không đọc được thì loại khỏi CẢ HAI mẫu số và đếm riêng —
    chấm nó là chấm chất lượng OCR, không phải việc của bậc 2 (spec §2.4).

    Ô XUỐNG DÒNG bị loại khỏi CẢ HAI vế và đếm riêng thành `wrapped`. Spec §10
    ghi rõ ô xuống dòng NGOÀI PHẠM VI bậc 2: bậc 2 gom hàng theo `line_id` nên
    token của một ô vắt qua nhiều dòng vật lý nằm ở các HÀNG lưới khác nhau,
    không bao giờ thoả "cùng một ô", kể cả khi cột tách hoàn toàn đúng.

    LOẠI KHỎI CẢ HAI VẾ, không phải chỉ vế `kept` (sửa 2026-09-07, phát hiện
    I1 của review toàn nhánh): bản trước loại ô `wrapped` khỏi `kept` nhưng
    vẫn cho nó tham gia vế `tach`, và ở vế đó nó ăn tín dụng MIỄN PHÍ — một ô
    không bao giờ nằm trọn trong một ô lưới thì cũng không bao giờ "rơi chung
    một ô" với ô khác, nên mọi cặp có nó đều tính là TÁCH ĐÚNG. Đo được:
    `ssc_bieumau.pdf` tr.4 ở cấu hình THỬ PHÁ `gap_factor=1000` (lưới MỘT cột)
    vẫn đạt `min=0,8333` — trên ngưỡng cổng, tức XANH ở đúng cấu hình suy biến
    mà phép thử phá sinh ra để bắt.
    """
    flat = flat_text.replace("\n", " ")
    kept = keep_total = split = split_total = unreadable = wrapped = 0
    for row in answer:
        readable = []
        for cell in row:
            t = tokens(cell)
            if not t:
                continue
            if not all(x in flat for x in t):
                unreadable += 1
                continue
            if "\n" in (cell or ""):
                wrapped += 1
                continue
            readable.append(t)
        for t in readable:
            keep_total += 1
            if any(all(x in c for x in t) for h in grid for c in h):
                kept += 1
        for i in range(len(readable)):
            for j in range(i + 1, len(readable)):
                split_total += 1
                shared = any(all(x in c for x in readable[i])
                             and all(y in c for y in readable[j])
                             for h in grid for c in h)
                if not shared:
                    split += 1
    return kept, keep_total, split, split_total, unreadable, wrapped


# Chuỗi tiền kiểu Việt: >=4 chữ số, dấu chấm phân nhóm nghìn, âm đặt trong
# ngoặc đơn theo lệ kế toán. Cố ý KHÔNG khớp mã số 2-3 chữ số hay năm.
MONEY = re.compile(r"^\(?\d{1,3}(?:\.\d{3})+\)?$")


def score_unlabelled(grid: list[list[str]]) -> tuple[int, int, int, int]:
    """(separated, money_rows, filled_cells, total_cells) — KHÔNG cần đáp án.

    Dùng cho scan thật, nơi không có bản vector để đối chiếu. Báo cáo tài chính
    TỰ mang đáp án: mỗi DÒNG có >=2 chuỗi tiền PHÂN BIỆT là một hàng bảng, và
    câu hỏi mở đầu spec §1 — "số nào là cuối kỳ, số nào là đầu năm" — tương
    đương với "hai chuỗi đó có nằm ở hai Ô KHÁC NHAU không".

    PHẢI dùng CẢ HAI cặp trả về. Đây là chỗ nhánh này đã trả giá bốn lần:
    `separated/money_rows` chỉ phạt GỘP NHẦM — một lưới tách vụn thành 30 cột
    vẫn đạt điểm tuyệt đối, vì hai token vẫn "ở ô khác nhau" (đúng giới hạn R2
    của review toàn nhánh). `filled_cells/total_cells` là vế ngược: tách vụn
    sinh cột rỗng nên mật độ ô sụp. Chấm một vế là không đo gì.

    So khớp bằng TOKEN CHÍNH XÁC chứ không phải chuỗi con — `'160'` nằm trong
    `'15.618.160.768'` (phát hiện C2 của review toàn nhánh).
    """
    separated = money_rows = 0
    for row in grid:
        money = sorted({t for cell in row for t in cell.split() if MONEY.match(t)})
        if len(money) < 2:
            continue
        where = {}
        for m in money:
            hit = [i for i, cell in enumerate(row) if m in cell.split()]
            if len(hit) != 1:      # cùng một chuỗi ở nhiều ô -> không kết luận được
                where = None
                break
            where[m] = hit[0]
        if where is None:
            continue
        money_rows += 1
        if len(set(where.values())) == len(money):
            separated += 1
    filled = sum(1 for row in grid for cell in row if cell.strip())
    total = sum(len(row) for row in grid)
    return separated, money_rows, filled, total
