"""Excel import/export tools (design doc §4.5/§4.11).

`import_plan_from_excel` replaces the whole plan, so — like the reference
app's `confirm()` dialog before importing (Renovation_Planner_v2.html:1665)
— it always requires `confirm=True`, routed through `interrupt_on` once
Phase 3/4 wires up the agent."""

from __future__ import annotations

from pathlib import Path

from renovator.domain.models import Plan
from renovator.io.excel_export import export_plan_to_excel as _export
from renovator.io.excel_import import import_plan_from_excel as _import
from renovator.tools.errors import ConfirmationRequired


def export_plan_to_excel(plan: Plan, out_path: Path) -> Path:
    return _export(plan, out_path)


def import_plan_from_excel(path: Path, confirm: bool = False) -> Plan:
    if not confirm:
        raise ConfirmationRequired(
            "Importing REPLACES everything currently in the planner. "
            "Export first if you want to keep the current plan. Continue?"
        )
    return _import(path)
