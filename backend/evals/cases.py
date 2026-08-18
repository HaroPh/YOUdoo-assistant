# backend/evals/cases.py
"""Eval sets cho gate M3 (ADR-009) — đo model THẬT, không mock.

INTENT_CASES: (câu tiếng Việt, intent kỳ vọng) — 5 nhánh × 8.
CONFIRM_CASES: (reply, nhãn kỳ vọng) — cases chọn để NÉ keyword fast-path
(confirmation.py xử lý 'có/không/ok/hủy...' bằng keyword, không tới LLM),
nên eval này đo đúng chất lượng LLM fallback.
"""

INTENT_CASES = [
    # erp_read
    ("tồn kho Desk Pad còn bao nhiêu?", "erp_read"),
    ("liệt kê các đơn bán tháng này", "erp_read"),
    ("doanh thu tháng 6 là bao nhiêu?", "erp_read"),
    ("top 5 sản phẩm bán chạy nhất", "erp_read"),
    ("chi tiết đơn S00042", "erp_read"),
    ("khách Azure Interior có bao nhiêu đơn chưa thanh toán?", "erp_read"),
    ("hóa đơn nào đang quá hạn?", "erp_read"),
    ("còn lô nào của Large Cabinet trong kho không?", "erp_read"),
    ("định mức nguyên liệu của Drawer gồm những gì?", "erp_read"),
    ("sản phẩm nào đang cần đặt hàng lại?", "erp_read"),
    ("đơn mua nào có số lượng nhận và hóa đơn không khớp nhau?", "erp_read"),
    ("phiếu giao hàng nào đang trễ hạn?", "erp_read"),
    ("công nợ hiện tại của khách Azure Interior là bao nhiêu?", "erp_read"),
    ("danh sách cơ hội đang mở gần đây", "erp_read"),
    # erp_write
    ("tạo báo giá cho Azure Interior, 2 Large Cabinet", "erp_write"),
    ("xác nhận đơn S00042", "erp_write"),
    # RANH GIỚI SOP (SP-2a §5.1) — ĐỪNG "sửa giúp" kỳ vọng này. Câu không nhắc
    # tới QUY TRÌNH nên đi tier-1 (erp_write → planner), KHÔNG đi SOP
    # giao-hang. Ranh giới cũ "có chữ 'bán' hay không" đã chết (nó không bảo
    # vệ được: với người dùng, có/không có chữ "bán" là một ý). Ranh giới mới
    # bảo vệ được: CÓ ngôn ngữ quy trình → SOP; KHÔNG có → tier-1. Đi tier-1
    # còn rẻ hơn (một call planner thay vì cả ReAct loop) và vẫn có confirm-gate
    # riêng. Đo trực tiếp bởi SOP_SELECT_CASES.
    ("giao hàng cho đơn S00040 luôn nhé", "erp_write"),
    ("đổi số lượng Desk Pad trong S00043 thành 5", "erp_write"),
    ("tạo đơn mua 10 Cabinet with Doors từ Wood Corner", "erp_write"),
    ("xuất hóa đơn cho đơn S00039", "erp_write"),
    ("điều chỉnh tồn kho Desk Pad về 100", "erp_write"),
    ("làm ơn tạo báo giá mới nhất cho khách Gemini Furniture, số lượng 3 bàn", "erp_write"),  # từng misroute
    ("tạo lead mới cho khách Green Valley, quan tâm sản phẩm bàn ghế văn phòng", "erp_write"),
    ("tạo lệnh sản xuất 20 Drawer", "erp_write"),
    ("cập nhật định mức nguyên liệu của Drawer, thêm 2 ốc vít", "erp_write"),
    ("chuyển 10 Desk Pad từ kho chính sang kho phụ", "erp_write"),
    ("loại bỏ 3 Desk Pad bị hỏng khỏi kho", "erp_write"),
    ("khách Azure Interior trả lại 1 Large Cabinet đã giao", "erp_write"),
    ("ghi nhận thanh toán cho hóa đơn INV/2026/00016", "erp_write"),
    # rag
    ("chính sách đổi trả hàng như thế nào?", "rag"),
    ("SLA giao hàng nội thành là bao lâu?", "rag"),
    ("quy trình xử lý khiếu nại khách hàng?", "rag"),
    ("hàng giảm giá có được hoàn trả không?", "rag"),
    ("điều kiện bảo hành sản phẩm gỗ?", "rag"),
    ("quy định về đặt cọc cho đơn hàng lớn?", "rag"),
    ("thời gian xử lý hoàn tiền là bao lâu?", "rag"),
    ("SOP nhập kho gồm những bước nào?", "rag"),
    # mixed
    ("đơn S00042 có được miễn phí giao không theo chính sách?", "mixed"),
    ("đơn của Azure Interior trễ SLA chưa?", "mixed"),
    ("đơn S00040 của khách này đủ điều kiện chiết khấu theo bảng giá không?", "mixed"),
    ("theo chính sách đổi trả, đơn S00035 còn hạn đổi không?", "mixed"),
    ("tồn kho Desk Pad có dưới ngưỡng cảnh báo trong SOP không?", "mixed"),
    ("đơn nào đang vi phạm SLA giao hàng?", "mixed"),
    ("giá trong đơn S00039 có khớp bảng giá hiện hành không?", "mixed"),
    ("khách Wood Corner có đơn nào vượt hạn mức công nợ theo chính sách không?", "mixed"),
    ("lệnh sản xuất mới có cần kiểm tra chất lượng theo SOP trước khi hoàn tất không?", "mixed"),
    # unknown
    ("chào bạn", "unknown"),
    ("cảm ơn nhé", "unknown"),
    ("bạn là ai?", "unknown"),
    ("thời tiết hôm nay thế nào?", "unknown"),
    ("kể chuyện cười đi", "unknown"),
    ("1+1 bằng mấy?", "unknown"),
    ("bạn đang dùng model gì vậy?", "unknown"),
    ("hay đấy", "unknown"),
]

CONFIRM_CASES = [
    # CONFIRM kỳ vọng
    ("chốt luôn đi", "confirm"),
    ("vậy triển đi nhé", "confirm"),
    ("gật", "confirm"),
    ("duyệt nhé", "confirm"),
    ("cứ thế mà làm", "confirm"),
    ("chốt đơn giùm mình", "confirm"),
    ("êm, quất luôn", "confirm"),
    ("lên đơn đi bạn", "confirm"),
    # CANCEL kỳ vọng
    ("để sau đi", "cancel"),
    ("từ từ đã", "cancel"),
    ("chưa vội đâu", "cancel"),
    ("đợi mình xem lại đã", "cancel"),
    ("bỏ qua giùm", "cancel"),
    ("để mình suy nghĩ thêm", "cancel"),
    ("hôm khác làm", "cancel"),
    ("sai rồi, làm lại cái khác", "cancel"),
    # UNCLEAR kỳ vọng (câu hỏi / yêu cầu sửa / mơ hồ)
    ("giá này rẻ hơn hôm qua à?", "unclear"),
    ("đơn này của khách nào vậy?", "unclear"),
    ("2 cái hay 3 cái nhỉ?", "unclear"),
    ("bạn nghĩ sao?", "unclear"),
    ("quy trình này hoạt động ra sao?", "unclear"),
    ("cho mình đổi thành 5 cái được chứ?", "unclear"),
    ("hmm để coi", "unclear"),
    ("à mà giá bao nhiêu ấy nhỉ?", "unclear"),
]

# ── Chitchat eval-gate (khóa #10, ADR-009) ────────────────────────────────────
# respond_unknown() KHÔNG có system prompt (backend/src/agents/nodes.py) — nếu
# router misroute 1 yêu cầu ERP thật vào đây, model có thể bịa đã thực hiện
# hành động (không tool nào chạy thật — rủi ro trust/UX, không phải data-sai).
# Gate tuyệt đối: violations phải = 0. Heuristic từ khóa, không LLM-judge —
# residual: có thể bỏ sót cách diễn đạt không khớp danh sách (spec §7).

HALLUCINATION_MARKERS = [
    "đã tạo", "đã xác nhận", "đã hủy", "đã huỷ", "đã giao", "đã nhận hàng",
    "đã xuất hóa đơn", "đã xuất hoá đơn", "đã điều chỉnh", "đã cập nhật",
    # "đã lưu" (bare) từng false-positive trên "đã lưu ý" (= đã ghi nhận, không
    # liên quan hành động ERP) — thay bằng cụm cụ thể có tân ngữ (review finding).
    "đã lưu đơn", "đã lưu thông tin", "đã lưu thay đổi",
    "hoàn tất giao dịch", "thực hiện thành công", "giao dịch thành công",
]

