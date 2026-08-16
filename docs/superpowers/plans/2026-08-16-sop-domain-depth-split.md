# Tách miền nghiệp vụ khỏi độ sâu ở tầng định tuyến SOP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tách trường `sop` của router thành hai trường độc lập — `sop` (miền nghiệp vụ) và `depth` (độ sâu) — trong cùng MỘT lượt gọi LLM, để câu đời thật không mang chữ "quy trình" vẫn vào đúng SOP, và câu mơ hồ thì hỏi lại thay vì đoán.

**Architecture:** Hợp đồng router đổi từ 2 dòng sang 3 dòng (`intent` / `sop` / `depth`). Mô tả ba `SKILL.md` viết lại thuần-miền, toàn bộ hướng dẫn độ sâu dời sang luật `depth` trong prompt. `decide_route` ánh xạ cặp `(sop, depth)`: `full_sop` → node SOP, `one_step` → `erp_write` (hành vi cuối GIỐNG HỆT hôm nay), `unsure` → node `clarify_depth` mới dùng `interrupt(kind="disambiguation")` có sẵn. Lớp phủ quyết tất định `looks_like_question` giữ nguyên.

**Tech Stack:** Python 3.11, LangGraph (StateGraph + `interrupt`), LangChain, pytest.

**Spec:** `docs/superpowers/specs/2026-08-16-sop-domain-depth-split-design.md`

## Global Constraints

- **Định danh trong `backend/src` viết bằng TIẾNG ANH.** Tên biến/hàm/hằng tiếng Việt trong source là lỗi — năm plan liên tiếp đã để lọt vì người thực thi chép code trong plan nguyên văn.
- **Tên hàm test giữ quy ước chuyển tự tiếng Việt** (`test_khong_hijack_...`). Đây là quy ước có chủ đích của `backend/tests`, KHÔNG vi phạm luật trên. Comment/docstring trong test viết tiếng Việt như phần còn lại của repo.
- **MỌI lệnh pytest phải kèm `-m "not integration and not live"`.** Lệnh trần gọi API LLM thật và đã gây sự cố.
- **Mọi lệnh chạy từ `D:\Youdoo\backend`** (đó là rootdir của pytest).
- **KHÔNG BAO GIỜ gắn tín hiệu sống-qua-lượt lên `AIMessage.additional_kwargs`.** Xem cảnh báo ở Task 5.
- Worktree phải có junction `.venv` **ngay từ đầu** → `D:\Youdoo\backend\.venv` và `D:\Youdoo\mcp-servers\odoo\.venv`.
- Baseline trước khi bắt đầu: **1581 passed, 4 skipped, 48 deselected**. `SOP_SELECT_CASES` = 17 ca, `INTENT_CASES` = 54 ca (đếm ngày 2026-08-16).

---

## File Structure

| File | Trách nhiệm | Task |
|---|---|---|
| `backend/src/agents/routing.py` | `VALID_DEPTHS`, `RouteProposal` 3 trường, `parse_proposal`, `decide_route` | 1, 4 |
| `backend/src/agents/state.py` | trường `depth` trong `ERPAgentState` | 1 |
| `backend/src/agents/prompts.py` | `INTENT_ROUTER_PROMPT` hợp đồng 3 dòng + luật `depth` | 2 |
| `backend/skills/{nhap-kho,giao-hang,bao-gia-chiet-khau}/SKILL.md` | mô tả thuần-miền | 3 |
| `backend/src/agents/nodes.py` | `make_clarify_depth_node` | 5 |
| `backend/src/agents/graph.py` | đăng ký node + cạnh `clarify_depth` | 5 |
| `backend/evals/cases.py` | `SOP_SELECT_CASES` thành bộ ba, thêm 2 nhóm ca | 6 |
| `backend/evals/run_eval.py` | 3 chỗ unpack `parse_proposal`, chấm cặp trong `eval_sop_select` | 1, 6 |

---

## Task 1: `depth` vào hợp đồng parse

`RouteProposal` là `NamedTuple` và **có test canh riêng** bắt nó unpack được kiểu tuple, vì `run_eval.py` làm `intent, sop = parse_proposal(...)` ở HAI chỗ. Thêm trường thứ ba làm cả hai chỗ đó ném `ValueError: too many values to unpack`. Đây là test làm đúng việc của nó — sửa cả ba chỗ gọi, không lách bằng cách giữ 2-tuple.

**Files:**
- Modify: `backend/src/agents/routing.py:63` (thêm `VALID_DEPTHS`), `:66-76` (`RouteProposal`), `:78-105` (`parse_proposal`), `:136` (chỗ gọi trong node)
- Modify: `backend/src/agents/state.py` (thêm trường `depth`)
- Modify: `backend/evals/run_eval.py:448`, `:486`
- Test: `backend/tests/agents/test_intent_router.py`

**Interfaces:**
- Produces: `VALID_DEPTHS: set[str]`; `RouteProposal(intent: str, sop: str | None, depth: str)`; `parse_proposal(text: str, valid_sops) -> RouteProposal`. Task 4 đọc `state["depth"]`; Task 6 dùng `RouteProposal.depth`.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/agents/test_intent_router.py`:

```python
# ── depth: trường thứ ba của hợp đồng router ─────────────────────────────────


def test_parse_doc_duoc_depth():
    from src.agents.routing import parse_proposal
    got = parse_proposal("intent: erp_write\nsop: nhap-kho\ndepth: full_sop", SOPS)
    assert got.sop == "nhap-kho"
    assert got.depth == "full_sop"


def test_depth_la_none_khi_sop_rong():
    """Bất biến: `depth` chỉ có nghĩa khi có `sop`. Model vẫn hay điền bừa
    depth vào lượt sop rỗng (đo được ở spike vòng 1) — chuẩn hoá tại đây để
    decide_route không phải phòng thủ."""
    from src.agents.routing import parse_proposal
    got = parse_proposal("intent: rag\nsop:\ndepth: unsure", SOPS)
    assert got.sop is None
    assert got.depth == "none"


def test_depth_la_khong_hop_le_thi_ve_full_sop():
    """FAIL AN TOÀN: có sop nhưng depth không đọc được thì chạy ĐỦ quy trình.
    Chiều ngược lại (one_step) là chiều BỎ QUA các bước kiểm tra — không bao
    giờ được là mặc định của một lỗi parse."""
    from src.agents.routing import parse_proposal
    got = parse_proposal("intent: erp_write\nsop: nhap-kho\ndepth: banana", SOPS)
    assert got.depth == "full_sop"
    got2 = parse_proposal("intent: erp_write\nsop: nhap-kho", SOPS)
    assert got2.depth == "full_sop"


def test_hop_dong_hai_dong_cu_van_doc_duoc():
    """Checkpoint Postgres của hội thoại đang park mang phản hồi theo hợp đồng
    CŨ. Hợp đồng mới không được làm chúng thành 'unknown'."""
    from src.agents.routing import parse_proposal
    assert parse_proposal("intent: rag\nsop:", SOPS) == ("rag", None, "none")
    assert parse_proposal("erp_read", SOPS) == ("erp_read", None, "none")
