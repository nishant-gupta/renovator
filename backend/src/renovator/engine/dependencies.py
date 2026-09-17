"""Dependency graph helpers. Port of wouldCreateCycle()/suggestedOrder()
(Renovation_Planner_v2.html:574-585). Both operate at the line level (not
the task level) — dependencies are stored per-line."""

from __future__ import annotations

from renovator.domain.models import Plan, TaskLine
from renovator.engine.schedule import stage_order


def would_create_cycle(
    plan: Plan,
    item_id: str,
    new_deps: list[str],
    override: list[TaskLine] | None = None,
) -> bool:
    """True if setting `item_id`'s dependencies to `new_deps` would create a
    cycle. Pass `override` (a prospective merged item list) when checking a
    save-in-progress edit, as the reference app's task editor does."""
    items = override if override is not None else plan.items
    dep_map: dict[str, list[str]] = {
        it.id: (new_deps if it.id == item_id else it.depends_on) for it in items
    }

    def reach(start: str, target: str, seen: set[str]) -> bool:
        if start == target:
            return True
        if start in seen:
            return False
        seen.add(start)
        return any(reach(d, target, seen) for d in dep_map.get(start, []))

    return any(reach(d, item_id, set()) for d in new_deps)


def suggested_order(plan: Plan) -> list[TaskLine]:
    """Dependency-aware, stage-ordered execution order of every line
    (Renovation_Planner_v2.html:580-585)."""
    by_id = {it.id: it for it in plan.items}
    visited: set[str] = set()
    temp: set[str] = set()
    order: list[str] = []

    def visit(item_id: str) -> None:
        if item_id in visited or item_id in temp:
            return
        temp.add(item_id)
        it = by_id.get(item_id)
        if it:
            for dep_id in it.depends_on:
                if dep_id in by_id:
                    visit(dep_id)
        temp.discard(item_id)
        visited.add(item_id)
        order.append(item_id)

    stage_sorted = sorted(plan.items, key=lambda it: stage_order(plan, it.stage_id))
    for it in stage_sorted:
        visit(it.id)

    return [by_id[i] for i in order if i in by_id]
