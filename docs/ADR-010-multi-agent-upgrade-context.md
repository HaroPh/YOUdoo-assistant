# ADR-010: Multi-Agent Upgrade — Context Handoff

> **Purpose:** This file exists so a fresh session in a **new repo** (SP-1
> onward) has the full rationale and roadmap without depending on this
> project's local memory system, which is keyed to this repo's path and
> does not carry over. Copy or link this file into the new repo before
> starting SP-1.

## Why this initiative exists

This project (`D:\Project`, single-repo ERP AI assistant) is evolving into
a new repo with a genuine multi-agent architecture: dedicated planner
model, real orchestrator, task-specialized models — not the current
single-LangGraph-with-role-based-model-routing design.

Framed explicitly as **executing a trigger `ADR-008-MCP-vs-A2A.md` §5
already pre-registered**, not reversing that ADR's prior rejection of
multi-agent (2026-06-24). ADR-008 rejected multi-agent for 2 reasons that
a cloud-API design specifically dissolves:
1. 1-GPU sequential Ollama latency ("8-12 LLM call tuần tự cho 1 câu hỏi
   ⇒ 30-90s. Không dùng được")
2. Small 8B model chokes on orchestrator indirection

ADR-008 §5 pre-registers exact graduation triggers, including "Report
Agent chạy cron... nặng, chạy nền, lịch riêng" and "Khác phần cứng: một
agent cần GPU lớn" — both independently satisfied by a second existing app
(meeting audio transcription + summarization, GPU-bound, separate repo)
that is planned as **one of the multi-agent's specialist agents**, not a
standalone app. This is the strongest concrete justification for going
ahead now.

`ADR-009-architecture-baseline-synthesis.md` (QĐ M2) already locks a
role-based hybrid model split — `CLOUD_ALLOWED = frozenset({"router",
"evaluator", "chitchat"})` in `backend/src/agents/models.py`;
Read/Planner/Fusion/Synthesis pinned local for privacy. QĐ M3: eval-gate
mandatory before ANY model/prompt flip — this is why SP-0 (measurement
capability) had to happen before SP-1 (actual model/architecture changes).

## Priorities (user-confirmed, in order)

**B (kiến trúc rõ ràng, portfolio-worthy) chính, cộng A (chất lượng) và C
(song song).** Data-egress/privacy concerns explicitly deferred for this
initiative ("tạm thời bỏ qua việc có lộ dữ liệu vì sử dụng api") — this is
a deliberate scope choice, not an oversight.

## Resources committed

3 free API keys:
- **OpenRouter** — unfunded account, ~50 req/day hard cap. Treat as a
  scarce/special-purpose provider, not a main path.
- **Google AI Studio**
- **Groq**

Local GPU: dropped entirely as a chat-path fallback. Repurposed for
Whisper transcription in the meeting agent (SP-4); summarization for that
agent goes to Groq instead (fast with long text).

## Architecture decisions already made (mid-brainstorm, before SP-1 starts)

- Orchestrator does multi-step coordination + synthesis, with **general
  fan-out capability** — not limited to the RAG+ERP hybrid-question case.
  Read-only tasks parallelize freely; writes stay sequential (confirm-gate
  + Odoo race-condition reasons already baked into the current codebase —
  this constraint carries forward unchanged).
- Cross-provider fallback (Groq ↔ Google ↔ OpenRouter) replaces the old
  local-GPU fallback chain for chat-path roles.
- Recommended orchestrator framework direction: `langgraph-supervisor`
  prebuilt package, built on the existing LangGraph investment, rather
  than switching frameworks entirely.
- `monitoring/litellm-config.yaml` already has Gemini free-tier wired for
  2 roles with a fallback-to-local chain — the mechanism SP-1 extends to
  3 providers.

## Roadmap: 5 sub-projects, each its own spec → plan → implement cycle

| # | Sub-project | Status |
|---|---|---|
| **SP-0** | Eval coverage expansion (measure BEFORE any model change — ADR-009 M3 hard prerequisite) | **DONE**, merged @ `57db71c` in this repo, pushed |
| SP-1 | Foundation: new repo + 3-provider gateway/fallback + Langfuse tracing + port tool/security/RAG layers wholesale | Next |
| SP-2 | Orchestrator + specialist agents, built-in fan-out (reads parallel, writes always sequential) | — |
| SP-3 | Quota/concurrency hardening for the 3 free tiers under real fan-out load | — |
| SP-4 | Meeting agent (Whisper GPU + Groq summarization) | — |

SP-0 had to precede SP-1 because a "before" baseline can only be captured
once, and QĐ M3 requires it before any model/prompt flip.

## SP-0 outcome (for context — full detail in this repo's memory/ledger, not reproduced here)

Extended `backend/evals/` / `backend/jobs/eval_gate.py` from 3 to 7 eval
sets (`intent`, `confirm`, `chitchat`, `planner`, `read`, `synthesis`,
`multi_source`), each with hard anti-hallucination/misroute gates.
Captured 6 real baseline files against local `qwen3:8b` — these are the
**"before" numbers SP-1 must compare against** once cloud models are
substituted in for cloud-eligible roles.

One known, deliberately-deferred limitation carried forward: `multi_source`
eval's `fabricated_number` hard gate reproducibly fails against baseline
qwen3:8b (`fabricated_number: 4`) due to a basis-mismatch bug in the eval
scanner itself (compares against raw chunk text instead of the
section-labeled context the model actually sees) — documented in
`backend/evals/cases.py` next to `MULTI_SOURCE_CASES`. Not fixed by user's
explicit choice; a candidate to revisit if SP-1's cloud models are
evaluated against this same set.

## Standing rule adopted from SP-0's final review

Any decision a future session must not re-litigate needs a comment in a
**tracked file** at the point of code it affects — not only in a
gitignored ledger or in this project's local memory system, both of which
do not survive a repo change. This file exists because of that rule.