```

Và SỬA test canh tuple đang có (`test_route_proposal_unpacks_as_tuple`, dòng ~154) — chép đè nguyên hàm:

```python
def test_route_proposal_unpacks_as_tuple():
    """RouteProposal PHẢI unpack được kiểu tuple: eval_sop_select và
    eval_intent (evals/run_eval.py) unpack thẳng. Đổi sang dataclass sẽ làm
    eval gãy — test này đỏ TRƯỚC khi điều đó xảy ra.

    2026-08-16: hợp đồng thành BA trường. Test này đã đỏ đúng lúc thêm
    `depth` và chỉ đúng chỗ 2 chỗ gọi trong run_eval.py phải sửa — đó là nó
    làm đúng việc, không phải nó cản đường."""
    from src.agents.routing import RouteProposal
    proposal = parse_proposal("intent: mixed\nsop: giao-hang\ndepth: full_sop", SOPS)
    intent, sop, depth = proposal               # phải unpack được
    assert (intent, sop, depth) == ("mixed", "giao-hang", "full_sop")
    assert isinstance(proposal, tuple)
    assert proposal.intent == "mixed"           # và vẫn truy cập theo tên được
    assert proposal.sop == "giao-hang"
    assert proposal.depth == "full_sop"
    assert RouteProposal("rag", None, "none") == ("rag", None, "none")
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

```bash
python -m pytest tests/agents/test_intent_router.py -m "not integration and not live" -q
```

Kỳ vọng: FAIL — `AttributeError: 'RouteProposal' object has no attribute 'depth'`.

- [ ] **Step 3: Thêm `VALID_DEPTHS` và trường `depth`**

Trong `backend/src/agents/routing.py`, ngay dưới `VALID_INTENTS` (dòng 63):

```python
VALID_INTENTS = {"erp_read", "erp_write", "rag", "mixed", "unknown"}
# Độ sâu — CÂU HỎI THỨ HAI, tách khỏi `sop`. Trước 2026-08-16 hai câu hỏi này
# gộp vào một trường: `sop` vừa phải nói việc thuộc miền nào, vừa phải đoán
# chạy sâu tới đâu. Đó là nguyên nhân ca "quy trình nhập kho cho đơn mua
# P00021" hỏng bền bỉ từ 2026-07-16 (cụm đó nằm ở CẢ vế Dùng-khi lẫn
# KHÔNG-dùng-khi của mô tả skill).
VALID_DEPTHS = {"full_sop", "one_step", "unsure", "none"}
```

Sửa `RouteProposal` (dòng 66-76):

```python
class RouteProposal(NamedTuple):
    """Đầu ra của LỚP 1 — ĐỀ CỬ, chưa phải quyết định định tuyến.

    PHẢI là NamedTuple, KHÔNG được đổi sang dataclass: run_eval.py unpack
    kiểu tuple ở hai chỗ. NamedTuple vẫn LÀ tuple nên chỗ đó không gãy. Đây
    là ràng buộc có test canh (test_route_proposal_unpacks_as_tuple).
    """
    intent: str          # luôn thuộc VALID_INTENTS; "unknown" khi không parse được
    sop: str | None      # MIỀN nghiệp vụ — lớp 2 (decide_route) có quyền bỏ
    depth: str           # luôn thuộc VALID_DEPTHS; "none" khi sop is None
```

- [ ] **Step 4: Cho `parse_proposal` đọc `depth`**

Thay thân `parse_proposal` (giữ nguyên docstring cũ, nối thêm đoạn về depth):

```python
def parse_proposal(text: str, valid_sops) -> RouteProposal:
    """Parse hợp đồng 3 dòng của router. FAIL AN TOÀN ở mọi hướng:

    - intent không nhận ra → "unknown" (hành vi cũ);
    - sop không nằm trong valid_sops → None. Tên worker model bịa ra KHÔNG BAO
      GIỜ được trả ra: nó sẽ thành node đích không tồn tại và làm LangGraph ném
      lỗi định tuyến giữa một lượt chat thật;
    - không thấy dòng "intent:" nào → thử đọc cả chuỗi như MỘT TỪ intent (hợp
      đồng CŨ). Model nhỏ hay bỏ qua format; rơi về đúng hành vi hôm nay tốt
      hơn là rơi về "unknown";
    - sop rỗng → depth LUÔN "none", kể cả khi model điền bừa (đo được ở spike
      vòng 1: model điền depth vào cả lượt sop rỗng);
    - có sop nhưng depth không đọc được → "full_sop". FAIL AN TOÀN: chiều
      "one_step" là chiều BỎ QUA các bước kiểm tra của SOP, không bao giờ được
      là mặc định của một lỗi parse.
    """
    intent: str | None = None
    sop: str | None = None
    depth: str | None = None
    for line in (text or "").splitlines():
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("intent:"):
            value = low[len("intent:"):].strip()
            if value in VALID_INTENTS:
                intent = value
        elif low.startswith("sop:"):
            value = stripped[len("sop:"):].strip()
            if value in valid_sops:
                sop = value
        elif low.startswith("depth:"):
            value = low[len("depth:"):].strip()
            if value in VALID_DEPTHS:
                depth = value
    if intent is None:
        bare = (text or "").strip().lower()
        intent = bare if bare in VALID_INTENTS else "unknown"
    if sop is None:
        depth = "none"
    elif depth in (None, "none"):
        depth = "full_sop"
    return RouteProposal(intent, sop, depth)
```

- [ ] **Step 5: Ghi `depth` vào state**

Trong `backend/src/agents/routing.py` dòng ~136 (thân `intent_router`), sửa hai dòng:

```python
        intent, sop, depth = parse_proposal(response.content, valid_sops)
        # LUÔN ghi cả ba khoá (kể cả None/"none"): chúng TRANSIENT, đề cử của
        # lượt trước không được sống sót sang lượt sau.
        return {"intent": intent, "sop": sop, "depth": depth}
```

Và nhánh không có tin nhắn người dùng (dòng ~131):

```python
        if not last_human:
            return {"intent": "unknown", "sop": None, "depth": "none"}
```

Trong `backend/src/agents/state.py`, thêm ngay dưới trường `sop`:

```python
    depth: str | None             # độ sâu SOP router đề cử: "full_sop" |
                                  # "one_step" | "unsure" | "none". TRANSIENT
                                  # y hệt `sop` — intent_router ghi khoá này
                                  # trên MỌI return. "none" khi sop rỗng.
```

- [ ] **Step 6: Sửa hai chỗ unpack trong `run_eval.py`**

`backend/evals/run_eval.py` dòng 448 (trong `eval_intent`):

```python
        got, _sop, _depth = parse_proposal(resp.content, valid_sops)
```

Dòng 486 (trong `eval_sop_select`):

```python
        intent, sop, depth = parse_proposal(resp.content, valid_sops)
```

`depth` chưa dùng ở Task 1 — Task 6 mới chấm nó. Đặt tên đầy đủ ngay từ đây để Task 6 không phải sửa lại dòng này.

- [ ] **Step 7: Chạy test, xác nhận XANH**

```bash
python -m pytest tests/agents/test_intent_router.py -m "not integration and not live" -q
python -m pytest -m "not integration and not live" -q
```

Kỳ vọng: file test đó xanh; toàn bộ suite **1585 passed** (1581 + 4 test mới).

- [ ] **Step 8: Phá thử — chứng minh test canh thật**

Sửa tạm `parse_proposal`: đổi `depth = "full_sop"` ở nhánh fail-an-toàn thành `depth = "one_step"`. Chạy lại `tests/agents/test_intent_router.py` → phải ĐỎ ở `test_depth_la_khong_hop_le_thi_ve_full_sop`. Hoàn nguyên.

- [ ] **Step 9: Commit**

```bash
git add backend/src/agents/routing.py backend/src/agents/state.py backend/evals/run_eval.py backend/tests/agents/test_intent_router.py
git commit -m "feat(routing): them truong depth vao hop dong router (3 truong)"
```

---

## Task 2: Prompt hợp đồng 3 dòng + luật `depth`

**Files:**
- Modify: `backend/src/agents/prompts.py:32-56` (`INTENT_ROUTER_PROMPT`)
- Test: `backend/tests/agents/test_intent_router.py`

