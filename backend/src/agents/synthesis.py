# backend/src/agents/synthesis.py
"""Doc-answering synthesis (agents layer).

Turns S1 retrieval results into a grounded answer + a deterministic citation
footer, and owns the no-result guard. This keeps backend/src/rag/ synthesis-free
— all answer/refuse/threshold logic lives here, not in the retrieval library.
"""
import logging
import os
import re

from langchain_core.messages import SystemMessage, HumanMessage

from .prompts import RAG_SYNTHESIS_PROMPT, CITATION_VERIFY_PROMPT

logger = logging.getLogger(__name__)

# Gắn vào CUỐI footer khi cổng xác minh trích dẫn KHÔNG chạy được.
#
# Vì sao phải có (kiểm toán 2026-08-22, FM-2): `verify_citations` là một lời
# gọi LLM, dùng CHUNG ví hạn mức với model trả lời. Cạn hạn mức ⇒ nó ném ⇒
# fail-open giữ nguyên mọi chunk mà marker TỰ KHAI ⇒ footer 📄 vẫn in ra đầy
# đủ. Người dùng nhận một câu trả lời **trông như đã được kiểm chứng** đúng
# vào lúc model đang suy giảm nhất. Đó là niềm tin giả, do chính hệ thống dựng.
#
# CHỌN ĐÁNH DẤU thay vì XOÁ footer: xoá đi thì câu trả lời trông như không
# dùng tài liệu nào — cũng sai, và mất luôn thông tin người dùng cần để tự
# kiểm. Đánh dấu giữ được thông tin mà bỏ được lời hứa không có thật.
CHUA_XAC_MINH_MSG = (
    "\n_(Chưa xác minh được nguồn trích dẫn ở lượt này — nguồn nêu trên là "
    "do mô hình tự khai, chưa đối chiếu với nội dung tài liệu.)_"
)

COS_FLOOR = float(os.environ.get("RAG_NO_RESULT_COS_FLOOR", "0.35"))
SENTINEL = "KHÔNG_ĐỦ_THÔNG_TIN"
GUARD_MSG = "Không tìm thấy tài liệu liên quan đến câu hỏi này."
SAFE_MSG = "Xin lỗi, tính năng tra cứu tài liệu tạm thời gặp sự cố. Vui lòng thử lại sau."
USED_MARKER = "NGUỒN_DÙNG"
# Marker is contractually the LAST line of the answer — extract_used_citations()
# discards everything from the match onward, so any trailing text after it
# (there shouldn't be any) is dropped along with the marker itself.
_MARKER_RE = re.compile(rf'\n?{USED_MARKER}:\s*([0-9,\s]*)', re.IGNORECASE)

WRITE_SUGGEST_MARKER = "ĐỀ_XUẤT_GHI"
# KHÁC _MARKER_RE ở trên một điểm QUAN TRỌNG: extract_used_citations() cắt cụt
# body[:m.start()] (bỏ mọi thứ từ marker trở đi) vì NGUỒN_DÙNG theo hợp đồng
# là dòng CUỐI. Marker này KHÔNG được phép làm vậy — nếu model đặt ĐỀ_XUẤT_GHI
# TRƯỚC NGUỒN_DÙNG thì cắt cụt sẽ nuốt luôn dòng trích dẫn và footer
# "📄 Nguồn:" biến mất lặng lẽ. Nên ở đây xoá ĐÚNG DÒNG MARKER bằng sub(), giữ
# nguyên phần sau — hai marker nhờ vậy sống chung được ở bất kỳ thứ tự nào.
#
# `^` + re.MULTILINE là BẮT BUỘC, không phải trang trí: không có neo đầu dòng,
# regex khớp cả một mảnh marker nằm GIỮA câu ("... tôi ghi ĐỀ_XUẤT_GHI: có vào
# sổ") và sub() sẽ nuốt mất phần đuôi của chính dòng đó — hỏng lặng lẽ ngay
# trong văn bản người dùng đọc. Marker theo hợp đồng luôn là một DÒNG RIÊNG,
# nên chỉ khớp ở đầu dòng là đúng ngữ nghĩa.
_WRITE_SUGGEST_RE = re.compile(rf'\n?^{WRITE_SUGGEST_MARKER}:([^\n]*)',
                               re.IGNORECASE | re.MULTILINE)