CHITCHAT_CASES = (
    # Nhóm A: chit-chat thật (tái dùng đúng 8 câu nhãn "unknown" trong
    # INTENT_CASES — tránh trùng lặp nội dung, cùng input, khác tầng kiểm tra).
    [text for text, label in INTENT_CASES if label == "unknown"]
    # Nhóm B: near-miss — hình dạng giống yêu cầu ERP thật, đủ mơ hồ để có thể
    # bị router misroute vào "unknown" (input thực tế nhất có thể chạm node này).
    + [
        "chốt đơn kia luôn nhé",
        "giao hàng được chưa vậy",
        "hủy giùm cái đơn lúc nãy",
        "tồn kho còn không ta",
        "báo giá xong chưa vậy",
        "đơn đó sao rồi",
        "làm luôn đi đừng hỏi nữa",
        "cập nhật giúp cái kia với",
    ]
)

# ── planner set (SP-0) ───────────────────────────────────────────────────────
# (câu tiếng Việt, tool kỳ vọng, args BẮT BUỘC khớp). Args chỉ khai báo key
# then chốt — key optional model tự thêm KHÔNG tính sai (planner còn 2 lớp
# chặn phía sau: confirm-gate + forbid_extra_kwargs tầng MCP).
# Tên tool + tên arg lấy ĐÚNG theo WRITE_PLANNER_PROMPT (prompts.py).
PLANNER_CASES = [
    # chuỗi bán
    ("xác nhận đơn S00042", "confirm_sale_order", {"order_ref": "S00042"}),
    ("tạo báo giá cho Azure Interior, 2 Large Cabinet", "create_quotation",
     {"partner_name": "Azure Interior",
      "lines": [{"product": "Large Cabinet", "qty": 2}]}),
    # RANH GIỚI SOP (SP-2a §5.1) — xem chú thích ở INTENT_CASES. Lệnh trực tiếp
    # không nhắc quy trình → planner tier-1 chọn deliver_order, KHÔNG phải SOP.
    ("giao hàng cho đơn S00040", "deliver_order", {"order_ref": "S00040"}),
    ("tạo hóa đơn từ đơn S00042", "create_invoice_from_order",
     {"order_ref": "S00042"}),
    ("đổi số lượng Desk Pad trong S00043 thành 5", "update_quotation_lines",
     {"order_ref": "S00043"}),
    # chuỗi mua
    ("xác nhận đơn mua P00003", "confirm_purchase_order", {"order_ref": "P00003"}),
    ("tạo RFQ cho Hồng Phúc, 10 Screw", "create_rfq",
     {"partner_name": "Hồng Phúc", "lines": [{"product": "Screw", "qty": 10}]}),
    ("nhận hàng cho đơn mua P00003", "receive_order", {"order_ref": "P00003"}),
    ("tạo hóa đơn nhà cung cấp từ đơn mua P00003", "create_bill_from_po",
     {"order_ref": "P00003"}),
    # phiếu kho — bẫy THẬT round 11 (WH/IN bị nhầm sang confirm_purchase_order)
    ("xác nhận phiếu WH/OUT/00001", "validate_picking",
     {"picking_ref": "WH/OUT/00001"}),
    ("xác nhận phiếu WH/IN/00005", "validate_picking",
     {"picking_ref": "WH/IN/00005"}),
    # kho
    ("đặt tồn kho Desk Pad về 100", "inventory_adjustment",
     {"new_qty": 100, "product_name": "Desk Pad"}),
    ("chuyển 5 Screw từ Shelf 1 sang Shelf 2", "internal_transfer",
     {"product_name": "Screw", "qty": 5,
      "from_location": "Shelf 1", "to_location": "Shelf 2"}),
    ("ghi nhận 3 Large Cabinet bị hỏng", "scrap_product",
     {"product_name": "Large Cabinet", "qty": 3}),
    # CRM
    ("tạo lead mới cho anh Trần Phúc, sđt 0901234567", "create_lead",
     {"phone": "0901234567"}),
    ("chuyển lead Modernize old offices thành cơ hội", "convert_lead",
     {"lead_ref": "Modernize old offices"}),
    ("lên lịch gọi cho lead Modernize old offices", "log_activity",
     {"res_model": "crm.lead", "ref": "Modernize old offices", "activity_type": "Call"}),
    # sản xuất
    ("tạo lệnh sản xuất 10 Drawer", "create_manufacturing_order",
     {"product_name": "Drawer", "qty": 10}),
    ("xác nhận lệnh sản xuất WH/MO/00007", "confirm_manufacturing_order",
     {"order_ref": "WH/MO/00007"}),
    ("hoàn tất lệnh sản xuất WH/MO/00007", "complete_manufacturing_order",
     {"order_ref": "WH/MO/00007"}),
    # BoM
    ("tạo định mức cho Office Lamp gồm 2 Screw", "create_bom",
     {"product_name": "Office Lamp",
      "components": [{"product": "Screw", "qty": 2}]}),
    # trả hàng / hoàn tiền
    ("trả hàng cho đơn S00042", "return_order", {"order_ref": "S00042"}),
    ("tạo credit memo cho hóa đơn INV/2026/00017", "create_credit_memo",
     {"invoice_ref": "INV/2026/00017"}),
    # nhà cung cấp (round 12)
    ("thêm nhà cung cấp mới tên Công ty ABC", "create_vendor",
     {"name": "Công ty ABC"}),
    ("khai giá Screw từ Hồng Phúc là 12000", "update_vendor_pricing",
     {"vendor_name": "Hồng Phúc", "product": "Screw", "price": 12000}),
]

# Mọi tool GHI hợp lệ — dùng để phân biệt "chọn sai tool ghi" (nguy hiểm) với
# "other"/thiếu tool ("không biết", an toàn). Đồng bộ WRITE_PLANNER_PROMPT.
WRITE_TOOL_NAMES = frozenset({
    "confirm_sale_order", "confirm_purchase_order", "post_invoice",
    "create_invoice_from_order", "validate_picking", "deliver_order",
    "receive_order", "create_bill_from_po", "register_payment",
    "create_quotation", "create_rfq", "update_quotation_lines",
    "update_rfq_lines", "inventory_adjustment", "internal_transfer",
    "scrap_product", "create_lead", "convert_lead", "log_activity",
    "close_activity",
    "create_manufacturing_order", "confirm_manufacturing_order",
    "complete_manufacturing_order", "create_bom", "update_bom_lines",
    "return_order", "create_credit_memo", "create_vendor",
    "update_vendor_pricing", "create_bulk_rfq",
    # 4 coordinator gửi mail (mail_write.py, MAIL_COORDINATOR_CFGS) — GỬI
    # THẬT, KHÔNG THỂ THU HỒI (mail rời hệ thống, khác một bản ghi ERP còn
    # sửa/hủy được), nên chọn nhầm sang một trong 4 tool này là misroute
    # NGUY HIỂM NHẤT hệ thống — phải nằm trong tập này để dangerous_misroute
    # (run_eval.py) tính đúng, không rơi vào bucket an toàn.
    "send_order_confirmation_email", "send_quotation_email",
    # send_delivery_email thiếu ở đây tới tận 2026-08-14 (đợt mail-trigger-points
    # thêm 4 tool mail nhưng sót tool thứ năm). Hệ quả: một misroute sang nó bị
    # run_eval xếp vào rổ AN TOÀN thay vì rổ nguy hiểm, tức dangerous_misroute
    # MÙ với đúng tool gửi mail ra ngoài. Bất biến prompt↔bảng ở
    # tests/agents/test_close_activity_roles.py giờ chặn lần lệch thứ ba.
    "send_rfq_email", "send_invoice_email", "send_delivery_email",
})

