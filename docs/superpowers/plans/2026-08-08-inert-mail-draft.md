# Bản nháp mail "trơ tính" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đóng 2 rủi ro đã biết của cơ chế gửi mail xác nhận đơn (plan
`order-confirmation-email`, đã merge) bằng cách làm cho bản nháp `mail.mail`
trơ tính với cron/gửi-thật của Odoo ngay từ lúc tạo, thay vì chỉ ghi chú
rủi ro hoặc chỉ sửa thông báo.

**Architecture:** `preview_template_email` (mcp-servers/odoo/tools/mail.py)
chuyển bản nháp vừa tạo sang `state='cancel'` ngay lập tức; `send_prepared_email`
lật lại `state='outgoing'` ngay trước khi gọi `send()` thật. Cả cron "Mail:
Email Queue Manager" lẫn `mail.mail._send()` nội bộ của Odoo chỉ xử lý bản
ghi ở `state='outgoing'` (xác minh qua đọc trực tiếp mã nguồn Odoo — xem
spec). `discard_prepared_email` giữ nguyên chức năng nhưng đổi vai trò từ
"cơ chế an toàn bắt buộc" thành "dọn dẹp best-effort".

**Tech Stack:** Python, Odoo XML-RPC (`odoo_call.odoo`), LangGraph
(coordinator không đổi cấu trúc node — chỉ đổi nội dung xử lý discard).

## Global Constraints

- Không thêm whitelist bảo mật mới — `write` đã có sẵn trong
  `ODOO_METHOD_OPERATION_MAP` (`mcp-servers/odoo/security.py`) từ plan
  `order-confirmation-email`.
- Không có unit test tự động cho logic nghiệp vụ trong
  `mcp-servers/odoo/tools/mail.py` (đúng quy ước hiện có của mọi tool
  trong `tools/*.py`, xem plan `order-confirmation-email` Task 2) — đúng
  đắn của thay đổi này được xác nhận bằng live-verify (Task 3), không phải
  pytest.
- Live-verify **TRƯỚC** khi merge vào `main`, không phải sau (quy trình đã
  đảo ngược từ plan `order-confirmation-email`, theo yêu cầu người dùng).
- Không đổi cấu trúc 2-node LangGraph hay wiring trong `graph.py` —
  `write_registry.py` — chỉ đổi nội dung xử lý bên trong node đã có.

---

### Task 1: Bản nháp trơ tính trong lớp MCP tool

**Files:**
- Modify: `mcp-servers/odoo/tools/mail.py`

**Interfaces:**
- Consumes: `odoo` từ `odoo_call` (đã có sẵn, không đổi chữ ký).
- Produces: không đổi chữ ký/shape trả về của `preview_template_email`,
  `send_prepared_email`, `discard_prepared_email` — chỉ đổi hành vi nội bộ
  (thêm 1 lệnh `write()` mỗi hàm). Task 2 (coordinator) không cần đổi cách
  gọi các tool này.

**Không có test tự động riêng cho task này** — cùng lý do đã ghi trong
Global Constraints (đúng quy ước hiện có cho mọi tool trong `tools/*.py`,
xác nhận qua Task 3 live-verify).

- [ ] **Step 1: Sửa `preview_template_email` — chuyển state sang 'cancel' ngay sau khi tạo**

Trong `mcp-servers/odoo/tools/mail.py`, thay dòng 59-60:

```python
    mail_id = odoo("mail.template", "send_mail", [tpls[0]["id"], recs[0]["id"]],
                   {"force_send": False})
```

thành:

