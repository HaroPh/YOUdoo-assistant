# backend/tests/agents/test_fanout.py
"""Test fan-out đường đọc (SP-2b) — 4 node thay node `fusion` cũ."""


def test_state_has_fanout_keys():
    from src.agents.state import ERPAgentState
    ann = ERPAgentState.__annotations__
    assert "doc_context" in ann
    assert "erp_facts" in ann


def test_gather_erp_prompt_forbids_concluding():
    from src.agents.prompts import GATHER_ERP_PROMPT
    assert "KHÔNG kết luận" in GATHER_ERP_PROMPT
    assert GATHER_ERP_PROMPT.rstrip().endswith("/no_think")


def test_gather_erp_prompt_forbids_citing_documents():
    from src.agents.prompts import GATHER_ERP_PROMPT
    assert "KHÔNG viện dẫn" in GATHER_ERP_PROMPT


def test_fuse_prompt_keeps_citation_trailer_contract():
    from src.agents.prompts import FUSE_PROMPT
    from src.agents.synthesis import USED_MARKER
    # extract_used_citations() parse đúng dòng này — không phải trang trí.
    assert USED_MARKER in FUSE_PROMPT
    assert FUSE_PROMPT.rstrip().endswith("/no_think")


def test_fuse_prompt_forbids_inline_section_numbers():
    from src.agents.prompts import FUSE_PROMPT
    assert "KHÔNG nêu số thứ tự Điều/Mục/Khoản" in FUSE_PROMPT
    assert "HAY số thứ tự đoạn tài liệu" in FUSE_PROMPT


def test_fuse_prompt_mentions_no_write():
    from src.agents.prompts import FUSE_PROMPT
    assert "KHÔNG thực hiện thao tác ghi" in FUSE_PROMPT