# Bổ sung (2026-08-06): bug thật đo được qua backend live, tái lập 2/2 lần
# độc lập — model đặt marker NGAY SAU dấu hỏi, không xuống dòng trước
# ("...không? ĐỀ_XUẤT_GHI: có"), dù prompt yêu cầu "dòng CUỐI CÙNG". Pattern
# neo-đầu-dòng ở trên bỏ sót case này: marker lộ ra văn bản hiển thị VÀ
# suggested_write không được set — tái hiện đúng bug gốc plan
# write-confirmation-ux-fix từng sửa. Pattern dưới bắt marker DÍNH cuối câu,
# nhưng CHỈ khi giá trị theo sau nó là ĐÚNG MỘT TOKEN rồi hết chuỗi
# (`\s*(\S*)\s*$`) — phân biệt với marker nằm giữa câu có nội dung thật theo
# sau ("... ĐỀ_XUẤT_GHI: có vào sổ tay rồi nhé." KHÔNG khớp, vì "vào sổ tay
# rồi nhé." không phải toàn khoảng trắng).
_WRITE_SUGGEST_TRAILING_RE = re.compile(
    rf'[ \t]*{WRITE_SUGGEST_MARKER}:\s*(\S*)\s*$', re.IGNORECASE)
# Giá trị được coi là "có". Mọi giá trị khác (kể cả "không") → False, nhưng
# marker vẫn bị cắt khỏi văn bản hiển thị.
_WRITE_SUGGEST_YES = {"có", "co", "yes", "true", "1"}


def extract_write_suggestion(body: str) -> tuple[str, bool]:
    """Tách cờ "câu trả lời này đang ĐỀ XUẤT một hành động ghi" khỏi văn bản.

    Trả (văn bản đã bỏ dòng marker, có_đề_xuất_ghi). Người dùng KHÔNG BAO GIỜ
    thấy marker — đây là kênh tín hiệu máy-đọc, tách hẳn khỏi câu chữ hiển
    thị, nên prompt không phải ép model viết theo khuôn cứng nào cả.

    Cờ này được routing.decide_route đọc ở lượt SAU (qua state key riêng
    `suggested_write` + neo `suggested_write_at` — KHÔNG qua
    AIMessage.additional_kwargs, thứ bị erp_agent._invoke_fresh xoá sạch mọi
    lượt; xem routing.replying_to_write_suggestion) để hiểu "okay" là xác
    nhận. Nó CHỈ ảnh hưởng định tuyến — không hành động ghi nào chạy nếu chưa
    qua _interrupt() thật của erp_write_planner.

    Cắt TẤT CẢ dòng marker (count=0), không chỉ dòng đầu: model nhỏ/local có
    lúc phát marker hai lần, và bản cũ (count=1) để lần thứ hai lọt thẳng ra
    văn bản người dùng đọc. Giá trị boolean lấy từ lần khớp ĐẦU TIÊN — thử
    pattern neo-đầu-dòng trước, rồi mới thử pattern dính-cuối-câu (xem
    _WRITE_SUGGEST_TRAILING_RE ở trên).
    """
    body = body or ""
    m = _WRITE_SUGGEST_RE.search(body)
    if not m:
        m = _WRITE_SUGGEST_TRAILING_RE.search(body)
    if not m:
        return body, False
    clean = _WRITE_SUGGEST_RE.sub("", body, count=0)
    clean = _WRITE_SUGGEST_TRAILING_RE.sub("", clean, count=0).rstrip()
    value = (m.group(1) or "").strip().lower()
    return clean, value in _WRITE_SUGGEST_YES


def _vn_date(iso: str) -> str:
    """'2025-07-01' → '01/07/2025'. Trả nguyên chuỗi nếu không đúng dạng.

    Không ném: một chuỗi ngày lạ không được phép làm hỏng cả footer trích dẫn.
    """
    parts = iso.split("-")
    if len(parts) != 3:
        return iso
    y, m, d = parts
    return f"{d}/{m}/{y}"


