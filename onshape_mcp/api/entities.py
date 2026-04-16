"""Entity enumeration for Part Studios.

The single unblock for every tool that needs to pick geometry. Starter's
fillet/chamfer/boolean all require deterministic IDs, but no tool gives Claude
a pickable list. Without this, Claude can only build on standard planes and
"sketch on top face of extrude1" is unreachable.

Strategy: hit /api/v9/partstudios/.../bodydetails (already exposes deterministic
ids for faces AND edges -- audit claim that edges were missing was wrong; the
raw blob just wasn't parsed for them). Enrich each entity with human-readable
type, geometric metadata, and a one-line description Claude can read to pick
the right one.

See scratchpad/starter-audit.md gap #2, and docs/SKETCH_PLANE_REFERENCE_GUIDE.md
for why `deterministicIds: ["JHO"]` + BTMIndividualQuery-138 is sufficient for
most downstream feature payloads.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from .client import OnshapeClient


def _vec(d: Optional[Dict[str, Any]]) -> Optional[List[float]]:
    if not d:
        return None
    return [d.get("x", 0.0), d.get("y", 0.0), d.get("z", 0.0)]


def _sub(a: List[float], b: List[float]) -> List[float]:
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _norm(v: List[float]) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _nearest_axis_label(v: Optional[List[float]]) -> Optional[str]:
    """Return +X / -X / +Y / -Y / +Z / -Z if v is close enough to an axis."""
    if v is None:
        return None
    n = _norm(v)
    if n < 1e-9:
        return None
    ux, uy, uz = v[0] / n, v[1] / n, v[2] / n
    for axis, comp, label_pos, label_neg in (
        ("x", ux, "+X", "-X"),
        ("y", uy, "+Y", "-Y"),
        ("z", uz, "+Z", "-Z"),
    ):
        if comp > 0.999:
            return label_pos
        if comp < -0.999:
            return label_neg
    return None


def _classify_face(face: Dict[str, Any]) -> Dict[str, Any]:
    """Extract human-friendly shape from a BTExportModelFace entry."""
    surface = face.get("surface") or {}
    stype = (surface.get("type") or "").upper() or "OTHER"
    origin = _vec(surface.get("origin"))
    normal = _vec(surface.get("normal"))
    radius = surface.get("radius")
    axis = None
    if stype in ("CYLINDER", "CONE", "TORUS"):
        axis = _vec(surface.get("axis"))

    normal_label = _nearest_axis_label(normal) if stype == "PLANE" else None

    desc_parts: List[str] = [stype.lower()]
    if normal_label:
        desc_parts.append(f"normal {normal_label}")
    if origin is not None:
        desc_parts.append(
            f"origin ({origin[0]*1000:.1f},{origin[1]*1000:.1f},{origin[2]*1000:.1f}) mm"
        )
    if radius is not None:
        desc_parts.append(f"radius {radius*1000:.2f} mm")

    return {
        "id": face.get("id"),
        "type": stype,
        "origin": origin,
        "normal": normal,
        "normal_axis": normal_label,
        "axis": axis,
        "radius": radius,
        "description": " / ".join(desc_parts),
    }


def _classify_edge(edge: Dict[str, Any]) -> Dict[str, Any]:
    """Extract human-friendly shape from a BTExportModelEdge entry."""
    geom = edge.get("geometry") or {}
    curve = edge.get("curve") or {}
    ctype = (curve.get("type") or "").upper() or "OTHER"
    start = _vec(geom.get("startPoint"))
    end = _vec(geom.get("endPoint"))
    mid = _vec(geom.get("midPoint"))
    radius = curve.get("radius")
    length: Optional[float] = None
    direction: Optional[List[float]] = None
    dir_label: Optional[str] = None
    if start is not None and end is not None:
        d = _sub(end, start)
        length = _norm(d)
        if length > 1e-9:
            direction = [d[0] / length, d[1] / length, d[2] / length]
            dir_label = _nearest_axis_label(direction)

    desc_parts: List[str] = [ctype.lower() if ctype else "edge"]
    if dir_label:
        desc_parts.append(f"along {dir_label}")
    if length is not None:
        desc_parts.append(f"length {length*1000:.2f} mm")
    if radius is not None:
        desc_parts.append(f"radius {radius*1000:.2f} mm")
    if mid is not None:
        desc_parts.append(
            f"mid ({mid[0]*1000:.1f},{mid[1]*1000:.1f},{mid[2]*1000:.1f}) mm"
        )

    return {
        "id": edge.get("id"),
        "type": ctype,
        "start": start,
        "end": end,
        "midpoint": mid,
        "length": length,
        "direction": direction,
        "direction_axis": dir_label,
        "radius": radius,
        "vertex_ids": edge.get("vertices") or [],
        "description": " / ".join(desc_parts),
    }


def _classify_vertex(vertex: Dict[str, Any]) -> Dict[str, Any]:
    pt = _vec(vertex.get("point"))
    parts = ["vertex"]
    if pt is not None:
        parts.append(f"at ({pt[0]*1000:.1f},{pt[1]*1000:.1f},{pt[2]*1000:.1f}) mm")
    return {
        "id": vertex.get("id"),
        "point": pt,
        "description": " / ".join(parts),
    }


class EntityManager:
    """Enumerate faces, edges, vertices, bodies with deterministic IDs.

    Claude calls this after every mutation before picking geometry for the
    next feature. IDs returned here are stable enough to drop into feature
    payloads as BTMIndividualQuery-138 deterministicIds.
    """

    def __init__(self, client: OnshapeClient):
        self.client = client

    async def list_entities(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        *,
        kinds: Optional[List[str]] = None,
        body_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return structured, enriched entity lists for all bodies in the PS.

        Args:
            kinds: subset of {"faces", "edges", "vertices"}. Default: all.
            body_index: 0-based index to limit to one body. Default: all bodies.

        Returns: {"bodies": [{"body_id", "body_type", "faces": [...], ...}], "summary": "..."}
        """
        wanted = set(kinds) if kinds else {"faces", "edges", "vertices"}
        path = (
            f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/bodydetails"
        )
        raw = await self.client.get(path)
        bodies_raw = raw.get("bodies") or []
        out_bodies: List[Dict[str, Any]] = []
        for idx, body in enumerate(bodies_raw):
            if body_index is not None and idx != body_index:
                continue
            entry: Dict[str, Any] = {
                "body_index": idx,
                "body_id": body.get("id"),
                "body_type": body.get("type"),
            }
            if "faces" in wanted:
                entry["faces"] = [_classify_face(f) for f in (body.get("faces") or [])]
            if "edges" in wanted:
                entry["edges"] = [_classify_edge(e) for e in (body.get("edges") or [])]
            if "vertices" in wanted:
                entry["vertices"] = [
                    _classify_vertex(v) for v in (body.get("vertices") or [])
                ]
            out_bodies.append(entry)

        # Build a compact summary for Claude's scratchpad.
        summary_lines: List[str] = []
        for b in out_bodies:
            fn = len(b.get("faces", [])) if "faces" in wanted else "-"
            en = len(b.get("edges", [])) if "edges" in wanted else "-"
            vn = len(b.get("vertices", [])) if "vertices" in wanted else "-"
            summary_lines.append(
                f"body[{b['body_index']}] id={b['body_id']} type={b['body_type']} "
                f"faces={fn} edges={en} vertices={vn}"
            )
        return {
            "bodies": out_bodies,
            "summary": "\n".join(summary_lines) if summary_lines else "no bodies",
        }
