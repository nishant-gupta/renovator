"""Excel export -> import round-trip tests (design doc §4.11)."""

from __future__ import annotations

import pytest

from renovator.engine.cost import grand_total
from renovator.engine.schedule import compute_schedule, project_end_date
from renovator.engine.tasks import group_by_task
from renovator.tools import io_tools as io
from renovator.tools.errors import ConfirmationRequired, ValidationError


def test_export_import_round_trip_preserves_plan(golden_plan, tmp_path):
    out_path = tmp_path / "plan.xlsx"
    io.export_plan_to_excel(golden_plan, out_path)
    assert out_path.exists()

    reimported = io.import_plan_from_excel(out_path, confirm=True)

    assert sorted(reimported.rooms) == sorted(golden_plan.rooms)
    assert [p.label for p in reimported.phases] == [p.label for p in golden_plan.phases]
    assert [s.label for s in reimported.stages] == [s.label for s in golden_plan.stages]
    assert len(reimported.items) == len(golden_plan.items)

    assert grand_total(reimported, reimported.items) == grand_total(golden_plan, golden_plan.items)
    assert len(group_by_task(reimported)) == len(group_by_task(golden_plan))

    orig_end = project_end_date(compute_schedule(golden_plan))
    reimported_end = project_end_date(compute_schedule(reimported))
    assert reimported_end == orig_end


def test_import_requires_confirmation(golden_plan, tmp_path):
    out_path = tmp_path / "plan.xlsx"
    io.export_plan_to_excel(golden_plan, out_path)
    with pytest.raises(ConfirmationRequired):
        io.import_plan_from_excel(out_path)


def test_import_missing_items_sheet_rejected(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.title = "Nothing Useful"
    path = tmp_path / "empty.xlsx"
    wb.save(path)
    with pytest.raises(ValidationError):
        io.import_plan_from_excel(path, confirm=True)
