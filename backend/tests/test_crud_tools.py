"""Unit tests for the Phase 2 tool layer (design doc §4.5), covering the
validation/confirmation contract from errors.py against both the golden
fixture plan and small synthetic plans for edge cases."""

from __future__ import annotations

import pytest

from renovator.domain.models import Phase, Plan, ProjectSettings, Stage, TaskLine
from renovator.tools import crud_tools as ct
from renovator.tools.errors import ConfirmationRequired, ValidationError


def _minimal_plan(**overrides) -> Plan:
    defaults = {
        "settings": ProjectSettings(project_start="2026-01-01"),
        "rooms": ["Kitchen"],
        "phases": [Phase(id=1, label="Now"), Phase(id=2, label="Later")],
        "stages": [Stage(id=1, label="Civil"), Stage(id=2, label="Paint")],
        "items": [],
    }
    defaults.update(overrides)
    return Plan(**defaults)


# ---- Rooms ----------------------------------------------------------------


def test_add_room_rejects_duplicate():
    plan = _minimal_plan()
    ct.add_room(plan, "Bathroom")
    assert "Bathroom" in plan.rooms
    with pytest.raises(ValidationError):
        ct.add_room(plan, "Bathroom")


def test_rename_room_cascades_to_items():
    plan = _minimal_plan(
        items=[TaskLine(room="Kitchen", name="Paint", category="Painting", phase=1)]
    )
    ct.rename_room(plan, "Kitchen", "Kitchen (Renovated)")
    assert plan.rooms == ["Kitchen (Renovated)"]
    assert plan.items[0].room == "Kitchen (Renovated)"


def test_remove_room_blocked_when_in_use():
    plan = _minimal_plan(
        items=[TaskLine(room="Kitchen", name="Paint", category="Painting", phase=1)]
    )
    with pytest.raises(ValidationError):
        ct.remove_room(plan, "Kitchen", confirm=True)


def test_remove_room_requires_confirmation_when_unused():
    plan = _minimal_plan()
    with pytest.raises(ConfirmationRequired):
        ct.remove_room(plan, "Kitchen")
    ct.remove_room(plan, "Kitchen", confirm=True)
    assert plan.rooms == []


# ---- Rates ------------------------------------------------------------------


def test_delete_rate_in_use_requires_confirmation_then_zeroes_cost(golden_plan):
    from renovator.engine.cost import item_cost

    rate_line = next(it for it in golden_plan.items if it.rate_key)
    key = rate_line.rate_key
    with pytest.raises(ConfirmationRequired):
        ct.delete_rate(golden_plan, key)
    ct.delete_rate(golden_plan, key, confirm=True)
    assert not any(r.key == key for r in golden_plan.rates)
    assert item_cost(golden_plan, rate_line) == 0


def test_delete_rate_unused_needs_no_confirmation():
    plan = _minimal_plan()
    ct.add_rate(plan, "Paint", "sqft", 10)
    key = plan.rates[0].key
    ct.delete_rate(plan, key)  # no confirm needed, not in use
    assert plan.rates == []


# ---- Phases ------------------------------------------------------------------


def test_remove_phase_requires_at_least_one():
    plan = _minimal_plan(phases=[Phase(id=1, label="Only")])
    with pytest.raises(ValidationError):
        ct.remove_phase(plan, 1, confirm=True)


def test_remove_phase_reassigns_tasks_to_fallback():
    plan = _minimal_plan(
        items=[TaskLine(room="Kitchen", name="Paint", category="Painting", phase=1)]
    )
    with pytest.raises(ConfirmationRequired):
        ct.remove_phase(plan, 1)
    ct.remove_phase(plan, 1, confirm=True)
    assert [p.id for p in plan.phases] == [2]
    assert plan.items[0].phase == 2


def test_move_phase_swaps_order():
    plan = _minimal_plan()
    ct.move_phase(plan, 0, 1)
    assert [p.label for p in plan.phases] == ["Later", "Now"]


# ---- Stages ------------------------------------------------------------------


def test_remove_stage_unassigns_tasks():
    plan = _minimal_plan(
        items=[TaskLine(room="Kitchen", name="Paint", category="Painting", phase=1, stage_id=1)]
    )
    with pytest.raises(ConfirmationRequired):
        ct.remove_stage(plan, 1)
    ct.remove_stage(plan, 1, confirm=True)
    assert plan.items[0].stage_id is None
    assert [s.id for s in plan.stages] == [2]


# ---- Tasks -------------------------------------------------------------------


def test_create_single_task():
    plan = _minimal_plan()
    ti = ct.TaskInput(
        room="Kitchen",
        name="Fresh paint",
        category="Painting",
        phase=1,
        single=ct.LineInput(cost_method="custom", custom_amount=5000),
    )
    ct.create_task(plan, ti)
    assert len(plan.items) == 1
    assert plan.items[0].name == "Fresh paint"
    assert plan.items[0].task_id is not None


def test_create_task_rejects_explicit_task_id():
    plan = _minimal_plan()
    ti = ct.TaskInput(task_id="task_x", room="Kitchen", name="x", category="Other", phase=1, single=ct.LineInput())
    with pytest.raises(ValidationError):
        ct.create_task(plan, ti)


def test_split_task_creates_material_and_labor_lines():
    plan = _minimal_plan()
    ti = ct.TaskInput(
        room="Kitchen",
        name="Re-tile",
        category="Tiling",
        phase=1,
        structure="split",
        material=ct.LineInput(cost_method="custom", custom_amount=3000),
        labor=ct.LineInput(cost_method="custom", custom_amount=2000),
    )
    ct.create_task(plan, ti)
    assert len(plan.items) == 2
    types = {it.line_type.value for it in plan.items}
    assert types == {"Material", "Labor"}
    assert plan.items[0].task_id == plan.items[1].task_id


