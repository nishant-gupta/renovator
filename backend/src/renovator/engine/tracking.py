"""Track tab derivation. Port of renderTrackTab()'s stats
(Renovation_Planner_v2.html:1115-1149). Operates at the line level, and
variance is only meaningful once >=1 line has an actual cost logged."""

from __future__ import annotations

from dataclasses import dataclass

from renovator.domain.models import Plan, TaskStatus
from renovator.engine.cost import grand_total


@dataclass
class TrackSummary:
    progress_pct: int
    lines_done: int
    lines_total: int
    estimated_total: float
    actual_total: float
    actuals_logged: int
    variance: float | None  # None until >=1 actual is logged


def track_summary(plan: Plan) -> TrackSummary:
    items = plan.items
    done = sum(1 for i in items if i.status == TaskStatus.DONE)
    pct = round(done / len(items) * 100) if items else 0
    estimated = grand_total(plan, items)
    actual = sum(i.actual_cost for i in items if i.actual_cost is not None)
    logged = sum(1 for i in items if i.actual_cost is not None)

    return TrackSummary(
        progress_pct=pct,
        lines_done=done,
        lines_total=len(items),
        estimated_total=estimated,
        actual_total=actual,
        actuals_logged=logged,
        variance=(actual - estimated) if logged > 0 else None,
    )
