from src.agents.prompts import WRITE_PLANNER_PROMPT


def test_planner_prompt_advertises_confirm_sale_order_contract():
    # The planner must emit the exact tool name + arg key the executor accepts.
    assert "confirm_sale_order" in WRITE_PLANNER_PROMPT
    assert "order_ref" in WRITE_PLANNER_PROMPT


def test_planner_prompt_advertises_t2_contracts():
    assert "confirm_purchase_order" in WRITE_PLANNER_PROMPT
    assert "post_invoice" in WRITE_PLANNER_PROMPT
    assert "validate_picking" in WRITE_PLANNER_PROMPT
    assert "partner_name" in WRITE_PLANNER_PROMPT
    assert "picking_ref" in WRITE_PLANNER_PROMPT


def test_planner_prompt_advertises_post_invoice_disambiguators():
    assert "amount: float" in WRITE_PLANNER_PROMPT
    assert "invoice_date" in WRITE_PLANNER_PROMPT


def test_planner_prompt_advertises_create_quotation():
    assert "create_quotation" in WRITE_PLANNER_PROMPT
    assert "lines" in WRITE_PLANNER_PROMPT


def test_planner_prompt_advertises_create_rfq():
    assert "create_rfq" in WRITE_PLANNER_PROMPT
    # the generalized order coordinator reads args["partner_name"] for purchase too,
    # so the RFQ contract must advertise partner_name (not supplier_name).
    assert "create_rfq(partner_name" in WRITE_PLANNER_PROMPT


def test_planner_prompt_advertises_inventory_adjustment():
    assert "inventory_adjustment" in WRITE_PLANNER_PROMPT
    assert "new_qty" in WRITE_PLANNER_PROMPT


def test_planner_prompt_advertises_create_invoice_from_order():
    assert "create_invoice_from_order(order_ref" in WRITE_PLANNER_PROMPT


def test_planner_prompt_advertises_deliver_order():
    assert "deliver_order(order_ref" in WRITE_PLANNER_PROMPT


def test_planner_prompt_advertises_receive_order():
    assert "receive_order(order_ref" in WRITE_PLANNER_PROMPT


def test_planner_prompt_advertises_create_bill_from_po():
    assert "create_bill_from_po(order_ref" in WRITE_PLANNER_PROMPT


from src.agents.prompts import render_working_context


def test_render_working_context_contains_ref_and_model_vi():
    text = render_working_context({"ref": "S00040", "model": "sale.order",
                                   "display": "Đã tạo báo giá S00040 (nháp)."})
    assert "S00040" in text and "đơn bán" in text


def test_render_working_context_instructs_explicit_wins():
    text = render_working_context({"ref": "P00015", "model": "purchase.order",
                                   "display": "x"})
    assert "đơn mua" in text
    assert "LUÔN dùng mã người dùng nêu" in text


def test_planner_prompt_advertises_register_payment():
    assert "register_payment(invoice_ref" in WRITE_PLANNER_PROMPT
    assert "journal" in WRITE_PLANNER_PROMPT


def test_planner_prompt_chain_description_ends_at_register_payment():
    assert "post_invoice → register_payment" in WRITE_PLANNER_PROMPT


def test_planner_prompt_advertises_crm_tools():
    assert "create_lead(name" in WRITE_PLANNER_PROMPT
    assert "convert_lead(lead_ref" in WRITE_PLANNER_PROMPT
    assert "log_activity(res_model" in WRITE_PLANNER_PROMPT


def test_planner_prompt_mentions_crm_chain():
    assert "create_lead → convert_lead" in WRITE_PLANNER_PROMPT


def test_planner_prompt_advertises_internal_transfer():
    assert "internal_transfer" in WRITE_PLANNER_PROMPT
    assert "from_location" in WRITE_PLANNER_PROMPT
    assert "to_location" in WRITE_PLANNER_PROMPT


def test_planner_prompt_advertises_scrap_product():
    assert "scrap_product" in WRITE_PLANNER_PROMPT
    assert "scrap_product(product_name" in WRITE_PLANNER_PROMPT


