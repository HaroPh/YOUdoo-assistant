# Đa ngôn ngữ Việt–Anh — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Youdoo trả lời bằng tiếng Anh khi người dùng viết tiếng Anh, bằng tiếng Việt khi viết tiếng Việt, không thụt bất kỳ cổng eval nào.

**Architecture:** Hai tầng tách biệt. (1) Mọi chuỗi do LLM sinh ra — `erp_read`, `rag`, `chitchat`, `mixed` — xử lý **hoàn toàn ở tầng prompt**: gỡ chỉ dẫn ngôn ngữ ghim cứng ở đầu, thêm khối `LANGUAGE RULE` ở cuối. Không sửa một chuỗi thông báo nào ở tầng MCP/đọc. (2) Chuỗi điều phối ghi (đi thẳng ra người dùng, không LLM đứng giữa) đi qua một chốt `localize()` duy nhất trong `ERPAgent.chat()`: LLM dịch, rồi **lớp phủ quyết tất định** kiểm mọi số/mã chứng từ còn nguyên vẹn, lệch thì rơi về bản tiếng Việt.

**Tech Stack:** Python 3.11, LangGraph, LangChain, pytest.

**Spec:** `docs/superpowers/specs/2026-08-18-multilingual-vi-en-design.md`

## Global Constraints

- **Định danh trong `backend/src` viết bằng TIẾNG ANH.** Tên biến/hàm/hằng tiếng Việt trong source là lỗi — nhiều plan liên tiếp đã để lọt vì người thực thi chép code trong plan nguyên văn.
- **Tên hàm test giữ quy ước chuyển tự tiếng Việt** (`test_khong_dich_khi_...`). Đây là quy ước có chủ đích của `backend/tests`. Comment/docstring trong test viết tiếng Việt như phần còn lại của repo.
- **MỌI lệnh pytest phải kèm `-m "not integration and not live"`.** Lệnh trần gọi API LLM thật và đã gây sự cố.
- **Mọi lệnh chạy từ `D:\Youdoo\backend`** (rootdir của pytest).
- **KHÔNG BAO GIỜ gắn tín hiệu sống-qua-lượt lên `AIMessage.additional_kwargs`** — nó không sống sót `_invoke_fresh`. Ngôn ngữ được suy lại từ `messages` mỗi lượt (Task 4), không gắn vào message.
- **Danh từ riêng KHÔNG dịch**: tên sản phẩm, đối tác, tài liệu giữ nguyên.
- Baseline trước khi bắt đầu: **1634 passed, 4 skipped, 48 deselected**.

## File Structure

| File | Trách nhiệm | Task |
|---|---|---|
| `backend/src/agents/language.py` | `detect_lang()` — tất định, không LLM | 1 |
| `backend/src/agents/prompts.py` | gỡ chỉ dẫn ghim cứng + `LANGUAGE_RULE` cho 4 prompt | 2 |
| `backend/src/agents/localize.py` | `extract_facts()`, `facts_survived()`, `localize()` | 3 |
| `backend/src/agents/erp_agent.py` | `_chat_inner()` + lớp bọc `chat()` gọi `localize` | 4 |
| `backend/evals/cases.py` | `LOCALIZE_CASES`, `LANGUAGE_CASES` | 5, 6 |
| `backend/evals/run_eval.py` | `eval_localize`, `eval_language`, `looks_vietnamese` | 5, 6 |
| `backend/jobs/eval_gate.py` | đăng ký hai bộ mới | 5, 6 |

---

## Task 1: `detect_lang`

Nhận diện ngôn ngữ **tất định, không LLM**. Chỉ tầng điều phối ghi (Task 3/4) cần nó — tầng prompt (Task 2) không cần, vì LLM tự nhìn tin nhắn.

**Files:**
- Create: `backend/src/agents/language.py`
- Test: `backend/tests/agents/test_language.py` (tạo mới)

⚠️ **LỆCH CÓ CHỦ ĐÍCH SO VỚI SPEC §5, đã ghi để người duyệt thấy.** Spec nói
lưu `lang` vào `ERPAgentState` vì "lượt trả lời xác nhận chỉ là 1/ok, quá ngắn
để nhận diện lại". Đúng vấn đề, nhưng có cách rẻ hơn: client thật (Open WebUI)
gửi **toàn bộ lịch sử** mỗi lượt, nên quét mọi tin nhắn người dùng trong
`messages` là đủ — không cần thêm trường state, không cần đọc checkpointer.
Thêm một trường mà không node nào đọc chính là lớp lỗi "khai báo không ai
dùng" repo này đã dính nhiều lần. Giới hạn còn lại (client script chỉ gửi một
tin nhắn) ghi rõ ở Task 4.

**Interfaces:**
- Produces: `detect_lang(text: str) -> str` trả `"vi"` hoặc `"en"`; hằng `VI`, `EN`.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_language.py`:

```python
# backend/tests/agents/test_language.py
"""Nhận diện ngôn ngữ — TẤT ĐỊNH, không LLM.

Chỉ dùng cho tầng điều phối ghi (chuỗi đi thẳng ra người dùng). Tầng prompt
KHÔNG dùng hàm này: LLM tự nhìn tin nhắn, đo được 2026-08-18.
"""
import pytest

from src.agents.language import EN, VI, detect_lang


@pytest.mark.parametrize("text", [
    "cho tôi xem chi tiết đơn mua P00003",
    "nhận hàng cho đơn mua P00003",
    "chào bạn",
])
def test_nhan_ra_tieng_viet(text):
    assert detect_lang(text) == VI


@pytest.mark.parametrize("text", [
    "show me the details of purchase order P00003",
    "which invoices are overdue?",
    "receive the goods for purchase order P00003",
])
def test_nhan_ra_tieng_anh(text):
    assert detect_lang(text) == EN


def test_cau_tieng_anh_co_ten_rieng_tieng_viet_thi_ve_vi():
    """FAIL AN TOÀN: có dấu tiếng Việt ⇒ vi, kể cả khi phần còn lại là tiếng
    Anh. Đoán nhầm sang `en` sẽ kéo câu xác nhận ghi qua một lượt dịch không
    cần thiết; đoán nhầm sang `vi` chỉ giữ nguyên hành vi hôm nay."""
    assert detect_lang("create a quotation for Cửa hàng ABC") == VI


@pytest.mark.parametrize("text", ["", "   ", "1", "ok", None])
def test_khong_du_tin_hieu_thi_ve_vi(text):
    """Lượt trả lời xác nhận thường chỉ là "1"/"ok" — quá ngắn để nhận diện.
    Rơi về vi là chiều an toàn; Task 4 quét TOÀN BỘ lịch sử người dùng nên
    lượt đó vẫn ra đúng ngôn ngữ khi client gửi đủ lịch sử."""
    assert detect_lang(text) == VI
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

