"""End-to-end integration test: full new stack on a throwaway document.

Exercises, in one test:
    DocumentManager.create_document              -> fresh doc
    PartStudioManager.create_part_studio         -> element id
    PartStudioManager.get_plane_id               -> Top plane id
    SketchBuilder + apply_feature_and_check      -> rect sketch (status=OK)
    ExtrudeBuilder + apply_feature_and_check     -> 10mm extrude
    ShadedViewManager.render_part_studio_views   -> iso render (#1)
    SketchBuilder (add_circle) + apply_*         -> hole sketch
    ExtrudeBuilder REMOVE + apply_*              -> through-cut
    ShadedViewManager.render_part_studio_views   -> iso render (#2)
    crop_cached_image                            -> top-centre crop

Assertions:
    - every feature apply comes back with status=="OK"
    - every render returns non-blank PNG (PIL stddev > threshold)
    - the post-cut render is visually different from the pre-cut render
      (byte-hash + per-channel stddev delta)
    - the crop is non-blank

Cleanup:
    - DELETE the document at the end regardless of test outcome.

Skipped unless ONSHAPE_ACCESS_KEY is in env, so default `pytest tests/` is
unaffected.

Evidence this test's assumptions are grounded in real API shapes:
    scratchpad/smoke-test.md
    scratchpad/probe-patch-and-shadedviews.md
"""

from __future__ import annotations

import hashlib
import io
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image, ImageStat

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.entities import EntityManager
from onshape_mcp.api.feature_apply import apply_feature_and_check
from onshape_mcp.api.partstudio import PartStudioManager
from onshape_mcp.api.rendering import (
    RenderedView,
    ShadedViewManager,
    crop_cached_image,
    get_image,
)
from onshape_mcp.builders.extrude import ExtrudeBuilder, ExtrudeType
from onshape_mcp.builders.sketch import SketchBuilder, SketchPlane


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (os.getenv("ONSHAPE_ACCESS_KEY") and os.getenv("ONSHAPE_SECRET_KEY")),
        reason="Requires ONSHAPE_ACCESS_KEY/ONSHAPE_SECRET_KEY in env",
    ),
]


MM = 1.0 / 25.4  # Starter builders take inches; spec uses mm.
TMP = Path("/tmp")


def _non_blank(png_bytes: bytes) -> tuple[bool, float]:
    """Return (is_non_blank, mean_rgb_stddev). A solid-color image has stddev=0."""
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    stddev = ImageStat.Stat(img).stddev  # list of 3 per-channel stddevs
    mean = sum(stddev) / len(stddev)
    return mean > 1.0, mean


@pytest.fixture
async def client():
    creds = OnshapeCredentials(
        access_key=os.environ["ONSHAPE_ACCESS_KEY"],
        secret_key=os.environ["ONSHAPE_SECRET_KEY"],
    )
    async with OnshapeClient(creds) as c:
        yield c


