# Cải thiện UX luồng xác nhận ghi ERP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Khi câu trả lời đường ĐỌC đề xuất một hành động ghi, người dùng trả
lời ngắn gọn ("okay") phải được hiểu là xác nhận và đi đúng vào luồng
`_interrupt()` thật — thay vì rơi vào chitchat và mất ngữ cảnh.

**Architecture:** LLM đường đọc phát một marker `ĐỀ_XUẤT_GHI: có` ở dòng
cuối; code parse rồi CẮT BỎ marker trước khi hiển thị (đúng pattern
`NGUỒN_DÙNG` đã có sẵn), gắn tín hiệu vào chính `AIMessage` qua
`additional_kwargs`. Lớp 2 tất định của tầng định tuyến (`decide_route`) thấy
cờ đó + câu trả lời khẳng định ngắn gọn thì ép route sang `erp_write_planner`
— nơi `_plan_json` đọc TOÀN BỘ lịch sử để dựng lại plan và phát `_interrupt()`
thật. Không thêm cơ chế xác nhận mới nào.

**Tech Stack:** Python 3.11, LangGraph, LangChain, pytest, Postgres
(checkpointer).

**Spec:** `docs/superpowers/specs/2026-08-05-write-confirmation-ux-fix-design.md`

## Global Constraints

- **Bất biến an toàn số 1 — KHÔNG được vi phạm:** không hành động ghi nào
  được thực thi mà chưa qua `_interrupt()` xác nhận thật. Plan này CHỈ đụng
  ĐỊNH TUYẾN (đi tới node nào) và VĂN PHONG câu hỏi. KHÔNG đụng
  `erp_write_executor`, KHÔNG đụng điều kiện `state.get("confirmed")`, KHÔNG
  đụng `write_gate`.
- **Bất biến an toàn số 2 — Invariant C tầng 3:** tool + args thật luôn hiện
  TẤT ĐỊNH trong câu xác nhận, không do LLM sinh lại. Số liệu (`summary`,
  `tool`, `args_line`, `chain_note`, các dòng hàng hoá) giữ nguyên y hệt.
- **Bất biến an toàn số 3:** KHÔNG thêm lệnh gọi LLM mới nào cho việc làm đẹp
  câu chữ.
- **Bất biến an toàn số 4:** câu xác nhận mới PHẢI chứa cả cụm `"xác nhận"`
  LẪN dấu `"?"` — `backend/tests/live_verify_common.py:58-68`
  (`_looks_like_confirm_gate`) dò cổng xác nhận bằng đúng hai dấu hiệu này.
- Marker mới là **cờ boolean, KHÔNG kèm tên tool**: `fuse_answer`/`erp_read`
  không có danh sách 29 tool ghi trong prompt của chúng; việc xác định tool
  vẫn thuộc `_plan_json` của `erp_write_planner`.
- Comment/docstring trong repo này viết **tiếng Việt**.
- Chạy test: `cd <worktree>/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest <path> -q`
  — thiếu 2 biến env này sẽ crash `UnicodeEncodeError` trên máy Windows này.
- Bộ test unit-only: `-m "not integration and not live"`. Baseline hiện tại
  **1123 passed, 4 skipped** — không được giảm.
- Chạy `tests/rag/` làm bẩn 2 fixture nhị phân
  (`backend/tests/rag/fixtures/bang_gia.xlsx`, `policy.docx`) — luôn
  `git checkout --` chúng trước khi stage/commit.

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/src/agents/synthesis.py` | Helper parse + cắt marker `ĐỀ_XUẤT_GHI` (nằm cạnh `extract_used_citations` — helper marker anh em) |
| `backend/src/agents/routing.py` | Điều kiện tất định mới trong `decide_route` |
| `backend/src/agents/fanout.py` | `fuse_answer` gắn cờ vào `AIMessage` |
| `backend/src/agents/nodes.py` | `erp_read` gắn cờ; `erp_write_planner` dùng hằng câu xác nhận mới |
| `backend/src/agents/prompts.py` | Chỉ dẫn marker (FUSE/SYSTEM); chỉ dẫn auto-tra cứu (GATHER_ERP/FUSE); hằng `WRITE_CONFIRM_SUFFIX` |
| 8 module write + 1 skill logic | Thay literal câu xác nhận bằng hằng số |

---

### Task 1: Helper parse + cắt marker `ĐỀ_XUẤT_GHI`

**Files:**
- Modify: `backend/src/agents/synthesis.py`
- Test: `backend/tests/agents/test_synthesis.py`

**Interfaces:**
- Produces: `WRITE_SUGGEST_MARKER: str = "ĐỀ_XUẤT_GHI"` và
  `extract_write_suggestion(body: str) -> tuple[str, bool]` — trả
  `(văn bản đã cắt marker, có_đề_xuất_ghi)`. Task 3 dùng hàm này.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/agents/test_synthesis.py`:

```python
def test_extract_write_suggestion_khong_co_marker():
    from src.agents.synthesis import extract_write_suggestion
    body = "Sản phẩm còn 16 cái trong kho."
    clean, suggested = extract_write_suggestion(body)
    assert clean == body
    assert suggested is False


def test_extract_write_suggestion_co_marker_thi_cat_bo():
    from src.agents.synthesis import extract_write_suggestion
    body = "Bạn có muốn tôi tạo đơn mua không?\nĐỀ_XUẤT_GHI: có"
    clean, suggested = extract_write_suggestion(body)
    assert clean == "Bạn có muốn tôi tạo đơn mua không?"
    assert suggested is True
    assert "ĐỀ_XUẤT_GHI" not in clean


def test_extract_write_suggestion_gia_tri_phu_dinh():
    from src.agents.synthesis import extract_write_suggestion
    clean, suggested = extract_write_suggestion("Chỉ tra cứu thôi.\nĐỀ_XUẤT_GHI: không")
    assert suggested is False
    assert "ĐỀ_XUẤT_GHI" not in clean       # vẫn phải cắt marker khỏi văn bản


def test_extract_write_suggestion_giu_nguyen_dong_nguon_dung_phia_sau():
    """Marker CHỈ được xoá đúng dòng của nó, KHÔNG cắt cụt phần còn lại.

    Bug thật nếu làm sai: extract_used_citations() dùng body[:m.start()] —
    cắt bỏ MỌI THỨ từ NGUỒN_DÙNG trở đi. Nếu helper này cũng cắt cụt kiểu đó
    thì khi LLM đặt ĐỀ_XUẤT_GHI TRƯỚC NGUỒN_DÙNG, dòng trích dẫn sẽ bị nuốt
    mất và toàn bộ footer "📄 Nguồn:" biến mất — hỏng lặng lẽ.
    """
    from src.agents.synthesis import extract_write_suggestion
    body = "Câu trả lời.\nĐỀ_XUẤT_GHI: có\nNGUỒN_DÙNG: 1,2"
    clean, suggested = extract_write_suggestion(body)
    assert suggested is True
    assert "NGUỒN_DÙNG: 1,2" in clean
    assert "ĐỀ_XUẤT_GHI" not in clean


def test_extract_write_suggestion_khong_pha_extract_used_citations():
    """Hai marker sống chung: chạy helper mới TRƯỚC rồi extract_used_citations
    vẫn phải ra đúng cả hai kết quả."""
    from src.agents.synthesis import extract_write_suggestion, extract_used_citations
    body = "Câu trả lời.\nĐỀ_XUẤT_GHI: có\nNGUỒN_DÙNG: 1"
    clean, suggested = extract_write_suggestion(body)
    final, used = extract_used_citations(clean, ["chunk1", "chunk2"])
    assert suggested is True
    assert final == "Câu trả lời."
    assert used == ["chunk1"]
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `cd <worktree>/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_synthesis.py -q -k write_suggestion`
Expected: FAIL — `ImportError: cannot import name 'extract_write_suggestion'`

- [ ] **Step 3: Cài đặt helper**

Trong `backend/src/agents/synthesis.py`, ngay SAU khối định nghĩa
`USED_MARKER`/`_MARKER_RE` (hiện ở dòng 19-23), thêm:

```python
WRITE_SUGGEST_MARKER = "ĐỀ_XUẤT_GHI"
# KHÁC _MARKER_RE ở trên một điểm QUAN TRỌNG: extract_used_citations() cắt cụt
# body[:m.start()] (bỏ mọi thứ từ marker trở đi) vì NGUỒN_DÙNG theo hợp đồng
# là dòng CUỐI. Marker này KHÔNG được phép làm vậy — nếu model đặt ĐỀ_XUẤT_GHI
# TRƯỚC NGUỒN_DÙNG thì cắt cụt sẽ nuốt luôn dòng trích dẫn và footer
# "📄 Nguồn:" biến mất lặng lẽ. Nên ở đây xoá ĐÚNG MỘT DÒNG bằng sub(), giữ
# nguyên phần sau — hai marker nhờ vậy sống chung được ở bất kỳ thứ tự nào.
_WRITE_SUGGEST_RE = re.compile(rf'\n?{WRITE_SUGGEST_MARKER}:([^\n]*)',
                               re.IGNORECASE)
# Giá trị được coi là "có". Mọi giá trị khác (kể cả "không") → False, nhưng
# marker vẫn bị cắt khỏi văn bản hiển thị.
_WRITE_SUGGEST_YES = {"có", "co", "yes", "true", "1"}


def extract_write_suggestion(body: str) -> tuple[str, bool]:
    """Tách cờ "câu trả lời này đang ĐỀ XUẤT một hành động ghi" khỏi văn bản.

    Trả (văn bản đã bỏ dòng marker, có_đề_xuất_ghi). Người dùng KHÔNG BAO GIỜ
    thấy marker — đây là kênh tín hiệu máy-đọc, tách hẳn khỏi câu chữ hiển
    thị, nên prompt không phải ép model viết theo khuôn cứng nào cả.

    Cờ này được routing.decide_route đọc ở lượt SAU (qua
    AIMessage.additional_kwargs) để hiểu "okay" là xác nhận. Nó CHỈ ảnh hưởng
    định tuyến — không hành động ghi nào chạy nếu chưa qua _interrupt() thật
    của erp_write_planner.
    """
    m = _WRITE_SUGGEST_RE.search(body or "")
    if not m:
        return body, False
    clean = _WRITE_SUGGEST_RE.sub("", body, count=1).rstrip()
    value = (m.group(1) or "").strip().lower()
    return clean, value in _WRITE_SUGGEST_YES
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `cd <worktree>/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_synthesis.py -q`
Expected: PASS toàn bộ file.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/synthesis.py backend/tests/agents/test_synthesis.py
git commit -m "feat(agents): helper tách marker ĐỀ_XUẤT_GHI khỏi câu trả lời"
```

---

### Task 2: Điều kiện tất định mới trong `decide_route`

**Files:**
- Modify: `backend/src/agents/routing.py`
- Test: `backend/tests/agents/test_routing_write_suggestion.py` (tạo mới)

**Interfaces:**
- Consumes: `classify_keyword(text) -> str` và hằng `CONFIRM` từ
  `backend/src/agents/confirmation.py` (module này CHỈ import `logging` + `re`,
  không có nguy cơ import vòng). Dùng hàm CÔNG KHAI `classify_keyword`, KHÔNG
  dùng `_CONFIRM_WORDS`/`_match_any` — `classify_keyword` đã xử lý đúng ca
  "vừa có tín hiệu đồng ý vừa có tín hiệu từ chối" (trả `UNCLEAR`), viết lại
  sẽ đánh mất phần đó.
- Produces: `replying_to_write_suggestion(state) -> bool`.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_routing_write_suggestion.py`:

