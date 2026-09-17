"""Org-wide defaults every new project is seeded with — timing flags and a
starter rate card. Backed by one JSON file (`global_settings.json`) under
`RENOVATOR_DATA_DIR`, same spirit as `project_registry.py`.

Deliberately seed-only, not live inheritance: `seed_plan()` copies these
values into a brand-new `Plan` once, in `project_registry.create_project()`.
Editing a global default afterward never touches a project that already
exists — each project's own settings (edited via the usual
`PATCH /projects/{id}/settings` and rate routes) are independent from here on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from renovator.domain.models import Plan, Rate, new_id
from renovator.store.plan_store import data_dir
from renovator.tools.errors import ValidationError

_FILE = "global_settings.json"

_DEFAULTS: dict[str, Any] = {"work_weekends": False, "sequence_stages": True, "rates": []}


def _path() -> Path:
    return data_dir() / _FILE


def get_global_settings() -> dict:
    path = _path()
    if not path.exists():
        return {**_DEFAULTS, "rates": []}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {**_DEFAULTS, "rates": []}
    return {
        "work_weekends": bool(data.get("work_weekends", _DEFAULTS["work_weekends"])),
        "sequence_stages": bool(data.get("sequence_stages", _DEFAULTS["sequence_stages"])),
        "rates": data.get("rates", []),
    }


def _write(settings: dict) -> None:
    _path().write_text(json.dumps(settings, indent=2))


def update_global_settings(patch: dict) -> dict:
    settings = get_global_settings()
    if "work_weekends" in patch:
        settings["work_weekends"] = bool(patch["work_weekends"])
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


def seed_plan(plan: Plan) -> None:
    """Applies the current global defaults to a brand-new plan, in place."""
    settings = get_global_settings()
    plan.settings.work_weekends = settings["work_weekends"]
    plan.settings.sequence_stages = settings["sequence_stages"]
    plan.rates = [Rate(**r) for r in settings["rates"]]
