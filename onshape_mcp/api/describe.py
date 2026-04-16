"""Combined structured + visual snapshot of a Part Studio.

Why this exists: Claude's spatial reasoning is weak but its text reasoning is
strong; its image perception is good but unreliable for "what's missing" vibe
checks. The right representation for Claude is BOTH:

- A structured text block: feature tree with statuses, body topology summary,
  sketch geometry, key measurements, bounding box. Claude reasons over this
  natively, no spatial inference needed.
- A multi-view image bundle: iso + top + front + right so Claude can catch
  visual regressions ("wait, where's the boss?"). Image_ids are cached so
  Claude can crop any suspicious region via crop_image.

This is the single tool to call after every non-trivial mutation. Instead of
manually chaining render + list_entities + get_features + get_mass_properties,
one describe_part_studio returns the whole design state in one shot.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger

from .client import OnshapeClient
from .entities import EntityManager, _classify_edge, _classify_face, _classify_vertex
from .featurescript import FeatureScriptManager
from .measurements import MeasurementManager
from .partstudio import PartStudioManager
from .rendering import RenderedView, ShadedViewManager


@dataclass
class PartStudioSnapshot:
    structured_text: str
    views: List[RenderedView]
    raw: Dict[str, Any] = field(default_factory=dict)


def _fmt_mm(x: Optional[float]) -> str:
    if x is None:
        return "?"
    return f"{x*1000:.2f} mm"


def _fmt_vec_mm(v: Optional[List[float]]) -> str:
    if v is None:
        return "?"
    return f"({v[0]*1000:.1f}, {v[1]*1000:.1f}, {v[2]*1000:.1f}) mm"


def _feature_tree_text(features_raw: Dict[str, Any]) -> str:
    feats = features_raw.get("features", []) or []
    states = features_raw.get("featureStates", {}) or {}
    lines = [f"FEATURE TREE ({len(feats)} features):"]
    for i, f in enumerate(feats):
        fid = f.get("featureId") or ""
        name = f.get("name", "?")
        ftype = f.get("featureType") or f.get("btType", "?")
        st = states.get(fid, {})
        status = st.get("featureStatus", "?")
        suppressed = " [suppressed]" if f.get("suppressed") else ""
        lines.append(f"  {i+1:2d}. [{status:5s}] {name:30s} ({ftype}) id={fid}{suppressed}")
    return "\n".join(lines)


def _body_topology_text(entities_out: Dict[str, Any]) -> str:
    bodies = entities_out.get("bodies") or []
    if not bodies:
        return "BODIES: none"
    lines = [f"BODIES ({len(bodies)}):"]
    for b in bodies:
        faces = b.get("faces") or []
        edges = b.get("edges") or []
        by_face_type: Dict[str, int] = {}
        for f in faces:
            by_face_type[f.get("type", "?")] = by_face_type.get(f.get("type", "?"), 0) + 1
        face_breakdown = ", ".join(f"{n} {t.lower()}" for t, n in sorted(by_face_type.items()))
        lines.append(
            f"  body[{b['body_index']}] id={b['body_id']} type={b['body_type']} "
            f"faces={len(faces)} ({face_breakdown}) edges={len(edges)}"
        )
        # Summarize interesting faces: every non-planar + every planar face
        # that's >10% of total planar area (the "big" ones Claude will want
        # to pick for sketches).
        for f in faces:
            if f.get("type") == "PLANE":
                lines.append(f"    FACE {f['id']}: {f['description']}")
            else:
                lines.append(f"    FACE {f['id']}: {f['description']}")
    return "\n".join(lines)


def _bbox_text(bbox: Optional[Dict[str, Any]]) -> str:
    if not bbox or "minCorner" not in bbox:
        return "BOUNDING BOX: unknown"
    mn = bbox["minCorner"]
    mx = bbox["maxCorner"]
    dx = (mx["x"] - mn["x"]) * 1000
    dy = (mx["y"] - mn["y"]) * 1000
    dz = (mx["z"] - mn["z"]) * 1000
    return (
        f"BOUNDING BOX: {dx:.2f} x {dy:.2f} x {dz:.2f} mm\n"
        f"  min=({mn['x']*1000:.2f}, {mn['y']*1000:.2f}, {mn['z']*1000:.2f}) mm\n"
        f"  max=({mx['x']*1000:.2f}, {mx['y']*1000:.2f}, {mx['z']*1000:.2f}) mm"
    )


def _mass_props_text(mp: Dict[str, Any]) -> str:
    bodies = mp.get("bodies") or {}
    if not bodies:
        return "MASS PROPERTIES: none"
    lines = ["MASS PROPERTIES:"]
    for bid, bdata in bodies.items():
        vol = bdata.get("volume") or [0, 0, 0]
        com = bdata.get("centroid") or [0, 0, 0, 0, 0, 0]  # pairs of [min,max] per axis
        vol_mm3 = vol[1] * 1e9 if len(vol) >= 2 else 0
        com_text = ""
        if isinstance(com, list) and len(com) >= 3:
            # Onshape returns [x_min, x_max, y_min, y_max, z_min, z_max] sometimes,
            # or [[x_min, x_mean, x_max], ...]. Normalize via mean.
            try:
                xs = com[:2] if len(com) <= 6 else com[0]
                com_txt = f"centroid≈({_fmt_mm((com[0]+com[1])/2) if len(com) >= 2 else '?'}, ...)"
            except Exception:
                com_txt = ""
            com_text = com_txt
        lines.append(f"  body {bid}: volume={vol_mm3:.1f} mm^3 {com_text}")
    return "\n".join(lines)


class DescribeManager:
    """One-shot snapshot of a Part Studio's design state for Claude's context.

    Returns a `PartStudioSnapshot` with both structured text and cached
    multi-view PNGs. The same image cache backs `crop_image`, so Claude can
    zoom into any returned view.
    """

    def __init__(
        self,
        client: OnshapeClient,
        *,
        entities: Optional[EntityManager] = None,
        renderer: Optional[ShadedViewManager] = None,
        measurements: Optional[MeasurementManager] = None,
        featurescript: Optional[FeatureScriptManager] = None,
        partstudio: Optional[PartStudioManager] = None,
    ):
        self.client = client
        self.entities = entities or EntityManager(client)
        self.renderer = renderer or ShadedViewManager(client)
        self.measurements = measurements or MeasurementManager(client)
        self.featurescript = featurescript or FeatureScriptManager(client)
        self.partstudio = partstudio or PartStudioManager(client)

    async def describe_part_studio(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        *,
        views: Optional[List[str]] = None,
        render_width: int = 1200,
        render_height: int = 800,
    ) -> PartStudioSnapshot:
        """Snapshot the current design state.

        Fires all the independent reads in parallel (bodydetails, features,
        bbox, massproperties, multi-view render), then assembles both
        representations. ~1-2s total even for complex parts.
        """
        views = list(views) if views else ["iso", "top", "front", "right"]

        features_task = asyncio.create_task(
            self.partstudio.get_features(document_id, workspace_id, element_id)
        )
        entities_task = asyncio.create_task(
            self.entities.list_entities(document_id, workspace_id, element_id)
        )
        bbox_task = asyncio.create_task(
            self.featurescript.get_bounding_box(document_id, workspace_id, element_id)
        )
        mass_task = asyncio.create_task(
            self._mass_props_safe(document_id, workspace_id, element_id)
        )
        render_task = asyncio.create_task(
            self.renderer.render_part_studio_views(
                document_id, workspace_id, element_id,
                views=views, width=render_width, height=render_height,
            )
        )

        features_raw, entities_out, bbox_raw, mass_raw, rendered = await asyncio.gather(
            features_task, entities_task, bbox_task, mass_task, render_task,
            return_exceptions=True,
        )

        def _safe(val, label):
            if isinstance(val, Exception):
                logger.warning(f"describe: {label} failed: {val}")
                return None
            return val

        features_raw = _safe(features_raw, "features") or {}
        entities_out = _safe(entities_out, "entities") or {"bodies": []}
        bbox_raw = _safe(bbox_raw, "bbox") or {}
        mass_raw = _safe(mass_raw, "mass_properties") or {}
        rendered = _safe(rendered, "render") or []

        # Pull bbox out of the FS evBox3d response; it's nested under "result".
        bbox = None
        if bbox_raw:
            result = bbox_raw.get("result") or {}
            msg = result.get("message") if isinstance(result, dict) else None
            if msg and msg.get("value"):
                vals = msg["value"]
                # FS returns value as a dict with "minCorner" and "maxCorner".
                mc = _extract_fs_vector(vals.get("minCorner"))
                xc = _extract_fs_vector(vals.get("maxCorner"))
                if mc and xc:
                    bbox = {"minCorner": mc, "maxCorner": xc}

        sections = [
            _feature_tree_text(features_raw),
            _body_topology_text(entities_out),
            _bbox_text(bbox),
            _mass_props_text(mass_raw),
            "VIEWS RENDERED:",
            *[f"  {r.view}: image_id={r.image_id} ({r.width}x{r.height}, {r.bytes}B)" for r in rendered],
        ]
        structured_text = "\n\n".join(sections)

        return PartStudioSnapshot(
            structured_text=structured_text,
            views=rendered,
            raw={
                "features": features_raw,
                "entities": entities_out,
                "bbox": bbox,
                "mass_properties": mass_raw,
            },
        )

    async def _mass_props_safe(self, did: str, wid: str, eid: str) -> Dict[str, Any]:
        try:
            return await self.measurements.mass_properties_part_studio(did, wid, eid)
        except Exception as e:
            logger.warning(f"mass_properties failed (likely empty PS): {e}")
            return {}


def _extract_fs_vector(fs_val: Optional[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    """Extract {x,y,z} meters from an FS-serialized Vector3d."""
    if not fs_val:
        return None
    v = fs_val.get("value") if isinstance(fs_val, dict) else None
    if isinstance(v, list) and len(v) >= 3:
        return {
            "x": _fs_num(v[0]),
            "y": _fs_num(v[1]),
            "z": _fs_num(v[2]),
        }
    return None


def _fs_num(component: Any) -> float:
    """Unwrap a single FS value {"value": {"value": number}}."""
    if isinstance(component, dict):
        inner = component.get("value")
        if isinstance(inner, dict):
            return float(inner.get("value", 0))
        if isinstance(inner, (int, float)):
            return float(inner)
    if isinstance(component, (int, float)):
        return float(component)
    return 0.0
