# Manual Test Scenarios — Youdoo ERP Assistant

Copy-paste these into the chat UI at **http://localhost:3002** (model
`erp-assistant` / "Youdoo ERP Assistant"). Every reference (order code,
invoice code, product name) below was verified against the **live Odoo
instance** just before writing this doc — not from eval fixtures, which
use frozen/synthetic data that doesn't necessarily match what's really in
Odoo right now. If you re-run this later and an order's state has drifted
(demo data does drift over time — see README "Known limitations"), that's
expected; re-verify with the read-query scenario first.

## 1. Read-only ERP lookup

```
Chi tiết đơn S00165
```
Exercises `erp_read` directly. Real order: Acme Corporation, delivered in
full (`delivery_status: full`, `effective_date` set 2026-07-25).

## 2. Mixed query — real delivery data (should give a confident answer)

```
Đơn S00165 có đáp ứng SLA giao hàng không?
```
This is exactly the case type the `fuse_answer` fix from today
(2026-08-04/05) targeted — needs both the SLA policy document (deadline +
penalty clauses) and this order's real ERP delivery data. Order S00165 has
real `effective_date` data, so expect a real synthesized answer, not an
"insufficient data" refusal.

## 3. Mixed query — known limitation (should honestly say "not enough data")

```
Đơn S00042 có đáp ứng SLA giao hàng không?
```
Order S00042 is real but currently sits in `draft` state with
`delivery_status`, `commitment_date`, and `effective_date` all unset — a
genuine demo-data gap, documented in `backend/evals/cases.py` and the
README's "Known limitations". **A good answer here is one that says it
doesn't have enough information** — if it confidently states a delivery
date or SLA verdict for this order, that's a real bug worth reporting, not
an expected result.

## 4. Document-only policy question

```
Chính sách hoàn hàng của công ty là gì?
```
Exercises the `rag` node — document retrieval only, no ERP call needed.

## 5. Price lookup (the capability fixed earlier today)

```
Giá niêm yết của Large Cabinet là bao nhiêu?
```
Exercises the `find_product` → `get_product_price` chain. Real product
(`E-COM07`, "Large Cabinet") exists in the catalog. Expect a plain list
price, no discount claim — `get_product_price` genuinely cannot compute
pricelist-applied discounts (see README).

## 6. ERP aggregate query

```
Hóa đơn nào đang quá hạn?
```
Real live data at time of writing: 22 overdue invoices across Acme
Corporation, OpenWood, LightsUp, and Azure Interior. A good answer
summarizes rather than dumping all 22 raw — worth noting if it doesn't.

## 7. Write action (optional — has a real effect, read this first)

Write actions are gated by a runtime kill-switch
(`erp_ai.write_actions_enabled` in Odoo → Settings → Technical → System
Parameters) that defaults to **off**. If it's off, this scenario should be
refused outright, which is itself a correct result to verify. If you
deliberately turn it on to test the confirmation flow:

```
Xác nhận đơn S00042
```
Expect the assistant to describe the exact action (tool + args) and ask
for explicit confirmation *before* touching Odoo — verifying the
confirm-before-execute flow the README describes. Don't confirm it unless
you're fine with S00042's live state actually changing.

## 8. Chitchat — identity

```
Bạn là ai?
```
Exercises `respond_unknown`/chitchat directly, no ERP or RAG call. Verified
2026-08-06: replies "Tôi là Youdoo, trợ lý ERP nội bộ của bạn" — confirms
the assistant identifies itself correctly (was a real gap, fixed 2026-08-05,
see README "Why it's structured this way").

## 9. Informal write suggestion → bare "okay" (also has a real effect, read
   scenario 7's caveat first)

Different code path from scenario 7: instead of an explicit write command,
this asks a *mixed* question, gets a natural-language suggestion back, then
replies with a bare "okay" — the case README's "Why it's structured this
way" describes (state-field marker carrying the suggestion across turns).
Send these three messages **in the same conversation, in order**:

```
có 1 khách hàng sắp đặt 30 cái individual workplace, nhưng kho chỉ còn 16 cái, tôi muốn nhập 20 cái individual workplace
```
Expect a clarifying question (which supplier) — or, if the product/supplier
data has changed since, it may answer differently; either is fine, just
keep going with what it actually asks.

```
có các nhà cung cấp nào bán individual workplace?
```
Expect a natural-language write suggestion ending in a question, e.g. "Bạn
có muốn tôi tạo đơn mua **20 cái** ... không?" — **no visible marker text**
in the reply (if you ever see literal "ĐỀ_XUẤT_GHI" in the response, that's
the bug from 2026-08-06 regressing — report it).

```
okay
```
Expect this to reach the **same interrupt-gated confirmation** as scenario
7 (e.g. "Bạn xác nhận giúp mình nhé? (trả lời "có" để thực hiện, "không" để
hủy)") — not a generic chitchat reply. Verified live 2026-08-06 against the
real backend on this exact 3-message conversation. Don't send a follow-up
"có" unless you're fine with a real purchase order being created.

## What to watch for across all of these

- Does the assistant ever state a number or date that isn't traceable to
  either the ERP data or the policy document? (Should never happen —
  report it if it does.)
- For scenario 3, does it correctly refuse rather than guess?
- Response latency — multi-source (mixed) queries call 2+ LLM turns
  sequentially plus retrieval, so a few seconds is normal.