# ── read set (SP-0) ──────────────────────────────────────────────────────────
# (câu hỏi, tool erp_query kỳ vọng, args then chốt, entity_keys).
# entity_keys = arg mang TÊN/MÃ thực thể → giá trị phải xuất hiện trong câu
# hỏi; nếu không = bịa (lớp lỗi thật round 6/round 3). Tool + tên arg lấy
# đúng theo backend/src/erp_query/ và SYSTEM_PROMPT.
READ_CASES = [
    ("tồn kho Desk Pad còn bao nhiêu?", "get_stock",
     {"product": "Desk Pad"}, ("product",)),
    ("liệt kê đơn bán tháng này", "list_sale_orders", {}, ()),
    ("chi tiết đơn S00042", "get_sale_order_detail",
     {"ref": "S00042"}, ("ref",)),
    ("doanh thu tháng này là bao nhiêu?", "sales_summary", {}, ()),
    # top_products(by, period) KHÔNG có tham số "limit" trong args_schema thật
    # (backend/src/erp_query/tools.py) — dù hàm nghiệp vụ bên dưới có limit,
    # tool LangChain không expose nó nên model không thể/không nên đưa "limit"
    # vào tool call. exp_args để rỗng như các case tham số-tùy-chọn khác.
    ("top 5 sản phẩm bán chạy nhất", "top_products", {}, ()),
    # Đo 2026-08-15: baseline "1.000" cũ (n=20, lưu 23510ae 2026-07-30) đo
    # TRƯỚC KHI get_customer_detail được đăng ký làm tool (c4fcaf3, 2026-08-07)
    # và trước khi SYSTEM_PROMPT có quy tắc "chủ động gọi get_customer_detail
    # khi câu hỏi xoay quanh một khách hàng cụ thể" (91c05f2/c46081d, cùng
    # ngày). Lúc đo baseline, get_customer_detail CHƯA TỒN TẠI trong bộ tool
    # — model không thể đã chọn nó. Kỳ vọng find_customer là LỖI THỜI, không
    # phải model bất ổn: get_customer_detail mới là câu trả lời ĐÚNG theo
    # đúng quy tắc prompt hiện hành (trả hồ sơ đầy đủ — liên hệ/thuế/điều
    # khoản — hợp với "thông tin thế nào?" hơn find_customer, vốn chỉ tìm
    # ứng viên+ID). Xác nhận bằng cô lập (revert cả prompt lẫn tool list về
    # bản trước nhánh feat/morning-work-queue): CÙNG kết quả — xác nhận
    # nguyên nhân không nằm ở nhánh đó, mà ở khoảng cách 8 ngày giữa lúc đo
    # baseline và lúc get_customer_detail ra đời.
    ("khách Azure Interior thông tin thế nào?", "get_customer_detail",
     {"name": "Azure Interior"}, ("name",)),
    ("hóa đơn nào đang quá hạn?", "get_overdue_invoices", {}, ()),
    ("công nợ của khách Azure Interior là bao nhiêu?", "get_partner_balance",
     {"name": "Azure Interior"}, ("name",)),
    ("còn lô nào của Large Cabinet trong kho không?", "get_lots",
     {"product": "Large Cabinet"}, ("product",)),
    ("sản phẩm nào đang cần đặt hàng lại?", "list_reorder_needed", {}, ()),
    ("định mức nguyên liệu của Drawer gồm những gì?", "get_bom_detail",
     {"product": "Drawer"}, ("product",)),
    ("các lệnh sản xuất đang mở", "list_manufacturing_orders", {}, ()),
    ("đơn mua nào có hóa đơn vượt thực nhận?", "list_po_mismatches", {}, ()),
    ("đối soát đơn mua P00003", "check_po_matching",
     {"ref": "P00003"}, ("ref",)),
    ("danh sách nhà cung cấp", "list_suppliers", {}, ()),
    ("nhà cung cấp nào bán Screw?", "get_product_suppliers",
     {"product": "Screw"}, ("product",)),
    ("phiếu giao hàng nào đang trễ hạn?", "list_late_deliveries", {}, ()),
    ("hồ sơ nhà cung cấp Hồng Phúc", "get_supplier_detail",
     {"name": "Hồng Phúc"}, ("name",)),
    ("danh sách cơ hội đang mở", "list_crm_leads", {}, ()),
    ("chi tiết đơn mua P00003", "get_purchase_order_detail",
     {"ref": "P00003"}, ("ref",)),
    # ── Bản tin việc cần xử lý (2026-08-15) ─────────────────────────────────
    # Nhóm A — câu buổi sáng phải đi tới tool tổng hợp. Đo trước khi có tool
    # này: 3/3 vai trả lời "không có việc nào được giao" trong khi hệ thống
    # có 29 phiếu trễ và 22 hóa đơn quá hạn.
    ("hôm nay tôi cần xử lý gì?", "list_pending_work", {}, ()),
    ("có việc gì cần làm không?", "list_pending_work", {}, ()),
    ("còn gì nữa không?", "list_pending_work", {}, ()),
    # Nhóm B — CHỐNG CƯỚP. Câu nêu rõ MỘT loại chứng từ phải đi thẳng tool
    # của loại đó, không bị hút về tool tổng hợp. Thiếu nhóm này thì tool mới
    # có thể nuốt hết mà điểm vẫn đẹp.
    ("có phiếu giao nào trễ hạn không?", "list_late_deliveries", {}, ()),
    ("liệt kê hóa đơn quá hạn", "get_overdue_invoices", {}, ()),
    ("hàng nào cần đặt bổ sung?", "list_reorder_needed", {}, ()),
    # Câu NGHIỆM THU SỐNG nguyên văn của tính năng bàn giao chéo bộ phận
    # (docs/superpowers/plans/2026-08-13-cross-department-handoff.md:874, hàng
    # #3 bảng nghiệm thu, vai kế toán). Đây là ca dễ bị list_pending_work cướp
    # nhất — dòng prompt của tool mới tự nhận "có việc gì không" làm trigger,
    # gần y hệt về mặt chữ. Nếu cướp, người dùng nhận một con số trần trụi
    # thay vì tóm tắt + hạn + chứng từ của việc bàn giao: hồi quy IM LẶNG của
    # một tính năng đã chạy thật. list_my_activities TRƯỚC ĐÂY CHƯA HỀ có ca
    # eval nào, ở bất kỳ set nào — đây là lớp phủ đầu tiên của nó.
    ("có việc gì chuyển cho tôi không?", "list_my_activities", {}, ()),
]

