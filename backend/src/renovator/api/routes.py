"""API endpoints (design doc §4.10) consumed by the rebuilt frontend.

Full CRUD for every tab, project management + cross-project transfer,
Excel import/export, and (Phase 7) the agentic chat endpoint plus the
plan-change SSE stream the canvas uses to know when to re-fetch.

Each request loads the project's Plan fresh from `PlanStore` and saves it
back after a successful mutation — there is no long-lived PlanSession here
for the direct-manipulation routes (that's the agent's concern,
agents/session.py); a plain HTTP request is naturally one-shot. `/chat` is
the one exception — it builds a fresh `PlanSession`/orchestrator per
request, but the LangGraph checkpointer and `PlanStore` are both keyed by
`project_id`, so conversation and plan state both resume correctly across
requests (and process restarts) without needing an in-memory session.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel

from renovator.agents.chat_stream import history_events, stream_turn
from renovator.agents.session import PlanSession
from renovator.store import global_settings as gs
from renovator.store import project_registry as registry
from renovator.store.plan_store import PlanStore
from renovator.tools import crud_tools as ct
from renovator.tools import io_tools as iot
from renovator.tools import read_tools as rt
from renovator.tools import template_tools as tt
from renovator.tools import transfer_tools as tfr
from renovator.tools.errors import ConfirmationRequired, ValidationError

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Collection-level (no project id in the path): list/create projects.
projects_router = APIRouter(prefix="/projects")

# Per-project: everything else.
router = APIRouter(prefix="/projects/{project_id}")

# Org-wide defaults new projects are seeded with (seed-only, never live).
settings_router = APIRouter(prefix="/settings/global")


def _store(project_id: str) -> PlanStore:
    return PlanStore(project_id)


# ---- project management (create/list/rename/delete) ------------------------


@projects_router.get("")
def list_projects() -> list[dict]:
    return registry.list_projects()


class CreateProjectBody(BaseModel):
    name: str


@projects_router.post("")
def create_project(body: CreateProjectBody) -> dict:
    try:
        return registry.create_project(body.name)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class RenameProjectBody(BaseModel):
    name: str


@router.patch("")
def rename_project(project_id: str, body: RenameProjectBody) -> dict:
    try:
        return registry.rename_project(project_id, body.name)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("")
def delete_project(project_id: str, confirm: bool = Query(False)) -> dict:
    if not confirm:
        raise HTTPException(
            status_code=409,
            detail="This permanently deletes the project and everything in it. Continue?",
        )
    try:
        registry.delete_project(project_id)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


# ---- global defaults (settings_router) -------------------------------------


@settings_router.get("")
def get_global_settings() -> dict:
    return gs.get_global_settings()


class UpdateGlobalSettingsBody(BaseModel):
    weekend_policy: str | None = None
    sequence_stages: bool | None = None


@settings_router.patch("")
def update_global_settings(body: UpdateGlobalSettingsBody) -> dict:
    try:
        return gs.update_global_settings(body.model_dump(exclude_none=True))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class AddGlobalRateBody(BaseModel):
    label: str
    unit: str
    value: float


@settings_router.post("/rates")
def add_global_rate(body: AddGlobalRateBody) -> dict:
    try:
        return gs.add_global_rate(body.label, body.unit, body.value)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class UpdateGlobalRateBody(BaseModel):
    value: float


@settings_router.patch("/rates/{key}")
def update_global_rate(key: str, body: UpdateGlobalRateBody) -> dict:
    try:
        return gs.update_global_rate(key, body.value)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@settings_router.delete("/rates/{key}")
def delete_global_rate(key: str) -> dict:
    return gs.delete_global_rate(key)


class BlockedDateBody(BaseModel):
    date: str  # yyyy-mm-dd


@settings_router.post("/blocked-dates")
def add_global_blocked_date(body: BlockedDateBody) -> dict:
    try:
        return gs.add_global_blocked_date(body.date)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@settings_router.delete("/blocked-dates/{date}")
def delete_global_blocked_date(date: str) -> dict:
    try:
        return gs.remove_global_blocked_date(date)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _mutate(project_id: str, action: str, detail: str, fn) -> None:
    """Load the plan, apply `fn(plan)`, persist on success. Raises
    HTTPException(400) for ValidationError, HTTPException(409) for
    ConfirmationRequired (the client must retry with confirm=true)."""
    store = _store(project_id)
    plan = store.load_or_create()
    try:
        fn(plan)
    except ConfirmationRequired as e:
        raise HTTPException(status_code=409, detail=e.reason) from e
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    store.save(plan, action=action, detail=detail)


# ---- read endpoints, one per tab -------------------------------------------


@router.get("/setup")
def get_setup(project_id: str) -> dict:
    return rt.get_setup(_store(project_id).load_or_create())


@router.get("/tasks")
def get_tasks(project_id: str) -> list[dict]:
    return rt.get_tasks(_store(project_id).load_or_create())


@router.get("/schedule")
def get_schedule(project_id: str) -> dict:
    return rt.get_schedule(_store(project_id).load_or_create())


@router.get("/suggested-order")
def get_suggested_order(project_id: str) -> list[dict]:
    return rt.get_suggested_order(_store(project_id).load_or_create())


@router.get("/materials")
def get_materials(project_id: str) -> dict:
    return rt.get_materials_plan(_store(project_id).load_or_create())


@router.get("/estimate")
def get_estimate(project_id: str) -> dict:
    return rt.get_estimate_summary(_store(project_id).load_or_create())


@router.get("/track")
def get_track(project_id: str) -> dict:
    return rt.get_track_summary(_store(project_id).load_or_create())


@router.get("/changelog")
def get_changelog(project_id: str, limit: int = 50) -> list[dict]:
    return _store(project_id).changelog(limit=limit)


# ---- setup mutations --------------------------------------------------------


class AddRoomBody(BaseModel):
    name: str


class RenameRoomBody(BaseModel):
    new_name: str


@router.post("/rooms")
def add_room(project_id: str, body: AddRoomBody) -> dict:
    _mutate(project_id, "add_room", f"Added room '{body.name}'", lambda plan: ct.add_room(plan, body.name))
    return get_setup(project_id)


@router.patch("/rooms/{name}")
def rename_room(project_id: str, name: str, body: RenameRoomBody) -> dict:
    _mutate(
        project_id,
        "rename_room",
        f"Renamed room '{name}' -> '{body.new_name}'",
        lambda plan: ct.rename_room(plan, name, body.new_name),
    )
    return get_setup(project_id)


@router.delete("/rooms/{name}")
def remove_room(project_id: str, name: str, confirm: bool = Query(False)) -> dict:
    _mutate(project_id, "remove_room", f"Removed room '{name}'", lambda plan: ct.remove_room(plan, name, confirm=confirm))
    return get_setup(project_id)


class AddRateBody(BaseModel):
    label: str
    unit: str
    value: float


class UpdateRateBody(BaseModel):
    value: float


@router.post("/rates")
def add_rate(project_id: str, body: AddRateBody) -> dict:
    _mutate(
        project_id,
        "add_rate",
        f"Added rate '{body.label}'",
        lambda plan: ct.add_rate(plan, body.label, body.unit, body.value),
    )
    return get_setup(project_id)


@router.patch("/rates/{key}")
def update_rate(project_id: str, key: str, body: UpdateRateBody) -> dict:
    _mutate(
        project_id, "update_rate", f"Set rate '{key}' to {body.value}", lambda plan: ct.update_rate(plan, key, body.value)
    )
    return get_setup(project_id)


@router.delete("/rates/{key}")
def delete_rate(project_id: str, key: str, confirm: bool = Query(False)) -> dict:
    _mutate(project_id, "delete_rate", f"Deleted rate '{key}'", lambda plan: ct.delete_rate(plan, key, confirm=confirm))
    return get_setup(project_id)


class AddLabelBody(BaseModel):
    label: str


class ReorderBody(BaseModel):
    index: int
    direction: int


@router.post("/phases")
def add_phase(project_id: str, body: AddLabelBody) -> dict:
    _mutate(project_id, "add_phase", f"Added phase '{body.label}'", lambda plan: ct.add_phase(plan, body.label))
    return get_setup(project_id)


@router.patch("/phases/{phase_id}")
def rename_phase(project_id: str, phase_id: int, body: AddLabelBody) -> dict:
    _mutate(
        project_id,
        "rename_phase",
        f"Renamed phase {phase_id} -> '{body.label}'",
        lambda plan: ct.rename_phase(plan, phase_id, body.label),
    )
    return get_setup(project_id)


@router.delete("/phases/{phase_id}")
def remove_phase(project_id: str, phase_id: int, confirm: bool = Query(False)) -> dict:
    _mutate(
        project_id,
        "remove_phase",
        f"Removed phase {phase_id}",
        lambda plan: ct.remove_phase(plan, phase_id, confirm=confirm),
    )
    return get_setup(project_id)


@router.post("/phases/reorder")
def move_phase(project_id: str, body: ReorderBody) -> dict:
    _mutate(
        project_id,
        "move_phase",
        f"Moved phase at {body.index} by {body.direction}",
        lambda plan: ct.move_phase(plan, body.index, body.direction),
    )
    return get_setup(project_id)


@router.post("/stages")
def add_stage(project_id: str, body: AddLabelBody) -> dict:
    _mutate(project_id, "add_stage", f"Added stage '{body.label}'", lambda plan: ct.add_stage(plan, body.label))
    return get_setup(project_id)


@router.patch("/stages/{stage_id}")
def rename_stage(project_id: str, stage_id: int, body: AddLabelBody) -> dict:
    _mutate(
        project_id,
        "rename_stage",
        f"Renamed stage {stage_id} -> '{body.label}'",
        lambda plan: ct.rename_stage(plan, stage_id, body.label),
    )
    return get_setup(project_id)


@router.delete("/stages/{stage_id}")
def remove_stage(project_id: str, stage_id: int, confirm: bool = Query(False)) -> dict:
    _mutate(
        project_id,
        "remove_stage",
        f"Removed stage {stage_id}",
        lambda plan: ct.remove_stage(plan, stage_id, confirm=confirm),
    )
    return get_setup(project_id)


@router.post("/stages/reorder")
def move_stage(project_id: str, body: ReorderBody) -> dict:
    _mutate(
        project_id,
        "move_stage",
        f"Moved stage at {body.index} by {body.direction}",
        lambda plan: ct.move_stage(plan, body.index, body.direction),
    )
    return get_setup(project_id)


class SettingsBody(BaseModel):
    project_start: str | None = None
    weekend_policy: str | None = None
    sequence_stages: bool | None = None


@router.patch("/settings")
def set_project_settings(project_id: str, body: SettingsBody) -> dict:
    _mutate(
        project_id,
        "set_project_settings",
        f"start={body.project_start} weekend_policy={body.weekend_policy} sequence={body.sequence_stages}",
        lambda plan: ct.set_project_settings(
            plan,
            project_start=body.project_start,
            weekend_policy=body.weekend_policy,
            sequence_stages=body.sequence_stages,
        ),
    )
    return get_setup(project_id)


@router.post("/blocked-dates")
def add_blocked_date(project_id: str, body: BlockedDateBody) -> dict:
    _mutate(
        project_id,
        "add_blocked_date",
        f"Blocked {body.date}",
        lambda plan: ct.add_blocked_date(plan, body.date),
    )
    return get_setup(project_id)


@router.delete("/blocked-dates/{date}")
def remove_blocked_date(project_id: str, date: str) -> dict:
    _mutate(
        project_id,
        "remove_blocked_date",
        f"Unblocked {date}",
        lambda plan: ct.remove_blocked_date(plan, date),
    )
    return get_setup(project_id)


# ---- tasks (feature.md §4) --------------------------------------------------


@router.get("/templates")
def list_templates(project_id: str) -> list[dict]:
    return tt.list_templates()


class InstantiateTemplateBody(BaseModel):
    template_id: str
    room: str
    name: str | None = None
    qty: float | None = None
    phase: int | None = None
    stage_id: int | None = None


@router.post("/tasks/from-template")
def instantiate_template(project_id: str, body: InstantiateTemplateBody) -> list[dict]:
    _mutate(
        project_id,
        "instantiate_template",
        f"'{body.template_id}' in {body.room}",
        lambda plan: tt.instantiate_template(
            plan,
            body.template_id,
            room=body.room,
            name=body.name,
            qty=body.qty,
            phase=body.phase,
            stage_id=body.stage_id,
        ),
    )
    return get_tasks(project_id)


@router.post("/tasks")
def create_task(project_id: str, body: ct.TaskInput) -> list[dict]:
    _mutate(project_id, "create_task", f"Created '{body.name}' in {body.room}", lambda plan: ct.create_task(plan, body))
    return get_tasks(project_id)


@router.patch("/tasks/{task_id}")
def update_task(project_id: str, task_id: str, body: ct.TaskInput) -> list[dict]:
    body.task_id = task_id
    _mutate(project_id, "update_task", f"Updated task {task_id}", lambda plan: ct.update_task(plan, body))
    return get_tasks(project_id)


@router.delete("/tasks/{task_id}")
def delete_task(project_id: str, task_id: str, confirm: bool = Query(False)) -> list[dict]:
    _mutate(
        project_id,
        "delete_task",
        f"Deleted task {task_id}",
        lambda plan: ct.delete_task(plan, task_id, confirm=confirm),
    )
    return get_tasks(project_id)


class MoveToStageBody(BaseModel):
    task_ids: list[str]
    stage_id: int | None


@router.post("/tasks/move-to-stage")
def move_tasks_to_stage(project_id: str, body: MoveToStageBody) -> dict:
    """Reassign one or more tasks to a stage (stage_id=null -> unassigned) —
    the Board view's drag-a-card-between-columns action (feature.md §5.3),
    and (bulk) Tasks tab's "Move to stage…" action (feature.md §4.3).
    Returns the schedule, since moving stages changes computed dates."""
    _mutate(
        project_id,
        "bulk_move_to_stage",
        f"{len(body.task_ids)} task(s) -> stage {body.stage_id}",
        lambda plan: ct.bulk_move_to_stage(plan, body.task_ids, body.stage_id),
    )
    return get_schedule(project_id)


class BulkMandatoryBody(BaseModel):
    task_ids: list[str]
    mandatory: bool


@router.post("/tasks/bulk-mandatory")
def bulk_set_mandatory(project_id: str, body: BulkMandatoryBody) -> list[dict]:
    """Tasks tab's "Mark mandatory/optional" bulk action (feature.md §4.3)."""
    _mutate(
        project_id,
        "bulk_set_mandatory",
        f"{len(body.task_ids)} task(s) -> mandatory={body.mandatory}",
        lambda plan: ct.bulk_set_mandatory(plan, body.task_ids, body.mandatory),
    )
    return get_tasks(project_id)


