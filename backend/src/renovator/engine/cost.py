"""Costing helpers. Port of itemCost()/grandTotal()/groupSums()/tradeBucket()
and the Estimate-tab derivations (Renovation_Planner_v2.html:322-336,546-549,1072-1084)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from renovator.domain.models import CostMethod, LineType, Plan, TaskLine


def item_cost(plan: Plan, line: TaskLine) -> float:
    if line.cost_method == CostMethod.RATE:
        rate = next((r for r in plan.rates if r.key == line.rate_key), None)
        return (rate.value if rate else 0) * (line.qty or 0)
    return line.custom_amount or 0


def grand_total(plan: Plan, lines: list[TaskLine]) -> float:
    return sum(item_cost(plan, line) for line in lines)


@dataclass(frozen=True)
class TradeBucket:
    key: str
    name: str


# Renovation_Planner_v2.html:322-331 — order matters, first match wins.
_TRADE_BUCKETS: list[tuple[re.Pattern, TradeBucket]] = [
    (re.compile(r"glass", re.IGNORECASE), TradeBucket("glass", "Glass")),
    (re.compile(r"plumb", re.IGNORECASE), TradeBucket("plumber", "Plumber")),
    (re.compile(r"electr", re.IGNORECASE), TradeBucket("electric", "Electrician")),
    (re.compile(r"tile|tiling", re.IGNORECASE), TradeBucket("tiling", "Tiling")),
    (re.compile(r"paint", re.IGNORECASE), TradeBucket("painter", "Painter")),
    (re.compile(r"carpenter|carpentry|furnish|vendor", re.IGNORECASE), TradeBucket("carpenter", "Carpenter")),
    (re.compile(r"mason|civil|pop|floor", re.IGNORECASE), TradeBucket("mason", "Mason / Civil")),
    (re.compile(r"material", re.IGNORECASE), TradeBucket("material", "Material")),
]


def trade_bucket(text: str | None) -> TradeBucket:
    s = text or ""
    for pattern, bucket in _TRADE_BUCKETS:
        if pattern.search(s):
            return bucket
    return TradeBucket("other", s.strip() or "Other")


def group_sums(plan: Plan, lines: list[TaskLine], key_fn) -> list[tuple[str, float]]:
    """Port of groupSums() (line 1072) — sums itemCost per key, sorted desc by value."""
    totals: dict[str, float] = {}
    for line in lines:
        k = key_fn(line)
        totals[k] = totals.get(k, 0) + item_cost(plan, line)
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)


def estimate_summary(plan: Plan) -> dict:
    """Port of renderEstimateTab()'s derivations (Renovation_Planner_v2.html:1077-1111).

    `by_trade` buckets by trade_bucket(workerType or category).name, matching
    what the UI groups/colours by. This differs from the Excel "By Trade"
    sheet, which groups by the raw worker_type string (see io/excel_export.py).
    """
    items = plan.items
    phases_by_id = {p.id: p.label for p in plan.phases}

    total = grand_total(plan, items)
    mandatory = grand_total(plan, [i for i in items if i.mandatory])
    optional = grand_total(plan, [i for i in items if not i.mandatory])
    materials = grand_total(plan, [i for i in items if i.line_type == LineType.MATERIAL])

    by_room = group_sums(plan, items, lambda i: i.room)
    by_trade = group_sums(plan, items, lambda i: trade_bucket(i.worker_type or i.category).name)
    by_phase = group_sums(plan, items, lambda i: phases_by_id.get(i.phase, "Unassigned"))

    return {
        "total": total,
        "mandatory": mandatory,
        "optional": optional,
        "materials": materials,
        "by_room": by_room,
        "by_trade": by_trade,
        "by_phase": by_phase,
    }
