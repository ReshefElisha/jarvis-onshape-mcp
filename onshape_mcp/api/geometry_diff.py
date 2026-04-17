"""Geometric diff between two bodydetails snapshots — "git diff for CAD".

Per vup4gnen's 2026-04-17 meta-feedback: Claude has strong reflexes for
`git diff` (what changed?), `grep` (what's the shape?), and function
abstraction, but no CAD equivalents. Response-layer tooling should match
the SHAPE of the code reflexes so they fire here too.

`changes:` embedded in a feature-apply response answers the git-diff
question: after this feature, what's different? Volume delta, faces
added/removed, edges added/removed, bbox before/after.

Deliberately minimal. An earlier draft had anomaly detection (tiny-face,
short-edge with magic thresholds) + `_approx_face_area` using a phantom
`loops` field the API doesn't return. Both gone — anomaly predicates
belong in user space per the cookbook pattern; face-area approximation
from bbox-extent was systematically wrong.

Two round-trips per call (before + after bodydetails + massproperties).
Opt-in via `apply_feature_and_check(..., track_changes=True)`.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


def _vec(d: Optional[Dict[str, Any]]) -> Optional[List[float]]:
    if not d:
        return None
    return [d.get("x", 0.0), d.get("y", 0.0), d.get("z", 0.0)]


def _face_signature(face: Dict[str, Any]) -> Tuple:
    """Identity tuple for a face — id + surface type + rounded origin.

    Not immune to id-drift across regens, but good enough for the common
    case (feature appended, prior faces keep ids). A perfect identity
    would require walking FeatureScript query history; we can add that
    when id-drift shows up as a real failure.
    """
    surface = face.get("surface") or {}
    origin = _vec(surface.get("origin"))
    origin_key = tuple(round(c, 6) for c in origin) if origin else None
    return (face.get("id"), surface.get("type"), origin_key)


def _edge_signature(edge: Dict[str, Any]) -> Tuple:
    geom = edge.get("geometry") or {}
    curve = edge.get("curve") or {}
    start = _vec(geom.get("startPoint"))
    end = _vec(geom.get("endPoint"))
    key_start = tuple(round(c, 6) for c in start) if start else None
    key_end = tuple(round(c, 6) for c in end) if end else None
    return (edge.get("id"), curve.get("type"), key_start, key_end)


def _face_map(bodies: List[Dict[str, Any]]) -> Dict[Any, Dict[str, Any]]:
    out: Dict[Any, Dict[str, Any]] = {}
    for body in bodies:
        for f in body.get("faces") or []:
            out[_face_signature(f)] = f
    return out


def _edge_map(bodies: List[Dict[str, Any]]) -> Dict[Any, Dict[str, Any]]:
    out: Dict[Any, Dict[str, Any]] = {}
    for body in bodies:
        for e in body.get("edges") or []:
            out[_edge_signature(e)] = e
    return out


def _edge_length_m(edge: Dict[str, Any]) -> Optional[float]:
    geom = edge.get("geometry") or {}
    start = _vec(geom.get("startPoint"))
    end = _vec(geom.get("endPoint"))
    if start is None or end is None:
        return None
    dx, dy, dz = end[0] - start[0], end[1] - start[1], end[2] - start[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _nearest_axis_label(v: Optional[List[float]]) -> Optional[str]:
    if v is None:
        return None
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if n < 1e-9:
        return None
    ux, uy, uz = v[0] / n, v[1] / n, v[2] / n
    for comp, label_pos, label_neg in (
        (ux, "+X", "-X"),
        (uy, "+Y", "-Y"),
        (uz, "+Z", "-Z"),
    ):
        if comp > 0.999:
            return label_pos
        if comp < -0.999:
            return label_neg
    return None


def _face_brief(face: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal face description for diff output. Deliberately does NOT call
    entities._classify_face — that function wants face-frame data we don't
    have at diff time, and costs a lot for the one-line summary we want.
    """
    surface = face.get("surface") or {}
    stype = (surface.get("type") or "").upper() or "OTHER"
    origin = _vec(surface.get("origin"))
    normal = _vec(surface.get("normal"))
    radius = surface.get("radius")

    parts: List[str] = [stype.lower()]
    if stype == "PLANE":
        lbl = _nearest_axis_label(normal)
        if lbl:
            parts.append(f"normal {lbl}")
    if origin is not None:
        parts.append(
            f"origin ({origin[0] * 1e3:.1f},{origin[1] * 1e3:.1f},{origin[2] * 1e3:.1f}) mm"
        )
    if radius is not None:
        parts.append(f"radius {radius * 1e3:.2f} mm")

    return {
        "id": face.get("id"),
        "type": stype,
        "description": " / ".join(parts),
    }


def _edge_brief(edge: Dict[str, Any]) -> Dict[str, Any]:
    curve = edge.get("curve") or {}
    ctype = (curve.get("type") or "").upper()
    length = _edge_length_m(edge)
    entry = {"id": edge.get("id"), "type": ctype}
    if length is not None:
        entry["length_mm"] = length * 1e3
    return entry


