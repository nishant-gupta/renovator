"""The 10 template jobs from feature.md §4.2. Port of TEMPLATES()/
pickTemplate() (Renovation_Planner_v2.html:340-351,1396-1415).

Templates prefill category, trade, and structure — the user (or agent)
still supplies room and, once known, quantity, matching feature.md §4.2:
"you just set the room, name, quantity, and dates." `instantiate_template`
therefore creates the task with qty left at 0 on any rate-costed line when
`qty` isn't supplied, exactly like the reference app's blank template draft.
"""

from __future__ import annotations

from dataclasses import dataclass

from renovator.domain.models import CostMethod, LineType, Plan
from renovator.domain.seed import CATEGORY_DURATION, trade_for
from renovator.tools.crud_tools import LineInput, TaskInput, create_task
from renovator.tools.errors import ValidationError


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    category: str
    unit: str
    split: bool
    material_rate_key: str | None = None
    labor_rate_key: str | None = None
    single_line_type: LineType = LineType.INCLUSIVE
    single_rate_key: str | None = None
    flat: bool = False


def _templates() -> list[Template]:
    return [
        Template("fresh_paint", "Fresh paint", "Painting", "sqft", True, "paint_material", "paint_labor"),
        Template("retile", "Re-tile wall / floor", "Tiling", "sqft", True, "tile_material", "tile_labor"),
        Template("wall_repair_pop", "Wall repair + POP", "Civil/POP", "sqft", True, "civil_material", "civil_labor"),
        Template("flooring", "Flooring", "Flooring", "sqft", True, "tile_material", "tile_labor"),
        Template(
            "electrical_points",
            "Electrical points / fixtures",
            "Electrical",
            "point",
            True,
            "electrical_material",
            "electrical_labor",
        ),
        Template(
            "countertop_granite",
            "Countertop (granite)",
            "Civil/Carpentry",
            "sqft",
            True,
            "granite_material",
            "granite_labor",
        ),
        Template(
            "glass_shower_partition",
            "Glass shower partition",
            "Plumbing/Glasswork",
            "sqft",
            True,
            "glass_material",
            "glass_labor",
        ),
        Template(
            "tv_storage_unit",
            "TV / storage unit",
            "Carpentry",
            "sqft",
            False,
            single_rate_key="carpenter",
        ),
        Template(
            "skirting",
            "Skirting",
            "Carpentry",
            "running ft",
            False,
            single_rate_key="skirting",
        ),
        Template(
            "custom_purchase",
            "Custom purchase / fixture",
            "Furnishing",
            "",
            False,
            flat=True,
        ),
    ]


_BY_ID = {t.id: t for t in _templates()}


def list_templates() -> list[dict]:
    return [
        {
            "id": t.id,
            "name": t.name,
            "category": t.category,
            "unit": t.unit,
            "structure": "split" if t.split else "single",
        }
        for t in _templates()
    ]


def instantiate_template(
    plan: Plan,
    template_id: str,
    room: str,
    name: str | None = None,
    qty: float | None = None,
    phase: int | None = None,
    stage_id: int | None = None,
) -> Plan:
    tpl = _BY_ID.get(template_id)
    if not tpl:
        raise ValidationError(f"No such template: {template_id}")

    resolved_phase = phase if phase is not None else (plan.phases[0].id if plan.phases else None)
    if resolved_phase is None:
        raise ValidationError("Plan has no phases to assign the new task to.")
    duration_days = CATEGORY_DURATION.get(tpl.category, 2)

    if tpl.split:
        material = LineInput(worker_type="Material")
        labor = LineInput(worker_type=trade_for(tpl.category, LineType.LABOR))
        if tpl.material_rate_key:
            material.cost_method = CostMethod.RATE
            material.rate_key = tpl.material_rate_key
            material.qty = qty
        if tpl.labor_rate_key:
            labor.cost_method = CostMethod.RATE
            labor.rate_key = tpl.labor_rate_key
            labor.qty = qty
        task_input = TaskInput(
            room=room,
            name=name or tpl.name,
            category=tpl.category,
            phase=resolved_phase,
            stage_id=stage_id,
            duration_days=duration_days,
            structure="split",
            material=material,
            labor=labor,
        )
    else:
        single = LineInput(worker_type=trade_for(tpl.category, tpl.single_line_type))
        if tpl.single_rate_key:
            single.cost_method = CostMethod.RATE
            single.rate_key = tpl.single_rate_key
            single.qty = qty
        elif tpl.flat:
            single.cost_method = CostMethod.CUSTOM
        task_input = TaskInput(
            room=room,
            name=name or tpl.name,
            category=tpl.category,
            phase=resolved_phase,
            stage_id=stage_id,
            duration_days=duration_days,
            structure="single",
            single_line_type=tpl.single_line_type,
            single=single,
        )

    return create_task(plan, task_input)
