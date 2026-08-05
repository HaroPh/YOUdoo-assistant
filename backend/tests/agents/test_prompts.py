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
    assert "log_activity(lead_ref" in WRITE_PLANNER_PROMPT


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
