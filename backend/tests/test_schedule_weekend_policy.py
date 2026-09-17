"""Unit tests for WeekendPolicy.SATURDAYS and blocked_dates — both new
capabilities with no reference-app equivalent (the static app only ever had
an on/off work_weekends toggle), so there's no golden fixture to check
against; these are direct engine-level tests instead. NONE/ALL parity with
the reference app is still covered by test_engine_golden.py.
"""

from __future__ import annotations

import datetime

from renovator.domain.models import (
    Phase,
    Plan,
    ProjectSettings,
    Rate,
    Stage,
    TaskLine,
    WeekendPolicy,
)
from renovator.engine.schedule import add_working_days, compute_schedule, next_workday


def _plan(**settings_overrides) -> Plan:
    settings = ProjectSettings(project_start="2026-01-05", **settings_overrides)  # a Monday
    return Plan(
        settings=settings,
        rooms=["Kitchen"],
        rates=[Rate(key="paint", label="Paint", unit="sqft", value=10)],
        phases=[Phase(id=1, label="Now")],
        stages=[Stage(id=1, label="Painting")],
        items=[],
    )


def test_saturdays_policy_treats_saturday_as_a_workday_but_not_sunday():
    saturday = datetime.date(2026, 1, 10)
    sunday = datetime.date(2026, 1, 11)
    assert next_workday(saturday, WeekendPolicy.SATURDAYS) == saturday
    assert next_workday(sunday, WeekendPolicy.SATURDAYS) == datetime.date(2026, 1, 12)


def test_none_policy_skips_both_weekend_days():
    saturday = datetime.date(2026, 1, 10)
    assert next_workday(saturday, WeekendPolicy.NONE) == datetime.date(2026, 1, 12)


def test_all_policy_skips_nothing():
    sunday = datetime.date(2026, 1, 11)
    assert next_workday(sunday, WeekendPolicy.ALL) == sunday


def test_blocked_date_is_skipped_even_on_a_weekday():
    monday = datetime.date(2026, 1, 5)
    assert next_workday(monday, WeekendPolicy.ALL, frozenset({"2026-01-05"})) == datetime.date(2026, 1, 6)


def test_add_working_days_counts_saturday_under_saturdays_policy():
    # Mon 1/5 + 6 working days, Saturdays count, Sunday doesn't:
    # Mon Tue Wed Thu Fri Sat = 6 days, landing on Sat 1/10 (no Sunday involved).
    start = datetime.date(2026, 1, 5)
    end = add_working_days(start, 6, WeekendPolicy.SATURDAYS)
    assert end == datetime.date(2026, 1, 10)


def test_add_working_days_skips_a_blocked_date_mid_span():
    # Mon-Fri (1/5-1/9) is 5 workdays under NONE; blocking Wednesday pushes
    # the 5th working day out to the following Monday.
    start = datetime.date(2026, 1, 5)
    end_unblocked = add_working_days(start, 5, WeekendPolicy.NONE)
    assert end_unblocked == datetime.date(2026, 1, 9)  # Friday

    end_blocked = add_working_days(start, 5, WeekendPolicy.NONE, frozenset({"2026-01-07"}))  # Wednesday
    assert end_blocked == datetime.date(2026, 1, 12)  # Monday


def test_compute_schedule_pushes_a_task_past_a_blocked_holiday():
    plan = _plan(weekend_policy=WeekendPolicy.NONE, blocked_dates=["2026-01-05", "2026-01-06"])
    item = TaskLine(
        id="line1",
        task_id="task1",
        room="Kitchen",
        name="Paint walls",
        category="Painting",
        phase=1,
        stage_id=1,
        duration_days=1,
        cost_method="rate",
        rate_key="paint",
        qty=10,
    )
    plan.items = [item]

    schedule = compute_schedule(plan)
    scheduled = schedule.tasks["task1"]
    # project_start is Monday 1/5, but 1/5 and 1/6 are blocked -> first
    # available workday is Wednesday 1/7.
    assert scheduled.start == datetime.date(2026, 1, 7)
    assert scheduled.end == datetime.date(2026, 1, 7)


def test_compute_schedule_with_legacy_work_weekends_true_matches_all_policy():
    # A plan loaded from before weekend_policy existed (§4.7 migration).
    legacy = Plan(
        settings={"project_start": "2026-01-05", "work_weekends": True, "sequence_stages": True},
        rooms=["Kitchen"],
        rates=[],
        phases=[Phase(id=1, label="Now")],
        stages=[Stage(id=1, label="Painting")],
        items=[
            TaskLine(
                id="line1",
                task_id="task1",
                room="Kitchen",
                name="Paint walls",
                category="Painting",
                phase=1,
                stage_id=1,
                duration_days=2,
                cost_method="custom",
                custom_amount=100,
            )
        ],
    )
    schedule = compute_schedule(legacy)
    scheduled = schedule.tasks["task1"]
    # Mon + 2 days with every day a workday -> Mon, Tue.
    assert scheduled.start == datetime.date(2026, 1, 5)
    assert scheduled.end == datetime.date(2026, 1, 6)
