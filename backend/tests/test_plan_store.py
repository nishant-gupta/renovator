"""Unit tests for the local SQLite plan store (design doc §4.7)."""

from __future__ import annotations

import pytest

from renovator.store import plan_store as ps
from renovator.tools import crud_tools as ct


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVATOR_DATA_DIR", str(tmp_path))


def test_load_returns_none_for_unseen_project():
    store = ps.PlanStore("brand-new-project")
    assert store.load() is None


def test_load_or_create_seeds_an_empty_plan_and_persists_it():
    store = ps.PlanStore("proj-a")
    plan = store.load_or_create()
    assert plan.items == []
    # a fresh PlanStore instance against the same project should see it
    reloaded = ps.PlanStore("proj-a").load()
    assert reloaded is not None
    assert reloaded.settings.project_start == plan.settings.project_start


def test_save_round_trips_mutations():
    store = ps.PlanStore("proj-b")
    plan = store.load_or_create()
    ct.add_room(plan, "Kitchen")
    store.save(plan, action="add_room", detail="Added room 'Kitchen'")

    reloaded = ps.PlanStore("proj-b").load()
    assert reloaded.rooms == ["Kitchen"]


def test_changelog_records_actions_most_recent_first():
    store = ps.PlanStore("proj-c")
    plan = store.load_or_create()  # one changelog entry: create_project
    store.save(plan, action="add_room", detail="Added room 'Kitchen'")
    store.save(plan, action="add_room", detail="Added room 'Bath'")

    entries = store.changelog()
    assert [e["action"] for e in entries[:2]] == ["add_room", "add_room"]
    assert entries[0]["detail"] == "Added room 'Bath'"
    assert len(entries) == 3


def test_projects_are_isolated_by_id():
    a = ps.PlanStore("proj-x").load_or_create()
    ct.add_room(a, "Kitchen")
    ps.PlanStore("proj-x").save(a, action="add_room")

    b = ps.PlanStore("proj-y").load_or_create()
    assert b.rooms == []


def test_usage_summary_empty_for_a_fresh_project():
    store = ps.PlanStore("proj-usage-empty")
    summary = store.usage_summary()
    assert summary["total_calls"] == 0
    assert summary["total_input_tokens"] == 0
    assert summary["total_output_tokens"] == 0
    assert summary["by_model"] == []
    assert summary["recent"] == []


def test_log_usage_accumulates_across_calls_and_models():
    store = ps.PlanStore("proj-usage")
    store.log_usage("claude-sonnet-4-5", 100, 20, 500)
    store.log_usage("claude-haiku-4-5", 50, 10, 200)
    store.log_usage("claude-sonnet-4-5", 30, 5, 100)

    summary = store.usage_summary()
    assert summary["total_calls"] == 3
    assert summary["total_input_tokens"] == 180
    assert summary["total_output_tokens"] == 35
    assert summary["total_duration_ms"] == 800

    by_model = {row["model"]: row for row in summary["by_model"]}
    assert by_model["claude-sonnet-4-5"]["calls"] == 2
    assert by_model["claude-sonnet-4-5"]["input_tokens"] == 130
    assert by_model["claude-haiku-4-5"]["calls"] == 1

    assert len(summary["recent"]) == 3
    assert summary["recent"][0]["model"] == "claude-sonnet-4-5"  # most recent first
    assert summary["recent"][0]["input_tokens"] == 30
