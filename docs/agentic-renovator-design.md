# AI Agentic Home Renovator — Product & Technical Design

Turning `Renovation_Planner_v2.html` (a deterministic, offline, single-file renovation planner) into a conversational AI agent, built on **LangChain Deep Agents**. This document covers the feature set, the technical architecture, and a phased implementation plan.

Base features referenced throughout: [`docs/feature.md`](./feature.md). Static reference implementation: `Renovation_Planner_v2.html`.

---

## 1. Executive summary

The static planner already encodes a correct, well-tested **domain model** (rooms, rate card, phases, stages, tasks/lines, dependencies, a deterministic scheduling engine) and a **manual UI** for editing it. The agentic version keeps that domain model and its deterministic engine exactly as-is — that logic must never be left to an LLM to "compute" — and adds a conversational layer on top that can:

- build and edit the plan from natural language ("redo the kids' bathroom, tile + paint, start after Diwali"),
- delegate specialist sub-tasks (scheduling trade-offs, procurement, budget triage, research) to focused sub-agents,
- research real-world rates/vendors instead of relying only on the built-in rate card,
- read room photos and turn them into draft tasks,
- proactively flag risks (budget overrun, overdue materials, circular dependencies, schedule slip),
- and still produce the same Excel workbook the static app produces, for backward compatibility and as a portable backup/handoff artifact.

The recommended framework is **`deepagents`** (`langchain-ai/deepagents`), which provides three primitives out of the box that map cleanly onto this problem: a **planning/todo tool**, a **virtual filesystem** for scratch state and memory, and a **sub-agent (`task`) tool** for delegating isolated multi-step work — the same shape of harness Claude Code itself uses.

---

## 2. Product vision — from self-planner to agentic co-pilot

The static app's mental model (feature.md §1) doesn't change: **Task → Lines (single/split) → Room, Rate card, Phase vs. Stage, Dependencies, Duration**. What changes is *how the user populates and steers that model*:

| Static app | Agentic app |
|---|---|
| User manually adds every task via a form or template | User describes intent; agent proposes tasks (from templates + research) for approval |
| User manually resolves budget overruns | Agent watches the Estimate tab live and proactively suggests phase pushes |
| User manually chases material need-by dates | Agent surfaces "buy this week" and can draft vendor messages |
| Rate card is whatever the user typed in | Agent can research current market rates and propose rate-card updates (never silently overwrites) |
| Import/export Excel is the only way to move data | Same Excel round-trip is retained as a tool the agent (and user) can invoke |
| Single HTML file, fully offline | Requires an LLM call to get "AI" behavior — see §6 open questions on the offline tradeoff |

**The UI is a full rebuild, not a reuse.** `Renovation_Planner_v2.html` is reference material for behavior (what every tab, control, and interaction must do), not a codebase to embed or extend live. The new frontend is built from scratch, and must work as a complete app in two modes on one codebase: **non-agentic** (tabs, Gantt, board, modals — direct manipulation, no LLM involved at all) and **agentic** (the same canvas plus a chat panel, §4.10).

---

## 3. Features

### 3.1 Retained core domain features (unchanged from feature.md)

These stay exactly as specified in feature.md and are ported faithfully, not reinterpreted:

- Rooms, rate card, phases (priority axis), stages (trade-sequence axis) — all centrally managed (feature.md §3).
- Tasks as one or two lines (single / Material+Labour split), with room, category, trade, duration, mandatory/optional flag, dependencies, fixed-start override (§1, §4).
- Templates for the 10 common jobs (§4.2) and bulk multi-select actions (§4.3).
- The forward-pass scheduling engine: project start → stage cascade (optional) → dependency finishes → fixed-start pin → working-day duration → project end (§10).
- Three schedule views (Timeline/Gantt, By-date/agenda, Board/kanban) and the suggested dependency-aware execution order (§5).
- Materials tab grouped by need-by week with buy-status and vendor notes (§6).
- Estimate tab (grand total / mandatory / optional / materials, by room/trade/phase) (§7).
- Track tab (status, actuals, variance) (§8).
- Autosave and the Excel export/import workbook (9 sheets) including legacy-format backward compatibility (§9).

### 3.2 New agentic capabilities (the delta)

1. **Conversational plan creation.** "It's a 3BHK in Bangalore, 8L budget, start Nov 1, kitchen + 2 bathrooms + full paint." The agent drafts rooms, tasks (via templates + rate card + research), phases, and a starting schedule — presented as a diff/draft for the user to approve before it's committed to the live plan.
2. **Natural-language task editing.** "Push all optional tasks to Phase 3", "move the tiling stage after electrical", "the plumber can only come on the 10th" — translated into the same bulk/edit operations the UI exposes, never freehand plan mutation outside the schema.
3. **Live budget guardian.** Watches the Estimate tab as the plan changes; when mandatory + likely-optional spend approaches the stated budget, proactively suggests moving specific optional tasks to a later phase (mirrors the "Managing the budget" workflow in feature.md §11) rather than deleting them.
4. **Rate & vendor research.** A research capability that looks up current market rates or vendor options for a material/labour line and proposes a rate-card update or a vendor note — always with sources, always proposed rather than silently applied.
5. **Room-photo intake.** Upload a photo of a room; the agent proposes plausible tasks/quantities (e.g., "wall area ≈ 140 sqft, tiling likely needed") as drafts, using the existing templates and rate card as the source of truth for costing.
6. **Schedule what-if / explainability.** "What if we don't run stages in order?", "why does painting start on the 14th?" — the agent answers by re-running the deterministic engine (§4.4) and explaining the cascade/dependency/fixed-start reasons for a date, never guessing dates itself.
7. **Procurement assistant.** Flags overdue/upcoming need-by materials, and can draft (not send) a vendor inquiry message for a material line.
8. **Progress narration.** On request (or on a cadence), a short "what's happening this week" or "here's the variance so far" summary, sourced from the Schedule/Track tabs.
9. **Conflict & risk detection.** Circular-dependency attempts, deleting a room/rate/stage/phase still in use, or importing a workbook that would replace the current plan are all surfaced as an explicit confirmation step (human-in-the-loop, §4.8) — mirroring the static app's existing confirmation modals, not bypassing them.
10. **Session memory.** The agent remembers durable preferences across sessions ("always keep a 15% contingency", "prefers pushing to a later phase over deleting") without needing to be told twice.

