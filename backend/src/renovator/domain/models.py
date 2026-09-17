"""Domain schema, ported 1:1 from the `state` object in Renovation_Planner_v2.html.

Field names are snake_case Python equivalents of the JS shape (see
docs/agentic-renovator-design.md §4.3). Nothing here computes anything —
schedule/cost/materials/variance derivations live in `renovator.engine`.

Two things that look wrong at first glance are deliberate, matching the
reference app exactly:

- Rooms are plain strings, not {id, label} objects — `TaskLine.room` holds
  the room name directly (Renovation_Planner_v2.html:392,420-421). Renaming a
  room means rewriting that string on every line that used the old name.
- `LineType.INCLUSIVE` is the type used by ordinary single-line tasks (a
  material+labour-inclusive job, e.g. "TV unit"), not `None`/absent — every
  line is one of Material, Labor, or Inclusive (line 290).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


def new_id(prefix: str) -> str:
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class LineType(str, Enum):
    MATERIAL = "Material"
    LABOR = "Labor"
    INCLUSIVE = "Inclusive"  # single-line task: one line covers material+labour together


class CostMethod(str, Enum):
    RATE = "rate"
    CUSTOM = "custom"  # flat/quoted amount


class BuyStatus(str, Enum):
    TO_BUY = "To buy"
    ORDERED = "Ordered"
    DELIVERED = "Delivered"


class TaskStatus(str, Enum):
    NOT_STARTED = "Not Started"
    IN_PROGRESS = "In Progress"
    ON_HOLD = "On Hold"
    DONE = "Done"


class WeekendPolicy(str, Enum):
    """Which weekend days count as workdays for schedule computation
    (engine/schedule.py). No reference-app equivalent — the static app only
    ever had a work_weekends on/off toggle (§4.4); SATURDAYS is new."""

    NONE = "none"  # weekdays only
    SATURDAYS = "saturdays"  # Saturday is a workday, Sunday isn't
    ALL = "all"  # every day is a workday


class ProjectSettings(BaseModel):
    project_start: str  # ISO yyyy-mm-dd
    weekend_policy: WeekendPolicy = WeekendPolicy.NONE
    sequence_stages: bool = True
    # ISO yyyy-mm-dd dates with no work allowed regardless of weekday
    # (public holidays, a contractor's planned days off, etc.).
    blocked_dates: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_work_weekends(cls, data: Any) -> Any:
        """A plan persisted before weekend_policy existed has a
        `work_weekends: bool` instead — map True/False to ALL/NONE so old
        SQLite snapshots (§4.7) keep loading correctly rather than needing
        a manual migration script."""
        if isinstance(data, dict) and "weekend_policy" not in data and "work_weekends" in data:
            data = dict(data)
            data["weekend_policy"] = WeekendPolicy.ALL if data.pop("work_weekends") else WeekendPolicy.NONE
        return data


class Rate(BaseModel):
    key: str
    label: str
    unit: str
    value: float


class Phase(BaseModel):
    """Order within Plan.phases is the priority order (sooner -> later)."""

    id: int
    label: str


class Stage(BaseModel):
    """Order within Plan.stages is the on-site trade sequence."""

    id: int
    label: str


class TaskLine(BaseModel):
    id: str = Field(default_factory=lambda: new_id("item"))
    task_id: str | None = None  # lines sharing task_id form one split task
    room: str  # matches an entry in Plan.rooms by name, not by id
    name: str
    category: str
    line_type: LineType = LineType.INCLUSIVE
    worker_type: str = ""
    phase: int  # Phase.id
    stage_id: int | None = None  # None == "unassigned"
    mandatory: bool = True
    duration_days: int | None = None  # None -> fall back to CATEGORY_DURATION[category]
    start_override: str | None = None  # ISO date, pins the task's start
    depends_on: list[str] = Field(default_factory=list)  # other TaskLine.id values
    cost_method: CostMethod = CostMethod.CUSTOM
    rate_key: str | None = None
    qty: float | None = None
    custom_amount: float | None = None
    buy_status: BuyStatus = BuyStatus.TO_BUY  # meaningful for Material lines
    status: TaskStatus = TaskStatus.NOT_STARTED
    notes: str = ""
    actual_cost: float | None = None


class Plan(BaseModel):
    settings: ProjectSettings
    rooms: list[str] = Field(default_factory=list)
    rates: list[Rate] = Field(default_factory=list)
    phases: list[Phase] = Field(default_factory=list)
    stages: list[Stage] = Field(default_factory=list)
    items: list[TaskLine] = Field(default_factory=list)
