"""Real-API tests for DrawingSectionManager.

Status 2026-04-16: the headline `render_section` method is BLOCKED by an
Onshape platform gap (section views cannot be created via the public API —
only TopLevel / Projected). See `scratchpad/drawing-section-research.md`.

This test file asserts two things against the LIVE Onshape API:

1. The WORKING scaffolding is really working — create a throwaway doc with a
   40x40x20 mm block + 10 mm hole, make a drawing, add a TopLevel Front view,
   export as PNG, and verify the bytes are a real PNG of nontrivial size.
   This proves the pipeline in `drawing_section.py` is correct; the day
   Onshape ships API section support, the `_add_section_view` stub is the
   only piece that needs filling in.

2. The BLOCKED section-view creation path fails loudly — `render_section`
   must raise NotImplementedError (never silently return or fall back to
   the FS cut path). Asserting this so a future refactor can't quietly
   turn it into a cosmetic regression.

Skipped unless ONSHAPE keys are in env.
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
from onshape_mcp.api.drawing_section import DrawingSectionManager
from onshape_mcp.api.feature_apply import apply_feature_and_check
from onshape_mcp.api.partstudio import PartStudioManager
from onshape_mcp.builders.extrude import ExtrudeBuilder, ExtrudeType
from onshape_mcp.builders.sketch import SketchBuilder, SketchPlane


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (
            (os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY"))
            and (os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET"))
        ),
        reason="Requires ONSHAPE_ACCESS_KEY/SECRET_KEY (or ONSHAPE_API_KEY/SECRET) in env",
    ),
]

MM = 1.0 / 25.4  # Builders take inches; spec uses mm.
TMP = Path("/tmp")


def _creds() -> OnshapeCredentials:
    ak = os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY", "")
    sk = os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET", "")
    return OnshapeCredentials(access_key=ak, secret_key=sk)


@pytest.fixture
async def client():
    async with OnshapeClient(_creds()) as c:
        yield c


async def _build_block_with_hole(client, did, wid) -> tuple[str, str]:
    """Build a 40x40x20 mm block with a centered 10 mm through-hole.

    Returns (part_studio_element_id, partId).
    """
    ps_mgr = PartStudioManager(client)
    eid = (await ps_mgr.create_part_studio(did, wid, name="block"))["id"]
    top = await ps_mgr.get_plane_id(did, wid, eid, "Top")

    # 40x40 rect centered on origin
    rect = SketchBuilder(plane=SketchPlane.TOP, plane_id=top, name="sq")
    rect.add_rectangle(corner1=(-20 * MM, -20 * MM), corner2=(20 * MM, 20 * MM))
    r = await apply_feature_and_check(client, did, wid, eid, rect.build())
    assert r.status == "OK", r.error_message

    ext = ExtrudeBuilder(
        name="block",
        sketch_feature_id=r.feature_id,
        depth=20 * MM,
        operation_type=ExtrudeType.NEW,
    )
    e = await apply_feature_and_check(client, did, wid, eid, ext.build())
    assert e.status == "OK", e.error_message

    # 10 mm centered through-hole
    circle = SketchBuilder(plane=SketchPlane.TOP, plane_id=top, name="hole_sk")
    circle.add_circle(center=(0.0, 0.0), radius=5 * MM)
    r2 = await apply_feature_and_check(client, did, wid, eid, circle.build())
    assert r2.status == "OK", r2.error_message

    cut = ExtrudeBuilder(
        name="hole",
        sketch_feature_id=r2.feature_id,
        depth=20 * MM,
        operation_type=ExtrudeType.REMOVE,
    )
    cr = await apply_feature_and_check(client, did, wid, eid, cut.build())
    assert cr.status == "OK", cr.error_message

    # Fetch partId (idTag we'll need for the drawing view reference)
    parts = await client.get(
        f"/api/v9/parts/d/{did}/w/{wid}/e/{eid}"
    )
    assert parts, "no parts on the block part studio"
    return eid, parts[0]["partId"]


@pytest.mark.asyncio
async def test_drawing_section_render_section_is_blocked_and_raises(client):
    """The headline method must fail loudly until Onshape ships server
    support. No silent fallback to the FS cut-render-delete path."""
    dsm = DrawingSectionManager(client)
    with pytest.raises(NotImplementedError) as excinfo:
        await dsm.render_section(
            document_id="x" * 24,
            workspace_id="x" * 24,
            part_studio_element_id="x" * 24,
            plane_origin=(0.0, 0.0, 0.01),
            plane_normal=(0.0, 1.0, 0.0),
        )
    msg = str(excinfo.value)
    # Must point at the research doc and name the specific Onshape error, so
    # future maintainers hit by this see the exact blocker without digging.
    assert "scratchpad/drawing-section-research.md" in msg
    assert "not supported" in msg.lower()


@pytest.mark.asyncio
async def test_drawing_scaffolding_end_to_end_png(client):
    """Exercise the WORKING pieces — create drawing, add TopLevel view,
    translate to PNG. Confirms the pipeline in `drawing_section.py` is wired
    up correctly so only `_add_section_view` needs a body on the day Onshape
    unlocks API section support.
    """
    docs = DocumentManager(client)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    doc = await docs.create_document(name=f"drawing-section-scaffold {ts}")
    did = doc.id
    assert did

    try:
        wid = (await docs.get_workspaces(did))[0].id
        ps_eid, part_id = await _build_block_with_hole(client, did, wid)

        dsm = DrawingSectionManager(client)

        # 1. Create drawing element
        drawing_eid = await dsm.create_drawing(
            did, wid,
            drawing_name=f"scaffold_drawing_{ts}",
            part_studio_element_id=ps_eid,
        )
        assert drawing_eid, "create_drawing returned no id"

        # 2. Add a Front TopLevel view
        view = await dsm.add_toplevel_view(
            did, wid, drawing_eid,
            part_studio_element_id=ps_eid,
            part_id=part_id,
            orientation="front",
            position=(5.0, 5.0),
        )
        assert view.status == "OK", view.error_message
        assert view.logical_id, "no logicalId returned"
        assert view.view_id, "no viewId returned"

        # 3. Translate to PNG. Drawings' /translations supports PNG per
        #    /translationformats (confirmed live 2026-04-16).
        result = await dsm.translate_drawing_to_png(
            did, wid, drawing_eid, format_name="PNG",
            timeout_seconds=180.0,
        )
        assert result.ok, f"translation failed: state={result.state} err={result.error_message}"
        assert result.data, "translation returned no bytes"
        # PNG magic: 89 50 4E 47 0D 0A 1A 0A
        assert result.data[:8] == b"\x89PNG\r\n\x1a\n", (
            f"not a PNG; first 8 bytes = {result.data[:8]!r}"
        )
        # Should be non-trivially large — a bare drawing with a Front view of
        # a 40 mm block is normally >30 KB.
        assert len(result.data) > 5000, f"PNG unexpectedly small: {len(result.data)} bytes"

        # Non-blank sanity check
        img = Image.open(io.BytesIO(result.data)).convert("RGB")
        stddev = ImageStat.Stat(img).stddev
        assert sum(stddev) / 3 > 0.5, f"PNG is effectively blank: stddev={stddev}"

        out_path = TMP / f"drawing-section-scaffold-{ts}.png"
        out_path.write_bytes(result.data)
        print(f"\nWROTE {out_path} ({len(result.data)} bytes)")

        # 4. Best-effort cleanup of the drawing element (noop on failure)
        await dsm.delete_drawing(did, wid, drawing_eid)

    finally:
        try:
            await client.delete(f"/api/v10/documents/{did}")
        except Exception:  # noqa: BLE001
            # API key may not have doc-delete scope. Leave doc for inspection.
            pass


@pytest.mark.asyncio
async def test_section_view_creation_reproduces_platform_rejection(client):
    """Regression probe: confirm directly against Onshape that the Section
    viewType is still rejected. If this EVER fails (i.e., Onshape starts
    accepting it), we know it's time to go fill in `_add_section_view` and
    implement `render_section` for real.
    """
    docs = DocumentManager(client)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    doc = await docs.create_document(name=f"drawing-section-probe {ts}")
    did = doc.id
    try:
        wid = (await docs.get_workspaces(did))[0].id
        ps_eid, part_id = await _build_block_with_hole(client, did, wid)

        dsm = DrawingSectionManager(client)
        drawing_eid = await dsm.create_drawing(
            did, wid,
            drawing_name=f"probe_{ts}",
            part_studio_element_id=ps_eid,
        )
        front = await dsm.add_toplevel_view(
            did, wid, drawing_eid,
            part_studio_element_id=ps_eid,
            part_id=part_id,
            orientation="front",
        )
        assert front.status == "OK"

        # Fire the best-guess Section payload directly and poll for result.
        mrid = await dsm._post_modify(
            did, wid, drawing_eid,
            description="Probe: section view creation",
            json_requests=[{
                "messageName": "onshapeCreateViews",
                "formatVersion": "2021-01-01",
                "views": [{
                    "viewType": "Section",
                    "position": {"x": 11.0, "y": 5.0},
                    "parentView": {"logicalId": front.logical_id},
                    "cuttingPlane": {
                        "origin": {"x": 0.0, "y": 0.0, "z": 0.01},
                        "normal": {"x": 0.0, "y": 1.0, "z": 0.0},
                    },
                }],
            }],
        )
        result = await dsm._poll_modify(mrid)

        # We expect this to fail. If it ever succeeds, Onshape shipped
        # support and the assertion below will fail — that's the signal.
        if result.ok:
            pytest.fail(
                "Section view creation UNEXPECTEDLY SUCCEEDED. "
                "Onshape may have shipped API support. Go implement "
                "DrawingSectionManager._add_section_view and render_section. "
                f"Result: {result.results!r}"
            )
        assert result.results, f"no per-view results: {result.raw!r}"
        err = result.results[0].error_message or ""
        assert "not supported" in err.lower(), (
            f"expected 'not supported' error, got: {err!r}"
        )

        await dsm.delete_drawing(did, wid, drawing_eid)
    finally:
        try:
            await client.delete(f"/api/v10/documents/{did}")
        except Exception:  # noqa: BLE001
            pass