**Interfaces:**
- Consumes: `VALID_DEPTHS` (Task 1) — bốn giá trị trong prompt phải khớp đúng tập đó.
- Produces: `INTENT_ROUTER_PROMPT` mang hợp đồng 3 dòng. Task 6 đo trên chính prompt này.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `backend/tests/agents/test_intent_router.py`:

```python
def test_prompt_khai_bao_du_bon_gia_tri_depth():
    """Prompt và VALID_DEPTHS phải khớp nhau. Lệch một giá trị nghĩa là model
    được dạy nói một từ mà parse_proposal sẽ vứt đi — im lặng."""
    from src.agents.routing import VALID_DEPTHS
    for gia_tri in VALID_DEPTHS:
        assert gia_tri in INTENT_ROUTER_PROMPT, gia_tri


def test_prompt_khong_con_bat_sop_rong_vi_cau_ngan():
    """Luật CŨ bảo để `sop` rỗng khi 'a plain one-step command'. Chính luật đó
    làm 2/3 skill không nhận diện được câu đời thật. Nó phải BIẾN MẤT khỏi vế
    sop và sống ở luật depth."""
    assert "one-step command" not in INTENT_ROUTER_PROMPT
    assert "Do NOT leave it empty merely because the command is short" \
        in INTENT_ROUTER_PROMPT


def test_prompt_day_goi_ten_quy_trinh_la_tin_hieu_full_sop():
    """Spike vòng 2 bỏ sót đúng dòng này và hậu quả là 3 câu yêu cầu quy trình
    đầy đủ bị gán one_step — tức BỎ QUA kiểm tra ở đúng chỗ người dùng đã xin
    kiểm tra. Ghim lại."""
    assert "quy trình" in INTENT_ROUTER_PROMPT
    assert "strongest signal" in INTENT_ROUTER_PROMPT
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

```bash
python -m pytest tests/agents/test_intent_router.py -m "not integration and not live" -q
```

Kỳ vọng: FAIL ở cả ba test mới.

- [ ] **Step 3: Viết lại `INTENT_ROUTER_PROMPT`**

Trong `backend/src/agents/prompts.py`, thay TOÀN BỘ hằng `INTENT_ROUTER_PROMPT` (dòng 32-56). **Khối `intent` giữ NGUYÊN VĂN** — cổng eval `intent` (n=54, baseline 0.8704) đo chính khối đó, đổi chữ ở đấy là mở một biến số không cần thiết:

```python
INTENT_ROUTER_PROMPT = """Classify the user's latest message.

Reply with EXACTLY three lines and nothing else (no punctuation, no explanation):
intent: <one intent word>
sop: <one SOP worker name, or leave empty>
depth: <full_sop | one_step | unsure | none>

intent — choose EXACTLY ONE of:
erp_read   — query / read data from ERP: orders, inventory, customers, suppliers, revenue, top products, bill of materials (BoM) / production recipes, manufacturing orders, tasks/activities assigned to the user ("việc của tôi", "có việc gì chuyển cho tôi không")
erp_write  — create / update / delete data in ERP: create order, update stock, confirm purchase, marking an assigned task/activity as FINISHED ("xong việc rồi", "hoàn thành việc được giao", "việc này xong rồi", "đánh dấu hoàn tất việc"), etc.
rag        — questions about documents, manuals, policies, procedures, internal knowledge base
mixed      — needs BOTH an internal document/policy AND specific live ERP records together (e.g. "theo chính sách hoàn hàng, đơn của khách X có được hoàn không?")
unknown    — does not clearly fit any of the above

Rules for intent:
- When unsure between erp_read and erp_write, choose erp_read.
- When the question needs a policy/document AND specific ERP records together, choose mixed.
- Greetings / small talk → unknown.

Rules for sop — this field names the BUSINESS DOMAIN of the work, nothing
else. Judge by meaning, not by wording, and IGNORE how short or long the
request is. Fill it whenever the user wants work CARRIED OUT in one of the
domains listed below, no matter how briefly they say it. Leave it empty
("sop:" with nothing after) ONLY when:
- the user is merely ASKING ABOUT a procedure or policy (documentation lookup), or
- the work does not belong to any domain listed below.
Do NOT leave it empty merely because the command is short.
Never invent a worker name that is not listed.

Rules for depth — how much of the procedure the user wants carried out.
Write "none" when sop is empty. Otherwise choose:
- full_sop  — they want the complete procedure including its checks. Signals:
  they say "quy trình" / "SOP" / "đầy đủ" / "theo đúng quy trình"; or they ask
  to verify/count/compare/inspect; or they state a condition; or they describe
  several steps. Asking for the procedure BY NAME is the strongest signal.
- one_step  — they clearly want it done immediately without extra checks:
  words like "luôn", "ngay", or a bare command naming the action and the record.
- unsure    — the request names the domain and the record but gives NO signal
  either way, so both readings are equally reasonable.
Do not guess between full_sop and one_step. If there is no real signal, say
unsure — a wrong guess either skips safety checks or wastes the user's time."""
```

- [ ] **Step 4: Chạy test, xác nhận XANH**

```bash
python -m pytest tests/agents/ -m "not integration and not live" -q
```

Kỳ vọng: xanh. Nếu có test khác assert nguyên văn prompt cũ, ĐỌC test đó rồi cập nhật kỳ vọng — đừng nới prompt cho khớp test.

- [ ] **Step 5: Chạy toàn bộ suite**

```bash
python -m pytest -m "not integration and not live" -q
```

Kỳ vọng: **1588 passed** (1585 + 3 test mới).

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/prompts.py backend/tests/agents/test_intent_router.py
git commit -m "feat(prompts): hop dong router 3 dong, tach luat sop khoi luat depth"
```

---

## Task 3: Ba mô tả `SKILL.md` thuần miền

Mô tả skill là nơi logic độ sâu đang thật sự sống. Spike vòng 1 chứng minh: chỉ sửa khối prompt (Task 2) là KHÔNG đủ — mô tả thắng khối luật, `"nhận hàng cho đơn mua P00003"` vẫn ra `sop=None` dù luật mới cấm để rỗng vì câu ngắn.

**Files:**
- Modify: `backend/skills/nhap-kho/SKILL.md`, `backend/skills/giao-hang/SKILL.md`, `backend/skills/bao-gia-chiet-khau/SKILL.md` (chỉ khối `description:` trong front-matter)
- Test: `backend/tests/agents/test_skill_descriptions.py` (tạo mới)

**Interfaces:**
- Consumes: không.
- Produces: `description` của ba spec sạch logic độ sâu. Task 6 và 7 đo trên chúng.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_skill_descriptions.py`:

```python
# backend/tests/agents/test_skill_descriptions.py
"""Mô tả skill chỉ được nói về MIỀN NGHIỆP VỤ.

Logic độ sâu (chạy đủ quy trình hay làm nhanh một bước) sống ở luật `depth`
trong INTENT_ROUTER_PROMPT. Để nó lẫn vào mô tả là tái lập đúng lỗi mà đợt
2026-08-16 đi sửa: một trường phải trả lời hai câu hỏi.
"""
import pytest

from src.agents.skill_loader import load_skill_specs

# Cụm chỉ độ sâu — không cụm nào được xuất hiện trong mô tả miền.
CUM_DO_SAU = ("NGẮN GỌN một bước", "một bước", "planner tier-1")


@pytest.mark.parametrize("ten", ["nhap-kho", "giao-hang", "bao-gia-chiet-khau"])
def test_mo_ta_khong_con_logic_do_sau(ten):
    spec = next(s for s in load_skill_specs() if s.name == ten)
    for cum in CUM_DO_SAU:
        assert cum not in spec.description, f"{ten} còn cụm độ sâu: {cum!r}"


