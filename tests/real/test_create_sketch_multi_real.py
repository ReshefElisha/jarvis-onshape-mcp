"""Real-API test for the multi-entity create_sketch tool.

Replays dogfooder z5rz5fhl bug #3: a 60x40x6 mm plate with 4 corner
mounting holes used to need 5 sketch features (1 rect + 4 circles) +
5 extrudes (1 plate + 4 cuts) = 10 features in the tree. With
`create_sketch`, the 4 holes go into ONE sketch driven through the
multi-entity entities array, so the tree shrinks to 4 features:
plate sketch + plate extrude + holes sketch + cut extrude.

Asserts:
    - all features apply with status OK (truth helper still wires through)
    - the body has exactly 1 cylinder face per hole (4 total at radius 1.5 mm)
    - the feature tree contains exactly 2 sketch features and 2 extrudes
      (proves we collapsed the 4 hole circles into 1 sketch)

Skipped automatically without Onshape creds.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.entities import EntityManager
from onshape_mcp.api.partstudio import PartStudioManager


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


@pytest.fixture
async def client():
    async with OnshapeClient(_creds()) as c:
        yield c


def _parse_text(blocks) -> str:
    """Pull the first text block out of a call_tool response."""
    for b in blocks:
        if getattr(b, "type", None) == "text":
            return b.text
    return ""


@pytest.mark.asyncio
async def test_plate_with_four_holes_in_one_sketch(client):
    """Plate (60x40x6 mm) + 4 corner ø3 mm through-holes via ONE sketch
    + ONE REMOVE extrude. Driven through `call_tool` so we exercise the
    actual MCP-facing tool surface, not just the underlying SketchBuilder.
    """
    import json

    from onshape_mcp.server import call_tool

    docs = DocumentManager(client)
    ps_mgr = PartStudioManager(client)
    ents = EntityManager(client)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    doc = await docs.create_document(name=f"dyna-mcp multi-sketch test {ts}")
    did = doc.id
    try:
        wid = (await docs.get_workspaces(did))[0].id
        ps = await ps_mgr.create_part_studio(did, wid, name="plate ps")
        eid = ps["id"]
        common = {"documentId": did, "workspaceId": wid, "elementId": eid}

        # 1. Plate outline as ONE rect via the multi-entity tool.
        out = await call_tool("create_sketch", {
            **common,
            "name": "Plate outline",
            "plane": "Top",
            "entities": [
                {"type": "rectangle", "corner1": [0, 0], "corner2": [60, 40]},
            ],
        })
        plate_sketch = json.loads(_parse_text(out))
        assert plate_sketch["status"] == "OK", plate_sketch
        plate_sketch_id = plate_sketch["feature_id"]

        # 2. Extrude the plate 6 mm.
        out = await call_tool("create_extrude", {
            **common,
            "name": "Plate extrude",
            "sketchFeatureId": plate_sketch_id,
            "depth": 6, "operationType": "NEW",
        })
        plate_ext = json.loads(_parse_text(out))
        assert plate_ext["status"] == "OK", plate_ext

        # 3. ALL 4 corner holes in ONE sketch (the whole point).
        snap = await ents.list_entities(did, wid, eid)
        top_face = next(
            f for f in snap["bodies"][0]["faces"]
            if f.get("type") == "PLANE" and f.get("outward_axis") == "+Z"
            and f.get("origin") and abs(f["origin"][2] * 1000 - 6.0) < 0.5
        )

        out = await call_tool("create_sketch", {
            **common,
            "name": "4 mounting holes",
            "faceId": top_face["id"],
            "entities": [
                # 6 mm inset from each edge -> centers at (6,6), (54,6), (54,34), (6,34)
                {"type": "circle", "center": [6, 6], "radius": 1.5},
                {"type": "circle", "center": [54, 6], "radius": 1.5},
                {"type": "circle", "center": [54, 34], "radius": 1.5},
                {"type": "circle", "center": [6, 34], "radius": 1.5},
            ],
        })
        holes_sketch = json.loads(_parse_text(out))
        assert holes_sketch["status"] == "OK", holes_sketch
        holes_sketch_id = holes_sketch["feature_id"]

        # 4. Single REMOVE extrude through all 4 holes.
        out = await call_tool("create_extrude", {
            **common,
            "name": "Cut holes",
            "sketchFeatureId": holes_sketch_id,
            "depth": 6, "operationType": "REMOVE",
            "oppositeDirection": True,
        })
        cut_ext = json.loads(_parse_text(out))
        assert cut_ext["status"] == "OK", cut_ext

        # 5. Verify: 4 cylinder faces of radius 1.5 mm.
        snap2 = await ents.list_entities(did, wid, eid)
        body = snap2["bodies"][0]
        cylinders = [
            f for f in body["faces"]
            if f.get("type") == "CYLINDER"
            and f.get("radius") is not None
            and abs(f["radius"] * 1000 - 1.5) < 0.05
        ]
        assert len(cylinders) == 4, (
            f"expected 4 ø3 cylinder faces from the multi-entity sketch, got "
            f"{len(cylinders)}: {[f['description'] for f in cylinders]}"
        )

        # 6. Feature tree should be exactly 4 (2 sketches + 2 extrudes), proving
        # the 4 holes collapsed into one sketch. Default features (Origin/Top/
        # Front/Right) live in `defaultFeatures`, not `features`.
        feats_path = (
            f"/api/v9/partstudios/d/{did}/w/{wid}/e/{eid}/features"
        )
        feats_doc = await client.get(feats_path)
        user_features = feats_doc.get("features", []) or []
        assert len(user_features) == 4, (
            f"expected exactly 4 user features (plate sketch + plate extrude + "
            f"holes sketch + cut), got {len(user_features)}: "
            f"{[(f.get('name'), f.get('featureType') or f.get('btType')) for f in user_features]}"
        )
        # Confirm shape: 2 sketches + 2 extrudes (order matters too)
        kinds = [
            "sketch" if f.get("btType") == "BTMSketch-151"
            else (f.get("featureType") or "").lower()
            for f in user_features
        ]
        assert kinds == ["sketch", "extrude", "sketch", "extrude"], (
            f"unexpected feature shape: {kinds}"
        )

    finally:
        try:
            await client.delete(f"/api/v6/documents/{did}")
        except Exception:  # noqa: BLE001
            pass
