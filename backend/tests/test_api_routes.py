"""Integration tests for the Phase 6 read/setup-mutation API routes."""

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


def test_get_setup_creates_an_empty_project_on_first_access(client):
    resp = client.get("/projects/p1/setup")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rooms"] == []
    assert len(body["phases"]) == 3
    assert len(body["stages"]) == 10


def test_add_and_rename_and_remove_room(client):
    resp = client.post("/projects/p2/rooms", json={"name": "Kitchen"})
    assert resp.status_code == 200
    assert resp.json()["rooms"] == ["Kitchen"]

    resp = client.patch("/projects/p2/rooms/Kitchen", json={"new_name": "Kitchen (New)"})
    assert resp.status_code == 200
    assert resp.json()["rooms"] == ["Kitchen (New)"]

    # unused room: needs confirm=true
    resp = client.delete("/projects/p2/rooms/Kitchen (New)")
    assert resp.status_code == 409
    resp = client.delete("/projects/p2/rooms/Kitchen (New)", params={"confirm": "true"})
    assert resp.status_code == 200
    assert resp.json()["rooms"] == []


def test_remove_room_in_use_is_blocked_even_with_confirm(client):
    client.post("/projects/p3/rooms", json={"name": "Kitchen"})
    # No task-mutation endpoints yet (Phase 6 build-out) — add one directly
    # via the store to exercise the "room in use" block.
    from renovator.store.plan_store import PlanStore
    from renovator.tools import crud_tools as ct

    store = PlanStore("p3")
    plan = store.load_or_create()
    ti = ct.TaskInput(
        room="Kitchen", name="Paint", category="Painting", phase=plan.phases[0].id, single=ct.LineInput()
    )
    ct.create_task(plan, ti)
    store.save(plan, action="create_task")

    resp = client.delete("/projects/p3/rooms/Kitchen", params={"confirm": "true"})
    assert resp.status_code == 400


def test_rate_crud_round_trip(client):
    resp = client.post("/projects/p4/rates", json={"label": "Paint", "unit": "sqft", "value": 10})
    assert resp.status_code == 200
    key = resp.json()["rates"][0]["key"]

    resp = client.patch(f"/projects/p4/rates/{key}", json={"value": 15})
    assert resp.status_code == 200

    resp = client.delete(f"/projects/p4/rates/{key}")
    assert resp.status_code == 200
    assert resp.json()["rates"] == []


def test_remove_last_phase_is_rejected(client):
    setup = client.get("/projects/p5/setup").json()
    phase_ids = [p["id"] for p in setup["phases"]]
    for pid in phase_ids[:-1]:
        resp = client.delete(f"/projects/p5/phases/{pid}", params={"confirm": "true"})
        assert resp.status_code == 200
    last = phase_ids[-1]
    resp = client.delete(f"/projects/p5/phases/{last}", params={"confirm": "true"})
    assert resp.status_code == 400


def test_stage_reorder(client):
    setup = client.get("/projects/p6/setup").json()
    first_label = setup["stages"][0]["label"]
    resp = client.post("/projects/p6/stages/reorder", json={"index": 0, "direction": 1})
    assert resp.status_code == 200
    assert resp.json()["stages"][1]["label"] == first_label


def test_settings_update(client):
    resp = client.patch(
        "/projects/p7/settings", json={"project_start": "2027-01-01", "work_weekends": True}
    )
    assert resp.status_code == 200
    setup = client.get("/projects/p7/setup").json()
    assert setup["project_start"] == "2027-01-01"
    assert setup["work_weekends"] is True


def test_changelog_reflects_mutations(client):
    client.post("/projects/p8/rooms", json={"name": "Kitchen"})
    client.post("/projects/p8/rooms", json={"name": "Bath"})
    resp = client.get("/projects/p8/changelog")
    assert resp.status_code == 200
    actions = [e["action"] for e in resp.json()]
    assert actions[:2] == ["add_room", "add_room"]


def test_read_endpoints_work_on_empty_project(client):
    for path in ["tasks", "schedule", "materials", "estimate", "track"]:
        resp = client.get(f"/projects/p9/{path}")
        assert resp.status_code == 200, path


def test_list_templates(client):
    resp = client.get("/projects/p10/templates")
    assert resp.status_code == 200
    assert len(resp.json()) == 10


