"""Real-API test for auto-`oppositeDirection` on REMOVE+faceId extrudes.

Dogfooder z5rz5fhl bug #7: a sketch placed on a +Z face followed by a
REMOVE extrude with the default direction cuts AWAY from the face --
into air -- so Onshape returns `INFO: nothing was cut`, the truth
helper reports ok=true, and the LLM moves on unaware.

Fix in server.py `create_extrude` handler: when `oppositeDirection` is
not passed AND `operationType == "REMOVE"` AND the sketch is on a
picked face (any deterministic id outside the standard JCC/JDC/JEC),
default to oppositeDirection=true and surface a `notes` entry.

Two tests:
    1. The auto-flip case: drop oppositeDirection on a REMOVE+face
       extrude. Assert the response carries the auto-flip note AND the
       body actually has 1 ø3 cylinder face (cut wasn't a no-op).
    2. The override case: pass oppositeDirection=false explicitly.
       Auto-flip note must NOT appear; body must NOT have a new
       cylinder (cut went the other way and removed nothing).

Each test creates its own OnshapeClient inline. The shared loop-scope
hazard (server.client._client cached across pytest-asyncio loops) is
handled by the autouse fixture in tests/real/conftest.py.
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


async def _build_plate_with_top_face(client, call_tool, *, doc_name: str):
    """Common setup: 60x40x6 plate, returns (did, wid, eid, top_face_id)."""
    docs = DocumentManager(client)
    ps_mgr = PartStudioManager(client)
    ents = EntityManager(client)

    doc = await docs.create_document(name=doc_name)
    did = doc.id
    wid = (await docs.get_workspaces(did))[0].id
    eid = (await ps_mgr.create_part_studio(did, wid, name="ps"))["id"]
    common = {"documentId": did, "workspaceId": wid, "elementId": eid}

    out = await call_tool("create_sketch_rectangle", {
        **common, "plane": "Top",
        "corner1": [0, 0], "corner2": [60, 40],
    })
    rect = json.loads(_parse_text(out))
    assert rect["status"] == "OK", rect

    out = await call_tool("create_extrude", {
        **common, "sketchFeatureId": rect["feature_id"],
        "depth": 6, "operationType": "NEW",
    })
    plate = json.loads(_parse_text(out))
    assert plate["status"] == "OK", plate

    snap = await ents.list_entities(did, wid, eid)
    top_face = next(
        f for f in snap["bodies"][0]["faces"]
        if f.get("type") == "PLANE" and f.get("outward_axis") == "+Z"
        and f.get("origin") and abs(f["origin"][2] * 1000 - 6.0) < 0.5
    )
    return did, wid, eid, top_face["id"]


# NB: tests/real/conftest.py provides an autouse fixture that resets
# `onshape_mcp.server.client._client = None` between tests, so multiple
# `call_tool`-driven tests in this file don't trip "Event loop is closed"
# from the module-level singleton being bound to a previous loop.


@pytest.mark.asyncio
async def test_remove_on_face_auto_flips_oppositeDirection():
    """REMOVE extrude on a picked face with NO explicit oppositeDirection
    should auto-flip the cut into the material."""
    from onshape_mcp.server import call_tool

    async with OnshapeClient(_creds()) as client:
        ents = EntityManager(client)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        did, wid, eid, top_face_id = await _build_plate_with_top_face(
            client, call_tool, doc_name=f"dyna-mcp auto-opposite test {ts}"
        )
        try:
            common = {"documentId": did, "workspaceId": wid, "elementId": eid}

            # Hole sketch on the top face.
            out = await call_tool("create_sketch_circle", {
                **common, "name": "Hole",
                "faceId": top_face_id,
                "center": [30, 20], "radius": 1.5,
            })
            hole = json.loads(_parse_text(out))
            assert hole["status"] == "OK", hole

            # The fix-under-test: REMOVE WITHOUT oppositeDirection.
            out = await call_tool("create_extrude", {
                **common, "name": "Cut hole",
                "sketchFeatureId": hole["feature_id"],
                "depth": 6, "operationType": "REMOVE",
                # NB: no oppositeDirection -- the regression-prone case.
            })
            cut = json.loads(_parse_text(out))
            assert cut["status"] == "OK", cut

            # Auto-flip should be reported via the new `notes` field.
            notes = cut.get("notes") or []
            assert any(
                "oppositeDirection" in n and "picked face" in n for n in notes
            ), (
                f"expected notes to flag the auto-flipped oppositeDirection on a "
                f"REMOVE+faceId extrude; got notes={notes!r}"
            )

            # Material was actually removed.
            snap2 = await ents.list_entities(did, wid, eid)
            cylinders = [
                f for f in snap2["bodies"][0]["faces"]
                if f.get("type") == "CYLINDER"
                and f.get("radius") is not None
                and abs(f["radius"] * 1000 - 1.5) < 0.05
            ]
            assert len(cylinders) == 1, (
                f"expected 1 ø3 cylinder face after auto-flipped REMOVE, got "
                f"{len(cylinders)}: {[f['description'] for f in cylinders]}. "
                f"The cut probably no-op'd -- auto-flip didn't fire?"
            )

        finally:
            try:
                await client.delete(f"/api/v6/documents/{did}")
            except Exception:  # noqa: BLE001
                pass


@pytest.mark.asyncio
async def test_explicit_oppositeDirection_false_overrides_auto_flip():
    """Caller can still override the smart default. Pass oppositeDirection=false
    explicitly on REMOVE+face and the cut goes the other way (away from the
    material). Assert the body has NO new cylinder, proving we did NOT cut
    into material -- the explicit override was honored."""
    from onshape_mcp.server import call_tool

    async with OnshapeClient(_creds()) as client:
        ents = EntityManager(client)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        did, wid, eid, top_face_id = await _build_plate_with_top_face(
            client, call_tool, doc_name=f"dyna-mcp auto-opposite override {ts}"
        )
        try:
            common = {"documentId": did, "workspaceId": wid, "elementId": eid}

            out = await call_tool("create_sketch_circle", {
                **common, "faceId": top_face_id,
                "center": [30, 20], "radius": 1.5,
            })
            hole = json.loads(_parse_text(out))
            assert hole["status"] == "OK"

            # Explicit override: oppositeDirection=false. Auto-flip must NOT
            # fire.
            out = await call_tool("create_extrude", {
                **common, "sketchFeatureId": hole["feature_id"],
                "depth": 6, "operationType": "REMOVE",
                "oppositeDirection": False,
            })
            cut = json.loads(_parse_text(out))
            # Onshape may report INFO ("nothing was cut") on this; the truth
            # helper still surfaces ok=true for INFO. What we care about: the
            # auto-flip note must NOT appear.
            notes = cut.get("notes") or []
            assert not any(
                "oppositeDirection" in n and "picked face" in n for n in notes
            ), (
                f"auto-flip note appeared despite explicit "
                f"oppositeDirection=false: {notes!r}"
            )

            # And no new cylinder face appeared -- override was honored.
            snap2 = await ents.list_entities(did, wid, eid)
            cylinders = [
                f for f in snap2["bodies"][0]["faces"]
                if f.get("type") == "CYLINDER"
                and f.get("radius") is not None
                and abs(f["radius"] * 1000 - 1.5) < 0.05
            ]
            assert len(cylinders) == 0, (
                f"explicit oppositeDirection=false should have cut UP into "
                f"air, but a ø3 cylinder appeared in the body -- override "
                f"was ignored. cylinders="
                f"{[f['description'] for f in cylinders]}"
            )

        finally:
            try:
                await client.delete(f"/api/v6/documents/{did}")
            except Exception:  # noqa: BLE001
                pass
