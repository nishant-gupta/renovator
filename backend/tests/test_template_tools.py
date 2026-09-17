"""Unit tests for the template picker tools (feature.md §4.2)."""

from __future__ import annotations

import pytest

from renovator.domain.models import Phase, Plan, ProjectSettings
from renovator.tools import template_tools as tt
from renovator.tools.errors import ValidationError


def _minimal_plan() -> Plan:
    return Plan(
        settings=ProjectSettings(project_start="2026-01-01"),
        rooms=["Kitchen"],
        phases=[Phase(id=1, label="Now")],
    )


def test_list_templates_has_ten_entries():
    templates = tt.list_templates()
    assert len(templates) == 10
    assert {"fresh_paint", "custom_purchase", "skirting"} <= {t["id"] for t in templates}


def test_unknown_template_rejected():
    plan = _minimal_plan()
    with pytest.raises(ValidationError):
        tt.instantiate_template(plan, "does_not_exist", room="Kitchen")


def test_split_template_creates_material_and_labor_with_trade_and_rate():
    plan = _minimal_plan()
    tt.instantiate_template(plan, "retile", room="Kitchen", qty=40)
    assert len(plan.items) == 2
    material = next(it for it in plan.items if it.line_type.value == "Material")
    labor = next(it for it in plan.items if it.line_type.value == "Labor")
    assert material.rate_key == "tile_material" and material.qty == 40
    assert labor.rate_key == "tile_labor" and labor.qty == 40
    assert labor.worker_type == "Tile Installer"


def test_single_rate_template_tv_unit():
    plan = _minimal_plan()
    tt.instantiate_template(plan, "tv_storage_unit", room="Kitchen", qty=52)
    assert len(plan.items) == 1
    line = plan.items[0]
    assert line.rate_key == "carpenter"
    assert line.qty == 52
    assert line.worker_type == "Carpenter"


def test_flat_template_custom_purchase_has_no_rate():
    plan = _minimal_plan()
    tt.instantiate_template(plan, "custom_purchase", room="Kitchen", name="Curtains")
    line = plan.items[0]
    assert line.cost_method.value == "custom"
    assert line.rate_key is None
    assert line.name == "Curtains"


def test_template_defaults_duration_from_category():
    plan = _minimal_plan()
    tt.instantiate_template(plan, "fresh_paint", room="Kitchen")
    # Painting -> CATEGORY_DURATION 2, applied to both split lines' shared duration.
    assert plan.items[0].duration_days == 2
