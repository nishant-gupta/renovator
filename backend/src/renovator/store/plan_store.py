"""Local, single-tenant plan storage.

One SQLite file per project under RENOVATOR_DATA_DIR (default ~/.renovator).
The same directory also holds each project's LangGraph checkpoint file
(agents/orchestrator.py) — kept as a separate file/connection from this
store's tables to avoid sharing a sqlite3.Connection across two unrelated
schemas, even though both live under the same project id.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
from pathlib import Path

from renovator.domain.models import Plan
from renovator.domain.seed import empty_plan

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plan_snapshot (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    plan_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS changelog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL
);
"""


def data_dir() -> Path:
    raw = os.environ.get("RENOVATOR_DATA_DIR", "~/.renovator")
    path = Path(raw).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_db_path(project_id: str) -> Path:
    return data_dir() / f"{project_id}.db"


def checkpoint_db_path(project_id: str) -> Path:
    """Separate file for the LangGraph checkpointer (agents/orchestrator.py),
    so agent-history storage schema never shares a connection with ours."""
    return data_dir() / f"{project_id}.checkpoints.db"


class PlanStore:
    """Thin, synchronous wrapper around one project's SQLite file: the
    latest Plan snapshot, plus a changelog of what mutated it and when."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.db_path = project_db_path(project_id)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def load(self) -> Plan | None:
        with self._connect() as conn:
            row = conn.execute("SELECT plan_json FROM plan_snapshot WHERE id = 1").fetchone()
        return Plan.model_validate_json(row[0]) if row else None

    def load_or_create(self) -> Plan:
        plan = self.load()
        if plan is not None:
            return plan
        plan = empty_plan()
        self.save(plan, action="create_project", detail="Initialized empty plan")
        return plan

    def save(self, plan: Plan, action: str = "", detail: str = "") -> None:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        plan_json = plan.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO plan_snapshot (id, plan_json, updated_at) VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET plan_json = excluded.plan_json, updated_at = excluded.updated_at
                """,
                (plan_json, now),
            )
            if action:
                conn.execute(
                    "INSERT INTO changelog (at, action, detail) VALUES (?, ?, ?)",
                    (now, action, detail),
                )
            conn.commit()

    def last_updated_at(self) -> str | None:
        """Cheap poll target for the plan-change SSE stream (api/routes.py)
        — just the timestamp column, not the whole snapshot."""
        with self._connect() as conn:
            row = conn.execute("SELECT updated_at FROM plan_snapshot WHERE id = 1").fetchone()
        return row[0] if row else None

    def log_usage(self, model: str, input_tokens: int, output_tokens: int, duration_ms: int) -> None:
        """One row per model call (Phase 9's local cost/latency tracker,
        design doc §4.6 — an alternative to LangSmith that needs no
        external account). A single chat turn can log more than one row
        (main agent + a delegated sub-agent call each have their own)."""
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO usage_log (at, model, input_tokens, output_tokens, duration_ms) VALUES (?, ?, ?, ?, ?)",
                (now, model, input_tokens, output_tokens, duration_ms),
            )
            conn.commit()

    def usage_summary(self, recent_limit: int = 20) -> dict:
        with self._connect() as conn:
            total_calls, total_input, total_output, total_duration = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0), "
                "COALESCE(SUM(duration_ms), 0) FROM usage_log"
            ).fetchone()
            by_model = conn.execute(
                "SELECT model, COUNT(*), COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0) "
                "FROM usage_log GROUP BY model ORDER BY model"
            ).fetchall()
            recent = conn.execute(
                "SELECT at, model, input_tokens, output_tokens, duration_ms FROM usage_log "
                "ORDER BY id DESC LIMIT ?",
                (recent_limit,),
            ).fetchall()
        return {
            "total_calls": total_calls,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_duration_ms": total_duration,
            "by_model": [
                {"model": m, "calls": c, "input_tokens": it, "output_tokens": ot} for m, c, it, ot in by_model
            ],
            "recent": [
                {"at": at, "model": m, "input_tokens": it, "output_tokens": ot, "duration_ms": dm}
                for at, m, it, ot, dm in recent
            ],
        }

    def changelog(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT at, action, detail FROM changelog ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"at": r[0], "action": r[1], "detail": r[2]} for r in rows]