class BulkPhaseBody(BaseModel):
    task_ids: list[str]
    phase_id: int


@router.post("/tasks/bulk-phase")
def bulk_move_to_phase(project_id: str, body: BulkPhaseBody) -> list[dict]:
    """Tasks tab's "Move to phase…" bulk action (feature.md §4.3)."""
    _mutate(
        project_id,
        "bulk_move_to_phase",
        f"{len(body.task_ids)} task(s) -> phase {body.phase_id}",
        lambda plan: ct.bulk_move_to_phase(plan, body.task_ids, body.phase_id),
    )
    return get_tasks(project_id)


class BulkTaskIdsBody(BaseModel):
    task_ids: list[str]


@router.post("/tasks/bulk-delete")
def bulk_delete_tasks(project_id: str, body: BulkTaskIdsBody, confirm: bool = Query(False)) -> list[dict]:
    """Tasks tab's bulk "Delete" action (feature.md §4.3). Requires human
    confirmation, same as a single delete_task."""
    _mutate(
        project_id,
        "bulk_delete_tasks",
        f"Deleted {len(body.task_ids)} task(s)",
        lambda plan: ct.bulk_delete_tasks(plan, body.task_ids, confirm=confirm),
    )
    return get_tasks(project_id)


class UpdateLineBody(BaseModel):
    buy_status: str | None = None
    status: str | None = None
    actual_cost: float | None = None
    notes: str | None = None