```python
    mail_id = odoo("mail.template", "send_mail", [tpls[0]["id"], recs[0]["id"]],
                   {"force_send": False})
    # Bản nháp trơ tính (spec 2026-08-08): chuyển NGAY sang state='cancel' —
    # giá trị Selection hợp lệ thật trong Odoo, không phải hack. Xác minh
    # qua mã nguồn Odoo (mail_mail.py): cron "Mail: Email Queue Manager" lọc
    # cứng theo state='outgoing', và _send() nội bộ có
    # "if mail.state != 'outgoing': continue" — bỏ qua LẶNG LẼ mọi state
    # khác, không lỗi. Bản nháp chưa xác nhận vì vậy không bao giờ ở trạng
    # thái mà cron/send() nhìn thấy, cho tới khi send_prepared_email chủ
    # động lật lại 'outgoing'.
    odoo("mail.mail", "write", [[mail_id], {"state": "cancel"}], {})
```

- [ ] **Step 2: Sửa `send_prepared_email` — lật state về 'outgoing' ngay trước khi gửi thật**

Thay dòng 96:

```python
    odoo("mail.mail", "send", [[mail_id]], {})
```

thành:

```python
    # Bắt buộc lật lại 'outgoing' TRƯỚC send() — thiếu bước này, send() nội
    # bộ của Odoo sẽ lặng lẽ bỏ qua bản ghi (state đang là 'cancel' từ
    # preview_template_email), không gửi, không báo lỗi. Xem spec 2026-08-08.
    odoo("mail.mail", "write", [[mail_id], {"state": "outgoing"}], {})
    odoo("mail.mail", "send", [[mail_id]], {})
```

- [ ] **Step 3: Cập nhật docstring module + 3 hàm cho khớp cơ chế mới**

Thay toàn bộ docstring module (dòng 1-21) thành:

```python
"""Tool MCP domain Mail (mail.template / mail.mail) — spec 2026-08-07,
cập nhật spec 2026-08-08 (bản nháp trơ tính).

3 tool DÙNG CHUNG cho MỌI điểm nối gửi mail tương lai (không riêng theo
domain — cơ chế gốc Odoo mail.template.send_mail/mail.mail.send đã là hàm
chung, không có logic nghiệp vụ riêng theo domain, khác hẳn
confirm_sale_order nơi state-check là logic riêng của sale). LLM KHÔNG tự
chọn template — mỗi coordinator ở tầng agent hardcode template_name của
chính nó; 3 tool này chỉ là lớp thực thi.

preview_template_email TẠO một bản mail.mail nháp thật (Odoo không cho
render template mà không tạo bản ghi qua XML-RPC — các method render nội
bộ như _render_template bị chặn gọi từ xa, đã kiểm chứng thật 2026-08-07).
Đây KHÔNG phải thao tác đọc thuần.

BẢN NHÁP TRƠ TÍNH TỪ LÚC TẠO (spec 2026-08-08, xác minh qua mã nguồn Odoo
thật D:\\Odoo\\server\\odoo\\addons\\mail\\models\\mail_mail.py): send_mail()
mặc định tạo bản ghi ở state='outgoing' — cron "Mail: Email Queue Manager"
của Odoo (chạy mỗi giờ) VÀ mail.mail._send() nội bộ đều chỉ xử lý bản ghi ở
state này (cron lọc cứng theo domain, _send() có
"if mail.state != 'outgoing': continue" — bỏ qua lặng lẽ, không lỗi).
preview_template_email vì vậy chuyển NGAY state sang 'cancel' (giá trị
Selection hợp lệ thật, không phải hack) sau khi tạo — bản nháp chưa xác
nhận không bao giờ ở trạng thái cron/send() nhìn thấy. send_prepared_email
PHẢI lật lại 'outgoing' NGAY TRƯỚC khi gọi send() thật (thiếu bước này thì
send() sẽ lặng lẽ không làm gì, đúng dòng nói trên).

discard_prepared_email giờ chỉ còn là DỌN DẸP (xóa bản nháp bị từ chối cho
gọn CSDL), KHÔNG còn là cơ chế an toàn — bản nháp đã trơ tính sẵn kể từ lúc
tạo nên thất bại của discard không còn kéo theo rủi ro gửi ngoài ý muốn."""
```