from src.agents.prompts import RAG_SYNTHESIS_PROMPT, FUSE_PROMPT


def test_rag_synthesis_prompt_forbids_inline_section_numbers():
    # Round 2026-07-25: the LLM must not type Điều/Mục/Khoản numbers itself
    # (measured to swap/fabricate them) — the deterministic footer already
    # carries the correct numbers.
    assert "KHÔNG nêu số thứ tự Điều/Mục/Khoản" in RAG_SYNTHESIS_PROMPT


def test_fuse_prompt_forbids_inline_section_numbers():
    assert "KHÔNG nêu số thứ tự Điều/Mục/Khoản" in FUSE_PROMPT


def test_rag_synthesis_prompt_forbids_bracket_index_citation():
    assert "HAY số thứ tự đoạn tài liệu" in RAG_SYNTHESIS_PROMPT


def test_fuse_prompt_forbids_bracket_index_citation():
    assert "HAY số thứ tự đoạn tài liệu" in FUSE_PROMPT


def test_register_payment_signature_shows_either_identifier_optional():
    # GitHub issue #10: the old signature showed BOTH invoice_ref and
    # partner_name with no default, implying both were required — but the
    # real tool (server.py) only needs ONE of the two. This caused qwen3:8b
    # to enter a non-terminating reasoning loop when a message supplied
    # only one of them.
    assert "register_payment(invoice_ref: str = null, partner_name: str = null" in WRITE_PLANNER_PROMPT
    assert "MỘT TRONG HAI" in WRITE_PLANNER_PROMPT


def test_fuse_prompt_has_obligation_penalty_rule():
    """Quy tắc mới (plan 2026-08-04-fuse-prompt-obligation-penalty-fix):
    đối chiếu đủ cặp nghĩa vụ/thời hạn + hậu quả/mức phạt cho câu hỏi
    tuân thủ/vi phạm — đo thật trên 8 ca multi_source_gather trước khi
    thêm, xem spec §2. Chốt cứng để không bị xoá nhầm khi ai đó dọn
    FUSE_PROMPT sau này. Assert TOÀN BỘ dòng (không chỉ đoạn giữa
    "NGHĨA VỤ/THỜI HẠN ... HẬU QUẢ/MỨC PHẠT") — một assert chỉ ghim đoạn
    giữa vẫn xanh nếu ai đó sửa mệnh đề điều kiện đầu dòng ("Với câu hỏi
    về việc có TUÂN THỦ/VI PHẠM...") hay mệnh đề hành động cuối dòng
    ("hãy dùng CẢ HAI — xác định trước...") mà chừa nguyên đoạn giữa."""
    from src.agents.prompts import FUSE_PROMPT
    assert ("Với câu hỏi về việc có TUÂN THỦ/VI PHẠM một điều khoản hay "
            "không (SLA, thời hạn, chính sách): nếu TÀI LIỆU có một đoạn "
            "nêu NGHĨA VỤ/THỜI HẠN và một đoạn KHÁC nêu HẬU QUẢ/"
            "MỨC PHẠT khi vi phạm, hãy dùng CẢ HAI — xác định trước có "
            "vi phạm nghĩa vụ hay không, rồi nêu hậu quả/mức phạt tương "
            "ứng nếu có vi phạm.") in FUSE_PROMPT


def test_chitchat_prompt_has_brand_name():
    """Gán tên thương hiệu (plan 2026-08-05-chitchat-brand-identity-fix):
    đo thật qua request tới backend live cho thấy hệ thống chưa từng tự
    giới thiệu bằng tên "Youdoo" khi được hỏi "bạn là ai" — grep toàn bộ
    prompts.py xác nhận 0 lần xuất hiện trước khi sửa. Chốt cứng để không
    bị mất khi ai đó sửa lại CHITCHAT_PROMPT sau này."""
    from src.agents.prompts import CHITCHAT_PROMPT
    assert CHITCHAT_PROMPT.startswith("Bạn là Youdoo,")