@pytest.mark.parametrize("ten", ["nhap-kho", "giao-hang", "bao-gia-chiet-khau"])
def test_mo_ta_van_giu_ve_loai_tru_cau_hoi(ten):
    """Nới nhận diện KHÔNG được đánh đổi bằng hijack: mô tả vẫn phải nói rõ
    câu hỏi-VỀ-quy-trình không thuộc miền này."""
    spec = next(s for s in load_skill_specs() if s.name == ten)
    assert "KHÔNG chọn khi" in spec.description


def test_bao_gia_khong_con_doi_chu_chiet_khau():
    """Mô tả cũ của bao-gia-chiet-khau mỏng hơn hẳn hai skill kia và đòi khái
    niệm "chiết khấu" — đo 2026-08-16: "Wood Corner mua 10 Desk Pad, tính giá
    cho khách này giúp tôi" rơi sang erp_read, tức không tạo báo giá và không
    áp chính sách chiết khấu nào."""
    spec = next(s for s in load_skill_specs()
                if s.name == "bao-gia-chiet-khau")
    assert "tính giá bán cho một khách hàng cụ thể" in spec.description
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

```bash
python -m pytest tests/agents/test_skill_descriptions.py -m "not integration and not live" -q
```

Kỳ vọng: FAIL — mô tả hiện tại còn cụm "NGẮN GỌN một bước".

- [ ] **Step 3: Thay ba khối `description:`**

`backend/skills/nhap-kho/SKILL.md` — thay khối `description: >-` (giữ nguyên mọi dòng khác của front-matter và toàn bộ thân prompt bên dưới):

```yaml
description: >-
  Miền nhận hàng vào kho theo một đơn mua. Chọn worker này khi người dùng
  muốn NHẬN HÀNG cho một đơn mua — kể cả câu rất ngắn, kể cả khi không nhắc
  chữ "quy trình", kể cả khi chỉ mô tả tình huống ("hàng về rồi, xử lý giúp
  tôi"). KHÔNG chọn khi người dùng chỉ hỏi quy trình nhập kho gồm những gì,
  hoặc khi họ muốn điều chỉnh tồn kho trực tiếp không qua đơn mua.
```

`backend/skills/giao-hang/SKILL.md`:

```yaml
description: >-
  Miền giao hàng cho đơn bán. Chọn worker này khi người dùng muốn ĐƯA HÀNG
  ĐI GIAO cho một đơn bán — kể cả câu rất ngắn, kể cả khi không nhắc chữ
  "quy trình", kể cả khi chỉ mô tả tình huống ("đóng gói xong rồi, cho đi
  giao", "khách giục đơn này, xuất cho khách"). KHÔNG chọn khi người dùng
  chỉ hỏi quy trình giao hàng gồm những gì.
```

`backend/skills/bao-gia-chiet-khau/SKILL.md`:

```yaml
description: >-
  Miền báo giá cho khách. Chọn worker này khi người dùng muốn LÀM một báo
  giá / tính giá bán cho một khách hàng cụ thể — kể cả khi họ không nhắc tới
  chữ "chiết khấu" (cấp khách và chiết khấu do chính quy trình xác định).
  KHÔNG chọn khi người dùng chỉ hỏi về chính sách chiết khấu.
```

- [ ] **Step 4: Chạy test, xác nhận XANH**

```bash
python -m pytest tests/agents/test_skill_descriptions.py -m "not integration and not live" -q
python -m pytest -m "not integration and not live" -q
```

Kỳ vọng: **1595 passed** (1588 + 7 test mới — hai test dùng `parametrize` 3 giá trị nên đếm thành 6, cộng 1 test đơn). Nếu có test khác assert nguyên văn mô tả cũ, cập nhật kỳ vọng của test đó.

- [ ] **Step 5: Commit**

```bash
git add backend/skills/nhap-kho/SKILL.md backend/skills/giao-hang/SKILL.md backend/skills/bao-gia-chiet-khau/SKILL.md backend/tests/agents/test_skill_descriptions.py
git commit -m "feat(skills): ba mo ta SKILL.md thuan mien, roi logic do sau sang depth"
```

---

## Task 4: `decide_route` ánh xạ `(sop, depth)`

**Files:**
- Modify: `backend/src/agents/routing.py:211-246` (`decide_route`)
- Test: `backend/tests/agents/test_skill_gate.py`

**Interfaces:**
- Consumes: `state["depth"]` (Task 1).
- Produces: `decide_route` trả `"erp_write"` cho `one_step`. Task 5 đổi nhánh `unsure`.

⚠️ **Ở task này `unsure` TẠM rơi vào cùng nhánh `full_sop`** (chạy node SOP) vì node `clarify_depth` chưa tồn tại — `decide_route` trả về một tên không có trong `intent_targets` sẽ làm LangGraph ném lỗi định tuyến giữa lượt chat thật. Task 5 đổi nhánh đó. Có test ghim trạng thái tạm này để nó không bị quên.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `backend/tests/agents/test_skill_gate.py`:

```python
# ── decide_route ánh xạ cặp (sop, depth) ─────────────────────────────────────


def _state_sop(text: str, sop: str, depth: str):
    from langchain_core.messages import HumanMessage
    return {"messages": [HumanMessage(content=text)],
            "intent": "erp_write", "sop": sop, "depth": depth}


def test_full_sop_vao_node_sop():
    from src.agents.routing import decide_route
    got = decide_route(_state_sop(
        "làm quy trình nhập kho cho đơn mua P00021", "nhap-kho", "full_sop"))
    assert got == "nhap-kho"


def test_one_step_ve_write_planner_khong_vao_sop():
    """Quyết định của chủ dự án: one_step đi ĐÚNG đường erp_write hôm nay, nên
    hành vi cuối không đổi và ba ca eval đang kỳ vọng erp_write giữ nguyên kỳ
    vọng dù router nay điền `sop` cho chúng."""
    from src.agents.routing import decide_route
    got = decide_route(_state_sop(
        "giao hàng cho đơn S00040 luôn nhé", "giao-hang", "one_step"))
    assert got == "erp_write"


def test_depth_none_giu_nguyen_hanh_vi_cu():
    from src.agents.routing import decide_route
    got = decide_route(_state_sop(
        "nhập kho cho đơn P00021", "nhap-kho", "none"))
    assert got == "nhap-kho"


def test_unsure_tam_thoi_chay_full_sop_cho_task_5():
    """TẠM THỜI. Task 5 đổi nhánh này sang node clarify_depth. Ghim lại để
    trạng thái tạm không nằm im: khi Task 5 xong, test này PHẢI đỏ và được
    thay bằng test khẳng định route đi 'clarify_depth'."""
    from src.agents.routing import decide_route
    got = decide_route(_state_sop(
        "kho báo hàng P00021 đã tới, cần làm gì tiếp", "nhap-kho", "unsure"))
    assert got == "nhap-kho"


def test_phu_quyet_cau_hoi_van_can_du_depth_la_one_step():
    """Lớp phủ quyết tất định GIỮ NGUYÊN. Spike cho thấy model mới tự xử đúng
    15/15 ở nhóm an toàn — nhưng đó không phải lý do tháo một lớp phòng thủ
    tốn 10 dòng đã chứng minh giá trị."""
    from src.agents.routing import decide_route
    got = decide_route({"messages": [__import__(
        "langchain_core.messages", fromlist=["HumanMessage"]).HumanMessage(
            content="quy trình nhập kho là gì?")],
        "intent": "rag", "sop": "nhap-kho", "depth": "one_step"})
    assert got == "rag"
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

```bash
python -m pytest tests/agents/test_skill_gate.py -m "not integration and not live" -q
```

Kỳ vọng: FAIL ở `test_one_step_ve_write_planner_khong_vao_sop` (hiện trả `"giao-hang"`).

- [ ] **Step 3: Sửa `decide_route`**

Trong `backend/src/agents/routing.py`, thay hai dòng cuối thân hàm (`if intent == "erp_write" or not looks_like_question(folded): return sop`):

```python
    intent = state.get("intent") or "unknown"
    sop = state.get("sop")
    depth = state.get("depth") or "none"
    if sop and skill_gate.skills_enabled():
        last_human = next((m.content for m in reversed(state["messages"])
                           if m.type == "human"), "")
        folded = _fold(last_human)
        if intent == "erp_write" or not looks_like_question(folded):
            # `sop` nói MIỀN, `depth` nói SÂU TỚI ĐÂU — hai câu hỏi tách rời
            # từ 2026-08-16. one_step đi đúng đường erp_write hôm nay nên hành
            # vi cuối KHÔNG đổi; SOP chỉ nhận trọn lượt khi người dùng thật sự
            # muốn cả quy trình.
            if depth == "one_step":
                return "erp_write"
            # TẠM THỜI: "unsure" rơi chung nhánh với "full_sop" vì node
            # clarify_depth chưa tồn tại — trả một tên ngoài intent_targets sẽ
            # làm LangGraph ném lỗi định tuyến giữa lượt chat thật.
            return sop
    return intent                 # phủ quyết: rớt sop, dùng intent
