"""Defaults ported 1:1 from Renovation_Planner_v2.html (lines 296-400).

`example_plan()` is not implemented here — the seed example plan used for
golden-fixture testing is generated directly from the reference app's own JS
(see backend/scripts/generate_golden_fixture.js) rather than hand-transcribed,
so it can't drift from the source of truth. Load it via the `golden`/
`golden_plan` fixtures in tests/conftest.py instead of reimplementing it.
"""

from __future__ import annotations

import datetime

from renovator.domain.models import LineType, Phase, Plan, ProjectSettings, Rate, Stage

# Category -> default duration in working days (Renovation_Planner_v2.html:311-314).
CATEGORY_DURATION: dict[str, int] = {
    "Carpentry": 4,
    "Furnishing": 1,
    "Plumbing": 2,
    "Electrical": 2,
    "Tiling": 3,
    "Civil": 3,
    "Civil/POP": 3,
    "Flooring": 3,
    "Painting": 2,
    "Civil/Carpentry": 2,
    "Plumbing/Glasswork": 2,
    "Other": 1,
}

# Category -> default trade for Labor/Inclusive lines; Material is always
# "Material" (Renovation_Planner_v2.html:296-319).
CATEGORY_TRADE: dict[str, dict[str, str]] = {
    "Carpentry": {"labor": "Carpenter", "inclusive": "Carpenter"},
    "Furnishing": {"labor": "Carpenter/Vendor", "inclusive": "Carpenter/Vendor"},
    "Plumbing": {"labor": "Plumber", "inclusive": "Plumber"},
    "Electrical": {"labor": "Electrician", "inclusive": "Electrician"},
    "Tiling": {"labor": "Tile Installer", "inclusive": "Tile Installer"},
    "Civil": {"labor": "Mason", "inclusive": "Mason"},
    "Civil/POP": {"labor": "Mason / POP", "inclusive": "Mason / POP"},
    "Flooring": {"labor": "Flooring Contractor", "inclusive": "Flooring Contractor"},
    "Painting": {"labor": "Painter", "inclusive": "Painter"},
    "Civil/Carpentry": {"labor": "Mason / Carpenter", "inclusive": "Mason / Carpenter"},
    "Plumbing/Glasswork": {"labor": "Glass Fabricator", "inclusive": "Glass Fabricator"},
    "Other": {"labor": "", "inclusive": ""},
}


def trade_for(category: str, line_type: LineType | str) -> str:
    """Port of tradeFor() (Renovation_Planner_v2.html:315-319)."""
    lt = line_type.value if isinstance(line_type, LineType) else line_type
    if lt == LineType.MATERIAL.value:
        return "Material"
    mapping = CATEGORY_TRADE.get(category)
    if not mapping:
        return ""
    return mapping["labor"] if lt == LineType.LABOR.value else mapping["inclusive"]


def default_phases() -> list[Phase]:
    return [
        Phase(id=1, label="Phase 1 — Now"),
        Phase(id=2, label="Phase 2 — Next"),
        Phase(id=3, label="Phase 3 — Later"),
    ]


def default_stages() -> list[Stage]:
    return [
        Stage(id=1, label="Civil & POP repairs"),
        Stage(id=2, label="Rough plumbing"),
        Stage(id=3, label="Rough electrical"),
        Stage(id=4, label="False ceiling"),
        Stage(id=5, label="Tiling, flooring & countertop"),
        Stage(id=6, label="Glasswork"),
        Stage(id=7, label="Painting"),
        Stage(id=8, label="Electrical fixtures"),
        Stage(id=9, label="Bathroom fixtures"),
        Stage(id=10, label="Carpentry & furniture"),
    ]


def default_rates() -> list[Rate]:
    return [
        Rate(key="carpenter", label="Carpenter (inclusive)", unit="sqft", value=1500),
        Rate(key="paint_material", label="Paint — material", unit="sqft", value=11),
        Rate(key="paint_labor", label="Paint — labour", unit="sqft", value=9),
        Rate(key="civil_material", label="Civil / POP — material", unit="sqft", value=30),
        Rate(key="civil_labor", label="Civil / POP — labour", unit="sqft", value=25),
        Rate(key="tile_material", label="Tile — material", unit="sqft", value=130),
        Rate(key="tile_labor", label="Tile — labour", unit="sqft", value=40),
        Rate(key="granite_material", label="Countertop — material", unit="sqft", value=250),
        Rate(key="granite_labor", label="Countertop — labour", unit="sqft", value=80),
        Rate(
            key="electrical_material",
            label="Electrical — material (per point)",
            unit="point",
            value=1200,
        ),
        Rate(key="electrical_labor", label="Electrical — labour (per point)", unit="point", value=300),
        Rate(key="glass_material", label="Glass partition — material", unit="sqft", value=650),
        Rate(key="glass_labor", label="Glass partition — labour", unit="sqft", value=150),
        Rate(key="skirting", label="Skirting (inclusive)", unit="running ft", value=185),
    ]


def default_rooms() -> list[str]:
    return [
        "Master Bedroom",
        "Kids Room",
        "Guest Room",
        "Study Room",
        "Living Room",
        "Overall (Whole House)",
        "Balcony",
        "Kids Bathroom",
    ]


def empty_plan() -> Plan:
    """A valid, empty starting plan — real rooms/rates/items still to be added."""
    return Plan(
        settings=ProjectSettings(project_start=datetime.date.today().isoformat()),
        phases=default_phases(),
        stages=default_stages(),
    )