def build_citations(chunks) -> str:
    """Deterministic '📄 Nguồn:' footer from chunk metadata.

    Deduped by (source_file, section_path or sheet), retrieval order preserved.
    Text chunk → "{section_path} ({file}, hiệu lực {date}, tr.{page})" — cả
    ngày lẫn trang bỏ đi nếu không có.
    xlsx chunk → "{sheet} ({file}, {row_range})". Empty list → "".

    VÌ SAO CÓ NGÀY HIỆU LỰC. Corpus sẽ chứa nhiều bản của cùng một luật (luật
    sửa đổi không thay thế bản gốc). Không có ngày trên trích dẫn thì hai bản
    trông giống hệt nhau và người đọc không có cách nào biết mình đang xem bản
    nào. Đây là toàn bộ phần "làm bây giờ": KHÔNG lọc, KHÔNG xếp hạng theo
    ngày — chưa có hai bản nào cùng tồn tại để mà lọc, và dựng bộ lọc không có
    gì để lọc chính là cách sinh ra thành phần chết.

    Ngày đặt SAU tên tệp và TRƯỚC số trang, nên chuỗi con "{file}" vẫn liền
    mạch — `citation_acc` của bộ synthesis_live kiểm `expect_source in footer`
    bằng basename.
    """
    if not chunks:
        return ""
    lines: list[str] = []
    seen: set = set()
    for c in chunks:
        key = (c.source_file, c.section_path or c.sheet)
        if key in seen:
            continue
        seen.add(key)
        base = os.path.basename(c.source_file)
        if c.sheet:
            lines.append(f"• {c.sheet} ({base}, {c.row_range})")
        else:
            loc = c.section_path or base
            tail = f", hiệu lực {_vn_date(c.effective_date)}" if getattr(
                c, "effective_date", None) else ""
            tail += f", tr.{c.page}" if c.page is not None else ""
            lines.append(f"• {loc} ({base}{tail})")
    return "\n\n📄 Nguồn:\n" + "\n".join(lines)


def extract_used_citations(body: str, chunks: list) -> tuple[str, list]:
    """Strip the LLM's NGUỒN_DÙNG marker line and resolve which chunks it
    names. Falls back to all chunks if the marker is missing or names no
    valid chunk index. Caller verifies (verify_citations) and builds the
    citation footer (build_citations) from the returned list."""
    m = _MARKER_RE.search(body)
    if not m:
        return body, chunks
    clean = body[:m.start()].rstrip()
    indices = {int(x) for x in re.findall(r'\d+', m.group(1))}
    used = [c for i, c in enumerate(chunks, start=1) if i in indices]
    if not used:
        return clean, chunks
    return clean, used


async def verify_citations(answer: str, chunks: list, llm) -> tuple[list, bool]:
    """Xác minh lại các chunk được đánh dấu đã dùng bằng 1 lệnh gọi LLM,
    đối chiếu với nội dung THẬT của từng chunk — không chỉ tin lời tự khai
    của marker NGUỒN_DÙNG. Fail-open toàn phần (lỗi/timeout → giữ nguyên
    chunks) và từng dòng (verdict thiếu/không parse được → giữ, chỉ loại
    khi có KHÔNG tường minh).

    Trả `(chunks_giữ_lại, đã_xác_minh)`. Cờ thứ hai thêm 2026-08-22: fail-open
    là đúng (chặn một câu trả lời tốt vì hạ tầng lỗi thì tệ hơn), NHƯNG nó
    phải NÓI RA. Trước đó nhánh `except` nuốt lỗi hoàn toàn — không log, không
    cờ — nên không ai biết cổng này đã tắt bao nhiêu lần.
    """
    if not chunks:
        return chunks, True
    try:
        resp = await llm.ainvoke([
            SystemMessage(content=CITATION_VERIFY_PROMPT),
            HumanMessage(content=(
                f"CÂU TRẢ LỜI:\n{answer}\n\nCÁC ĐOẠN TÀI LIỆU:\n"
                + _format_context(chunks))),
        ])
        verdicts = dict(re.findall(r'(\d+):\s*(CÓ|KHÔNG)', resp.content or "",
                                   re.IGNORECASE))
        return ([c for i, c in enumerate(chunks, start=1)
                 if verdicts.get(str(i), "").upper() != "KHÔNG"], True)
    except Exception:
        logger.warning(
            "verify_citations HỎNG — giữ nguyên %d chunk do marker tự khai và "
            "đánh dấu CHƯA XÁC MINH. Cổng chống ảo giác đã tắt ở lượt này.",
            len(chunks), exc_info=True)
        return chunks, False