### 3.3 Feature → capability mapping

| feature.md area | Static behavior | Agentic addition |
|---|---|---|
| Setup (§3) | Manual rooms/rates/phases/stages tables | Agent can add/rename/reorder via chat; still routes through the same validation (e.g. "can't delete a room in use") |
| Tasks (§4) | Manual form / template picker | NL task creation, bulk NL edits, photo intake |
| Schedule (§5) | Three read-only computed views | NL "what-if" queries answered by re-running the same engine |
| Materials (§6) | Manual buy-status updates | Proactive overdue alerts, draft vendor messages |
| Estimate (§7) | Read-only breakdown | Proactive budget-overrun coaching |
| Track (§8) | Manual status/actuals entry | NL status updates ("tiling is done, came in ₹4,000 over"), variance narration |
| Excel (§9) | Manual export/import buttons | Same workbook, callable as a tool; agent can also read an imported workbook to answer questions |

---

## 4. Technical approach

### 4.1 Why Deep Agents

[`deepagents`](https://github.com/langchain-ai/deepagents) (LangChain's "batteries-included agent harness," built on LangGraph) provides exactly the three primitives this problem needs, out of the box, instead of hand-rolling them:

- **Planning tool** (`TodoListMiddleware` → `write_todos`): lets the orchestrator break "plan my kitchen renovation" into tracked steps (draft tasks → cost them → check budget → propose schedule) instead of doing it in one opaque shot.
- **Virtual filesystem** (`FilesystemMiddleware`, pluggable backends — in-memory, LangGraph store, or real disk): a natural home for scratch artifacts that shouldn't pollute the committed plan yet — draft task lists, vendor-email drafts, research notes — plus durable memory via `AGENTS.md`-style files.
- **Sub-agents** (`SubAgentMiddleware` → `task` tool): lets specialist sub-agents (scheduling, procurement, budget, research) run with their own system prompt/tools/model and report back a single result, keeping the main conversation's context small.

Because it's built on LangGraph, it also gets durable execution, streaming, checkpointing, and human-in-the-loop interrupts for free (`interrupt_on=` on `create_deep_agent`) — which is exactly the mechanism needed to reproduce the static app's confirmation modals (delete-in-use, replace-plan-on-import, etc.).

Everything **numeric or date-bearing must not be produced by the LLM**. The agent's job is to decide *which tool to call with which arguments*; the tools do the actual cost/date/variance math, ported 1:1 from the reference implementation.

### 4.2 High-level architecture

```
┌─────────────────────────────┐        ┌───────────────────────────────────────────┐
│ Frontend (browser)          │  HTTP/ │ Backend (FastAPI)                          │
│ - existing tab UI (Setup,   │  SSE   │  ┌───────────────────────────────────────┐ │
│   Tasks, Schedule, Materials,│<------>│  │ Deep Agent (create_deep_agent)       │ │
│   Estimate, Track)          │        │  │  - orchestrator + write_todos          │ │
│ - NEW: chat dock            │        │  │  - subagents: Intake, Scheduling,      │ │
│                             │        │  │    Procurement, Budget, Tracking,      │ │
│                             │        │  │    Research                            │ │
└─────────────────────────────┘        │  └───────────────────────────────────────┘ │
                                        │  ┌───────────────────────────────────────┐ │
                                        │  │ Tool layer (plain Python, unit-tested)│ │
                                        │  │  - CRUD tools (rooms/rates/phases/     │ │
                                        │  │    stages/tasks/dependencies)          │ │
                                        │  │  - deterministic engine (§4.4)         │ │
                                        │  │  - excel import/export (openpyxl)      │ │
                                        │  │  - web research tools                 │ │
                                        │  └───────────────────────────────────────┘ │
                                        │  ┌───────────────────────────────────────┐ │
                                        │  │ Plan store (Pydantic schema, §4.3)    │ │
                                        │  │ + LangGraph checkpointer/store         │ │
                                        │  │ (Postgres/SQLite) — one thread/project │ │
                                        │  └───────────────────────────────────────┘ │
                                        └───────────────────────────────────────────┘
```

The plan document is the single source of truth. Both the chat and the tab UI read/write it through the same tool layer — the UI never talks to the LLM directly, and the LLM never talks to the browser directly.

### 4.3 Domain data model (ported 1:1 from the reference app)

The static app's `state` object (`Renovation_Planner_v2.html`) becomes a Pydantic schema:

```
ProjectSettings: project_start (date), work_weekends (bool), sequence_stages (bool)
Room:  id, label
Rate:  key, label, unit, value
Phase: id, label                      # order in list = priority order
Stage: id, label                      # order in list = trade sequence
TaskLine:
  id, task_id, room, name, category, line_type (Material|Labor|None),
  worker_type, phase, stage_id, mandatory, duration_days, start_override,
  depends_on: [line_id], cost_method (rate|flat), rate_key, qty, custom_amount,
  buy_status (To buy|Ordered|Delivered), status (Not Started|In Progress|On Hold|Done),
  notes, actual_cost
Plan: settings, rooms, rates, phases, stages, items: [TaskLine]
```

A **Task** (what the UI shows as one row) is a derived grouping of 1–2 `TaskLine`s sharing a `task_id` — exactly the split Material+Labour behavior in feature.md §1/§4. This grouping, not the raw line list, is what schedule/estimate/materials views are computed over — matching `groupByTask()` in the reference implementation.

### 4.4 Deterministic core stays deterministic

Port these functions from JS to Python **verbatim in logic**, not "as an LLM approximation":

- `computeSchedule()` — forward pass: project start → stage cascade (if `sequence_stages`) → dependency finishes → `start_override` pin → working-day duration (skipping weekends unless `work_weekends`) → end date.
- `wouldCreateCycle()` — dependency cycle guard, must reject before save, same as the modal in feature.md §4.1.
- `suggestedOrder()` — dependency-aware, stage-ordered topological sort.
- Cost helpers — `item_cost` (rate×qty or flat amount), `grand_total`, and the by-room/by-trade/by-phase/mandatory-optional/materials breakdowns for Estimate.
- Materials grouping — by ISO week of the computed need-by date, with overdue detection.
- Track variance — actual − estimate, only surfaced once ≥1 actual is logged (same "stays meaningful" rule as feature.md §8).

**Validation:** before writing new Python logic from scratch, generate a handful of representative plans in the actual HTML app, export them to `.xlsx`, and use those as golden fixtures — the Python engine's schedule/estimate/materials output must match the exported workbook exactly. This is the single highest-value test suite in the whole project, because every other feature depends on trusting these numbers.

### 4.5 Tool catalog

All tools are plain, typed, unit-testable Python functions operating on the `Plan`, then registered with the agent via `tools=` (or attached per-subagent).

**Mutating (CRUD) tools** — one per entity, mirroring Setup/Tasks tab actions:
`add_room`, `rename_room`, `delete_room`, `add_rate`, `update_rate`, `delete_rate`, `add_phase`, `reorder_phase`, `rename_phase`, `delete_phase`, `add_stage`, `reorder_stage`, `rename_stage`, `delete_stage`, `create_task` (supports template + split), `update_task`, `delete_task`, `bulk_update_tasks` (phase/stage/mandatory in bulk), `set_dependencies`, `set_project_settings`.

Each mutating tool re-runs the same guards the UI has today: can't delete a room/rate/stage/phase in use without confirmation (routed through `interrupt_on`, §4.8); can't save a dependency that creates a cycle.

**Read/derived tools** (always recomputed, never cached across a mutation):
`get_schedule` (timeline/agenda/board + suggested order), `get_materials_plan`, `get_estimate_summary`, `get_track_summary`.

**I/O tools:**
`export_plan_to_excel`, `import_plan_from_excel` (includes the legacy trade-batch migration from feature.md §9; replacing the current plan is an `interrupt_on` action).

**Template tool:**
`list_templates`, `instantiate_template(template_id, room, qty, ...)` — the 10 jobs from feature.md §4.2.

**Research tools (new):**
`search_material_rate(material, location)`, `search_vendors(category, location)` — web search, returns candidate values **with sources**; these only ever *propose* a rate-card change, never apply one directly.

### 4.6 Sub-agent design

One orchestrator (holds `write_todos`, has the full CRUD/read tool set for simple direct asks) delegates focused, multi-step, or research-heavy work via the `task` tool to:

1. **Intake agent** — turns a freeform brief (and optional room photos) into a *draft* set of rooms/tasks using templates + rate card + research tools; writes the draft to the virtual filesystem for review, then proposes the exact `create_task`/`add_room` calls for the user to approve.
2. **Scheduling agent** — owns `get_schedule`; answers what-if questions, explains why a date landed where it did, helps resequence stages/dependencies.
3. **Procurement agent** — owns `get_materials_plan`; flags overdue/upcoming buys, drafts (never sends) vendor messages.
4. **Budget agent** — owns `get_estimate_summary`; watches for overrun and proposes phase pushes.
5. **Tracking agent** — owns `get_track_summary`/status updates during the build; narrates progress and variance.
6. **Research agent** — wraps the web-search tools; always returns sourced findings, never a bare number without a citation.

Each is defined via `subagents=[...]` on `create_deep_agent`, with its own `system_prompt`, restricted `tools`, and (optionally) a cheaper/faster `model` where deep reasoning isn't needed (e.g., Research or Procurement). **Decided:** all six run on `subagents.py::SUBAGENT_MODEL` (`anthropic:claude-haiku-4-5-20251001`) — every sub-agent's job is narrow tool orchestration over data the deterministic engine already computed, not open-ended reasoning, so only the main orchestrator (`orchestrator.py::DEFAULT_MODEL`, `claude-sonnet-4-5`) needs the full-capability model. Live-verified: delegating to `intake` on the cheaper model still correctly found and proposed the right template. Locked in by `tests/test_subagents.py::test_every_subagent_uses_the_cheaper_model`.

### 4.7 Backends, state & persistence

**Deployment model (decided):** the backend runs **locally** on the user's own machine (a FastAPI + `deepagents` process started alongside the browser UI, not a hosted multi-tenant service). The LLM itself is still called over the network via API key — only the app/backend/data stay local. Practical consequences:

- Single-tenant by design: no auth/multi-user layer needed for v1.
- **SQLite** (not Postgres) is the default store/checkpointer backend — no server process to run beyond the app's own.
- The LLM API key is supplied via a local `.env`/OS keychain, never checked into the repo or sent anywhere but the model provider.
- The "offline-first" property from the static app (feature.md line 5) is preserved for everything except the AI layer itself: the deterministic engine, the tab UI, and Excel import/export all continue to work with zero network access; only chat/research/photo-intake require the LLM API to be reachable. The UI should visibly distinguish "offline-capable" actions from "needs network" ones (e.g., disable/flag chat when the API key is missing or unreachable, same spirit as the static app's save-indicator honesty).
- Because it's local and single-user, the plan store can live in a simple local SQLite file (e.g. `~/.renovator/<project>.db`) — easy to back up alongside (or instead of) the Excel export.

- **Plan document** — persisted via a `StoreBackend` (LangGraph's durable store) backed by SQLite, keyed by project id, so a conversation can be resumed days later with full plan + chat history via the LangGraph checkpointer.
- **Virtual filesystem (in-memory/state-backed)** — scratch space for draft plans before commit, vendor-message drafts, research notes, and `AGENTS.md`-style durable memory of user preferences (contingency %, "push don't delete," etc.).
- **Real filesystem backend** — only needed at the export boundary (writing the generated `.xlsx` to a temp path before it's returned to the client); not used for plan state.
- Every mutating tool call appends a lightweight changelog entry (`what changed, by whom/what, when`) to the plan document, giving basic audit/undo history the static app never had.

### 4.8 Human-in-the-loop & guardrails

`interrupt_on` is configured for every action that already has a confirmation modal in the static app, plus a few new ones introduced by giving an LLM write access:

- Delete room/rate/phase/stage while still in use.
- Bulk delete of multiple tasks.
- `import_plan_from_excel` (replaces the whole plan — the static app already warns and suggests exporting first).
- Applying a research-suggested rate-card change.
- Anything that would send an external message (out of scope for v1 — vendor messages are drafted, never sent, until a "send" capability is explicitly designed and approved).

Additional guardrails: sanitize/segregate any fetched web content before it re-enters the agent's context (basic prompt-injection hygiene, since rate/vendor pages are untrusted input), and treat the budget figure as a soft target the Budget agent nudges toward, never a hard constraint it silently enforces by deleting work.

### 4.9 Memory

Durable, cross-session preferences (contingency buffer, "prefer phase-push over delete," preferred vendors) are stored as agent memory (backed by the same store as the virtual filesystem) and loaded into the system prompt at session start — this is what lets the agent "not need to be told twice," matching how project/feedback memories work in this environment generally.

### 4.10 Frontend — full rebuild, HTML is reference-only

**Decided:** `Renovation_Planner_v2.html` is not reused live, in whole or in part (no embedding it, no lifting its render functions verbatim, no swapping its state source and calling it done). It is *reference material only* — the source of truth for what every tab, control, and interaction must do (feature.md, and the HTML itself when a behavioral detail isn't fully captured in feature.md). The real frontend is a new application, built from scratch against the FastAPI backend and the `Plan` schema in §4.3.

**Stack (decided):** React + TypeScript + Vite, as a SPA talking to the FastAPI backend purely over the REST/SSE API from §4.5/§4.10 — no server-rendered coupling to the backend process. Lives in a new top-level `frontend/` directory alongside `backend/`.

The new frontend has to serve **two usage modes on one codebase**, not two separate apps:

- **Non-agentic mode** — the direct-manipulation experience feature.md describes: Setup/Tasks/Schedule/Materials/Estimate/Track tabs, the task editor modal, template picker, bulk actions, Gantt/agenda/board views, drag-and-drop. Every interaction in feature.md §3–§8 must have a direct equivalent here, usable with the LLM/chat entirely absent (no API key configured, no network to the model).
- **Agentic mode** — the same tabs/canvas, plus a chat surface wired to `POST /projects/{id}/chat`. Agent tool calls mutate the same `Plan` the canvas renders; the canvas live-updates via the SSE/WebSocket stream in point 3 below. A user can freely mix the two — edit a task by hand, then ask the agent to reschedule around it.

Both modes read/write the exact same `Plan` via the exact same REST endpoints — the chat is an *additional* way to call the tool layer from §4.5, never a parallel code path with its own mutation logic. This is what keeps the two modes consistent by construction instead of by discipline.

Build sequence:

1. Stand up the FastAPI backend exposing `GET/PUT /projects/{id}/plan`, `POST /projects/{id}/chat` (streamed), `GET /projects/{id}/export.xlsx`, `POST /projects/{id}/import`, plus the direct CRUD endpoints the non-agentic UI needs (one per tool in `tools/crud_tools.py` — the UI calls the same tool layer the agent does, just without an LLM in between).
2. Build the non-agentic canvas first (new codebase, framework TBD — a decision point, see below) covering every tab in feature.md §3–§8, driven entirely by the REST endpoints. This alone is a complete, usable, non-agentic app and the natural place to verify the Phase 1 engine end-to-end against real interaction, not just fixtures.
3. Add the chat surface + SSE/WebSocket plan-change stream. No canvas rendering logic changes — it already re-renders from `Plan` state; the stream just tells it *when* to re-fetch/re-render.
4. Excel export/import gets a UI entry point wired to the same endpoints as the sidebar buttons did in the reference app.

The reference HTML's Gantt/agenda/board *interaction design* (what a drag does, what a click opens, how weekends/today are marked) should be mined for behavioral fidelity while building step 2 — but the implementation is new, in the chosen frontend framework, not lifted DOM/JS.

### 4.11 Excel import/export & backward compatibility

Reuse the exact 9-sheet layout from feature.md §9 (Project, Rate Card, Phases, Stages, Rooms & Items, Schedule, Materials, Suggested Order, Estimate Summary, Track), implemented server-side with `openpyxl`. Port the legacy-format detection/migration described in feature.md §9 (old combined phase+trade-batch columns → rebuilt stages, default phases from the mandatory flag, back-filled durations) so existing exported workbooks from the static app remain importable without any user-visible loss.

### 4.12 Observability & evals

- Tracing (e.g., LangSmith) on every tool call and sub-agent delegation, since correctness of dates/costs is safety-critical to user trust.
- A golden **conversation eval suite** derived directly from the "Suggested workflows" in feature.md §11 (start from example, template-heavy entry, get-the-sequence-right, managing the budget, on-site tracking) — each becomes a scripted multi-turn test asserting the resulting `Plan` JSON matches expectations.
- The scheduling-engine golden-fixture tests from §4.4 run in CI as a hard gate — no PR may change engine output on existing fixtures without an explicit, reviewed reason.

---

## 5. Step-by-step implementation plan

**Phase 0 — Foundations** ✅ done
Repo layout (`backend/`), Python 3.12 via `uv`, dependencies (FastAPI, `deepagents`/LangGraph, Pydantic v2, `openpyxl`). `Plan` Pydantic schema 1:1 with the reference app's `state` shape. `Renovation_Planner_v2.html` stays at repo root as reference material only — never embedded in or extended by the live app.

**Phase 1 — Port the deterministic core** ✅ done
Ported `computeSchedule`, `groupByTask`, cost helpers, `wouldCreateCycle`, `suggestedOrder`, and materials/estimate/track aggregations to Python (`src/renovator/engine/`). Validated against golden fixtures generated by running the reference app's own JS under Node (`backend/scripts/generate_golden_fixture.js`) — no browser needed, no hand-transcription. Excel export/import (with legacy-format migration) is still a stub, deferred to the tool layer below since it's naturally exposed as an `io_tools` tool rather than tested in isolation.

**Phase 2 — Tool layer** ✅ done
CRUD tools for rooms/rates/phases/stages/tasks/dependencies/settings (`tools/crud_tools.py`), read tools for schedule/materials/estimate/track (`tools/read_tools.py`), the 10 template jobs (`tools/template_tools.py`), and Excel export/import (`io/excel_export.py`, `io/excel_import.py`, wrapped in `tools/io_tools.py`) — all plain, typed, unit-tested Python functions, no LLM involved. Established the `ValidationError` (hard reject) vs. `ConfirmationRequired` (needs `confirm=True`, matching the reference app's `confirm()` dialogs) contract in `tools/errors.py`, which is what Phase 3/4's `interrupt_on` wiring will hook into. Excel round-trip verified against the golden fixture plan (rooms/phases/stages/items/costs/schedule all preserved). This tool layer is also what the non-agentic UI in Phase 6 will call directly.

**Phase 3 — Single Deep Agent MVP** ✅ done
`create_deep_agent()` (`agents/orchestrator.py`) with every Phase 2 tool wrapped as a LangChain tool (`agents/tool_bindings.py`, bound to one in-memory `PlanSession`), `TodoListMiddleware` for planning, and `interrupt_on` gating the destructive tools (`delete_task`, `bulk_delete_tasks`, `remove_room`, `delete_rate`, `remove_phase`, `remove_stage`, `import_plan_from_excel`) via `HumanInTheLoopMiddleware`. System prompt (`agents/prompts.py`) distilled from feature.md §1/§11. Validated two ways: structural tests with no live model call (`tests/test_orchestrator.py`), and a real scripted conversation against the Anthropic API (multi-step plan creation via templates, schedule/estimate reads, and a genuine interrupt-pause-approve-resume cycle on `delete_task`) — all worked correctly. A manual CLI (`uv run python -m renovator.cli`) is available for further hand-testing.

**Phase 4 — Sub-agents & orchestration** ✅ done
`subagents=[intake, scheduling, procurement, budget, tracking, research]` (`agents/subagents.py`), each with a deliberately narrow tool subset (built via a `_by_name` filter over the main tool list), its own system prompt, and — by construction — none of the `interrupt_on`-gated destructive tools; only the main orchestrator can delete/import. The Research sub-agent (`tools/research_tools.py`) wraps the Tavily search API for material-rate/vendor lookups, always returning sourced results with URLs; `TAVILY_API_KEY` is optional — its absence degrades to an `{"error": ...}` response rather than failing the run. Validated with structural tests (`tests/test_subagents.py`) and a real scripted conversation against the Anthropic API: delegating to `research` produced properly sourced, cited findings, and delegating to `scheduling` produced a technically correct explanation of the stage-cascade behavior (matching the actual engine logic — empty earlier stages are treated as already complete) rather than a plausible-sounding guess.

**Phase 5 — Persistence & multi-project** ✅ done
`PlanStore` (`store/plan_store.py`) — one SQLite file per project id under `RENOVATOR_DATA_DIR` (default `~/.renovator`), holding the latest `Plan` snapshot plus a changelog table (what mutated it, when). A separate `SqliteSaver` checkpointer file per project (`agents/orchestrator.py::build_checkpointer`) persists the LangGraph conversation/interrupt state. `PlanSession` (`agents/session.py`) now takes an optional `project_id`: with one, every mutating tool call in `tool_bindings.py` calls `session.persist(action, detail)` after success (never before, so a rejected call never half-persists); without one, it's the original ephemeral in-memory session (tests, one-off scripts) and `persist()` is a no-op. Validated with unit tests (`tests/test_plan_store.py`, `tests/test_session.py`, checkpointer-selection tests in `tests/test_orchestrator.py`) and — the real correctness claim — a scripted conversation against the Anthropic API where a **brand-new** `PlanSession`/orchestrator instance (simulating a process restart) correctly recalled details from turn 1 ("Sunshine Reno", a ₹5,00,000 budget ceiling) that exist only in resumed conversation history, not in the Plan data itself.

**Phase 6 — Non-agentic frontend (full rebuild)** ✅ done
Stack: React + TypeScript + Vite in a new top-level `frontend/`, talking to the backend purely over REST (`src/api/client.ts`/`types.ts`, kept snake_case to match the wire format 1:1, no mapping layer). Backend routes (`api/routes.py`): full reads for every tab, the complete Setup-tab mutation set, task mutations (create/update/delete, bulk mandatory/phase/stage/delete, `/templates` + `/tasks/from-template`, `/suggested-order`, `/tasks/move-to-stage`), Excel export/import (`/export.xlsx`, `/import`), and a lightweight `PATCH /lines/{line_id}` for one-field inline edits (`update_line` in `crud_tools.py` — added because routing Materials/Track's single-field edits through the full `update_task` would mean resending the whole task just to flip a buy-status) — all with the `ValidationError`(400)/`ConfirmationRequired`(409) contract carried through to HTTP status codes, verified with `tests/test_api_routes.py` (32 tests).

**Every tab from feature.md §3-§9 is fully wired**, direct-manipulation only, no LLM involved: Setup (rooms/rates/phases/stages/settings, confirm-before-delete); Tasks (add/edit/delete via `TaskEditor.tsx` — single or split Material+Labor, dependency checklist per feature.md §4.1's "material lines don't show this" rule — plus the template picker and bulk-select bar for mandatory/phase/stage/delete, feature.md §4.2-§4.3); Excel export/import from the sidebar rail; Materials (inline buy-status + vendor-note editing) and Track (inline status + actual-cost editing, split-task expand-to-per-line) via `update_line`; Schedule — all three views from feature.md §5.1-§5.3 (Timeline/Gantt, By-date/agenda, Board/kanban with drag-to-reassign-stage and drag-to-reorder-stages), sharing one trade-color classifier (`trade.ts`, a direct TS port of the reference app's `tradeBucket()`) across bars/badges/card-borders/legend. One known simplification: Board's cards omit the "after: X" dependency note the reference app shows, since that needs per-line `depends_on` data the Schedule views' task-level rows don't carry — dependency *editing* itself is fully wired in the task editor, just not surfaced as a read-only hint on Board cards.

**Project management UI & cross-project transfer** ✅ done
Two new backend primitives, both built independent of `Plan`/`PlanStore`: `store/project_registry.py` — a JSON file at `~/.renovator/projects.json` listing every project (id/name/created_at/updated_at), with list/create/rename/delete; `create_project` slugifies the name into a stable id (deduped with a short uuid suffix on collision) and immediately materializes an empty plan so the project isn't registry-only. Pre-existing project files (`default`, or anything created before this registry existed) are auto-bootstrapped into the registry — with `name == id` — the first time `list_projects()` runs, so nothing pre-dates the feature. And `tools/transfer_tools.py::transfer_tasks(source, target, task_ids, mode)` — copies or moves a set of tasks between two `Plan`s, reconciling rooms/rates/phases/stages by **label**, not id (same precedent as `io/excel_import.py`): if the target already has a room/rate/phase/stage with a matching label it's reused, otherwise a new one is created. Dependencies are re-linked only within the transferred set (an id map from old→new); a dependency pointing outside the set is dropped and counted in the result rather than causing a partial failure. `mode="move"` additionally strips the transferred lines (and now-dangling dependency references in what's left) out of the source. New routes on `api/routes.py`: `GET/POST /projects` (list/create), `PATCH/DELETE /projects/{id}` (rename/delete, delete needs `confirm=true` like every other destructive route), `POST /projects/{id}/tasks/transfer` (`task_ids`, `mode`, and either `target_project_id` or `new_project_name`). Covered by `tests/test_project_registry.py` (10), `tests/test_transfer_tools.py` (8), and `tests/test_project_management_api.py` (7) — full suite at 132 passed.

Frontend: `App.tsx` no longer hardcodes a `PROJECT_ID` — it fetches `GET /projects` on load, remembers the active project id in `localStorage`, and falls back to the first project (or a "no projects yet" empty state) if the remembered id no longer exists. A new shared `components/TransferMenu.tsx` renders the "Copy to project…"/"Move to project…" pair (every other project, plus a "New project…" entry that prompts for a name) and is reused in three places: the Tasks bulk-action bar (transfers the current selection), the single-task editor's footer (transfers just that task), and Setup's Phases card (transfers a whole phase's tasks, resolving the id set lazily via `getTasks()` filtered by `phase` at click time, since Setup doesn't otherwise load tasks). The Phases card needed a more compact trigger than `TransferMenu`'s two labeled buttons, so `components/Menu.tsx` grew a `variant="icon"` option (a plain icon-btn, no caret) — used there for a single "⇄" menu combining copy/move against every target into one dropdown.

**Projects as a tab, global defaults, and a real project-settings page** ✅ done
Superseding the first pass's inline Rail dropdown: `Rail.tsx` now lists **Projects** as an ordinary first tab, same as Setup/Tasks/etc. — there's no other way to switch projects anymore. `tabs/ProjectsTab.tsx` is what that tab shows: a "Global defaults" card (`work_weekends`/`sequence_stages` toggles plus a starter rate card) above a table of every project, each row expandable for its created/updated timestamps, with "Open" (makes it the active project and jumps to Tasks) and "✎ Edit" (opens the settings page) actions, plus a "+ New project" button. `components/ProjectEditor.tsx` is the "proper create/edit project page" this replaces window.prompt with — a `Modal`-based form for the name, project timing (moved out of Setup), and the rate card (also moved out of Setup — Setup now only has rooms/phases/stages, the truly structural building blocks with no global-default concept). Creating a project keeps the same modal open and flips it straight into edit mode for the just-created project, so the user can immediately adjust anything before moving on. Every other tab now renders a small read-only `components/TopBar.tsx` ("Project: X · Switch project") above its content, so the active project is always visible as context without it being editable from anywhere but Projects.

Backend: `store/global_settings.py` is the new org-wide default store — one JSON file (`global_settings.json`, same pattern as `project_registry.py`'s `projects.json`) holding `work_weekends`, `sequence_stages`, and a starter `rates` list, with `GET/PATCH /settings/global` and `POST/PATCH/DELETE /settings/global/rates/{key}` routes (`settings_router` in `api/routes.py`). Deliberately **seed-only, not live inheritance** (a real design choice, not a shortcut): `project_registry.create_project()` calls `global_settings.seed_plan(plan)` once, right after materializing the new project's empty plan, copying the current global values in; editing a global default afterward never touches a project that already exists, and a project's own settings (edited via the existing per-project routes) are fully independent from that point on. Covered by `tests/test_global_settings.py` (7 tests) plus seeding-specific cases added to `tests/test_project_registry.py` and `tests/test_project_management_api.py` — full suite at 142 passed.

Three things worth keeping in mind going forward:
- **No visual browser pass has happened on any of this.** A real bug already shipped once because of it — the first pass omitted `import "./App.css"` in `App.tsx`, silently dropping every style, and neither the build nor the API field-shape checks caught it (the user caught it visually). Build success + API contract checks are necessary, not sufficient. This applies with extra force to the Gantt/agenda/board views: drag-and-drop, absolute bar positioning, and sticky-column scrolling are exactly the class of bug no automated check in this environment can catch.
- **The `default` project is the user's real, hand-entered plan**, built by using the Tasks tab as it was completed — not a fixture. Verification from here on uses a disposable scratch project id, never `default`.
- A caught-in-review bug during this phase: `update_line`'s enum fields (`buy_status`, `status`) need explicit coercion (`BuyStatus(value)`) when assigning to an already-constructed `TaskLine` — direct attribute assignment skips Pydantic's validation, unlike constructing a fresh object. The API-level test alone missed this (the JSON round-trip through `Plan.model_validate_json` on reload silently "fixed" the type on the way back out); the direct unit test on `crud_tools.update_line` caught it. Worth remembering for any future partial-update helper that mutates fields in place.

**Phase 7 — Agentic chat integration** ✅ done
`agents/chat_stream.py::stream_turn(session, thread_id, step_input)` turns one agent turn into a sequence of small SSE-framed JSON events, using `graph.stream(step_input, config, stream_mode="values")` — the full accumulated state after every super-step — rather than depending on deepagents' internal node names (they vary with middleware and aren't a public contract). Each newly-seen `messages` entry becomes one event (`tool_call`, `tool_result`, or the final `message`); a snapshot carrying `__interrupt__` (the same key `graph.invoke()` returns on a gated tool call, per `cli.py`) ends the turn early with an `interrupt` event (the action name/args/description, for the UI to render an approve/reject prompt) instead of `done`. A real bug caught only by a live scripted run against the Anthropic API (structural tests with a fake graph didn't catch it, because they don't span multiple turns on one thread): `stream_mode="values"` re-yields the *entire* accumulated message list every turn, so a second `stream_turn()` call — starting its own new-message counter at 0 — was re-emitting the whole prior conversation as brand-new events. Fixed by seeding that counter from `graph.get_state(config).values["messages"]` (how many messages the checkpointer already has for this thread) before the loop starts; re-verified live afterward, turn-by-turn, that no turn ever re-emits an earlier one's events. `POST /projects/{id}/chat` (`api/routes.py`) accepts either `{"message": str}` (a new user turn) or `{"resume": {"decisions": [...]}}` (approve/reject after an `interrupt` event, same shape `cli.py`'s `Command(resume=...)` already used) and streams `stream_turn`'s output back as `text/event-stream`; a fresh `PlanSession`/orchestrator is built per request, but the LangGraph checkpointer and `PlanStore` are both keyed by `project_id`, so conversation and plan state both resume correctly across requests without an in-memory session.

The plan-change stream is `GET /projects/{id}/plan-events` — deliberately simple: `PlanStore.last_updated_at()` reads just the one timestamp column, and a `StreamingResponse` generator polls it once a second, yielding a `changed` event whenever it moves. No pub/sub layer needed for a local single-user app; this is what tells the canvas *when* to re-fetch; it never carries the data itself. Frontend: `api/client.ts::streamChat` parses the SSE body from a `fetch()` `POST` by hand (the standard `EventSource` only supports `GET`); `subscribePlanEvents` uses a real `EventSource` against the `GET` stream. `components/ChatPanel.tsx` is the dock (a floating 💬 toggle when collapsed) — a plain client-side transcript of every event, with Approve/Reject buttons on an `interrupt` item that resume the same thread. `App.tsx` holds one `planVersion` counter, bumped on every `changed` event, threaded into every tab's `useFetch` deps alongside `projectId` — so a tab re-fetches on an externally-sourced change (chat, or in principle another browser tab) without losing its own local UI state (open modals, row selection), and `TasksTab`'s local optimistic-update override is cleared on exactly that signal (adjusted during render, React's documented pattern for "reset state when a prop changes," not in an effect). The two simplifications this phase originally shipped with — client-side-only transcript, no recovery from a reload mid-interrupt — turned out to be one fix: `chat_stream.py::history_events(session, thread_id)` reads `graph.get_state(config)` for the thread and replays `.values["messages"]` through the same `_message_event()` conversion `stream_turn` already uses (now also handling `HumanMessage`, for the user's own turns), plus a trailing `interrupt` event if `state.interrupts` is non-empty — `StateSnapshot.interrupts` is exactly the still-pending interrupt(s) for that thread, independent of whether a browser is currently connected. `GET /projects/{id}/chat/history` exposes it; `ChatPanel` replays it on mount before anything else. Since a still-open interrupt just shows up as the last replayed event, "recovering after a reload" needed no separate UI — the normal Approve/Reject card is already there. Verified live against the Anthropic API: history empty on a fresh thread, correctly ordered after a normal turn, and — the actual scenario — fetching history *without resuming* after hitting an interrupt still returns that interrupt as the last event, and approving from that recovered state actually deletes the task. Covered by `tests/test_chat_stream.py` (11 total now) and `tests/test_chat_api.py` (6).

**Phase 8 — Multimodal intake & guardrails** ✅ done
**Room-photo intake.** `POST /projects/{id}/chat` accepts an optional `image` (a `data:` URL, what a browser's `FileReader.readAsDataURL` produces) alongside `message`; `api/routes.py` parses it (`_parse_data_url`, with an 11M-char base64 cap — roughly 8MB decoded) and builds a standard multimodal `HumanMessage` content list (`{"type": "text", ...}` + `{"type": "image", "source_type": "base64", ...}`), verified against the real Anthropic API to actually reach the model (confirmed by asking it to name a synthetic test image's exact color). A real architectural finding from that same live testing, not something guessable from reading deepagents' docs: its `task` delegation tool only accepts a plain text `description` — a sub-agent never receives the original image, only whatever the *delegating* agent writes about it. So the design here is: the main agent (multimodal) looks at the photo itself and relays its own observations as text when it delegates to **intake**; intake works from that description, never the photo. `agents/chat_stream.py::_message_event` reflects this on the wire too — a multimodal `HumanMessage`'s content (a list of blocks) is reduced to just its text plus a `has_image` flag for the event the browser sees; the base64 payload is never echoed back down (the browser already has it, and `history_events` replay has no way to reconstruct it from the checkpointer's stored copy anyway — a real, disclosed simplification: a photo attached to an earlier turn shows only "📷 photo" on reload, not the image itself).

**Intake is draft-only by construction, not by prompt.** `subagents.py`'s intake now has exactly `get_setup`, `get_tasks`, `list_templates`, plus the research tools — no `add_room`/`create_task`/`instantiate_template`. It cannot apply its own proposal even if a crafted brief (or manipulated photo-derived text) told it to try; that's a property `tests/test_subagents.py::test_intake_subagent_is_draft_only_by_construction` checks directly (every intake tool name against a mutating-prefix list), not something that could regress silently via a prompt edit. Its system prompt now ends every report with a numbered list of exact rooms/tasks to create; the main agent shows that to the user and only calls `add_room`/`create_task` itself after they agree (prompt-level, same as any other conversational confirmation — the *code* guarantee is specifically that intake itself cannot mutate).

**`update_rate` is now `interrupt_on`-gated** (`tool_bindings.py::GATED_TOOL_NAMES`) — closing a real gap between what §4.8 always specified ("applying a research-suggested rate-card change" requires confirmation) and what Phase 3 actually gated (only deletes + import). Gating it needed no change to `crud_tools.update_rate` itself — `interrupt_on` pauses by tool *name* before the call happens, independent of whether the tool's own signature has a `confirm` param, and a tool call alone can't reliably tell "the model's own idea" apart from "a number a scraped web page suggested," so it's gated unconditionally. Live-verified: asking the agent to change a rate pauses on `interrupt` with the exact key/value, the rate is provably unchanged until approved, and correctly updates once it is.

**Prompt-injection hygiene on research results** (`tools/research_tools.py`): every snippet/title is capped at 500 chars and has triple-backtick fences (the cheapest delimiter-escape trick) neutralized before it enters the agent's context, and the whole result is wrapped with an explicit `untrusted_web_content: true` flag plus an instruction telling the model these are excerpts to read, not commands to follow. This is hygiene, not a guarantee — the actual backstop, as ever, is that every tool capable of real damage is either read-only or `interrupt_on`-gated, so even a fully successful injection still can't apply anything without a human approving it.

**No tool can send an external message** — true today because no such tool exists anywhere in the codebase, verified by `tests/test_guardrails.py`: a substring audit (`send`/`email`/`sms`/`webhook`/etc. against every tool name) plus an explicit allowlist of the full current tool set, so any future addition has to pass through both checks deliberately rather than slipping in unnoticed. Covered by `tests/test_research_tools.py` (+2), `tests/test_subagents.py` (+1), `tests/test_orchestrator.py` (+1), `tests/test_chat_stream.py` (+3, multimodal `HumanMessage` handling), `tests/test_chat_api.py` (+4, the image/size-cap path), and the new `tests/test_guardrails.py` (2) — full suite at 168 passed.

**Phase 9 — Evaluation & hardening** ✅ done
**Repo + CI, from scratch.** This project had no version control at all before this phase — `git init`, a root `.gitignore` (both `.env` files, `.venv`/`node_modules`/`dist`, and a stray local `Home_Renovation_Plan (2).xlsx` export that looked like it could carry real personal data), and pushed to `github.com/nishant-gupta/renovator`. `.github/workflows/ci.yml` runs on every push/PR to `main`: a backend job (`uv run pytest -q` + `ruff check`, no live model calls) and a frontend job (`tsc -b`, `npm run build`, `npm run lint`) — this is the "keep the scheduling-engine fixture tests as a CI gate" ask, now literal instead of aspirational. `scripts/ci-check.sh` mirrors both jobs locally. Verified green on the very first real push.

**Golden conversation-eval suite** (`backend/scripts/eval_conversations.py`) — five scripted multi-turn conversations against the real Anthropic API, one per feature.md §11 workflow (starting a plan, templates + bulk actions, sequencing via dependencies, budget triage via phase-push not delete, on-site tracking). Assertions check structural outcomes (the right rooms/tasks/phases/dependencies/status actually landed), not exact wording, since phrasing varies run to run. A real bug surfaced on the first run and was fixed before commit: the script assumed `POST /tasks/from-template`'s response was `[the new task]`, but every task-mutation route actually returns the *full* task list (`routes.py`'s `_mutate` + `get_tasks`) — same shape the frontend has always correctly handled, just a wrong assumption in the new eval script itself, not a product bug. Costs real API calls, so it's a manual script plus an optional `workflow_dispatch`-only Actions workflow (`.github/workflows/eval.yml`), not part of the default CI. Passed consistently across two full runs.

**LangSmith tracing** — `.env.example` documents `LANGSMITH_TRACING`/`LANGSMITH_API_KEY`/`LANGSMITH_PROJECT`; LangChain reads these itself, so enabling tracing needs no code change. No account was available to verify actual trace capture in this session — that's on whoever adds a real key.

**Local cost/latency dashboard** — since LangSmith couldn't be verified end-to-end, a second, fully self-verifiable path: every `/chat` turn now emits a `usage` event (input/output tokens, wall-clock duration, a rough estimated cost from `agents/pricing.py`'s public list prices) and persists it to a new `usage_log` table (`store/plan_store.py`); `GET /projects/{id}/usage` aggregates it, and `ChatPanel`'s header shows a running cumulative token count. A real, load-bearing limitation was found live rather than assumed: a delegated sub-agent call (`task` tool, `subagents.py::SUBAGENT_MODEL`) runs as its own nested sub-graph — its internal `AIMessage`s (and their `usage_metadata`) never appear in the parent thread's top-level `messages` state, only the tool's final result does. So this dashboard currently undercounts turns that delegate — it only ever captured the main agent's own token usage in testing, confirmed by checking `by_model` after a turn that visibly delegated to `intake`. Documented rather than fixed: capturing sub-agent usage would need `stream_mode`'s `subgraphs=True` (a real refactor of the streaming loop, with its own per-namespace "already seen" tracking), out of scope for what's meant to be a basic dashboard — LangSmith tracing does see sub-agent calls, once configured.

**Phase 10 — Packaging**
Local-run packaging (script/installer to launch backend + frontend together), key entry UX (first-run prompt vs. `.env`), and a migration path for anyone with an exported `.xlsx` from the reference app to import into a new project.

---

## 6. Risks & open questions

- **Deployment model — decided.** Backend runs locally (§4.7); LLM API key supplied and used locally, only the model call itself leaves the machine. No hosting/multi-tenant concerns for v1.
- **Model/provider choice and per-session cost**, especially for the Research and Intake agents, which can be long-running. Since the key is user-supplied, surface running cost/usage somewhere visible (mirrors the static app's save-indicator transparency) rather than letting spend be a surprise.
- **Data handling for room photos** — stays local with everything else, but photos sent to a multimodal model still leave the machine as part of that call; worth a one-line disclosure to the user the first time it happens.
- **Multi-user/collab** — the static app is explicitly single-user/export-to-share (feature.md §12); local single-tenant deployment keeps this unchanged, so no action needed unless requirements change.
- **"Send" actions** (vendor emails, calendar invites) are explicitly out of scope for v1 (draft-only) — flag if the user wants this sooner, since it changes the guardrail design meaningfully.
- **Key management UX** — since there's no hosting layer to hold secrets centrally, decide how the key is entered/stored on first run (`.env` file the user edits vs. a simple in-app settings field that writes to a local config file/OS keychain).

---

## 7. Appendix — feature.md → implementation mapping

| feature.md section | Ported as |
|---|---|
| §1 Mental model | `Plan` Pydantic schema (§4.3) |
| §3 Setup | CRUD tools for rooms/rates/phases/stages (§4.5) |
| §4 Tasks + editor + templates + bulk | `create_task`/`update_task`/`bulk_update_tasks`, `list_templates`/`instantiate_template` |
| §5 Schedule (3 views) | `computeSchedule` port + `get_schedule` tool (§4.4, §4.5), owned by the Scheduling sub-agent |
| §6 Materials | `get_materials_plan` tool, owned by the Procurement sub-agent |
| §7 Estimate | `get_estimate_summary` tool, owned by the Budget sub-agent |
| §8 Track | `get_track_summary` tool, owned by the Tracking sub-agent |
| §9 Excel + legacy import | `export_plan_to_excel`/`import_plan_from_excel` (§4.11) |
| §10 Scheduling algorithm | Golden-fixture-tested Python port (§4.4) |
| §11 Suggested workflows | Source material for the golden conversation eval suite (§4.12) |
