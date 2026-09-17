"""Structural tests for the chat SSE event framing (Phase 7) — no live
model call (see the manual live-API smoke test for that). Fakes the
graph's `.stream()` output, so these only check `stream_turn` turns a
sequence of state snapshots into the right SSE events, independent of
deepagents' internal node names.
"""

from __future__ import annotations

import json

from renovator.agents import chat_stream
from renovator.agents.session import PlanSession

# Bare stand-ins matching the two message class *names* `_message_event`
# dispatches on — real langchain_core message classes aren't needed since
# the dispatch is purely by `__class__.__name__`, by design.


class HumanMessage:
    def __init__(self, content: str = ""):
        self.content = content


class AIMessage:
    def __init__(self, content: str = "", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class ToolMessage:
    def __init__(self, name: str, content):
        self.name = name
        self.content = content


class FakeInterrupt:
    def __init__(self, value):
        self.value = value


class FakeStateSnapshot:
    def __init__(self, values: dict, interrupts: tuple = ()):
        self.values = values
        self.interrupts = interrupts


class FakeGraph:
    def __init__(self, chunks=(), error: Exception | None = None, existing_messages=None, interrupts: tuple = ()):
        self._chunks = chunks
        self._error = error
        self._existing_messages = existing_messages or []
        self._interrupts = interrupts

    def get_state(self, config):
        return FakeStateSnapshot({"messages": self._existing_messages}, interrupts=self._interrupts)

    def stream(self, step_input, config, stream_mode):
        yield from self._chunks
        if self._error:
            raise self._error


def _events(monkeypatch, graph) -> list[dict]:
    monkeypatch.setattr(chat_stream, "build_orchestrator", lambda session: graph)
    raw = list(chat_stream.stream_turn(PlanSession(), "thread-1", {"messages": []}))
    return [json.loads(line[len("data: ") :].strip()) for line in raw]


def test_stream_turn_emits_tool_call_then_result_then_message(monkeypatch):
    ai_call = AIMessage(tool_calls=[{"name": "add_room", "args": {"name": "Kitchen"}}])
    tool_result = ToolMessage(name="add_room", content={"rooms": ["Kitchen"]})
    ai_final = AIMessage(content="Added the Kitchen room.")
    graph = FakeGraph(
        [
            {"messages": [ai_call]},
            {"messages": [ai_call, tool_result]},
            {"messages": [ai_call, tool_result, ai_final]},
        ]
    )

    events = _events(monkeypatch, graph)

    assert events == [
        {"type": "tool_call", "calls": [{"name": "add_room", "args": {"name": "Kitchen"}}]},
        {"type": "tool_result", "name": "add_room", "content": "{'rooms': ['Kitchen']}"},
        {"type": "message", "role": "assistant", "content": "Added the Kitchen room."},
        {"type": "done"},
    ]


def test_stream_turn_skips_empty_assistant_messages(monkeypatch):
    # An AIMessage with neither tool_calls nor content (e.g. a routing
    # step some middleware inserts) produces no event at all.
    routing_step = AIMessage()
    ai_final = AIMessage(content="Done.")
    graph = FakeGraph([{"messages": [routing_step]}, {"messages": [routing_step, ai_final]}])

    events = _events(monkeypatch, graph)

    assert events == [{"type": "message", "role": "assistant", "content": "Done."}, {"type": "done"}]


def test_stream_turn_emits_interrupt_and_stops_early(monkeypatch):
    ai_call = AIMessage(tool_calls=[{"name": "delete_task", "args": {"task_id": "t1"}}])
    interrupt = FakeInterrupt(
        {"action_requests": [{"name": "delete_task", "args": {"task_id": "t1"}, "description": "Delete this task?"}]}
    )
    graph = FakeGraph(
        [
            {"messages": [ai_call]},
            {"messages": [ai_call], "__interrupt__": (interrupt,)},
        ]
    )

    events = _events(monkeypatch, graph)

    assert events == [
        {"type": "tool_call", "calls": [{"name": "delete_task", "args": {"task_id": "t1"}}]},
        {
            "type": "interrupt",
            "actions": [{"name": "delete_task", "args": {"task_id": "t1"}, "description": "Delete this task?"}],
        },
    ]


def test_stream_turn_does_not_replay_earlier_turns_messages(monkeypatch):
    # stream_mode="values" re-yields the *full* message list every turn,
    # including whatever a prior stream_turn() call on the same thread
    # already sent as events — get_state() is how a fresh call learns to
    # skip those instead of re-emitting the whole conversation each turn.
    turn1_ai = AIMessage(content="Added the room.")
    turn2_ai = AIMessage(content="Deleted the task.")
    graph = FakeGraph(
        chunks=[{"messages": [turn1_ai, turn2_ai]}],
        existing_messages=[turn1_ai],
    )

    events = _events(monkeypatch, graph)

    assert events == [{"type": "message", "role": "assistant", "content": "Deleted the task."}, {"type": "done"}]


def test_stream_turn_emits_error_event_on_exception(monkeypatch):
    graph = FakeGraph([{"messages": []}], error=RuntimeError("model unavailable"))

    events = _events(monkeypatch, graph)

    assert events == [{"type": "error", "message": "model unavailable"}]


def test_history_events_replays_the_full_conversation(monkeypatch):
    messages = [
        HumanMessage(content="Add a Kitchen room."),
        AIMessage(tool_calls=[{"name": "add_room", "args": {"name": "Kitchen"}}]),
        ToolMessage(name="add_room", content={"ok": True}),
        AIMessage(content="Done — added Kitchen."),
    ]
    graph = FakeGraph(existing_messages=messages)
    monkeypatch.setattr(chat_stream, "build_orchestrator", lambda session: graph)

    events = chat_stream.history_events(PlanSession(), "thread-1")

    assert events == [
        {"type": "message", "role": "user", "content": "Add a Kitchen room.", "has_image": False},
        {"type": "tool_call", "calls": [{"name": "add_room", "args": {"name": "Kitchen"}}]},
        {"type": "tool_result", "name": "add_room", "content": "{'ok': True}"},
        {"type": "message", "role": "assistant", "content": "Done — added Kitchen."},
    ]


def test_history_events_includes_a_still_pending_interrupt(monkeypatch):
    messages = [
        HumanMessage(content="Delete the Paint walls task."),
        AIMessage(tool_calls=[{"name": "delete_task", "args": {"task_id": "t1"}}]),
    ]
    interrupt = FakeInterrupt(
        {"action_requests": [{"name": "delete_task", "args": {"task_id": "t1"}, "description": "Delete this task?"}]}
    )
    graph = FakeGraph(existing_messages=messages, interrupts=(interrupt,))
    monkeypatch.setattr(chat_stream, "build_orchestrator", lambda session: graph)

    events = chat_stream.history_events(PlanSession(), "thread-1")

    assert events[-1] == {
        "type": "interrupt",
        "actions": [{"name": "delete_task", "args": {"task_id": "t1"}, "description": "Delete this task?"}],
    }


def test_multimodal_human_message_extracts_text_and_flags_image(monkeypatch):
    # A room-photo turn's HumanMessage.content is a list of content blocks,
    # not a plain string — the event must carry only the text (never the
    # base64 image data back down to the browser) plus a has_image flag.
    photo_message = HumanMessage(
        content=[
            {"type": "text", "text": "What's in this room?"},
            {"type": "image", "source_type": "base64", "data": "aGVsbG8=", "mime_type": "image/png"},
        ]
    )
    ai_final = AIMessage(content="Looks like a bathroom mid-renovation.")
    graph = FakeGraph([{"messages": [photo_message]}, {"messages": [photo_message, ai_final]}])

    events = _events(monkeypatch, graph)

    assert events == [
        {"type": "message", "role": "user", "content": "What's in this room?", "has_image": True},
        {"type": "message", "role": "assistant", "content": "Looks like a bathroom mid-renovation."},
        {"type": "done"},
    ]


def test_multimodal_human_message_with_only_an_image_and_no_text(monkeypatch):
    photo_only = HumanMessage(content=[{"type": "image", "source_type": "base64", "data": "aGVsbG8="}])
    graph = FakeGraph([{"messages": [photo_only]}])

    events = _events(monkeypatch, graph)

    assert events[0] == {"type": "message", "role": "user", "content": "", "has_image": True}


def test_history_events_empty_for_a_fresh_thread(monkeypatch):
    graph = FakeGraph()
    monkeypatch.setattr(chat_stream, "build_orchestrator", lambda session: graph)

    assert chat_stream.history_events(PlanSession(), "brand-new-thread") == []
