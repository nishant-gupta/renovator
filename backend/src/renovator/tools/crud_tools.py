"""Mutating tools — one per entity, mirroring the Setup/Tasks tab actions
(design doc §4.5). Ported from Renovation_Planner_v2.html's mutation
functions (renameRoom, removeRoom, addRate, deleteRate, addPhase,
removePhase, movePhase, addStage, removeStage, moveStage,
saveDraftTask/deleteTask, bulk*), preserving their exact validation and
confirmation semantics — see errors.py for the ValidationError vs.
ConfirmationRequired contract.

Deliberate deviations from the reference app, both because it's a UI
convenience that doesn't belong in a data-mutation API:

- Empty/invalid input (empty room name, unknown phase/stage id, etc.) raises
  `ValidationError` here; the reference app's `prompt()`-based UI just
  silently no-ops in most of these cases.
- The task editor's category -> trade/duration auto-fill (feature.md §4.1)
  is a UI/agent-side convenience applied *before* calling `create_task`, not
  something these tools do themselves. Callers pass fully-specified lines.
"""

from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel

from renovator.domain.models import (
    BuyStatus,
    CostMethod,
    LineType,
    Phase,
    Plan,
    Rate,
    Stage,
    TaskLine,
    TaskStatus,
    WeekendPolicy,
    new_id,
)
from renovator.engine.dependencies import would_create_cycle
from renovator.engine.tasks import clamp_duration
from renovator.tools.errors import ConfirmationRequired, ValidationError

# --------------------------------------------------------------------------
# Rooms (Renovation_Planner_v2.html:1512-1528)
# --------------------------------------------------------------------------


def add_room(plan: Plan, name: str) -> Plan:
    name = name.strip()
    if not name:
        raise ValidationError("Room name is required.")
    if name in plan.rooms:
        raise ValidationError(f'Room "{name}" already exists.')
    plan.rooms.append(name)
    return plan


def rename_room(plan: Plan, old_name: str, new_name: str) -> Plan:
    new_name = new_name.strip()
    if not new_name or new_name == old_name:
        return plan
    if old_name not in plan.rooms:
        raise ValidationError(f'No such room: "{old_name}"')
    if new_name in plan.rooms:
        raise ValidationError(f'Room "{new_name}" already exists.')
    plan.rooms = [new_name if r == old_name else r for r in plan.rooms]
    for it in plan.items:
        if it.room == old_name:
            it.room = new_name
    return plan


def remove_room(plan: Plan, name: str, confirm: bool = False) -> Plan:
    in_use = sum(1 for it in plan.items if it.room == name)
    if in_use:
        raise ValidationError(
            f'"{name}" is used by {in_use} task(s). Move or delete those first.'
        )
    if not confirm:
        raise ConfirmationRequired(f'Remove "{name}"?')
    if name not in plan.rooms:
        raise ValidationError(f'No such room: "{name}"')
    plan.rooms = [r for r in plan.rooms if r != name]
    return plan


# --------------------------------------------------------------------------
# Rate card (Renovation_Planner_v2.html:1530-1542)
# --------------------------------------------------------------------------


def add_rate(plan: Plan, label: str, unit: str, value: float) -> Plan:
    plan.rates.append(Rate(key=new_id("rate"), label=label, unit=unit, value=value))
    return plan


def update_rate(plan: Plan, key: str, value: float) -> Plan:
    rate = next((r for r in plan.rates if r.key == key), None)
    if not rate:
        raise ValidationError(f"No such rate: {key}")
    rate.value = value
    return plan


def delete_rate(plan: Plan, key: str, confirm: bool = False) -> Plan:
    in_use = any(it.cost_method == CostMethod.RATE and it.rate_key == key for it in plan.items)
    if in_use and not confirm:
        raise ConfirmationRequired(
            "Some tasks use this rate — deleting it will zero their cost until you fix them. Continue?"
        )
    plan.rates = [r for r in plan.rates if r.key != key]
    return plan


# --------------------------------------------------------------------------
# Phases (Renovation_Planner_v2.html:1544-1557)
# --------------------------------------------------------------------------


def _next_phase_id(plan: Plan) -> int:
    return max([p.id for p in plan.phases], default=0) + 1


def add_phase(plan: Plan, label: str) -> Plan:
    label = label.strip()
    if not label:
        raise ValidationError("Phase name is required.")
    plan.phases.append(Phase(id=_next_phase_id(plan), label=label))
    return plan