```python
"""Điều kiện tất định mới của decide_route: trả lời ngắn gọn cho một ĐỀ XUẤT
GHI ở lượt trước phải đi vào erp_write, không rơi về chitchat.

Bug thật đã xảy ra (2026-08-05): fuse_answer gợi ý "Bạn có muốn tôi tiến hành
tạo đơn mua ... không?", user trả lời "okay" → rơi vào chitchat, mất ngữ cảnh.
"""
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.routing import decide_route, replying_to_write_suggestion


def _ai_goi_y(text="Bạn có muốn tôi tạo đơn mua không?"):
    return AIMessage(content=text, additional_kwargs={"suggested_write": True})


def _ai_thuong(text="Đơn S00012 đang ở trạng thái nháp."):
    return AIMessage(content=text)


# ── hướng DƯƠNG ──────────────────────────────────────────────────────────────

def test_dong_y_ngan_gon_sau_de_xuat_ghi_thi_route_erp_write():
    state = {"messages": [HumanMessage(content="tôi muốn nhập 20 cái"),
                          _ai_goi_y(),
                          HumanMessage(content="okay")],
             "intent": "unknown", "sop": None}
    assert decide_route(state) == "erp_write"


def test_thang_intent_router_du_router_de_xuat_khac():
    """Điều kiện này là lớp PHỦ QUYẾT — thắng cả đề cử của router LLM."""
    state = {"messages": [HumanMessage(content="tôi muốn nhập 20 cái"),
                          _ai_goi_y(),
                          HumanMessage(content="có")],
             "intent": "rag", "sop": None}
    assert decide_route(state) == "erp_write"


# ── hướng ÂM (chống hồi quy hội thoại thường) ────────────────────────────────

def test_khong_co_co_thi_khong_ep_route():
    """RAG/chitchat cũng hay hỏi '...không?' — KHÔNG được ép sang erp_write."""
    state = {"messages": [HumanMessage(content="chính sách hoàn hàng?"),
                          _ai_thuong("Bạn có muốn tôi giải thích thêm không?"),
                          HumanMessage(content="ok")],
             "intent": "rag", "sop": None}
    assert decide_route(state) == "rag"


def test_tra_loi_tu_choi_thi_khong_ep_route():
    state = {"messages": [HumanMessage(content="tôi muốn nhập 20 cái"),
                          _ai_goi_y(),
                          HumanMessage(content="không")],
             "intent": "unknown", "sop": None}
    assert decide_route(state) == "unknown"


def test_tra_loi_dai_khong_phai_xac_nhan_thi_khong_ep_route():
    state = {"messages": [HumanMessage(content="tôi muốn nhập 20 cái"),
                          _ai_goi_y(),
                          HumanMessage(content="thế còn nhà cung cấp khác thì sao?")],
             "intent": "erp_read", "sop": None}
    assert decide_route(state) == "erp_read"


def test_co_moi_hon_khong_mang_co_thi_vo_hieu_hoa_co_cu():
    """Tự hết hạn: decide_route chỉ đọc AI message MỚI NHẤT, nên một câu trả
    lời mới không mang cờ sẽ tự vô hiệu hoá cờ của lượt cũ — không cần cơ chế
    dọn dẹp nào."""
    state = {"messages": [HumanMessage(content="tôi muốn nhập 20 cái"),
                          _ai_goi_y(),
                          HumanMessage(content="chính sách hoàn hàng?"),
                          _ai_thuong(),
                          HumanMessage(content="ok")],
             "intent": "rag", "sop": None}
    assert decide_route(state) == "rag"


def test_khong_co_ai_message_nao_thi_an_toan():
    """eval_sop_select dựng state chỉ có MỘT human message — điều kiện mới
    phải là no-op ở đó, nếu không sẽ làm lệch bộ eval đang đo decide_route."""
    state = {"messages": [HumanMessage(content="ok")],
             "intent": "erp_read", "sop": None}
    assert replying_to_write_suggestion(state) is False
    assert decide_route(state) == "erp_read"
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `cd <worktree>/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_routing_write_suggestion.py -q`
Expected: FAIL — `ImportError: cannot import name 'replying_to_write_suggestion'`

- [ ] **Step 3: Cài đặt điều kiện mới**

Trong `backend/src/agents/routing.py`, thêm vào khối import (sau
`from .skill_gate import _fold`):

```python
from .confirmation import CONFIRM, classify_keyword
```

Rồi thêm hàm mới NGAY TRƯỚC `def decide_route(...)`:

```python
def replying_to_write_suggestion(state: ERPAgentState) -> bool:
    """Lượt này có phải người dùng ĐỒNG Ý với một ĐỀ XUẤT GHI ở lượt trước?

    Tín hiệu KHÔNG đọc từ văn bản mà từ `additional_kwargs["suggested_write"]`
    của AIMessage — cờ do fuse_answer/erp_read gắn khi câu trả lời của chúng
    thật sự đề xuất một hành động ghi (xem synthesis.extract_write_suggestion).

    VÌ SAO KHÔNG DÒ VĂN BẢN: câu gây bug thật ("...từ nhà cung cấp Acme
    Corporation không?") không có khuôn "(có / không)" nào để bắt; mà nới ra
    bắt mọi câu kết thúc "...không?" thì MỌI câu hỏi chitchat/RAG thường ngày
    ("Bạn có muốn tôi giải thích thêm không?") theo sau bởi "ok" đều bị ép sai
    sang đường ghi. Cờ trên message tránh hẳn thế lưỡng nan đó.

    VÌ SAO GẮN VÀO MESSAGE, KHÔNG PHẢI STATE KEY RIÊNG: `intent_router` chạy
    TRƯỚC hàm này. State key riêng thì hoặc bị intent_router xoá (theo mẫu
    `sop`) nên không bao giờ đọc được, hoặc không ai xoá nên sống dai sang các
    lượt sau gây kích hoạt sai. Cờ nằm trên chính message thì TỰ GIỚI HẠN
    PHẠM VI: hàm này luôn đọc AI message MỚI NHẤT, nên một câu trả lời mới
    không mang cờ tự vô hiệu hoá cờ cũ — không cần kỷ luật dọn dẹp trải khắp
    các node.

    Đây CHỈ là quyết định định tuyến. Không hành động ghi nào chạy nếu chưa
    qua _interrupt() thật của erp_write_planner.
    """
    messages = state.get("messages") or []
    last_ai = next((m for m in reversed(messages) if m.type == "ai"), None)
    if last_ai is None:
        return False
    if not (getattr(last_ai, "additional_kwargs", None) or {}).get("suggested_write"):
        return False
    last_human = next((m for m in reversed(messages) if m.type == "human"), None)
    if last_human is None:
        return False
    return classify_keyword(last_human.content or "") == CONFIRM
