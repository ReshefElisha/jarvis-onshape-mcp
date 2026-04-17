"""Real-API proof that SYMMETRIC extrude straddles the sketch plane.

Dogfooder's bug #5: without an endType, every "symmetric" feature had to
be built as TWO mirrored BLIND extrudes. This test builds a 40x40 mm
square on the Top plane (Z=0) and extrudes 20 mm SYMMETRIC, then asserts
the resulting bbox Z spans [-10, +10] mm — exactly depth/2 each side.

A BLIND extrude of depth 20 would give Z in [0, +20] instead.

Auto-skipped without credentials.
"""

from __future__ import annotations

import os

import httpx
import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.featurescript import FeatureScriptManager
from onshape_mcp.api.partstudio import PartStudioManager
from onshape_mcp.api.feature_apply import apply_feature_and_check
from onshape_mcp.builders.sketch import SketchBuilder, SketchPlane
from onshape_mcp.builders.extrude import ExtrudeBuilder, ExtrudeEndType, ExtrudeType

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
    access_key = os.environ.get("ONSHAPE_ACCESS_KEY") or os.environ["ONSHAPE_API_KEY"]
    secret_key = os.environ.get("ONSHAPE_SECRET_KEY") or os.environ["ONSHAPE_API_SECRET"]
    creds = OnshapeCredentials(access_key=access_key, secret_key=secret_key)
    async with OnshapeClient(creds) as c:
        yield c


async def _disposable_doc(client: OnshapeClient) -> tuple[str, str, str]:
    docs = DocumentManager(client)
    doc = await docs.create_document(name="mcp-extrude-sym-real (auto)")
    summary = await docs.get_document_summary(doc.id)
    ws = summary["workspaces"][0]
    elements = summary["workspace_details"][0]["elements"]
    ps = [e for e in elements if e.element_type.replace(" ", "").upper() == "PARTSTUDIO"]
    if not ps:
        created = await PartStudioManager(client).create_part_studio(
            doc.id, ws.id, name="Part Studio 1"
        )
        return doc.id, ws.id, created["id"]
    return doc.id, ws.id, ps[0].id


@pytest.mark.asyncio
async def test_symmetric_extrude_straddles_sketch_plane(client):
    doc_id, ws_id, elem_id = await _disposable_doc(client)
    ps = PartStudioManager(client)
    fs = FeatureScriptManager(client)

    try:
        top = await ps.get_plane_id(doc_id, ws_id, elem_id, "Top")
        sketch = SketchBuilder(name="Square", plane=SketchPlane.TOP, plane_id=top)
        sketch.add_rectangle(corner1=(-20, -20), corner2=(20, 20))  # 40 mm square
        sr = await apply_feature_and_check(client, doc_id, ws_id, elem_id, sketch.build())
        assert sr.ok, f"sketch failed: {sr.error_message}"

        extrude = ExtrudeBuilder(
            name="SymBody",
            sketch_feature_id=sr.feature_id,
            operation_type=ExtrudeType.NEW,
            end_type=ExtrudeEndType.SYMMETRIC,
        )
        extrude.set_depth(20)  # 20 mm TOTAL -> 10 each side of plane
        er = await apply_feature_and_check(client, doc_id, ws_id, elem_id, extrude.build())
        assert er.ok, f"symmetric extrude failed: {er.error_message}"

        bbox_script = """
function(context is Context, queries) {
    var bbox = evBox3d(context, {"topology": qAllModifiableSolidBodies()});
    var minC = bbox.minCorner;
    var maxC = bbox.maxCorner;
    return [
        minC[0] / millimeter, minC[1] / millimeter, minC[2] / millimeter,
        maxC[0] / millimeter, maxC[1] / millimeter, maxC[2] / millimeter
    ];
}""".strip()
        raw = await fs.evaluate(doc_id, ws_id, elem_id, bbox_script)
        entries = (raw.get("result") or {}).get("value") or []
        nums = [float(e.get("value", 0.0)) for e in entries if isinstance(e, dict)]
        assert len(nums) == 6, f"expected 6 bbox numbers, got {nums!r}"
        min_x, min_y, min_z, max_x, max_y, max_z = nums

        tol = 0.01  # 0.01 mm
        # Z span is 20 mm total, symmetric about Z=0.
        assert abs(min_z - (-10.0)) < tol, (
            f"SYMMETRIC extrude did not land below sketch plane: "
            f"min_z={min_z:.3f} mm (expected -10). If this is ~0 the "
            f"endBound enum isn't reaching Onshape (BLIND fallback) or "
            f"the Top plane's +Z direction flipped."
        )
        assert abs(max_z - 10.0) < tol, (
            f"SYMMETRIC extrude did not land above sketch plane: "
            f"max_z={max_z:.3f} mm (expected +10)."
        )
        assert abs((max_z - min_z) - 20.0) < tol, (
            f"Z extent is {max_z - min_z:.3f} mm, expected 20.0 mm"
        )
        # X/Y should just be the sketch footprint (40 mm square).
        assert abs((max_x - min_x) - 40.0) < tol
        assert abs((max_y - min_y) - 40.0) < tol
    finally:
        try:
            await DocumentManager(client).delete_document(doc_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                raise