def rename_phase(plan: Plan, phase_id: int, label: str) -> Plan:
    phase = next((p for p in plan.phases if p.id == phase_id), None)
    if not phase:
        raise ValidationError(f"No such phase: {phase_id}")
    label = label.strip()
    if not label:
        raise ValidationError("Phase name is required.")
    phase.label = label
    return plan


def remove_phase(plan: Plan, phase_id: int, confirm: bool = False) -> Plan:
    if len(plan.phases) <= 1:
        raise ValidationError("You need at least one phase.")
    fallback = next((p for p in plan.phases if p.id != phase_id), None)
    if not fallback:
        raise ValidationError(f"No such phase: {phase_id}")
    in_use = sum(1 for it in plan.items if it.phase == phase_id)
    if in_use and not confirm:
        raise ConfirmationRequired(
            f'{in_use} task(s) use this phase — they\'ll move to "{fallback.label}". Continue?'
        )
    for it in plan.items:
        if it.phase == phase_id:
            it.phase = fallback.id
    plan.phases = [p for p in plan.phases if p.id != phase_id]
    return plan


def move_phase(plan: Plan, index: int, direction: Literal[-1, 1]) -> Plan:
    j = index + direction
    if j < 0 or j >= len(plan.phases) or index < 0 or index >= len(plan.phases):
        raise ValidationError("Move out of range.")
    plan.phases[index], plan.phases[j] = plan.phases[j], plan.phases[index]
    return plan


# --------------------------------------------------------------------------
# Stages (Renovation_Planner_v2.html:997-999,1558-1561)
# --------------------------------------------------------------------------


def _next_stage_id(plan: Plan) -> int:
    return max([s.id for s in plan.stages], default=0) + 1


def add_stage(plan: Plan, label: str) -> Plan:
    label = label.strip()
    if not label:
        raise ValidationError("Stage name is required.")
    plan.stages.append(Stage(id=_next_stage_id(plan), label=label))
    return plan


def rename_stage(plan: Plan, stage_id: int, label: str) -> Plan:
    stage = next((s for s in plan.stages if s.id == stage_id), None)
    if not stage:
        raise ValidationError(f"No such stage: {stage_id}")
    label = label.strip()
    if not label:
        raise ValidationError("Stage name is required.")
    stage.label = label
    return plan


def remove_stage(plan: Plan, stage_id: int, confirm: bool = False) -> Plan:
    if not any(s.id == stage_id for s in plan.stages):
        raise ValidationError(f"No such stage: {stage_id}")
    in_use = sum(1 for it in plan.items if it.stage_id == stage_id)
    if in_use and not confirm:
        raise ConfirmationRequired(
            f"{in_use} task line(s) are in this stage — they'll become unassigned. Continue?"
        )
    for it in plan.items:
        if it.stage_id == stage_id:
            it.stage_id = None
    plan.stages = [s for s in plan.stages if s.id != stage_id]
    return plan


def move_stage(plan: Plan, index: int, direction: Literal[-1, 1]) -> Plan:
    j = index + direction
    if j < 0 or j >= len(plan.stages) or index < 0 or index >= len(plan.stages):
        raise ValidationError("Move out of range.")
    plan.stages[index], plan.stages[j] = plan.stages[j], plan.stages[index]
    return plan


# --------------------------------------------------------------------------
# Project settings (Renovation_Planner_v2.html:542,837-838)
# --------------------------------------------------------------------------


def set_project_settings(
    plan: Plan,
    project_start: str | None = None,
    weekend_policy: WeekendPolicy | str | None = None,
    sequence_stages: bool | None = None,
) -> Plan:
    if project_start is not None:
        plan.settings.project_start = project_start
    if weekend_policy is not None:
        try:
            plan.settings.weekend_policy = WeekendPolicy(weekend_policy)
        except ValueError as e:
            raise ValidationError(
                f"Invalid weekend_policy: {weekend_policy!r} (must be one of "
                f"{[p.value for p in WeekendPolicy]})"
            ) from e
    if sequence_stages is not None:
        plan.settings.sequence_stages = sequence_stages
    return plan


def add_blocked_date(plan: Plan, date: str) -> Plan:
    """Marks one ISO yyyy-mm-dd date as no-work-allowed (a holiday, a
    contractor's day off) regardless of weekday. No reference-app
    equivalent — new in Phase 9's scheduling follow-up."""
    try:
        datetime.date.fromisoformat(date)
    except ValueError as e:
        raise ValidationError(f"Invalid date (expected yyyy-mm-dd): {date!r}") from e
    if date not in plan.settings.blocked_dates:
        plan.settings.blocked_dates = sorted([*plan.settings.blocked_dates, date])
    return plan