```

Rồi trong thân `decide_route`, thêm NGAY SAU dòng docstring kết thúc
(`...tool boundary vẫn chặn mọi write chưa được duyệt."""`), TRƯỚC dòng
`intent = state.get("intent") or "unknown"`:

```python
    # Phủ quyết SỚM NHẤT: người dùng vừa đồng ý với một đề xuất ghi ở lượt
    # trước. Đặt trước cả nhánh SOP vì đây là ý định tường minh nhất có thể
    # có — mọi đề cử của lớp 1 đều thua nó.
    if replying_to_write_suggestion(state):
        return "erp_write"
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `cd <worktree>/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_routing_write_suggestion.py tests/agents/test_intent_router.py tests/agents/test_skill_gate.py tests/agents/test_sop_select_gate.py -q`
Expected: PASS toàn bộ — bao gồm các test định tuyến CŨ (không hồi quy).

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/routing.py backend/tests/agents/test_routing_write_suggestion.py
git commit -m "feat(routing): 'okay' sau đề xuất ghi được ép route sang erp_write"
```

---

### Task 3: Nối dây cờ vào `fuse_answer` + `erp_read` + chỉ dẫn prompt

**Files:**
- Modify: `backend/src/agents/prompts.py`, `backend/src/agents/fanout.py`,
  `backend/src/agents/nodes.py`
- Test: `backend/tests/agents/test_fanout.py`,
  `backend/tests/agents/test_write_suggestion_checkpoint.py` (tạo mới,
  integration)

**Interfaces:**
- Consumes: `extract_write_suggestion(body) -> tuple[str, bool]` từ Task 1;
  khoá `additional_kwargs["suggested_write"]` mà Task 2 đọc.

- [ ] **Step 1: Viết test thất bại (unit)**

Thêm vào cuối `backend/tests/agents/test_fanout.py`. **Bám đúng style sẵn có
của file này:** KHÔNG dùng `@pytest.mark.asyncio` (`pytest.ini` đã đặt
`asyncio_mode = auto`), dùng helper `_fuse_state(...)` có sẵn ở dòng 293, và
monkeypatch `verify_erp_grounding` + `cite_and_verify` như các test
`fuse_answer` khác — nếu không, mock LLM sẽ bị hai hàm đó gọi lại và làm
nhiễu kết quả.

```python
async def test_fuse_answer_gan_co_va_cat_marker(monkeypatch):
    """Marker bị cắt khỏi văn bản hiển thị và chuyển thành cờ trên message."""
    import src.agents.fanout as fanout
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(
        content="Chỉ có Acme Corporation. Bạn có muốn tôi tạo đơn mua không?"
                "\nĐỀ_XUẤT_GHI: có"))
    monkeypatch.setattr(fanout, "verify_erp_grounding",
                        AsyncMock(side_effect=lambda a, t, l: a))
    monkeypatch.setattr(fanout, "cite_and_verify", _passthrough_cite())
    out = await fanout.make_fuse_answer_node(llm)(
        _fuse_state([], "- NCC: Acme Corporation", text="nhập 20 cái"))
    msg = out["messages"][0]
    assert "ĐỀ_XUẤT_GHI" not in msg.content
    assert msg.content.endswith("Bạn có muốn tôi tạo đơn mua không?")
    assert msg.additional_kwargs.get("suggested_write") is True


async def test_fuse_answer_khong_co_marker_thi_khong_gan_co(monkeypatch):
    import src.agents.fanout as fanout
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="Kho còn 16 cái."))
    monkeypatch.setattr(fanout, "verify_erp_grounding",
                        AsyncMock(side_effect=lambda a, t, l: a))
    monkeypatch.setattr(fanout, "cite_and_verify", _passthrough_cite())
    out = await fanout.make_fuse_answer_node(llm)(
        _fuse_state([], "- tồn: 16", text="còn bao nhiêu?"))
    assert not out["messages"][0].additional_kwargs.get("suggested_write")


async def test_fuse_answer_safe_msg_khong_mang_co():
    """Nhánh trả về sớm (cả hai chân rỗng) phải khởi tạo cờ = False, nếu
    không sẽ ném UnboundLocalError."""
    import src.agents.fanout as fanout
    from src.agents.synthesis import SAFE_MSG
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=AssertionError("không được gọi LLM"))
    out = await fanout.make_fuse_answer_node(llm)(_fuse_state([], ""))
    assert out["messages"][0].content == SAFE_MSG
    assert not out["messages"][0].additional_kwargs.get("suggested_write")
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `cd <worktree>/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_fanout.py -q -k gan_co`
Expected: FAIL — `assert None is True` (chưa gắn cờ).

- [ ] **Step 3: Thêm chỉ dẫn marker vào prompt**

Trong `backend/src/agents/prompts.py`, thêm khối sau vào CUỐI chuỗi
`FUSE_PROMPT` (ngay trước dấu `"""` đóng), và CÙNG khối đó vào cuối
`SYSTEM_PROMPT`:

```
Nếu câu trả lời của bạn ĐANG ĐỀ XUẤT một thao tác ghi cụ thể (tạo/sửa/xác nhận đơn, điều chỉnh tồn kho...) và chờ người dùng đồng ý, hãy thêm một dòng CUỐI CÙNG đúng dạng: ĐỀ_XUẤT_GHI: có
Dòng này là tín hiệu nội bộ, sẽ bị hệ thống xoá trước khi hiển thị — KHÔNG nhắc tới nó trong câu trả lời, và KHÔNG đổi cách hành văn vì nó. Chỉ thêm khi bạn thật sự đề xuất một thao tác ghi; câu hỏi làm rõ thông thường thì KHÔNG thêm.
```

- [ ] **Step 4: Nối dây `fuse_answer`**

Trong `backend/src/agents/fanout.py`, sửa import (dòng 27):

```python
from .synthesis import (SAFE_MSG, _format_context, cite_and_verify,
                        extract_write_suggestion, passes_floor)