Thay docstring của `preview_template_email` (dòng 31-42):

```python
    """
    Soạn (nhưng CHƯA gửi) một mail từ template Odoo có sẵn cho MỘT bản ghi
    cụ thể. LƯU Ý: bước này TẠO một bản ghi mail.mail nháp thật trong Odoo
    (Odoo không cho render template mà không tạo bản ghi qua XML-RPC) —
    KHÔNG phải thao tác đọc thuần. Bản ghi được chuyển NGAY sang
    state='cancel' (trơ tính với cron gửi mail của Odoo — xem docstring
    module) cho tới khi send_prepared_email được gọi. YÊU CẦU XÁC NHẬN từ
    người dùng trước khi gọi send_prepared_email với mail_id trả về.

    Args:
        template_name: Tên chính xác của mail.template, vd "Sales: Order Confirmation".
        res_model: Model của bản ghi nguồn, vd "sale.order".
        ref: Mã bản ghi (field 'name'), vd "S00166".
    """
```

Thay docstring của `send_prepared_email` (dòng 88-95):

```python
    """
    Gửi thật một mail đã soạn sẵn qua preview_template_email (dùng ĐÚNG
    mail_id đã trả về, không tạo lại). Lật state từ 'cancel' (trơ tính)
    sang 'outgoing' ngay trước khi gọi send() — xem docstring module.
    YÊU CẦU XÁC NHẬN từ người dùng trước khi gọi.

    Args:
        mail_id: ID bản ghi mail.mail đã soạn (từ preview_template_email).
    """
```

Thay docstring của `discard_prepared_email` (dòng 119-130):

```python
    """
    Hủy một mail đã soạn qua preview_template_email nhưng người dùng từ
    chối gửi — xóa bản mail.mail nháp. Bản nháp đã trơ tính với cron gửi
    mail của Odoo ngay từ lúc tạo (state='cancel' — xem docstring module),
    nên gọi tool này ở nhánh từ chối chỉ là DỌN DẸP (tránh tích lũy bản
    nháp rác trong Odoo theo thời gian) — không còn là cơ chế an toàn bắt
    buộc, thất bại của nó không còn kéo theo rủi ro gửi ngoài ý muốn.

    Args:
        mail_id: ID bản ghi mail.mail cần hủy (từ preview_template_email).
    """
```

- [ ] **Step 4: Chạy toàn bộ test suite để xác nhận không hồi quy**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"`
Expected: cùng số lượng pass như baseline trước plan này (file này không
có test riêng, nhưng đảm bảo import/cấu trúc module không vỡ).

- [ ] **Step 5: Commit**

```bash
git add mcp-servers/odoo/tools/mail.py
git commit -m "$(cat <<'EOF'
feat(mail): bản nháp mail trơ tính từ lúc tạo (state='cancel')

preview_template_email chuyển state sang 'cancel' ngay khi tạo bản nháp;
send_prepared_email lật lại 'outgoing' ngay trước khi gửi thật. Đóng rủi
ro cron "Mail: Email Queue Manager" của Odoo tự gửi bản nháp bị bỏ dở —
xác minh qua mã nguồn Odoo: cron + send() nội bộ đều lọc cứng theo
state='outgoing'.
EOF
)"
```

---

### Task 2: Đơn giản hóa xử lý discard ở coordinator

**Files:**
- Modify: `backend/src/agents/mail_write.py`
- Test: `backend/tests/agents/test_mail_write.py`

**Interfaces:**
- Consumes: không đổi — vẫn dùng `discard_prepared_email` qua `by_name`
  như cũ, chỉ đổi cách xử lý kết quả trả về của nó.
- Produces: không đổi chữ ký của `make_send_order_confirmation_email_node`,
  `make_send_order_confirmation_email_preview_node`, `route_after_mail_preview`.

