"""Scheduling engine. Port of computeSchedule() and its date helpers
(Renovation_Planner_v2.html:554-568, 631-676).

Forward pass: project start -> stage cascade (if sequence_stages) -> dependency
finishes -> start_override pin -> working-day duration (skip weekends unless
work_weekends) -> end date. Validated against tests/fixtures/*_golden.json,
generated directly from the reference app's own JS logic (see
backend/scripts/generate_golden_fixture.js) — do not change this module
without regenerating and re-checking against those fixtures.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from renovator.domain.models import Plan
from renovator.engine.tasks import Task, clamp_duration, group_by_task


def iso_date(d: datetime.date) -> str:
    return d.isoformat()


def parse_date(s: str | None) -> datetime.date | None:
    if not s:
        return None
    return datetime.date.fromisoformat(s)


def is_weekend(d: datetime.date) -> bool:
    return d.weekday() in (5, 6)  # Saturday, Sunday


def next_workday(d: datetime.date, work_weekends: bool) -> datetime.date:
    x = d
    if work_weekends:
        return x
    while is_weekend(x):
        x = x + datetime.timedelta(days=1)
    return x


def add_working_days(start: datetime.date, duration_days: int, work_weekends: bool) -> datetime.date:
    """End date after `duration_days` working days starting at `start`
    (Renovation_Planner_v2.html:560-564)."""
    x = next_workday(start, work_weekends)
    count = 1
    while count < duration_days:
        x = x + datetime.timedelta(days=1)
        if not work_weekends:
            while is_weekend(x):
                x = x + datetime.timedelta(days=1)
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
            return next_workday(latest + datetime.timedelta(days=1), plan.settings.work_weekends)
        return default_start

    for tid in ordered:
        t = by_id.get(tid)
        if t is None:
            continue
        s = next_workday(default_start, plan.settings.work_weekends)
        cascade = stage_cascade_start(t)
        s = max(s, cascade)
        for dep_tid in task_deps(t):
            dep_sched = sched.get(dep_tid)
            if dep_sched:
                after = next_workday(dep_sched.end + datetime.timedelta(days=1), plan.settings.work_weekends)
                s = max(s, after)
        if t.start_override:
            ov = parse_date(t.start_override)
            if ov:
                s = next_workday(ov, plan.settings.work_weekends)
        dur = clamp_duration(t.duration_days)
        e = add_working_days(s, dur, plan.settings.work_weekends)
        sched[tid] = ScheduledTask(start=s, end=e, dur=dur)

    return Schedule(tasks=sched, by_id=by_id, task_list=tasks, project_start=default_start)


def project_end_date(schedule: Schedule) -> datetime.date | None:
    if not schedule.tasks:
        return None
    return max(st.end for st in schedule.tasks.values())
