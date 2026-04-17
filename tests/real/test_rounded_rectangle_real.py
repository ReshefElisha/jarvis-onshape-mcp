"""Real-API test for the rounded-rectangle sketch primitive.

Dogfooder vup4gnen reported rewriting the 4-line-4-arc rounded rectangle
twice in one session and fumbling radians vs degrees. New tool:
`create_rounded_rectangle_sketch` emits all 8 entities + connecting
constraints in one feature, plus a `type: "rounded_rectangle"` branch
on the multi-entity `create_sketch` tool.

Test: build a 40x30 mm rounded rectangle with r=5 mm on Top, extrude 5mm.
Asserts:
    - sketch + extrude both regen OK
    - the resulting body has exactly 4 cylindrical faces of radius 5 mm
      (one per filleted corner, running vertically through the extrusion)
    - list_entities surfaces 4 CIRCLE edges of radius 5 mm on the top face
      (the arc traces at z = 5 mm)
"""

from __future__ import annotations

import json
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


def _parse_text(blocks) -> str:
    for b in blocks:
        if getattr(b, "type", None) == "text":
            return b.text
    return ""


@pytest.mark.asyncio
async def test_rounded_rectangle_standalone_tool_builds_clean_body():
    from onshape_mcp.server import call_tool

    async with OnshapeClient(_creds()) as client:
        docs = DocumentManager(client)
        ps_mgr = PartStudioManager(client)
        ents = EntityManager(client)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        doc = await docs.create_document(name=f"dyna-mcp rrect test {ts}")
        did = doc.id
        try:
            wid = (await docs.get_workspaces(did))[0].id
            eid = (await ps_mgr.create_part_studio(did, wid, name="ps"))["id"]
            common = {"documentId": did, "workspaceId": wid, "elementId": eid}

            # Sketch via the standalone tool.
            out = await call_tool("create_rounded_rectangle_sketch", {
                **common, "name": "Rrect", "plane": "Top",
                "corner1": [0, 0], "corner2": [40, 30],
                "cornerRadius": 5,
            })
            sketch = json.loads(_parse_text(out))
            assert sketch["status"] == "OK", sketch

            # Extrude 5 mm.
            out = await call_tool("create_extrude", {
                **common, "name": "Ext",
                "sketchFeatureId": sketch["feature_id"],
                "depth": 5, "operationType": "NEW",
            })
            ext = json.loads(_parse_text(out))
            assert ext["status"] == "OK", ext

            # Verify body-level face count: 4 cylindrical faces at r=5 mm.
            snap = await ents.list_entities(did, wid, eid)
            body = snap["bodies"][0]
            cyl5 = [
                f for f in body["faces"]
                if f.get("type") == "CYLINDER"
                and f.get("radius") is not None
                and abs(f["radius"] * 1000 - 5.0) < 0.05
            ]
            assert len(cyl5) == 4, (
                f"expected 4 cylindrical fillet faces of r=5mm, got "
                f"{len(cyl5)}: {[f.get('description') for f in cyl5]}"
            )

            # The top face at z=5 should have 4 CIRCLE edges of radius 5 mm
            # (the arc traces) plus 4 LINE edges of length 30 and 20 mm
            # (40-2*5 and 30-2*5).
            top_arcs = [
                e for e in body["edges"]
                if e.get("type") == "CIRCLE"
                and e.get("radius") is not None
                and abs(e["radius"] * 1000 - 5.0) < 0.05
                and e.get("midpoint") is not None
                and abs(e["midpoint"][2] * 1000 - 5.0) < 0.5
            ]
            assert len(top_arcs) == 4, (
                f"expected 4 arc edges of r=5mm on the top face, got "
                f"{len(top_arcs)}: {[e.get('description') for e in top_arcs]}"
            )

        finally:
            try:
                await client.delete(f"/api/v6/documents/{did}")
            except Exception:  # noqa: BLE001
                pass


@pytest.mark.asyncio
async def test_rounded_rectangle_via_multi_entity_sketch():
    """Same rounded rect, but through the multi-entity `create_sketch` tool
    via `type: "rounded_rectangle"`. Also mixes a second entity (centred
    circle) in the same feature to confirm composition."""
    from onshape_mcp.server import call_tool

    async with OnshapeClient(_creds()) as client:
        docs = DocumentManager(client)
        ps_mgr = PartStudioManager(client)
        ents = EntityManager(client)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        doc = await docs.create_document(name=f"dyna-mcp rrect-multi test {ts}")
        did = doc.id
        try:
            wid = (await docs.get_workspaces(did))[0].id
            eid = (await ps_mgr.create_part_studio(did, wid, name="ps"))["id"]
            common = {"documentId": did, "workspaceId": wid, "elementId": eid}

            out = await call_tool("create_sketch", {
                **common, "name": "Rrect+hole", "plane": "Top",
                "entities": [
                    {"type": "rounded_rectangle",
                     "corner1": [0, 0], "corner2": [40, 30], "cornerRadius": 5},
                    {"type": "circle", "center": [20, 15], "radius": 2},
                ],
            })
            sketch = json.loads(_parse_text(out))
            assert sketch["status"] == "OK", sketch

            # Extrude: with an inner hole sketched as a second closed profile,
            # Onshape treats it as a through-hole region and yields a body
            # with 5 cylindrical faces (4 corner fillets + 1 inner cylinder).
            out = await call_tool("create_extrude", {
                **common, "sketchFeatureId": sketch["feature_id"],
                "depth": 4, "operationType": "NEW",
            })
            ext = json.loads(_parse_text(out))
            assert ext["status"] == "OK", ext

            snap = await ents.list_entities(did, wid, eid)
            body = snap["bodies"][0]
            cyl5 = [
                f for f in body["faces"]
                if f.get("type") == "CYLINDER"
                and f.get("radius") is not None
                and abs(f["radius"] * 1000 - 5.0) < 0.05
            ]
            cyl2 = [
                f for f in body["faces"]
                if f.get("type") == "CYLINDER"
                and f.get("radius") is not None
                and abs(f["radius"] * 1000 - 2.0) < 0.05
            ]
            assert len(cyl5) == 4, f"expected 4 r=5 cylinders, got {len(cyl5)}"
            assert len(cyl2) == 1, f"expected 1 r=2 inner cylinder, got {len(cyl2)}"

        finally:
            try:
                await client.delete(f"/api/v6/documents/{did}")
            except Exception:  # noqa: BLE001
                pass
