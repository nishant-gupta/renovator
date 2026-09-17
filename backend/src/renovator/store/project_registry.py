"""The list of projects itself — separate from each project's own Plan data
(plan_store.py). Backed by one small JSON file (`projects.json`) under
`RENOVATOR_DATA_DIR`, since this is a local, single-user app with no need
for anything heavier.

A project's id is a stable slug (never shown to the user, never renamed);
its name is the user-editable display label. `default` — created before
this registry existed — is auto-registered the first time it's listed, so
existing users don't lose their project.
"""

from __future__ import annotations

import datetime
import json
import re
import uuid
from pathlib import Path

from renovator.store import global_settings as gs
from renovator.store.plan_store import PlanStore, checkpoint_db_path, data_dir, project_db_path
from renovator.tools.errors import ValidationError

_REGISTRY_FILE = "projects.json"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "project"


def _registry_path() -> Path:
    return data_dir() / _REGISTRY_FILE


def _read_registry() -> list[dict]:
    path = _registry_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _write_registry(entries: list[dict]) -> None:
    _registry_path().write_text(json.dumps(entries, indent=2))


def _bootstrap_existing_projects(entries: list[dict]) -> list[dict]:
    """Any `<id>.db` file with no registry entry (i.e. `default`, or a
    project created before this registry existed) gets one, name=id."""
    known_ids = {e["id"] for e in entries}
    for db_path in data_dir().glob("*.db"):
        project_id = db_path.stem
        if project_id in known_ids:
            continue
        entries.append({"id": project_id, "name": project_id, "created_at": _now(), "updated_at": _now()})
        known_ids.add(project_id)
    return entries


def list_projects() -> list[dict]:
    entries = _bootstrap_existing_projects(_read_registry())
    _write_registry(entries)
    return sorted(entries, key=lambda e: e["name"].lower())


def create_project(name: str) -> dict:
    name = name.strip()
    if not name:
        raise ValidationError("Project name is required.")
    entries = _bootstrap_existing_projects(_read_registry())
    existing_ids = {e["id"] for e in entries}

    base_slug = _slugify(name)
    project_id = base_slug
    if project_id in existing_ids:
        project_id = f"{base_slug}-{uuid.uuid4().hex[:6]}"

    entry = {"id": project_id, "name": name, "created_at": _now(), "updated_at": _now()}
    entries.append(entry)
    _write_registry(entries)

    # Materialize a plan immediately, seeded from the current global
    # defaults (timing flags + starter rate card), so the project shows up
    # with real data rather than only existing in the registry.
    plan_store = PlanStore(project_id)
    plan = plan_store.load_or_create()
    gs.seed_plan(plan)
    plan_store.save(plan, action="create_project", detail="Seeded from global defaults")
    return entry


def rename_project(project_id: str, name: str) -> dict:
    name = name.strip()
    if not name:
        raise ValidationError("Project name is required.")
    entries = _bootstrap_existing_projects(_read_registry())
    entry = next((e for e in entries if e["id"] == project_id), None)
    if not entry:
        raise ValidationError(f"No such project: {project_id}")
    entry["name"] = name
    entry["updated_at"] = _now()
    _write_registry(entries)
    return entry


def delete_project(project_id: str) -> None:
    entries = _bootstrap_existing_projects(_read_registry())
    if not any(e["id"] == project_id for e in entries):
        raise ValidationError(f"No such project: {project_id}")
    entries = [e for e in entries if e["id"] != project_id]
    _write_registry(entries)

    db_path = project_db_path(project_id)
    for path in (
        db_path,
        db_path.with_name(db_path.name + "-wal"),
        db_path.with_name(db_path.name + "-shm"),
        checkpoint_db_path(project_id),
    ):
        path.unlink(missing_ok=True)