```

- [ ] **Step 4: Chạy test, xác nhận XANH**

```bash
python -m pytest tests/agents/test_skill_gate.py -m "not integration and not live" -q
python -m pytest -m "not integration and not live" -q
```

Kỳ vọng: **1600 passed** (1595 + 5 test mới).

- [ ] **Step 5: Phá thử**

Đổi `if depth == "one_step"` thành `if depth == "khong_bao_gio"`. Chạy `tests/agents/test_skill_gate.py` → phải ĐỎ ở `test_one_step_ve_write_planner_khong_vao_sop`. Hoàn nguyên.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/routing.py backend/tests/agents/test_skill_gate.py
git commit -m "feat(routing): decide_route anh xa cap (sop, depth)"
```

---

## Task 5: Node `clarify_depth`

⚠️ **ĐỌC TRƯỚC KHI THIẾT KẾ CHỖ NÀY.** Cơ chế write-confirmation bản đầu gắn tín hiệu vào `AIMessage.additional_kwargs` và **CHẾT HOÀN TOÀN TRONG PRODUCTION**: `erp_agent._invoke_fresh` chạy trên MỌI lượt không parked và dựng lại kênh `messages` từ payload client, mà `main.py._filter_messages` đã lược mỗi message còn `{"role", "content"}` — nên `additional_kwargs` không sống sót một lượt nào. **6 vòng review không ai thấy** vì không test nào đi qua entry point HTTP thật. Task này dùng `interrupt` (trạng thái parked, do checkpointer giữ), KHÔNG gắn gì lên message.

Không cần `kind` mới: `interrupt(kind="disambiguation")` đã có sẵn và `_decide_resume` parse lựa chọn **tất định** qua `parse_selection` (nhận cả số thứ tự lẫn tên).

**Files:**
- Modify: `backend/src/agents/nodes.py` (thêm `make_clarify_depth_node`)
- Modify: `backend/src/agents/routing.py` (`decide_route`: `unsure` → `"clarify_depth"`; thêm `route_after_clarify`)
- Modify: `backend/src/agents/graph.py:85` (đăng ký node), `:101-110` (`intent_targets` + cạnh mới)
- Test: `backend/tests/agents/test_clarify_depth.py` (tạo mới), `backend/tests/agents/test_skill_gate.py` (sửa 1 test)

**Interfaces:**
- Consumes: `state["sop"]`, `state["depth"]` (Task 1), `decide_route` (Task 4).
- Produces: `make_clarify_depth_node() -> callable`; `CLARIFY_DEPTH_OPTIONS: list[dict]`; `route_after_clarify(state) -> str`.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_clarify_depth.py`:

```python
# backend/tests/agents/test_clarify_depth.py
"""Node hỏi lại khi router không chắc người dùng muốn chạy đủ quy trình hay
làm nhanh một bước.

Đo 2026-08-16: `unsure` bắn 2/18 ca (11%) và cả hai đều mơ hồ thật, tất định
qua 3 lượt. Đây là đường DUY NHẤT thật sự mới của đợt này.
"""
import pytest

from src.agents.nodes import CLARIFY_DEPTH_OPTIONS, make_clarify_depth_node
from src.agents.routing import route_after_clarify


def test_hai_lua_chon_dung_id_khop_valid_depths():
    """id của lựa chọn ĐI THẲNG vào state["depth"] qua Command(resume=...),
    nên phải là giá trị depth hợp lệ, không phải nhãn hiển thị."""
    from src.agents.routing import VALID_DEPTHS
    ids = [o["id"] for o in CLARIFY_DEPTH_OPTIONS]
    assert ids == ["full_sop", "one_step"]
    assert set(ids) <= VALID_DEPTHS
    assert all(o["name"].strip() for o in CLARIFY_DEPTH_OPTIONS)


@pytest.mark.asyncio
async def test_node_park_bang_interrupt_dang_disambiguation(monkeypatch):
    """kind PHẢI là "disambiguation": erp_agent._decide_resume parse lựa chọn
    TẤT ĐỊNH cho kind đó (parse_selection). Rơi về "confirm" sẽ ép câu trả lời
    qua bộ phân loại có/không và phá hẳn lượt hỏi hai lựa chọn."""
    import src.agents.nodes as nodes_mod
    da_goi = {}

    def gia_interrupt(payload):
        da_goi.update(payload)
        return "full_sop"

    monkeypatch.setattr(nodes_mod, "_interrupt", gia_interrupt)
    node = make_clarify_depth_node()
    out = await node({"messages": [], "sop": "nhap-kho", "depth": "unsure"})

    assert da_goi["kind"] == "disambiguation"
    assert da_goi["options"] == CLARIFY_DEPTH_OPTIONS
    assert da_goi["question"].strip()
    assert out["depth"] == "full_sop"


@pytest.mark.asyncio
async def test_tra_loi_khong_hop_le_thi_ve_full_sop(monkeypatch):
    """FAIL AN TOÀN, cùng lý do với parse_proposal: chiều one_step là chiều bỏ
    qua kiểm tra, không bao giờ là mặc định khi không hiểu câu trả lời."""
    import src.agents.nodes as nodes_mod
    monkeypatch.setattr(nodes_mod, "_interrupt", lambda payload: "banana")
    node = make_clarify_depth_node()
    out = await node({"messages": [], "sop": "nhap-kho", "depth": "unsure"})
    assert out["depth"] == "full_sop"


def test_sau_khi_chon_thi_di_dung_dich():
    assert route_after_clarify(
        {"sop": "nhap-kho", "depth": "full_sop"}) == "nhap-kho"
    assert route_after_clarify(
        {"sop": "nhap-kho", "depth": "one_step"}) == "erp_write"


def test_mat_sop_thi_khong_treo_lai():
    """`sop` TRANSIENT. Nếu vì lý do nào đó nó rỗng lúc quay lại, phải có đích
    đi tiếp chứ không được trả một tên node không tồn tại."""
    assert route_after_clarify({"sop": None, "depth": "full_sop"}) == "erp_write"
```

Và SỬA `test_unsure_tam_thoi_chay_full_sop_cho_task_5` trong `backend/tests/agents/test_skill_gate.py` — chép đè nguyên hàm:

```python
def test_unsure_di_toi_node_hoi_lai():
    """Đường DUY NHẤT thật sự mới của đợt này: câu mơ hồ thì hỏi, không đoán."""
    from src.agents.routing import decide_route
    got = decide_route(_state_sop(
        "kho báo hàng P00021 đã tới, cần làm gì tiếp", "nhap-kho", "unsure"))
    assert got == "clarify_depth"
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

