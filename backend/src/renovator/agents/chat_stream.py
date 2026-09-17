"""Turns one agent turn into a sequence of small SSE-framed JSON events for
the chat endpoint (design doc §4.10, Phase 7) — the browser-side
equivalent of cli.py's invoke-loop, just incremental instead of a single
blocking call.

Uses `stream_mode="values"` (the full state snapshot after every
super-step) rather than depending on deepagents' internal node names —
those vary with middleware and aren't part of any public contract. Each
new `messages` entry since the last snapshot becomes one event; a snapshot
carrying `__interrupt__` (the same key `graph.invoke()` returns on a gated
tool call, per cli.py) ends the turn early with an `interrupt` event
instead of `done`.

`history_events()` replays a thread's checkpointed state the same way, for
`GET /chat/history` — it's how the frontend recovers a transcript (and any
still-pending interrupt) after a page reload, since `StateSnapshot` keeps
the full message list *and* any unresolved interrupt around independent of
whether a browser is currently streaming a turn.

Every turn also emits one `usage` event (Phase 9's local cost/latency
tracker) summing token counts across every *main-agent* model call in the
turn, persisted via `session.log_usage` for `GET /projects/{id}/usage` to
aggregate later. Known gap, confirmed live rather than assumed: a
delegated sub-agent call (the `task` tool, subagents.py::SUBAGENT_MODEL)
runs as its own nested sub-graph invocation — its internal AIMessages
(and their usage_metadata) never appear in this thread's top-level
`messages` state, only the tool's final result does, as an ordinary
ToolMessage. So a turn that delegates undercounts real spend: the
sub-agent's own tokens aren't in the total. Capturing those would need
`stream_mode`'s `subgraphs=True` (separate per-namespace message
channels, each needing its own "already seen" tracking) — a real
refactor of this streaming loop, not attempted here; LangSmith tracing
(§4.9/.env.example) does capture the sub-agent calls if that's needed.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

from renovator.agents.orchestrator import build_orchestrator
from renovator.agents.pricing import estimate_cost_usd
from renovator.agents.session import PlanSession


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _text_and_image_flag(content: Any) -> tuple[str, bool]:
    """A HumanMessage's content is a plain string, unless a photo was
    attached (Phase 8, room-photo intake) — then it's a list of content
    blocks (`{"type": "text", ...}` / `{"type": "image", ...}`). Either
    way, the event sent to the browser only ever carries the text: the
    browser already has whatever image it sent, and echoing the base64
    payload back would bloat every SSE event with data the client can't
    even use (history replay never returns the original bytes)."""
    if isinstance(content, str):
        return content, False
    if isinstance(content, list):
        texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        has_image = any(isinstance(b, dict) and b.get("type") == "image" for b in content)
        return " ".join(t for t in texts if t), has_image
    return "", False


def _message_event(msg: Any) -> dict | None:
    cls = msg.__class__.__name__
    if cls == "HumanMessage":
        text, has_image = _text_and_image_flag(msg.content)
        if not text and not has_image:
            return None
        return {"type": "message", "role": "user", "content": text, "has_image": has_image}
    if cls == "AIMessage":
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            return {"type": "tool_call", "calls": [{"name": tc["name"], "args": tc["args"]} for tc in tool_calls]}
        if msg.content:
            return {"type": "message", "role": "assistant", "content": msg.content}
        return None
    if cls == "ToolMessage":
        return {"type": "tool_result", "name": getattr(msg, "name", ""), "content": str(msg.content)[:2000]}
    return None


def _usage_from_message(msg: Any) -> tuple[str, int, int] | None:
    """(model, input_tokens, output_tokens) for an AIMessage that actually
    made a model call, or None (ToolMessage/HumanMessage never have this;
    an AIMessage can lack it too, depending on provider/version)."""
    usage = getattr(msg, "usage_metadata", None)
    if not usage:
        return None
    model = (getattr(msg, "response_metadata", None) or {}).get("model_name", "unknown")
    return model, usage.get("input_tokens", 0), usage.get("output_tokens", 0)


def _interrupt_event(interrupt: Any) -> dict:
    # Same shape cli.py's _handle_interrupt reads: request["action_requests"]
    # is a list of {"name", "args", "description"} dicts, one per gated
    # tool call HumanInTheLoopMiddleware paused on.
    request = interrupt.value
    actions = [
        {"name": a["name"], "args": a["args"], "description": a.get("description", "")}
        for a in request["action_requests"]
    ]
    return {"type": "interrupt", "actions": actions}


def stream_turn(session: PlanSession, thread_id: str, step_input: Any) -> Iterator[str]:
    """Runs one turn — a new user message, or a `Command(resume=...)` after
    a previous interrupt — and yields SSE-framed events as they occur."""
    graph = build_orchestrator(session)
    config = {"configurable": {"thread_id": thread_id}}

    # `stream_mode="values"` yields the *full* accumulated message list on
    # every super-step, including everything from earlier turns already
    # sent as events on a prior `stream_turn()` call — each call here
    # starts a fresh generator with no memory of that. So `seen` has to
    # start at however many messages the checkpointer already has for
    # this thread, not 0, or every turn re-emits the whole conversation.
    seen = len(graph.get_state(config).values.get("messages", []))
    turn_start = time.perf_counter()
    usage_by_model: dict[str, list[int]] = {}

    def usage_event() -> dict:
        duration_ms = int((time.perf_counter() - turn_start) * 1000)
        # Wall-clock time covers the whole turn, not one model call, so it's
        # only attributed to the first model logged this turn — summing
        # duration_ms across models in a multi-model turn would double it.
        for i, (model, (inp, out)) in enumerate(usage_by_model.items()):
            session.log_usage(model, inp, out, duration_ms if i == 0 else 0)
        return {
            "type": "usage",
            "duration_ms": duration_ms,
            "total_input_tokens": sum(inp for inp, _ in usage_by_model.values()),
            "total_output_tokens": sum(out for _, out in usage_by_model.values()),
            "estimated_cost_usd": round(
                sum(estimate_cost_usd(model, inp, out) for model, (inp, out) in usage_by_model.items()), 6
            ),
        }

    try:
        for chunk in graph.stream(step_input, config=config, stream_mode="values"):
            messages = chunk.get("messages", [])
            for msg in messages[seen:]:
                event = _message_event(msg)
                if event:
                    yield _sse(event)
                usage = _usage_from_message(msg)
                if usage:
                    model, inp, out = usage
                    acc = usage_by_model.setdefault(model, [0, 0])
                    acc[0] += inp
                    acc[1] += out
            seen = len(messages)

            if "__interrupt__" in chunk:
                (interrupt,) = chunk["__interrupt__"]
                yield _sse(usage_event())
                yield _sse(_interrupt_event(interrupt))
                return
    except Exception as e:  # noqa: BLE001 - surface to the chat panel instead of a bare 500 mid-stream
        yield _sse(usage_event())
        yield _sse({"type": "error", "message": str(e)})
        return

    yield _sse(usage_event())
    yield _sse({"type": "done"})


def history_events(session: PlanSession, thread_id: str) -> list[dict]:
    """Every message the checkpointer has for this thread, as the same
    event dicts `stream_turn` yields (just not SSE-framed — this is a
    plain JSON response, not a stream), plus a trailing `interrupt` event
    if the thread is currently paused on one. A thread with no history yet
    (or an unknown thread_id) just returns an empty list."""
    graph = build_orchestrator(session)
    config = {"configurable": {"thread_id": thread_id}}
    state = graph.get_state(config)

    events = []
    for msg in state.values.get("messages", []) if state.values else []:
        event = _message_event(msg)
        if event:
            events.append(event)
    if state.interrupts:
        events.append(_interrupt_event(state.interrupts[0]))
    return events
