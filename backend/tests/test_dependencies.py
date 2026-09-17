"""Unit tests for would_create_cycle — not exercised by the golden fixtures,
since valid plan data never contains a cycle in the first place."""

from __future__ import annotations

from renovator.domain.models import Phase, Plan, ProjectSettings, TaskLine
from renovator.engine.dependencies import would_create_cycle


def _plan_with(items: list[TaskLine]) -> Plan:
    return Plan(
        settings=ProjectSettings(project_start="2026-01-01"),
        phases=[Phase(id=1, label="Now")],
        items=items,
    )


def _line(id_: str, depends_on: list[str] | None = None) -> TaskLine:
    return TaskLine(id=id_, room="Room", name=id_, category="Other", phase=1, depends_on=depends_on or [])


def test_no_cycle_for_independent_chain():
    a, b, c = _line("a"), _line("b", ["a"]), _line("c", ["b"])
    plan = _plan_with([a, b, c])
    assert would_create_cycle(plan, "a", []) is False


def test_direct_self_cycle_detected():
    a = _line("a")
    plan = _plan_with([a])
    assert would_create_cycle(plan, "a", ["a"]) is True


def test_transitive_cycle_detected():
    # a depends on b, b depends on c: proposing c depends on a closes the loop.
    a, b, c = _line("a", ["b"]), _line("b", ["c"]), _line("c")
    plan = _plan_with([a, b, c])
    assert would_create_cycle(plan, "c", ["a"]) is True


def test_diamond_dependency_is_not_a_cycle():
    # a <- b, a <- c, d depends on both b and c: valid DAG, no cycle.
    a = _line("a")
    b = _line("b", ["a"])
    c = _line("c", ["a"])
    d = _line("d", ["b", "c"])
    plan = _plan_with([a, b, c, d])
    assert would_create_cycle(plan, "d", ["b", "c"]) is False
