"""Materials tab derivation. Port of materialLines()/renderMaterialsTab()
(Renovation_Planner_v2.html:1009-1068). Material lines grouped by the week
their parent task's schedule needs them, with buy-status totals."""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from renovator.domain.models import BuyStatus, CostMethod, LineType, Plan, TaskLine
from renovator.engine.cost import item_cost
from renovator.engine.schedule import compute_schedule
from renovator.engine.tasks import group_by_task

NO_DATE_BUCKET = "zzz"  # sorts after any real ISO week key, matches the JS grouping key


def iso_week_key(d: datetime.date) -> str:
    """Monday of the week containing `d` (Renovation_Planner_v2.html:567)."""
    return (d - datetime.timedelta(days=d.weekday())).isoformat()


@dataclass
class MaterialLine:
    line: TaskLine
    need_by: datetime.date | None
    qty: float | None
    unit: str
    cost: float

    @property
    def overdue(self) -> bool:
        return self.need_by is not None and self.need_by < datetime.date.today()


@dataclass
class MaterialWeekGroup:
    week_key: str  # NO_DATE_BUCKET, or the ISO date of that week's Monday
    lines: list[MaterialLine]
    subtotal: float


@dataclass
class MaterialsPlan:
    lines: list[MaterialLine]
    groups: list[MaterialWeekGroup]
    total: float = 0
    to_buy_cost: float = 0
    to_buy_count: int = 0
    ordered_count: int = 0
    delivered_count: int = 0


def material_lines(plan: Plan) -> list[MaterialLine]:
    schedule = compute_schedule(plan)
    task_by_line_id = {line.id: t for t in group_by_task(plan) for line in t.lines}
    rates_by_key = {r.key: r for r in plan.rates}

    result: list[MaterialLine] = []
    for m in plan.items:
        if m.line_type != LineType.MATERIAL:
            continue
        task = task_by_line_id.get(m.id)
        sched = schedule.tasks.get(task.task_id) if task else None
        rate = rates_by_key.get(m.rate_key) if m.cost_method == CostMethod.RATE else None
        result.append(
            MaterialLine(
                line=m,
                need_by=sched.start if sched else None,
                qty=m.qty if m.cost_method == CostMethod.RATE else None,
                unit=rate.unit if rate else "",
                cost=item_cost(plan, m),
            )
        )
    return result


def materials_plan(plan: Plan) -> MaterialsPlan:
    lines = material_lines(plan)
    # sort by need_by ascending, no-date lines last (Renovation_Planner_v2.html:1028)
    lines.sort(key=lambda r: (r.need_by is None, r.need_by or datetime.date.max))

    groups_map: dict[str, list[MaterialLine]] = {}
    for r in lines:
        key = iso_week_key(r.need_by) if r.need_by else NO_DATE_BUCKET
        groups_map.setdefault(key, []).append(r)
    groups = [
        MaterialWeekGroup(week_key=key, lines=rows, subtotal=sum(r.cost for r in rows))
        for key, rows in sorted(groups_map.items())
    ]

    total = sum(r.cost for r in lines)
    to_buy = [r for r in lines if r.line.buy_status == BuyStatus.TO_BUY]
    ordered = [r for r in lines if r.line.buy_status == BuyStatus.ORDERED]
    delivered = [r for r in lines if r.line.buy_status == BuyStatus.DELIVERED]

    return MaterialsPlan(
        lines=lines,
        groups=groups,
        total=total,
        to_buy_cost=sum(r.cost for r in to_buy),
        to_buy_count=len(to_buy),
        ordered_count=len(ordered),
        delivered_count=len(delivered),
    )