def test_gather_erp_prompt_yeu_cau_tra_cuu_truoc_khi_hoi_lai():
    """Bug thật 2026-08-05: agent hỏi 'nhà cung cấp nào?' mà không tra cứu,
    dù chính nó tra được ngay khi được hỏi thẳng ở lượt sau. Assert CẢ CÂU
    (không chỉ từ khoá rời) — một sửa lệch mệnh đề hành động (vd đảo ngược
    thành "đừng tra cứu") vẫn giữ nguyên các từ khoá rời nhưng đổi nghĩa,
    xem test_fuse_prompt_has_obligation_penalty_rule cùng file để biết vì
    sao chỉ ghim từ khoá là không đủ."""
    from src.agents.prompts import GATHER_ERP_PROMPT
    assert ("hãy GỌI TOOL tra cứu trước, đừng hỏi lại người dùng khi tự tra được"
            in GATHER_ERP_PROMPT)


def test_fuse_prompt_neu_dung_mot_lua_chon_thi_neu_thang():
    """Assert CẢ mệnh đề hành động (không chỉ cụm kích hoạt "một lựa chọn")
    — cùng lý do với test phía trên."""
    from src.agents.prompts import FUSE_PROMPT
    assert ("hãy nêu thẳng lựa chọn đó kèm số liệu thật và đề nghị tiến hành, "
            "thay vì hỏi lại người dùng chọn gì" in FUSE_PROMPT)
    assert "Nếu có NHIỀU lựa chọn, liệt kê ra để người dùng chọn." in FUSE_PROMPT


def test_write_confirm_suffix_giu_dau_hieu_cong_xac_nhan():
    """RÀNG BUỘC BẮT BUỘC: live_verify_common._looks_like_confirm_gate dò cổng
    xác nhận bằng ĐÚNG hai dấu hiệu — cụm 'xác nhận' và dấu '?'. Mất một trong
    hai là làm hỏng 3 script live-verify skill agentic."""
    from src.agents.prompts import WRITE_CONFIRM_SUFFIX
    assert "xác nhận" in WRITE_CONFIRM_SUFFIX.lower()
    assert "?" in WRITE_CONFIRM_SUFFIX