**Bối cảnh bắt buộc đọc trước:** Task 1 làm cho bản nháp trơ tính ngay từ
lúc tạo — `discard_prepared_email` thất bại giờ chỉ để lại rác trong Odoo,
không còn rủi ro gửi ngoài ý muốn. Đoạn cảnh báo "⚠️ Không hủy được bản
nháp... có thể vẫn tự động gửi... trong vòng 1 giờ tới" (thêm ở plan
`order-confirmation-email`, final review Finding 1) giờ SAI — phải bỏ,
không chỉ để yên (một cảnh báo về rủi ro không còn tồn tại gây hoang mang
không cần thiết, tệ hơn không nói gì).

- [ ] **Step 1: Sửa 2 test hiện có để phản ánh hành vi MỚI (không còn cảnh báo)**

Trong `backend/tests/agents/test_mail_write.py`, thay toàn bộ hàm
`test_discard_loi_khong_chan_thong_bao_huy` (dòng 138-167) thành:

```python
@pytest.mark.asyncio
async def test_discard_loi_khong_chan_thong_bao_huy_khong_con_canh_bao_rui_ro(monkeypatch):
    """discard_prepared_email lỗi (vd Odoo mạng lỗi) không được chặn thông
    báo 'đã hủy' cho người dùng — best-effort, không phải hợp đồng chính.
    KHÁC bản trước spec 2026-08-08 (bản nháp trơ tính — xem
    mcp-servers/odoo/tools/mail.py): bản nháp đã ở state='cancel' từ lúc
    Node 1 tạo ra, cron/gửi thật không thể chạm tới nó dù discard thất
    bại, nên KHÔNG còn cần cảnh báo rủi ro cron 1 giờ như trước."""
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: True)
    preview_calls, send_calls = [], []
    preview_tool, send_tool, _ = _tools(preview_calls, send_calls, [])
    discard_tool = MagicMock()
    discard_tool.name = "discard_prepared_email"

    async def _raise_discard(_args):
        raise RuntimeError("Lỗi kết nối Odoo")

    discard_tool.ainvoke = _raise_discard
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    cfg = {"configurable": {"thread_id": "m3b"}}
    await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    res = await graph.ainvoke(Command(resume=False), cfg)
    assert send_calls == []
    final = res["messages"][-1].content
    assert "hủy" in final.lower()
    assert "không hủy được bản nháp" not in final.lower()
    assert "1 giờ" not in final
```

Thay toàn bộ hàm `test_gate_tat_va_discard_loi_thi_canh_bao_ro_rui_ro_con_lai`
(dòng 170-202) thành:

```python
@pytest.mark.asyncio
async def test_gate_tat_va_discard_loi_khong_con_canh_bao_rui_ro(monkeypatch):
    """Nhánh gate-tắt-giữa-chừng: discard_prepared_email tự nó gọi odoo()
    với method 'unlink', bị CHÍNH write_actions_enabled() gate (đã False ở
    nhánh này) chặn giống mọi write khác, nên gần như chắc chắn thất bại
    đúng lúc cần dọn nhất. KHÁC bản trước spec 2026-08-08: bản nháp đã trơ
    tính (state='cancel') từ lúc tạo, nên thất bại dọn dẹp ở đây chỉ để
    lại rác trong Odoo — KHÔNG còn kéo theo rủi ro gửi ngoài ý muốn, nên
    KHÔNG còn cần cảnh báo."""
    gate = {"on": True}
    monkeypatch.setattr(write_gate, "write_actions_enabled", lambda: gate["on"])
    preview_calls, send_calls = [], []
    preview_tool, send_tool, _ = _tools(preview_calls, send_calls, [])
    discard_tool = MagicMock()
    discard_tool.name = "discard_prepared_email"

    async def _raise_discard(_args):
        raise RuntimeError("Thao tác 'unlink' bị chặn — write-mode đang tắt")

    discard_tool.ainvoke = _raise_discard
    tools = [preview_tool, send_tool, discard_tool]
    graph = _graph(mw.make_send_order_confirmation_email_preview_node(tools),
                   mw.make_send_order_confirmation_email_node(tools))
    cfg = {"configurable": {"thread_id": "m3c"}}
    res1 = await graph.ainvoke(_state({"order_ref": "S00166"}), cfg)
    assert "__interrupt__" in res1

    gate["on"] = False
    res2 = await graph.ainvoke(Command(resume=True), cfg)
    assert send_calls == []
    final = res2["messages"][-1].content
    assert "không hủy được bản nháp" not in final.lower()
    assert "1 giờ" not in final
```

