"""Read/derived tools — thin, JSON-serializable wrappers over
`renovator.engine` (design doc §4.5). Always recomputed from the current
`Plan`, never cached across a mutation. These are the same functions both
the direct-CRUD UI and the agent's tool calls read through."""

from __future__ import annotations

from renovator.domain.models import Plan
from renovator.engine.cost import estimate_summary as _estimate_summary
from renovator.engine.dependencies import suggested_order as _suggested_order
from renovator.engine.materials import materials_plan as _materials_plan
from renovator.engine.schedule import compute_schedule, project_end_date
from renovator.engine.tasks import group_by_task
from renovator.engine.tracking import track_summary as _track_summary


def get_setup(plan: Plan) -> dict:
    """Setup tab (feature.md §3): the building blocks every other tab
    reuses — rooms, rate card, phases (priority order), stages (trade
    sequence), and project timing settings."""
    return {
        "rooms": list(plan.rooms),
        "rates": [
            {"key": r.key, "label": r.label, "unit": r.unit, "value": r.value} for r in plan.rates
        ],
        "phases": [{"id": p.id, "label": p.label} for p in plan.phases],
        "stages": [{"id": s.id, "label": s.label} for s in plan.stages],
        "project_start": plan.settings.project_start,
        "work_weekends": plan.settings.work_weekends,
        "sequence_stages": plan.settings.sequence_stages,
    }


def get_tasks(plan: Plan) -> list[dict]:
    """Tasks tab (feature.md §4): every task with its line/dependency ids —
    call this before update_task/delete_task/set_dependencies to find the
    task_id and line ids to reference."""
    tasks = group_by_task(plan)
    return [
        {
            "task_id": t.task_id,
            "room": t.room,
            "name": t.name,
            "category": t.category,
            "phase": t.phase,
            "stage_id": t.stage_id,
            "mandatory": t.mandatory,
            "duration_days": t.duration_days,
            "start_override": t.start_override,
            "is_split": t.is_split,
            "total_cost": t.total_cost,
            "lines": [
                {
                    "line_id": l.id,
                    "line_type": l.line_type.value,
                    "worker_type": l.worker_type,
                    "status": l.status.value,
                    "cost_method": l.cost_method.value,
                    "rate_key": l.rate_key,
                    "qty": l.qty,
                    "custom_amount": l.custom_amount,
                    "buy_status": l.buy_status.value,
                    "depends_on": l.depends_on,
                    "actual_cost": l.actual_cost,
                    "notes": l.notes,
                }
                for l in t.lines
            ],
        }
        for t in tasks
    ]


def get_schedule(plan: Plan) -> dict:
    """Timeline/agenda/board views all derive from this one computed
    schedule (feature.md §5) — task start/end/duration plus the project
    span. Views (grouping by stage/week, drag targets, etc.) are a frontend
    concern; this returns the data they render."""
    schedule = compute_schedule(plan)
    tasks = []
    for t in schedule.task_list:
        sched = schedule.tasks.get(t.task_id)
        # Same "primary line" a split task's trade comes from as the reference
        # app's taskTradeBucket() (Renovation_Planner_v2.html:626): the Labor
        # line if split, otherwise the task's only line.
        primary = t.labor or t.lines[0]
        tasks.append(
            {
                "task_id": t.task_id,
                "room": t.room,
                "name": t.name,
                "category": t.category,
                "phase": t.phase,
                "stage_id": t.stage_id,
                "mandatory": t.mandatory,
                "is_split": t.is_split,
                "total_cost": t.total_cost,
                "worker_type": primary.worker_type,
                "start": sched.start.isoformat() if sched else None,
                "end": sched.end.isoformat() if sched else None,
                "duration_days": sched.dur if sched else None,
                "fixed_start": t.start_override is not None,
            }
        )
    end = project_end_date(schedule)
    return {
        "project_start": schedule.project_start.isoformat(),
        "project_end": end.isoformat() if end else None,
        "tasks": tasks,
    }


def get_suggested_order(plan: Plan) -> list[dict]:
    """Dependency-aware, stage-ordered execution order (feature.md §5.3)."""
    return [
        {"line_id": it.id, "room": it.room, "name": it.name, "line_type": it.line_type.value}
        for it in _suggested_order(plan)
    ]


def get_materials_plan(plan: Plan) -> dict:
    """Materials tab (feature.md §6): need-by grouped by week, with
    buy-status totals."""
    result = _materials_plan(plan)
    return {
        "total": result.total,
        "to_buy_cost": result.to_buy_cost,
        "to_buy_count": result.to_buy_count,
        "ordered_count": result.ordered_count,
        "delivered_count": result.delivered_count,
        "groups": [
            {
                "week_key": g.week_key,
                "subtotal": g.subtotal,
                "lines": [
                    {
                        "line_id": r.line.id,
                        "name": r.line.name,
                        "room": r.line.room,
                        "need_by": r.need_by.isoformat() if r.need_by else None,
                        "overdue": r.overdue,
                        "qty": r.qty,
                        "unit": r.unit,
                        "cost": r.cost,
                        "buy_status": r.line.buy_status.value,
                        "notes": r.line.notes,
                    }
                    for r in g.lines
                ],
            }
            for g in result.groups
        ],
    }


def get_estimate_summary(plan: Plan) -> dict:
    """Estimate tab (feature.md §7): totals, by-room/by-trade/by-phase
    breakdowns, and the full task table sorted by cost (highest first)."""
    summary = _estimate_summary(plan)
    tasks = sorted(group_by_task(plan), key=lambda t: t.total_cost, reverse=True)
    return {
        **summary,
        "tasks": [
            {
                "task_id": t.task_id,
                "room": t.room,
                "name": t.name,
                "is_split": t.is_split,
                "total_cost": t.total_cost,
            }
            for t in tasks
        ],
    }


def get_track_summary(plan: Plan) -> dict:
    """Track tab (feature.md §8): progress %, actual-vs-estimate, variance
    (variance is None until >=1 actual has been logged), plus per-task rows."""
    summary = _track_summary(plan)
    tasks = group_by_task(plan)
    task_rows = []
    for t in tasks:
        actual_lines = [l.actual_cost for l in t.lines if l.actual_cost is not None]
        statuses = {l.status.value for l in t.lines}
        if statuses == {"Done"}:
            combined_status = "Done"
        elif "In Progress" in statuses:
            combined_status = "In Progress"
        elif statuses == {"On Hold"}:
            combined_status = "On Hold"
        else:
            combined_status = "Not Started"
        task_rows.append(
            {
                "task_id": t.task_id,
                "room": t.room,
                "name": t.name,
                "is_split": t.is_split,
                "total_cost": t.total_cost,
                "actual_cost": sum(actual_lines) if actual_lines else None,
                "status": combined_status,
            }
        )
    return {
        "progress_pct": summary.progress_pct,
        "lines_done": summary.lines_done,
        "lines_total": summary.lines_total,
        "estimated_total": summary.estimated_total,
        "actual_total": summary.actual_total,
        "actuals_logged": summary.actuals_logged,
        "variance": summary.variance,
        "tasks": task_rows,
    }