def test_instantiate_template_creates_a_task(client):
    client.post("/projects/p11/rooms", json={"name": "Kitchen"})
    resp = client.post(
        "/projects/p11/tasks/from-template",
        json={"template_id": "fresh_paint", "room": "Kitchen", "qty": 100},
    )
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) == 1
    assert tasks[0]["room"] == "Kitchen"
    assert tasks[0]["is_split"] is True


def test_create_single_task(client):
    client.post("/projects/p12/rooms", json={"name": "Kitchen"})
    setup = client.get("/projects/p12/setup").json()
    phase_id = setup["phases"][0]["id"]
    resp = client.post(
        "/projects/p12/tasks",
        json={
            "room": "Kitchen",
            "name": "Custom shelf",
            "category": "Carpentry",
            "phase": phase_id,
            "structure": "single",
            "single": {"cost_method": "custom", "custom_amount": 8000},
        },
    )
    assert resp.status_code == 200
    tasks = resp.json()
    assert tasks[0]["name"] == "Custom shelf"
    assert tasks[0]["total_cost"] == 8000


def test_create_task_rejects_an_explicit_task_id(client):
    client.post("/projects/p13/rooms", json={"name": "Kitchen"})
    resp = client.post(
        "/projects/p13/tasks",
        json={
            "task_id": "task_should_not_be_set",
            "room": "Kitchen",
            "name": "X",
            "category": "Other",
            "phase": 1,
            "single": {},
        },
    )
    assert resp.status_code == 400


def test_update_and_delete_task(client):
    client.post("/projects/p14/rooms", json={"name": "Kitchen"})
    setup = client.get("/projects/p14/setup").json()
    phase_id = setup["phases"][0]["id"]
    create_resp = client.post(
        "/projects/p14/tasks",
        json={
            "room": "Kitchen",
            "name": "Custom shelf",
            "category": "Carpentry",
            "phase": phase_id,
            "structure": "single",
            "single": {"cost_method": "custom", "custom_amount": 8000},
        },
    )
    task_id = create_resp.json()[0]["task_id"]

    update_resp = client.patch(
        f"/projects/p14/tasks/{task_id}",
        json={
            "room": "Kitchen",
            "name": "Custom shelf (bigger)",
            "category": "Carpentry",
            "phase": phase_id,
            "structure": "single",
            "single": {"cost_method": "custom", "custom_amount": 12000},
        },
    )
    assert update_resp.status_code == 200
    assert update_resp.json()[0]["name"] == "Custom shelf (bigger)"
    assert update_resp.json()[0]["total_cost"] == 12000
    # still exactly one task — update, not a duplicate
    assert len(update_resp.json()) == 1

    del_resp = client.delete(f"/projects/p14/tasks/{task_id}")
    assert del_resp.status_code == 409
    del_resp = client.delete(f"/projects/p14/tasks/{task_id}", params={"confirm": "true"})
    assert del_resp.status_code == 200
    assert del_resp.json() == []


def test_export_excel_returns_a_workbook(client):
    client.post("/projects/p15/rooms", json={"name": "Kitchen"})
    resp = client.get("/projects/p15/export.xlsx")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert resp.content[:2] == b"PK"  # xlsx is a zip archive


