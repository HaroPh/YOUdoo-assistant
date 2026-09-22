# backend/tests/agents/test_rag_denied_nodes.py
"""Vai bị chặn phải nhận câu từ chối TẤT ĐỊNH — không LLM (spec 2026-09-21 §5).
Patch retrieve, LLM giả nổ nếu bị gọi."""
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents import fanout, rag_access, roles
import src.agents.nodes as nodes_mod
from src.rag.types import Chunk, RetrievalResult

TM = frozenset({"commercial"})
KHO = roles.PROFILES["small-business"]["warehouse"]

# dense_score vượt sàn COS_FLOOR mặc định (synthesis.py, 0.35) để
# passes_floor()/is_empty() của synthesize() KHÔNG tự chặn hộ trước khi tới
# llm.ainvoke() — nếu không, bẫy _LLMKhongDuocGoi bất động bất kể rag_node có
# đúng hay sai (xem "Vòng sửa 1" trong task-3-report.md).
_CHUNK_VUOT_SAN = Chunk(chunk_id=1, doc_id="d1", source_file="f", doc_title="t",
                        section_path=None, page=1, sheet=None, row_range=None,
                        text="nội dung", dense_score=0.9, sparse_score=None,
                        rrf_score=0.9, rank=0)


class _LLMKhongDuocGoi:
    """Ném ra NGAY khi bị gọi — nhưng nếu bên gọi nuốt exception đó (vd
    `except Exception` bao ngoài của rag_node) rồi vẫn trả nội dung ĐÚNG,
    so khớp nội dung sẽ không bắt được việc LLM đã chạy. `bi_goi` là bằng
    chứng ĐỘC LẬP với nội dung trả về — set TRƯỚC dòng raise nên sống sót
    qua mọi lớp except bên ngoài (coordinator round 2, spec 2026-09-21 §5)."""
    def __init__(self):
        self.bi_goi = False

    async def ainvoke(self, messages, config=None):
        self.bi_goi = True
        raise AssertionError("LLM bị gọi dù đã có câu từ chối tất định")


class _LLMKhongDu:
    async def ainvoke(self, messages, config=None):
        return AIMessage(content="KHÔNG_ĐỦ_THÔNG_TIN")


def _ket_qua(hidden=frozenset()):
    return RetrievalResult(query="q", query_used="q", chunks=[], top_score=0.0,
                           total_candidates=0, hidden_classes=hidden)


def _state(text="Chính sách chiết khấu?"):
    return {"messages": [HumanMessage(content=text)]}


async def test_rag_node_bi_chan_tra_cau_tu_choi_khong_goi_llm(monkeypatch):
    monkeypatch.setattr(nodes_mod, "retrieve", lambda *a, **kw: _ket_qua(TM))
    out = await nodes_mod.make_rag_node(_LLMKhongDuocGoi(), role_cfg=KHO)(_state())
    msg = out["messages"][0].content
    assert msg == rag_access.denied_message(KHO, TM, roles.load_profile())
    assert "Kế toán" in msg and "Bán hàng" in msg and rag_access.DENIED_MARKER in msg


async def test_rag_node_khong_bi_chan_van_di_synthesize(monkeypatch):
    monkeypatch.setattr(nodes_mod, "retrieve", lambda *a, **kw: _ket_qua())
    out = await nodes_mod.make_rag_node(_LLMKhongDu(), role_cfg=KHO)(_state())
    assert rag_access.DENIED_MARKER not in out["messages"][0].content


