"""Export a Plan to the 9-sheet workbook: Project, Rate Card, Phases, Stages,
Rooms & Items, Schedule, Materials, Suggested Order, Estimate Summary, Track.
Port of exportXLSX() (Renovation_Planner_v2.html:1564-1646)."""

from __future__ import annotations

import datetime
from pathlib import Path

from openpyxl import Workbook

from renovator.domain.models import LineType, Plan, TaskLine
from renovator.engine.cost import grand_total, group_sums, item_cost
from renovator.engine.dependencies import suggested_order
from renovator.engine.materials import material_lines
from renovator.engine.schedule import compute_schedule, stage_order


def _write_sheet(wb: Workbook, title: str, rows: list[dict]) -> None:
    ws = wb.create_sheet(title=title[:31])
    if not rows:
        return
    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])


def export_plan_to_excel(plan: Plan, out_path: Path) -> Path:
    wb = Workbook()
    wb.remove(wb.active)  # openpyxl creates a default "Sheet" we don't want

    rate_by_key = {r.key: r for r in plan.rates}
    phase_by_id = {p.id: p.label for p in plan.phases}
    stage_by_id = {s.id: s.label for s in plan.stages}
    item_by_id = {it.id: it for it in plan.items}

    def dep_tag(x: TaskLine) -> str:
        return f"{x.room} - {x.name} [{x.line_type.value}]"

    def deps_str(it: TaskLine) -> str:
        return "; ".join(dep_tag(item_by_id[d]) for d in it.depends_on if d in item_by_id)

    schedule = compute_schedule(plan)
    task_by_line_id = {line.id: t for t in schedule.task_list for line in t.lines}

    def start_for(it: TaskLine) -> str:
        t = task_by_line_id.get(it.id)
        s = schedule.tasks.get(t.task_id) if t else None
        return s.start.isoformat() if s else ""

    def end_for(it: TaskLine) -> str:
        t = task_by_line_id.get(it.id)
        s = schedule.tasks.get(t.task_id) if t else None
        return s.end.isoformat() if s else ""

    # Project
    _write_sheet(
        wb,
        "Project",
        [
            {"Setting": "Project start", "Value": plan.settings.project_start or ""},
            {"Setting": "Work weekends", "Value": "Yes" if plan.settings.work_weekends else "No"},
            {"Setting": "Cascade stages", "Value": "Yes" if plan.settings.sequence_stages else "No"},
        ],
    )

    # Rate Card
    _write_sheet(
        wb,
        "Rate Card",
        [{"Rate": r.label, "Unit": r.unit, "Rate (INR)": r.value} for r in plan.rates],
    )

    # Phases / Stages master lists (order preserved so empty ones survive a round-trip)
    _write_sheet(
        wb, "Phases", [{"Order": i + 1, "Phase": p.label} for i, p in enumerate(plan.phases)]
    )
    _write_sheet(
        wb, "Stages", [{"Order": i + 1, "Stage": s.label} for i, s in enumerate(plan.stages)]
    )

    # Rooms & Items
    item_rows = []
    for it in plan.items:
        rate = rate_by_key.get(it.rate_key) if it.cost_method.value == "rate" else None
        item_rows.append(
            {
                "Room": it.room,
                "Item": it.name,
                "Category": it.category,
                "Line Type": it.line_type.value,
                "Worker/Trade": it.worker_type,
                "Mandatory/Optional": "Mandatory" if it.mandatory else "Optional",
                "Costing Method": "Rate x Qty" if it.cost_method.value == "rate" else "Flat Amount",
                "Rate Used": rate.label if rate else "",
                "Quantity": it.qty if it.cost_method.value == "rate" else "",
                "Est. Cost (INR)": item_cost(plan, it),
                "Stage": stage_by_id.get(it.stage_id, ""),
                "Phase": phase_by_id.get(it.phase, ""),
                "Duration (days)": it.duration_days if it.duration_days is not None else "",
                "Fixed Start": it.start_override or "",
                "Buy Status": it.buy_status.value if it.line_type == LineType.MATERIAL else "",
                "Depends On": deps_str(it),
                "Status": it.status.value,
                "Actual Cost (INR)": it.actual_cost if it.actual_cost is not None else "",
                "Notes": it.notes or "",
                "Task ID": it.task_id or it.id,
            }
        )
    _write_sheet(wb, "Rooms & Items", item_rows)

    # Schedule — sorted by computed start date, then stage order
    def sched_sort_key(it: TaskLine):
        t = task_by_line_id.get(it.id)
        s = schedule.tasks.get(t.task_id) if t else None
        return (s.start if s else datetime.date.min, stage_order(plan, it.stage_id))

    sched_rows = [
        {
            "Start": start_for(it),
            "End": end_for(it),
            "Stage": stage_by_id.get(it.stage_id, ""),
            "Phase": phase_by_id.get(it.phase, ""),
            "Room": it.room,
            "Item": it.name,
            "Line Type": it.line_type.value,
            "Trade": it.worker_type,
            "Duration (days)": it.duration_days if it.duration_days is not None else "",
            "Depends On": deps_str(it),
        }
        for it in sorted(plan.items, key=sched_sort_key)
    ]
    _write_sheet(wb, "Schedule", sched_rows)

    # Materials
    mat_rows = [
        {
            "Need By": r.need_by.isoformat() if r.need_by else "",
            "Material": r.line.name,
            "Room": r.line.room,
            "Quantity": r.qty if r.qty is not None else "",
            "Unit": r.unit or "",
            "Est. Cost (INR)": r.cost,
            "Buy Status": r.line.buy_status.value,
            "Vendor / Note": r.line.notes or "",
        }
        for r in material_lines(plan)
    ]
    mat_rows.sort(key=lambda r: (r["Need By"] == "", r["Need By"]))
    _write_sheet(wb, "Materials", mat_rows or [{"Need By": "", "Material": "(no material lines)"}])

    # Suggested Order
    order_rows = [
        {"Step": i + 1, "Room": it.room, "Item": it.name, "Line Type": it.line_type.value}
        for i, it in enumerate(suggested_order(plan))
    ]
    _write_sheet(wb, "Suggested Order", order_rows)

    # Estimate Summary — "By Trade" uses the raw worker_type string, unlike
    # the UI's Estimate tab, which buckets by trade_bucket(...).name (§4.6
    # of the design doc's estimate_summary docstring).
    items = plan.items
    by_room = group_sums(plan, items, lambda i: i.room)
    by_trade = group_sums(plan, items, lambda i: i.worker_type or "—")
    by_phase = group_sums(plan, items, lambda i: phase_by_id.get(i.phase, "Unassigned"))
    summary_rows = [
        {"Section": "GRAND TOTAL", "Key": "", "Amount (INR)": grand_total(plan, items)},
        {
            "Section": "Mandatory vs Optional",
            "Key": "Mandatory",
            "Amount (INR)": grand_total(plan, [i for i in items if i.mandatory]),
        },
        {"Section": "", "Key": "Optional", "Amount (INR)": grand_total(plan, [i for i in items if not i.mandatory])},
        {
            "Section": "",
            "Key": "Materials",
            "Amount (INR)": grand_total(plan, [i for i in items if i.line_type == LineType.MATERIAL]),
        },
        *[{"Section": "By Room", "Key": k, "Amount (INR)": v} for k, v in by_room],
        *[{"Section": "By Trade", "Key": k, "Amount (INR)": v} for k, v in by_trade],
        *[{"Section": "By Phase", "Key": k, "Amount (INR)": v} for k, v in by_phase],
    ]
    _write_sheet(wb, "Estimate Summary", summary_rows)

    # Track
    track_rows = [
        {
            "Room": it.room,
            "Item": it.name,
            "Trade": it.worker_type,
            "Est. Cost (INR)": item_cost(plan, it),
            "Actual Cost (INR)": it.actual_cost if it.actual_cost is not None else "",
            "Status": it.status.value,
            "Notes": it.notes or "",
        }
        for it in plan.items
    ]
    _write_sheet(wb, "Track", track_rows)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    return out_path
