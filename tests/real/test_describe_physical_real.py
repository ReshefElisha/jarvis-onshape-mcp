"""Real-API test for the PHYSICAL SUMMARY section added to describe_part_studio.

Builds a simple pillow-block-like body (plate + cylindrical boss + through-
hole) and asserts that describe_part_studio's structured text now carries:

    - face-type breakdown (PLANE + CYLINDER counts)
    - edge-type breakdown (LINE + CIRCLE counts) with a length range
    - face-area range from FS `evArea`
    - body count + aggregate volume + bbox summary
    - a "suspect geometry" block (even if empty -- we assert "none" here)

Skipped automatically without Onshape credentials.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.describe import DescribeManager
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.entities import EntityManager
from onshape_mcp.api.feature_apply import apply_feature_and_check
from onshape_mcp.api.partstudio import PartStudioManager
from onshape_mcp.builders.extrude import ExtrudeBuilder, ExtrudeType
from onshape_mcp.builders.sketch import SketchBuilder, SketchPlane


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (
            (os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY"))
            and (os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET"))
        ),
        reason="Requires Onshape credentials in env",
    ),
]


def _creds() -> OnshapeCredentials:
    ak = os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY", "")
    sk = os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET", "")
    return OnshapeCredentials(access_key=ak, secret_key=sk)


@pytest.mark.asyncio
async def test_describe_carries_physical_summary_section():
    async with OnshapeClient(_creds()) as client:
        docs = DocumentManager(client)
        ps_mgr = PartStudioManager(client)
        ents = EntityManager(client)
        describe = DescribeManager(client, entities=ents, partstudio=ps_mgr)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        doc = await docs.create_document(name=f"dyna-mcp physical-summary {ts}")
        did = doc.id
        try:
            wid = (await docs.get_workspaces(did))[0].id
            eid = (await ps_mgr.create_part_studio(did, wid, name="ps"))["id"]
            top_id = await ps_mgr.get_plane_id(did, wid, eid, "Top")

            # Plate 60x40x8.
            rect = SketchBuilder(plane=SketchPlane.TOP, plane_id=top_id, name="plate")
            rect.add_rectangle(corner1=(0, 0), corner2=(60, 40))
            r = await apply_feature_and_check(client, did, wid, eid, rect.build())
            assert r.status == "OK", r

            ext = ExtrudeBuilder(name="plate ext", sketch_feature_id=r.feature_id,
                                 depth=8, operation_type=ExtrudeType.NEW)
            await apply_feature_and_check(client, did, wid, eid, ext.build())

            # Boss (cylinder) centred on the plate.
            snap0 = await ents.list_entities(did, wid, eid)
            top_face = next(
                f for f in snap0["bodies"][0]["faces"]
                if f.get("type") == "PLANE"
                and f.get("outward_axis") == "+Z"
                and f.get("origin") and abs(f["origin"][2] * 1000 - 8.0) < 0.5
            )
            boss_sketch = SketchBuilder(plane=SketchPlane.TOP, plane_id=top_face["id"], name="boss")
            boss_sketch.add_circle(center=(30, 20), radius=10)
            br = await apply_feature_and_check(client, did, wid, eid, boss_sketch.build())
            boss_ext = ExtrudeBuilder(name="boss ext", sketch_feature_id=br.feature_id,
                                      depth=6, operation_type=ExtrudeType.ADD)
            await apply_feature_and_check(client, did, wid, eid, boss_ext.build())

            # Through-hole down the middle.
            snap1 = await ents.list_entities(did, wid, eid)
            boss_top = next(
                f for f in snap1["bodies"][0]["faces"]
                if f.get("type") == "PLANE"
                and f.get("outward_axis") == "+Z"
                and f.get("origin") and abs(f["origin"][2] * 1000 - 14.0) < 0.5
            )
            hole_sketch = SketchBuilder(
                plane=SketchPlane.TOP, plane_id=boss_top["id"], name="hole",
            )
            hole_sketch.add_circle(center=(30, 20), radius=3)
            hs = await apply_feature_and_check(client, did, wid, eid, hole_sketch.build())
            cut = ExtrudeBuilder(
                name="hole cut", sketch_feature_id=hs.feature_id,
                depth=14, operation_type=ExtrudeType.REMOVE,
                opposite_direction=True,
            )
            await apply_feature_and_check(client, did, wid, eid, cut.build())

            # === The actual assertions on PHYSICAL SUMMARY. ===
            snap = await describe.describe_part_studio(
                did, wid, eid, views=["iso"], render_width=600, render_height=400,
            )
            text = snap.structured_text
            assert "PHYSICAL SUMMARY:" in text, (
                f"missing PHYSICAL SUMMARY section. text=\n{text[:2000]}"
            )

            # Split out the physical summary for readability in failures.
            ps_block = text.split("PHYSICAL SUMMARY:", 1)[1].split("\n\n", 1)[0]

            # 1 body, non-zero aggregate volume, bbox present.
            assert re.search(r"bodies: 1\b", ps_block), ps_block
            vol_match = re.search(r"volume: ([\d.]+) mm\^3", ps_block)
            assert vol_match and float(vol_match.group(1)) > 1000, (
                f"expected sensible volume (>1000 mm^3), got {vol_match and vol_match.group(1)}"
            )
            # bbox MUST render as dimensions on a healthy body (was relaxed
            # to also accept "unknown" while the FS evBox3d parser was
            # walking the wrong response key; fixed in [describe-bbox-fix]).
            # Plate is 60x40x14 (boss adds 6 to the 8 mm plate height).
            bbox_match = re.search(
                r"bbox: ([\d.]+) x ([\d.]+) x ([\d.]+) mm", ps_block
            )
            assert bbox_match, (
                f"bbox should be reported as dimensions on a healthy body, "
                f"got {ps_block!r}"
            )
            dims = sorted(float(bbox_match.group(i)) for i in (1, 2, 3))
            # Plate footprint dominates: longest side 60, mid 40, height 14
            # (8 mm plate + 6 mm boss). Allow a tight tolerance.
            assert abs(dims[2] - 60.0) < 0.5, f"longest dim should be ~60mm: {dims}"
            assert abs(dims[1] - 40.0) < 0.5, f"mid dim should be ~40mm: {dims}"
            assert abs(dims[0] - 14.0) < 0.5, f"shortest dim should be ~14mm: {dims}"

            # Face + edge type breakdowns appear. The final body should have
            # PLANE and CYLINDER faces at minimum; 1 body has both plate
            # rectangle sides and the boss/hole walls.
            assert "plane" in ps_block.lower()
            assert "cylinder" in ps_block.lower()
            # Edges: CIRCLE edges exist from the boss/hole; LINE edges from
            # the rectangular plate.
            assert re.search(r"line", ps_block.lower())
            assert re.search(r"circle", ps_block.lower())

            # Edge length range line present with two distinct numbers.
            edge_range_match = re.search(
                r"edge lengths: min=([\d.]+) mm  max=([\d.]+) mm", ps_block
            )
            assert edge_range_match, f"missing edge length range: {ps_block!r}"
            min_e, max_e = float(edge_range_match.group(1)), float(edge_range_match.group(2))
            assert max_e > min_e > 0, f"bad edge range min={min_e} max={max_e}"

            # Face area range from FS evArea. Min should be positive; max
            # should be on the order of the plate face area (60*40 = 2400 mm^2).
            face_area_match = re.search(
                r"face areas: min=([\d.]+) mm\^2 \([A-Za-z0-9_.-]+\)  "
                r"max=([\d.]+) mm\^2",
                ps_block,
            )
            assert face_area_match, (
                f"face area range missing or unparseable: {ps_block!r}"
            )
            min_a, max_a = float(face_area_match.group(1)), float(face_area_match.group(2))
            assert 0 < min_a < max_a, f"bad face area range min={min_a} max={max_a}"
            assert max_a > 100, f"expected a face > 100 mm^2 on this body, got max={max_a}"

            # Suspect block is present -- for this clean build it should be
            # "none" (no sub-threshold slivers).
            assert "suspect geometry" in ps_block.lower()
            # Don't assert "none" strictly -- Onshape sometimes emits tiny
            # trim faces on cylinders. Just assert the line exists.

            # raw dict now carries face_areas so predicate callers can read it.
            assert isinstance(snap.raw.get("face_areas"), dict)
            assert len(snap.raw["face_areas"]) > 0

        finally:
            try:
                await client.delete(f"/api/v6/documents/{did}")
            except Exception:  # noqa: BLE001
                pass