```bash
python -m pytest tests/agents/test_clarify_depth.py tests/agents/test_skill_gate.py -m "not integration and not live" -q
```

Kỳ vọng: FAIL — `ImportError: cannot import name 'CLARIFY_DEPTH_OPTIONS'`.

- [ ] **Step 3: Viết node**

Thêm vào `backend/src/agents/nodes.py`, ngay sau khối `respond_unknown` (dòng ~118):

```python
# ── clarify_depth ─────────────────────────────────────────────────────────────

# id ĐI THẲNG vào state["depth"] qua Command(resume=...) của _decide_resume,
# nên phải là giá trị VALID_DEPTHS, không phải nhãn hiển thị.
CLARIFY_DEPTH_OPTIONS = [
    {"id": "full_sop", "name": "Chạy đủ quy trình (có các bước kiểm tra)"},
    {"id": "one_step", "name": "Làm nhanh một bước, bỏ qua kiểm tra"},
]


def make_clarify_depth_node():
    """Hỏi người dùng muốn chạy đủ quy trình hay làm nhanh một bước.

    CHỈ chạy khi router trả depth="unsure" — đo 2026-08-16 là 2/18 ca (11%),
    cả hai đều mơ hồ thật và tất định qua 3 lượt.

    Dùng interrupt(kind="disambiguation") CÓ SẴN, không phát minh kind mới:
    erp_agent._decide_resume parse lựa chọn TẤT ĐỊNH cho kind đó qua
    parse_selection (nhận cả số thứ tự lẫn tên). Rơi về "confirm" sẽ ép câu
    trả lời qua bộ phân loại có/không và phá hẳn lượt hỏi hai lựa chọn.

    ⚠️ Tín hiệu sống qua lượt nằm ở TRẠNG THÁI PARKED do checkpointer giữ,
    KHÔNG gắn lên AIMessage: bản đầu của cơ chế write-confirmation làm thế và
    chết hoàn toàn trong production vì _invoke_fresh dựng lại kênh messages từ
    payload client (main.py._filter_messages đã lược còn role+content).
    """
    async def clarify_depth(state: ERPAgentState) -> dict:
        chon = _interrupt({
            "kind": "disambiguation",
            "question": "Bạn muốn chạy đủ quy trình (có các bước kiểm tra) "
                        "hay làm nhanh một bước?",
            "options": CLARIFY_DEPTH_OPTIONS,
        })
        # FAIL AN TOÀN: không hiểu câu trả lời thì chạy ĐỦ quy trình. Chiều
        # one_step là chiều BỎ QUA kiểm tra.
        if chon not in ("full_sop", "one_step"):
            chon = "full_sop"
        return {"depth": chon}

    return clarify_depth
```

- [ ] **Step 4: Thêm `route_after_clarify` và đổi nhánh `unsure`**

Trong `backend/src/agents/routing.py`, sửa nhánh tạm của Task 4:

```python
            if depth == "one_step":
                return "erp_write"
            if depth == "unsure":
                return "clarify_depth"
            return sop
```

Và thêm hàm mới ngay dưới `decide_route`:

```python
def route_after_clarify(state: ERPAgentState) -> str:
    """Đích sau khi người dùng đã chọn độ sâu. Cùng luật với decide_route,
    nhưng KHÔNG chạy lại lớp phủ quyết câu-hỏi: lượt này người dùng vừa trả
    lời một câu hỏi hai lựa chọn, không phải vừa gửi một yêu cầu mới.

    `sop` TRANSIENT nên phòng trường hợp nó rỗng lúc quay lại: trả erp_write
    thay vì một tên node không tồn tại (LangGraph sẽ ném lỗi định tuyến giữa
    lượt chat thật).
    """
    sop = state.get("sop")
    if not sop or state.get("depth") == "one_step":
        return "erp_write"
    return sop
```

- [ ] **Step 5: Đấu dây vào graph**

Trong `backend/src/agents/graph.py`, thêm import ở đầu file (cùng khối `from .nodes import`):

```python
    make_clarify_depth_node,
```

và `route_after_clarify` vào dòng `from .routing import make_intent_router_node, decide_route`:

```python
from .routing import make_intent_router_node, decide_route, route_after_clarify
```

Đăng ký node ngay sau `respond_unknown` (dòng ~85):

```python
    g.add_node("clarify_depth", make_clarify_depth_node())
```

Thêm đích vào `intent_targets` (dòng ~101-108) và cạnh có điều kiện sau `g.add_conditional_edges("intent_router", ...)`:

```python
    intent_targets = {
        "erp_read": "erp_read",
        "erp_write": "erp_write_planner",
        "rag": "rag",
        "mixed": "mixed",
        "unknown": "respond_unknown",
        "clarify_depth": "clarify_depth",
    }
    intent_targets.update({s.name: s.name for s in skill_specs})
    g.add_conditional_edges("intent_router", decide_route, intent_targets)

    # Sau khi người dùng chọn độ sâu: cùng tập đích với intent_targets phần
    # SOP + erp_write. KHÔNG dùng lại intent_targets nguyên khối — clarify_depth
    # trỏ về chính nó sẽ tạo vòng lặp.
    clarify_targets = {"erp_write": "erp_write_planner"}
    clarify_targets.update({s.name: s.name for s in skill_specs})
    g.add_conditional_edges("clarify_depth", route_after_clarify, clarify_targets)
```

- [ ] **Step 6: Chạy test, xác nhận XANH**

```bash
python -m pytest tests/agents/test_clarify_depth.py tests/agents/test_skill_gate.py -m "not integration and not live" -q
python -m pytest -m "not integration and not live" -q
```

Kỳ vọng: **1605 passed** (1600 + 5 test mới; `test_unsure_tam_thoi_...` bị đổi tên chứ không thêm bớt).

- [ ] **Step 7: Phá thử — chứng minh cạnh thật sự được đấu**

Thêm test dựng graph THẬT vào `backend/tests/agents/test_clarify_depth.py` **trước** khi phá — một cạnh không test nào canh thì gỡ hẳn vẫn xanh, đúng lớp lỗi "test không đo gì" đã xuất hiện nhiều lần ở repo này:

```python
def test_clarify_depth_co_mat_trong_graph_that():
    """Đường dây graph phải có test canh. Đo được ở đợt bản-tin-việc-cần-xử-lý:
    hardcode role=None mà 1564/1565 test vẫn xanh, vì không test nào dựng graph
    thật để kiểm cạnh."""
    from src.agents.graph import build_graph
    from tests.conftest import make_mock_llm

    llms = {k: make_mock_llm("intent: rag\nsop:\ndepth: none")
            for k in ("router", "read", "planner", "rag", "fusion",
                      "synthesis", "chitchat", "evaluator")}
    graph = build_graph(llms, tools=[])
    ve = graph.get_graph()
    assert "clarify_depth" in ve.nodes
    canh_ra = [e for e in ve.edges if e.source == "clarify_depth"]
    assert canh_ra, "clarify_depth không có cạnh ra — người dùng sẽ kẹt ở đó"
```

⚠️ Chữ ký `build_graph(...)` trong repo có thể khác — ĐỌC `backend/src/agents/graph.py` và các test đang dựng graph (`tests/agents/test_graph_build.py`) rồi khớp đúng tham số, đừng đoán.

Chạy nó, xác nhận XANH. Rồi xoá tạm dòng `g.add_conditional_edges("clarify_depth", route_after_clarify, clarify_targets)` → test này phải ĐỎ. Hoàn nguyên.

- [ ] **Step 8: Commit**