```

Rồi trong thân `fuse_answer`, thay đoạn hiện tại:

```python
            answer = (resp.content or "").strip()
            if not answer:
                return {"messages": [AIMessage(content=SAFE_MSG)], **clear}
```

thành:

```python
            answer = (resp.content or "").strip()
            if not answer:
                return {"messages": [AIMessage(content=SAFE_MSG)], **clear}
            # Tách cờ TRƯỚC cite_and_verify: extract_used_citations() cắt cụt
            # mọi thứ từ NGUỒN_DÙNG trở đi, nên nếu model đặt ĐỀ_XUẤT_GHI sau
            # NGUỒN_DÙNG thì để muộn hơn là mất cờ.
            answer, suggested_write = extract_write_suggestion(answer)
```

và thay dòng `return` cuối cùng của khối `try`/`except`:

```python
        except Exception:
            logger.exception("fuse_answer failed")
            answer = SAFE_MSG
        return {"messages": [AIMessage(content=answer)], **clear}
```

thành:

```python
        except Exception:
            logger.exception("fuse_answer failed")
            answer = SAFE_MSG
            suggested_write = False
        kwargs = {"suggested_write": True} if suggested_write else {}
        return {"messages": [AIMessage(content=answer,
                                       additional_kwargs=kwargs)], **clear}
```

**Lưu ý bắt buộc:** khởi tạo `suggested_write = False` ngay đầu thân hàm
`fuse_answer` (trước `try`), nếu không nhánh trả về sớm
`if not chunks and not erp_facts` sẽ ném `UnboundLocalError`.

- [ ] **Step 5: Nối dây `erp_read`**

Trong `backend/src/agents/nodes.py`, sửa import từ `.synthesis` (dòng 18):

```python
from .synthesis import synthesize, SAFE_MSG, extract_write_suggestion
```

Rồi thay thân `erp_read` từ dòng `tool_outputs = ...` tới `return`:

```python
        tool_outputs = [m.content for m in new_msgs if m.type == "tool"]
        if tool_outputs and new_msgs and new_msgs[-1].type == "ai":
            verified = await verify_erp_grounding(new_msgs[-1].content, tool_outputs, llm)
            if verified != new_msgs[-1].content:
                new_msgs = [*new_msgs[:-1], AIMessage(content=verified)]
        return {"messages": new_msgs}
```

thành:

```python
        tool_outputs = [m.content for m in new_msgs if m.type == "tool"]
        if tool_outputs and new_msgs and new_msgs[-1].type == "ai":
            verified = await verify_erp_grounding(new_msgs[-1].content, tool_outputs, llm)
            if verified != new_msgs[-1].content:
                new_msgs = [*new_msgs[:-1], AIMessage(content=verified)]
        # Tách cờ ĐỀ_XUẤT_GHI khỏi câu trả lời cuối (nếu có) và gắn lên chính
        # message đó — routing.replying_to_write_suggestion đọc ở lượt sau.
        if new_msgs and new_msgs[-1].type == "ai":
            clean, suggested = extract_write_suggestion(new_msgs[-1].content or "")
            if suggested or clean != new_msgs[-1].content:
                new_msgs = [*new_msgs[:-1], AIMessage(
                    content=clean,
                    additional_kwargs=({"suggested_write": True} if suggested else {}))]
        return {"messages": new_msgs}
```

- [ ] **Step 6: Chạy test unit, xác nhận PASS**

Run: `cd <worktree>/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_fanout.py tests/agents/test_simple_nodes.py tests/agents/test_prompts.py -q`
Expected: PASS toàn bộ.

- [ ] **Step 7: Viết integration test (Postgres thật)**

Tạo `backend/tests/agents/test_write_suggestion_checkpoint.py`:

```python
"""Test tích hợp — cần Postgres đang chạy.

Chạy:  pytest tests/agents/test_write_suggestion_checkpoint.py -m integration -v
Bỏ:    pytest -m "not integration"

VÌ SAO PHẢI LÀ INTEGRATION TEST, KHÔNG PHẢI UNIT TEST MOCK: state.py ghi rõ
bài học SP-1C2 — có loại lỗi CHỈ hỏng khi checkpointer Postgres thật chạy
(dữ liệu không JSON-thuần đi qua sạch mọi unit test rồi hỏng trên production).
Toàn bộ cơ chế ở đây dựa vào việc additional_kwargs sống sót vòng lưu/đọc
checkpoint, nên phải đo bằng Postgres thật.
"""
import os
import sys
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph, START, END
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.agents.state import ERPAgentState
from src.agents.routing import replying_to_write_suggestion

pytestmark = pytest.mark.integration

DSN = os.environ.get("DATABASE_URL")


async def test_co_suggested_write_song_sot_qua_checkpoint_postgres():
    if not DSN:
        pytest.skip("chưa đặt DATABASE_URL")
    if sys.platform == "win32":
        # psycopg3 async KHÔNG chạy trên ProactorEventLoop (xem backend/run.py).
        import asyncio
        if not isinstance(asyncio.get_running_loop(), asyncio.SelectorEventLoop):
            pytest.skip("cần SelectorEventLoop trên Windows")

    pool = AsyncConnectionPool(
        conninfo=DSN, max_size=2, open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0,
                "row_factory": dict_row})
    await pool.open()
    try:
        cp = AsyncPostgresSaver(pool)
        await cp.setup()

        async def node(state):
            return {"messages": [AIMessage(
                content="Bạn có muốn tôi tạo đơn mua không?",
                additional_kwargs={"suggested_write": True})]}

        g = StateGraph(ERPAgentState)
        g.add_node("a", node)
        g.add_edge(START, "a")
        g.add_edge("a", END)
        graph = g.compile(checkpointer=cp)

        tid = "test-write-suggest-" + uuid.uuid4().hex[:8]
        config = {"configurable": {"thread_id": tid}}
        await graph.ainvoke(
            {"messages": [HumanMessage(content="tôi muốn nhập 20 cái")]},
            config=config)

        # ĐỌC LẠI TỪ POSTGRES, không dùng giá trị in-memory vừa trả về
        snap = await graph.aget_state(config)
        msgs = snap.values["messages"]
        last_ai = [m for m in msgs if m.type == "ai"][-1]
        assert last_ai.additional_kwargs.get("suggested_write") is True

        # và decide_route đọc được cờ đó sau khi qua checkpoint
        assert replying_to_write_suggestion(
            {"messages": [*msgs, HumanMessage(content="okay")]}) is True

        await cp.adelete_thread(tid)
    finally:
        await pool.close()
