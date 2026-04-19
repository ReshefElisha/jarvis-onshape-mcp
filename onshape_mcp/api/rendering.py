"""Shaded-view rendering + in-process image cache + crop helper.

Why this exists: Claude Opus 4.7 can see images. Onshape exposes a /shadedviews
REST endpoint that returns base64 PNGs for part studios and assemblies. Without
this, every tool returns JSON and Claude is blind to its own CAD output.

Anthropic's "with tools" CharXiv benchmark result (84.7% -> 91.0%) is delivered
almost entirely by a single image crop tool. We replicate that pattern here:
render_views produces images, crop_image zooms into regions of interest.

See scratchpad/probe-patch-and-shadedviews.md for the API probe that confirmed
parameters and response shape.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from loguru import logger
from PIL import Image

from .client import OnshapeClient


# Onshape /shadedviews accepts these named view strings in the viewMatrix
# parameter. Confirmed via live probe 2026-04-16.
NAMED_VIEWS = {
    "iso": "isometric",
    "isometric": "isometric",
    "front": "front",
    "back": "back",
    "top": "top",
    "bottom": "bottom",
    "left": "left",
    "right": "right",
}

DEFAULT_VIEWS = ("iso", "top", "front", "right")


ViewName = Literal["iso", "isometric", "front", "back", "top", "bottom", "left", "right"]


# Process-scoped image cache. image_id -> PNG bytes.
# Keyed by sha256 of content so identical renders dedupe naturally and the
# crop_image tool can find what render_views just produced.
_IMAGE_CACHE: Dict[str, bytes] = {}
_IMAGE_META: Dict[str, Dict[str, Any]] = {}


def _put_image(png_bytes: bytes, meta: Dict[str, Any]) -> str:
    """Insert a PNG into the cache and return a stable image_id."""
    image_id = "img_" + hashlib.sha256(png_bytes).hexdigest()[:16]
    _IMAGE_CACHE[image_id] = png_bytes
    _IMAGE_META[image_id] = meta
    return image_id


def get_image(image_id: str) -> bytes:
    """Return cached PNG bytes or raise KeyError."""
    return _IMAGE_CACHE[image_id]


def get_image_meta(image_id: str) -> Dict[str, Any]:
    return _IMAGE_META.get(image_id, {})


def list_cached_image_ids() -> List[Dict[str, Any]]:
    """Return a summary of every image currently in cache."""
    return [
        {
            "image_id": img_id,
            **_IMAGE_META.get(img_id, {}),
            "bytes": len(_IMAGE_CACHE[img_id]),
        }
        for img_id in _IMAGE_CACHE
    ]


@dataclass
class RenderedView:
    view: str
    image_id: str
    width: int
    height: int
    bytes: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "view": self.view,
            "image_id": self.image_id,
            "width": self.width,
            "height": self.height,
            "bytes": self.bytes,
        }


class ShadedViewManager:
    """Wraps Onshape /shadedviews for part studios and assemblies.

    Usage:
        svm = ShadedViewManager(client)
        rendered = await svm.render_part_studio_views(did, wid, eid,
            views=["iso", "top", "front"], width=1200, height=800)
        # rendered is a list[RenderedView]; PNGs live in the module cache.
    """

    def __init__(self, client: OnshapeClient):
        self.client = client

    async def render_part_studio_views(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        views: List[str] = None,
        width: int = 1200,
        height: int = 800,
        pixel_size: float = 0.0,
        edges: bool = True,
    ) -> List[RenderedView]:
        """Render one or more views of a Part Studio in parallel.

        Args:
            views: list of named views ("iso", "top", "front", "back", "left",
                "right", "bottom") or raw comma-separated 12-float matrices.
                Defaults to ["iso", "top", "front", "right"].
            width/height: output pixel dimensions. 1200x800 returns in ~500ms
                per view. Opus 4.7 accepts up to 2576px long-edge natively.
            pixel_size: 0.0 lets Onshape auto-fit.
            edges: include silhouette/feature edges in the render.
        """
        views = list(views) if views else list(DEFAULT_VIEWS)
        base_path = (
            f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/shadedviews"
        )
        return await self._render_many(
            base_path=base_path,
            views=views,
            width=width,
            height=height,
            pixel_size=pixel_size,
            edges=edges,
            source={"kind": "partstudio", "did": document_id, "wid": workspace_id, "eid": element_id},
        )

    async def render_assembly_views(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        views: List[str] = None,
        width: int = 1200,
        height: int = 800,
        pixel_size: float = 0.0,
        edges: bool = True,
    ) -> List[RenderedView]:
        views = list(views) if views else list(DEFAULT_VIEWS)
        base_path = (
            f"/api/v9/assemblies/d/{document_id}/w/{workspace_id}/e/{element_id}/shadedviews"
        )
        return await self._render_many(
            base_path=base_path,
            views=views,
            width=width,
            height=height,
            pixel_size=pixel_size,
            edges=edges,
            source={"kind": "assembly", "did": document_id, "wid": workspace_id, "eid": element_id},
        )

    async def _render_many(
        self,
        *,
        base_path: str,
        views: List[str],
        width: int,
        height: int,
        pixel_size: float,
        edges: bool,
        source: Dict[str, Any],
    ) -> List[RenderedView]:
        tasks = [
            self._render_one(
                base_path=base_path,
                view=view,
                width=width,
                height=height,
                pixel_size=pixel_size,
                edges=edges,
                source=source,
            )
            for view in views
        ]
        return await asyncio.gather(*tasks)

    async def _render_one(
        self,
        *,
        base_path: str,
        view: str,
        width: int,
        height: int,
        pixel_size: float,
        edges: bool,
        source: Dict[str, Any],
    ) -> RenderedView:
        view_matrix = NAMED_VIEWS.get(view.lower(), view)
        params = {
            "viewMatrix": view_matrix,
            "outputWidth": width,
            "outputHeight": height,
            "pixelSize": pixel_size,
            "edges": "true" if edges else "false",
        }
        logger.debug(f"render {view}: GET {base_path} {params}")
        resp = await self.client.get(base_path, params=params)
        images = resp.get("images") or []
        if not images:
            raise RuntimeError(
                f"/shadedviews returned no images for view={view}; response keys={list(resp.keys())}"
            )
        png_bytes = base64.b64decode(images[0])
        image_id = _put_image(
            png_bytes,
            meta={"view": view, "source": source, "width": width, "height": height},
        )
        return RenderedView(
            view=view, image_id=image_id, width=width, height=height, bytes=len(png_bytes)
        )


def load_local_image(image_path: str, max_edge: int = 1568) -> RenderedView:
    """Read a PNG from disk, cap long edge at `max_edge`, push into cache.

    Lets the agent pass a filesystem reference image (from the brief) to
    `crop_image` for dimension-callout zoom-ins. Downsamples to `max_edge`
    on the long side — Claude's many-image API rejects >2000px in any
    dimension, so we stay comfortably under. Subsequent `crop_image` calls
    operate on the (possibly-downsampled) cached copy.
    """
    from pathlib import Path
    p = Path(image_path)
    if not p.exists():
        raise FileNotFoundError(f"load_local_image: {image_path}")
    img = Image.open(p).convert("RGB")
    if max(img.width, img.height) > max_edge:
        scale = max_edge / max(img.width, img.height)
        img = img.resize((int(img.width * scale), int(img.height * scale)),
                         Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    image_id = _put_image(
        png_bytes,
        meta={"source": {"kind": "local", "path": str(p.resolve())},
              "width": img.width, "height": img.height},
    )
    return RenderedView(
        view=f"local:{p.name}",
        image_id=image_id,
        width=img.width,
        height=img.height,
        bytes=len(png_bytes),
    )


def compose_reference_comparison(
    reference_image_path: str,
    rendered_views: List[RenderedView],
    label_ref: str = "REFERENCE",
    label_agent: str = "YOUR BUILD",
    agent_bbox_mm: Optional[tuple[float, float, float]] = None,
) -> RenderedView:
    """Compose a side-by-side comparison: reference image on top, a row of agent
    renders below. Caches the composite and returns a RenderedView.

    The reference image is typically a multi-view engineering sheet (iso +
    front + top + right) from the brief. Placing it directly above the
    agent's fresh renders makes the diff obvious in a single ImageContent
    block — the agent can see at a glance where features are missing or
    misplaced.

    Image scaling: the reference is resized to match the total width of the
    agent-renders row (preserving aspect), so both rows share the same
    horizontal extent.

    If `agent_bbox_mm` is supplied, it's stamped into the agent-row label so
    the agent can numerically cross-check its build's dimensions against the
    drawing's explicit dimensions. Without this annotation the composite
    hides scale mismatch — a 800 mm reference and a 200 mm agent render
    look identical pixel-wise.
    """
    from pathlib import Path
    from PIL import ImageDraw, ImageFont

    ref_path = Path(reference_image_path)
    if not ref_path.exists():
        raise FileNotFoundError(f"reference image not found: {reference_image_path}")

    ref_img = Image.open(ref_path).convert("RGB")
    if not rendered_views:
        raise ValueError("compose_reference_comparison: need at least 1 rendered view")

    # Agent row: concatenate rendered views horizontally at their native height.
    agent_imgs = [Image.open(io.BytesIO(get_image(r.image_id))).convert("RGB")
                  for r in rendered_views]
    row_h = max(img.height for img in agent_imgs)
    # Normalize each agent view to row_h keeping aspect ratio.
    agent_imgs = [img if img.height == row_h
                  else img.resize((int(img.width * row_h / img.height), row_h), Image.LANCZOS)
                  for img in agent_imgs]
    agent_row_w = sum(img.width for img in agent_imgs)

    # Reference row: scale to agent_row_w.
    ref_w = agent_row_w
    ref_h = int(ref_img.height * ref_w / ref_img.width)
    ref_img = ref_img.resize((ref_w, ref_h), Image.LANCZOS)

    # Compose: labels strip + ref + labels strip + agent row.
    label_h = 40
    total_h = label_h + ref_h + label_h + row_h
    composite = Image.new("RGB", (agent_row_w, total_h), "white")
    draw = ImageDraw.Draw(composite)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
    except Exception:
        font = ImageFont.load_default()

    # Reference label: always flag that pixel size != world size.
    draw.rectangle([(0, 0), (agent_row_w, label_h)], fill="#333333")
    draw.text((16, 6),
              f"{label_ref} — dims from drawing callouts (NOT pixel size)",
              fill="white", font=font)
    composite.paste(ref_img, (0, label_h))

    agent_label_y = label_h + ref_h
    draw.rectangle([(0, agent_label_y), (agent_row_w, agent_label_y + label_h)],
                   fill="#333333")
    views_str = ", ".join(r.view for r in rendered_views)
    agent_label = f"{label_agent}  ({views_str})"
    if agent_bbox_mm is not None:
        dx, dy, dz = agent_bbox_mm
        agent_label += f"  |  bbox {dx:.1f} × {dy:.1f} × {dz:.1f} mm"
    draw.text((16, agent_label_y + 6), agent_label, fill="white", font=font)

    x = 0
    y = agent_label_y + label_h
    for img in agent_imgs:
        composite.paste(img, (x, y))
        x += img.width

    # Cap at 1568px long edge — Claude's many-image API rejects >2000 per
    # dimension, and each compare_to_reference call stacks an ImageContent
    # block in the conversation.
    max_edge = 1568
    if max(composite.width, composite.height) > max_edge:
        scale = max_edge / max(composite.width, composite.height)
        composite = composite.resize(
            (int(composite.width * scale), int(composite.height * scale)),
            Image.LANCZOS,
        )

    buf = io.BytesIO()
    composite.save(buf, format="PNG")
    out_bytes = buf.getvalue()
    new_id = _put_image(
        out_bytes,
        meta={
            "kind": "comparison",
            "reference_path": str(ref_path),
            "agent_views": [r.view for r in rendered_views],
            "agent_image_ids": [r.image_id for r in rendered_views],
            "width": composite.width,
            "height": composite.height,
        },
    )
    return RenderedView(
        view="reference_vs_build",
        image_id=new_id,
        width=composite.width,
        height=composite.height,
        bytes=len(out_bytes),
    )


def crop_cached_image(
    image_id: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> RenderedView:
    """Crop a cached image by normalized 0..1 bounding box (Anthropic cookbook
    schema). Returns a new RenderedView whose PNG is also placed in the cache.

    Coordinates: (0, 0) is top-left, (1, 1) is bottom-right. Values outside
    [0, 1] are clamped. x2 must be > x1 and y2 > y1.
    """
    source_bytes = get_image(image_id)
    img = Image.open(io.BytesIO(source_bytes))
    W, H = img.size
    x1c = max(0.0, min(1.0, float(x1)))
    y1c = max(0.0, min(1.0, float(y1)))
    x2c = max(0.0, min(1.0, float(x2)))
    y2c = max(0.0, min(1.0, float(y2)))
    if x2c <= x1c or y2c <= y1c:
        raise ValueError(
            f"invalid crop bbox after clamp: ({x1c},{y1c})-({x2c},{y2c})"
        )
    left = int(round(x1c * W))
    top = int(round(y1c * H))
    right = int(round(x2c * W))
    bottom = int(round(y2c * H))
    cropped = img.crop((left, top, right, bottom))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG")
    out_bytes = buf.getvalue()
    source_meta = get_image_meta(image_id)
    new_id = _put_image(
        out_bytes,
        meta={
            **source_meta,
            "crop_of": image_id,
            "crop_bbox": [x1c, y1c, x2c, y2c],
            "crop_px": [left, top, right, bottom],
            "width": cropped.width,
            "height": cropped.height,
        },
    )
    return RenderedView(
        view=f"crop_of:{image_id}",
        image_id=new_id,
        width=cropped.width,
        height=cropped.height,
        bytes=len(out_bytes),
    )
