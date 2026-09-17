"""Cross-project task transfer — copy or move one or more tasks from one
project's Plan into another. Rooms/rates/phases/stages are reconciled by
*label*, not id (match an existing one in the target if the label already
exists there, otherwise create it) — the same approach Excel import already
uses for cross-context references (io/excel_import.py).

Dependencies pointing outside the transferred set are silently dropped
(same precedent as Excel import's tag-based re-linking for unresolvable
tags) rather than left dangling or blocking the transfer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from renovator.domain.models import Phase, Plan, Rate, Stage, TaskLine, new_id
from renovator.engine.tasks import group_by_task
from renovator.tools.errors import ValidationError


@dataclass
class TransferResult:
    transferred_task_count: int
    created_rooms: list[str] = field(default_factory=list)
    created_rates: list[str] = field(default_factory=list)
    created_phases: list[str] = field(default_factory=list)
    created_stages: list[str] = field(default_factory=list)
    dropped_dependencies: int = 0


def _find_or_create_room(target: Plan, name: str, created: list[str]) -> str:
    if name in target.rooms:
        return name
    target.rooms.append(name)
    created.append(name)
    return name


def _find_or_create_rate(target: Plan, source_rate: Rate, created: list[str]) -> str:
    existing = next((r for r in target.rates if r.label == source_rate.label), None)
    if existing:
        return existing.key
    key = new_id("rate")
    target.rates.append(Rate(key=key, label=source_rate.label, unit=source_rate.unit, value=source_rate.value))
    created.append(source_rate.label)
    return key


def _find_or_create_phase(target: Plan, label: str, created: list[str]) -> int:
    existing = next((p for p in target.phases if p.label == label), None)
    if existing:
        return existing.id
    phase_id = max([p.id for p in target.phases], default=0) + 1
    target.phases.append(Phase(id=phase_id, label=label))
    created.append(label)
    return phase_id


def _find_or_create_stage(target: Plan, label: str | None, created: list[str]) -> int | None:
    if label is None:
        return None
    existing = next((s for s in target.stages if s.label == label), None)
    if existing:
        return existing.id
    stage_id = max([s.id for s in target.stages], default=0) + 1
    target.stages.append(Stage(id=stage_id, label=label))
    created.append(label)
    return stage_id


def transfer_tasks(source: Plan, target: Plan, task_ids: list[str], mode: str) -> TransferResult:
    if mode not in ("copy", "move"):
        raise ValidationError(f"Unknown transfer mode: {mode!r} (must be 'copy' or 'move')")
    if source is target:
        raise ValidationError("Source and target project must be different.")

    tasks = [t for t in group_by_task(source) if t.task_id in task_ids]
    if not tasks:
        raise ValidationError("No matching tasks to transfer.")

    result = TransferResult(transferred_task_count=len(tasks))
    source_rates_by_key = {r.key: r for r in source.rates}
    source_phase_label = {p.id: p.label for p in source.phases}
    source_stage_label = {s.id: s.label for s in source.stages}
    fallback_phase_label = target.phases[0].label if target.phases else "Phase 1 — Now"

    new_line_by_old_id: dict[str, TaskLine] = {}
    dropped_ids: set[str] = set()

    for t in tasks:
        new_task_id = new_id("task")
        for line in t.lines:
            dropped_ids.add(line.id)
            room = _find_or_create_room(target, line.room, result.created_rooms)
            new_rate_key = line.rate_key
            if line.rate_key and line.rate_key in source_rates_by_key:
                new_rate_key = _find_or_create_rate(target, source_rates_by_key[line.rate_key], result.created_rates)
            phase_label = source_phase_label.get(line.phase, fallback_phase_label)
            new_phase_id = _find_or_create_phase(target, phase_label, result.created_phases)
            stage_label = source_stage_label.get(line.stage_id) if line.stage_id is not None else None
            new_stage_id = _find_or_create_stage(target, stage_label, result.created_stages)

            new_line = line.model_copy(
                update={
                    "id": new_id("item"),
                    "task_id": new_task_id,
                    "room": room,
                    "rate_key": new_rate_key,
                    "phase": new_phase_id,
                    "stage_id": new_stage_id,
                    "depends_on": [],  # resolved below, once every new id is known
                }
            )
            new_line_by_old_id[line.id] = new_line

    for old_id, new_line in new_line_by_old_id.items():
        original = next(it for it in source.items if it.id == old_id)
        resolved = [new_line_by_old_id[d].id for d in original.depends_on if d in new_line_by_old_id]
        result.dropped_dependencies += len(original.depends_on) - len(resolved)
        new_line.depends_on = resolved

    target.items.extend(new_line_by_old_id.values())

    if mode == "move":
        source.items = [it for it in source.items if it.id not in dropped_ids]
        for it in source.items:
            if any(d in dropped_ids for d in it.depends_on):
                it.depends_on = [d for d in it.depends_on if d not in dropped_ids]

    return result