```

- [ ] **Step 8: Chạy integration test, xác nhận PASS**

Run: `cd <worktree>/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_write_suggestion_checkpoint.py -m integration -q`
Expected: PASS (hoặc SKIP nếu Postgres/event-loop không sẵn — nếu SKIP, ghi
rõ vào report là CHƯA xác minh được, không được coi là đạt).

- [ ] **Step 9: Chạy toàn bộ unit test**

Run: `cd <worktree>/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"`
Expected: PASS, không giảm so với baseline **1123 passed, 4 skipped**.

- [ ] **Step 10: Commit**

```bash
git checkout -- backend/tests/rag/fixtures/bang_gia.xlsx backend/tests/rag/fixtures/policy.docx 2>/dev/null || true
git add backend/src/agents/prompts.py backend/src/agents/fanout.py backend/src/agents/nodes.py backend/tests/agents/test_fanout.py backend/tests/agents/test_write_suggestion_checkpoint.py
git commit -m "feat(agents): fuse_answer/erp_read gắn cờ suggested_write lên message"
```

---

### Task 4: Chủ động tra cứu khi thiếu đúng 1 lựa chọn

**Files:**
- Modify: `backend/src/agents/prompts.py`
- Test: `backend/tests/agents/test_prompts.py`

**Interfaces:** Không có API mới — chỉ đổi nội dung prompt.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/agents/test_prompts.py`:

```python
def test_gather_erp_prompt_yeu_cau_tra_cuu_truoc_khi_hoi_lai():
    """Bug thật 2026-08-05: agent hỏi 'nhà cung cấp nào?' mà không tra cứu,
    dù chính nó tra được ngay khi được hỏi thẳng ở lượt sau."""
    from src.agents.prompts import GATHER_ERP_PROMPT
    assert "tra cứu" in GATHER_ERP_PROMPT.lower()
    assert "hỏi lại" in GATHER_ERP_PROMPT.lower()


def test_fuse_prompt_neu_dung_mot_lua_chon_thi_neu_thang():
    from src.agents.prompts import FUSE_PROMPT
    assert "một lựa chọn" in FUSE_PROMPT.lower()
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `cd <worktree>/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_prompts.py -q -k "tra_cuu or lua_chon"`
Expected: FAIL — `AssertionError`.

- [ ] **Step 3: Thêm chỉ dẫn vào `GATHER_ERP_PROMPT`**

Trong `backend/src/agents/prompts.py`, thêm dòng sau vào khối "Quy tắc" của
`GATHER_ERP_PROMPT`:

```
- Nếu câu hỏi ngụ ý người dùng muốn thực hiện một thao tác nhưng còn THIẾU một thông tin bắt buộc (nhà cung cấp, khách hàng, kho...), và bạn CÓ tool tra cứu được thông tin đó — hãy GỌI TOOL tra cứu trước, đừng hỏi lại người dùng khi tự tra được.
```

- [ ] **Step 4: Thêm chỉ dẫn vào `FUSE_PROMPT`**

Trong `backend/src/agents/prompts.py`, thêm dòng sau vào `FUSE_PROMPT` (cùng
khối quy tắc với dòng nghĩa vụ/hậu quả đã có):

```
- Khi dữ kiện cho thấy chỉ có ĐÚNG một lựa chọn khả dĩ cho thao tác người dùng muốn làm (vd chỉ một nhà cung cấp), hãy nêu thẳng lựa chọn đó kèm số liệu thật và đề nghị tiến hành, thay vì hỏi lại người dùng chọn gì. Nếu có NHIỀU lựa chọn, liệt kê ra để người dùng chọn.
```

- [ ] **Step 5: Chạy test, xác nhận PASS**

Run: `cd <worktree>/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_prompts.py -q`
Expected: PASS toàn bộ file.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/prompts.py backend/tests/agents/test_prompts.py
git commit -m "feat(prompts): chủ động tra cứu khi thiếu 1 thông tin bắt buộc"
```

---

### Task 5: Gom câu xác nhận về một hằng số + đổi câu chữ

**Files:**
- Modify: `backend/src/agents/prompts.py`, `backend/src/agents/nodes.py`,
  `backend/src/agents/create_order.py`, `backend/src/agents/bom_write.py`,
  `backend/src/agents/crm_write.py`, `backend/src/agents/inventory_write.py`,
  `backend/src/agents/mrp_write.py`, `backend/src/agents/purchase_write.py`,
  `backend/src/agents/returns_write.py`, `backend/src/agents/edit_order.py`,
  `backend/skills/bao-gia-chiet-khau/logic.py`
- Test: `backend/tests/agents/test_prompts.py`,
  `backend/tests/agents/test_auto_chain.py`

**Interfaces:**
- Produces: `WRITE_CONFIRM_SUFFIX: str` trong `prompts.py`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/agents/test_prompts.py`:

```python
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
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `cd <worktree>/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/agents/test_prompts.py -q -k "confirm_suffix or literal"`
Expected: FAIL — `ImportError` cho test đầu, và test sau liệt kê 10 file.

- [ ] **Step 3: Thêm hằng số**

Trong `backend/src/agents/prompts.py`, thay dòng 124:

```python
WRITE_CONFIRM_PREFIX = "Bạn có muốn thực hiện thao tác sau không?\n\n"
```

thành:

```python
WRITE_CONFIRM_PREFIX = "Mình sẽ thực hiện thao tác sau giúp bạn:\n\n"
# NGUỒN SỰ THẬT DUY NHẤT cho câu hỏi chốt của MỌI cổng xác nhận ghi — trước
# 2026-08-05 chuỗi này bị chép nguyên văn 19 chỗ / 10 file, nên câu chữ muốn
# đổi phải sửa 19 nơi và rất dễ lệch nhau giữa đường single-step với đường
# coordinated.
# RÀNG BUỘC: phải giữ CẢ cụm "xác nhận" LẪN dấu "?" —
# tests/live_verify_common.py:58-68 (_looks_like_confirm_gate) dò cổng xác
# nhận bằng đúng hai dấu hiệu này; mất một trong hai là làm hỏng 3 script
# live-verify skill agentic (có test canh trong test_prompts.py).
WRITE_CONFIRM_SUFFIX = ('Bạn xác nhận giúp mình nhé? '
                        '(trả lời "có" để thực hiện, "không" để hủy)')
```

- [ ] **Step 4: Thay literal ở 19 chỗ**

Ở MỖI file dưới đây: thêm import rồi thay chuỗi
`Xác nhận? (có / không)` bằng tham chiếu hằng số. Vì literal nằm bên trong
f-string, cách thay an toàn nhất là kết thúc f-string trước đó rồi nối chuỗi.

Import cho 8 file trong `src/agents/` (thêm vào khối import sẵn có):

```python
from .prompts import WRITE_CONFIRM_SUFFIX
```

Import cho `skills/bao-gia-chiet-khau/logic.py` (file này dùng import tuyệt
đối, xem các import sẵn có của nó):

```python
from src.agents.prompts import WRITE_CONFIRM_SUFFIX
```

Danh sách chính xác 19 vị trí (đường dẫn tương đối từ `backend/`):

| # | File:dòng | Cách thay |
|---|---|---|
| 1 | `src/agents/create_order.py:48` | `f"{head} {partner['name']}:\n{body}{note}\n" + WRITE_CONFIRM_SUFFIX` |
| 2 | `src/agents/create_order.py:52` | `f"Tổng: {total:,.0f}{note}\n" + WRITE_CONFIRM_SUFFIX` |
| 3 | `src/agents/bom_write.py:157` | `+ "\n".join(lines) + note + "\n" + WRITE_CONFIRM_SUFFIX` |
| 4 | `src/agents/bom_write.py:276` | `f"Hiện tại:\n{cur_txt}\nSau khi sửa:\n{aft_txt}{warn}\n" + WRITE_CONFIRM_SUFFIX` |
| 5 | `src/agents/crm_write.py:114` | `f"{dup_note}{note}\n" + WRITE_CONFIRM_SUFFIX` |
| 6 | `src/agents/crm_write.py:155` | `f"Chuyển lead '{lead['name']}' thành cơ hội{who}.\n" + WRITE_CONFIRM_SUFFIX` |
| 7 | `src/agents/crm_write.py:210` | `f"{summary} — hạn {deadline}.\n" + WRITE_CONFIRM_SUFFIX` |
| 8 | `src/agents/inventory_write.py:63` | `f"về {new_qty:g}.\n" + WRITE_CONFIRM_SUFFIX` |
| 9 | `src/agents/inventory_write.py:116` | `f"{to_location}.\n" + WRITE_CONFIRM_SUFFIX` |
| 10 | `src/agents/inventory_write.py:170` | `f"Ghi nhận phế liệu {qty:g} {product['name']}{loc_txt}{reason_txt}.\n" + WRITE_CONFIRM_SUFFIX` |
| 11 | `src/agents/mrp_write.py:120` | `+ warn + note + "\n" + WRITE_CONFIRM_SUFFIX` |
| 12 | `src/agents/purchase_write.py:93` | `f"{dup_note}{note}\n" + WRITE_CONFIRM_SUFFIX` |
| 13 | `src/agents/purchase_write.py:159` | `f"{price:,.0f}đ{extra_txt}.\n" + WRITE_CONFIRM_SUFFIX` |
| 14 | `src/agents/purchase_write.py:223` | `+ "\n".join(lines_txt) + "\n" + WRITE_CONFIRM_SUFFIX` |
| 15 | `src/agents/returns_write.py:96` | `f"{body}\n" + WRITE_CONFIRM_SUFFIX` |
| 16 | `src/agents/returns_write.py:135` | `f"{inv.get('amount_total', 0):,.0f}{reason_txt}.\n" + WRITE_CONFIRM_SUFFIX` |
| 17 | `src/agents/edit_order.py:91` | `+ "\n".join(body) + note + "\n" + WRITE_CONFIRM_SUFFIX` |
| 18 | `src/agents/nodes.py:246` | xem Step 5 (đổi cả cấu trúc) |
| 19 | `skills/bao-gia-chiet-khau/logic.py:54` | `f"Tổng sau chiết khấu: {total_after:,.0f}\n" + WRITE_CONFIRM_SUFFIX` |

**KHÔNG đổi bất kỳ số liệu nào** — chỉ thay đúng chuỗi câu hỏi chốt.

- [ ] **Step 5: Sửa `erp_write_planner` (vị trí #18)**

Trong `backend/src/agents/nodes.py`, sửa import (dòng 14-15) để thêm
`WRITE_CONFIRM_SUFFIX`:

```python
from .prompts import (SYSTEM_PROMPT, WRITE_PLANNER_PROMPT,
                      WRITE_CONFIRM_PREFIX, WRITE_CONFIRM_SUFFIX,
                      CHITCHAT_PROMPT, render_working_context)
```

Rồi thay dòng 243-246:

```python
        question = WRITE_CONFIRM_PREFIX + (f"**{summary}**\n"
                                           f"({plan.get('tool')}: {args_line})"
                                           f"{plan.get('chain_note') or ''}\n\n"
                                           f"Xác nhận? (có / không)")
