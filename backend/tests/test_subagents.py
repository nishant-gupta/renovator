"""Structural tests for the Phase 4 sub-agents — no live model calls (see
scripts/ for the manual CLI; sub-agent delegation was verified manually
against the real API during development)."""

from __future__ import annotations

from renovator.agents.session import PlanSession
from renovator.agents.subagents import SUBAGENT_MODEL, build_subagents
from renovator.agents.tool_bindings import GATED_TOOL_NAMES


def test_six_subagents_with_expected_names():
    session = PlanSession()
    subagents = build_subagents(session)
    names = {sa["name"] for sa in subagents}
    assert names == {"intake", "scheduling", "procurement", "budget", "tracking", "research"}


def test_no_subagent_has_a_gated_tool():
    session = PlanSession()
    subagents = build_subagents(session)
    for sa in subagents:
        tool_names = {t.name for t in sa["tools"]}
        overlap = tool_names & set(GATED_TOOL_NAMES)
        assert not overlap, f"{sa['name']} must not have gated tools: {overlap}"


def test_research_subagent_is_read_only_web_search():
    session = PlanSession()
    subagents = build_subagents(session)
    research = next(sa for sa in subagents if sa["name"] == "research")
    tool_names = {t.name for t in research["tools"]}
    assert tool_names == {"search_material_rate", "search_vendors"}


# Prefixes any mutating tool in this codebase uses (crud_tools.py, io_tools.py) —
# see test_no_tool_can_send_an_external_message in test_guardrails.py for the
# full-tool-set audit this mirrors, scoped here to just the intake sub-agent.
_MUTATING_PREFIXES = ("add_", "create_", "update_", "delete_", "remove_", "bulk_", "instantiate_", "import_")


def test_intake_subagent_is_draft_only_by_construction():
    # design doc §4.6/§4.8's "draft-only" promise for room-photo/brief intake
    # is enforced here, not just in its system prompt: it has no tool capable
    # of creating or changing a room/task, so it cannot apply its own proposal
    # even if a crafted brief (or a photo with injected text) told it to try.
    session = PlanSession()
    subagents = build_subagents(session)
    intake = next(sa for sa in subagents if sa["name"] == "intake")
    tool_names = {t.name for t in intake["tools"]}
    assert "get_setup" in tool_names and "get_tasks" in tool_names  # still needs read access
    for name in tool_names:
        assert not name.startswith(_MUTATING_PREFIXES), f"intake must not have a mutating tool: {name}"


def test_every_subagent_uses_the_cheaper_model():
    # design doc §4.6: sub-agents do narrow tool orchestration over
    # already-computed data, not open-ended reasoning, so they run on a
    # cheaper/faster model than the main orchestrator (orchestrator.py's
    # DEFAULT_MODEL, which this must differ from).
    session = PlanSession()
    for sa in build_subagents(session):
        assert sa.get("model") == SUBAGENT_MODEL, f"{sa['name']} not on the shared sub-agent model"


def test_every_subagent_has_a_system_prompt_and_description():
    session = PlanSession()
    for sa in build_subagents(session):
        assert sa.get("system_prompt"), f"{sa['name']} missing system_prompt"
        assert sa.get("description"), f"{sa['name']} missing description"
        assert sa["tools"], f"{sa['name']} has no tools"