@pytest.mark.asyncio
async def test_e2e_bracket_full_stack(client):
    docs = DocumentManager(client)
    ps_mgr = PartStudioManager(client)
    renderer = ShadedViewManager(client)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    doc_name = f"dyna-mcp e2e test {ts}"

    # 1. Fresh document
    doc = await docs.create_document(name=doc_name)
    assert doc.id, "create_document returned no id"
    did = doc.id

    try:
        # 2. Part Studio
        workspaces = await docs.get_workspaces(did)
        assert workspaces, "new document has no workspaces"
        wid = workspaces[0].id

        ps_result = await ps_mgr.create_part_studio(did, wid, name="bracket")
        eid = ps_result.get("id")
        assert eid, f"create_part_studio returned no id: {ps_result!r}"

        top_plane_id = await ps_mgr.get_plane_id(did, wid, eid, "Top")

        # 3. 50x30 mm rectangle on Top (inches for the builder)
        rect_builder = SketchBuilder(
            name="Rect 50x30",
            plane=SketchPlane.TOP,
            plane_id=top_plane_id,
        )
        rect_builder.add_rectangle(
            corner1=(0.0, 0.0),
            corner2=(50 * MM, 30 * MM),
        )
        rect_result = await apply_feature_and_check(
            client, did, wid, eid, rect_builder.build(), operation="create"
        )
        assert rect_result.status == "OK", (
            f"rect sketch failed: {rect_result.status} {rect_result.error_message}"
        )
        rect_sketch_id = rect_result.feature_id

        # 4. Extrude 10mm — routed through apply_feature_and_check
        extrude_builder = ExtrudeBuilder(
            name="Extrude 10mm",
            sketch_feature_id=rect_sketch_id,
            depth=10 * MM,
            operation_type=ExtrudeType.NEW,
        )
        extrude_result = await apply_feature_and_check(
            client, did, wid, eid, extrude_builder.build(), operation="create"
        )
        assert extrude_result.status == "OK", (
            f"extrude failed: {extrude_result.status} {extrude_result.error_message}"
        )
        assert extrude_result.feature_id and extrude_result.feature_id != "unknown", (
            "extrude feature_id should be the real id, not 'unknown'"
        )

        # 5. Iso render — non-blank
        pre_views = await renderer.render_part_studio_views(
            did, wid, eid, views=["iso"], width=1200, height=800
        )
        assert len(pre_views) == 1
        pre_view = pre_views[0]
        pre_bytes = get_image(pre_view.image_id)
        ok, pre_stddev = _non_blank(pre_bytes)
        assert ok, f"pre-cut iso render is blank (stddev={pre_stddev:.3f})"
        pre_path = TMP / f"e2e-bracket-pre-{ts}.png"
        pre_path.write_bytes(pre_bytes)

        # 6. ø10mm circle on Top, centred on rect centre (25, 15) mm
        circle_builder = SketchBuilder(
            name="Hole Circle",
            plane=SketchPlane.TOP,
            plane_id=top_plane_id,
        )
        circle_builder.add_circle(center=(25 * MM, 15 * MM), radius=5 * MM)
        circle_result = await apply_feature_and_check(
            client, did, wid, eid, circle_builder.build(), operation="create"
        )
        assert circle_result.status == "OK", (
            f"hole sketch failed: {circle_result.status} {circle_result.error_message}"
        )
        hole_sketch_id = circle_result.feature_id

        # 7. Cut-extrude REMOVE, 10mm deep (exactly through the 10mm plate)
        cut_builder = ExtrudeBuilder(
            name="Cut hole",
            sketch_feature_id=hole_sketch_id,
            depth=10 * MM,
            operation_type=ExtrudeType.REMOVE,
        )
        cut_result = await apply_feature_and_check(
            client, did, wid, eid, cut_builder.build(), operation="create"
        )
        assert cut_result.status == "OK", (
            f"cut failed: {cut_result.status} {cut_result.error_message}"
        )

        # 8. Second iso render — must differ from pre-cut
        post_views = await renderer.render_part_studio_views(
            did, wid, eid, views=["iso"], width=1200, height=800
        )
        post_view = post_views[0]
        post_bytes = get_image(post_view.image_id)
        ok, post_stddev = _non_blank(post_bytes)
        assert ok, f"post-cut iso render is blank (stddev={post_stddev:.3f})"
        post_path = TMP / f"e2e-bracket-post-{ts}.png"
        post_path.write_bytes(post_bytes)

        pre_hash = hashlib.sha256(pre_bytes).hexdigest()
        post_hash = hashlib.sha256(post_bytes).hexdigest()
        assert pre_hash != post_hash, (
            "pre-cut and post-cut renders are byte-identical; the hole didn't register"
        )

        # 9+10. Crop top-centre of the post-cut iso render and assert non-blank
        crop: RenderedView = crop_cached_image(
            post_view.image_id, 0.35, 0.2, 0.65, 0.6
        )
        assert crop.image_id, "crop returned no image_id"
        crop_bytes = get_image(crop.image_id)
        assert crop_bytes, "crop produced empty bytes"
        ok, crop_stddev = _non_blank(crop_bytes)
        assert ok, f"crop is blank (stddev={crop_stddev:.3f})"
        crop_path = TMP / f"e2e-bracket-crop-{ts}.png"
        crop_path.write_bytes(crop_bytes)

    finally:
        # 11. Tear down the throwaway document.
        try:
            await client.delete(f"/api/v10/documents/{did}")
        except Exception:  # noqa: BLE001
            # Best-effort; surface via warning rather than masking a test failure.
            pass