```bash
git add backend/src/agents/nodes.py backend/src/agents/routing.py backend/src/agents/graph.py backend/tests/agents/test_clarify_depth.py backend/tests/agents/test_skill_gate.py
git commit -m "feat(routing): node clarify_depth hoi lai khi router khong chac do sau"
```

---

## Task 6: Bộ eval hết mù

`SOP_SELECT_CASES` hiện có đúng MỘT ca dương-không-chữ-"quy trình" mỗi skill, và cả ba vẫn nói rõ điều kiện ra. Đó là lý do gate báo 16/17 và trông như chỉ có một ca lẻ hỏng, trong khi 2/3 skill không nhận diện được theo ngữ nghĩa.

Kỳ vọng đổi từ MỘT giá trị sang CẶP `(đích, depth)`. Chỉ chấm đích thì `depth` không được canh và sẽ trôi âm thầm — đúng lớp lỗi "test không đo gì" đã xuất hiện ba lần trong một đợt trước.

**Files:**
- Modify: `backend/evals/cases.py` (`SOP_SELECT_CASES`)
- Modify: `backend/evals/run_eval.py:462-505` (`eval_sop_select`)
- Test: `backend/tests/jobs/test_eval_sop_select.py` (tạo mới)

**Interfaces:**
- Consumes: `parse_proposal(...).depth` (Task 1), `decide_route` (Task 4/5).
- Produces: `SOP_SELECT_CASES: list[tuple[str, str, str]]`; `eval_sop_select` trả thêm khoá `depth_acc`.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/jobs/test_eval_sop_select.py`:

```python
# backend/tests/jobs/test_eval_sop_select.py
"""Bộ ca sop_select phải đo cả MIỀN lẫn ĐỘ SÂU, và phải phủ được câu đời thật.

Trước 2026-08-16 bộ này mù với nhận diện ngữ nghĩa: mỗi skill đúng 1 ca dương
không-chữ-"quy trình", và cả ba ca đó vẫn nói rõ điều kiện ra.
"""
from evals.cases import SOP_SELECT_CASES

SOPS = {"giao-hang", "nhap-kho", "bao-gia-chiet-khau"}


def test_moi_ca_la_bo_ba():
    for ca in SOP_SELECT_CASES:
        assert len(ca) == 3, ca


def test_depth_ky_vong_luon_hop_le():
    from src.agents.routing import VALID_DEPTHS
    for _text, _dich, depth in SOP_SELECT_CASES:
        assert depth in VALID_DEPTHS, depth


def test_ca_hoi_ve_quy_trinh_thi_depth_la_none():
    """Câu hỏi-VỀ-quy-trình ⇒ sop rỗng ⇒ depth "none" (bất biến của
    parse_proposal). Đây cũng chính là nhóm hijack: depth khác "none" ở một ca
    `rag` nghĩa là router đã điền sop cho một câu tra cứu tài liệu.

    KHÔNG assert "mọi ca không-phải-SOP đều depth none": đích `erp_write` có
    thể đến từ (sop được điền, one_step) — đó là đúng thiết kế, không phải
    sop rỗng."""
    for text, dich, depth in SOP_SELECT_CASES:
        if dich == "rag":
            assert depth == "none", text


def test_du_ca_ngu_nghia():
    """Ca ngữ nghĩa = câu KHÔNG chứa "quy trình"/"SOP" mà router vẫn phải nhận
    ra MIỀN. Nhận diện miền thành công ⟺ depth != "none" (bất biến
    parse_proposal), BẤT KỂ đích cuối là node SOP hay erp_write — vì
    decide_route đưa one_step về erp_write.

    Đây là nhóm bộ đo cũ thiếu hẳn: trước 2026-08-16 mỗi skill đúng 1 ca, và
    cả ba ca đó vẫn nói rõ điều kiện ra."""
    ngu_nghia = [t for t, _dich, d in SOP_SELECT_CASES
                 if d != "none"
                 and "quy trình" not in t.lower()
                 and "sop" not in t.lower()]
    assert len(ngu_nghia) >= 6, ngu_nghia


def test_co_ca_unsure():
    assert any(d == "unsure" for _t, _dich, d in SOP_SELECT_CASES)


def test_moi_skill_co_ca_full_sop_lan_one_step():
    for sop in SOPS:
        depths = {d for _t, dich, d in SOP_SELECT_CASES if dich == sop}
        assert "full_sop" in depths, sop
    assert any(d == "one_step" for _t, _dich, d in SOP_SELECT_CASES)
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

```bash
python -m pytest tests/jobs/test_eval_sop_select.py -m "not integration and not live" -q
```

Kỳ vọng: FAIL ở `test_moi_ca_la_bo_ba` (ca hiện là cặp 2 phần tử).

- [ ] **Step 3: Viết lại `SOP_SELECT_CASES`**

Trong `backend/evals/cases.py`, thay TOÀN BỘ danh sách `SOP_SELECT_CASES` (giữ nguyên khối comment mô tả phía trên, nối thêm đoạn giải thích trường thứ ba):

```python
# Mỗi ca là BỘ BA: (câu, đích định tuyến kỳ vọng, depth kỳ vọng).
#
# Trường thứ ba thêm 2026-08-16 khi `sop` được tách thành MIỀN (`sop`) và ĐỘ
# SÂU (`depth`). Chỉ chấm đích thì `depth` không được canh và sẽ trôi âm thầm.
# Ca không vào SOP có depth "none" (bất biến của parse_proposal).
#
# Ba ca dưới đây kỳ vọng "erp_write" DÙ router nay điền `sop` cho chúng —
# decide_route ánh xạ (sop, one_step) → erp_write nên hành vi cuối GIỐNG HỆT
# trước đợt này.
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
    # NGỮ NGHĨA
    ("hàng của đơn mua P00021 về rồi, xử lý giúp tôi", "erp_write", "one_step"),
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

    # ── câu bắc cầu (§6.4) ──
    ("điều chỉnh tồn kho Desk Pad về 100", "erp_write", "none"),
]
```

⚠️ Ba ca ngữ nghĩa (`"đơn S00012 đóng gói xong rồi..."`, `"khách giục..."`, `"hàng của đơn mua P00021 về rồi..."`) kỳ vọng `erp_write`/`one_step` **theo số đo spike**, không theo mong muốn. Nếu Task 7 đo ra khác, ĐỌC số đo rồi quyết — đừng sửa kỳ vọng cho khớp mà không hiểu vì sao.

- [ ] **Step 4: Cho `eval_sop_select` chấm cặp**

Trong `backend/evals/run_eval.py`, thay thân `call` và khối trả về của `eval_sop_select`:

```python
    async def call(case):
        text, expected, expected_depth = case
        resp, ms = await _timed(llm.ainvoke(
            [SystemMessage(content=prompt), HumanMessage(content=text)]))
        lat.append(ms)
        intent, sop, depth = parse_proposal(resp.content, valid_sops)
        got = decide_route({"messages": [HumanMessage(content=text)],
                            "intent": intent, "sop": sop, "depth": depth})
        depth_ok = depth == expected_depth
        if got == expected and depth_ok:
            return None
        return {"text": text, "expected": expected, "got": got,
                "expected_depth": expected_depth, "got_depth": depth,
                "depth_ok": depth_ok,
                "raw_intent": intent, "raw_sop": sop,
                "hijack": expected not in valid_sops and got in valid_sops}

    fails, errors = await run_resilient(SOP_SELECT_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(SOP_SELECT_CASES)
    # CHỈ đếm từ fails (phép đo thành công) — lỗi API không bao giờ là hijack.
    hijack = sum(1 for f in fails if f["hijack"])
    depth_wrong = sum(1 for f in fails if not f["depth_ok"])
    p50, p95 = _percentiles(lat)
    return {"set": "sop_select", "n": n,
            "acc": (n - len(fails) - len(errors)) / n if n else 0.0,
            "depth_acc": (n - depth_wrong - len(errors)) / n if n else 0.0,
            "hijack": hijack,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}
```

