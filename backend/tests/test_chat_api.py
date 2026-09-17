"""API-level tests for the /chat and /plan-events routes (Phase 7) — the
routing/wiring only. `stream_turn`/`_plan_events` themselves are covered by
test_chat_stream.py and the direct plan-events tests below; no live model
call happens here.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from langgraph.types import Command

from renovator.api import routes
from renovator.app import app


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVATOR_DATA_DIR", str(tmp_path))


@pytest.fixture()
def client():
    return TestClient(app)


def test_chat_with_message_streams_events(client, monkeypatch):
    captured = {}

    def fake_stream_turn(session, thread_id, step_input):
        captured["thread_id"] = thread_id
        captured["step_input"] = step_input
        yield 'data: {"type": "done"}\n\n'

    monkeypatch.setattr(routes, "stream_turn", fake_stream_turn)

    resp = client.post("/projects/p1/chat", json={"message": "add a kitchen room"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.text == 'data: {"type": "done"}\n\n'
    assert captured["thread_id"] == "p1"
    assert captured["step_input"] == {"messages": [{"role": "user", "content": "add a kitchen room"}]}


def test_chat_with_resume_passes_a_command(client, monkeypatch):
    captured = {}

    def fake_stream_turn(session, thread_id, step_input):
        captured["step_input"] = step_input
        yield 'data: {"type": "done"}\n\n'

    monkeypatch.setattr(routes, "stream_turn", fake_stream_turn)

    resp = client.post("/projects/p1/chat", json={"resume": {"decisions": [{"type": "approve"}]}})

    assert resp.status_code == 200
    assert isinstance(captured["step_input"], Command)
    assert captured["step_input"].resume == {"decisions": [{"type": "approve"}]}


def test_chat_requires_message_or_resume(client):
    resp = client.post("/projects/p1/chat", json={})
    assert resp.status_code == 400


def test_chat_with_image_builds_multimodal_content(client, monkeypatch):
    captured = {}

    def fake_stream_turn(session, thread_id, step_input):
        captured["step_input"] = step_input
        yield 'data: {"type": "done"}\n\n'

    monkeypatch.setattr(routes, "stream_turn", fake_stream_turn)

    resp = client.post(
        "/projects/p1/chat",
        json={"message": "What's in this room?", "image": "data:image/png;base64,aGVsbG8="},
    )

    assert resp.status_code == 200
    content = captured["step_input"]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "What's in this room?"}
    assert content[1] == {"type": "image", "source_type": "base64", "data": "aGVsbG8=", "mime_type": "image/png"}


def test_chat_with_image_and_no_message_gets_a_default_prompt(client, monkeypatch):
    captured = {}

    def fake_stream_turn(session, thread_id, step_input):
        captured["step_input"] = step_input
        yield 'data: {"type": "done"}\n\n'

    monkeypatch.setattr(routes, "stream_turn", fake_stream_turn)

    resp = client.post("/projects/p1/chat", json={"image": "data:image/jpeg;base64,aGVsbG8="})

    assert resp.status_code == 200
    text_block = captured["step_input"]["messages"][0]["content"][0]
    assert text_block["type"] == "text" and text_block["text"]


def test_chat_rejects_an_oversized_image(client):
    huge_payload = "a" * (routes._MAX_IMAGE_B64_CHARS + 1)
    resp = client.post("/projects/p1/chat", json={"image": f"data:image/png;base64,{huge_payload}"})
    assert resp.status_code == 400


def test_parse_data_url_falls_back_to_jpeg_without_a_recognizable_header():
    assert routes._parse_data_url("not-a-data-url,aGVsbG8=") == ("image/jpeg", "aGVsbG8=")
    assert routes._parse_data_url("data:image/webp;base64,aGVsbG8=") == ("image/webp", "aGVsbG8=")


def test_usage_route_returns_the_summary(client):
    resp = client.get("/projects/p1/usage")
    assert resp.status_code == 200
    assert resp.json() == {
        "total_calls": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_duration_ms": 0,
        "by_model": [],
        "recent": [],
    }


def test_chat_history_route_returns_the_events_list(client, monkeypatch):
    captured = {}

    def fake_history_events(session, thread_id):
        captured["thread_id"] = thread_id
        return [{"type": "message", "role": "user", "content": "hi"}]

    monkeypatch.setattr(routes, "history_events", fake_history_events)

    resp = client.get("/projects/p1/chat/history")

    assert resp.status_code == 200
    assert resp.json() == {"events": [{"type": "message", "role": "user", "content": "hi"}]}
    assert captured["thread_id"] == "p1"


def test_plan_events_route_streams_from_the_generator(client, monkeypatch):
    def fake_plan_events(project_id, poll_interval, max_polls):
        assert project_id == "p1"
        yield 'data: {"type": "ready"}\n\n'
        yield 'data: {"type": "changed", "updated_at": "x"}\n\n'

    monkeypatch.setattr(routes, "_plan_events", fake_plan_events)

    resp = client.get("/projects/p1/plan-events")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.text == 'data: {"type": "ready"}\n\ndata: {"type": "changed", "updated_at": "x"}\n\n'


def test_plan_events_generator_detects_a_change_between_polls():
    from renovator.store.plan_store import PlanStore

    store = PlanStore("evt-test")
    plan = store.load_or_create()

    gen = routes._plan_events("evt-test", poll_interval=0, max_polls=5)
    assert next(gen) == 'data: {"type": "ready"}\n\n'

    store.save(plan, action="edit", detail="x")
    import sqlite3

    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE plan_snapshot SET updated_at = ? WHERE id = 1", ("forced-new-timestamp",))
        conn.commit()

    assert next(gen) == 'data: {"type": "changed", "updated_at": "forced-new-timestamp"}\n\n'
    assert list(gen) == []  # remaining bounded polls see no further change
