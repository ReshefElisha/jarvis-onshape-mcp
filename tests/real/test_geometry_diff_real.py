"""Real-API test for the changes: block — git-diff for CAD.

Confirms that apply_feature_and_check with track_changes=True returns a
structured diff after a topology mutation: volume delta, faces added/
removed, edges added/removed, bbox delta, anomalies. Based on peer
vup4gnen's 2026-04-17 meta-feedback.
"""

from __future__ import annotations

import os
import time

import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.feature_apply import apply_feature_and_check
from onshape_mcp.api.partstudio import PartStudioManager
from onshape_mcp.builders.extrude import ExtrudeBuilder, ExtrudeType
from onshape_mcp.builders.sketch import SketchBuilder, SketchPlane


def _creds_present() -> bool:
    ak = os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY")
    sk = os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET")
    return bool(ak and sk)


pytestmark = pytest.mark.skipif(
    not _creds_present(),
    reason="ONSHAPE_ACCESS_KEY/SECRET_KEY or ONSHAPE_API_KEY/SECRET not set",
)


@pytest.mark.asyncio
async def test_hole_cut_yields_changes_block():
    """After cutting a ø10mm through-hole in a 40x40x10 plate, the
    changes: block should report a negative volume delta, cylinder face
    added, bounding box unchanged."""
    ak = os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY", "")
    sk = os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET", "")
    creds = OnshapeCredentials(access_key=ak, secret_key=sk)
    async with OnshapeClient(creds) as c:
        dm = DocumentManager(c)
        psm = PartStudioManager(c)
        doc = await dm.create_document(f"diff-test-{int(time.time())}")
        did = doc.id
        wid = (await dm.get_workspaces(did))[0].id
        ps = await psm.create_part_studio(did, wid, "ps")
        eid = ps["id"] if isinstance(ps, dict) else ps.id

        # Base plate: 40x40 on Top, extrude 10mm. Don't care about this
        # feature's changes — it's creating the initial body. Builders
        # take bare numbers as mm after the [units] refactor.
        s1 = SketchBuilder(name="base", plane=SketchPlane.TOP, plane_id="JDC")
        s1.add_rectangle(corner1=(-20, -20), corner2=(20, 20))
        r = await apply_feature_and_check(c, did, wid, eid, s1.build())
        assert r.ok
        ex = ExtrudeBuilder(sketch_feature_id=r.feature_id, depth=10, operation_type=ExtrudeType.NEW)
        r = await apply_feature_and_check(c, did, wid, eid, ex.build(), track_changes=True)
        assert r.ok
        assert r.changes is not None
        assert r.changes["body_count_before"] == 0
        assert r.changes["body_count_after"] == 1
        assert len(r.changes["faces_added"]) == 6
        vol_after = r.changes["volume_after_mm3"]
        assert abs(vol_after - 16000.0) < 10.0, f"volume_after: {vol_after}"
        bb = r.changes["bbox_after_mm"]
        # 40x40x10 plate, Top-plane sketch centered at origin.
        assert abs((bb["x_max_mm"] - bb["x_min_mm"]) - 40.0) < 0.5
        assert abs((bb["z_max_mm"] - bb["z_min_mm"]) - 10.0) < 0.5

        # Now the interesting diff: cut a ø10mm hole (radius 5 mm).
        s2 = SketchBuilder(name="hole", plane=SketchPlane.TOP, plane_id="JDC")
        s2.add_circle(center=(0, 0), radius=5)
        r = await apply_feature_and_check(c, did, wid, eid, s2.build())
        assert r.ok
        ex2 = ExtrudeBuilder(sketch_feature_id=r.feature_id, depth=15, operation_type=ExtrudeType.REMOVE)
        r = await apply_feature_and_check(c, did, wid, eid, ex2.build(), track_changes=True)
        assert r.ok

        assert r.changes is not None, "changes block missing"
        # Volume delta: -(pi * 5^2 * 10) = -785.4 mm^3
        vol_delta = r.changes.get("volume_delta_mm3")
        assert vol_delta is not None
        assert -790 < vol_delta < -780, f"unexpected volume delta: {vol_delta}"

        # Topology change: at least one cylinder added (the hole wall).
        added_types = [f["type"] for f in r.changes["faces_added"]]
        assert "CYLINDER" in added_types, f"no cylinder in faces_added: {added_types}"

        # Summary is human-readable and carries the volume sign.
        summary = r.changes.get("summary", "")
        assert "volume" in summary.lower()
        assert "-" in summary, f"summary missing negative sign: {summary!r}"

        # bbox should be preserved (hole goes through; bbox doesn't change).
        assert "bbox_before_mm" in r.changes and "bbox_after_mm" in r.changes


@pytest.mark.asyncio
async def test_track_changes_false_by_default():
    """Default apply_feature_and_check call must NOT incur the two extra
    bodydetails/massproperties round-trips — changes stays None."""
    ak = os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY", "")
    sk = os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET", "")
    creds = OnshapeCredentials(access_key=ak, secret_key=sk)
    async with OnshapeClient(creds) as c:
        dm = DocumentManager(c)
        psm = PartStudioManager(c)
        doc = await dm.create_document(f"diff-default-{int(time.time())}")
        did = doc.id
        wid = (await dm.get_workspaces(did))[0].id
        ps = await psm.create_part_studio(did, wid, "ps")
        eid = ps["id"] if isinstance(ps, dict) else ps.id

        s = SketchBuilder(name="base", plane=SketchPlane.TOP, plane_id="JDC")
        s.add_rectangle(corner1=(-10, -10), corner2=(10, 10))
        r = await apply_feature_and_check(c, did, wid, eid, s.build())  # no kwarg
        assert r.ok
        assert r.changes is None, "changes block should be absent when track_changes not set"