@router.patch("/lines/{line_id}")
def update_line(project_id: str, line_id: str, body: UpdateLineBody) -> list[dict]:
    """Lightweight partial update for Materials/Track inline editing
    (feature.md §6/§8) — patches one line's buy-status/status/actual-cost/
    notes without resending the whole task (unlike PATCH /tasks/{task_id})."""
    _mutate(
        project_id,
        "update_line",
        f"Updated line {line_id}",
        lambda plan: ct.update_line(
            plan,
            line_id,
            buy_status=body.buy_status,
            status=body.status,
            actual_cost=body.actual_cost,
            notes=body.notes,
        ),
    )
    return get_tasks(project_id)


# ---- cross-project transfer -------------------------------------------------


class TransferTasksBody(BaseModel):
    task_ids: list[str]
    target_project_id: str | None = None  # provide this OR new_project_name
    new_project_name: str | None = None
    mode: Literal["copy", "move"]


@router.post("/tasks/transfer")
def transfer_tasks(project_id: str, body: TransferTasksBody) -> dict:
    """Copy or move one or more tasks into another (existing or brand new)
    project. Rooms/rates/phases/stages are matched by label in the target,
    creating them there if they don't already exist; dependencies pointing
    outside the transferred set are dropped rather than left dangling."""
    target_id = body.target_project_id
    if not target_id:
        if not body.new_project_name:
            raise HTTPException(status_code=400, detail="Provide target_project_id or new_project_name.")
        try:
            target_id = registry.create_project(body.new_project_name)["id"]
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    if target_id == project_id:
        raise HTTPException(status_code=400, detail="Source and target project must be different.")

    source_store, target_store = _store(project_id), _store(target_id)
    source_plan, target_plan = source_store.load_or_create(), target_store.load_or_create()

    try:
        result = tfr.transfer_tasks(source_plan, target_plan, body.task_ids, body.mode)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    target_store.save(
        target_plan, action="transfer_in", detail=f"{result.transferred_task_count} task(s) from '{project_id}'"
    )
    if body.mode == "move":
        source_store.save(
            source_plan, action="transfer_out", detail=f"{result.transferred_task_count} task(s) to '{target_id}'"
        )

    return {
        "target_project_id": target_id,
        "transferred_task_count": result.transferred_task_count,
        "created_rooms": result.created_rooms,
        "created_rates": result.created_rates,
        "created_phases": result.created_phases,
        "created_stages": result.created_stages,
        "dropped_dependencies": result.dropped_dependencies,
    }