- [ ] **Step 2: Chạy 2 test vừa sửa để xác nhận chúng FAIL trên code cũ**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q tests/agents/test_mail_write.py -k "khong_con_canh_bao_rui_ro" -v`
Expected: FAIL — cả 2 test đều thấy `"không hủy được bản nháp"` VÀ
`"1 giờ"` xuất hiện trong thông báo (code cũ vẫn thêm cảnh báo), đúng
nghĩa "đỏ trước khi sửa".

- [ ] **Step 3: Sửa `mail_write.py` — bỏ `_with_discard_warning`, đơn giản hóa `_discard_draft`**

Thay toàn bộ khối từ `async def _discard_draft` tới hết `_with_discard_warning`
(dòng 159-181) thành:

```python
    async def _discard_draft(mail_id) -> None:
        """Best-effort dọn dẹp bản nháp bị từ chối/gate-tắt. Bản nháp đã trơ
        tính (state='cancel' — mcp-servers/odoo/tools/mail.py, spec
        2026-08-08) ngay từ lúc Node 1 tạo ra nó, nên thất bại ở đây (vd
        unlink cũng bị chặn bởi write_actions_enabled() giống mọi write
        khác) chỉ để lại một bản ghi rác nằm im trong Odoo — KHÔNG còn kéo
        theo rủi ro gửi ngoài ý muốn (khác thiết kế cũ trước 2026-08-08)."""
        discard_tool = by_name.get("discard_prepared_email")
        if discard_tool is None:
            return
        try:
            await discard_tool.ainvoke({"mail_id": mail_id})
        except Exception:  # noqa: BLE001 — best-effort, không raise cho user
            pass
```

Thay 2 điểm gọi. Đoạn nhánh gate-tắt (dòng 187-199), thay:

```python
        if not write_gate.write_actions_enabled():
            # Bản nháp (Node 1) đã tồn tại thật, đang ở trạng thái 'outgoing'
            # — cron "Mail: Email Queue Manager" sẽ gửi nó bất kể gate nếu
            # không chủ động hủy (khác các coordinator khác: gate tắt ở đó
            # chỉ cần từ chối, KHÔNG có side-effect nào đã xảy ra để dọn).
            # discard_prepared_email TỰ NÓ gọi odoo() với method "unlink"
            # (không phải "read") — cùng write_actions_enabled() gate vừa
            # kiểm tra False ở trên sẽ chặn LUÔN cả unlink này (Finding 1,
            # final review 2026-08-07). Nghĩa là đúng lúc cần dọn nhất, cuộc
            # gọi dọn gần như chắc chắn thất bại — không được im lặng nuốt
            # kết quả đó như trước, phải báo thật cho người dùng.
            discarded = await _discard_draft(mail_id)
            return _with_discard_warning(WRITE_DISABLED_MSG, discarded)
```

thành:

```python
        if not write_gate.write_actions_enabled():
            # Bản nháp (Node 1) đã tồn tại thật, nhưng đã trơ tính
            # (state='cancel', spec 2026-08-08) ngay từ lúc tạo — dọn ở đây
            # chỉ là best-effort, không còn ảnh hưởng tới an toàn (xem
            # docstring module + _discard_draft).
            await _discard_draft(mail_id)
            return _msg(WRITE_DISABLED_MSG)
