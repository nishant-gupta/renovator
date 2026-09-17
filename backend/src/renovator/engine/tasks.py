"""Line -> Task grouping. Port of deriveTaskIds()/groupByTask()
(Renovation_Planner_v2.html:606-626)."""

from __future__ import annotations

from dataclasses import dataclass

from renovator.domain.models import LineType, Plan, TaskLine, new_id
from renovator.engine.cost import item_cost


@dataclass
class Task:
    """A derived grouping of 1-2 TaskLines sharing a task_id (split Material+Labor, or single).

    `duration_days` is carried through raw (possibly None) exactly as the
    reference app does — clamping to a minimum of 1 happens at the point of
    use (compute_schedule, display), it is not baked in here.
    """

    task_id: str
    room: str
    name: str
    category: str
    phase: int
    stage_id: int | None
    mandatory: bool
    duration_days: int | None
    start_override: str | None
    lines: list[TaskLine]
    is_split: bool
    material: TaskLine | None
    labor: TaskLine | None
    total_cost: float


def clamp_duration(duration_days: int | None) -> int:
    """Port of `Math.max(1, Number(t.durationDays) || 1)` (Renovation_Planner_v2.html:668)."""
    if not duration_days or duration_days < 1:
        return 1
    return duration_days


def derive_task_ids(items: list[TaskLine]) -> None:
    """Assign task_id in place to any line missing one, exactly like the JS version:
    lines sharing (room, name, category) pair up into a split task only if there
    are exactly two of them and they are one Material + one Labor line; otherwise
    each line is its own task."""
    groups: dict[tuple[str, str, str], list[TaskLine]] = {}
    for it in items:
        if it.task_id:
            continue
        key = (it.room, it.name, it.category)
        groups.setdefault(key, []).append(it)

    for group in groups.values():
        if len(group) == 2:
            types = sorted(g.line_type.value for g in group)
            if types == [LineType.LABOR.value, LineType.MATERIAL.value]:
                tid = new_id("task")
                for g in group:
                    g.task_id = tid
                continue
        for g in group:
            if not g.task_id:
                g.task_id = g.id


def group_by_task(plan: Plan) -> list[Task]:
    order: list[str] = []
    by_task: dict[str, list[TaskLine]] = {}
    for it in plan.items:
        tid = it.task_id or it.id
        if tid not in by_task:
            by_task[tid] = []
            order.append(tid)
        by_task[tid].append(it)

    tasks: list[Task] = []
    for tid in order:
        lines = by_task[tid]
        material = next((l for l in lines if l.line_type == LineType.MATERIAL), None)
        labor = next((l for l in lines if l.line_type == LineType.LABOR), None)
        is_split = len(lines) == 2 and material is not None and labor is not None
        primary = labor or lines[0]
        total_cost = sum(item_cost(plan, l) for l in lines)
        tasks.append(
            Task(
                task_id=tid,
                room=primary.room,
                name=primary.name,
                category=primary.category,
                phase=primary.phase,
                stage_id=primary.stage_id,
                mandatory=primary.mandatory,
                duration_days=primary.duration_days,
                start_override=primary.start_override,
                lines=lines,
                is_split=is_split,
                material=material,
                labor=labor,
                total_cost=total_cost,
            )
        )
    return tasks
