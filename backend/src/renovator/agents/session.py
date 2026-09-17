"""A session's Plan, optionally backed by durable per-project storage.

With no `project_id`, this is a purely in-memory, non-persistent session —
useful for tests and one-off scripts. With a `project_id`, every mutating
tool call (tool_bindings.py) persists the plan and appends a changelog
entry via PlanStore (§4.7), so a conversation can resume after a restart
with the plan intact.
"""

from __future__ import annotations

from renovator.domain.models import Plan
from renovator.domain.seed import empty_plan
from renovator.store.plan_store import PlanStore


class PlanSession:
    def __init__(self, project_id: str | None = None, plan: Plan | None = None):
        self.project_id = project_id
        self.store: PlanStore | None = PlanStore(project_id) if project_id else None

        if plan is not None:
            self.plan = plan
        elif self.store is not None:
            self.plan = self.store.load_or_create()
        else:
            self.plan = empty_plan()

    def persist(self, action: str, detail: str = "") -> None:
        """Save the current plan and append a changelog entry. No-op for a
        non-persistent (no project_id) session."""
        if self.store is not None:
            self.store.save(self.plan, action=action, detail=detail)

    def changelog(self, limit: int = 50) -> list[dict]:
        return self.store.changelog(limit=limit) if self.store is not None else []