# ── synthesis set (SP-0) ─────────────────────────────────────────────────────
# (topic fixture, câu hỏi, kind, expect).
# kind="answerable" → tài liệu ĐỦ, expect = chuỗi phải có trong câu trả lời.
# kind="insufficient" → tài liệu KHÔNG đề cập, phải trả KHÔNG_ĐỦ_THÔNG_TIN.
# Topic đổi so với brief gốc (round: đọc corpus thật trước khi viết case) —
# "quy_trinh_mua_hang" bị bỏ vì KHÔNG có tài liệu nguồn tương ứng trong RAG DB
# thật (không module purchase-approval nào được index); thay bằng
# "chinh_sach_thanh_toan" (payment_policy.docx), khớp corpus thật có sẵn.
# expect COPY NGUYÊN VĂN từ chunk thật đọc bằng script Task 4 Step 2
# (backend/evals/fixtures/chunks.json) — không đoán/viết tay.
# ── grounded_acc: expect có thể là tuple nhiều phương án (SP-1C1) ───────────
# Chạy gate thật lần 1 phát hiện case "Hàng giảm giá có được hoàn trả không?"
# (expect="không được hoàn trả") bị model diễn giải lại thành "không được áp
# dụng chính sách hoàn trả" — đúng nghĩa, không bịa, nhưng so nguyên văn thì
# trượt. Chạy lại riêng --set synthesis xác nhận ổn định (cùng 1 case, cùng
# response y hệt) — không phải nhiễu lấy mẫu.
# Quyết định (sau 2 vòng review độc lập bác bỏ hướng "nới lỏng chung theo
# thứ tự từ" — luôn tìm được câu trả lời SAI lọt qua bất kể siết rào tới
# đâu): KHÔNG sửa cách so khớp trong run_eval.py. Thay vào đó, `expect` có
# thể là MỘT TUPLE nhiều chuỗi — `_grounded_match()` so khớp NGUYÊN VĂN với
# BẤT KỲ phương án nào trong đó. Mỗi phương án là một diễn giải THẬT đã quan
# sát được, không phải suy luận ngữ nghĩa/mờ chung chung — không có bề mặt
# lọt sai mới nào so với so khớp nguyên văn gốc.
SYNTHESIS_CASES = [
    # sla_giao_hang ← sla.docx "Thỏa thuận mức dịch vụ nhà cung cấp"
    ("sla_giao_hang", "Đơn hàng khẩn cấp được xử lý trong bao lâu?",
     "answerable", "3 ngày"),
    ("sla_giao_hang", "Phạt chậm trễ giao hàng là bao nhiêu mỗi ngày?",
     "answerable", "0,5%"),
    # chinh_sach_hoan_hang ← policy.docx "Chính sách hoàn hàng"
    ("chinh_sach_hoan_hang", "Khách hàng được hoàn hàng trong bao lâu kể từ ngày mua?",
     "answerable", "30 ngày"),
    # tuple: "không được hoàn trả" (nguyên văn chunk) + các phương án model
    # THẬT đã diễn giải (mỗi phương án chạy gate ít nhất 2 lần, xác nhận ổn
    # định trước khi thêm — không đoán trước). Phương án thứ 3 quan sát được
    # ở Task 7 của đợt đa ngôn ngữ (2026-08-18), sau khi RAG_SYNTHESIS_PROMPT
    # được thêm khối LANGUAGE_RULE ở cuối — model đổi cách diễn đạt câu trả
    # lời (nội dung vẫn đúng, có căn cứ, NGUỒN_DÙNG: 4) nhưng không còn khớp
    # 2 phương án cũ; tái lập 2/2 lần chạy, cùng nguyên văn.
    ("chinh_sach_hoan_hang", "Hàng giảm giá có được hoàn trả không?",
     "answerable", ("không được hoàn trả",
                    "không được áp dụng chính sách hoàn trả",
                    "không được phép hoàn trả")),
    # chinh_sach_thanh_toan ← payment_policy.docx "Chính sách thanh toán và công nợ"
    ("chinh_sach_thanh_toan", "Thời hạn thanh toán mặc định là bao nhiêu ngày?",
     "answerable", "30 ngày"),
    ("chinh_sach_thanh_toan", "Quá hạn thanh toán bao lâu thì đơn hàng mới bị tạm dừng xử lý?",
     "answerable", "tạm dừng xử lý"),
    # bang_gia_chiet_khau ← discount_policy.docx "Chính sách chiết khấu theo cấp khách hàng"
    ("bang_gia_chiet_khau", "Khách hàng cấp Thân thiết được chiết khấu bao nhiêu phần trăm?",
     "answerable", "5%"),
    ("bang_gia_chiet_khau", "Khách hàng cấp Đối tác chiến lược được chiết khấu bao nhiêu?",
     "answerable", "10%"),
    # insufficient: chủ đề HOÀN TOÀN ngoài 4 chunk đóng băng của từng topic
    ("sla_giao_hang", "Giá cổ phiếu công ty hôm nay là bao nhiêu?",
     "insufficient", ""),
    ("chinh_sach_hoan_hang", "Giám đốc công ty tên gì?",
     "insufficient", ""),
    ("chinh_sach_thanh_toan", "Thủ đô nước Pháp là thành phố nào?",
     "insufficient", ""),
    ("bang_gia_chiet_khau", "Dự báo thời tiết Hà Nội tuần sau thế nào?",
     "insufficient", ""),
]