def test_update_task_switching_split_to_single_drops_a_line_and_its_dependents():
    plan = _minimal_plan()
    ti = ct.TaskInput(
        room="Kitchen",
        name="Re-tile",
        category="Tiling",
        phase=1,
        structure="split",
        material=ct.LineInput(cost_method="custom", custom_amount=3000),
        labor=ct.LineInput(cost_method="custom", custom_amount=2000),
    )
    ct.create_task(plan, ti)
    task_id = plan.items[0].task_id
    material_id = next(it.id for it in plan.items if it.line_type.value == "Material")

    # a third, independent task depends on the material line
    other = TaskLine(
        room="Kitchen", name="Countertop", category="Other", phase=1, depends_on=[material_id]
    )
    plan.items.append(other)

    # now edit the re-tile task down to a single line — the material line is dropped
    labor_id = next(it.id for it in plan.items if it.line_type.value == "Labor")
    ti2 = ct.TaskInput(
        task_id=task_id,
        room="Kitchen",
        name="Re-tile",
        category="Tiling",
        phase=1,
        structure="single",
        single=ct.LineInput(id=labor_id, cost_method="custom", custom_amount=2000),
    )
    ct.update_task(plan, ti2)

    assert len(plan.items) == 2  # the single re-tile line + the countertop line
    countertop = next(it for it in plan.items if it.name == "Countertop")
    assert countertop.depends_on == []  # stale dependency on the dropped material line is gone


def test_create_task_with_circular_dependency_rejected():
    plan = _minimal_plan()
    a = TaskLine(id="a", room="Kitchen", name="A", category="Other", phase=1)
    b = TaskLine(id="b", room="Kitchen", name="B", category="Other", phase=1, depends_on=["a"])
    plan.items = [a, b]
    ti = ct.TaskInput(
        task_id=None,
        room="Kitchen",
        name="C",
        category="Other",
        phase=1,
        single=ct.LineInput(depends_on=["b"]),
    )
    # not a cycle yet — sanity check it succeeds
    ct.create_task(plan, ti)

    # now try to make "a" depend on the new task "C" — that would close a loop
    c_id = next(it.id for it in plan.items if it.name == "C")
    with pytest.raises(ValidationError):
        ct.set_dependencies(plan, "a", [c_id])


def test_delete_task_requires_confirmation_and_cleans_dependents():
    plan = _minimal_plan()
    a = TaskLine(id="a", room="Kitchen", name="A", category="Other", phase=1, task_id="task_a")
    b = TaskLine(
        id="b", room="Kitchen", name="B", category="Other", phase=1, task_id="task_b", depends_on=["a"]
    )
    plan.items = [a, b]
    with pytest.raises(ConfirmationRequired):
        ct.delete_task(plan, "task_a")
    ct.delete_task(plan, "task_a", confirm=True)
    assert len(plan.items) == 1
    assert plan.items[0].depends_on == []


# ---- Bulk actions -------------------------------------------------------------


def test_bulk_move_to_phase_and_mandatory():
    plan = _minimal_plan()
    a = TaskLine(id="a", room="Kitchen", name="A", category="Other", phase=1, task_id="task_a")
    b = TaskLine(id="b", room="Kitchen", name="B", category="Other", phase=1, task_id="task_b")
    plan.items = [a, b]
    ct.bulk_move_to_phase(plan, ["task_a", "task_b"], 2)
    ct.bulk_set_mandatory(plan, ["task_a"], False)
    assert plan.items[0].phase == 2 and plan.items[1].phase == 2
    assert plan.items[0].mandatory is False
    assert plan.items[1].mandatory is True


def test_bulk_delete_requires_confirmation():
    plan = _minimal_plan()
    a = TaskLine(id="a", room="Kitchen", name="A", category="Other", phase=1, task_id="task_a")
    plan.items = [a]
    with pytest.raises(ConfirmationRequired):
        ct.bulk_delete_tasks(plan, ["task_a"])
    ct.bulk_delete_tasks(plan, ["task_a"], confirm=True)
    assert plan.items == []


# ---- update_line --------------------------------------------------------------


def test_update_line_patches_only_given_fields():
    plan = _minimal_plan()
    line = TaskLine(id="a", room="Kitchen", name="Tiles", category="Tiling", phase=1, notes="old note")
    plan.items = [line]

    ct.update_line(plan, "a", buy_status="Ordered")
    assert plan.items[0].buy_status.value == "Ordered"
    assert plan.items[0].notes == "old note"  # untouched

    ct.update_line(plan, "a", notes="new note", actual_cost=1234)
    assert plan.items[0].notes == "new note"
    assert plan.items[0].actual_cost == 1234
    assert plan.items[0].buy_status.value == "Ordered"  # still untouched by this call


def test_update_line_rejects_unknown_line():
    plan = _minimal_plan()
    with pytest.raises(ValidationError):
        ct.update_line(plan, "does-not-exist", notes="x")


def test_update_line_rejects_invalid_enum_value():
    plan = _minimal_plan()
    line = TaskLine(id="a", room="Kitchen", name="Tiles", category="Tiling", phase=1)
    plan.items = [line]
    with pytest.raises(ValidationError):
        ct.update_line(plan, "a", buy_status="Not A Real Status")