# ---- excel (feature.md §9) --------------------------------------------------


@router.get("/export.xlsx")
def export_excel(project_id: str) -> Response:
    plan = _store(project_id).load_or_create()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "plan.xlsx"
        iot.export_plan_to_excel(plan, path)
        data = path.read_bytes()
    return Response(
        content=data,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="Home_Renovation_Plan.xlsx"'},
    )


@router.post("/import")
async def import_excel(
    project_id: str, file: UploadFile = File(...), confirm: bool = Query(False)  # noqa: B008 - FastAPI convention
) -> dict:
    if not confirm:
        raise HTTPException(
            status_code=409,
            detail="Importing REPLACES everything currently in the planner. "
            "Export first if you want to keep the current plan. Continue?",
        )
    contents = await file.read()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / (file.filename or "upload.xlsx")
        path.write_bytes(contents)
        try:
            plan = iot.import_plan_from_excel(path, confirm=True)
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    store = _store(project_id)
    store.save(plan, action="import_plan_from_excel", detail=f"Imported '{file.filename}'")
    return get_setup(project_id)


# ---- agentic chat & the plan-change stream (design doc §4.10/§4.6, Phase 7/8) --

SSE_MEDIA_TYPE = "text/event-stream"

# A decoded-size cap on an attached room photo (Phase 8) — generous enough
# for a real phone photo, small enough that one request can't balloon
# memory/context. Checked against the base64 payload length, which is
# ~4/3 the decoded size, so this is intentionally a bit above the nominal
# 8MB decoded target.
_MAX_IMAGE_B64_CHARS = 11_000_000