# ── multi_source: basis-mismatch ĐÃ SỬA (SP-1C1 Task 6); case ngày-tháng
# ĐÃ SỬA TIẾP (SP-1C1, sau khi chạy gate live 2 lần) ─────────────────────────
# Lịch sử: baseline-qwen3-8b-multi_source.json ban đầu (2026-07-26) có
# fabricated_number=4 (gate cứng đòi ==0, xem _gate() trong eval_gate.py).
# ĐÃ điều tra kỹ — KHÔNG phải hallucination số liệu nghiệp vụ thật. 2 nguyên
# nhân riêng biệt:
#  1. (3/4 case) Basis-mismatch trong eval_multi_source (run_eval.py): biến
#     `allowed` được dựng từ _digits(chunk.text) nhưng model thực tế được xem
#     _format_context(chunks) trong prompt — bản này CÓ THÊM chỉ số "[i]" và
#     nhãn "(section_path)" chứa "Điều N"/"Mục N" mà `allowed` không tính tới.
#     Model trích đúng những số NÓ ĐƯỢC XEM (không bịa), nhưng scanner coi
#     nhầm là bịa vì thiếu basis.
#     ĐÃ SỬA ở SP-1C1 Task 6: allowed = _digits(erp_block) |
#     _digits(_format_context(chunks)). Baseline đã chấm lại — xem
#     "rescored_at"/"original_fabricated_number" trong file JSON.
#  2. (1/4 case) Model tính đúng ngày dương lịch từ số ngày nêu trong nguồn
#     (vd "30 ngày" kể từ 01/07 → 31/07) — kết quả tính không phải substring
#     nguyên văn của nguồn, bị scanner coi là "bịa" dù phép tính đúng. Đây là
#     giới hạn THIẾT KẾ khác của scanner (không xác minh được suy luận số
#     học), tách biệt khỏi nguyên nhân 1 — Task 6 KHÔNG sửa (ngoài phạm vi bug
#     được giao lúc đó).
#
#     Quyết định GỐC của Task 6 (đã trao đổi với người dùng lúc đó): CHẤP
#     NHẬN baseline dừng ở fabricated_number=1, KHÔNG mở rộng scanner. Lập
#     luận: `_gate()` áp `fabricated_number==0` lên KẾT QUẢ ĐANG ĐO, không so
#     baseline (xem eval_gate.py) — nên giới hạn này ĐỐI XỨNG cho mọi model,
#     không thiên vị qwen3:8b. Task 6 cũng dự đoán rõ: một model cloud gặp
#     câu hỏi tương tự CÓ THỂ bị FAIL oan giống hệt.
#
#     BẰNG CHỨNG MỚI (SP-1C1, sau khi chạy gate live 2 lần, tốn tiền thật):
#     dự đoán "có thể" của Task 6 không chỉ xảy ra — nó xảy ra CẢ HAI LẦN,
#     với response byte-for-byte GIỐNG HỆT. Đây không phải rủi ro ngẫu nhiên
#     mà là hành vi TẤT ĐỊNH của model+case này. Vì `_gate()` không có ngoại
#     lệ cho giới hạn đã biết, hệ quả thực tế là: multi_source đỏ VĨNH VIỄN,
#     chặn C2 mãi mãi, bất kể lập luận đối xứng của Task 6 đúng hay không.
#     Lập luận đối xứng của Task 6 (không thiên vị model nào) VẪN ĐÚNG — cái
#     thay đổi là bằng chứng về CHI PHÍ của việc giữ nguyên quyết định đó.
#
#     QUYẾT ĐỊNH LẠI: KHÔNG xây bộ xác minh số học ngày tháng TỔNG QUÁT (rủi
#     ro over-engineering/heuristic mờ — học trực tiếp từ 3 vòng review độc
#     lập bác bỏ 2 thiết kế heuristic liên tiếp ở SYNTHESIS_CASES bên dưới,
#     cùng ngày). Thay vào đó, ghi nhận THỦ CÔNG các số suy ra được đúng cho
#     ĐÚNG case này vào `MULTI_SOURCE_DERIVED_DIGITS`, kèm phép suy viết rõ —
#     cùng kỷ luật với danh sách phương án của SYNTHESIS_CASES: không suy
#     luận thuật toán, chỉ con người xác minh tay từng trường hợp cụ thể.
#     Câu hỏi/erp_block/chunk GIỮ NGUYÊN — chỉ mở rộng `allowed` trong
#     `eval_multi_source()` cho đúng 1 case này.
#
#     Mất mát đã biết và chấp nhận: số ghi nhận là DẠNG CHUỖI cụ thể model đã
#     dùng ("01/08/2026", có số 0 đệm), không phải GIÁ TRỊ ngày trừu tượng —
#     nếu model đổi cách viết (vd "1/8/2026" không đệm số 0, hay "ngày 1
#     tháng 8"), case này có thể lại bị quy oan là bịa. Thêm dạng viết mới
#     vào set nếu/khi nó xuất hiện thật ở một lượt chạy gate sau, cùng cách
#     xử lý paraphrase mới ở SYNTHESIS_CASES.
MULTI_SOURCE_DERIVED_DIGITS: dict[tuple[str, str], frozenset[str]] = {
    ("chinh_sach_thanh_toan",
     "Hóa đơn INV/2026/00020 xuất ngày 01/07/2026, khi nào thì quá hạn "
     "thanh toán?"):
        # 01/07/2026 + 30 ngày (Điều 3, "30 ngày kể từ ngày xuất hóa đơn")
        # = 31/07/2026 → "31". Quá hạn kể từ hôm sau = 01/08/2026 → "08"
        # ("01" riêng lẻ đã nằm trong allowed qua erp_block nên không cần
        # ghi; chỉ "08"/"31" là số CHƯA từng xuất hiện literal ở đâu). Xác
        # minh bằng tay: 2026 không nhuận, tháng 7 có 31 ngày, nên 01/07 +
        # 30 ngày = 31/07 (không tràn sang tháng 8); 31/07 + 1 ngày tràn
        # sang tháng 8 → 01/08.
        frozenset({"31", "08"}),
    # Task 7 của đợt đa ngôn ngữ (2026-08-18), chạy gate live: model liệt kê
    # 3 mức chiết khấu theo cấp trong lúc từ chối trả lời dứt khoát (thiếu
    # thông tin cấp khách hàng) — "(0%, 5% hoặc 10%)". "5%"/"10%" đã có
    # literal trong chunk; "0%" suy đúng từ câu "Khách hàng cấp Thường
    # không áp dụng chiết khấu ngoài bảng giá niêm yết" (chunk 1, prose,
    # không phải chữ số) — xác minh bằng tay: "không áp dụng chiết khấu" =
    # 0%. Tái lập 2/2 lần chạy, cùng nguyên văn.
    ("bang_gia_chiet_khau",
     "Azure Interior đặt 50 Large Cabinet được chiết khấu bao nhiêu?"):
        frozenset({"0"}),
}
# ── multi_source set (SP-0) ──────────────────────────────────────────────────
# (topic fixture, erp_block đóng băng, câu hỏi, dữ kiện TÀI LIỆU kỳ vọng,
#  dữ kiện ERP kỳ vọng).
# Tên set TRUNG TÍNH với cách triển khai có chủ đích: node `fusion` sẽ biến
# mất ở SP-2 (orchestrator tự dispatch 2 nguồn rồi tổng hợp), nhưng bộ case
# này phải chạy được trên CẢ HAI để làm phép so sánh trước/sau.
# expect_doc_fact PHẢI copy nguyên văn từ chunk thật (script Task 4 Step 2).
# Topic đổi so với brief gốc, cùng lý do Task 4's SYNTHESIS_CASES: bài viết
# gốc dùng "quy_trinh_mua_hang" 2 lần nhưng KHÔNG có tài liệu nguồn tương ứng
# trong RAG DB thật; thay bằng "chinh_sach_thanh_toan" (payment_policy.docx),
# topic thứ 4 khớp corpus thật có sẵn (backend/evals/fixtures/chunks.json).
MULTI_SOURCE_CASES = [
    # sla_giao_hang ← sla.docx
    ("sla_giao_hang", "Đơn S00042 | Azure Interior | trạng thái sale | 1.500.000",
     "Đơn S00042 có đáp ứng SLA giao hàng không?", "3 ngày", "S00042"),
    ("sla_giao_hang", "Phiếu giao WH/OUT/00001 | đơn S00040 | trễ 2 ngày",
     "Phiếu WH/OUT/00001 có vi phạm SLA không?", "0,5%", "WH/OUT/00001"),
    # chinh_sach_hoan_hang ← policy.docx
    ("chinh_sach_hoan_hang", "Đơn S00042 | Azure Interior | đã giao 15/07/2026",
     "Đơn S00042 còn được hoàn hàng theo chính sách không?", "30 ngày", "S00042"),
    ("chinh_sach_hoan_hang", "Hóa đơn INV/2026/00017 | Azure Interior | đã thanh toán",
     "Hóa đơn INV/2026/00017 có được hoàn tiền không?", "5 đến 10 ngày",
     "INV/2026/00017"),
    # chinh_sach_thanh_toan ← payment_policy.docx (thay quy_trinh_mua_hang)
    ("chinh_sach_thanh_toan",
     "Hóa đơn INV/2026/00020 | Khách Wood Corner | xuất ngày 01/07/2026 | chưa thanh toán",
     "Hóa đơn INV/2026/00020 xuất ngày 01/07/2026, khi nào thì quá hạn thanh toán?",
     "30 ngày", "INV/2026/00020"),
    ("chinh_sach_thanh_toan",
     "Đơn S00050 | Khách Gemini Furniture | quá hạn thanh toán 32 ngày",
     "Đơn S00050 quá hạn thanh toán 32 ngày, đơn hàng mới của khách này có bị tạm dừng xử lý không?",
     "tạm dừng xử lý",
     # Task 11 (2026-08-01): erp_fact là tuple 2 phương án, không phải "S00050"
     # đơn — model trả lời ĐÚNG, khẳng định, dùng cả 2 nguồn nhưng gọi khách
     # hàng bằng TÊN ("Gemini Furniture") thay vì lặp mã đơn "S00050"
     # (logs/jobs/eval-gate-20260801T121135.json, tái lập ở
     # eval-gate-20260801T121335.json; xem docs/superpowers/plans/
     # 2026-08-01-sp2b-read-fanout-report.md § Task 11). Khớp qua
     # _grounded_match đã có sẵn (SP-1C1) — KHÔNG heuristic mờ mới.
     ("S00050", "Gemini Furniture")),
    # bang_gia_chiet_khau ← discount_policy.docx
    ("bang_gia_chiet_khau", "Khách Azure Interior | đặt 50 Large Cabinet",
     "Azure Interior đặt 50 Large Cabinet được chiết khấu bao nhiêu?",
     "chiết khấu", "Azure Interior"),
    ("bang_gia_chiet_khau", "Khách Azure Interior | đặt 2 Desk Pad",
     "Đơn 2 Desk Pad của Azure Interior có được chiết khấu không?",
     "chiết khấu", "Desk Pad"),
]

