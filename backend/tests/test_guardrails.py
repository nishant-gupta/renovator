"""Structural guardrail tests (design doc §4.8) that don't fit naturally
under orchestrator/subagents/research_tools — no live model calls.
"""

from __future__ import annotations

from renovator.agents.session import PlanSession
from renovator.agents.tool_bindings import build_research_tools, build_tools

# §4.8: "anything that would send an external message is out of scope for
# v1 — vendor messages are drafted, never sent." There is deliberately no
# tool anywhere in this codebase that can send email/SMS/webhooks/etc.; this
# is an audit of the *current* tool set, and an allowlist any future tool
# addition has to pass through deliberately, not silently.
_FORBIDDEN_NAME_SUBSTRINGS = (
    "send",
    "email",
    "sms",
    "notify",
    "webhook",
    "post_message",
    "slack",
    "publish",
    "message_vendor",
)

_EXPECTED_TOOL_NAMES = {
    "get_setup",
    "get_tasks",
    "get_schedule",
    "get_suggested_order",
    "get_materials_plan",
    "get_estimate_summary",
    "get_track_summary",
    "list_templates",
    "get_changelog",
    "add_room",
    "rename_room",
    "remove_room",
    "add_rate",
    "update_rate",
    "delete_rate",
    "add_phase",
    "rename_phase",
    "remove_phase",
    "move_phase",
    "add_stage",
    "rename_stage",
    "remove_stage",
    "move_stage",
    "set_project_settings",
    "add_blocked_date",
    "remove_blocked_date",
    "instantiate_template",
    "create_task",
    "update_task",
    "delete_task",
    "set_dependencies",
    "bulk_set_mandatory",
    "bulk_move_to_phase",
    "bulk_move_to_stage",
    "bulk_delete_tasks",
    "export_plan_to_excel",
    "import_plan_from_excel",
    "search_material_rate",
    "search_vendors",
}


def test_no_tool_name_suggests_sending_an_external_message():
    session = PlanSession()
    tools = build_tools(session) + build_research_tools()
    for t in tools:
        lname = t.name.lower()
        for bad in _FORBIDDEN_NAME_SUBSTRINGS:
            assert bad not in lname, f"tool {t.name!r} looks like it could send an external message"


def test_full_tool_set_is_the_expected_allowlist():
    # Forces a deliberate update to this test (and a look at the substring
    # check above) whenever a new tool is added — the point isn't the exact
    # set, it's that additions can't slip through unnoticed.
    session = PlanSession()
    tools = build_tools(session) + build_research_tools()
    names = {t.name for t in tools}
    assert names == _EXPECTED_TOOL_NAMES