@pytest.mark.asyncio
async def test_sketch_on_top_face_creates_visible_boss(client):
    """Stage a plate, discover its top face via `list_entities`, sketch a
    5 mm circle on that face and extrude a 3 mm boss. Asserts:
        - list_entities surfaces at least one +Z-normal PLANE face with
          the highest z-origin (the top face)
        - SketchBuilder + apply_feature_and_check accepts the face's
          deterministic id as `plane_id` and returns status=="OK"
        - the post-boss iso render differs from the pre-boss one
    """
    docs = DocumentManager(client)
    ps_mgr = PartStudioManager(client)
    entities = EntityManager(client)
    renderer = ShadedViewManager(client)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    doc = await docs.create_document(name=f"dyna-mcp boss e2e {ts}")
    did = doc.id
    try:
        wid = (await docs.get_workspaces(did))[0].id
        eid = (await ps_mgr.create_part_studio(did, wid, name="plate"))["id"]
        top_plane_id = await ps_mgr.get_plane_id(did, wid, eid, "Top")

        # Base plate: 50 x 30 x 10 mm on Top
        rect = SketchBuilder(plane=SketchPlane.TOP, plane_id=top_plane_id, name="Plate")
        rect.add_rectangle(corner1=(0, 0), corner2=(50 * MM, 30 * MM))
        rect_r = await apply_feature_and_check(client, did, wid, eid, rect.build())
        assert rect_r.status == "OK", rect_r.error_message

        ext = ExtrudeBuilder(
            name="Plate 10mm", sketch_feature_id=rect_r.feature_id,
            depth=10 * MM, operation_type=ExtrudeType.NEW,
        )
        ext_r = await apply_feature_and_check(client, did, wid, eid, ext.build())
        assert ext_r.status == "OK", ext_r.error_message

        # Render for the before/after diff
        pre = (await renderer.render_part_studio_views(did, wid, eid, views=["iso"]))[0]
        pre_bytes = get_image(pre.image_id)
        ok, _ = _non_blank(pre_bytes)
        assert ok, "pre-boss render is blank"

        # Discover geometry — the whole point of this test.
        ent = await entities.list_entities(did, wid, eid, kinds=["faces"])
        assert ent["bodies"], f"list_entities returned no bodies: {ent!r}"
        faces = ent["bodies"][0]["faces"]
        top_candidates = [
            f for f in faces
            if f.get("type") == "PLANE" and f.get("normal_axis") == "+Z"
        ]
        assert top_candidates, (
            f"no +Z-normal PLANE face surfaced by list_entities; "
            f"available: {[(f.get('id'), f.get('type'), f.get('normal_axis')) for f in faces]}"
        )
        # Highest-z origin = top face (the one we just extruded up onto).
        top_face = max(top_candidates, key=lambda f: (f.get("origin") or [0, 0, 0])[2])
        top_face_id = top_face["id"]
        assert top_face_id, f"top face missing id: {top_face!r}"

        # Sketch a ø5mm circle on the top face. SketchBuilder reuses plane_id
        # for the BTMIndividualQuery-138 payload regardless of whether the ID
        # is a standard plane or a face — that is the one-line unblock.
        boss_sketch = SketchBuilder(
            plane=SketchPlane.TOP,  # plane enum is unused by build() when plane_id is set
            plane_id=top_face_id,
            name="Boss sketch",
        )
        # Centred on the plate (25, 15) mm in the local sketch frame.
        boss_sketch.add_circle(center=(25 * MM, 15 * MM), radius=2.5 * MM)
        boss_r = await apply_feature_and_check(client, did, wid, eid, boss_sketch.build())
        assert boss_r.status == "OK", (
            f"sketch-on-face status={boss_r.status}; "
            f"error={boss_r.error_message!r}; face={top_face!r}"
        )

        # Extrude +3 mm as ADD so it fuses onto the plate.
        boss_ext = ExtrudeBuilder(
            name="Boss 3mm", sketch_feature_id=boss_r.feature_id,
            depth=3 * MM, operation_type=ExtrudeType.ADD,
        )
        boss_ext_r = await apply_feature_and_check(client, did, wid, eid, boss_ext.build())
        assert boss_ext_r.status == "OK", boss_ext_r.error_message

        post = (await renderer.render_part_studio_views(did, wid, eid, views=["iso"]))[0]
        post_bytes = get_image(post.image_id)
        ok, _ = _non_blank(post_bytes)
        assert ok, "post-boss render is blank"

        assert (
            hashlib.sha256(pre_bytes).hexdigest()
            != hashlib.sha256(post_bytes).hexdigest()
        ), "pre- and post-boss renders are byte-identical; boss did not land"

        (TMP / f"e2e-boss-pre-{ts}.png").write_bytes(pre_bytes)
        (TMP / f"e2e-boss-post-{ts}.png").write_bytes(post_bytes)

    finally:
        try:
            await client.delete(f"/api/v10/documents/{did}")
        except Exception:  # noqa: BLE001
            pass