```

Đoạn nhánh từ chối (dòng 209-211), thay:

```python
        if not confirmed:
            discarded = await _discard_draft(mail_id)
            return _with_discard_warning("Đã hủy gửi mail xác nhận đơn.", discarded)
```

thành:

```python
        if not confirmed:
            await _discard_draft(mail_id)
            return _msg("Đã hủy gửi mail xác nhận đơn.")
```

- [ ] **Step 4: Cập nhật docstring module cho khớp cơ chế mới**

Thay toàn bộ docstring module `mail_write.py` (dòng 2-80) thành:

```python
"""Coordinator gửi mail xác nhận đơn hàng thật — spec 2026-08-07, cập nhật
spec 2026-08-08 (bản nháp trơ tính — xem mcp-servers/odoo/tools/mail.py).

TÁCH 2 NODE LangGraph — KHÁC MỌI coordinator khác trong package này (chỉ
có 1 node). Lý do: preview_template_email TỰ NÓ là một write thật (tạo
mail.mail nháp) — Odoo không cho render template mà không tạo bản ghi qua
XML-RPC. Nếu gọi nó TRƯỚC _interrupt() trong CÙNG một node (khuôn mọi
coordinator khác dùng, vì bước "render" của họ là READ thuần, idempotent),
LangGraph sẽ REPLAY TOÀN BỘ node khi resume sau interrupt — đo thật bằng
probe (review Task 3, 2026-08-07): preview bị gọi LẦN THỨ HAI, tạo bản
mail.mail thứ hai, và mail thật sự gửi đi KHÔNG PHẢI bản người dùng đã
duyệt. Tách node giải quyết triệt để: mỗi node hoàn tất là một ranh giới
checkpoint LangGraph — node đã return xong không bị replay khi node SAU
nó (nơi có interrupt) resume.

  Node 1 (send_order_confirmation_email_preview): gọi preview_template_email
    MỘT LẦN DUY NHẤT, lưu mail_id/subject/recipients vào pending_action.args
    (persist qua state, không phải biến cục bộ), rồi (qua conditional edge ở
    graph.py, KHÔNG unconditional) chuyển sang Node 2 nếu thành công, hoặc
    thẳng write_continuation nếu lỗi/thiếu input.
  Node 2 (send_order_confirmation_email): đọc dữ liệu đã lưu từ Node 1
    (KHÔNG gọi lại preview), tự re-check write_gate (xem Finding 1 dưới),
    _interrupt xác nhận, rồi gọi send_prepared_email.

"recipients" LÀ DANH SÁCH NGƯỜI NHẬN THẬT, KHÔNG PHẢI SỐ LƯỢNG (final review
2026-08-07, Finding 4 — Important): bản trước lưu "recipient_count" và hiện
"Tới: N người nhận" ở cổng xác nhận — người dùng không thể biết AI định gửi
mail cho AI, nên cổng xác nhận (thứ được dựng ra CHÍNH để bắt sai người nhận)
mất tác dụng. preview_template_email (mcp-servers/odoo/tools/mail.py) giờ đọc
cả recipient_ids (many2many res.partner, resolve tên/email qua "read") lẫn
email_to (field địa chỉ thô song song — bỏ sót nó thì đếm/liệt kê ra rỗng dù
mail VẪN sẽ gửi tới địa chỉ đó) và trả về "recipients": [chuỗi người đọc
được, ...].

BẢN NHÁP TRƠ TÍNH TỪ LÚC TẠO (spec 2026-08-08 — ĐÓNG rủi ro "hội thoại bị
bỏ dở" từng ghi ở đây là CHẤP NHẬN, không sửa): preview_template_email giờ
tự chuyển state của bản nháp sang 'cancel' ngay sau khi tạo (xác minh qua
chính mã nguồn Odoo: cron "Mail: Email Queue Manager" VÀ mail.mail._send()
nội bộ đều chỉ xử lý bản ghi ở state='outgoing', bỏ qua lặng lẽ mọi state
khác) — coordinator ở file này không cần biết/làm gì thêm, cơ chế nằm trọn
trong lớp MCP tool. Hệ quả: discard_prepared_email (dưới đây) không còn là
cơ chế an toàn bắt buộc nữa, chỉ còn là dọn dẹp best-effort.

NODE 2 PHẢI TỰ RE-CHECK write_gate (review round 2, Finding 1 — Important,
2026-08-07): tách 2 node vô tình xóa mất một bất biến an toàn mà mọi
coordinator 1-node khác có MIỄN PHÍ — LangGraph replay TOÀN BỘ node khi
resume sau interrupt, nên gate check ở đầu node của họ tự động chạy lại ở
MỌI lần resume. Node 1 ở đây chỉ chạy MỘT LẦN trước khi interrupt tồn tại,
nên nếu chỉ Node 1 check gate, gate bị tắt (từ Odoo UI) ngay lúc câu hỏi
xác nhận đang chờ sẽ không bao giờ được phát hiện — đo thật: thiếu check
này, resume(confirm=True) vẫn gửi mail thật dù gate đã tắt.

TỪ CHỐI GỬI VẪN GỌI discard_prepared_email — GIỜ CHỈ LÀ DỌN DẸP, KHÔNG PHẢI
AN TOÀN (đảo ngược nốt phần còn lại của quyết định §4.1 gốc của spec, sau
khi spec 2026-08-08 đóng triệt để rủi ro cron ở lớp MCP tool): bản nháp đã
trơ tính (state='cancel') ngay từ lúc Node 1 tạo ra nó, nên thất bại của
discard_prepared_email (vd bị chính write_actions_enabled() gate chặn ở
nhánh gate-tắt-giữa-chừng — unlink cũng là write) chỉ để lại một bản ghi
rác nằm im trong Odoo, KHÔNG kéo theo rủi ro gửi ngoài ý muốn nữa — không
còn cần cảnh báo người dùng về rủi ro đó (khác bản trước 2026-08-07).

KHÔNG đăng ký vào NEXT_STEPS: confirm_sale_order đã có bước kế tiếp
"deliver_order" — thêm bước này vào sẽ ghi đè, phá chuỗi giao hàng có sẵn.
Gửi mail xác nhận là hành động người dùng tự yêu cầu riêng — PHẢI được
liệt kê trong WRITE_PLANNER_PROMPT (prompts.py) để planner có thể chọn nó,
khác các coordinator chỉ tới được qua NEXT_STEPS."""
```

- [ ] **Step 5: Chạy lại 2 test vừa sửa, xác nhận PASS**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q tests/agents/test_mail_write.py -v`
Expected: toàn bộ 10 test trong file PASS (bao gồm 2 test vừa đổi tên).