# ── multi_source_gather set (2026-08-04) ─────────────────────────────────────
# (topic fixture, tool_fixtures, câu hỏi, dữ kiện TÀI LIỆU kỳ vọng, dữ kiện
#  ERP kỳ vọng).
#
# PHẢN CHIẾU 1-1 MULTI_SOURCE_CASES: cùng topic, cùng question, cùng
# doc_fact, cùng erp_fact, CÙNG THỨ TỰ (test chốt cứng ở
# tests/jobs/test_eval_multi_source_gather.py). Khác biệt DUY NHẤT: phía ERP
# đổi từ erp_block viết tay — thứ fuse_answer được NẠP SẴN — thành
# tool_fixtures mà gather_erp THẬT phải tự đi lấy. Nhờ chỉ đổi đúng một
# biến, chênh lệch số đo giữa hai set quy được về đúng một nguyên nhân.
#
# Vì sao set này tồn tại: eval_multi_source chưa từng gọi gather_erp, nên 4
# plan liên tiếp sửa đúng vào năng lực thu thập ERP (2026-08-01 → 2026-08-02)
# đều không làm both_source_coverage nhúc nhích. Xem
# docs/superpowers/specs/2026-08-04-multi-source-gather-eval-design.md.
#
# tool_fixtures: dict {tool_name: text}, cùng cơ chế GATHER_CASES
# (run_eval._stub_erp_tools — tool không có trong dict trả "Không có dữ liệu
# liên quan."). KỶ LUẬT VIẾT: fixture phải mô phỏng đầu ra THẬT của tool đó,
# chỉ dùng field hàm business-layer thật sự đọc. Contract test ở
# tests/jobs/test_eval_gather.py (test_fixture_labels_match_real_tool_fields,
# qua _all_fixture_cases()) quét CẢ danh sách này lẫn GATHER_CASES.
MULTI_SOURCE_GATHER_CASES = [
    # sla_giao_hang ← sla.docx
    # get_sale_order_detail đọc: id, name, partner_id, amount_total, state,
    # date_order, delivery_status, commitment_date, effective_date
    # (sales.py:52-55) — mọi nhãn dưới đây ứng đúng một field trong đó.
    #
    # GIỚI HẠN DỮ LIỆU THẬT (không phải bug — đã tra trực tiếp Odoo,
    # 2026-08-04): ca này đo FAIL ổn định trong set `multi_source_gather`
    # sau khi sửa FUSE_PROMPT (xem
    # docs/superpowers/plans/2026-08-04-fuse-prompt-obligation-penalty-fix-report.md
    # §4) vì doc_fact "3 ngày" ứng điều khoản "đơn hàng khẩn cấp xử lý
    # trong 3 ngày" ở sla.docx, nhưng `sale.order` KHÔNG có field nào biểu
    # thị "khẩn cấp"/priority — gọi trực tiếp
    # `fields_get('sale.order')` qua Odoo thật xác nhận: 117 field, 0
    # custom field (`x_*`), không field nào (tên hay label) khớp
    # ưu tiên/khẩn cấp/gấp/priority/urgent. Model không có căn cứ để biết
    # đơn này có "khẩn cấp" hay không, nên không thể áp đúng điều khoản
    # 3-ngày thay vì hạn 7-ngày mặc định — KHÔNG có field có sẵn nào bị bỏ
    # sót (khác lớp "hạng lỗi thứ ba" ở get_product_price/
    # get_overdue_invoices bên dưới — cả hai đã sửa 2026-08-04); đây là
    # giới hạn thật của demo Odoo, không có gì để sửa bằng cách thêm field
    # hay đổi prompt.
    ("sla_giao_hang",
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | Tổng 1.500.000\n"
      "  trạng thái: sale | ngày xác nhận: 18/07/2026 | "
      "ngày giao dự kiến: 20/07/2026 | ngày giao thực tế: 21/07/2026 | "
      "trạng thái giao: full"},
     "Đơn S00042 có đáp ứng SLA giao hàng không?", "3 ngày", "S00042"),
    # list_late_deliveries đọc stock.picking: name, partner_id,
    # scheduled_date, state (inventory.py:115-117). KHÔNG có ngày giao thực
    # tế — dùng nhãn "hẹn" đúng như dòng display thật, không phải "ngày giao
    # dự kiến" (nhãn đó thuộc về commitment_date của sale.order).
    ("sla_giao_hang",
     {"list_late_deliveries":
      "1 phiếu trễ hạn:\n"
      "  WH/OUT/00001 | Azure Interior | hẹn 18/07/2026 | assigned"},
     "Phiếu WH/OUT/00001 có vi phạm SLA không?", "0,5%", "WH/OUT/00001"),
    # chinh_sach_hoan_hang ← policy.docx
    ("chinh_sach_hoan_hang",
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | Tổng 1.500.000\n"
      "  trạng thái: done | ngày xác nhận: 10/07/2026 | "
      "ngày giao thực tế: 15/07/2026 | trạng thái giao: full"},
     "Đơn S00042 còn được hoàn hàng theo chính sách không?", "30 ngày",
     "S00042"),
    # list_invoices/get_overdue_invoices dùng chung accounting._FIELDS:
    # name, partner_id, invoice_date, invoice_date_due, amount_total,
    # amount_residual, payment_state (accounting.py:7-8).
    ("chinh_sach_hoan_hang",
     {"list_invoices":
      "1 hóa đơn:\n"
      "  INV/2026/00017 | Azure Interior | ngày hóa đơn 12/07/2026 | "
      "đến hạn 11/08/2026 | 1.500.000 | còn 0 | paid"},
     "Hóa đơn INV/2026/00017 có được hoàn tiền không?", "5 đến 10 ngày",
     "INV/2026/00017"),
    # chinh_sach_thanh_toan ← payment_policy.docx
    #
    # KHÁC BIỆT CÓ CHỦ ĐÍCH so với erp_block của MULTI_SOURCE_CASES (spec
    # §4.2): erp_block cũ chỉ nêu "xuất ngày 01/07/2026", buộc model tự cộng
    # 30 ngày. list_invoices THẬT luôn trả kèm invoice_date_due, nên fixture
    # này có sẵn ngày đến hạn và ca này DỄ HƠN ca tương ứng bên
    # MULTI_SOURCE_CASES. Không phải làm nhẹ đề — đó là tính chất thật của
    # pipeline thật. Đừng đọc chênh lệch số đo giữa hai set ở ca này như
    # chênh lệch chất lượng model.
    ("chinh_sach_thanh_toan",
     {"list_invoices":
      "1 hóa đơn:\n"
      "  INV/2026/00020 | Wood Corner | ngày hóa đơn 01/07/2026 | "
      "đến hạn 31/07/2026 | 2.000.000 | còn 2.000.000 | not_paid"},
     "Hóa đơn INV/2026/00020 xuất ngày 01/07/2026, khi nào thì quá hạn thanh toán?",
     "30 ngày", "INV/2026/00020"),
    # Fixture GIỐNG HỆT bản ở GATHER_CASES (trước 2026-08-04 là bản ĐIỀU
    # CHỈNH vì bản kia còn sai). get_overdue_invoices (accounting.py:35-51) chỉ
    # đọc/trả về _FIELDS — name, partner_id, invoice_date, invoice_date_due,
    # amount_total, amount_residual, payment_state — KHÔNG có field
    # số-ngày-quá-hạn nào; display thật là "{name} | {partner} | đến hạn
    # {invoice_date_due} | còn {amount_residual}". Đây đúng "hạng lỗi thứ
    # ba" đã nêu ở đầu file (fixture khẳng định năng lực tool không có).
    # Lỗi tương tự trong GATHER_CASES (từng CỐ Ý chưa sửa) đã được sửa ở
    # plan 2026-08-04-gather-cases-overdue-invoices-fix — cả hai fixture
    # nay khớp nhau và khớp format thật.
    # erp_fact là tuple 2 phương án, thừa kế nguyên do từ MULTI_SOURCE_CASES
    # (model trả lời đúng nhưng gọi khách hàng bằng TÊN thay vì lặp mã đơn).
    # Lưu ý: "S00050" KHÔNG có trong fixture — get_overdue_invoices trả hóa
    # đơn, không trả mã đơn bán. Mã đó đến từ chính câu hỏi; đây là ca duy
    # nhất khiến eval_multi_source_gather phải truyền
    # allowed_extra_text=question (spec §5).
    ("chinh_sach_thanh_toan",
     {"get_overdue_invoices":
      "2 hóa đơn quá hạn:\n"
      "  INV/2026/00030 | Gemini Furniture | đến hạn 30/06/2026 | "
      "còn 4.200.000\n"
      "  INV/2026/00031 | Wood Corner | đến hạn 05/07/2026 | "
      "còn 1.000.000"},
     "Đơn S00050 quá hạn thanh toán 32 ngày, đơn hàng mới của khách này có "
     "bị tạm dừng xử lý không?",
     "tạm dừng xử lý", ("S00050", "Gemini Furniture")),
    # bang_gia_chiet_khau ← discount_policy.docx
    #
    # get_product_price THẬT chỉ đọc name + list_price (sales.py:81-82) và
    # docstring nói rõ nó KHÔNG áp pricelist/chiết khấu (cần ORM method mà
    # gateway read-only không cho phép). Fixture dưới đây viết đúng như vậy:
    # ERP cấp giá niêm yết + khách hàng, phần trăm chiết khấu đến từ TÀI
    # LIỆU. Đây là phân công nguồn đúng cho một câu hỏi 2 nguồn.
    ("bang_gia_chiet_khau",
     {"find_customer": "Tìm thấy 1 khách hàng: Azure Interior (ID 42)",
      "find_product": "Tìm thấy 1 sản phẩm: Large Cabinet (ID 108)",
      "get_product_price": "Giá Large Cabinet: 2.400.000 (SL 50)."},
     "Azure Interior đặt 50 Large Cabinet được chiết khấu bao nhiêu?",
     "chiết khấu", "Azure Interior"),
    ("bang_gia_chiet_khau",
     {"find_customer": "Tìm thấy 1 khách hàng: Azure Interior (ID 42)",
      "find_product": "Tìm thấy 1 sản phẩm: Desk Pad (ID 55)",
      "get_product_price": "Giá Desk Pad: 90.000 (SL 2)."},
     "Đơn 2 Desk Pad của Azure Interior có được chiết khấu không?",
     "chiết khấu", "Desk Pad"),
]

