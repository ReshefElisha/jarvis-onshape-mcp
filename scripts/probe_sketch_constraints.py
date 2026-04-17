"""Live-test the constraint-first sketch primitive against Onshape.

Builds the outer-profile skeleton of Shef's clevis — two circles + two
tangent lines — with only a seed position and then 9 constraints
(HORIZONTAL, DIAMETER x2, DISTANCE, COINCIDENT x4, TANGENT x2).

If Onshape's solver accepts + regens, the wire format is right and we
can extrude from the resulting region.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.partstudio import PartStudioManager
from onshape_mcp.api.feature_apply import apply_feature_and_check
from onshape_mcp.builders.sketch import SketchBuilder, SketchPlane


async def main() -> None:
    ak = os.getenv("ONSHAPE_API_KEY") or os.getenv("ONSHAPE_ACCESS_KEY", "")
    sk = os.getenv("ONSHAPE_API_SECRET") or os.getenv("ONSHAPE_SECRET_KEY", "")
    client = OnshapeClient(OnshapeCredentials(access_key=ak, secret_key=sk))
    docs = DocumentManager(client)
    ps = PartStudioManager(client)

    doc = await docs.create_document(name="probe-sketch-constraints")
    did = doc.id
    print(f"[doc] {did}")
    try:
        summary = await docs.get_document_summary(did)
        wid = summary["workspaces"][0].id
        studios = await docs.find_part_studios(did, wid)
        eid = studios[0].id
        top_plane_id = await ps.get_plane_id(did, wid, eid, "Top")

        sb = SketchBuilder(name="Outer", plane=SketchPlane.TOP, plane_id=top_plane_id)
        # Seed entities with rough positions; solver will pull them to the
        # right spots once constraints are applied.
        sb.add_entity_spec({"type": "circle", "id": "hub", "center": [0, 0], "radius": 0.025})
        sb.add_entity_spec({"type": "circle", "id": "tip", "center": [0.09, 0], "radius": 0.012})
        sb.add_entity_spec({"type": "line",   "id": "upper", "start": [0, 0.025], "end": [0.09, 0.012]})
        sb.add_entity_spec({"type": "line",   "id": "lower", "start": [0, -0.025], "end": [0.09, -0.012]})

        # Skip HORIZONTAL on centers — without the externalSecond axis ref
        # that the UI emits, Onshape can't resolve "horizontal to what."
        # DISTANCE(direction=HORIZONTAL) between the centers pins them to a
        # shared horizontal line, which covers the same intent.
        sb.add_constraint_spec({"type": "DIAMETER", "entity": "hub", "value": "50 mm"})
        sb.add_constraint_spec({"type": "DIAMETER", "entity": "tip", "value": "24 mm"})
        sb.add_constraint_spec({"type": "DISTANCE", "entities": ["hub.center", "tip.center"],
                                "value": "100 mm", "direction": "HORIZONTAL"})
        sb.add_constraint_spec({"type": "COINCIDENT", "entities": ["upper.start", "hub"]})
        sb.add_constraint_spec({"type": "COINCIDENT", "entities": ["upper.end", "tip"]})
        sb.add_constraint_spec({"type": "COINCIDENT", "entities": ["lower.start", "hub"]})
        sb.add_constraint_spec({"type": "COINCIDENT", "entities": ["lower.end", "tip"]})
        sb.add_constraint_spec({"type": "TANGENT", "entities": ["upper", "hub"]})
        sb.add_constraint_spec({"type": "TANGENT", "entities": ["upper", "tip"]})
        sb.add_constraint_spec({"type": "TANGENT", "entities": ["lower", "hub"]})
        sb.add_constraint_spec({"type": "TANGENT", "entities": ["lower", "tip"]})

        feat = sb.build()
        print(f"[payload] {len(feat['feature']['entities'])} entities, "
              f"{len(feat['feature']['constraints'])} constraints")

        r = await apply_feature_and_check(client, did, wid, eid, feat)
        print(f"[sketch] status={r.status} id={r.feature_id}")
        if not r.ok:
            print(f"  error: {r.error_message}")
            # Dump the feature state for debug.
            feats = await client.get(
                f"/api/v9/partstudios/d/{did}/w/{wid}/e/{eid}/features"
            )
            fs = (feats.get("featureStates") or {}).get(r.feature_id or "")
            print(f"  featureState: {json.dumps(fs, indent=2, default=str)[:1000]}")
            return
        print("[sketch] SOLVER ACCEPTED ✓")

        # Now extrude the resulting region to prove the region detection works.
        from onshape_mcp.builders.extrude import ExtrudeBuilder, ExtrudeType
        ex = ExtrudeBuilder(
            name="TopProfile",
            sketch_feature_id=r.feature_id,
            depth=0.010,
            operation_type=ExtrudeType.NEW,
        )
        er = await apply_feature_and_check(client, did, wid, eid, ex.build())
        print(f"[extrude] status={er.status} err={er.error_message}")
    finally:
        try:
            await docs.delete_document(did)
        except Exception as e:  # noqa: BLE001
            print(f"[cleanup] delete failed (non-blocking): {e}")
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
