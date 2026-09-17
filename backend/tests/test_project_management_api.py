"""API integration tests for project management and cross-project transfer."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from renovator.app import app


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVATOR_DATA_DIR", str(tmp_path))


@pytest.fixture()
def client():
    return TestClient(app)


def test_list_create_rename_delete_project(client):
    assert client.get("/projects").json() == []

    resp = client.post("/projects", json={"name": "Kitchen Reno"})
    assert resp.status_code == 200
    project_id = resp.json()["id"]

    projects = client.get("/projects").json()
    assert [p["name"] for p in projects] == ["Kitchen Reno"]

    resp = client.patch(f"/projects/{project_id}", json={"name": "Kitchen Reno 2026"})
    assert resp.status_code == 200
    assert client.get("/projects").json()[0]["name"] == "Kitchen Reno 2026"

    resp = client.delete(f"/projects/{project_id}")
    assert resp.status_code == 409  # needs confirm
    resp = client.delete(f"/projects/{project_id}", params={"confirm": "true"})
    assert resp.status_code == 200
    assert client.get("/projects").json() == []


def test_create_project_requires_a_name(client):
    resp = client.post("/projects", json={"name": "  "})
    assert resp.status_code == 400


def test_pre_existing_project_appears_without_being_created_via_api(client):
    # simulate a project that predates the registry (e.g. "default")
    client.get("/projects/default/setup")
    projects = client.get("/projects").json()
    assert any(p["id"] == "default" for p in projects)


def test_copy_tasks_to_existing_project(client):
    client.post("/projects/src/rooms", json={"name": "Kitchen"})
    create_resp = client.post(
        "/projects/src/tasks/from-template", json={"template_id": "fresh_paint", "room": "Kitchen", "qty": 100}
    )
    task_id = create_resp.json()[0]["task_id"]
    client.post("/projects", json={"name": "Target"})
    target_id = next(p["id"] for p in client.get("/projects").json() if p["name"] == "Target")

    resp = client.post(
        "/projects/src/tasks/transfer",
        json={"task_ids": [task_id], "target_project_id": target_id, "mode": "copy"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["transferred_task_count"] == 1
    assert "Kitchen" in body["created_rooms"]

    # source untouched, target has the task
    assert len(client.get("/projects/src/tasks").json()) == 1
    target_tasks = client.get(f"/projects/{target_id}/tasks").json()
    assert target_tasks[0]["name"] == "Fresh paint"


def test_move_tasks_removes_from_source(client):
    client.post("/projects/src2/rooms", json={"name": "Kitchen"})
    create_resp = client.post(
        "/projects/src2/tasks/from-template", json={"template_id": "fresh_paint", "room": "Kitchen", "qty": 100}
    )
    task_id = create_resp.json()[0]["task_id"]

    resp = client.post(
        "/projects/src2/tasks/transfer",
        json={"task_ids": [task_id], "new_project_name": "Brand New Project", "mode": "move"},
    )
    assert resp.status_code == 200
    target_id = resp.json()["target_project_id"]

    assert client.get("/projects/src2/tasks").json() == []
    assert len(client.get(f"/projects/{target_id}/tasks").json()) == 1


def test_transfer_requires_a_target(client):
    client.post("/projects/src3/rooms", json={"name": "Kitchen"})
    create_resp = client.post(
        "/projects/src3/tasks/from-template", json={"template_id": "fresh_paint", "room": "Kitchen", "qty": 100}
    )
    task_id = create_resp.json()[0]["task_id"]
    resp = client.post("/projects/src3/tasks/transfer", json={"task_ids": [task_id], "mode": "copy"})
    assert resp.status_code == 400


def test_global_settings_defaults_and_patch(client):
    resp = client.get("/settings/global")
    assert resp.status_code == 200
    assert resp.json() == {"weekend_policy": "none", "sequence_stages": True, "rates": [], "blocked_dates": []}

    resp = client.patch("/settings/global", json={"weekend_policy": "all"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["weekend_policy"] == "all"
    assert body["sequence_stages"] is True  # untouched by the partial patch


def test_global_settings_patch_rejects_invalid_weekend_policy(client):
    resp = client.patch("/settings/global", json={"weekend_policy": "whenever"})
    assert resp.status_code == 400


def test_global_blocked_dates_add_and_remove(client):
    resp = client.post("/settings/global/blocked-dates", json={"date": "2027-01-01"})
    assert resp.status_code == 200
    assert resp.json()["blocked_dates"] == ["2027-01-01"]

    resp = client.delete("/settings/global/blocked-dates/2027-01-01")
    assert resp.status_code == 200
    assert resp.json()["blocked_dates"] == []


def test_global_rate_crud(client):
    resp = client.post("/settings/global/rates", json={"label": "Paint", "unit": "sqft", "value": 12})
    assert resp.status_code == 200
    key = resp.json()["rates"][0]["key"]

    resp = client.patch(f"/settings/global/rates/{key}", json={"value": 20})
    assert resp.status_code == 200
    assert resp.json()["rates"][0]["value"] == 20

    resp = client.delete(f"/settings/global/rates/{key}")
    assert resp.status_code == 200
    assert resp.json()["rates"] == []


def test_new_project_is_seeded_from_global_defaults(client):
    client.patch("/settings/global", json={"weekend_policy": "all"})
    client.post("/settings/global/rates", json={"label": "Paint", "unit": "sqft", "value": 12})

    create_resp = client.post("/projects", json={"name": "Seeded"})
    project_id = create_resp.json()["id"]

    setup = client.get(f"/projects/{project_id}/setup").json()
    assert setup["weekend_policy"] == "all"
    assert len(setup["rates"]) == 1
    assert setup["rates"][0]["label"] == "Paint"


def test_transfer_to_self_rejected(client):
    client.post("/projects/src4/rooms", json={"name": "Kitchen"})
    create_resp = client.post(
        "/projects/src4/tasks/from-template", json={"template_id": "fresh_paint", "room": "Kitchen", "qty": 100}
    )
    task_id = create_resp.json()[0]["task_id"]
    resp = client.post(
        "/projects/src4/tasks/transfer",
        json={"task_ids": [task_id], "target_project_id": "src4", "mode": "copy"},
    )
    assert resp.status_code == 400