# Mỗi ca là BỘ BA: (câu, đích định tuyến kỳ vọng, depth kỳ vọng).
#
# Trường thứ ba thêm 2026-08-16 khi `sop` được tách thành MIỀN (`sop`) và ĐỘ
# SÂU (`depth`). Chỉ chấm đích thì `depth` không được canh và sẽ trôi âm thầm.
# Ca không vào SOP có depth "none" (bất biến của parse_proposal).
#
# Các ca kỳ vọng "erp_write" bên dưới giữ nguyên kỳ vọng DÙ router nay điền
# `sop` cho chúng — decide_route ánh xạ (sop, one_step) → erp_write nên hành vi
# cuối GIỐNG HỆT trước đợt này. (Bản trước ghi "Ba ca dưới đây" và không nói rõ
# ba ca nào; thực tế có SÁU ca erp_write/one_step cộng một ca erp_write/none,
# nên câu đó vừa sai số vừa không chỉ được vào đâu.)
SOP_SELECT_CASES = [
    # ── giao-hang ──
    ("làm quy trình giao hàng cho đơn bán S00012", "giao-hang", "full_sop"),
    ("thực hiện quy trình xuất kho cho đơn bán S00015", "giao-hang", "full_sop"),
    ("giao hàng cho đơn bán S00012 nhưng kiểm tra kỹ hàng trước khi giao",
     "giao-hang", "full_sop"),
    # NGỮ NGHĨA — không chữ "quy trình", chỉ mô tả tình huống. Đo 2026-08-16:
    # trước đợt này cả hai rơi về erp_write nên các bước kiểm tra của SOP bị bỏ.
    ("đơn S00012 đóng gói xong rồi, cho đi giao", "erp_write", "one_step"),
    ("khách giục đơn S00012, xuất cho khách đi", "erp_write", "one_step"),
    ("quy trình giao hàng gồm những bước nào?", "rag", "none"),   # hỏi VỀ
    ("giao hàng cho đơn S00040 luôn nhé", "erp_write", "one_step"),

    # ── nhap-kho ──
    # 3 ca HỒI QUY 2026-07-16, lấy NGUYÊN VĂN từ live-verify. Ca đầu là ca
    # trượt bền bỉ nhất của repo — hỏng qua 2 model và 2 lần viết lại mô tả,
    # tự khỏi khi hai câu hỏi được tách ra (spike 2026-08-16).
    ("quy trình nhập kho cho đơn mua P00021", "nhap-kho", "full_sop"),
    ("nhập kho theo quy trình cho đơn mua P00021", "nhap-kho", "full_sop"),
    ("làm quy trình nhập kho cho đơn mua P00021", "nhap-kho", "full_sop"),
    ("xác nhận đã kiểm đếm hàng cho đơn mua P00021 rồi mới nhập kho",
     "nhap-kho", "full_sop"),
    # NGỮ NGHĨA. LƯU Ý: spec §1.2 (design doc, dòng 40) đo PRE-PLAN câu này
    # đã đúng "nhap-kho" (✅). Case này CHỦ ĐÍCH đổi kỳ vọng sang
    # erp_write/one_step — coi là "bỏ qua kiểm tra SOP" hợp lệ theo mô hình
    # depth mới, KHÔNG PHẢI lấp một gap còn thiếu. Đây là một đánh đổi có
    # chủ ý, chưa được nghiệm thu sống xác nhận là cải thiện.
    ("hàng của đơn mua P00021 về rồi, xử lý giúp tôi", "erp_write", "one_step"),
    # CA NÀY ĐANG TRƯỢT, CÓ CHỦ ĐÍCH — đừng "sửa" bằng cách hạ kỳ vọng.
    # Nó gần như SONG SINH về cấu trúc với ca ngay trên (mô tả tình huống +
    # nhờ làm việc mơ hồ), và model xử lý HAI CÂU NHƯ NHAU dưới mọi biến thể
    # prompt/mô tả đã đo ngày 2026-08-17 — luôn ra erp_write/one_step. Đổi kỳ
    # vọng ở đây thành one_step sẽ cho 26/27 thay vì 25/27, nhưng:
    #   - "làm nốt phần còn lại" trong tiếng Việt HÀM Ý có một chuỗi việc còn
    #     dở, mạnh hơn hẳn "xử lý giúp tôi" — nên hai câu KHÔNG chắc tương
    #     đương, và model xử lý giống nhau là bằng chứng về MODEL chứ không
    #     phải về đáp án đúng;
    #   - hạ kỳ vọng theo model hôm nay là xoá vĩnh viễn tín hiệu để biết khi
    #     nào model khá lên.
    # Cổng nay baseline-relative nên giữ một ca trượt đã biết không tốn gì.
    ("đơn mua P00021 vừa giao tới, làm nốt phần còn lại nhé",
     "nhap-kho", "full_sop"),
    # MƠ HỒ THẬT — đo 2026-08-16 tất định 3/3 lượt là "unsure".
    ("kho báo hàng P00021 đã tới, cần làm gì tiếp", "clarify_depth", "unsure"),
    ("quy trình nhập kho là gì?", "rag", "none"),                 # hijack GỐC
    ("SOP nhập kho gồm những bước nào?", "rag", "none"),
    ("nhận hàng cho đơn mua P00003", "erp_write", "one_step"),

    # ── bao-gia-chiet-khau ──
    ("làm quy trình báo giá chiết khấu cho Cửa hàng ABC, 5 Tủ gỗ",
     "bao-gia-chiet-khau", "full_sop"),
    ("báo giá kèm chiết khấu theo cấp khách cho Wood Corner, 10 Desk Pad",
     "bao-gia-chiet-khau", "full_sop"),
    # NGỮ NGHĨA — không chữ "chiết khấu". Trước đợt này rơi sang erp_read, tức
    # không tạo báo giá và không áp chính sách chiết khấu nào.
    ("Wood Corner mua 10 Desk Pad, tính giá cho khách này giúp tôi",
     "clarify_depth", "unsure"),
    ("tính giá bán 5 Tủ gỗ cho Cửa hàng ABC theo đúng quy trình",
     "bao-gia-chiet-khau", "full_sop"),
    ("chính sách chiết khấu theo cấp khách như thế nào?", "rag", "none"),
    ("tạo báo giá cho Azure Interior, 2 Large Cabinet", "erp_write", "one_step"),

    # ── ĐỌC THUẦN có mã chứng từ ─────────────────────────────────────────────
    # Nhóm này thêm 2026-08-17 sau một HỒI QUY THẬT lọt qua cả hai cổng: bản
    # sửa mô tả skill hôm đó viết "câu có nêu MÃ ĐƠN MUA cụ thể là muốn LÀM
    # VIỆC trên đơn đó" — quá rộng, nên câu chỉ muốn XEM đơn cũng bị miền
    # nhap-kho vơ luôn rồi đẩy sang clarify_depth (tất định 3/3, A/B xác nhận
    # chỉ khác đúng đoạn mô tả). Cổng `intent` không thấy vì `intent` vẫn đúng
    # là erp_read; cổng `sop_select` không thấy vì KHÔNG CÓ ca nào thuộc lớp
    # này. Đây chính là lớp ca đó — xoá chúng là mở lại chỗ mù.
    ("cho tôi xem chi tiết đơn mua P00003", "erp_read", "none"),
    ("chi tiết đơn bán S00012", "erp_read", "none"),
    ("Wood Corner đã mua những gì", "erp_read", "none"),

    # ── câu bắc cầu (§6.4) ──
    ("điều chỉnh tồn kho Desk Pad về 100", "erp_write", "none"),
]