```

thành:

```python
        question = WRITE_CONFIRM_PREFIX + (f"**{summary}**\n"
                                           f"({plan.get('tool')}: {args_line})"
                                           f"{plan.get('chain_note') or ''}\n\n"
                                           + WRITE_CONFIRM_SUFFIX)
```

`summary`, `plan.get('tool')`, `args_line`, `chain_note` GIỮ NGUYÊN VỊ TRÍ VÀ
CÁCH TÍNH — đây là Invariant C tầng 3.

- [ ] **Step 6: Cập nhật 4 assert trong `test_auto_chain.py`**

Trong `backend/tests/agents/test_auto_chain.py`, ở các dòng 243, 249, 262,
293: thay literal `"Xác nhận? (có / không)"` bằng hằng số. Thêm import vào
đầu file:

```python
from src.agents.prompts import WRITE_CONFIRM_SUFFIX
```

rồi đổi từng assert, ví dụ dòng 243:

```python
    assert out.index("Sau đó tự động") < out.index("Xác nhận? (có / không)")
```

thành:

```python
    assert out.index("Sau đó tự động") < out.index(WRITE_CONFIRM_SUFFIX)
```

Áp dụng y hệt cho 3 dòng còn lại (249, 262, 293 — dòng 293 dùng biến `q` thay
vì `out`).

- [ ] **Step 7: Chạy toàn bộ unit test**

Run: `cd <worktree>/backend && PYTHONIOENCODING=utf-8 PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest -q -m "not integration and not live"`
Expected: PASS, không giảm so với baseline **1123 passed, 4 skipped**. Nếu có
test nào khác bám literal cũ, sửa nó sang hằng số y như Step 6 (đừng đổi
ngược hằng số về literal).

- [ ] **Step 8: Commit**

```bash
git checkout -- backend/tests/rag/fixtures/bang_gia.xlsx backend/tests/rag/fixtures/policy.docx 2>/dev/null || true
git add backend/src backend/skills backend/tests
git commit -m "refactor(agents): gom câu xác nhận ghi về WRITE_CONFIRM_SUFFIX, câu chữ tự nhiên hơn"
```

---

### Task 6: Viết report

**Files:**
- Create: `docs/superpowers/plans/2026-08-05-write-confirmation-ux-fix-report.md`

- [ ] **Step 1: Viết report**

Gồm: từng task đã làm gì (file:dòng cụ thể), kết quả `pytest` unit-only đầy
đủ, kết quả integration test (hoặc ghi rõ SKIP và lý do), và một mục **"Cổng
đánh giá §7 — CHƯA CHẠY"** nêu rõ 3 tiêu chí live-verify còn phải đo sau
merge (controller tự làm, xem cuối plan này).

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/2026-08-05-write-confirmation-ux-fix-report.md
git commit -m "docs(write-confirm-ux): report Task 1-5"
```

---

## Sau khi merge — cổng đánh giá §7 (controller tự làm, KHÔNG delegate)

Quyết định §2.1 của spec là **TẠM THỜI**. Sau merge, controller tự chạy
live-verify trên `D:\Youdoo` (backend thật, đã có Langfuse tracing ở
`http://localhost:3001` để xác nhận đúng node/route, không suy đoán):

1. **Ca gốc chạy đúng:** tái hiện kịch bản — "có 1 khách hàng sắp đặt 30 cái
   individual workplace, nhưng kho chỉ còn 16 cái, tôi muốn nhập 20 cái
   individual workplace" → (agent gợi ý nhà cung cấp) → "okay". Trace phải
   cho thấy lượt "okay" đi vào `erp_write_planner` và phát `_interrupt()`.
2. **Không hồi quy hội thoại thường:** ít nhất 3 ca chitchat/RAG có câu hỏi
   dạng "...không?" theo sau bởi "ok"/"có" — KHÔNG ca nào vào
   `erp_write_planner`.
3. **Tool-selection không hỏng:** ít nhất 3 ca `gather_erp` thật (có ca
   1-lựa-chọn và ca nhiều-lựa-chọn) chọn đúng tool/tham số.

**Nếu tiêu chí 2 hoặc 3 trượt:** revert phần tương ứng, ghi số đo thật vào
report, trình bày lại cho người dùng quyết định — KHÔNG tự nới tiêu chí.

Ghi kết quả vào chính report của Task 6 (thêm mục mới, không tạo file thứ hai).

---

## Self-Review

**Spec coverage:**

| Mục spec | Task |
|---|---|
| §2.1 marker + cắt bỏ | Task 1 (helper), Task 3 Step 3-5 (prompt + nối dây) |
| §2.1 điều kiện `decide_route` | Task 2 |
| §2.1 kiểm chứng checkpointer | Task 3 Step 7-8 |
| §2.2 auto-tra cứu | Task 4 |
| §2.3 gom hằng + câu chữ mới | Task 5 |
| §5 bất biến an toàn 1-4 | Global Constraints + Task 5 Step 1 (test canh dấu hiệu cổng) |
| §6 kiểm chứng 1-5 | Task 1-5 (từng Step chạy test) |
| §6 kiểm chứng 6 (`eval_chitchat`) | Cổng đánh giá sau merge (cần LLM thật, không chạy được trong unit test) |
| §7 cổng đánh giá | Mục "Sau khi merge" |

**Placeholder scan:** không có "TBD"/"TODO"/"tương tự Task N" — mọi bước có
code thật hoặc bảng vị trí chính xác.

**Type consistency:** `extract_write_suggestion(body) -> tuple[str, bool]`
dùng thống nhất ở Task 1 (định nghĩa), Task 3 Step 4 (fanout) và Step 5
(nodes). Khoá `additional_kwargs["suggested_write"]` dùng thống nhất ở Task 2
(đọc) và Task 3 (ghi). `WRITE_CONFIRM_SUFFIX` dùng thống nhất ở Task 5 và
test.