```bash
python -m pytest tests/agents/test_language.py -m "not integration and not live" -q
```

Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'src.agents.language'`.

- [ ] **Step 3: Viết `language.py`**

```python
# backend/src/agents/language.py
"""Nhận diện ngôn ngữ người dùng — TẤT ĐỊNH, không gọi LLM.

Chỉ hai ngôn ngữ: "vi" và "en". Mọi thứ khác rơi về "vi".

VÌ SAO KHÔNG DÙNG LLM: đây là đường nóng (mỗi lượt chat) và câu trả lời có
thể suy ra từ chính ký tự. Ngân sách xác suất để dành cho việc thật sự cần
phán đoán. Cùng lý do lớp phủ quyết của routing.decide_route là tất định.

VÌ SAO FAIL VỀ "vi": đoán nhầm sang "en" kéo câu xác nhận ghi qua một lượt
dịch không cần thiết (tốn tiền + thêm một chỗ có thể sai); đoán nhầm sang
"vi" chỉ giữ nguyên đúng hành vi hôm nay.
"""
import re

VI = "vi"
EN = "en"

# Ký tự CHỈ tiếng Việt mới có (đủ dấu thanh + nguyên âm riêng). Chỉ cần MỘT
# ký tự trong nhóm này là chắc chắn tiếng Việt.
_VI_CHARS = re.compile(
    r"[ăâđêôơưĂÂĐÊÔƠƯáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩị"
    r"óòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]")

# Hư từ tiếng Anh — cần ít nhất một để dám kết luận "en". Không có nghĩa là
# tiếng Việt; nghĩa là KHÔNG ĐỦ TÍN HIỆU, và không đủ thì về "vi".
_EN_WORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "do", "does", "did",
    "show", "me", "my", "what", "which", "who", "when", "where", "how",
    "for", "of", "to", "in", "on", "and", "or", "with", "please", "can",
    "could", "would", "should", "list", "give", "create", "receive",
    "confirm", "order", "invoice", "customer", "supplier", "details",
})

_WORD = re.compile(r"[a-z]+")


def detect_lang(text) -> str:
    """"vi" | "en". Không bao giờ ném; đầu vào rỗng/None → "vi"."""
    s = (text or "").strip()
    if not s:
        return VI
    if _VI_CHARS.search(s):
        return VI
    words = set(_WORD.findall(s.lower()))
    return EN if words & _EN_WORDS else VI
```

- [ ] **Step 4: Chạy test, xác nhận XANH**

```bash
python -m pytest tests/agents/test_language.py -m "not integration and not live" -q
python -m pytest -m "not integration and not live" -q
```

Kỳ vọng: test mới xanh; toàn suite **1644 passed** (1634 + 10 test mới). Nếu số khác, GHI SỐ THẬT vào báo cáo, đừng sửa cho khớp.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/language.py backend/tests/agents/test_language.py
git commit -m "feat(i18n): detect_lang tat dinh, khong goi LLM"
```

---

## Task 2: Bốn prompt

⚠️ **ĐỌC SỐ ĐO TRƯỚC KHI SỬA.** Spike 2026-08-18 (spec §2) đã BÁC BỎ hai cách làm:
- Đổi câu *"trả lời bằng tiếng Việt"* thành *"reply in the same language"* → vẫn ra **toàn tiếng Việt**.
- Sửa thêm luật `display` → vẫn ra **toàn tiếng Việt**.

Cách DUY NHẤT đo được là hoạt động: **gỡ** chỉ dẫn ghim cứng ở đầu **và** **thêm** khối quy tắc ở **cuối**. Làm nửa vời hỏng đúng ở `mixed` — nơi ngữ cảnh nạp vào toàn tiếng Việt nên câu mở đầu thắng lại.

**Files:**
- Modify: `backend/src/agents/prompts.py`
- Test: `backend/tests/agents/test_prompt_language_rule.py` (tạo mới)

**Interfaces:**
- Produces: hằng `LANGUAGE_RULE: str`.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_prompt_language_rule.py`:

```python
# backend/tests/agents/test_prompt_language_rule.py
"""Bốn prompt sinh câu trả lời phải theo ngôn ngữ người dùng.

Đo 2026-08-18 qua HTTP thật: chỉ THÊM quy tắc ở cuối là KHÔNG đủ nếu prompt
còn ghim "trả lời bằng tiếng Việt" ở đầu — `mixed`/fuse hỏng vì ngữ cảnh nạp
vào (đoạn tài liệu + dữ liệu ERP, đều tiếng Việt) đủ nặng để câu mở đầu thắng
lại. Phải GỠ câu đầu VÀ THÊM khối cuối.
"""
import pytest

from src.agents import prompts

BON_PROMPT = ["SYSTEM_PROMPT", "CHITCHAT_PROMPT", "RAG_SYNTHESIS_PROMPT",
              "FUSE_PROMPT"]


@pytest.mark.parametrize("ten", BON_PROMPT)
def test_khong_con_ghim_cung_tieng_viet(ten):
    assert "trả lời bằng tiếng Việt" not in getattr(prompts, ten)


@pytest.mark.parametrize("ten", BON_PROMPT)
def test_co_khoi_language_rule(ten):
    assert prompts.LANGUAGE_RULE.strip() in getattr(prompts, ten)


@pytest.mark.parametrize("ten", BON_PROMPT)
def test_language_rule_nam_o_CUOI(ten):
    """Vị trí là thứ quyết định, không phải nội dung: spike đo được quy tắc
    đặt giữa prompt KHÔNG lật được ngôn ngữ đầu ra."""
    p = getattr(prompts, ten)
    con_lai = p[p.index(prompts.LANGUAGE_RULE.strip())
                + len(prompts.LANGUAGE_RULE.strip()):]
    assert len(con_lai.strip().replace("/no_think", "").strip()) == 0, (
        f"{ten}: còn {len(con_lai)} ký tự sau LANGUAGE_RULE")


def test_language_rule_dan_danh_tu_rieng_giu_nguyen():
    """Tên tài liệu/sản phẩm/đối tác KHÔNG được dịch — nếu dịch thì trích dẫn
    nguồn và mã sản phẩm mất khả năng tra ngược."""
    assert "Proper nouns" in prompts.LANGUAGE_RULE
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

```bash
python -m pytest tests/agents/test_prompt_language_rule.py -m "not integration and not live" -q
```

Kỳ vọng: FAIL — `AttributeError: module 'src.agents.prompts' has no attribute 'LANGUAGE_RULE'`.

- [ ] **Step 3: Thêm hằng `LANGUAGE_RULE`**

Thêm vào `backend/src/agents/prompts.py`, NGAY TRƯỚC `SYSTEM_PROMPT` (dòng ~6):

```python
# Đo 2026-08-18 qua HTTP thật (spec §2): chỉ đổi câu "trả lời bằng tiếng Việt"
# thành "reply in the same language" là KHÔNG ĐỦ — model vẫn trả lời tiếng
# Việt. Thủ phạm là VỊ TRÍ và ĐỘ DỨT KHOÁT, không phải nội dung câu đó. Khối
# này phải nằm ở CUỐI prompt và nói rõ nó đè lên mọi thứ phía trên.
LANGUAGE_RULE = """LANGUAGE RULE (overrides everything above): write your final answer in the SAME LANGUAGE as the user's latest message. If the user wrote in English, answer entirely in English — translate every label you took from tool output or documents; never copy Vietnamese wording through. Proper nouns (product, partner, document names) stay as-is."""
```

