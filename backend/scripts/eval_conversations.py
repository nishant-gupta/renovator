"""Golden conversation-eval suite (design doc §4.6/Phase 9, feature.md §11).

Scripted multi-turn conversations against the real Anthropic API, one per
feature.md §11 "suggested workflow". Assertions check *structural*
correctness of the resulting plan state (rooms/tasks/phases/dependencies/
status actually landed right) rather than exact wording, since a model's
phrasing varies run to run even when its actions are correct.

Costs real API calls — not part of the pytest suite or the default CI
workflow. Run manually:

    uv run python scripts/eval_conversations.py

Uses its own isolated RENOVATOR_DATA_DIR (a fresh temp directory, removed
at the end) so it never touches ~/.renovator, and a fresh scratch project
per scenario, deleted whether that scenario passes or fails.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

_DATA_DIR = tempfile.mkdtemp(prefix="renovator-eval-")
os.environ["RENOVATOR_DATA_DIR"] = _DATA_DIR
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi.testclient import TestClient  # noqa: E402

from renovator.app import app  # noqa: E402

client = TestClient(app, headers={"Content-Type": "application/json"})


def send(project_id: str, message: str) -> list[dict]:
    """One chat turn; returns every SSE event, parsed. Raises if the turn
    ends on an interrupt — no scenario here should trigger a gated tool,
    that machinery is already covered by the Phase 7/8 live validations."""
    events = []
    with client.stream("POST", f"/projects/{project_id}/chat", json={"message": message}) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    if any(e["type"] == "interrupt" for e in events):
        raise AssertionError(f"turn unexpectedly hit an interrupt: {events}")
    if any(e["type"] == "error" for e in events):
        raise AssertionError(f"turn errored: {events}")
    return events


def new_project(name: str) -> str:
    return client.post("/projects", json={"name": name}).json()["id"]


def cleanup(project_id: str) -> None:
    client.delete(f"/projects/{project_id}?confirm=true")


# ---- scenarios, one per feature.md §11 workflow ----------------------------


def scenario_starting_a_plan() -> None:
    """"Starting a real plan" — a freeform brief should produce a real room
    and a real task via a template, not just a description of what it would
    do."""
    pid = new_project("Eval: starting a plan")
    try:
        send(
            pid,
            "I'm renovating my kitchen. Add a Kitchen room, then create a Fresh Paint task there "
            "using the matching template.",
        )
        setup = client.get(f"/projects/{pid}/setup").json()
        tasks = client.get(f"/projects/{pid}/tasks").json()
        assert "Kitchen" in setup["rooms"], f"expected a Kitchen room, got {setup['rooms']}"
        assert any(t["room"] == "Kitchen" for t in tasks), f"expected a task in Kitchen, got {tasks}"
        assert any(t["category"] == "Painting" for t in tasks), f"expected a Painting task, got {tasks}"
    finally:
        cleanup(pid)


def scenario_templates_and_bulk_actions() -> None:
    """"Fastest way to enter a lot of work" — template-based creation, then
    bulk-style follow-ups (mark optional, push to a later phase) via chat."""
    pid = new_project("Eval: templates and bulk actions")
    try:
        client.post(f"/projects/{pid}/rooms", json={"name": "Kitchen"})
        send(
            pid,
            "Create a Re-tile task for the Kitchen floor using a template with quantity 120 sqft, "
            "then mark it optional and move it to Phase 2.",
        )
        setup = client.get(f"/projects/{pid}/setup").json()
        tasks = client.get(f"/projects/{pid}/tasks").json()
        phase2_id = next(p["id"] for p in setup["phases"] if p["label"].startswith("Phase 2"))
        tiling = next((t for t in tasks if t["category"] == "Tiling"), None)
        assert tiling is not None, f"expected a Tiling task, got {tasks}"
        assert tiling["mandatory"] is False, f"expected it optional, got {tiling}"
        assert tiling["phase"] == phase2_id, f"expected phase {phase2_id}, got {tiling['phase']}"
    finally:
        cleanup(pid)


def scenario_sequencing_with_dependencies() -> None:
    """"Getting the sequence right" — a dependency should only be wired up
    where the user actually asked for one, by name, without the user
    needing to know line ids."""
    pid = new_project("Eval: sequencing")
    try:
        client.post(f"/projects/{pid}/rooms", json={"name": "Bathroom"})
        client.post(
            f"/projects/{pid}/tasks",
            json={
                "room": "Bathroom",
                "name": "Fix the leak",
                "category": "Plumbing",
                "phase": 1,
                "structure": "single",
                "single_line_type": "Inclusive",
                "single": {"cost_method": "custom", "custom_amount": 2000},
            },
        )
        # Both routes return the *full* task list (routes.py's `_mutate` +
        # `get_tasks`), not just the one just created — find each by name
        # rather than assuming a position.
        tasks_before = client.post(
            f"/projects/{pid}/tasks/from-template",
            json={"template_id": "retile", "room": "Bathroom", "qty": 80},
        ).json()
        leak = next(t for t in tasks_before if t["name"] == "Fix the leak")
        retile = next(t for t in tasks_before if t["name"] == "Re-tile wall / floor")

        send(
            pid,
            "Make sure 'Fix the leak' finishes before 'Re-tile wall / floor' starts in the Bathroom — "
            "set that dependency.",
        )

        tasks = client.get(f"/projects/{pid}/tasks").json()
        retile_after = next(t for t in tasks if t["task_id"] == retile["task_id"])
        leak_line_ids = {leak_line["line_id"] for leak_line in leak["lines"]}
        retile_depends_on = {dep for line in retile_after["lines"] for dep in line["depends_on"]}
        assert retile_depends_on & leak_line_ids, (
            f"expected a re-tile line to depend on a leak-fix line; "
            f"leak lines={leak_line_ids}, retile depends_on={retile_depends_on}"
        )
    finally:
        cleanup(pid)


def scenario_budget_pushes_not_deletes() -> None:
    """"Managing the budget" — over budget should move optional work later,
    never delete it (design doc §4.6's budget agent, feature.md §11)."""
    pid = new_project("Eval: budget triage")
    try:
        client.post(f"/projects/{pid}/rooms", json={"name": "Living Room"})
        optional_task = client.post(
            f"/projects/{pid}/tasks",
            json={
                "room": "Living Room",
                "name": "Accent wall wallpaper",
                "category": "Painting",
                "phase": 1,
                "mandatory": False,
                "structure": "single",
                "single_line_type": "Inclusive",
                "single": {"cost_method": "custom", "custom_amount": 50000},
            },
        ).json()[0]
        client.post(
            f"/projects/{pid}/tasks",
            json={
                "room": "Living Room",
                "name": "Electrical rewiring",
                "category": "Electrical",
                "phase": 1,
                "mandatory": True,
                "structure": "single",
                "single_line_type": "Inclusive",
                "single": {"cost_method": "custom", "custom_amount": 60000},
            },
        )

        before_count = len(client.get(f"/projects/{pid}/tasks").json())
        send(
            pid,
            "My budget is ₹70,000 and I'm over it. Don't delete any work — push optional tasks to a "
            "later phase instead.",
        )

        tasks_after = client.get(f"/projects/{pid}/tasks").json()
        assert len(tasks_after) == before_count, f"expected no deletions, had {before_count} now {len(tasks_after)}"
        wallpaper_after = next(t for t in tasks_after if t["task_id"] == optional_task["task_id"])
        assert wallpaper_after["phase"] != 1, f"expected the optional task pushed off phase 1, still: {wallpaper_after}"
    finally:
        cleanup(pid)


def scenario_on_site_tracking() -> None:
    """"On site" — logging status/actuals during the build should show up
    correctly in tracking, including variance against the estimate."""
    pid = new_project("Eval: on-site tracking")
    try:
        client.post(f"/projects/{pid}/rooms", json={"name": "Kitchen"})
        task = client.post(
            f"/projects/{pid}/tasks",
            json={
                "room": "Kitchen",
                "name": "Fresh paint",
                "category": "Painting",
                "phase": 1,
                "structure": "single",
                "single_line_type": "Inclusive",
                "single": {"cost_method": "custom", "custom_amount": 10000},
            },
        ).json()[0]

        send(pid, "The Fresh paint task in the Kitchen is done. It actually cost ₹12,000.")

        tasks_after = client.get(f"/projects/{pid}/tasks").json()
        line = next(iter(next(t for t in tasks_after if t["task_id"] == task["task_id"])["lines"]))
        assert line["status"] == "Done", f"expected status Done, got {line}"
        assert line["actual_cost"] == 12000, f"expected actual_cost 12000, got {line}"

        track = client.get(f"/projects/{pid}/track").json()
        assert track["actuals_logged"] >= 1, f"expected at least one actual logged, got {track}"
    finally:
        cleanup(pid)


SCENARIOS = [
    scenario_starting_a_plan,
    scenario_templates_and_bulk_actions,
    scenario_sequencing_with_dependencies,
    scenario_budget_pushes_not_deletes,
    scenario_on_site_tracking,
]


def main() -> int:
    results: list[tuple[str, bool, str]] = []
    for scenario in SCENARIOS:
        name = scenario.__doc__.splitlines()[0] if scenario.__doc__ else scenario.__name__
        print(f"== {scenario.__name__}: {name} ==")
        try:
            scenario()
            print("  PASS")
            results.append((scenario.__name__, True, ""))
        except Exception as e:  # noqa: BLE001 - report every scenario, don't stop the run
            print(f"  FAIL: {e}")
            traceback.print_exc()
            results.append((scenario.__name__, False, str(e)))

    print("\n== summary ==")
    failed = [r for r in results if not r[1]]
    for name, ok, _ in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    shutil.rmtree(_DATA_DIR, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
