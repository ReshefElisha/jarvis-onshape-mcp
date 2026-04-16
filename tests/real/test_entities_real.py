"""Real-API test for list_entities. Auto-skips without creds."""

from __future__ import annotations

import os
import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.entities import EntityManager

SMOKE_DOC = "c287a50857bf10a5be2320c5"
SMOKE_WS = "24098a6dfa377ad0daa8e665"
SMOKE_PARTSTUDIO = "e3c89e99b01c0eb6fbfdc773"


def _creds_present() -> bool:
    ak = os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY")
    sk = os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET")
    return bool(ak and sk)


pytestmark = pytest.mark.skipif(
    not _creds_present(),
    reason="ONSHAPE_ACCESS_KEY/SECRET_KEY or ONSHAPE_API_KEY/SECRET not set",
)


@pytest.mark.asyncio
async def test_list_entities_returns_faces_and_edges_with_ids_and_descriptions():
    ak = os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY", "")
    sk = os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET", "")
    creds = OnshapeCredentials(access_key=ak, secret_key=sk)
    async with OnshapeClient(creds) as c:
        em = EntityManager(c)
        out = await em.list_entities(SMOKE_DOC, SMOKE_WS, SMOKE_PARTSTUDIO)

    assert out["bodies"], "no bodies returned"
    body = out["bodies"][0]

    # Faces: smoke doc's body is a 50x30x15mm rectangular solid with a blind
    # cylindrical hole on top. That is 7 planar faces (6 of the rectangular
    # box + 1 planar bottom of the hole) plus 1 cylindrical face = 8 total.
    faces = body["faces"]
    assert len(faces) == 8, f"expected 8 faces, got {len(faces)}"
    plane_faces = [f for f in faces if f["type"] == "PLANE"]
    cyl_faces = [f for f in faces if f["type"] == "CYLINDER"]
    assert len(plane_faces) == 7
    assert len(cyl_faces) == 1

    # Every face has a deterministic id and a human description.
    for f in faces:
        assert f["id"], f"face missing id: {f}"
        assert f["description"], f"face missing description: {f}"

    # Top face exists (normal +Z at the highest z): must be uniquely identifiable.
    top_faces = [
        f for f in plane_faces
        if f.get("normal_axis") == "+Z" and f.get("origin") and f["origin"][2] > 0.01
    ]
    assert len(top_faces) >= 1, (
        f"expected at least one +Z face above origin; got {[f['description'] for f in plane_faces]}"
    )

    # Edges: should include some linear edges with computed lengths.
    edges = body["edges"]
    assert edges, "no edges returned"
    lines = [e for e in edges if e["type"] == "LINE"]
    assert lines, "expected some LINE edges"
    for e in lines:
        assert e["length"] is not None and e["length"] > 0
        assert e["id"]
        assert e["description"]

    # The 15mm-tall rect has 4 vertical line edges of length 15mm.
    vertical_15 = [
        e for e in lines
        if abs((e["length"] or 0) - 0.015) < 1e-4 and e.get("direction_axis") in ("+Z", "-Z")
    ]
    assert len(vertical_15) == 4, f"expected 4 vertical 15mm edges, got {len(vertical_15)}"


@pytest.mark.asyncio
async def test_list_entities_respects_kinds_filter():
    ak = os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY", "")
    sk = os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET", "")
    creds = OnshapeCredentials(access_key=ak, secret_key=sk)
    async with OnshapeClient(creds) as c:
        em = EntityManager(c)
        out = await em.list_entities(
            SMOKE_DOC, SMOKE_WS, SMOKE_PARTSTUDIO, kinds=["faces"]
        )
    body = out["bodies"][0]
    assert "faces" in body
    assert "edges" not in body
    assert "vertices" not in body