def _parse_data_url(data_url: str) -> tuple[str, str]:
    """Splits a `data:<mime>;base64,<payload>` string (what a browser's
    FileReader.readAsDataURL produces) into (mime_type, base64_payload)."""
    header, _, payload = data_url.partition(",")
    mime = "image/jpeg"
    if header.startswith("data:"):
        mime = header[len("data:") :].split(";")[0] or mime
    return mime, payload


class ChatMessageBody(BaseModel):
    # Provide exactly one: a new user message (optionally with an attached
    # room photo, Phase 8), or a resume decision for a gated tool call the
    # previous turn's `interrupt` event asked about (`decisions`: one
    # {"type": "approve"} or {"type": "reject", "message": str} per pending
    # action, in the same order they were listed).
    message: str | None = None
    image: str | None = None  # a data: URL, e.g. "data:image/jpeg;base64,..."
    resume: dict | None = None


@router.post("/chat")
def chat(project_id: str, body: ChatMessageBody) -> StreamingResponse:
    if body.resume is not None:
        step_input = Command(resume=body.resume)
    elif body.image:
        mime, payload = _parse_data_url(body.image)
        if len(payload) > _MAX_IMAGE_B64_CHARS:
            raise HTTPException(status_code=400, detail="Photo is too large.")
        content = [{"type": "text", "text": body.message or "Here's a photo of the room."}]
        content.append({"type": "image", "source_type": "base64", "data": payload, "mime_type": mime})
        step_input = {"messages": [{"role": "user", "content": content}]}
    elif body.message:
        step_input = {"messages": [{"role": "user", "content": body.message}]}
    else:
        raise HTTPException(status_code=400, detail="Provide message, image, or resume.")

    session = PlanSession(project_id=project_id)
    return StreamingResponse(stream_turn(session, project_id, step_input), media_type=SSE_MEDIA_TYPE)


