"""Real-API proof that arc start/end angles accept mixed units.

Peer vup4gnen hit a silent-error bug on the Pi case: fed radians into
`startAngle`/`endAngle` thinking they were degrees, the extrude silently
ERROR'd. After [sketch-arc-units], bare numbers are DEGREES and strings
with explicit `deg`/`rad` suffixes route through `parse_angle`.

This test proves, through the live API, that a 0..90 deg arc built from
a mix of int and "90 deg" strings produces a valid sketch feature
(featureStatus OK).

Auto-skipped without credentials.
"""

from __future__ import annotations

import os

import httpx
import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.partstudio import PartStudioManager
from onshape_mcp.api.feature_apply import apply_feature_and_check
from onshape_mcp.builders.sketch import SketchBuilder, SketchPlane

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (
            (os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY"))
            and (os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET"))
        ),
        reason="Requires ONSHAPE_ACCESS_KEY/ONSHAPE_SECRET_KEY (or ONSHAPE_API_KEY/SECRET) in env",
    ),
]


@pytest.fixture
async def client():
    ak = os.environ.get("ONSHAPE_ACCESS_KEY") or os.environ["ONSHAPE_API_KEY"]
    sk = os.environ.get("ONSHAPE_SECRET_KEY") or os.environ["ONSHAPE_API_SECRET"]
    async with OnshapeClient(OnshapeCredentials(access_key=ak, secret_key=sk)) as c:
        yield c


@pytest.mark.asyncio
async def test_arc_deg_string_and_bare_int_both_land_sketch_ok(client):
    dm = DocumentManager(client)
    ps = PartStudioManager(client)
    doc = await dm.create_document(name="mcp-arc-units-real (auto)")
    try:
        summary = await dm.get_document_summary(doc.id)
        ws = summary["workspaces"][0]
        elem = (await ps.create_part_studio(doc.id, ws.id, "arc_units"))["id"]
        top = await ps.get_plane_id(doc.id, ws.id, elem, "Top")

        # Mix a bare int (interpreted as degrees) with an explicit string
        # form to prove both routes go through parse_angle.
        sk = SketchBuilder(plane=SketchPlane.TOP, plane_id=top)
        sk.add_arc(center=(0, 0), radius=10, start_angle=0, end_angle="90 deg")
        result = await apply_feature_and_check(client, doc.id, ws.id, elem, sk.build())
        assert result.ok, f"arc sketch should succeed: {result.error_message!r}"

        # Prove rad strings work too (independent feature on same studio).
        sk2 = SketchBuilder(plane=SketchPlane.TOP, plane_id=top)
        sk2.add_arc(
            center=(30, 0), radius=5, start_angle="0 rad", end_angle="1.5 rad"
        )
        result2 = await apply_feature_and_check(client, doc.id, ws.id, elem, sk2.build())
        assert result2.ok, f"rad-string arc should succeed: {result2.error_message!r}"

    finally:
        try:
            await dm.delete_document(doc.id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                raise