- [ ] **Step 4: Sửa bốn prompt**

Trong cùng file, với MỖI prompt trong `SYSTEM_PROMPT`, `CHITCHAT_PROMPT`, `RAG_SYNTHESIS_PROMPT`, `FUSE_PROMPT`:

1. **Gỡ** cụm `, trả lời bằng tiếng Việt` khỏi câu mở đầu (giữ nguyên phần còn lại của câu). Ví dụ `SYSTEM_PROMPT`: `Bạn là trợ lý ERP nội bộ, trả lời bằng tiếng Việt.` → `Bạn là trợ lý ERP nội bộ.`
2. Với ba prompt kết thúc bằng ` /no_think` (`SYSTEM_PROMPT`, `RAG_SYNTHESIS_PROMPT`, `FUSE_PROMPT`): chèn `\n\n{LANGUAGE_RULE}` NGAY TRƯỚC ` /no_think`.
3. `CHITCHAT_PROMPT` không có `/no_think`: nối `\n\n{LANGUAGE_RULE}` vào cuối.

Vì các prompt là chuỗi thường (không f-string, trừ `SYSTEM_PROMPT`), cách gọn nhất là ghép sau khi khai báo. Thêm ngay dưới khai báo `FUSE_PROMPT`:

```python
# Ghép LANGUAGE_RULE vào CUỐI cả bốn prompt sinh câu trả lời. Ghép ở đây thay
# vì nội suy trong từng chuỗi: ba prompt kết thúc bằng " /no_think" (tín hiệu
# tắt suy luận của model), nên quy tắc phải chèn TRƯỚC nó chứ không sau.
def _with_language_rule(prompt: str) -> str:
    marker = " /no_think"
    if prompt.endswith(marker):
        return prompt[:-len(marker)] + "\n\n" + LANGUAGE_RULE + marker
    return prompt + "\n\n" + LANGUAGE_RULE


SYSTEM_PROMPT = _with_language_rule(SYSTEM_PROMPT)
CHITCHAT_PROMPT = _with_language_rule(CHITCHAT_PROMPT)
RAG_SYNTHESIS_PROMPT = _with_language_rule(RAG_SYNTHESIS_PROMPT)
FUSE_PROMPT = _with_language_rule(FUSE_PROMPT)
```

⚠️ Đặt khối này SAU khai báo của cả bốn prompt. Nếu `RAG_SYNTHESIS_PROMPT` hoặc `FUSE_PROMPT` khai báo sau `SYSTEM_PROMPT` trong file, khối ghép phải nằm dưới cái cuối cùng — ĐỌC file thật để đặt đúng chỗ.

- [ ] **Step 5: Chạy test, xác nhận XANH**

```bash
python -m pytest tests/agents/test_prompt_language_rule.py -m "not integration and not live" -q
python -m pytest -m "not integration and not live" -q
```

Kỳ vọng: test mới xanh; toàn suite **1657 passed** (1644 + 13 test mới). Ghi số thật nếu khác.

⚠️ Một số test hiện có có thể khẳng định nội dung prompt (ví dụ test canh khối `intent` không đổi). Nếu có test đỏ, ĐỌC nó: nếu nó ghim đúng quyết định cũ thì sửa kèm lý do mới, KHÔNG nới lỏng assertion cho xanh.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/prompts.py backend/tests/agents/test_prompt_language_rule.py
git commit -m "feat(i18n): LANGUAGE_RULE o cuoi 4 prompt, go chi dan ghim cung"
```

---

## Task 3: `localize()` + lớp phủ quyết tất định

Chuỗi điều phối ghi **chính là** câu trả lời — không LLM nào đứng giữa, nên Task 2 không chạm tới được. Chủ dự án quyết: **cho LLM dịch**. Rủi ro đã nêu và đã chấp nhận: dịch sai số/mã chứng từ ⇒ người dùng duyệt nhầm một thao tác ghi THẬT. Lớp phủ quyết dưới đây chặn đúng rủi ro đó.

**Files:**
- Create: `backend/src/agents/localize.py`
- Test: `backend/tests/agents/test_localize.py` (tạo mới)

**Interfaces:**
- Consumes: `detect_lang` (Task 1) — chỉ để hiểu ngữ cảnh, không gọi trực tiếp.
- Produces: `extract_facts(text) -> set[str]`; `facts_survived(src, out) -> bool`; `async localize(text, lang, llm) -> str`; hằng `TRANSLATE_PROMPT`.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_localize.py`:

```python
# backend/tests/agents/test_localize.py
"""Dịch chuỗi điều phối ghi, có lớp phủ quyết tất định.

Model được phép đổi CÂU CHỮ, không được phép đổi SỰ VIỆC. Đây là đường an
toàn: người dùng đọc câu này rồi duyệt một thao tác ghi THẬT.
"""
import pytest

from src.agents.localize import extract_facts, facts_survived, localize

GOC = ('Mình sẽ thực hiện thao tác sau giúp bạn:\n\n'
       '**Nhận hàng cho đơn mua P00003**\n(receive_order: order_ref=P00003)\n'
       'Tổng: 255\n'
       'Bạn xác nhận giúp mình nhé? (trả lời "có" để thực hiện, "không" để hủy)')


def test_trich_duoc_so_va_ma_chung_tu():
    facts = extract_facts(GOC)
    assert "P00003" in facts
    assert "255" in facts


def test_trich_duoc_ma_phieu_kho_co_gach_cheo():
    assert "WH/OUT/00001" in extract_facts("Xác nhận phiếu WH/OUT/00001?")


def test_ban_dich_giu_du_su_viec_thi_qua():
    dich = ('I will perform the following action:\n\n**Receive goods for '
            'purchase order P00003**\n(receive_order: order_ref=P00003)\n'
            'Total: 255\nDo you confirm? (reply "yes" to proceed, "no" to cancel)')
    assert facts_survived(GOC, dich) is True


def test_doi_MOT_chu_so_thi_truot():
    """Đây là ca đắt nhất nếu lọt: người dùng duyệt một con số khác."""
    assert facts_survived(GOC, GOC.replace("255", "265")) is False


def test_lam_mat_ma_don_thi_truot():
    assert facts_survived(GOC, GOC.replace("P00003", "the order")) is False


@pytest.mark.asyncio
async def test_lang_vi_thi_tra_nguyen_van_khong_goi_llm():
    """Hành vi hôm nay phải BYTE-IDENTICAL và chi phí bằng 0."""
    class LLMKhongDuocGoi:
        async def ainvoke(self, *a, **k):
            raise AssertionError("lang=vi không được gọi LLM")
    assert await localize(GOC, "vi", LLMKhongDuocGoi()) == GOC


@pytest.mark.asyncio
async def test_van_ban_khong_co_dau_tieng_viet_thi_khong_dich():
    """Câu trả lời do LLM sinh sẵn bằng tiếng Anh không được đem đi dịch lại."""
    class LLMKhongDuocGoi:
        async def ainvoke(self, *a, **k):
            raise AssertionError("không có dấu tiếng Việt thì không dịch")
    anh = "Order P00003 has been received."
    assert await localize(anh, "en", LLMKhongDuocGoi()) == anh


@pytest.mark.asyncio
async def test_dich_dat_thi_tra_ban_dich():
    class LLMGia:
        async def ainvoke(self, messages):
            class R:
                content = ('I will perform the following action: Receive goods '
                           'for purchase order P00003 (receive_order: '
                           'order_ref=P00003) Total: 255 Do you confirm?')
            return R()
    out = await localize(GOC, "en", LLMGia())
    assert "purchase order P00003" in out
    assert "Mình sẽ thực hiện" not in out


@pytest.mark.asyncio
async def test_dich_lam_sai_so_thi_ROI_VE_BAN_GOC():
    """Lớp phủ quyết: sai sự việc thì thà giữ tiếng Việt còn hơn cho duyệt
    nhầm."""
    class LLMBia:
        async def ainvoke(self, messages):
            class R:
                content = "I will receive purchase order P99999. Total: 999."
            return R()
    assert await localize(GOC, "en", LLMBia()) == GOC


@pytest.mark.asyncio
async def test_llm_nem_thi_ROI_VE_BAN_GOC():
    """Bất biến: một lượt chat không bao giờ vỡ vì lớp dịch."""
    class LLMHong:
        async def ainvoke(self, messages):
            raise RuntimeError("provider hỏng")
    assert await localize(GOC, "en", LLMHong()) == GOC


@pytest.mark.asyncio
async def test_llm_tra_rong_thi_ROI_VE_BAN_GOC():
    class LLMRong:
        async def ainvoke(self, messages):
            class R:
                content = "   "
            return R()
    assert await localize(GOC, "en", LLMRong()) == GOC
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

```bash
python -m pytest tests/agents/test_localize.py -m "not integration and not live" -q
```

Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'src.agents.localize'`.

