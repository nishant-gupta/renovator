"""Manual CLI chat harness — not a product surface.

    uv run python -m renovator.cli [project_id]

Talks to the orchestrator (agents/orchestrator.py) against a persistent
PlanSession (§4.7) — the plan and conversation both survive a restart under
the same project_id, at ~/.renovator/<project_id>{.db,.checkpoints.db}.
Omit project_id for a throwaway, non-persistent session. Prints tool calls
as they happen and prompts for approve/reject on any interrupted (gated)
tool call.
"""

from __future__ import annotations

import json
import sys

from dotenv import load_dotenv
from langgraph.types import Command

from renovator.agents.orchestrator import build_orchestrator
from renovator.agents.session import PlanSession


def _print_tool_calls(step: dict) -> None:
    for msg in step.get("messages", []):
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                print(f"  -> {tc['name']}({json.dumps(tc['args'])[:200]})")
        if msg.__class__.__name__ == "ToolMessage":
            content = str(msg.content)
            print(f"  <- {content[:300]}")


def _handle_interrupt(interrupt) -> Command:
    request = interrupt.value
    decisions = []
    for action in request["action_requests"]:
        print(f"\n[confirmation needed] {action['name']}({json.dumps(action['args'])})")
        if action.get("description"):
            print(f"  {action['description']}")
        answer = input("  approve? [y/N]: ").strip().lower()
        if answer == "y":
            decisions.append({"type": "approve"})
        else:
            decisions.append({"type": "reject", "message": "User declined."})
    return Command(resume={"decisions": decisions})


def main() -> None:
    load_dotenv()
    project_id = sys.argv[1] if len(sys.argv) > 1 else None
    session = PlanSession(project_id=project_id)
    graph = build_orchestrator(session)
    config = {"configurable": {"thread_id": project_id or "ephemeral"}}

    if project_id:
        print(f"Renovator agent CLI — project '{project_id}' (persistent). Ctrl+C to quit.\n")
    else:
        print("Renovator agent CLI — ephemeral session (nothing saved). Ctrl+C to quit.\n")
    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue

        step_input = {"messages": [{"role": "user", "content": user_input}]}
        while True:
            result = graph.invoke(step_input, config=config)
            _print_tool_calls(result)
            if "__interrupt__" in result:
                (interrupt,) = result["__interrupt__"]
                step_input = _handle_interrupt(interrupt)
                continue
            break

        final = result["messages"][-1]
        print(f"\nagent> {final.content}\n")


if __name__ == "__main__":
    main()
