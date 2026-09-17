"""Orchestrator: create_deep_agent() with the full tool set,
TodoListMiddleware for planning, interrupt_on for the gated (destructive)
tools (see tool_bindings.py for what's gated and why), and the
Intake/Scheduling/Procurement/Budget/Tracking/Research sub-agents
(design doc §4.6, subagents.py) available via the `task` tool.

The main agent keeps the full tool set too (not just the sub-agents) so it
can handle simple direct asks itself without a delegation round-trip —
sub-agents are for focused, multi-step, or research-heavy work.

Persistence (§4.7, Phase 5): a session with a `project_id` gets a SQLite
checkpointer at that project's own file, so the conversation (and any
pending interrupt) survives a process restart — resume by building a new
orchestrator against the same PlanSession/project_id and invoking with the
same `thread_id`. A session with no `project_id` (tests, one-off scripts)
gets an in-memory checkpointer instead.
"""

from __future__ import annotations

import sqlite3

from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from renovator.agents.prompts import SYSTEM_PROMPT
from renovator.agents.session import PlanSession
from renovator.agents.subagents import build_subagents
from renovator.agents.tool_bindings import GATED_TOOL_NAMES, build_research_tools, build_tools
from renovator.store.plan_store import checkpoint_db_path

DEFAULT_MODEL = "anthropic:claude-sonnet-4-5"


def build_checkpointer(session: PlanSession) -> BaseCheckpointSaver:
    if session.project_id is None:
        return InMemorySaver()
    conn = sqlite3.connect(checkpoint_db_path(session.project_id), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def build_orchestrator(session: PlanSession, model: str = DEFAULT_MODEL):
    """Compile the agent graph for one session. Returns a LangGraph
    CompiledStateGraph — invoke/stream it with a `thread_id` in config so
    the checkpointer can track (and resume) conversation state and any
    pending interrupted tool call."""
    tools = build_tools(session) + build_research_tools()
    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        middleware=[TodoListMiddleware()],
        subagents=build_subagents(session),
        interrupt_on={name: True for name in GATED_TOOL_NAMES},
        checkpointer=build_checkpointer(session),
    )