def _body_bbox(bodies: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    """Union bbox over all bodies, sampled from vertex coordinates.

    Earlier draft sampled face-surface.origin + edge endpoints. Plane
    origins sit inside the body, cylinder origins sit on the axis —
    those give a bbox strictly smaller than reality. Vertices are the
    ground truth; they're the only points guaranteed to be on the body
    boundary.
    """
    xs: List[float] = []
    ys: List[float] = []
    zs: List[float] = []
    for body in bodies:
        for v in body.get("vertices") or []:
            p = _vec(v.get("point"))
            if p:
                xs.append(p[0]); ys.append(p[1]); zs.append(p[2])
        # Fallback: if a body has no vertices (degenerate / all-curves),
        # use edge endpoints so we at least have something.
        if not body.get("vertices"):
            for e in body.get("edges") or []:
                geom = e.get("geometry") or {}
                for k in ("startPoint", "endPoint"):
                    p = _vec(geom.get(k))
                    if p:
                        xs.append(p[0]); ys.append(p[1]); zs.append(p[2])
    if not xs:
        return None
    return {
        "x_min_mm": min(xs) * 1e3, "x_max_mm": max(xs) * 1e3,
        "y_min_mm": min(ys) * 1e3, "y_max_mm": max(ys) * 1e3,
        "z_min_mm": min(zs) * 1e3, "z_max_mm": max(zs) * 1e3,
    }


def _aggregate_volume_mm3(mass_props: Optional[Dict[str, Any]]) -> Optional[float]:
    """Sum per-body volume (mean) from a /massproperties response.

    Onshape returns per-body entries under `bodies` — for a Part Studio
    with one body the key is `"-all-"` with the aggregate. Each body's
    `volume` is `[mean, min_err, max_err]` in m³. We take [0] as mean.
    """
    if not mass_props:
        return None
    bodies = mass_props.get("bodies") or {}
    if not bodies:
        return None
    # Prefer "-all-" if present; otherwise sum individual bodies.
    if "-all-" in bodies:
        vol = bodies["-all-"].get("volume") or []
        if isinstance(vol, list) and vol:
            return float(vol[0]) * 1e9
        return None
    total = 0.0
    for bdata in bodies.values():
        vol = bdata.get("volume") or []
        if isinstance(vol, list) and vol:
            total += float(vol[0]) * 1e9
    return total


def compute_diff(
    bodies_before: List[Dict[str, Any]],
    bodies_after: List[Dict[str, Any]],
    *,
    mass_before: Optional[Dict[str, Any]] = None,
    mass_after: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a structured diff summarizing what changed.

    Keys:
      - body_count_before / body_count_after
      - volume_before_mm3 / volume_after_mm3 / volume_delta_mm3  (if mass given)
      - faces_added / faces_removed: [{id, type, description}]
      - edges_added / edges_removed: [{id, type, length_mm?}]
      - bbox_before_mm / bbox_after_mm  (x_min_mm..z_max_mm; absent if no bodies)
      - summary: one-line human-readable

    Deliberately NOT included:
      - bbox_delta. Extent-delta is a lie on translations; corner-delta
        duplicates before/after. Caller can compute if needed.
      - anomalies (tiny-face/short-edge). Those are predicates; per
        vup4gnen's feedback, predicates live in user space.
    """
    out: Dict[str, Any] = {
        "body_count_before": len(bodies_before),
        "body_count_after": len(bodies_after),
    }

    fb = _face_map(bodies_before)
    fa = _face_map(bodies_after)
    added = set(fa) - set(fb)
    removed = set(fb) - set(fa)
    out["faces_added"] = [_face_brief(fa[s]) for s in sorted(added, key=str)]
    out["faces_removed"] = [_face_brief(fb[s]) for s in sorted(removed, key=str)]

    eb = _edge_map(bodies_before)
    ea = _edge_map(bodies_after)
    e_added = set(ea) - set(eb)
    e_removed = set(eb) - set(ea)
    out["edges_added"] = [_edge_brief(ea[s]) for s in sorted(e_added, key=str)]
    out["edges_removed"] = [_edge_brief(eb[s]) for s in sorted(e_removed, key=str)]

    bb_before = _body_bbox(bodies_before)
    bb_after = _body_bbox(bodies_after)
    if bb_before:
        out["bbox_before_mm"] = bb_before
    if bb_after:
        out["bbox_after_mm"] = bb_after

    vb = _aggregate_volume_mm3(mass_before)
    va = _aggregate_volume_mm3(mass_after)
    if vb is not None:
        out["volume_before_mm3"] = vb
    if va is not None:
        out["volume_after_mm3"] = va
    if vb is not None and va is not None:
        out["volume_delta_mm3"] = va - vb

    parts: List[str] = []
    if "volume_delta_mm3" in out:
        d = out["volume_delta_mm3"]
        sign = "+" if d >= 0 else ""
        parts.append(f"volume {sign}{d:.1f} mm³")
    if out["faces_added"] or out["faces_removed"]:
        parts.append(f"faces +{len(out['faces_added'])}/-{len(out['faces_removed'])}")
    if out["edges_added"] or out["edges_removed"]:
        parts.append(f"edges +{len(out['edges_added'])}/-{len(out['edges_removed'])}")
    if out["body_count_before"] != out["body_count_after"]:
        parts.append(
            f"bodies {out['body_count_before']} → {out['body_count_after']}"
        )
    out["summary"] = "; ".join(parts) if parts else "no visible change"

    return out
