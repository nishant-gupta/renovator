"""Unit tests for the project registry (design doc — multi-project management)."""

from __future__ import annotations

import pytest

from renovator.store import global_settings as gs
from renovator.store import project_registry as reg
from renovator.tools.errors import ValidationError


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVATOR_DATA_DIR", str(tmp_path))


def test_list_projects_empty_when_nothing_created():
    assert reg.list_projects() == []


def test_create_and_list_project():
    entry = reg.create_project("Kitchen Reno")
    assert entry["name"] == "Kitchen Reno"
    assert entry["id"]  # a slug was generated

    projects = reg.list_projects()
    assert [p["id"] for p in projects] == [entry["id"]]
    assert projects[0]["name"] == "Kitchen Reno"


def test_create_project_requires_a_name():
    with pytest.raises(ValidationError):
        reg.create_project("   ")


def test_create_project_deduplicates_slug_collision():
    a = reg.create_project("Kitchen")
    b = reg.create_project("Kitchen")
    assert a["id"] != b["id"]


def test_create_project_materializes_an_empty_plan():
    entry = reg.create_project("Bath Reno")
    from renovator.store.plan_store import PlanStore

    plan = PlanStore(entry["id"]).load()
    assert plan is not None
    assert plan.items == []


def test_create_project_seeds_from_current_global_defaults():
    gs.update_global_settings({"work_weekends": True, "sequence_stages": False})
    gs.add_global_rate("Paint", "sqft", 12)

    entry = reg.create_project("Seeded Reno")
    from renovator.store.plan_store import PlanStore

    plan = PlanStore(entry["id"]).load()
    assert plan is not None
    assert plan.settings.work_weekends is True
    assert plan.settings.sequence_stages is False
    assert len(plan.rates) == 1
    assert plan.rates[0].label == "Paint"


def test_rename_project():
    entry = reg.create_project("Old Name")
    reg.rename_project(entry["id"], "New Name")
    projects = reg.list_projects()
    assert projects[0]["name"] == "New Name"


def test_rename_unknown_project_rejected():
    with pytest.raises(ValidationError):
        reg.rename_project("does-not-exist", "X")


def test_delete_project_removes_registry_entry_and_files():
    entry = reg.create_project("Temp Project")
    from renovator.store.plan_store import project_db_path

    assert project_db_path(entry["id"]).exists()
    reg.delete_project(entry["id"])
    assert entry["id"] not in [p["id"] for p in reg.list_projects()]
    assert not project_db_path(entry["id"]).exists()


def test_delete_unknown_project_rejected():
    with pytest.raises(ValidationError):
        reg.delete_project("does-not-exist")


def test_bootstraps_a_pre_existing_project_file_with_no_registry_entry():
    from renovator.store.plan_store import PlanStore

    # simulate a project created before the registry existed (e.g. "default")
    PlanStore("legacy-project").load_or_create()
    projects = reg.list_projects()
    assert [p["id"] for p in projects] == ["legacy-project"]
    assert projects[0]["name"] == "legacy-project"