- [ ] **Step 6: Chạy toàn bộ test suite để xác nhận không hồi quy nơi khác**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q -m "not live and not integration"`
Expected: cùng số lượng pass như baseline (Task 1 không thêm test, Task 2
đổi tên 2 test cũ chứ không tăng tổng số).

- [ ] **Step 7: Commit**

```bash
git add backend/src/agents/mail_write.py backend/tests/agents/test_mail_write.py
git commit -m "$(cat <<'EOF'
refactor(mail): bỏ cảnh báo rủi ro cron đã lỗi thời sau bản nháp trơ tính

Task 1 (mail.py) đã đóng triệt để rủi ro cron tự gửi bản nháp ở lớp MCP
tool — cảnh báo "có thể vẫn bị gửi trong 1 giờ" ở coordinator giờ sai và
gây hoang mang không cần thiết. discard_prepared_email giờ chỉ còn là
dọn dẹp best-effort, không phải cơ chế an toàn.
EOF
)"
```

---

### Task 3: Cổng nghiệm thu live-verify

**Files:** không sửa code. Ghi kết quả vào
`docs/superpowers/plans/2026-08-08-inert-mail-draft-report.md`.

**Bối cảnh bắt buộc đọc trước:** không có unit test nào chứng minh được
`state` thật sự đổi đúng thời điểm trong Odoo thật — phải đọc trực tiếp
`mail.mail.state` qua XML-RPC/Odoo UI ở từng bước.

- [ ] **Step 1: Khởi động lại backend + mcp-odoo để nạp code mới**

```powershell
.\start-dev.ps1
```

Nếu backend/mcp-odoo đã chạy sẵn từ phiên trước, **phải dừng và khởi động
lại thủ công** (script tự phát hiện cổng đã có tiến trình khỏe mạnh và BỎ
QUA khởi động lại — không đủ để nạp code Task 1-2 vừa viết). Kiểm tra PID
trước/sau để xác nhận đã restart thật.

- [ ] **Step 2: Tiêu chí 1 — bản nháp phải ở state='cancel' ngay sau khi soạn**

Xác nhận thật một đơn bán (chuỗi `create_quotation → confirm_sale_order`
qua đối tác/sản phẩm thật), rồi gửi: `"Gửi mail xác nhận đơn [mã đơn thật]
cho khách"`. Ghi lại `mail_id` xuất hiện trong phản hồi xem trước.

