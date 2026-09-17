"""Unit tests for org-wide default settings (seed-only, not live inheritance)."""

from __future__ import annotations

import pytest

from renovator.domain.models import Plan, ProjectSettings, WeekendPolicy
from renovator.store import global_settings as gs
from renovator.tools.errors import ValidationError


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVATOR_DATA_DIR", str(tmp_path))


def test_defaults_before_any_write():
    settings = gs.get_global_settings()
    assert settings == {"weekend_policy": "none", "sequence_stages": True, "rates": [], "blocked_dates": []}


def test_update_global_settings_partial_patch():
    gs.update_global_settings({"weekend_policy": "all"})
    settings = gs.get_global_settings()
    assert settings["weekend_policy"] == "all"
    assert settings["sequence_stages"] is True  # untouched


def test_update_global_settings_rejects_an_invalid_weekend_policy():
    with pytest.raises(ValidationError):
        gs.update_global_settings({"weekend_policy": "whenever"})


def test_add_remove_global_blocked_date():
    gs.add_global_blocked_date("2027-01-01")
    assert gs.get_global_settings()["blocked_dates"] == ["2027-01-01"]

    gs.remove_global_blocked_date("2027-01-01")
    assert gs.get_global_settings()["blocked_dates"] == []


def test_add_global_blocked_date_rejects_a_bad_date():
    with pytest.raises(ValidationError):
        gs.add_global_blocked_date("not-a-date")


def test_remove_global_blocked_date_rejects_unknown_date():
    with pytest.raises(ValidationError):
        gs.remove_global_blocked_date("2027-01-01")


def test_add_update_delete_global_rate():
    gs.add_global_rate("Waterproofing", "sqft", 30)
    settings = gs.get_global_settings()
    assert len(settings["rates"]) == 1
    key = settings["rates"][0]["key"]
    assert settings["rates"][0] == {"key": key, "label": "Waterproofing", "unit": "sqft", "value": 30}

    gs.update_global_rate(key, 45)
    assert gs.get_global_settings()["rates"][0]["value"] == 45

    gs.delete_global_rate(key)
    assert gs.get_global_settings()["rates"] == []


def test_add_global_rate_requires_a_label():
    with pytest.raises(ValidationError):
        gs.add_global_rate("  ", "sqft", 30)


def test_update_global_rate_rejects_unknown_key():
    with pytest.raises(ValidationError):
        gs.update_global_rate("does-not-exist", 10)


def test_seed_plan_applies_current_defaults():
    gs.update_global_settings({"weekend_policy": "all", "sequence_stages": False})
    gs.add_global_rate("Paint", "sqft", 12)
    gs.add_global_blocked_date("2027-01-01")

    plan = Plan(settings=ProjectSettings(project_start="2026-01-01"))
    gs.seed_plan(plan)

    assert plan.settings.weekend_policy == WeekendPolicy.ALL
    assert plan.settings.sequence_stages is False
    assert plan.settings.blocked_dates == ["2027-01-01"]
    assert len(plan.rates) == 1
    assert plan.rates[0].label == "Paint"
