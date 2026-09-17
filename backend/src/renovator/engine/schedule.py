"""Scheduling engine. Port of computeSchedule() and its date helpers
(Renovation_Planner_v2.html:554-568, 631-676).

Forward pass: project start -> stage cascade (if sequence_stages) -> dependency
finishes -> start_override pin -> working-day duration (skip non-workdays per
weekend_policy and blocked_dates) -> end date. Validated against
tests/fixtures/*_golden.json, generated directly from the reference app's own
JS logic (see backend/scripts/generate_golden_fixture.js) — do not change
the weekend-skipping semantics for WeekendPolicy.NONE without regenerating
and re-checking against those fixtures (the reference app only ever had
NONE/ALL; SATURDAYS and blocked_dates are new, with no fixture to match).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from renovator.domain.models import Plan, WeekendPolicy
from renovator.engine.tasks import Task, clamp_duration, group_by_task


def iso_date(d: datetime.date) -> str:
    return d.isoformat()


def parse_date(s: str | None) -> datetime.date | None:
    if not s:
        return None
    return datetime.date.fromisoformat(s)


def _is_weekend_off(d: datetime.date, weekend_policy: WeekendPolicy) -> bool:
    weekday = d.weekday()  # 0=Mon ... 5=Sat, 6=Sun
    if weekend_policy == WeekendPolicy.ALL:
        return False
    if weekend_policy == WeekendPolicy.SATURDAYS:
        return weekday == 6  # only Sunday is off
    return weekday in (5, 6)  # NONE: both Saturday and Sunday are off


def is_workday(d: datetime.date, weekend_policy: WeekendPolicy, blocked_dates: frozenset[str] = frozenset()) -> bool:
    if d.isoformat() in blocked_dates:
        return False
    return not _is_weekend_off(d, weekend_policy)


def next_workday(
    d: datetime.date, weekend_policy: WeekendPolicy, blocked_dates: frozenset[str] = frozenset()
) -> datetime.date:
    x = d
    while not is_workday(x, weekend_policy, blocked_dates):
        x = x + datetime.timedelta(days=1)
    return x


def add_working_days(
    start: datetime.date,
    duration_days: int,
    weekend_policy: WeekendPolicy,
    blocked_dates: frozenset[str] = frozenset(),
) -> datetime.date:
    """End date after `duration_days` working days starting at `start`
    (Renovation_Planner_v2.html:560-564 — extended with blocked_dates,
    no reference-app equivalent)."""
    x = next_workday(start, weekend_policy, blocked_dates)
    count = 1
    while count < duration_days:
        x = x + datetime.timedelta(days=1)
        x = next_workday(x, weekend_policy, blocked_dates)
        count += 1
    return x


def stage_order(plan: Plan, stage_id: int | None) -> int:
    for i, s in enumerate(plan.stages):
        if s.id == stage_id:
            return i
    return 998


@dataclass
class ScheduledTask:
    start: datetime.date
    end: datetime.date
    dur: int


@dataclass
class Schedule:
    tasks: dict[str, ScheduledTask]  # task_id -> ScheduledTask
    by_id: dict[str, Task]
    task_list: list[Task]
    project_start: datetime.date


def compute_schedule(plan: Plan) -> Schedule:
    default_start = parse_date(plan.settings.project_start) or datetime.date.today()
    weekend_policy = plan.settings.weekend_policy
    blocked_dates = frozenset(plan.settings.blocked_dates)
    tasks = group_by_task(plan)
    by_id = {t.task_id: t for t in tasks}

    line_to_task = {i.id: (i.task_id or i.id) for i in plan.items}

    def task_deps(t: Task) -> list[str]:
        deps: list[str] = []
        seen: set[str] = set()
        for line in t.lines:
            for dep_line_id in line.depends_on:
                tid = line_to_task.get(dep_line_id)
                if tid and tid != t.task_id and tid not in seen:
                    seen.add(tid)
                    deps.append(tid)
        return deps

    order_index = {t.task_id: i for i, t in enumerate(tasks)}
    stage_sorted = sorted(tasks, key=lambda t: (stage_order(plan, t.stage_id), order_index[t.task_id]))

    ordered: list[str] = []
    visited: set[str] = set()
    temp: set[str] = set()

    def visit(tid: str) -> None:
        if tid in visited or tid in temp:
            return
        temp.add(tid)
        t = by_id.get(tid)
        if t:
            for dep_tid in task_deps(t):
                if dep_tid in by_id:
                    visit(dep_tid)
        temp.discard(tid)
        visited.add(tid)
        ordered.append(tid)

    for t in stage_sorted:
        visit(t.task_id)

    sched: dict[str, ScheduledTask] = {}

    def stage_cascade_start(t: Task) -> datetime.date:
        if not plan.settings.sequence_stages:
            return default_start
        so = stage_order(plan, t.stage_id)
        latest: datetime.date | None = None
        for tid, st in sched.items():
            other = by_id.get(tid)
            if other and stage_order(plan, other.stage_id) < so and (latest is None or st.end > latest):
                latest = st.end
        if latest is not None:
            return next_workday(latest + datetime.timedelta(days=1), weekend_policy, blocked_dates)
        return default_start

    for tid in ordered:
        t = by_id.get(tid)
        if t is None:
            continue
        s = next_workday(default_start, weekend_policy, blocked_dates)
        cascade = stage_cascade_start(t)
        s = max(s, cascade)
        for dep_tid in task_deps(t):
            dep_sched = sched.get(dep_tid)
            if dep_sched:
                after = next_workday(dep_sched.end + datetime.timedelta(days=1), weekend_policy, blocked_dates)
                s = max(s, after)
        if t.start_override:
            ov = parse_date(t.start_override)
            if ov:
                s = next_workday(ov, weekend_policy, blocked_dates)
        dur = clamp_duration(t.duration_days)
        e = add_working_days(s, dur, weekend_policy, blocked_dates)
        sched[tid] = ScheduledTask(start=s, end=e, dur=dur)

    return Schedule(tasks=sched, by_id=by_id, task_list=tasks, project_start=default_start)


def project_end_date(schedule: Schedule) -> datetime.date | None:
    if not schedule.tasks:
        return None
    return max(st.end for st in schedule.tasks.values())
