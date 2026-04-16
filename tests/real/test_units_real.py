"""Real-API proof for the mm-default unit convention.

Builds a 60 x 40 x 6 mm plate with a 20 mm dia boss stacked on top (boss
height 6 mm for a nice round 12 mm total on the Z axis) using BARE NUMBERS
only — no "mm" / "in" strings anywhere. Then asserts the resulting bounding
box matches millimeters, not inches. If the unit convention regressed back to
"inches" the box would come out 25.4x bigger and the test would fail loudly.

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
from onshape_mcp.builders.extrude import ExtrudeBuilder, ExtrudeType

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
    doc = await docs.create_document(name="mcp-units-real (auto)")
    summary = await docs.get_document_summary(doc.id)
    workspace = summary["workspaces"][0]
    elements = summary["workspace_details"][0]["elements"]
    part_studios = [e for e in elements if e.element_type.replace(" ", "").upper() == "PARTSTUDIO"]
    if not part_studios:
        created = await PartStudioManager(client).create_part_studio(
            doc.id, workspace.id, name="Part Studio 1"
        )
        return doc.id, workspace.id, created["id"]
    return doc.id, workspace.id, part_studios[0].id


@pytest.mark.asyncio
async def test_mm_default_plate_and_boss_bbox(client):
    """60×40×6 mm plate + 20 mm diameter × 6 mm boss, all bare numbers."""
    doc_id, ws_id, elem_id = await _disposable_doc(client)
    ps = PartStudioManager(client)
    fs = FeatureScriptManager(client)

    try:
        # --- plate sketch: 60x40 mm rectangle on Top plane ------------------
        top_plane = await ps.get_plane_id(doc_id, ws_id, elem_id, "Top")
        plate_sketch = SketchBuilder(name="PlateSketch", plane=SketchPlane.TOP, plane_id=top_plane)
        plate_sketch.add_rectangle(corner1=(0, 0), corner2=(60, 40))  # bare numbers -> mm
        sr = await apply_feature_and_check(client, doc_id, ws_id, elem_id, plate_sketch.build())
        assert sr.ok, f"plate sketch failed: {sr.error_message}"

        # --- plate extrude: 6 mm ------------------------------------------
        plate = ExtrudeBuilder(
            name="Plate",
            sketch_feature_id=sr.feature_id,
            operation_type=ExtrudeType.NEW,
        )
        plate.set_depth(6)  # bare -> 6 mm
        pr = await apply_feature_and_check(client, doc_id, ws_id, elem_id, plate.build())
        assert pr.ok, f"plate extrude failed: {pr.error_message}"

        # --- boss sketch: 20 mm circle on top face -------------------------
        # Top plane + 6 mm extrude -> top face is at Z=6 mm. We put the boss
        # circle on the Top datum for simplicity (circles extrude upward by
        # default); boss center is (30, 20) — the plate midpoint in sketch
        # coords — and radius 10 mm.
        boss_sketch = SketchBuilder(name="BossSketch", plane=SketchPlane.TOP, plane_id=top_plane)
        boss_sketch.add_circle(center=(30, 20), radius=10)  # all mm
        bs = await apply_feature_and_check(client, doc_id, ws_id, elem_id, boss_sketch.build())
        assert bs.ok, f"boss sketch failed: {bs.error_message}"

        # --- boss extrude: 12 mm ADD (6 mm plate + 6 mm boss = 12 mm total) -
        boss = ExtrudeBuilder(
            name="Boss",
            sketch_feature_id=bs.feature_id,
            operation_type=ExtrudeType.ADD,
        )
        boss.set_depth(12)  # 12 mm
        br = await apply_feature_and_check(client, doc_id, ws_id, elem_id, boss.build())
        assert br.ok, f"boss extrude failed: {br.error_message}"

        # --- bbox check ---------------------------------------------------
        # `get_bounding_box` returns a BTFSValueMap (with Box3d unit-tagged
        # entries) that's awkward to traverse. A one-off FS lambda that
        # returns bare numeric mm is much easier to assert on.
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
        # Response shape: {"result": {"btType": "...BTFSValueArray", "value":
        # [{"value": <float_mm>, ...}, ...]}}
        result = raw.get("result") or {}
        entries = result.get("value") or []
        nums = [float(e.get("value", 0.0)) for e in entries if isinstance(e, dict)]
        assert len(nums) == 6, f"expected 6 bbox numbers, got {nums!r}"
        min_x, min_y, min_z, max_x, max_y, max_z = nums

        tol = 0.01  # 0.01 mm tolerance
        assert abs((max_x - min_x) - 60.0) < tol, (
            f"X extent wrong: {max_x - min_x!r} mm, expected 60.0 mm. "
            f"If bare numbers reverted to inches, this would be ~1524 mm "
            f"(60 in = 1524 mm); got {max_x - min_x:.3f} mm."
        )
        assert abs((max_y - min_y) - 40.0) < tol, (
            f"Y extent wrong: {max_y - min_y!r} mm, expected 40.0 mm"
        )
        assert abs((max_z - min_z) - 12.0) < tol, (
            f"Z extent wrong: {max_z - min_z!r} mm, expected 12.0 mm"
        )
    finally:
        try:
            await DocumentManager(client).delete_document(doc_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                raise