- [ ] **Step 3: Viết `localize.py`**

```python
# backend/src/agents/localize.py
"""Dịch chuỗi ĐIỀU PHỐI sang ngôn ngữ người dùng, có lớp phủ quyết tất định.

VÌ SAO CẦN: chuỗi ở tầng điều phối ghi (create_order._msg, question của
interrupt, thông báo lỗi) đi THẲNG ra người dùng — không LLM nào đứng giữa để
viết lại, nên khối LANGUAGE_RULE ở prompt không chạm tới được. Đo 2026-08-18
qua HTTP thật: hỏi tiếng Anh vẫn nhận câu xác nhận ghi bằng tiếng Việt.

VÌ SAO CÓ LỚP PHỦ QUYẾT: người dùng đọc chính câu này rồi DUYỆT một thao tác
ghi thật. Một bản dịch đổi "255" thành "265" hay đánh rơi mã đơn là đổi thứ
người ta đang duyệt. Model được phép đổi CÂU CHỮ, không được phép đổi SỰ VIỆC
— cùng khuôn "lớp xác suất + lớp phủ quyết tất định" của routing.decide_route
và erp_grounding.verify_erp_grounding.

Không bao giờ ném: mọi lỗi → bản gốc tiếng Việt.
"""
import re

# Ký tự chỉ tiếng Việt mới có — dùng để bỏ qua văn bản đã là tiếng Anh.
_VI_CHARS = re.compile(
    r"[ăâđêôơưĂÂĐÊÔƠƯáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩị"
    r"óòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]")

# SỰ VIỆC không được phép đổi:
#   - mã chứng từ có gạch chéo: WH/OUT/00001, INV/2026/00004
#   - mã dạng chữ+số: P00003, S00012, E-COM07
#   - mọi cụm chữ số: 255, 25.5, 10.0
# Cố ý RỘNG: thà bắt nhầm một token vô hại (bản dịch giữ nguyên nó thì vẫn
# qua) còn hơn bỏ sót một con số người dùng sắp duyệt.
_FACT = re.compile(r"[A-Z]{2,}/[A-Z0-9/]+|[A-Za-z]+-?\d[\w/-]*|\d[\d.,]*")

TRANSLATE_PROMPT = (
    "Translate the message below into {target}. Keep EVERY number, amount, "
    "reference code and tool name EXACTLY as they appear — do not reformat, "
    "round, or re-order them. Keep proper nouns (product, partner, document "
    "names) unchanged. Keep the line structure. Reply with the translation "
    "only, no preamble.\n\n{text}")

_TARGET = {"en": "English", "vi": "Vietnamese"}


def extract_facts(text: str) -> set[str]:
    """Các token KHÔNG được phép đổi trong bản dịch."""
    return set(_FACT.findall(text or ""))


def facts_survived(src: str, out: str) -> bool:
    """Mọi sự việc của bản gốc còn nguyên trong bản dịch?

    Chỉ kiểm CHIỀU MẤT/ĐỔI. Bản dịch thêm token mới (ví dụ "1." của danh sách)
    là vô hại và không bị chặn — chặn cả chiều đó sẽ làm cổng bắn giả liên tục
    và người ta sẽ tắt nó.
    """
    if not (out or "").strip():
        return False
    return extract_facts(src) <= extract_facts(out)


async def localize(text: str, lang: str, llm) -> str:
    """Bản dịch nếu ĐẠT lớp phủ quyết, ngược lại bản gốc. Không bao giờ ném."""
    if not text or lang not in _TARGET or lang == "vi":
        return text
    if not _VI_CHARS.search(text):
        return text          # đã là tiếng Anh — không dịch lại
    try:
        from langchain_core.messages import HumanMessage
        prompt = TRANSLATE_PROMPT.format(target=_TARGET[lang], text=text)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        out = (getattr(response, "content", "") or "").strip()
    except Exception:                                       # noqa: BLE001
        return text
    return out if facts_survived(text, out) else text
```

- [ ] **Step 4: Chạy test, xác nhận XANH**

```bash
python -m pytest tests/agents/test_localize.py -m "not integration and not live" -q
python -m pytest -m "not integration and not live" -q
```

Kỳ vọng: test mới xanh; toàn suite **1668 passed** (1657 + 11 test mới). Ghi số thật nếu khác.

- [ ] **Step 5: Phá thử — chứng minh lớp phủ quyết có sức nặng**

Sửa tạm `facts_survived` thành `return True` (bỏ lớp phủ quyết), chạy:

```bash
python -m pytest tests/agents/test_localize.py::test_dich_lam_sai_so_thi_ROI_VE_BAN_GOC -m "not integration and not live" -q
```