ĐẠT khi: đọc trực tiếp `mail.mail.state` (qua XML-RPC hoặc Odoo UI —
Settings → Technical → Email → Emails, tìm theo ID) bằng đúng `mail_id`
đó, giá trị là **`'cancel'`**, KHÔNG phải `'outgoing'`.

- [ ] **Step 3: Tiêu chí 2 — bản nháp 'cancel' phải vô hình với cron**

Trong lúc bản nháp (Tiêu chí 1) vẫn đang chờ xác nhận (chưa trả lời có/không),
kiểm tra cron "Mail: Email Queue Manager" (Settings → Technical → Automation
→ Scheduled Actions) — chạy thủ công nếu có thể ("Run Manually"), hoặc đợi
tới chu kỳ chạy tự nhiên.

ĐẠT khi: sau khi cron chạy, đọc lại `mail.mail.state` bằng `mail_id` đó —
**vẫn là `'cancel'`**, không đổi, không có `mail.mail` nào bị gửi ngoài ý
muốn.

- [ ] **Step 4: Tiêu chí 3 — từ chối vẫn hoạt động đúng (không hồi quy)**

Từ đơn ở Tiêu chí 1 (nếu đã bị cron ở Tiêu chí 3 "tiêu thụ" do state
không đổi thì vẫn dùng lại được), trả lời `"không"`.

ĐẠT khi: phản hồi xác nhận đã hủy; `mail.mail` bị xóa (discard/unlink
thành công) hoặc — nếu discard thất bại vì lý do khác — vẫn ở `state`
không phải trạng thái đã gửi.

- [ ] **Step 5: Tiêu chí 4 — gửi thật vẫn hoạt động đúng (không hồi quy)**

Lặp lại Tiêu chí 1 với một đơn khác, trả lời `"có"`.

ĐẠT khi: `mail.mail.state` chuyển sang trạng thái đã gửi (không phải
`exception`), xác nhận qua XML-RPC/Odoo UI — hoặc bản ghi biến mất hoàn
toàn nếu template có `auto_delete=True` (hành vi đã biết từ plan
`order-confirmation-email`, không phải lỗi). Nếu có quyền truy cập hộp
mail nhận thật, xác nhận email thật sự tới nơi.

- [ ] **Step 6: Viết report và commit**

Ghi rõ từng tiêu chí ĐẠT/KHÔNG kèm bằng chứng thật (trạng thái `mail.mail`
đọc trực tiếp từ Odoo ở mỗi bước, không suy đoán).

```bash
git add docs/superpowers/plans/2026-08-08-inert-mail-draft-report.md
git commit -m "docs(inert-mail-draft): kết quả live-verify"
```
