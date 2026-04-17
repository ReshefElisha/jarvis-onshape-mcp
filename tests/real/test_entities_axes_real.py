"""Real-API proof that the evFaceTangentPlane probe returns clean U/V axes.

Builds a plate with +Z top and +Y side faces, then checks list_entities
labels the top face's sketch axes as `+X` / `+Y` (identity) and one of the
side faces' sketch axes as `+X` / `+Z`. If either comes back None or off-axis,
the FS probe or parser broke.

Auto-skipped without credentials.
"""

from __future__ import annotations

import os

import httpx
import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.entities import EntityManager
from onshape_mcp.api.partstudio import PartStudioManager
from onshape_mcp.api.feature_apply import apply_feature_and_check
from onshape_mcp.builders.sketch import SketchBuilder, SketchPlane
from onshape_mcp.builders.extrude import ExtrudeBuilder

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
    ak = os.environ.get("ONSHAPE_ACCESS_KEY") or os.environ["ONSHAPE_API_KEY"]
    sk = os.environ.get("ONSHAPE_SECRET_KEY") or os.environ["ONSHAPE_API_SECRET"]
    async with OnshapeClient(OnshapeCredentials(access_key=ak, secret_key=sk)) as c:
        yield c


@pytest.mark.asyncio
async def test_face_local_axes_on_planar_faces(client):
    dm = DocumentManager(client)
    ps = PartStudioManager(client)
    doc = await dm.create_document(name="mcp-entities-axes-real (auto)")
    try:
        summary = await dm.get_document_summary(doc.id)
        ws = summary["workspaces"][0]
        elem = (await ps.create_part_studio(doc.id, ws.id, "plate"))["id"]
        top = await ps.get_plane_id(doc.id, ws.id, elem, "Top")

        # 40 x 30 plate, 6 mm thick on Top plane.
        sk = SketchBuilder(plane=SketchPlane.TOP, plane_id=top)
        sk.add_rectangle(corner1=(0, 0), corner2=(40, 30))
        sr = await apply_feature_and_check(client, doc.id, ws.id, elem, sk.build())
        assert sr.ok
        ex = ExtrudeBuilder(sketch_feature_id=sr.feature_id, depth=6)
        er = await apply_feature_and_check(client, doc.id, ws.id, elem, ex.build())
        assert er.ok

        em = EntityManager(client)
        result = await em.list_entities(doc.id, ws.id, elem, kinds=["faces"])
        faces = [f for b in result["bodies"] for f in b["faces"]]

        # Every planar face should have sketch_x_world + sketch_y_world set.
        planar = [f for f in faces if f["type"] == "PLANE"]
        for f in planar:
            assert f["sketch_x_world"] is not None, f"face {f['id']} missing sketch_x"
            assert f["sketch_y_world"] is not None, f"face {f['id']} missing sketch_y"

        # Top face: outward +Z, sketch axes should land on world X/Y cleanly.
        tops = [f for f in planar if f.get("outward_axis") == "+Z"]
        assert tops, "no +Z face found"
        top_face = tops[0]
        assert top_face["sketch_x_axis"] in ("+X", "-X", "+Y", "-Y"), (
            f"top face sketch-x not axis-aligned: {top_face['sketch_x_axis']!r}"
        )
        assert top_face["sketch_y_axis"] in ("+X", "-X", "+Y", "-Y"), (
            f"top face sketch-y not axis-aligned: {top_face['sketch_y_axis']!r}"
        )
        # And the description carries both labels.
        assert "sketch-x=" in top_face["description"]
        assert "sketch-y=" in top_face["description"]

        # A +Y-facing side face should have sketch_y = ±Z (vertical on that
        # face maps to world Z) and sketch_x = ±X.
        y_faces = [f for f in planar if f.get("outward_axis") in ("+Y", "-Y")]
        assert y_faces, "no Y-facing side face found"
        y_face = y_faces[0]
        assert y_face["sketch_x_axis"] in ("+X", "-X", "+Z", "-Z")
        assert y_face["sketch_y_axis"] in ("+X", "-X", "+Z", "-Z")
        # At least one sketch axis must be along Z for a vertical face —
        # that's the whole point: vertical side faces had guesswork sketch
        # mapping before this.
        assert "+Z" in {y_face["sketch_x_axis"], y_face["sketch_y_axis"]} or \
               "-Z" in {y_face["sketch_x_axis"], y_face["sketch_y_axis"]}

    finally:
        try:
            await dm.delete_document(doc.id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                raise