Kỳ vọng: **ĐỎ**. Hoàn nguyên rồi chạy lại, kỳ vọng XANH. Nếu nó vẫn xanh khi đã bỏ lớp phủ quyết thì bài test không đo gì — sửa test trước khi đi tiếp.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/localize.py backend/tests/agents/test_localize.py
git commit -m "feat(i18n): localize() + lop phu quyet tat dinh giu nguyen su viec"
```

---

## Task 4: Đấu vào `ERPAgent.chat()`

**Files:**
- Modify: `backend/src/agents/erp_agent.py`
- Test: `backend/tests/agents/test_chat_localize.py` (tạo mới)

**Interfaces:**
- Consumes: `detect_lang` (Task 1), `localize` (Task 3).

⚠️ `chat()` hiện có **SÁU** chỗ `return` (đếm trong mã, không ước lượng): câu nhắc nhập, câu từ chối vai, câu hỏi-lại của `_decide_resume`, `RECURSION_MSG`, `question` của interrupt, và nội dung message cuối. Vá từng chỗ là để sót. Đổi thân hàm thành `_chat_inner()` và để `chat()` chỉ còn là lớp bọc.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/agents/test_chat_localize.py`:

```python
# backend/tests/agents/test_chat_localize.py
"""chat() bọc MỌI đường ra qua localize.

Vá từng `return` là để sót — chat() có SÁU chỗ trả về, và những đường thêm
sau này sẽ không ai nhớ vá. Lớp bọc phủ hết.
"""
import pytest

from src.agents import erp_agent as agent_mod


class _AgentGia(agent_mod.ERPAgent):
    """Chỉ thay _chat_inner: phần còn lại của chat() (lớp bọc) là thứ đang đo."""
    def __init__(self, tra_ve):
        self._tra_ve = tra_ve
        self._llms = {"evaluator": None}
        self._localize_calls = []

    async def _chat_inner(self, messages, thread_id=None, reset_if_fresh=False,
                          role="admin"):
        return self._tra_ve


@pytest.mark.asyncio
async def test_hoi_tieng_viet_thi_khong_dich(monkeypatch):
    goi = []

    async def gia_localize(text, lang, llm):
        goi.append(lang)
        return text
    monkeypatch.setattr(agent_mod, "localize", gia_localize)

    a = _AgentGia("Bạn xác nhận giúp mình nhé?")
    out = await a.chat([{"role": "user", "content": "nhận hàng cho đơn P00003"}])
    assert out == "Bạn xác nhận giúp mình nhé?"
    assert goi == ["vi"]


@pytest.mark.asyncio
async def test_hoi_tieng_anh_thi_di_qua_localize(monkeypatch):
    async def gia_localize(text, lang, llm):
        return "TRANSLATED" if lang == "en" else text
    monkeypatch.setattr(agent_mod, "localize", gia_localize)

    a = _AgentGia("Bạn xác nhận giúp mình nhé?")
    out = await a.chat([{"role": "user",
                         "content": "receive the goods for order P00003"}])
    assert out == "TRANSLATED"


@pytest.mark.asyncio
async def test_luot_tra_loi_ngan_van_giu_ngon_ngu_cua_luot_dau(monkeypatch):
    """Lượt xác nhận chỉ là "yes" — quá ngắn để nhận diện. Client thật gửi đủ
    lịch sử, nên câu hỏi tiếng Anh mở đầu vẫn quyết đúng ngôn ngữ. Đây là ca
    làm cho luồng GHI bằng tiếng Anh không bị đứt giữa chừng."""
    async def gia_localize(text, lang, llm):
        return "TRANSLATED" if lang == "en" else text
    monkeypatch.setattr(agent_mod, "localize", gia_localize)

    a = _AgentGia("Đã nhận hàng cho đơn P00003.")
    out = await a.chat([
        {"role": "user", "content": "receive the goods for order P00003"},
        {"role": "assistant", "content": "Bạn xác nhận giúp mình nhé?"},
        {"role": "user", "content": "yes"},
    ])
    assert out == "TRANSLATED"


@pytest.mark.asyncio
async def test_localize_nem_thi_van_tra_duoc_cau_goc(monkeypatch):
    """Bất biến: một lượt chat không bao giờ vỡ vì lớp dịch."""
    async def gia_localize(text, lang, llm):
        raise RuntimeError("hỏng")
    monkeypatch.setattr(agent_mod, "localize", gia_localize)

    a = _AgentGia("Bạn xác nhận giúp mình nhé?")
    out = await a.chat([{"role": "user", "content": "receive order P00003"}])
    assert out == "Bạn xác nhận giúp mình nhé?"
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

```bash
python -m pytest tests/agents/test_chat_localize.py -m "not integration and not live" -q
```

Kỳ vọng: FAIL — `AttributeError: 'ERPAgent' object has no attribute '_chat_inner'`.

- [ ] **Step 3: Đổi thân `chat()` thành `_chat_inner()` và thêm lớp bọc**

Trong `backend/src/agents/erp_agent.py`:

1. Thêm import ở đầu file, cạnh các import `.` khác:

```python
from .language import EN, VI, detect_lang
from .localize import localize
```

2. **Đổi tên** `async def chat(` hiện tại thành `async def _chat_inner(` — giữ NGUYÊN toàn bộ thân hàm và docstring.

3. Thêm hàm `chat()` mới NGAY TRƯỚC `_chat_inner`:

```python
    async def chat(self, messages: list[dict], thread_id: str | None = None,
                   reset_if_fresh: bool = False, role: str = "admin") -> str:
        """Lớp bọc: chạy lượt chat rồi đưa câu trả lời qua localize.

        Bọc thay vì vá từng `return`: _chat_inner có SÁU đường ra (câu nhắc
        nhập, từ chối vai, hỏi-lại, RECURSION_MSG, question của interrupt,
        message cuối) và những đường thêm sau này sẽ không ai nhớ vá.

        `lang` suy từ TOÀN BỘ tin nhắn người dùng trong lượt này, không chỉ tin
        nhắn mới nhất: lượt trả lời xác nhận thường chỉ là "yes"/"1" — quá ngắn
        để nhận diện. Client thật (Open WebUI) gửi đủ lịch sử mỗi lượt, nên câu
        hỏi tiếng Anh mở đầu vẫn nằm trong `messages` và quyết đúng ngôn ngữ.

        Chỉ cần MỘT tin nhắn tiếng Anh là cả lượt tính là "en": detect_lang đã
        fail an toàn về "vi" (đòi có hư từ tiếng Anh VÀ không có dấu tiếng
        Việt), nên một chữ lạc không đủ kích hoạt.

        GIỚI HẠN CÒN LẠI, có ghi: client script chỉ gửi đúng một tin nhắn mỗi
        lượt (kiểu `{"session_id": ..., "messages": [{"role": "user",
        "content": "yes"}]}`) sẽ mất ngôn ngữ ở lượt xác nhận → rơi về "vi".
        Đó là chiều an toàn (giữ đúng hành vi hôm nay), không phải lỗi.

        KHÔNG BAO GIỜ để lớp dịch làm hỏng một lượt chat: mọi lỗi → câu gốc.
        """
        answer = await self._chat_inner(messages, thread_id=thread_id,
                                        reset_if_fresh=reset_if_fresh,
                                        role=role)
        lang = VI
        for m in messages or []:
            if m.get("role") == "user" and detect_lang(m.get("content")) == EN:
                lang = EN
                break
        try:
            return await localize(answer, lang, self._llms["evaluator"])
        except Exception:                                   # noqa: BLE001
            return answer
```

⚠️ Vai `evaluator` được chọn có chủ đích: nó đã được dùng cho `_decide_resume` (phân loại nhẹ), chuỗi của nó (`gemma-4-26b` → `groq-gpt-oss-20b`) KHÔNG chung ví với `gemini-3.1-flash-lite` đang gánh `router`/`fusion`/`synthesis` — nên lớp dịch không ăn vào hạn mức của đường định tuyến.

- [ ] **Step 4: Chạy test, xác nhận XANH**

```bash
python -m pytest tests/agents/test_chat_localize.py -m "not integration and not live" -q
python -m pytest -m "not integration and not live" -q
```

Kỳ vọng: test mới xanh; toàn suite **1672 passed** (1668 + 4 test mới). Ghi số thật nếu khác.

⚠️ Test hiện có gọi `agent.chat(...)` với LLM giả có thể đỏ vì lớp bọc gọi thêm `self._llms["evaluator"]`. Nếu đỏ: ĐỌC test, và nhớ `localize` trả nguyên văn khi `lang == "vi"` (không chạm LLM) — phần lớn test tiếng Việt sẽ không bị ảnh hưởng.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/erp_agent.py backend/tests/agents/test_chat_localize.py
git commit -m "feat(i18n): chat() boc moi duong ra qua localize"
```

---

## Task 5: Bộ eval `localize`

**Files:**
- Modify: `backend/evals/cases.py`, `backend/evals/run_eval.py`, `backend/jobs/eval_gate.py`
- Test: `backend/tests/jobs/test_eval_localize.py` (tạo mới)

**Interfaces:**
- Consumes: `localize`, `facts_survived` (Task 3).
- Produces: `LOCALIZE_CASES: list[tuple[str, str]]`; `eval_localize` trả `{"set","n","acc","fact_loss","lat_p50","lat_p95","fails","errors"}`.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/jobs/test_eval_localize.py`:

```python
# backend/tests/jobs/test_eval_localize.py
"""Bộ ca dịch phải phủ đúng thứ đắt nhất: SỰ VIỆC trong câu xác nhận ghi."""
import re

from evals.cases import LOCALIZE_CASES


def test_moi_ca_la_cap_va_deu_co_dau_tieng_viet():
    vi = re.compile(r"[ăâđêôơưáàảãạéèẻẽẹíìỉĩịóòỏõọúùủũụýỳỷỹỵ]")
    for goc, _lang in LOCALIZE_CASES:
        assert vi.search(goc), goc


def test_moi_ca_deu_mang_it_nhat_mot_su_viec():
    """Ca không có số/mã nào thì lớp phủ quyết không đo được gì."""
    from src.agents.localize import extract_facts
    for goc, _lang in LOCALIZE_CASES:
        assert extract_facts(goc), goc


def test_co_ca_cau_xac_nhan_ghi():
    assert any("xác nhận" in g for g, _ in LOCALIZE_CASES)


def test_du_so_ca():
    assert len(LOCALIZE_CASES) >= 6
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

```bash
python -m pytest tests/jobs/test_eval_localize.py -m "not integration and not live" -q
```

Kỳ vọng: FAIL — `ImportError: cannot import name 'LOCALIZE_CASES'`.

- [ ] **Step 3: Thêm `LOCALIZE_CASES`**

Thêm vào cuối `backend/evals/cases.py`:

```python
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
    ('Quy trình nhập kho này yêu cầu có đơn mua (PO).', "en"),
]
```

- [ ] **Step 4: Thêm `eval_localize`**

Thêm vào `backend/evals/run_eval.py`, ngay sau `eval_sop_select`:

```python
async def eval_localize(llm, pace: float = 0.0, checkpoint_path=None):
    """Đo lớp dịch chuỗi điều phối: BẢN DỊCH GIỮ ĐỦ SỰ VIỆC hay không.

    `acc` = tỉ lệ ca trả về BẢN DỊCH (tức đã qua lớp phủ quyết).
    `fact_loss` = số ca lớp phủ quyết phải chặn (bản dịch làm mất/đổi sự
    việc). fact_loss > 0 KHÔNG phải lỗi hệ thống — đó là cổng làm đúng việc;
    nhưng nó đo được model dịch tệ tới đâu, nên phải nổi lên trong báo cáo.
    """
    from src.agents.localize import facts_survived, localize
    lat: list[float] = []

    async def call(case):
        text, lang = case
        out, ms = await _timed(localize(text, lang, llm))
        lat.append(ms)
        if out != text:
            return None                    # đã dịch và qua lớp phủ quyết
        return {"text": text[:80], "lang": lang,
                "reason": "roi_ve_ban_goc"}

    fails, errors = await run_resilient(LOCALIZE_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(LOCALIZE_CASES)
    p50, p95 = _percentiles(lat)
    return {"set": "localize", "n": n,
            "acc": (n - len(fails) - len(errors)) / n if n else 0.0,
            "fact_loss": len(fails),
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}
```

Thêm `LOCALIZE_CASES` vào khối import từ `evals.cases` ở đầu file (ĐỌC dòng import thật rồi thêm vào, đừng đoán thứ tự).

- [ ] **Step 5: Đăng ký vào `eval_gate.py`**

Trong `backend/jobs/eval_gate.py`:

```python
# EVAL_FN
           "localize": run_eval.eval_localize,
# ROLE_FOR_SET
                "localize": "evaluator",
```

Và trong `_gate`, thêm TRƯỚC nhánh `intent`:

```python
    if set_name == "localize":
        # GÁC NHẸ ở đợt đầu, cùng lý do gather/multi_source_gather: chưa có số
        # đo nào để biết ngưỡng hợp lý. Số vào báo cáo để người đọc tự đánh
        # giá. Siết thành ngưỡng thật khi đủ số đo.
        return True
```

`localize` CỐ Ý không vào `--set all` ở đợt này (gate trả True vô điều kiện → để trong "all" chỉ tạo PASS giả):

```python
        sets = [s for s in EVAL_FN
                if s not in ("gather", "multi_source_gather", "localize")]
```

- [ ] **Step 6: Chạy test, xác nhận XANH**

```bash
python -m pytest tests/jobs/test_eval_localize.py -m "not integration and not live" -q
python -m pytest -m "not integration and not live" -q
```

Kỳ vọng: test mới xanh; toàn suite **1676 passed** (1672 + 4 test mới). Ghi số thật nếu khác.

⚠️ `tests/jobs/test_eval_gate.py::test_set_all_runs_every_registered_set_except_gather_pair` khẳng định tập "all" bằng `set(EVAL_FN) - {...}` — thêm `localize` vào EVAL_FN sẽ làm nó đỏ. Sửa cả assertion lẫn TÊN test cho khớp thực tế mới, kèm lý do.

- [ ] **Step 7: Commit**

```bash
git add backend/evals/cases.py backend/evals/run_eval.py backend/jobs/eval_gate.py backend/tests/jobs/test_eval_localize.py backend/tests/jobs/test_eval_gate.py
git commit -m "feat(evals): bo localize do su viec song sot qua ban dich"
```

---

## Task 6: Bộ smoke song ngữ (spec §6)

Bảy kịch bản sống của Task 7 chỉ đúng MỘT LẦN. Bộ này chạy lại được, và nó là
thứ duy nhất bắt được việc ai đó sau này sửa prompt làm mất tiếng Anh.

⚠️ Bộ dò phải **phân biệt NHÃN với DANH TỪ RIÊNG** (spec §2.4). Spike
2026-08-18 đã báo động giả vì đếm tên tài liệu tiếng Việt trong phần trích dẫn
nguồn là "lọt tiếng Việt" — tên tài liệu/sản phẩm/đối tác giữ nguyên mới ĐÚNG.

**Files:**
- Modify: `backend/evals/cases.py`, `backend/evals/run_eval.py`, `backend/jobs/eval_gate.py`
- Test: `backend/tests/jobs/test_eval_language.py` (tạo mới)

**Interfaces:**
- Consumes: `LANGUAGE_RULE` (Task 2).
- Produces: `LANGUAGE_CASES: list[tuple[str, str, str]]` — `(prompt_name, câu hỏi, ngôn ngữ kỳ vọng)`; `looks_vietnamese(text) -> bool`; `eval_language`.

- [ ] **Step 1: Viết test thất bại**

Tạo `backend/tests/jobs/test_eval_language.py`:

```python
# backend/tests/jobs/test_eval_language.py
"""Bộ dò ngôn ngữ đầu ra phải phân biệt NHÃN với DANH TỪ RIÊNG.

Spike 2026-08-18 báo động giả vì đếm tên tài liệu tiếng Việt ở phần trích dẫn
nguồn là lỗi. Tên riêng giữ nguyên mới đúng — dịch chúng thì mất khả năng tra
ngược tài liệu/sản phẩm.
"""
from evals.cases import LANGUAGE_CASES
from evals.run_eval import looks_vietnamese


def test_cau_tieng_anh_thuan_thi_khong_bi_bao_dong():
    assert looks_vietnamese("Order P00003 from Azure Interior. Status: Draft.") is False


def test_cau_tieng_anh_kem_TEN_RIENG_tieng_viet_thi_khong_bi_bao_dong():
    """Đây đúng ca spike đếm nhầm."""
    assert looks_vietnamese(
        "The receipt procedure has 4 steps.

Sources:
"
        "- Quy trình nhập kho › Bước 1 (sop.docx)") is False


def test_cau_tieng_viet_that_thi_bi_bao_dong():
    assert looks_vietnamese(
        "Chi tiết đơn mua P00003 từ nhà cung cấp Azure Interior.") is True


def test_moi_prompt_deu_co_ca_hai_ngon_ngu():
    for ten in ("CHITCHAT_PROMPT", "RAG_SYNTHESIS_PROMPT", "FUSE_PROMPT"):
        langs = {lang for p, _q, lang in LANGUAGE_CASES if p == ten}
        assert langs == {"vi", "en"}, ten
```

- [ ] **Step 2: Chạy test, xác nhận ĐỎ**

```bash
python -m pytest tests/jobs/test_eval_language.py -m "not integration and not live" -q
```

Kỳ vọng: FAIL — `ImportError: cannot import name 'LANGUAGE_CASES'`.

- [ ] **Step 3: Thêm `LANGUAGE_CASES`**

Thêm vào cuối `backend/evals/cases.py`:

```python
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
```

- [ ] **Step 4: Thêm `looks_vietnamese` + `eval_language`**

Thêm vào `backend/evals/run_eval.py`, ngay sau `eval_localize`:

```python
# Hư từ tiếng Việt. CỐ Ý không dùng dấu thanh: tên tài liệu/sản phẩm/đối tác
# tiếng Việt được phép (và phải) giữ nguyên trong câu trả lời tiếng Anh — đếm
# dấu thanh làm bộ dò báo động giả trên chính phần trích dẫn nguồn (đo được ở
# spike 2026-08-18).
_VI_FUNCTION_WORDS = re.compile(
    r"(của|và|là|cho|không|được|với|các|những|này|tôi|bạn|mình|hãy|"
    r"nếu|theo|khi|đã|sẽ|có thể|vui lòng)", re.IGNORECASE)


def looks_vietnamese(text: str) -> bool:
    """Câu trả lời được VIẾT bằng tiếng Việt?

    Chấm trên HƯ TỪ chứ không trên dấu thanh: một câu tiếng Anh trích tên tài
    liệu "Quy trình nhập kho" là ĐÚNG, không phải lỗi.
    """
    return bool(_VI_FUNCTION_WORDS.search(text or ""))


async def eval_language(llm, pace: float = 0.0, checkpoint_path=None):
    """Câu trả lời có theo ngôn ngữ người dùng không — đo tầng PROMPT.

    Gọi thẳng từng prompt với một câu hỏi, không dựng graph: thứ đang đo là
    khối LANGUAGE_RULE, không phải định tuyến.
    """
    from src.agents import prompts as prompts_mod
    lat: list[float] = []

    async def call(case):
        prompt_name, question, want = case
        system = getattr(prompts_mod, prompt_name)
        resp, ms = await _timed(llm.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=question)]))
        lat.append(ms)
        body = (resp.content or "").strip()
        got = "vi" if looks_vietnamese(body) else "en"
        if got == want:
            return None
        return {"prompt": prompt_name, "question": question,
                "want": want, "got": got, "body": body[:160]}

    fails, errors = await run_resilient(LANGUAGE_CASES, call, pace=pace,
                                        checkpoint_path=checkpoint_path)
    n = len(LANGUAGE_CASES)
    p50, p95 = _percentiles(lat)
    return {"set": "language", "n": n,
            "acc": (n - len(fails) - len(errors)) / n if n else 0.0,
            "lat_p50": p50, "lat_p95": p95,
            "fails": fails, "errors": errors}
```

Thêm `LANGUAGE_CASES` vào khối import từ `evals.cases` (ĐỌC dòng import thật rồi thêm).

- [ ] **Step 5: Đăng ký vào `eval_gate.py`**

```python
# EVAL_FN
           "language": run_eval.eval_language,
# ROLE_FOR_SET
                "language": "chitchat",
```

Trong `_gate`, thêm cạnh nhánh `localize`:

```python
    if set_name == "language":
        # Gate TUYỆT ĐỐI: đây là thuộc tính nhị phân (đúng ngôn ngữ hay không),
        # không phải phép đo chất lượng tương đối. Trả lời sai ngôn ngữ là hỏng
        # hẳn với người dùng đó, không phải "kém hơn hôm qua".
        return result["acc"] == 1.0
```

Và loại khỏi `--set all` ở đợt đầu, cùng lý do `localize`:

```python
        sets = [s for s in EVAL_FN
                if s not in ("gather", "multi_source_gather", "localize",
                             "language")]
```

- [ ] **Step 6: Chạy test, xác nhận XANH**

```bash
python -m pytest tests/jobs/test_eval_language.py -m "not integration and not live" -q
python -m pytest -m "not integration and not live" -q
```

Kỳ vọng: test mới xanh; toàn suite **1680 passed** (1676 + 4 test mới). Ghi số thật nếu khác.

⚠️ `test_set_all_runs_every_registered_set_except_gather_pair` lại đỏ (tập loại trừ đổi lần nữa). Sửa assertion + TÊN test cho khớp, kèm lý do.

- [ ] **Step 7: Commit**

```bash
git add backend/evals/cases.py backend/evals/run_eval.py backend/jobs/eval_gate.py backend/tests/jobs/test_eval_language.py backend/tests/jobs/test_eval_gate.py
git commit -m "feat(evals): bo language do ngon ngu dau ra, do phan biet ten rieng"
```

---

## Task 7: Đo thật và nghiệm thu sống

Không viết code sản phẩm. Nhiệm vụ: chứng minh đợt này đạt, hoặc nói rõ nó không đạt ở đâu.

**Files:**
- Create: `docs/superpowers/plans/2026-08-18-multilingual-vi-en-report.md`

- [ ] **Step 1: Chạy 4 cổng có thể thụt**

Task 2 sửa đúng 4 prompt mà các cổng này đo. Tạo runner tạm **NGOÀI repo** (Task 7 của một plan trước đã để nó trong repo rồi phải nhớ xoá):

```python
# C:\Users\ADMIN\AppData\Local\Temp\...\run_eval_env.py — tệp tạm, KHÔNG commit
import asyncio, sys
from dotenv import load_dotenv
load_dotenv(r"D:\Youdoo\.env")
sys.path.insert(0, r"D:\Youdoo\backend")   # trỏ đúng checkout ĐANG LÀM VIỆC
from evals.run_eval import main
asyncio.run(main(sys.argv[1:]))
```

Đặt biến `TMP_RUNNER` trỏ tới đường dẫn tuyệt đối của tệp trên, rồi chạy
từng cổng và ghi nguyên văn JSON vào báo cáo:

```bash
python "%TMP_RUNNER%" --set read --model gemini-3.5-flash-lite --pace 4.8 --baseline evals/baseline-qwen3-8b-read.json
python "%TMP_RUNNER%" --set planner --model gemini-3.5-flash-lite --pace 4.8 --baseline evals/baseline-qwen3-8b-planner.json
python "%TMP_RUNNER%" --set synthesis --model gemini-3.1-flash-lite --pace 4.8 --baseline evals/baseline-qwen3-8b-synthesis.json
python "%TMP_RUNNER%" --set multi_source --model gemini-3.1-flash-lite --pace 4.8 --baseline evals/baseline-qwen3-8b-multi_source.json
```

⚠️ **Kiểm hạn mức TRƯỚC khi chạy.** Sổ dùng cửa sổ TRƯỢT 24h nên có thể chặn dù nhà cung cấp đã reset. `gemini-3.1-flash-lite` (router/fusion/synthesis) hay cạn trước; `gemini-3.5-flash-lite` (read/planner) thường còn nhiều. Cách đo và cách chạy khi cạn: xem ghi chú "nghiệm thu sống khi sổ ngân sách báo cạn".

Kỳ vọng: **cả 4 GATE PASS**. Thụt cái nào thì DỪNG, ghi rõ ca nào và vì sao — KHÔNG nới baseline.

- [ ] **Step 2: Chạy bộ `language` (tầng prompt)**

```bash
python "%TMP_RUNNER%" --set language --model gemini-3.5-flash --pace 4.8
```

Kỳ vọng: `acc = 1.000` — đây là thuộc tính nhị phân, sai ngôn ngữ là hỏng hẳn
với người dùng đó. Trượt ca nào thì ghi rõ prompt nào, câu nào, và nguyên văn
`body` đo được.

- [ ] **Step 3: Chạy bộ `localize` (tầng điều phối)**

```bash
python "%TMP_RUNNER%" --set localize --model gemma-4-26b --pace 2.4
```

Ghi `acc`, `fact_loss`, và nguyên văn `fails`. `fact_loss > 0` không phải lỗi — đó là lớp phủ quyết làm việc; nhưng nếu **quá nửa số ca** rơi về bản gốc thì bản dịch vô dụng trên thực tế: ghi thẳng vào báo cáo và đề nghị xem lại quyết định "cho LLM dịch" (spec §7).

- [ ] **Step 4: Nghiệm thu sống QUA HTTP THẬT**

⚠️ Bắt buộc đi qua entry point HTTP. Khởi động bằng `start-dev.ps1`.

| # | câu | kỳ vọng |
|---|---|---|
| 1 | `show me the details of purchase order P00003` | trả lời **tiếng Anh**, nhãn được dịch |
| 2 | `cho tôi xem chi tiết đơn mua P00003` | trả lời **tiếng Việt** (không hồi quy) |
| 3 | `what is the company return policy?` | **tiếng Anh**; tên tài liệu ở phần nguồn GIỮ nguyên tiếng Việt |
| 4 | `does order S00165 meet the delivery SLA?` | **tiếng Anh** — đây là đường `mixed` đã hỏng ở spike, phải xanh |
| 5 | `hi, who are you?` | **tiếng Anh** |
| 6 | `receive the goods for purchase order P00003` | câu xác nhận **tiếng Anh**, và **mã P00003 còn nguyên** |
| 7 | `nhận hàng cho đơn mua P00003` | câu xác nhận **tiếng Việt**, byte-identical với hôm nay |

Kịch bản 6 là kịch bản DUY NHẤT chứng minh Task 3+4 hoạt động đầu-cuối. Đọc kỹ: nếu mã đơn hoặc số tiền sai lệch so với kịch bản 7 thì lớp phủ quyết đã thủng — DỪNG.

- [ ] **Step 5: Viết báo cáo**

Tạo `docs/superpowers/plans/2026-08-18-multilingual-vi-en-report.md`: số đo từng bước (nguyên văn JSON), kết quả 7 kịch bản sống, mọi chỗ lệch so với dự đoán của spike, và danh sách những gì CHƯA làm được.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/plans/2026-08-18-multilingual-vi-en-report.md
git commit -m "docs(report): so do va nghiem thu song cho da ngon ngu Viet-Anh"
```

---

## Ghi chú cho người thực thi

- **Số test kỳ vọng là số CỘNG DỒN** từ mốc 1634. Lệch thì đếm lại bằng `--collect-only` và ghi số THẬT vào báo cáo task, đừng sửa cho khớp plan.
- **Chạy lại `git status` sau mỗi lượt pytest.** Bộ test từng ghi đè file fixture đã commit; thấy file lạ "modified" mà mình không đụng thì nghi lớp lỗi đó trước.
- **Không có test nào chứng minh được ngôn ngữ đầu ra.** Mọi khẳng định về "trả lời bằng tiếng Anh" chỉ có giá trị khi đo qua HTTP thật (Task 6) — spike đã cho thấy thiết kế nghe hợp lý mà sai 2/3 vòng đầu.
