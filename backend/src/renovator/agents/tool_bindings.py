"""Wraps the plain-Python tool layer (renovator.tools.*) as LangChain tools
bound to one PlanSession, for use with deepagents' create_deep_agent.

Three conventions used throughout:

- Every wrapped tool returns either its natural success payload, or
  `{"error": "<message>"}` on `ValidationError` — never raises — so the
  model sees the failure in the ToolMessage and can self-correct instead of
  crashing the run.
- "Gated" tools (delete_task, bulk_delete_tasks, remove_room, delete_rate,
  remove_phase, remove_stage, import_plan_from_excel, update_rate) never
  expose a `confirm` parameter to the model. Confirmation is handled once,
  up front, by `HumanInTheLoopMiddleware` via `interrupt_on` (see
  orchestrator.py) — by the time a gated tool actually runs, the human has
  already approved the call, so the wrapper always passes `confirm=True`
  where the underlying function accepts one. The underlying function's own
  hard-block rules (e.g. "you need at least one phase") still apply
  regardless and surface as an error. `update_rate` is gated even though
  its underlying function has no `confirm` param at all (a price change
  was never destructive enough to need one before an LLM could call it) —
  `interrupt_on` pauses by tool *name*, before the call happens, so gating
  it needed no change to crud_tools.update_rate itself. This is also the
  guardrail for a research-suggested rate-card change (design doc §4.8) —
  applying one always requires confirmation, unconditionally, since a tool
  call alone can't reliably tell "the model's own idea" apart from "a
  number a scraped web page suggested."
- Every successful mutation calls `session.persist(...)` (§4.7) — a no-op
  for a non-persistent session (no project_id), a real save + changelog
  entry otherwise. This happens after the mutation, never before, so a
  rejected/erroring call never persists a half-applied change.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import BaseTool, tool

from renovator.agents.session import PlanSession
from renovator.tools import crud_tools as ct
from renovator.tools import io_tools as iot
from renovator.tools import read_tools as rt
from renovator.tools import research_tools as res
from renovator.tools import template_tools as tt
from renovator.tools.errors import ValidationError

# Tool names that must be routed through interrupt_on in orchestrator.py.
# Kept here, next to the wrappers, so the two stay in sync.
GATED_TOOL_NAMES = [
    "delete_task",
    "bulk_delete_tasks",
    "remove_room",
    "delete_rate",
    "remove_phase",
    "remove_stage",
    "import_plan_from_excel",
    "update_rate",
]


def _err(e: ValidationError) -> dict:
    return {"error": str(e)}


def build_tools(session: PlanSession) -> list[BaseTool]:
    """Build the full tool set for one session's Plan. Called once per
    agent/session — closures capture `session`, not a copy of the plan, so
    every tool call sees the latest mutations from prior calls."""

    # ---- read tools -----------------------------------------------------

    @tool
    def get_setup() -> dict:
        """Get the project's rooms, rate card, phases, stages, and timing settings."""
        return rt.get_setup(session.plan)

    @tool
    def get_tasks() -> list[dict]:
        """List every task with its line ids, dependencies, and cost — call
        this before update_task/delete_task/set_dependencies to find the
        task_id and line ids to reference."""
        return rt.get_tasks(session.plan)

    @tool
    def get_schedule() -> dict:
        """Get the computed schedule: each task's start/end dates and the
        overall project span."""
        return rt.get_schedule(session.plan)

    @tool
    def get_suggested_order() -> list[dict]:
        """Get the dependency-aware, stage-ordered execution order of every line."""
        return rt.get_suggested_order(session.plan)

    @tool
    def get_materials_plan() -> dict:
        """Get the materials/procurement plan: what to buy, grouped by the
        week it's needed, with buy-status totals."""
        return rt.get_materials_plan(session.plan)

    @tool
    def get_estimate_summary() -> dict:
        """Get the cost estimate: totals, mandatory/optional/materials
        subtotals, by-room/by-trade/by-phase breakdowns, and a task table
        sorted by cost."""
        return rt.get_estimate_summary(session.plan)

    @tool
    def get_track_summary() -> dict:
        """Get build progress: percent done, estimated vs. actual spend, and
        variance (variance is null until at least one actual cost is logged)."""
        return rt.get_track_summary(session.plan)

    @tool
    def list_templates() -> list[dict]:
        """List the common renovation job templates available for
        instantiate_template (e.g. fresh paint, re-tile, flooring)."""
        return tt.list_templates()

    @tool
    def get_changelog(limit: int = 20) -> list[dict]:
        """Get the recent history of changes made to this plan (what, when)."""
        return session.changelog(limit=limit)

    # ---- setup mutations --------------------------------------------------

    @tool
    def add_room(name: str) -> dict:
        """Add a new room/area to the project."""
        try:
            ct.add_room(session.plan, name)
            session.persist("add_room", f"Added room '{name}'")
            return {"ok": True, "rooms": session.plan.rooms}
        except ValidationError as e:
            return _err(e)

    @tool
    def rename_room(old_name: str, new_name: str) -> dict:
        """Rename a room. Every task currently in that room moves with it."""
        try:
            ct.rename_room(session.plan, old_name, new_name)
            session.persist("rename_room", f"Renamed room '{old_name}' -> '{new_name}'")
            return {"ok": True, "rooms": session.plan.rooms}
        except ValidationError as e:
            return _err(e)

    @tool
    def remove_room(name: str) -> dict:
        """Remove a room. Blocked if any task still uses it — move or delete
        those tasks first. Requires human confirmation."""
        try:
            ct.remove_room(session.plan, name, confirm=True)
            session.persist("remove_room", f"Removed room '{name}'")
            return {"ok": True, "rooms": session.plan.rooms}
        except ValidationError as e:
            return _err(e)

    @tool
    def add_rate(label: str, unit: str, value: float) -> dict:
        """Add a new entry to the shared rate card (e.g. "Waterproofing", "sqft", 45)."""
        ct.add_rate(session.plan, label, unit, value)
        session.persist("add_rate", f"Added rate '{label}' ({unit}, {value})")
        return {"ok": True, "rates": [r.model_dump() for r in session.plan.rates]}

    @tool
    def update_rate(key: str, value: float) -> dict:
        """Update a rate card entry's price per unit. Every task costed by
        this rate re-costs automatically. Requires human confirmation."""
        try:
            ct.update_rate(session.plan, key, value)
            session.persist("update_rate", f"Set rate '{key}' to {value}")
            return {"ok": True}
        except ValidationError as e:
            return _err(e)

    @tool
    def delete_rate(key: str) -> dict:
        """Delete a rate card entry. If tasks use it, their cost drops to
        zero until re-costed. Requires human confirmation."""
        try:
            ct.delete_rate(session.plan, key, confirm=True)
            session.persist("delete_rate", f"Deleted rate '{key}'")
            return {"ok": True}
        except ValidationError as e:
            return _err(e)

    @tool
    def add_phase(label: str) -> dict:
        """Add a new phase (priority bucket, e.g. "Phase 4" or "Someday")."""
        try:
            ct.add_phase(session.plan, label)
            session.persist("add_phase", f"Added phase '{label}'")
            return {"ok": True, "phases": [p.model_dump() for p in session.plan.phases]}
        except ValidationError as e:
            return _err(e)

    @tool
    def rename_phase(phase_id: int, label: str) -> dict:
        """Rename a phase."""
        try:
            ct.rename_phase(session.plan, phase_id, label)
            session.persist("rename_phase", f"Renamed phase {phase_id} -> '{label}'")
            return {"ok": True}
        except ValidationError as e:
            return _err(e)

    @tool
    def remove_phase(phase_id: int) -> dict:
        """Remove a phase. Tasks in it move to a remaining phase. A plan
        must always keep at least one phase. Requires human confirmation."""
        try:
            ct.remove_phase(session.plan, phase_id, confirm=True)
            session.persist("remove_phase", f"Removed phase {phase_id}")
            return {"ok": True, "phases": [p.model_dump() for p in session.plan.phases]}
        except ValidationError as e:
            return _err(e)

    @tool
    def move_phase(index: int, direction: int) -> dict:
        """Reorder a phase up (direction=-1) or down (direction=1) by index
        in the current phase list (0-based). Order defines priority."""
        try:
            ct.move_phase(session.plan, index, direction)
            session.persist("move_phase", f"Moved phase at index {index} by {direction}")
            return {"ok": True, "phases": [p.model_dump() for p in session.plan.phases]}
        except ValidationError as e:
            return _err(e)

    @tool
    def add_stage(label: str) -> dict:
        """Add a new stage (trade-execution-order bucket, e.g. "Waterproofing")."""
        try:
            ct.add_stage(session.plan, label)
            session.persist("add_stage", f"Added stage '{label}'")
            return {"ok": True, "stages": [s.model_dump() for s in session.plan.stages]}
        except ValidationError as e:
            return _err(e)

    @tool
    def rename_stage(stage_id: int, label: str) -> dict:
        """Rename a stage."""
        try:
            ct.rename_stage(session.plan, stage_id, label)
            session.persist("rename_stage", f"Renamed stage {stage_id} -> '{label}'")
            return {"ok": True}
        except ValidationError as e:
            return _err(e)

    @tool
    def remove_stage(stage_id: int) -> dict:
        """Remove a stage. Tasks in it become unassigned (schedulable, no
        forced position). Requires human confirmation."""
        try:
            ct.remove_stage(session.plan, stage_id, confirm=True)
            session.persist("remove_stage", f"Removed stage {stage_id}")
            return {"ok": True, "stages": [s.model_dump() for s in session.plan.stages]}
        except ValidationError as e:
            return _err(e)

    @tool
    def move_stage(index: int, direction: int) -> dict:
        """Reorder a stage up (direction=-1) or down (direction=1) by index
        in the current stage list (0-based). Order defines on-site trade sequence."""
        try:
            ct.move_stage(session.plan, index, direction)
            session.persist("move_stage", f"Moved stage at index {index} by {direction}")
            return {"ok": True, "stages": [s.model_dump() for s in session.plan.stages]}
        except ValidationError as e:
            return _err(e)

    @tool
    def set_project_settings(
        project_start: str | None = None,
        weekend_policy: str | None = None,
        sequence_stages: bool | None = None,
    ) -> dict:
        """Update project timing: start date (YYYY-MM-DD), whether stages
        run in strict trade order, and weekend_policy — one of "none" (crew
        doesn't work weekends), "saturdays" (Saturday is a workday, Sunday
        isn't), or "all" (every day is a workday)."""
        try:
            ct.set_project_settings(
                session.plan,
                project_start=project_start,
                weekend_policy=weekend_policy,
                sequence_stages=sequence_stages,
            )
        except ValidationError as e:
            return _err(e)
        session.persist(
            "set_project_settings",
            f"start={project_start} weekend_policy={weekend_policy} sequence={sequence_stages}",
        )
        return {"ok": True}

    @tool
    def add_blocked_date(date: str) -> dict:
        """Mark one date (YYYY-MM-DD) as no-work-allowed — a holiday, a
        contractor's planned day off — regardless of weekday. Every task
        scheduled on or after that date shifts to skip it."""
        try:
            ct.add_blocked_date(session.plan, date)
        except ValidationError as e:
            return _err(e)
        session.persist("add_blocked_date", f"Blocked {date}")
        return {"ok": True}

    @tool
    def remove_blocked_date(date: str) -> dict:
        """Un-block a previously blocked date (YYYY-MM-DD)."""
        try:
            ct.remove_blocked_date(session.plan, date)
        except ValidationError as e:
            return _err(e)
        session.persist("remove_blocked_date", f"Unblocked {date}")
        return {"ok": True}

    # ---- task mutations -----------------------------------------------------

    @tool
    def create_task(task: ct.TaskInput) -> dict:
        """Create a new task. `task.task_id` must be left unset. Use
        structure="single" with `single` set, or structure="split" with both
        `material` and `labor` set. Costing per line is either
        cost_method="rate" with rate_key+qty, or cost_method="custom" with
        custom_amount."""
        try:
            ct.create_task(session.plan, task)
            session.persist("create_task", f"Created '{task.name}' in {task.room}")
            return {"ok": True, "tasks": rt.get_tasks(session.plan)}
        except ValidationError as e:
            return _err(e)

    @tool
    def update_task(task: ct.TaskInput) -> dict:
        """Update an existing task. `task.task_id` must be set (from
        get_tasks). Pass the line ids of lines you're keeping unchanged in
        `id` so they aren't replaced; omit `id` on a line to create it fresh
        (e.g. switching a single task to split)."""
        try:
            ct.update_task(session.plan, task)
            session.persist("update_task", f"Updated task {task.task_id}")
            return {"ok": True, "tasks": rt.get_tasks(session.plan)}
        except ValidationError as e:
            return _err(e)

    @tool
    def delete_task(task_id: str) -> dict:
        """Delete a task (all its lines) and remove it from any dependency
        lists. Requires human confirmation."""
        try:
            ct.delete_task(session.plan, task_id, confirm=True)
            session.persist("delete_task", f"Deleted task {task_id}")
            return {"ok": True}
        except ValidationError as e:
            return _err(e)

    @tool
    def set_dependencies(line_id: str, depends_on: list[str]) -> dict:
        """Set which other lines (by line_id, from get_tasks) must finish
        before this line can start. Rejected if it would create a circular
        dependency."""
        try:
            ct.set_dependencies(session.plan, line_id, depends_on)
            session.persist("set_dependencies", f"Set deps for {line_id}: {depends_on}")
            return {"ok": True}
        except ValidationError as e:
            return _err(e)

    @tool
    def bulk_set_mandatory(task_ids: list[str], mandatory: bool) -> dict:
        """Flag many tasks mandatory or optional at once."""
        ct.bulk_set_mandatory(session.plan, task_ids, mandatory)
        session.persist("bulk_set_mandatory", f"{len(task_ids)} task(s) -> mandatory={mandatory}")
        return {"ok": True}

    @tool
    def bulk_move_to_phase(task_ids: list[str], phase_id: int) -> dict:
        """Move many tasks to a phase at once."""
        try:
            ct.bulk_move_to_phase(session.plan, task_ids, phase_id)
            session.persist("bulk_move_to_phase", f"{len(task_ids)} task(s) -> phase {phase_id}")
            return {"ok": True}
        except ValidationError as e:
            return _err(e)

    @tool
    def bulk_move_to_stage(task_ids: list[str], stage_id: int | None) -> dict:
        """Move many tasks to a stage at once (stage_id=null -> unassigned)."""
        try:
            ct.bulk_move_to_stage(session.plan, task_ids, stage_id)
            session.persist("bulk_move_to_stage", f"{len(task_ids)} task(s) -> stage {stage_id}")
            return {"ok": True}
        except ValidationError as e:
            return _err(e)

    @tool
    def bulk_delete_tasks(task_ids: list[str]) -> dict:
        """Delete many tasks at once and clean them out of dependency lists.
        Requires human confirmation."""
        try:
            ct.bulk_delete_tasks(session.plan, task_ids, confirm=True)
            session.persist("bulk_delete_tasks", f"Deleted {len(task_ids)} task(s)")
            return {"ok": True}
        except ValidationError as e:
            return _err(e)

    # ---- templates -----------------------------------------------------------

    @tool
    def instantiate_template(
        template_id: str,
        room: str,
        name: str | None = None,
        qty: float | None = None,
        phase: int | None = None,
        stage_id: int | None = None,
    ) -> dict:
        """Create a task from a common-job template (see list_templates),
        prefilled with the right category/trade/structure/starting rate."""
        try:
            tt.instantiate_template(
                session.plan, template_id, room=room, name=name, qty=qty, phase=phase, stage_id=stage_id
            )
            session.persist("instantiate_template", f"'{template_id}' in {room}")
            return {"ok": True, "tasks": rt.get_tasks(session.plan)}
        except ValidationError as e:
            return _err(e)

    # ---- excel -----------------------------------------------------------------

    @tool
    def export_plan_to_excel(out_path: str) -> dict:
        """Export the whole plan to an Excel workbook at the given path."""
        path = iot.export_plan_to_excel(session.plan, Path(out_path))
        return {"ok": True, "path": str(path)}

    @tool
    def import_plan_from_excel(path: str) -> dict:
        """Import a plan from an Excel workbook, REPLACING the current
        plan entirely. Requires human confirmation."""
        try:
            session.plan = iot.import_plan_from_excel(Path(path), confirm=True)
            session.persist("import_plan_from_excel", f"Replaced plan from '{path}'")
            return {"ok": True, "setup": rt.get_setup(session.plan)}
        except ValidationError as e:
            return _err(e)

    return [
        get_setup,
        get_tasks,
        get_schedule,
        get_suggested_order,
        get_materials_plan,
        get_estimate_summary,
        get_track_summary,
        list_templates,
        get_changelog,
        add_room,
        rename_room,
        remove_room,
        add_rate,
        update_rate,
        delete_rate,
        add_phase,
        rename_phase,
        remove_phase,
        move_phase,
        add_stage,
        rename_stage,
        remove_stage,
        move_stage,
        set_project_settings,
        add_blocked_date,
        remove_blocked_date,
        create_task,
        update_task,
        delete_task,
        set_dependencies,
        bulk_set_mandatory,
        bulk_move_to_phase,
        bulk_move_to_stage,
        bulk_delete_tasks,
        instantiate_template,
        export_plan_to_excel,
        import_plan_from_excel,
    ]


def build_research_tools() -> list[BaseTool]:
    """Web-research tools (design doc §4.6's Research sub-agent). These
    don't touch the plan, so — unlike build_tools() — they don't need a
    session and are shared across every agent instance."""

    @tool
    def search_material_rate(material: str, location: str = "India") -> dict:
        """Search current market rates for a material or labour line item.
        Always returns sourced results — never state a price without
        citing where it came from, and never call update_rate without the
        user's explicit go-ahead."""
        return res.search_material_rate(material, location)

    @tool
    def search_vendors(category: str, location: str) -> dict:
        """Search for vendors/contractors for a trade category in a
        location. Leads only, not a vetted recommendation."""
        return res.search_vendors(category, location)

    return [search_material_rate, search_vendors]
