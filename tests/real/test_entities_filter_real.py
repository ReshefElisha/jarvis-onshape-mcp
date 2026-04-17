"""Real-API proof for the list_entities filter layer.

Builds a small disposable part (plate + cylindrical boss) and exercises each
filter knob against it. Asserts both that filtered_counts < original_counts
where appropriate AND that the kept entities are the ones we expect.

The 80–100 KB response sizes vup4gnen hit came from moderately complex parts
(the 2-part Raspberry Pi case); we don't need to replicate that scale to
prove the predicate wiring — we need to prove each filter kicks in
independently against a body we control.

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
from onshape_mcp.builders.extrude import ExtrudeBuilder, ExtrudeType

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


async def _build_plate_with_boss(client):
    """Return (doc_id, ws_id, elem_id) with a 40x30x6 mm plate + 5 mm radius boss.

    Body topology after build: 6 plate faces + 2 boss top/bottom planes + 1
    cylindrical boss side + plate edges + boss edges. Enough distinct kinds
    to exercise every filter.
    """
    dm = DocumentManager(client)
    ps = PartStudioManager(client)
    doc = await dm.create_document(name="mcp-entities-filter-real (auto)")
    summary = await dm.get_document_summary(doc.id)
    ws = summary["workspaces"][0]
    elem = (await ps.create_part_studio(doc.id, ws.id, "plate"))["id"]
    top = await ps.get_plane_id(doc.id, ws.id, elem, "Top")

    # 40 x 30 plate, 6 mm thick.
    plate_sk = SketchBuilder(plane=SketchPlane.TOP, plane_id=top)
    plate_sk.add_rectangle(corner1=(0, 0), corner2=(40, 30))
    sr = await apply_feature_and_check(client, doc.id, ws.id, elem, plate_sk.build())
    assert sr.ok
    plate_ex = ExtrudeBuilder(
        sketch_feature_id=sr.feature_id, depth=6, operation_type=ExtrudeType.NEW
    )
    er = await apply_feature_and_check(client, doc.id, ws.id, elem, plate_ex.build())
    assert er.ok

    # 5 mm radius boss, 10 mm tall, ADD on top of plate.
    boss_sk = SketchBuilder(plane=SketchPlane.TOP, plane_id=top)
    boss_sk.add_circle(center=(20, 15), radius=5)
    bsr = await apply_feature_and_check(client, doc.id, ws.id, elem, boss_sk.build())
    assert bsr.ok
    boss_ex = ExtrudeBuilder(
        sketch_feature_id=bsr.feature_id, depth=16, operation_type=ExtrudeType.ADD
    )
    ber = await apply_feature_and_check(client, doc.id, ws.id, elem, boss_ex.build())
    assert ber.ok

    return doc.id, ws.id, elem


@pytest.mark.asyncio
async def test_geometry_type_prunes_to_cylinders(client):
    doc_id, ws_id, elem_id = await _build_plate_with_boss(client)
    try:
        em = EntityManager(client)
        # Unfiltered
        all_entities = await em.list_entities(doc_id, ws_id, elem_id, kinds=["faces"])
        all_face_count = sum(len(b["faces"]) for b in all_entities["bodies"])
        assert all_face_count >= 7  # 6 plate + cylinder + boss top (some edges split)

        # Cylinders only
        cyl = await em.list_entities(
            doc_id, ws_id, elem_id, kinds=["faces"], geometry_type="CYLINDER"
        )
        cyl_faces = sum(len(b["faces"]) for b in cyl["bodies"])
        assert 0 < cyl_faces < all_face_count, (
            f"cylinder filter should prune strictly: "
            f"all={all_face_count} cyl={cyl_faces}"
        )
        for body in cyl["bodies"]:
            for face in body["faces"]:
                assert face["type"] == "CYLINDER"
    finally:
        try:
            await DocumentManager(client).delete_document(doc_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                raise


@pytest.mark.asyncio
async def test_outward_axis_plus_z_keeps_only_top_faces(client):
    doc_id, ws_id, elem_id = await _build_plate_with_boss(client)
    try:
        em = EntityManager(client)
        top = await em.list_entities(
            doc_id, ws_id, elem_id, kinds=["faces"], outward_axis="+Z"
        )
        for body in top["bodies"]:
            for face in body["faces"]:
                axis = face.get("outward_axis") or face.get("normal_axis")
                assert axis == "+Z", (
                    f"unexpected face after +Z filter: id={face['id']} "
                    f"axis={axis!r}"
                )
        total = sum(len(b["faces"]) for b in top["bodies"])
        # Plate top (at z=6) AND boss top (at z=16) both face +Z ⇒ ≥2.
        assert total >= 2, f"expected plate-top and boss-top, got {total}"
    finally:
        try:
            await DocumentManager(client).delete_document(doc_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                raise


@pytest.mark.asyncio
async def test_at_z_mm_picks_faces_at_plate_bottom(client):
    doc_id, ws_id, elem_id = await _build_plate_with_boss(client)
    try:
        em = EntityManager(client)
        bottom = await em.list_entities(
            doc_id, ws_id, elem_id, kinds=["faces"], at_z_mm=0.0, at_z_tol_mm=0.1
        )
        for body in bottom["bodies"]:
            for face in body["faces"]:
                z_mm = face["origin"][2] * 1000.0
                assert abs(z_mm) < 0.11, f"face {face['id']} origin z={z_mm:.3f} mm"
    finally:
        try:
            await DocumentManager(client).delete_document(doc_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                raise


@pytest.mark.asyncio
async def test_radius_range_mm_picks_boss_cylinder(client):
    """5 mm boss radius is in [4, 6]; no other face has a radius."""
    doc_id, ws_id, elem_id = await _build_plate_with_boss(client)
    try:
        em = EntityManager(client)
        result = await em.list_entities(
            doc_id, ws_id, elem_id, kinds=["faces"],
            radius_range_mm=[4.0, 6.0],
        )
        picks = [f for b in result["bodies"] for f in b["faces"]]
        assert len(picks) == 1, f"expected exactly 1 cylinder in [4,6] mm, got {picks!r}"
        assert picks[0]["type"] == "CYLINDER"
        assert abs((picks[0]["radius"] or 0) * 1000 - 5.0) < 0.001
    finally:
        try:
            await DocumentManager(client).delete_document(doc_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                raise


@pytest.mark.asyncio
async def test_length_range_mm_edges_only(client):
    """Plate long edges are 40 mm, short edges are 30 mm. [35, 45] picks 40s."""
    doc_id, ws_id, elem_id = await _build_plate_with_boss(client)
    try:
        em = EntityManager(client)
        forty = await em.list_entities(
            doc_id, ws_id, elem_id, kinds=["edges"],
            length_range_mm=[38.0, 42.0],
        )
        picks = [e for b in forty["bodies"] for e in b["edges"]]
        assert len(picks) >= 2, f"expected ≥2 edges in [38,42] mm, got {len(picks)}"
        for e in picks:
            length_mm = (e.get("length") or 0) * 1000.0
            assert 38.0 <= length_mm <= 42.0
    finally:
        try:
            await DocumentManager(client).delete_document(doc_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                raise


@pytest.mark.asyncio
async def test_response_echoes_filters_and_counts(client):
    doc_id, ws_id, elem_id = await _build_plate_with_boss(client)
    try:
        em = EntityManager(client)
        result = await em.list_entities(
            doc_id, ws_id, elem_id, kinds=["faces"],
            geometry_type="PLANE", outward_axis="+Z",
        )
        assert result["filters"]["geometry_type"] == "PLANE"
        assert result["filters"]["outward_axis"] == "+Z"
        assert result["original_counts"], "original_counts must be populated"
        assert result["filtered_counts"], "filtered_counts must be populated"
        # Filtered count must be <= original count per body.
        for bid, orig in result["original_counts"].items():
            filt = result["filtered_counts"].get(bid)
            assert filt is not None
            assert filt["faces"] <= orig["faces"]
    finally:
        try:
            await DocumentManager(client).delete_document(doc_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                raise