async def test_rag_node_bi_chan_khong_goi_llm_that_su_du_chunk_khong_rong(monkeypatch):
    """Hai test trên dùng chunks=[] — synthesize() tự chặn ở is_empty() trước
    khi tới LLM, nên bẫy _LLMKhongDuocGoi không bao giờ thực sự có cơ hội nổ
    dù rag_node đúng hay sai (bug/no-bug đều ra 'không gọi LLM' theo cùng lý
    do sai). Test này dùng CHUNK VƯỢT SÀN cosine để loại bỏ đường tắt đó —
    nếu rag_node lỡ rơi xuống synthesize() sau khi đã tính xong câu từ chối,
    llm.ainvoke() SẼ bị gọi thật và bẫy nổ đúng như thiết kế."""
    monkeypatch.setattr(nodes_mod, "retrieve",
                        lambda *a, **kw: RetrievalResult(
                            query="q", query_used="q", chunks=[_CHUNK_VUOT_SAN],
                            top_score=0.9, total_candidates=1, hidden_classes=TM))
    llm = _LLMKhongDuocGoi()
    out = await nodes_mod.make_rag_node(llm, role_cfg=KHO)(_state())
    msg = out["messages"][0].content
    assert msg == rag_access.denied_message(KHO, TM, roles.load_profile())
    # Bằng chứng ĐỘC LẬP với nội dung: cổng "content đúng nhưng LLM đã chạy
    # song song" (coordinator round 2) không đổi `msg` nếu code cố tình nuốt
    # exception của synthesize() rồi vẫn trả câu từ chối — chỉ `bi_goi` mới
    # lộ ra rằng llm.ainvoke() đã thực sự được gọi.
    assert llm.bi_goi is False


# ─── Đường mixed ───────────────────────────────────────────────────────────

class _LLMGhiInput:
    """Ghi lại input để kiểm dòng 'bị hạn chế theo vai'; trả câu ERP thuần."""
    def __init__(self):
        self.seen = []

    async def ainvoke(self, messages, config=None):
        self.seen.append(messages[-1].content)
        return AIMessage(content="Đơn S00042 đã giao ngày 12/09.")


async def test_gather_docs_bi_chan_dat_doc_denied(monkeypatch):
    monkeypatch.setattr(fanout, "retrieve", lambda *a, **kw: _ket_qua(TM))
    out = await fanout.make_gather_docs_node(role_cfg=KHO)(_state())
    assert out["doc_context"] == []
    assert out["doc_denied"] == rag_access.denied_message(KHO, TM, roles.load_profile())


async def test_gather_docs_khong_bi_chan_khong_co_khoa_doc_denied(monkeypatch):
    """Giữ nguyên hình dạng cũ để `mixed` (xoá lúc VÀO) là lớp chịu lực duy nhất."""
    monkeypatch.setattr(fanout, "retrieve", lambda *a, **kw: _ket_qua())
    out = await fanout.make_gather_docs_node(role_cfg=KHO)(_state())
    assert "doc_denied" not in out


async def test_mixed_xoa_doc_denied_luc_vao():
    out = await fanout.make_mixed_node()({"messages": [], "doc_denied": "cũ"})
    assert out["doc_denied"] is None


async def test_fuse_bi_chan_va_erp_rong_tra_thang_cau_tu_choi():
    msg = rag_access.denied_message(KHO, TM, roles.load_profile())
    out = await fanout.make_fuse_answer_node(_LLMKhongDuocGoi())(
        {"messages": [HumanMessage(content="q")], "doc_context": [],
         "erp_facts": "", "doc_denied": msg})
    assert out["messages"][0].content == msg
    assert out["doc_denied"] is None            # clear lúc RA


async def test_fuse_bi_chan_co_erp_noi_cau_tu_choi_vao_cuoi(monkeypatch):
    async def _giu_nguyen(answer, *a, **kw):
        return answer
    monkeypatch.setattr(fanout, "cite_and_verify", _giu_nguyen)
    monkeypatch.setattr(fanout, "verify_erp_grounding", _giu_nguyen)
    msg = rag_access.denied_message(KHO, TM, roles.load_profile())
    llm = _LLMGhiInput()
    out = await fanout.make_fuse_answer_node(llm)(
        {"messages": [HumanMessage(content="S00042 có được chiết khấu không?")],
         "doc_context": [], "erp_facts": "S00042: đã giao 12/09", "doc_denied": msg})
    answer = out["messages"][0].content
    assert answer.startswith("Đơn S00042 đã giao ngày 12/09.")
    assert answer.endswith(msg)                  # tất định, nối vào CUỐI
    assert "bị hạn chế theo vai" in llm.seen[0]  # model được BÁO, không được tự suy
    assert "KHÔNG kết luận gì về chính sách" in llm.seen[0]


def test_render_fuse_input_mac_dinh_khong_doi():
    from src.agents.fanout import render_fuse_input
    assert render_fuse_input([], "erp", "q") == "TÀI LIỆU:\n\n\nDỮ LIỆU ERP:\nerp\n\nCÂU HỎI: q"
    assert "bị hạn chế theo vai" in render_fuse_input([], "erp", "q", doc_denied="x")
