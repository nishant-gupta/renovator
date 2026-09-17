"""Org-wide defaults every new project is seeded with — timing flags, a
starter rate card, and shared blocked dates. Backed by one JSON file
(`global_settings.json`) under `RENOVATOR_DATA_DIR`, same spirit as
`project_registry.py`.

Deliberately seed-only, not live inheritance: `seed_plan()` copies these
values into a brand-new `Plan` once, in `project_registry.create_project()`.
Editing a global default afterward never touches a project that already
exists — each project's own settings (edited via the usual
`PATCH /projects/{id}/settings` and rate routes) are independent from here on.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from renovator.domain.models import Plan, Rate, WeekendPolicy, new_id
from renovator.store.plan_store import data_dir
from renovator.tools.errors import ValidationError

_FILE = "global_settings.json"

_DEFAULTS: dict[str, Any] = {
    "weekend_policy": WeekendPolicy.NONE.value,
    "sequence_stages": True,
    "rates": [],
    "blocked_dates": [],
}


def _path() -> Path:
    return data_dir() / _FILE


def _normalize_weekend_policy(data: dict) -> str:
    """A global_settings.json written before weekend_policy existed has
    `work_weekends: bool` instead — same True/False -> ALL/NONE mapping as
    ProjectSettings' migration (domain/models.py)."""
    if "weekend_policy" in data:
        try:
            return WeekendPolicy(data["weekend_policy"]).value
        except ValueError:
            return _DEFAULTS["weekend_policy"]
    if "work_weekends" in data:
        return WeekendPolicy.ALL.value if data["work_weekends"] else WeekendPolicy.NONE.value
    return _DEFAULTS["weekend_policy"]


def get_global_settings() -> dict:
    path = _path()
    if not path.exists():
        return {**_DEFAULTS, "rates": [], "blocked_dates": []}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {**_DEFAULTS, "rates": [], "blocked_dates": []}
    return {
        "weekend_policy": _normalize_weekend_policy(data),
        "sequence_stages": bool(data.get("sequence_stages", _DEFAULTS["sequence_stages"])),
        "rates": data.get("rates", []),
        "blocked_dates": data.get("blocked_dates", []),
    }


def _write(settings: dict) -> None:
    _path().write_text(json.dumps(settings, indent=2))


def update_global_settings(patch: dict) -> dict:
    settings = get_global_settings()
    if "weekend_policy" in patch:
        try:
            settings["weekend_policy"] = WeekendPolicy(patch["weekend_policy"]).value
        except ValueError as e:
            raise ValidationError(
                f"Invalid weekend_policy: {patch['weekend_policy']!r} "
                f"(must be one of {[p.value for p in WeekendPolicy]})"
            ) from e
    if "sequence_stages" in patch:
        settings["sequence_stages"] = bool(patch["sequence_stages"])
    _write(settings)
    return settings


def add_global_rate(label: str, unit: str, value: float) -> dict:
    label = label.strip()
    if not label:
        raise ValidationError("Rate name is required.")
    settings = get_global_settings()
    settings["rates"].append({"key": new_id("rate"), "label": label, "unit": unit, "value": value})
    _write(settings)
    return settings


def update_global_rate(key: str, value: float) -> dict:
    settings = get_global_settings()
    rate = next((r for r in settings["rates"] if r["key"] == key), None)
    if not rate:
        raise ValidationError(f"No such default rate: {key}")
    rate["value"] = value
    _write(settings)
    return settings


def delete_global_rate(key: str) -> dict:
    settings = get_global_settings()
    settings["rates"] = [r for r in settings["rates"] if r["key"] != key]
    _write(settings)
    return settings


def add_global_blocked_date(date: str) -> dict:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise ValidationError(f"Invalid date (expected yyyy-mm-dd): {date!r}")
    settings = get_global_settings()
    if date not in settings["blocked_dates"]:
        settings["blocked_dates"] = sorted([*settings["blocked_dates"], date])
    _write(settings)
    return settings


def remove_global_blocked_date(date: str) -> dict:
    settings = get_global_settings()
    if date not in settings["blocked_dates"]:
        raise ValidationError(f"No such blocked date: {date}")
    settings["blocked_dates"] = [d for d in settings["blocked_dates"] if d != date]
    _write(settings)
    return settings


def seed_plan(plan: Plan) -> None:
    """Applies the current global defaults to a brand-new plan, in place."""
    settings = get_global_settings()
    plan.settings.weekend_policy = WeekendPolicy(settings["weekend_policy"])
    plan.settings.sequence_stages = settings["sequence_stages"]
    plan.settings.blocked_dates = list(settings["blocked_dates"])
    plan.rates = [Rate(**r) for r in settings["rates"]]
