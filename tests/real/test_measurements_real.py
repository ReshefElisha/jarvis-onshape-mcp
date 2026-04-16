"""Real-API tests for measure + mass_properties. Auto-skips without creds."""

from __future__ import annotations

import os
import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.measurements import MeasurementManager

SMOKE_DOC = "c287a50857bf10a5be2320c5"
SMOKE_WS = "24098a6dfa377ad0daa8e665"
SMOKE_PARTSTUDIO = "e3c89e99b01c0eb6fbfdc773"

# From list_entities on the smoke doc: 50x30x15mm box with a blind cylindrical hole.
TOP_FACE = "JHK"     # plane / normal +Z / origin at z=15mm
BOTTOM_FACE = "JNK"  # plane / normal +Z / origin at z=0mm
PLUSX_FACE = "JHO"   # plane / normal -X / origin at x=25mm
MINUSX_FACE = "JHW"  # plane / normal +X / origin at x=-25mm
CYL_FACE = "JNC"     # cylinder / axis +Z / radius 5mm


def _creds_present() -> bool:
    ak = os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY")
    sk = os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET")
    return bool(ak and sk)


pytestmark = pytest.mark.skipif(
    not _creds_present(),
    reason="ONSHAPE_ACCESS_KEY/SECRET_KEY or ONSHAPE_API_KEY/SECRET not set",
)


@pytest.fixture
async def mm():
    ak = os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY", "")
    sk = os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET", "")
    creds = OnshapeCredentials(access_key=ak, secret_key=sk)
    async with OnshapeClient(creds) as c:
        yield MeasurementManager(c)


@pytest.mark.asyncio
async def test_measure_parallel_faces_returns_correct_distance(mm):
    r = await mm.measure(
        SMOKE_DOC, SMOKE_WS, SMOKE_PARTSTUDIO,
        entity_a_id=TOP_FACE, entity_b_id=BOTTOM_FACE,
    )
    assert r["ok"]
    assert r["parallel"] is True
    assert abs(r["angle_deg"]) < 1e-3
    # Rectangular box is 15mm tall -> perpendicular plane-to-plane distance = 15mm.
    assert abs(r["projected_distance_mm"] - 15.0) < 1e-3
    assert abs(r["point_distance_mm"] - 15.0) < 1e-3


@pytest.mark.asyncio
async def test_measure_opposing_x_faces_are_parallel_and_50mm_apart(mm):
    r = await mm.measure(
        SMOKE_DOC, SMOKE_WS, SMOKE_PARTSTUDIO,
        entity_a_id=PLUSX_FACE, entity_b_id=MINUSX_FACE,
    )
    assert r["ok"]
    assert r["parallel"] is True
    assert abs(r["projected_distance_mm"] - 50.0) < 1e-3


@pytest.mark.asyncio
async def test_measure_adjacent_orthogonal_faces_are_perpendicular(mm):
    r = await mm.measure(
        SMOKE_DOC, SMOKE_WS, SMOKE_PARTSTUDIO,
        entity_a_id=TOP_FACE, entity_b_id=PLUSX_FACE,
    )
    assert r["ok"]
    assert r["perpendicular"] is True
    assert abs(r["angle_deg"] - 90.0) < 1e-3


@pytest.mark.asyncio
async def test_measure_cylinder_axis_parallel_to_top_normal(mm):
    """Cylinder drills straight through: its axis is parallel to the top face normal."""
    r = await mm.measure(
        SMOKE_DOC, SMOKE_WS, SMOKE_PARTSTUDIO,
        entity_a_id=CYL_FACE, entity_b_id=TOP_FACE,
    )
    assert r["ok"]
    assert r["parallel"] is True
    assert r["notes"], "should note that cylinder representative point is axis origin"


@pytest.mark.asyncio
async def test_measure_missing_entity_reports_error(mm):
    r = await mm.measure(
        SMOKE_DOC, SMOKE_WS, SMOKE_PARTSTUDIO,
        entity_a_id="NOPE", entity_b_id=TOP_FACE,
    )
    assert r["ok"] is False
    assert "NOPE" in r["error"]


@pytest.mark.asyncio
async def test_mass_properties_returns_volume(mm):
    r = await mm.mass_properties_part_studio(SMOKE_DOC, SMOKE_WS, SMOKE_PARTSTUDIO)
    assert "bodies" in r
    bodies = r["bodies"]
    assert len(bodies) >= 1
    first = next(iter(bodies.values()))
    # Volume comes back as [min, mean, max]; mean must be positive.
    vol = first.get("volume") or []
    assert len(vol) == 3
    assert vol[1] > 0, f"expected positive volume, got {vol}"
    # Expected ~50 x 30 x 15 - blind-hole volume. Box is 22.5 cm^3 = 22.5e-6 m^3.
    # Minus hole (pi * 5^2 * 2.3 mm^3 ~= 181 mm^3 = 1.8e-7 m^3) = ~22.3e-6 m^3.
    assert 20e-6 < vol[1] < 25e-6, f"volume out of expected range: {vol[1]}"
