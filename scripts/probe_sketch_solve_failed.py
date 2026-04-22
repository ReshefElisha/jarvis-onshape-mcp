"""Probe Onshape's response body on SKETCH_SOLVE_FAILED.

Peer ot0309vt burned 6 turns bisecting an over-constrained pocket.
Find out whether Onshape actually surfaces per-constraint diagnostics
anywhere in the response — featureState, entity geometry coords, or
a buried notices array — so we can stop leaving Claude in silence.

Builds two sketches per run:
  A. Deliberately over-constrained: 2 lines with tangent + parallel +
     perpendicular simultaneously. Solver can't satisfy all three.
  B. Successfully-solved reference to diff against.

Dumps every field of the /features GET response for the broken sketch:
- featureStates map
- feature.entities (look for unresolved coords / NaN)
- any notices at feature or top level
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

    doc = await docs.create_document(name="probe-solve-failed")
    did = doc.id
    print(f"[doc] {did}")
    try:
        summary = await docs.get_document_summary(did)
        wid = summary["workspaces"][0].id
        studios = await docs.find_part_studios(did, wid)
        eid = studios[0].id
        top = await ps.get_plane_id(did, wid, eid, "Top")

        # Over-constrained: line1 PARALLEL line2 AND line1 PERPENDICULAR
        # line2. Solver can't satisfy both.
        sb = SketchBuilder(plane=SketchPlane.TOP, plane_id=top, name="Broken")
        sb.add_entity_spec({"type": "line", "id": "line1",
                            "start": [0, 0], "end": [0.030, 0]})
        sb.add_entity_spec({"type": "line", "id": "line2",
                            "start": [0, 0.010], "end": [0.030, 0.010]})
        sb.add_constraint_spec({"type": "PARALLEL", "id": "c_par",
                                "entities": ["line1", "line2"]})
        sb.add_constraint_spec({"type": "PERPENDICULAR", "id": "c_perp",
                                "entities": ["line1", "line2"]})
        sb.add_constraint_spec({"type": "COINCIDENT", "id": "c_coin",
                                "entities": ["line1.end", "line2.start"]})
        r = await apply_feature_and_check(client, did, wid, eid, sb.build())
        print(f"\n[over-constrained] status={r.status}")
        print(f"  error_message={r.error_message}")

        base = f"/api/v9/partstudios/d/{did}/w/{wid}/e/{eid}/features"

        # 1) Full /features payload — look for notices anywhere.
        feats = await client.get(base)
        fs_map = feats.get("featureStates") or {}
        print(f"\n=== featureStates keys ===")
        for fid, state in fs_map.items():
            if fid == r.feature_id:
                print(json.dumps(state, indent=2, default=str)[:4000])

        print(f"\n=== /features top-level keys ===")
        print(list(feats.keys()))
        for k in feats:
            if k.lower().endswith("notices"):
                print(f"  {k}: {json.dumps(feats[k], indent=2, default=str)[:500]}")

        # 2) Single-feature fetch — sometimes carries more detail.
        try:
            single = await client.get(f"{base}/featureid/{r.feature_id}")
            print(f"\n=== single-feature response keys ===")
            print(list(single.keys()))
            feat = single.get("feature") or {}
            print(f"  feature.entities count: {len(feat.get('entities') or [])}")
            # Look for NaN / None / unresolved coords in entity geometries.
            unresolved = []
            for e in feat.get("entities") or []:
                geo = e.get("geometry") or {}
                bad = [k for k, v in geo.items()
                       if isinstance(v, (int, float)) and (v != v or abs(v) > 1e30)]
                if bad:
                    unresolved.append({"entityId": e.get("entityId"), "bad_fields": bad})
            print(f"  entities with unresolved coords: {unresolved}")
            # Look for notices on the feature itself.
            for k in feat:
                if "notice" in k.lower() or "warning" in k.lower():
                    print(f"  feature.{k}: {feat[k]}")
        except Exception as e:  # noqa: BLE001
            print(f"[single-feature fetch failed] {e}")

        # 3) Try feature-specific featureState endpoint variants.
        for variant in [
            f"{base}/featurestate",
            f"{base}/featurestates",
            f"{base}/{r.feature_id}/featurestate",
        ]:
            try:
                fs = await client.get(variant)
                print(f"\n=== {variant} OK ===")
                print(json.dumps(fs, indent=2, default=str)[:1500])
            except Exception as e:  # noqa: BLE001
                err = str(e)[:100]
                print(f"[{variant}] err: {err}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
