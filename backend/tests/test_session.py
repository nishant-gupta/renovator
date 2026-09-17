"""Unit tests for PlanSession's persistence behavior (design doc §4.7)."""

from __future__ import annotations

import pytest

from renovator.agents.session import PlanSession
from renovator.tools import crud_tools as ct


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVATOR_DATA_DIR", str(tmp_path))


def test_ephemeral_session_has_no_store_and_persist_is_a_noop():
    session = PlanSession()
    assert session.store is None
    ct.add_room(session.plan, "Kitchen")
    session.persist("add_room", "Added room 'Kitchen'")  # must not raise
    assert session.changelog() == []


def test_persistent_session_survives_a_simulated_restart():
    session_a = PlanSession(project_id="restart-test")
    ct.add_room(session_a.plan, "Kitchen")
    session_a.persist("add_room", "Added room 'Kitchen'")

    # a brand-new PlanSession/process against the same project_id
    session_b = PlanSession(project_id="restart-test")
    assert session_b.plan.rooms == ["Kitchen"]
    assert any(e["action"] == "add_room" for e in session_b.changelog())


def test_explicit_plan_overrides_stored_plan():
    from renovator.domain.seed import empty_plan

    custom = empty_plan()
    custom.rooms = ["Custom Room"]
    session = PlanSession(project_id="override-test", plan=custom)
    assert session.plan.rooms == ["Custom Room"]


def test_ephemeral_session_usage_summary_is_a_noop_with_empty_result():
    session = PlanSession()
    session.log_usage("claude-sonnet-4-5", 100, 20, 500)  # must not raise
    summary = session.usage_summary()
    assert summary == {
        "total_calls": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_duration_ms": 0,
        "by_model": [],
        "recent": [],
    }


def test_persistent_session_usage_summary_reflects_logged_usage():
    session = PlanSession(project_id="usage-session-test")
    session.log_usage("claude-sonnet-4-5", 100, 20, 500)
    summary = session.usage_summary()
    assert summary["total_calls"] == 1
    assert summary["total_input_tokens"] == 100