@router.get("/chat/history")
def get_chat_history(project_id: str) -> dict:
    session = PlanSession(project_id=project_id)
    return {"events": history_events(session, project_id)}


@router.get("/usage")
def get_usage(project_id: str) -> dict:
    """Phase 9's local cost/latency dashboard data — cumulative token
    counts/duration per model call this project's chat has made, logged by
    chat_stream.py's usage_event() after every turn. Estimated cost only
    (agents/pricing.py); real billing includes prompt-caching discounts
    this doesn't model."""
    return PlanSession(project_id=project_id).usage_summary()


def _plan_events(project_id: str, poll_interval: float, max_polls: int | None):
    """Yields an SSE event whenever the plan's `updated_at` changes — cheap
    enough to poll (one indexed column read) and avoids needing an
    in-process pub/sub layer for a single-user local app. `max_polls`
    bounds the loop for tests; production callers leave it unbounded."""
    store = _store(project_id)
    last = store.last_updated_at()
    yield f"data: {json.dumps({'type': 'ready'})}\n\n"
    polls = 0
    while max_polls is None or polls < max_polls:
        time.sleep(poll_interval)
        current = store.last_updated_at()
        if current != last:
            last = current
            yield f"data: {json.dumps({'type': 'changed', 'updated_at': current})}\n\n"
        polls += 1


@router.get("/plan-events")
def plan_events(project_id: str) -> StreamingResponse:
    return StreamingResponse(_plan_events(project_id, poll_interval=1.0, max_polls=None), media_type=SSE_MEDIA_TYPE)
