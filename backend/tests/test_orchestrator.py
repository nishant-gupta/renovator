"""Structural tests for the Phase 3 orchestrator — no live model calls (see
scripts/ for the manual CLI smoke test that does). These just confirm the
graph assembles correctly and the gating list stays in sync with the tools.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from renovator.agents.orchestrator import build_checkpointer, build_orchestrator
from renovator.agents.session import PlanSession
from renovator.agents.tool_bindings import GATED_TOOL_NAMES, build_tools


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RENOVATOR_DATA_DIR", str(tmp_path))


def test_build_tools_exposes_every_gated_name():
    session = PlanSession()
    tools = build_tools(session)
    names = {t.name for t in tools}
    for gated in GATED_TOOL_NAMES:
        assert gated in names, f"gated tool {gated!r} not found in tool set"


def test_update_rate_is_gated():
    # design doc §4.8: applying a rate-card change (research-suggested or
    # not) requires human confirmation, unconditionally.
    assert "update_rate" in GATED_TOOL_NAMES


def test_build_tools_has_no_confirm_param_on_gated_tools():
    session = PlanSession()
    tools = build_tools(session)
    by_name = {t.name: t for t in tools}
    for gated in GATED_TOOL_NAMES:
        schema_props = by_name[gated].args_schema.model_fields
        assert "confirm" not in schema_props, (
            f"{gated} must not expose confirm to the model — "
            "approval is handled by interrupt_on"
        )


def test_orchestrator_compiles_with_interrupt_and_todo_middleware():
    session = PlanSession()
    graph = build_orchestrator(session)
    nodes = set(graph.get_graph().nodes.keys())
    assert "TodoListMiddleware.after_model" in nodes
    assert "HumanInTheLoopMiddleware.after_model" in nodes


def test_ephemeral_session_gets_in_memory_checkpointer():
    session = PlanSession()
    assert isinstance(build_checkpointer(session), InMemorySaver)


def test_persistent_session_gets_sqlite_checkpointer():
    session = PlanSession(project_id="checkpointer-test")
    checkpointer = build_checkpointer(session)
    assert isinstance(checkpointer, SqliteSaver)


def test_orchestrator_compiles_for_a_persistent_session():
    session = PlanSession(project_id="orchestrator-persistence-test")
    graph = build_orchestrator(session)
    nodes = set(graph.get_graph().nodes.keys())
    assert "HumanInTheLoopMiddleware.after_model" in nodes