def test_export_import_round_trip_via_api(client):
    client.post("/projects/p16/rooms", json={"name": "Kitchen"})
    client.post(
        "/projects/p16/tasks",
        json={
            "room": "Kitchen",
            "name": "Custom shelf",
            "category": "Carpentry",
            "phase": 1,
            "structure": "single",
            "single": {"cost_method": "custom", "custom_amount": 8000},
        },
    )
    workbook = client.get("/projects/p16/export.xlsx").content

    resp = client.post(
        "/projects/p17/import",
        files={"file": ("plan.xlsx", workbook, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 409  # needs confirm=true

    resp = client.post(
        "/projects/p17/import",
        params={"confirm": "true"},
        files={"file": ("plan.xlsx", workbook, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200
    assert resp.json()["rooms"] == ["Kitchen"]
    tasks = client.get("/projects/p17/tasks").json()
    assert tasks[0]["name"] == "Custom shelf"
    assert tasks[0]["total_cost"] == 8000


def test_update_line_patches_a_single_field(client):
    client.post("/projects/p18/rooms", json={"name": "Kitchen"})
    create_resp = client.post(
        "/projects/p18/tasks",
        json={
            "room": "Kitchen",
            "name": "Tiles",
            "category": "Tiling",
            "phase": 1,
            "structure": "single",
            "single": {"cost_method": "custom", "custom_amount": 3000, "notes": "old note"},
        },
    )
    line_id = create_resp.json()[0]["lines"][0]["line_id"]

    resp = client.patch(f"/projects/p18/lines/{line_id}", json={"buy_status": "Ordered"})
    assert resp.status_code == 200
    line = resp.json()[0]["lines"][0]
    assert line["buy_status"] == "Ordered"
    assert line["notes"] == "old note"  # untouched

    resp = client.patch(f"/projects/p18/lines/{line_id}", json={"notes": "new note", "actual_cost": 3500})
    line = resp.json()[0]["lines"][0]
    assert line["notes"] == "new note"
    assert line["actual_cost"] == 3500
    assert line["buy_status"] == "Ordered"  # still untouched by this call


def test_update_line_rejects_unknown_line(client):
    resp = client.patch("/projects/p19/lines/does-not-exist", json={"notes": "x"})
    assert resp.status_code == 400


def test_get_schedule_includes_worker_type(client):
    client.post("/projects/p20/rooms", json={"name": "Kitchen"})
    client.post(
        "/projects/p20/tasks/from-template", json={"template_id": "fresh_paint", "room": "Kitchen", "qty": 100}
    )
    resp = client.get("/projects/p20/schedule")
    assert resp.status_code == 200
    assert resp.json()["tasks"][0]["worker_type"] == "Painter"


def test_get_suggested_order(client):
    client.post("/projects/p21/rooms", json={"name": "Kitchen"})
    client.post(
        "/projects/p21/tasks/from-template", json={"template_id": "fresh_paint", "room": "Kitchen", "qty": 100}
    )
    resp = client.get("/projects/p21/suggested-order")
    assert resp.status_code == 200
    assert len(resp.json()) == 2  # material + labor line


def test_move_tasks_to_stage(client):
    client.post("/projects/p22/rooms", json={"name": "Kitchen"})
    setup = client.get("/projects/p22/setup").json()
    stage_id = setup["stages"][0]["id"]
    create_resp = client.post(
        "/projects/p22/tasks/from-template", json={"template_id": "fresh_paint", "room": "Kitchen", "qty": 100}
    )
    task_id = create_resp.json()[0]["task_id"]

    resp = client.post("/projects/p22/tasks/move-to-stage", json={"task_ids": [task_id], "stage_id": stage_id})
    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    assert tasks[0]["stage_id"] == stage_id

    resp = client.post("/projects/p22/tasks/move-to-stage", json={"task_ids": [task_id], "stage_id": None})
    assert resp.json()["tasks"][0]["stage_id"] is None


def test_bulk_mandatory_and_phase(client):
    client.post("/projects/p23/rooms", json={"name": "Kitchen"})
    setup = client.get("/projects/p23/setup").json()
    phase_2 = setup["phases"][1]["id"]
    create_resp = client.post(
        "/projects/p23/tasks/from-template", json={"template_id": "fresh_paint", "room": "Kitchen", "qty": 100}
    )
    task_id = create_resp.json()[0]["task_id"]

    resp = client.post("/projects/p23/tasks/bulk-mandatory", json={"task_ids": [task_id], "mandatory": False})
    assert resp.status_code == 200
    assert resp.json()[0]["mandatory"] is False

    resp = client.post("/projects/p23/tasks/bulk-phase", json={"task_ids": [task_id], "phase_id": phase_2})
    assert resp.status_code == 200
    assert resp.json()[0]["phase"] == phase_2


def test_bulk_delete_requires_confirmation(client):
    client.post("/projects/p24/rooms", json={"name": "Kitchen"})
    create_resp = client.post(
        "/projects/p24/tasks/from-template", json={"template_id": "fresh_paint", "room": "Kitchen", "qty": 100}
    )
    task_id = create_resp.json()[0]["task_id"]

    resp = client.post("/projects/p24/tasks/bulk-delete", json={"task_ids": [task_id]})
    assert resp.status_code == 409

    resp = client.post("/projects/p24/tasks/bulk-delete", json={"task_ids": [task_id]}, params={"confirm": "true"})
    assert resp.status_code == 200
    assert resp.json() == []