def remove_blocked_date(plan: Plan, date: str) -> Plan:
    if date not in plan.settings.blocked_dates:
        raise ValidationError(f"No such blocked date: {date}")
    plan.settings.blocked_dates = [d for d in plan.settings.blocked_dates if d != date]
    return plan


# --------------------------------------------------------------------------
# Tasks — create/update share one upsert path, matching saveDraftTask()
# (Renovation_Planner_v2.html:1331-1355), since the reference app assigns a
# fresh taskId at "add" time and reaches the same save function either way.
# --------------------------------------------------------------------------


class LineInput(BaseModel):
    """One line's editable fields (Renovation_Planner_v2.html:1160-1170)."""

    id: str | None = None  # existing TaskLine.id when editing that line, else None
    worker_type: str = ""
    status: TaskStatus = TaskStatus.NOT_STARTED
    cost_method: CostMethod = CostMethod.CUSTOM
    rate_key: str | None = None
    qty: float | None = None
    custom_amount: float | None = None
    buy_status: BuyStatus = BuyStatus.TO_BUY
    depends_on: list[str] = []
    actual_cost: float | None = None
    notes: str = ""


class TaskInput(BaseModel):
    """Payload for create_task/update_task (Renovation_Planner_v2.html:1172-1197)."""

    task_id: str | None = None  # None => create a new task; set => update that task
    room: str
    name: str
    category: str
    phase: int
    stage_id: int | None = None
    mandatory: bool = True
    duration_days: int | None = None
    start_override: str | None = None
    structure: Literal["single", "split"] = "single"
    single_line_type: LineType = LineType.INCLUSIVE
    single: LineInput | None = None
    material: LineInput | None = None
    labor: LineInput | None = None


def _build_lines(task_id: str, ti: TaskInput) -> list[TaskLine]:
    name = ti.name.strip()
    if not name:
        raise ValidationError("Give the task a name first.")
    shared = {
        "task_id": task_id,
        "room": ti.room,
        "name": name,
        "category": ti.category,
        "phase": ti.phase,
        "stage_id": ti.stage_id,
        "mandatory": ti.mandatory,
        "duration_days": clamp_duration(ti.duration_days),
        "start_override": ti.start_override or None,
    }

    def line_from(input_line: LineInput, line_type: LineType, default_worker: str) -> TaskLine:
        return TaskLine(
            **shared,
            id=input_line.id or new_id("item"),
            line_type=line_type,
            worker_type=input_line.worker_type or default_worker,
            status=input_line.status,
            cost_method=input_line.cost_method,
            rate_key=input_line.rate_key,
            qty=input_line.qty,
            custom_amount=input_line.custom_amount,
            buy_status=input_line.buy_status,
            depends_on=list(input_line.depends_on),
            actual_cost=input_line.actual_cost,
            notes=input_line.notes,
        )

    if ti.structure == "split":
        if ti.material is None or ti.labor is None:
            raise ValidationError("A split task needs both a material and a labour line.")
        return [
            line_from(ti.material, LineType.MATERIAL, "Material"),
            line_from(ti.labor, LineType.LABOR, ""),
        ]

    if ti.single is None:
        raise ValidationError("A single-line task needs its line details.")
    return [line_from(ti.single, ti.single_line_type, "")]


def upsert_task(plan: Plan, task_input: TaskInput) -> Plan:
    task_id = task_input.task_id or new_id("task")
    new_lines = _build_lines(task_id, task_input)

    old_member_ids: set[str] = set()
    if task_input.task_id:
        old_member_ids = {it.id for it in plan.items if it.task_id == task_input.task_id}
    new_ids = {l.id for l in new_lines}
    dropped_ids = old_member_ids - new_ids

    others = [it for it in plan.items if it.id not in old_member_ids]
    if dropped_ids:
        for it in others:
            if any(d in it.depends_on for d in dropped_ids):
                it.depends_on = [d for d in it.depends_on if d not in dropped_ids]

    prospective = others + new_lines
    for line in new_lines:
        if line.depends_on and would_create_cycle(plan, line.id, line.depends_on, override=prospective):
            raise ValidationError(
                f'The "{line.line_type.value}" line has a circular dependency — '
                "please review before saving."
            )

    plan.items = prospective
    return plan


def create_task(plan: Plan, task_input: TaskInput) -> Plan:
    if task_input.task_id is not None:
        raise ValidationError("create_task cannot be called with an existing task_id — use update_task.")
    return upsert_task(plan, task_input)


