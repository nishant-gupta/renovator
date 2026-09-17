"""Smoke tests for the read-tool JSON shapes against the golden fixture —
the engine's own values are already verified in test_engine_golden.py, this
just checks the wrapper doesn't lose/misshape data."""

from __future__ import annotations

from renovator.tools import read_tools as rt


def test_get_setup_shape(golden_plan):
    out = rt.get_setup(golden_plan)
    assert out["rooms"] == golden_plan.rooms
    assert len(out["rates"]) == len(golden_plan.rates)
    assert len(out["phases"]) == len(golden_plan.phases)
    assert len(out["stages"]) == len(golden_plan.stages)


def test_get_tasks_shape(golden_plan):
    out = rt.get_tasks(golden_plan)
    assert len(out) > 0
    row = out[0]
    assert set(row) >= {"task_id", "room", "name", "lines"}
    assert row["lines"], "expected at least one line per task"
    line = row["lines"][0]
    assert set(line) >= {"line_id", "line_type", "depends_on"}


def test_get_schedule_shape(golden_plan):
    out = rt.get_schedule(golden_plan)
    assert out["project_start"]
    assert out["project_end"]
    assert len(out["tasks"]) == len(golden_plan.items) or len(out["tasks"]) > 0
    row = out["tasks"][0]
    assert set(row) >= {"task_id", "room", "name", "start", "end", "duration_days", "worker_type"}


def test_get_schedule_worker_type_uses_labor_line_for_split_tasks(golden_plan):
    from renovator.engine.tasks import group_by_task

    out = rt.get_schedule(golden_plan)
    by_id = {row["task_id"]: row for row in out["tasks"]}
    for t in group_by_task(golden_plan):
        expected = (t.labor or t.lines[0]).worker_type
        assert by_id[t.task_id]["worker_type"] == expected


def test_get_materials_plan_shape(golden_plan):
    out = rt.get_materials_plan(golden_plan)
    assert out["total"] >= 0
    all_lines = [line for g in out["groups"] for line in g["lines"]]
    assert len(all_lines) == out["to_buy_count"] + sum(
        1 for line in all_lines if line["buy_status"] != "To buy"
    )


def test_get_estimate_summary_includes_task_table(golden_plan):
    out = rt.get_estimate_summary(golden_plan)
    assert out["total"] > 0
    assert out["tasks"], "expected at least one task row"
    costs = [t["total_cost"] for t in out["tasks"]]
    assert costs == sorted(costs, reverse=True)


def test_get_track_summary_variance_none_until_actuals_logged(golden_plan):
    out = rt.get_track_summary(golden_plan)
    assert out["variance"] is None
    assert out["actuals_logged"] == 0

    golden_plan.items[0].actual_cost = 100
    out2 = rt.get_track_summary(golden_plan)
    assert out2["variance"] is not None
    assert out2["actuals_logged"] == 1