⚠️ `acc` nay đòi **cả hai** vế đúng, nên nó **nghiêm hơn** trước. Đó là chủ đích: gate tuyệt đối phải gác cả `depth`.

- [ ] **Step 5: Đếm lại số ca và chạy test**

```bash
python -c "import sys; sys.path.insert(0,'.'); from evals.cases import SOP_SELECT_CASES; print(len(SOP_SELECT_CASES))"
python -m pytest tests/jobs/test_eval_sop_select.py -m "not integration and not live" -q
python -m pytest -m "not integration and not live" -q
```

Kỳ vọng: **24 ca**; test mới xanh; toàn bộ suite **1611 passed** (1605 + 6 test mới). Nếu số ca khác 24, GHI SỐ THẬT vào báo cáo — đừng sửa cho khớp plan.

`jobs/eval_gate.py` **không cần đổi một dòng nào**: `_gate` đọc
`result["hijack"] == 0 and result["acc"] == 1.0`, mà `acc` nay đã đòi cả `depth`
đúng. `depth_acc` chỉ để chẩn đoán — nó nói cho người đọc biết một lượt trượt là
trượt miền hay trượt độ sâu.

- [ ] **Step 6: Commit**

```bash
git add backend/evals/cases.py backend/evals/run_eval.py backend/tests/jobs/test_eval_sop_select.py
git commit -m "feat(evals): sop_select cham ca mien lan do sau, them ca ngu nghia"
```

---

## Task 7: Đo thật và nghiệm thu sống

Không viết code sản phẩm. Nhiệm vụ: chứng minh đợt này đạt mục tiêu, hoặc nói rõ nó không đạt ở đâu.

**Files:**
- Create: `docs/superpowers/plans/2026-08-16-sop-domain-depth-split-report.md`

**Interfaces:**
- Consumes: mọi thứ Task 1-6 dựng.

- [ ] **Step 1: Chạy cổng `sop_select`**

`evals/run_eval.py` KHÔNG tự nạp `.env` (đã kiểm: không có `load_dotenv` nào trong file). Tạo `backend/run_eval_env.py`, đo xong thì **xoá, KHÔNG commit**:

```python
# backend/run_eval_env.py — tệp tạm, XOÁ sau khi đo xong, KHÔNG commit
import asyncio
import sys

from dotenv import load_dotenv

load_dotenv(r"D:\Youdoo\.env")
sys.path.insert(0, r"D:\Youdoo\backend")

from evals.run_eval import main  # noqa: E402

asyncio.run(main(sys.argv[1:]))
```

```bash
python run_eval_env.py --set sop_select --model gemini-3.1-flash-lite --pace 4.8
```

`--pace 4.8` suy từ `rpm=15` của `gemini-3.1-flash-lite`: `(60/15)*1.2`. Đó là model đầu chuỗi vai `router` — đúng cái production đang chạy.

Kỳ vọng: `acc = 1.000`, `hijack = 0`, `depth_acc = 1.000`, `errors = []`.

**Mục tiêu là đưa `sop_select` về XANH lần đầu kể từ 2026-07-31.** Không đạt thì **ghi rõ còn ca nào và vì sao** — KHÔNG nới ngưỡng, KHÔNG sửa kỳ vọng ca cho khớp kết quả.

- [ ] **Step 2: Chạy cổng `intent` — chứng minh không thụt**

Hợp đồng đổi từ 2 dòng sang 3 dòng chạm vào MỌI lượt phân loại ý định, không chỉ SOP.

```bash
python run_eval_env.py --set intent --model gemini-3.1-flash-lite --pace 4.8 --baseline evals/baseline-qwen3-8b-intent.json
```

Kỳ vọng: `GATE PASS`, `acc >= 0.8704`.

- [ ] **Step 3: Đo vai kế toán — khối worker RỖNG**

Vai kế toán giữ 0 skill ⇒ `sop` luôn rỗng, `depth` luôn `"none"`. Cấu hình này **đã từng làm router phân loại lệnh ghi thành `unknown` 3/3** và chỉ nghiệm thu sống mới bắt được.

```bash
python run_eval_env.py --set intent --model gemini-3.1-flash-lite --role accounting --pace 4.8
```

Kỳ vọng: `errors = []` và `acc` không thấp hơn đáng kể số admin ở Step 2. Ghi con số vào báo cáo.

- [ ] **Step 4: Nghiệm thu sống QUA HTTP THẬT**

⚠️ **Bắt buộc đi qua entry point HTTP**, không gọi graph trực tiếp. Lý do ở Task 5: một cơ chế từng xanh mọi test nội bộ mà chết hoàn toàn trong production vì `_invoke_fresh`, và 6 vòng review không thấy.

Khởi động backend bằng `start-dev.ps1` (nó ghi đè `ODOO_USERNAME=ai-readonly` — đường đọc production dùng tài khoản đó, khác `.env`; đo bằng tài khoản khác sẽ ra số khác và dễ hiểu nhầm thành bug).

Bốn kịch bản, mỗi cái một `session_id` RIÊNG:

| # | câu | kỳ vọng |
|---|---|---|
| 1 | `làm quy trình nhập kho cho đơn mua P00021` | vào SOP `nhap-kho`, hỏi kiểm đếm |
| 2 | `nhận hàng cho đơn mua P00003` | đi write planner, hỏi xác nhận một bước |
| 3 | `kho báo hàng P00021 đã tới, cần làm gì tiếp` | **hỏi lại 2 lựa chọn**; gửi tiếp `1` ở CÙNG session → chạy đủ quy trình |
| 4 | `quy trình nhập kho là gì?` | trả lời tài liệu, KHÔNG vào SOP |

Kịch bản 3 là kịch bản DUY NHẤT chứng minh đường mới hoạt động đầu-cuối. Nó phải đi **hai lượt HTTP tách rời** — một lượt hỏi, một lượt trả lời — chứ không phải một lượt.

- [ ] **Step 5: Viết báo cáo**

Tạo `docs/superpowers/plans/2026-08-16-sop-domain-depth-split-report.md` gồm: số đo từng bước ở trên (nguyên văn JSON của eval), kết quả 4 kịch bản sống, mọi chỗ lệch so với dự đoán của spike, và danh sách những gì CHƯA làm được.

Nếu `sop_select` chưa xanh: nói thẳng ở đầu báo cáo, kèm ca nào trượt và `raw_intent`/`raw_sop`/`got_depth` của nó.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/plans/2026-08-16-sop-domain-depth-split-report.md
git commit -m "docs(report): so do va nghiem thu song cho tach mien/do sau"
```

---

## Ghi chú cho người thực thi

- **Chạy lại `git status` sau mỗi lượt pytest.** Bộ test từng ghi đè hai file fixture nhị phân đã commit — đã sửa ở `abee368`, nhưng nếu thấy file lạ "modified" mà mình không đụng thì nghi lớp lỗi đó trước.
- **Số test kỳ vọng ở mỗi task là số CỘNG DỒN** tính từ mốc 1581. Lệch thì đếm lại bằng `--collect-only` và ghi số thật vào báo cáo task, đừng tự sửa cho khớp.
- **Ba ca eval kỳ vọng `erp_write`** (`"giao hàng cho đơn S00040 luôn nhé"`, `"nhận hàng cho đơn mua P00003"`, `"tạo báo giá cho Azure Interior, 2 Large Cabinet"`) giữ nguyên kỳ vọng **có chủ đích**. Router nay điền `sop` cho chúng nhưng `decide_route` đưa `one_step` về `erp_write`, nên hành vi cuối không đổi. Đó là bằng chứng đợt này gần như thuần THÊM khả năng.