def update_task(plan: Plan, task_input: TaskInput) -> Plan:
    if not task_input.task_id:
        raise ValidationError("update_task requires task_id — use create_task for a new task.")
    if not any(it.task_id == task_input.task_id for it in plan.items):
        raise ValidationError(f"No such task: {task_input.task_id}")
    return upsert_task(plan, task_input)


def delete_task(plan: Plan, task_id: str, confirm: bool = False) -> Plan:
    members = [it for it in plan.items if it.task_id == task_id]
    if not members:
        raise ValidationError(f"No such task: {task_id}")
    if not confirm:
        label = f"{members[0].room} — {members[0].name}"
        suffix = " (both Material and Labour lines)" if len(members) > 1 else ""
        raise ConfirmationRequired(
            f'Delete "{label}"{suffix}? This also removes it from any dependency lists.'
        )
    dropped_ids = {m.id for m in members}
    plan.items = [it for it in plan.items if it.task_id != task_id]
    for it in plan.items:
        if any(d in it.depends_on for d in dropped_ids):
            it.depends_on = [d for d in it.depends_on if d not in dropped_ids]
    return plan


def set_dependencies(plan: Plan, line_id: str, depends_on: list[str]) -> Plan:
    line = next((it for it in plan.items if it.id == line_id), None)
    if not line:
        raise ValidationError(f"No such line: {line_id}")
    if depends_on and would_create_cycle(plan, line_id, depends_on):
        raise ValidationError("That dependency would create a circular chain — please review.")
    line.depends_on = list(depends_on)
    return plan


def update_line(
    plan: Plan,
    line_id: str,
    buy_status: BuyStatus | None = None,
    status: TaskStatus | None = None,
    actual_cost: float | None = None,
    notes: str | None = None,
) -> Plan:
    """Patch one line's Materials/Track-tab fields in place, without
    touching structure/costing/dependencies — the lightweight counterpart
    to update_task for the Materials/Track tabs' inline editing
    (feature.md §6, §8), which only ever change one of these fields at a
    time and shouldn't have to resend the whole task to do it."""
    line = next((it for it in plan.items if it.id == line_id), None)
    if not line:
        raise ValidationError(f"No such line: {line_id}")
    # Direct attribute assignment on an already-constructed model does not
    # re-validate/coerce (unlike building a fresh TaskLine(...)), so enum
    # fields need an explicit coercion here or they'd end up holding a
    # plain str instead of the enum member.
    try:
        if buy_status is not None:
            line.buy_status = BuyStatus(buy_status)
        if status is not None:
            line.status = TaskStatus(status)
    except ValueError as e:
        raise ValidationError(str(e)) from e
    if actual_cost is not None:
        line.actual_cost = actual_cost
    if notes is not None:
        line.notes = notes
    return plan


# --------------------------------------------------------------------------
# Bulk actions (Renovation_Planner_v2.html:785-805)
# --------------------------------------------------------------------------


def bulk_set_mandatory(plan: Plan, task_ids: list[str], mandatory: bool) -> Plan:
    ids = set(task_ids)
    for it in plan.items:
        if it.task_id in ids:
            it.mandatory = mandatory
    return plan


def bulk_move_to_phase(plan: Plan, task_ids: list[str], phase_id: int) -> Plan:
    if not any(p.id == phase_id for p in plan.phases):
        raise ValidationError(f"No such phase: {phase_id}")
    ids = set(task_ids)
    for it in plan.items:
        if it.task_id in ids:
            it.phase = phase_id
    return plan


def bulk_move_to_stage(plan: Plan, task_ids: list[str], stage_id: int | None) -> Plan:
    if stage_id is not None and not any(s.id == stage_id for s in plan.stages):
        raise ValidationError(f"No such stage: {stage_id}")
    ids = set(task_ids)
    for it in plan.items:
        if it.task_id in ids:
            it.stage_id = stage_id
    return plan


def bulk_delete_tasks(plan: Plan, task_ids: list[str], confirm: bool = False) -> Plan:
    ids = set(task_ids)
    dropped_line_ids = {it.id for it in plan.items if it.task_id in ids}
    if not dropped_line_ids:
        raise ValidationError("No matching tasks to delete.")
    if not confirm:
        raise ConfirmationRequired(
            f"Delete {len(ids)} task(s)? They'll also be removed from any dependency lists."
        )
    plan.items = [it for it in plan.items if it.task_id not in ids]
    for it in plan.items:
        if any(d in it.depends_on for d in dropped_line_ids):
            it.depends_on = [d for d in it.depends_on if d not in dropped_line_ids]
    return plan