def test_khong_con_literal_xac_nhan_lap_lai_trong_src():
    """Chuỗi này từng lặp nguyên văn 19 chỗ / 10 file. Sau khi gom về hằng số,
    không file nguồn nào được viết lại literal đó nữa."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    offenders = []
    for path in list((root / "src").rglob("*.py")) + list((root / "skills").rglob("*.py")):
        if "Xác nhận? (có / không)" in path.read_text(encoding="utf-8"):
            offenders.append(str(path))
    assert offenders == [], f"còn literal chưa gom: {offenders}"


def test_gather_erp_prompt_chu_dong_neu_lien_lac_khi_dung_mot_doi_tac():
    """Rule mới (spec 2026-08-07): khi câu trả lời xoay quanh ĐÚNG MỘT đối
    tác cụ thể có tính nghiệp vụ, agent phải chủ động nêu contact — không
    chờ người dùng hỏi thẳng. Assert CẢ CÂU (điều kiện lẫn hành động), không
    chỉ mệnh đề hành động — cùng lý do với test_gather_erp_prompt_yeu_cau_tra_cuu_truoc_khi_hoi_lai
    trong file này: một sửa lệch đảo ngược nghĩa vẫn có thể giữ từ khoá rời.
    Bản gốc chỉ ghim mệnh đề hành động, để lọt mệnh đề điều kiện — đúng nửa
    phần kiểm soát tiếng ồn/chi phí (ĐÚNG MỘT, "không phải danh sách nhiều
    đối tác") — ai xoá cụm đó test vẫn xanh (review 2026-08-07). Ghim CẢ
    dòng liền mạch để bịt lỗ đó."""
    from src.agents.prompts import GATHER_ERP_PROMPT
    assert ("Nếu câu trả lời xoay quanh ĐÚNG MỘT khách hàng/nhà cung cấp cụ "
            "thể làm trọng tâm (không phải danh sách nhiều đối tác), và câu "
            "hỏi có tính chất nghiệp vụ có thể cần liên hệ tiếp theo (đặt "
            "hàng, hỏi thêm, xác nhận, báo giá) — hãy chủ động gọi "
            "get_customer_detail/get_supplier_detail và nêu email/SĐT nếu "
            "có, không cần người dùng hỏi thẳng"
            in GATHER_ERP_PROMPT)


def test_gather_erp_prompt_no_think_van_la_token_cuoi():
    """Chống hồi quy: thêm rule mới không được đẩy /no_think ra khỏi vị trí
    cuối cùng (bất biến của toàn bộ prompts.py, xem CHITCHAT_PROMPT/FUSE_PROMPT)."""
    from src.agents.prompts import GATHER_ERP_PROMPT
    assert GATHER_ERP_PROMPT.rstrip().endswith("/no_think")


def test_system_prompt_advertises_get_customer_detail():
    """Review cuối nhánh 2026-08-07 (customer-contact-detail): get_customer_detail
    được bind đầy đủ vào node erp_read (SYSTEM_PROMPT là system prompt thật của
    node đó, xem test_simple_nodes.py) nhưng thiếu trong danh mục tool "Bán hàng:"
    — trong khi get_supplier_detail đã có mặt ở danh mục "Mua hàng:" từ trước.
    Đây đúng là bất đối xứng khách/NCC mà plan này tồn tại để đóng, chỉ là ở
    SYSTEM_PROMPT thay vì GATHER_ERP_PROMPT (nơi Task 3 đã sửa). Cùng khuôn mẫu
    với test_mrp_registered_in_registry_and_prompts trong test_mrp_write.py
    (kiểm get_bom_detail/list_manufacturing_orders có trong SYSTEM_PROMPT)."""
    from src.agents.prompts import SYSTEM_PROMPT
    assert "get_customer_detail" in SYSTEM_PROMPT


def test_system_prompt_chu_dong_neu_lien_lac_khi_dung_mot_doi_tac():
    """Live-verify Task 4 (2026-08-07, sau merge): câu hỏi nghiệp vụ đơn
    giản về MỘT khách hàng cụ thể (vd "công nợ của khách Azure Interior là
    bao nhiêu?") đi qua route:read (SYSTEM_PROMPT), KHÔNG qua gather_erp
    (GATHER_ERP_PROMPT) — xác nhận bằng Langfuse trace thật: trace chỉ có
    đúng 1 observation "route:read", không có gather_erp/fuse_answer nào.
    Rule chủ động gợi ý liên lạc mà Task 3 thêm vào GATHER_ERP_PROMPT vì vậy
    KHÔNG BAO GIỜ chạy trên đường phổ biến này — agent biết get_customer_detail
    tồn tại (test phía trên) nhưng không có chỉ dẫn nào bảo nó chủ động gọi.
    Đo thật: câu trả lời không có email/SĐT dù dữ liệu có sẵn. Thêm ĐÚNG câu
    rule đã duyệt/đã hoạt động ở GATHER_ERP_PROMPT vào đây để đóng đường thứ
    hai của cùng một tính năng."""
    from src.agents.prompts import SYSTEM_PROMPT
    assert ("Nếu câu trả lời xoay quanh ĐÚNG MỘT khách hàng/nhà cung cấp cụ "
            "thể làm trọng tâm (không phải danh sách nhiều đối tác), và câu "
            "hỏi có tính chất nghiệp vụ có thể cần liên hệ tiếp theo (đặt "
            "hàng, hỏi thêm, xác nhận, báo giá) — hãy chủ động gọi "
            "get_customer_detail/get_supplier_detail và nêu email/SĐT nếu "
            "có, không cần người dùng hỏi thẳng"
            in SYSTEM_PROMPT)


def test_system_prompt_no_think_van_la_token_cuoi():
    """Chống hồi quy: thêm rule mới không được đẩy /no_think ra khỏi vị trí
    cuối cùng — cùng bất biến với GATHER_ERP_PROMPT/FUSE_PROMPT."""
    from src.agents.prompts import SYSTEM_PROMPT
    assert SYSTEM_PROMPT.rstrip().endswith("/no_think")
