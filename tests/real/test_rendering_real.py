"""Real-API test for rendering tools. Auto-skips when ONSHAPE keys absent.

Uses the persistent smoke-test doc c287a50857bf10a5be2320c5 preserved by peer
47ausr6g. Doc contains a small Part Studio with an extrude, a cut, a fillet
(in ERROR state -- deliberate), etc. These tests just exercise the render path;
they do not mutate the doc.
"""

from __future__ import annotations

import io
import os
import pytest
from PIL import Image

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.rendering import (
    ShadedViewManager,
    crop_cached_image,
    get_image,
    list_cached_image_ids,
)

SMOKE_DOC = "c287a50857bf10a5be2320c5"
SMOKE_WS = "24098a6dfa377ad0daa8e665"
# Peer 47ausr6g's probe built the geometry in this specific Part Studio element.
# The doc also contains an empty Part Studio; rendering that one returns a blank
# PNG which is technically correct but useless for verifying the render path.
SMOKE_PARTSTUDIO = "e3c89e99b01c0eb6fbfdc773"


def _creds_present() -> bool:
    ak = os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY")
    sk = os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET")
    return bool(ak and sk)


pytestmark = pytest.mark.skipif(
    not _creds_present(),
    reason="ONSHAPE_ACCESS_KEY/SECRET_KEY or ONSHAPE_API_KEY/SECRET not set",
)


async def _get_workspace_and_element(client: OnshapeClient):
    """Return the known workspace + Part Studio id from the probe."""
    return SMOKE_WS, SMOKE_PARTSTUDIO


@pytest.mark.asyncio
async def test_render_part_studio_iso_view_returns_real_png():
    ak = os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY", "")
    sk = os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET", "")
    creds = OnshapeCredentials(access_key=ak, secret_key=sk)
    async with OnshapeClient(creds) as client:
        wid, eid = await _get_workspace_and_element(client)
        svm = ShadedViewManager(client)
        rendered = await svm.render_part_studio_views(
            document_id=SMOKE_DOC,
            workspace_id=wid,
            element_id=eid,
            views=["iso"],
            width=800,
            height=600,
        )

    assert len(rendered) == 1
    rv = rendered[0]
    assert rv.view == "iso"
    assert rv.image_id.startswith("img_")
    assert rv.width == 800 and rv.height == 600
    png = get_image(rv.image_id)
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    img = Image.open(io.BytesIO(png))
    assert img.size == (800, 600)
    # Must have real geometry, not a blank viewport. If max red channel is 0,
    # we picked an empty Part Studio or Onshape returned a transparent render.
    extrema = img.convert("RGBA").getextrema()
    assert extrema[0][1] > 0, f"render appears blank: extrema={extrema}"


@pytest.mark.asyncio
async def test_render_multiple_views_in_parallel_and_crop():
    ak = os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY", "")
    sk = os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET", "")
    creds = OnshapeCredentials(access_key=ak, secret_key=sk)
    async with OnshapeClient(creds) as client:
        wid, eid = await _get_workspace_and_element(client)
        svm = ShadedViewManager(client)
        rendered = await svm.render_part_studio_views(
            document_id=SMOKE_DOC,
            workspace_id=wid,
            element_id=eid,
            views=["iso", "top", "front", "right"],
            width=600,
            height=400,
        )

    assert len(rendered) == 4
    assert [r.view for r in rendered] == ["iso", "top", "front", "right"]
    # All image_ids distinct (different viewMatrices should produce different
    # pixels and therefore different sha256s).
    ids = {r.image_id for r in rendered}
    assert len(ids) == 4

    # Crop the center quarter of the iso view.
    iso = next(r for r in rendered if r.view == "iso")
    cropped = crop_cached_image(iso.image_id, 0.25, 0.25, 0.75, 0.75)
    assert cropped.width == 300 and cropped.height == 200
    assert cropped.image_id != iso.image_id
    # Crop is in the cache and has lineage metadata.
    all_ids = {e["image_id"] for e in list_cached_image_ids()}
    assert cropped.image_id in all_ids


def test_crop_rejects_invalid_bbox():
    # Seed a tiny image manually so this test doesn't need Onshape creds.
    from onshape_mcp.api.rendering import _put_image

    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color="white").save(buf, format="PNG")
    img_id = _put_image(buf.getvalue(), meta={"view": "synthetic", "width": 100, "height": 100})
    with pytest.raises(ValueError):
        crop_cached_image(img_id, 0.5, 0.5, 0.5, 0.5)
    with pytest.raises(ValueError):
        crop_cached_image(img_id, 0.8, 0.2, 0.2, 0.8)
