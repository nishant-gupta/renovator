"""Unit tests for cross-project task transfer (tools/transfer_tools.py)."""

from __future__ import annotations

import pytest

from renovator.domain.models import Phase, Plan, ProjectSettings, Rate, Stage, TaskLine
from renovator.tools import crud_tools as ct
from renovator.tools.errors import ValidationError
from renovator.tools.transfer_tools import transfer_tasks


def _plan(**overrides) -> Plan:
    defaults = {
        "settings": ProjectSettings(project_start="2026-01-01"),
        "rooms": ["Kitchen"],
        "rates": [Rate(key="paint", label="Paint", unit="sqft", value=10)],
        "phases": [Phase(id=1, label="Now"), Phase(id=2, label="Later")],
        "stages": [Stage(id=1, label="Painting")],
        "items": [],
    }
    defaults.update(overrides)
    return Plan(**defaults)


def test_copy_task_leaves_source_untouched_and_adds_to_target():
    source = _plan()
    ct.create_task(
        source,
        ct.TaskInput(
            room="Kitchen", name="Paint wall", category="Painting", phase=1, stage_id=1,
            single=ct.LineInput(cost_method="rate", rate_key="paint", qty=50),
        ),
    )
    task_id = source.items[0].task_id
    target = _plan(rooms=[], rates=[], phases=[Phase(id=1, label="Someday")], stages=[])

    result = transfer_tasks(source, target, [task_id], mode="copy")

    assert result.transferred_task_count == 1
    assert len(source.items) == 1  # untouched
    assert len(target.items) == 1
    new_line = target.items[0]
    assert new_line.name == "Paint wall"
    assert new_line.id != source.items[0].id
    # room/rate/stage didn't exist in target -> created
    assert "Kitchen" in target.rooms
    assert any(r.label == "Paint" for r in target.rates)
    assert any(s.label == "Painting" for s in target.stages)
    assert result.created_rooms == ["Kitchen"]
    assert result.created_rates == ["Paint"]
    assert result.created_stages == ["Painting"]


def test_move_task_removes_from_source():
    source = _plan()
    ct.create_task(
        source,
        ct.TaskInput(room="Kitchen", name="Paint wall", category="Painting", phase=1, single=ct.LineInput()),
    )
    task_id = source.items[0].task_id
    target = _plan()

    transfer_tasks(source, target, [task_id], mode="move")

    assert source.items == []
    assert len(target.items) == 1


def test_reuses_existing_room_and_rate_by_label_instead_of_duplicating():
    source = _plan()
    ct.create_task(
        source,
        ct.TaskInput(
            room="Kitchen", name="Paint wall", category="Painting", phase=1,
            single=ct.LineInput(cost_method="rate", rate_key="paint", qty=50),
        ),
    )
    task_id = source.items[0].task_id
    target = _plan(rooms=["Kitchen"], rates=[Rate(key="p2", label="Paint", unit="sqft", value=99)])

    result = transfer_tasks(source, target, [task_id], mode="copy")

    assert target.rooms == ["Kitchen"]  # not duplicated
    assert len(target.rates) == 1  # reused target's existing "Paint" rate, not a new one
    assert target.items[0].rate_key == "p2"
    assert result.created_rooms == []
    assert result.created_rates == []


def test_dependency_within_transferred_set_is_relinked():
    source = _plan()
    a = TaskLine(id="a", task_id="task_a", room="Kitchen", name="A", category="Other", phase=1)
    b = TaskLine(id="b", task_id="task_b", room="Kitchen", name="B", category="Other", phase=1, depends_on=["a"])
    source.items = [a, b]
    target = _plan()

    transfer_tasks(source, target, ["task_a", "task_b"], mode="copy")

    b_new = next(it for it in target.items if it.name == "B")
    a_new = next(it for it in target.items if it.name == "A")
    assert b_new.depends_on == [a_new.id]


def test_dependency_outside_transferred_set_is_dropped():
    source = _plan()
    a = TaskLine(id="a", task_id="task_a", room="Kitchen", name="A", category="Other", phase=1)
    b = TaskLine(id="b", task_id="task_b", room="Kitchen", name="B", category="Other", phase=1, depends_on=["a"])
    source.items = [a, b]
    target = _plan()

    # only transfer B, whose dependency on A is not part of the set
    result = transfer_tasks(source, target, ["task_b"], mode="copy")

    b_new = target.items[0]
    assert b_new.depends_on == []
    assert result.dropped_dependencies == 1


def test_transfer_to_same_plan_rejected():
    plan = _plan()
    ct.create_task(plan, ct.TaskInput(room="Kitchen", name="X", category="Other", phase=1, single=ct.LineInput()))
    with pytest.raises(ValidationError):
        transfer_tasks(plan, plan, [plan.items[0].task_id], mode="copy")


def test_transfer_no_matching_tasks_rejected():
    source, target = _plan(), _plan()
    with pytest.raises(ValidationError):
        transfer_tasks(source, target, ["does-not-exist"], mode="copy")


def test_transfer_invalid_mode_rejected():
    source = _plan()
    ct.create_task(source, ct.TaskInput(room="Kitchen", name="X", category="Other", phase=1, single=ct.LineInput()))
    target = _plan()
    with pytest.raises(ValidationError):
        transfer_tasks(source, target, [source.items[0].task_id], mode="swap")
