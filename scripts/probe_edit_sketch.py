"""Live-test edit_sketch: atomic create + iteration pass.

Pass 1: create_sketch with 2 circles + 2 tangent lines, fully constrained.
Pass 2: edit_sketch adds an INNER bore circle concentric to the hub +
  DIAMETER constraint on it, as a second pass.
Pass 3: edit_sketch removes the inner bore, checks cascade tells us the
  DIAMETER got auto-dropped.
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
from onshape_mcp.api.sketch_edit import edit_sketch
from onshape_mcp.builders.sketch import SketchBuilder, SketchPlane


async def main() -> None:
    ak = os.getenv("ONSHAPE_API_KEY") or os.getenv("ONSHAPE_ACCESS_KEY", "")
    sk = os.getenv("ONSHAPE_API_SECRET") or os.getenv("ONSHAPE_SECRET_KEY", "")
    client = OnshapeClient(OnshapeCredentials(access_key=ak, secret_key=sk))
    docs = DocumentManager(client)
    ps = PartStudioManager(client)

    doc = await docs.create_document(name="probe-edit-sketch")
    did = doc.id
    print(f"[doc] {did}")
    try:
        summary = await docs.get_document_summary(did)
        wid = summary["workspaces"][0].id
        studios = await docs.find_part_studios(did, wid)
        eid = studios[0].id
        top_plane_id = await ps.get_plane_id(did, wid, eid, "Top")

        # --- Pass 1: atomic create ---
        sb = SketchBuilder(name="Profile", plane=SketchPlane.TOP, plane_id=top_plane_id)
        for spec in [
            {"type": "circle", "id": "hub", "center": [0, 0], "radius": 0.025},
            {"type": "circle", "id": "tip", "center": [0.09, 0], "radius": 0.012},
            {"type": "line", "id": "upper", "start": [0, 0.025], "end": [0.09, 0.012]},
            {"type": "line", "id": "lower", "start": [0, -0.025], "end": [0.09, -0.012]},
        ]:
            sb.add_entity_spec(spec)
        for cspec in [
            {"type": "DIAMETER", "entity": "hub", "value": "50 mm", "id": "d_hub"},
            {"type": "DIAMETER", "entity": "tip", "value": "24 mm", "id": "d_tip"},
            {"type": "DISTANCE", "entities": ["hub.center", "tip.center"],
             "value": "100 mm", "direction": "HORIZONTAL", "id": "d_ctr"},
            {"type": "COINCIDENT", "entities": ["upper.start", "hub"]},
            {"type": "COINCIDENT", "entities": ["upper.end", "tip"]},
            {"type": "COINCIDENT", "entities": ["lower.start", "hub"]},
            {"type": "COINCIDENT", "entities": ["lower.end", "tip"]},
            {"type": "TANGENT", "entities": ["upper", "hub"]},
            {"type": "TANGENT", "entities": ["upper", "tip"]},
            {"type": "TANGENT", "entities": ["lower", "hub"]},
            {"type": "TANGENT", "entities": ["lower", "tip"]},
        ]:
            sb.add_constraint_spec(cspec)
        r = await apply_feature_and_check(client, did, wid, eid, sb.build())
        assert r.ok, f"Pass 1 failed: {r.error_message}"
        print(f"[pass 1] create_sketch status={r.status} id={r.feature_id}")

        sketch_id = r.feature_id

        # --- Pass 2: add an inner bore + DIAMETER via edit_sketch ---
        er = await edit_sketch(
            client, did, wid, eid, sketch_id,
            add_entities=[
                {"type": "circle", "id": "bore", "center": [0, 0], "radius": 0.018},
            ],
            add_constraints=[
                {"id": "d_bore", "type": "DIAMETER", "entity": "bore", "value": "36 mm"},
                {"id": "c_bore", "type": "CONCENTRIC", "entities": ["bore", "hub"]},
            ],
        )
        if not er.apply.ok:
            print(f"[pass 2] FAILED: {er.apply.error_message}")
            return
        print(f"[pass 2] edit_sketch added bore: status={er.apply.status}")
        print(f"        added_entity_ids={er.added_entity_ids}")
        print(f"        added_constraint_ids={er.added_constraint_ids}")

        # --- Pass 3: remove the bore entity, cascade should drop its constraints ---
        er2 = await edit_sketch(
            client, did, wid, eid, sketch_id,
            remove_ids=["bore"],
        )
        if not er2.apply.ok:
            print(f"[pass 3] FAILED: {er2.apply.error_message}")
            return
        print(f"[pass 3] edit_sketch removed bore: status={er2.apply.status}")
        print(f"        removed_entity_ids={er2.removed_entity_ids}")
        print(f"        cascaded_removals={[(c.constraint_id, c.referenced) for c in er2.cascaded_removals]}")

        # Expect: removed bore + 2 cascaded constraints (d_bore, c_bore)
        assert len(er2.cascaded_removals) >= 2, \
            f"expected >=2 cascaded (d_bore + c_bore); got {er2.cascaded_removals}"
        cascaded_ids = {c.constraint_id for c in er2.cascaded_removals}
        assert "d_bore" in cascaded_ids, f"expected d_bore in cascade; got {cascaded_ids}"
        assert "c_bore" in cascaded_ids, f"expected c_bore in cascade; got {cascaded_ids}"
        print("\n✓ CREATE + EDIT + CASCADE-REMOVE all pass")
    finally:
        try:
            await docs.delete_document(did)
        except Exception as e:  # noqa: BLE001
            print(f"[cleanup] delete failed (non-blocking): {e}")
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