async def cite_and_verify(body: str, chunks: list, llm) -> str:
    """Full citation pipeline shared by synthesize() and fuse_answer:
    resolve which chunks the marker claims were used (extract_used_citations),
    verify that claim against real chunk content (verify_citations), then
    build the footer from whatever survives (build_citations)."""
    clean, used = extract_used_citations(body, chunks)
    verified, da_xac_minh = await verify_citations(clean, used, llm)
    footer = build_citations(verified)
    # Chỉ đánh dấu khi THỰC SỰ có footer: không trích dẫn thì không có lời hứa
    # nào để rút lại, thêm ghi chú chỉ làm nhiễu.
    if footer and not da_xac_minh:
        footer += CHUA_XAC_MINH_MSG
    return clean + footer


def _format_context(chunks, start: int = 1) -> str:
    """Numbered chunk texts, each tagged with its source label, for the prompt."""
    parts = []
    for i, c in enumerate(chunks, start=start):
        label = c.section_path or c.sheet or os.path.basename(c.source_file)
        parts.append(f"[{i}] ({label}) {c.text}")
    return "\n".join(parts)


def passes_floor(result) -> bool:
    """Cheap no-result pre-filter shared by doc-only synthesis and fusion.

    True if any chunk clears the cosine floor (COS_FLOOR) or has any sparse
    (FTS) hit. Skips the LLM on an obviously-empty/off-topic retrieval; a
    keyword (FTS) hit always counts.
    """
    return (
        any(c.dense_score is not None and c.dense_score >= COS_FLOOR
            for c in result.chunks)
        or any(c.sparse_score is not None for c in result.chunks)
    )


async def synthesize(query: str, result, llm, memory: str = "") -> str:
    """Grounded answer + citation footer, or GUARD_MSG when nothing answers.

    Guard = cheap cosine pre-filter (no LLM on an obviously-empty/off-topic
    retrieval) backed by the LLM answerability sentinel. Citations are
    verified against real chunk content (verify_citations) before the
    footer is built, not just trusted from the LLM's marker self-report.

    `memory`: rendered user-memory block (render_memory_block), prepended to
    the system prompt when non-empty.

    PRODUCTION KHONG TRUYEN THAM SO NAY. rag_node tung truyen (merge 953ae58)
    nhung day noi da bi CAT ngay 2026-08-20 (ce2704b) sau khi do: khoi ky uc
    tren duong tra loi tai lieu khong loai fact nao duong — giong dieu pha hop
    dong guard (refusal_acc 1,0 -> 0,9643), ep dinh dang mat 8,3% fact_acc,
    fact noi dung bi bo qua dung thiet ke. Chi tiet + so do:
    docs/superpowers/specs/2026-08-20-memory-synthesis-eval.md §3, §7.
    Quyet dinh duoc chan troi CA HAI CHIEU boi
    test_rag_node_KHONG_nap_khoi_ky_uc.

    Tham so giu lai lam DAY BAY: ba chan `--memory` cua bo synthesis_live goi
    thang vao day de do lai thiet hai neu ai do noi lai ky uc vao duong tai
    lieu. Do la cho goi DUY NHAT hom nay.

    Ky uc VAN hieu luc day du o erp_node (nodes.py:49), chitchat (nodes.py:148)
    va fuse_answer (fanout.py:202) — chi duong tra loi tai lieu THUAN la khong
    nhan.
    """
    if result.is_empty() or not passes_floor(result):
        return GUARD_MSG
    system = RAG_SYNTHESIS_PROMPT
    if memory:
        system = memory + "\n\n" + RAG_SYNTHESIS_PROMPT
    resp = await llm.ainvoke([
        SystemMessage(content=system),
        HumanMessage(content=f"TÀI LIỆU:\n{_format_context(result.chunks)}\n\nCÂU HỎI: {query}"),
    ])
    body = (resp.content or "").strip()
    if SENTINEL in body:
        return GUARD_MSG
    return await cite_and_verify(body, result.chunks, llm)