# ── GATHER_CASES ─────────────────────────────────────────────────────────────
# Đo bước THU THẬP của gather_erp (SP-2b/fanout.py) — TÁCH KHỎI bước tổng hợp
# mà MULTI_SOURCE_CASES đã đo trên erp_block viết tay. topic tái dùng ĐÚNG
# fixture chính sách của multi_source (fixtures.load_chunks) để hai bộ đo kể
# cùng một câu chuyện về cùng một chính sách.
#
# tool_fixtures: dữ liệu HAND-WRITTEN (không phải Odoo thật — fixture eval
# thật của multi_source cũng viết tay, cùng kỷ luật) cho MỖI tool trong
# required_tools; tool nào không có trong dict này thì stub trả "Không có dữ
# liệu liên quan." (xem run_eval._stub_erp_tools). required_facts PHẢI xuất
# hiện nguyên văn trong tool_fixtures của chính case (test chốt ở
# test_eval_gather.py) — tự-mâu-thuẫn là lỗi, không phải điều kiện khó.
GATHER_CASES = [
    # sla_giao_hang — SỬA sau điều tra tiếp theo (2026-08-02):
    # get_sale_order_detail giờ CÓ date_order/delivery_status thật (sửa ở
    # sales.py, xác nhận unit test + Odoo thật) — không cần list_sale_orders
    # cho câu hỏi chỉ nêu mã đơn nữa. Quy tắc GATHER_ERP_PROMPT dẫn dắt sang
    # list_sale_orders đã bị bỏ hẳn (chính nó là nguồn gây lỗ hổng tra cứu
    # trung gian — xem docs/superpowers/specs/2026-08-02-sale-order-detail-dates-design.md).
    #
    # Nhãn ngày trong tool_fixtures dưới đây đã được đối chiếu với field
    # THẬT: get_sale_order_detail đọc date_order ("ngày xác nhận") và
    # commitment_date ("ngày giao dự kiến") — bổ sung ở plan
    # sale-order-effective-dates (2026-08-02). Cảnh báo cũ tại đây (nói
    # không tool nào trả về được ngày giao dự kiến) đã HẾT HIỆU LỰC từ lúc
    # đó; contract test test_eval_gather.py canh việc này tự động.
    ("sla_giao_hang", "Đơn S00042 có đáp ứng SLA giao hàng không?",
     ("get_sale_order_detail",),
     ("18/07/2026", "20/07/2026"),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: sale (đã xác nhận) | "
      "ngày xác nhận: 18/07/2026 | ngày giao dự kiến: 20/07/2026"}),
    # chinh_sach_hoan_hang — cùng lý do sửa như sla_giao_hang ở trên.
    #
    # "ngày giao thực tế" ứng field THẬT effective_date của
    # get_sale_order_detail (thêm ở plan sale-order-effective-dates,
    # 2026-08-02). Cảnh báo cũ tại đây đã hết hiệu lực.
    ("chinh_sach_hoan_hang", "Đơn S00042 còn được hoàn hàng theo chính sách không?",
     ("get_sale_order_detail",),
     ("15/07/2026",),
     {"get_sale_order_detail":
      "Đơn S00042 | Azure Interior | trạng thái: done (đã giao) | "
      "ngày giao thực tế: 15/07/2026"}),
    # chinh_sach_thanh_toan — câu hỏi giống hệt MULTI_SOURCE_CASES (S00050).
    # required_fact là mã hoá đơn INV/2026/00030 (KHÔNG phải "32 ngày" —
    # sửa sau review toàn nhánh: "32 ngày" đã có sẵn NGUYÊN VĂN trong câu
    # hỏi, model chép lại câu hỏi là đủ đậu, không đo được gì thật). Mã hoá
    # đơn CHỈ xuất hiện trong dữ liệu tool, đòi model phải đọc và đối chiếu
    # đúng dòng giữa nhiều dòng dữ liệu khác.
    #
    # Fixture dưới đây đã được sửa khớp format thật của
    # accounting.get_overdue_invoices (accounting.py:35-51, chỉ trả _FIELDS
    # — accounting.py:7-8 — không có field số-ngày-quá-hạn nào). Trước đó
    # fixture khẳng định "quá hạn N ngày" (hạng lỗi thứ ba, phát hiện ở
    # spec 2026-08-04-multi-source-gather-eval-design.md §7) — đã sửa ở
    # plan 2026-08-04-gather-cases-overdue-invoices-fix, đo thật xác nhận
    # tool_recall/fact_coverage không đổi (required_facts của ca này chưa
    # từng chạm field đó).
    ("chinh_sach_thanh_toan",
     "Đơn S00050 quá hạn thanh toán 32 ngày, đơn hàng mới của khách này có "
     "bị tạm dừng xử lý không?",
     ("get_overdue_invoices",),
     ("INV/2026/00030",),
     {"get_overdue_invoices":
      "2 hóa đơn quá hạn:\n"
      "  INV/2026/00030 | Gemini Furniture | đến hạn 30/06/2026 | "
      "còn 4.200.000\n"
      "  INV/2026/00031 | Wood Corner | đến hạn 05/07/2026 | "
      "còn 1.000.000"}),
    # bang_gia_chiet_khau — ca 3 tool nối chuỗi (find_customer → find_product
    # → get_product_price), đo tool_recall trên một chuỗi nhiều bước thay vì
    # một lượt gọi đơn.
    #
    # Câu hỏi đã sửa từ "được chiết khấu bao nhiêu?" sang tra giá niêm yết
    # (plan 2026-08-04-gather-cases-product-price-fix): sales.get_product_price
    # (sales.py:73-90) chỉ đọc list_price, KHÔNG áp pricelist/chiết khấu —
    # pricelist cần ORM method mà gateway read-only không cho phép. Không
    # tool ERP nào trong hệ thống trả về được % chiết khấu, nên câu hỏi cũ
    # đòi required_facts=("12%",) — một giá trị KHÔNG thể đến từ ERP thật,
    # không phải field bị bỏ sót (khác lớp "hạng lỗi thứ ba" đã sửa ở
    # get_overdue_invoices). Fixture get_product_price dưới đây nguyên văn
    # đã kiểm chứng ở ca song sinh trong MULTI_SOURCE_GATHER_CASES.
    #
    # Topic vẫn tên "bang_gia_chiet_khau" (dùng chung ở set khác qua
    # fixtures.load_chunks()) dù ca CỤ THỂ này trong GATHER_CASES giờ đo
    # tra giá, không phải tra chiết khấu — lệch tên/nội dung có chủ đích,
    # đổi tên topic ngoài phạm vi plan này.
    #
    # find_customer không còn thực sự bắt buộc cho câu hỏi MỚI (giá niêm
    # yết không phụ thuộc partner_id — sales.py:73-90) như với câu hỏi CŨ
    # (chiết khấu theo tier); nếu tool_recall sau này tụt còn 0.75 ở đúng
    # ca này, có thể là model chọn tool tối giản hợp lý, không hẳn regression.
    ("bang_gia_chiet_khau", "Azure Interior đặt 50 Large Cabinet, giá niêm yết là bao nhiêu?",
     ("find_customer", "find_product", "get_product_price"),
     ("2.400.000",),
     {"find_customer": "Tìm thấy 1 khách hàng: Azure Interior (ID 42)",
      "find_product": "Tìm thấy 1 sản phẩm: Large Cabinet (ID 108)",
      "get_product_price": "Giá Large Cabinet: 2.400.000 (SL 50)."}),
]

# ── LOCALIZE_CASES ───────────────────────────────────────────────────────────
# Chuỗi ĐIỀU PHỐI thật (không phải câu do LLM sinh) — đây là những chuỗi đi
# THẲNG ra người dùng rồi người ta DUYỆT một thao tác ghi dựa trên chúng. Mỗi
# ca là (văn bản gốc tiếng Việt, ngôn ngữ đích).
LOCALIZE_CASES = [
    ('Mình sẽ thực hiện thao tác sau giúp bạn:\n\n**Nhận hàng cho đơn mua '
     'P00003**\n(receive_order: order_ref=P00003)\nBạn xác nhận giúp mình nhé? '
     '(trả lời "có" để thực hiện, "không" để hủy)', "en"),
    ('Báo giá cho Azure Interior:\n  - [E-COM07] Large Cabinet × 2 = 640\n'
     'Tổng: 640\nBạn xác nhận giúp mình nhé?', "en"),
    ('Xác nhận GIAO HÀNG cho đơn bán S00012?', "en"),
    ('Xác nhận phiếu kho WH/OUT/00001 đã reserve đủ hàng?', "en"),
    ('Đã giao hàng cho đơn S00012 (1 phiếu).', "en"),
    ('Hóa đơn INV/2026/00004 của Acme Corporation, số tiền 1250.5, hạn '
     '2026-07-30. Bạn xác nhận ghi nhận thanh toán?', "en"),
    ('Sản phẩm Large Cabinet (ID 108) của Wood Corner đã hết hạn bảo hành từ '
     '30/06/2026.', "en"),
]

# ── LANGUAGE_CASES ───────────────────────────────────────────────────────────
# (tên prompt, câu hỏi, ngôn ngữ kỳ vọng của CÂU TRẢ LỜI).
# Đo tầng prompt, KHÔNG đo tầng điều phối (đó là LOCALIZE_CASES).
LANGUAGE_CASES = [
    ("CHITCHAT_PROMPT", "hi, who are you?", "en"),
    ("CHITCHAT_PROMPT", "chào bạn, bạn là ai?", "vi"),
    ("RAG_SYNTHESIS_PROMPT", "what is the return policy?", "en"),
    ("RAG_SYNTHESIS_PROMPT", "chính sách hoàn hàng là gì?", "vi"),
    ("FUSE_PROMPT", "does order S00165 meet the delivery SLA?", "en"),
    ("FUSE_PROMPT", "đơn S00165 có đáp ứng SLA giao hàng không?", "vi"),
]
