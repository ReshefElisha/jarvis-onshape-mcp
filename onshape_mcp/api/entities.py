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


def _classify_face(
    face: Dict[str, Any],
    face_frames: Optional[Dict[str, Dict[str, List[float]]]] = None,
) -> Dict[str, Any]:
    """Extract human-friendly shape from a BTExportModelFace entry.

    `face_frames` (face_id -> {"normal", "x", "y"}) carries the body-outward
    frame fetched via FeatureScript (`evFaceTangentPlane`). The bodydetails
    REST surface only exposes the plane's *defining* normal, which on a
    body's bottom face still reads as the plane's local +Z even though the
    body-outward direction is -Z. Picking by `outward_axis` instead of
    `normal_axis` resolves that ambiguity.

    For planar faces the FS probe also gives us the plane's in-plane U / V
    axes in world coordinates; we surface those as `sketch_x_world` /
    `sketch_y_world` so the caller knows how an `(x, y)` sketch coordinate
    on this face maps to world space. "Sketching on vertical side faces
    was guesswork" was a direct dogfood complaint this fixes.
    """
    surface = face.get("surface") or {}
    stype = (surface.get("type") or "").upper() or "OTHER"
    origin = _vec(surface.get("origin"))
    normal = _vec(surface.get("normal"))
    radius = surface.get("radius")
    axis = None
    if stype in ("CYLINDER", "CONE", "TORUS"):
        axis = _vec(surface.get("axis"))

    normal_label = _nearest_axis_label(normal) if stype == "PLANE" else None

    face_id = face.get("id") or ""
    frame = (face_frames or {}).get(face_id) if face_frames else None
    outward = frame.get("normal") if frame else None
    sketch_x = frame.get("x") if frame else None
    sketch_y = frame.get("y") if frame else None
    outward_label = _nearest_axis_label(outward) if outward is not None else None
    sketch_x_label = _nearest_axis_label(sketch_x) if sketch_x is not None else None
    sketch_y_label = _nearest_axis_label(sketch_y) if sketch_y is not None else None

    desc_parts: List[str] = [stype.lower()]
    # Prefer the outward-facing label in the description: it's what the LLM
    # caller actually wants to reason about ("the +Z face" should mean "the
    # face that faces +Z away from the body").
    if outward_label:
        desc_parts.append(f"outward {outward_label}")
    elif normal_label:
        desc_parts.append(f"normal {normal_label}")
    # Surface sketch-frame labels on planar faces. Only render when both
    # axes map cleanly to a world-axis (so we never lie about a face whose
    # U/V lands halfway between X and Y).
    if stype == "PLANE" and sketch_x_label and sketch_y_label:
        desc_parts.append(f"sketch-x={sketch_x_label} sketch-y={sketch_y_label}")
    if origin is not None:
        desc_parts.append(
            f"origin ({origin[0]*1000:.1f},{origin[1]*1000:.1f},{origin[2]*1000:.1f}) mm"
        )
    if radius is not None:
        desc_parts.append(f"radius {radius*1000:.2f} mm")

    return {
        "id": face_id,
        "type": stype,
        "origin": origin,
        "normal": normal,
        "normal_axis": normal_label,
        "outward_normal": outward,
        "outward_axis": outward_label,
        "sketch_x_world": sketch_x if stype == "PLANE" else None,
        "sketch_y_world": sketch_y if stype == "PLANE" else None,
        "sketch_x_axis": sketch_x_label if stype == "PLANE" else None,
        "sketch_y_axis": sketch_y_label if stype == "PLANE" else None,
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


def _in_range(value: Optional[float], rng: Optional[List[float]]) -> bool:
    """Inclusive range check. Returns False if value is None AND a range is set."""
    if rng is None:
        return True
    if value is None:
        return False
    lo, hi = rng[0], rng[1]
    return lo <= value <= hi


def _face_passes_filters(
    face: Dict[str, Any],
    *,
    geometry_type: Optional[str],
    outward_axis: Optional[str],
    at_z_mm: Optional[float],
    at_z_tol_mm: float,
    radius_range_mm: Optional[List[float]],
) -> bool:
    if geometry_type is not None and (face.get("type") or "").upper() != geometry_type:
        return False
    if outward_axis is not None:
        # Prefer outward_axis (body-outward), fall back to plane-defining
        # normal_axis when the FS probe missed this face.
        axis = face.get("outward_axis") or face.get("normal_axis")
        if axis != outward_axis:
            return False
    if at_z_mm is not None:
        origin = face.get("origin")
        if origin is None:
            return False
        # origin is in meters; convert to mm for comparison.
        z_mm = origin[2] * 1000.0
        if abs(z_mm - at_z_mm) > at_z_tol_mm:
            return False
    if radius_range_mm is not None:
        r = face.get("radius")
        r_mm = r * 1000.0 if r is not None else None
        if not _in_range(r_mm, radius_range_mm):
            return False
    return True


def _edge_passes_filters(
    edge: Dict[str, Any],
    *,
    geometry_type: Optional[str],
    at_z_mm: Optional[float],
    at_z_tol_mm: float,
    radius_range_mm: Optional[List[float]],
    length_range_mm: Optional[List[float]],
) -> bool:
    if geometry_type is not None and (edge.get("type") or "").upper() != geometry_type:
        return False
    if at_z_mm is not None:
        mid = edge.get("midpoint")
        if mid is None:
            return False
        z_mm = mid[2] * 1000.0
        if abs(z_mm - at_z_mm) > at_z_tol_mm:
            return False
    if radius_range_mm is not None:
        r = edge.get("radius")
        r_mm = r * 1000.0 if r is not None else None
        if not _in_range(r_mm, radius_range_mm):
            return False
    if length_range_mm is not None:
        length = edge.get("length")
        length_mm = length * 1000.0 if length is not None else None
        if not _in_range(length_mm, length_range_mm):
            return False
    return True


def _vertex_passes_filters(
    vertex: Dict[str, Any],
    *,
    at_z_mm: Optional[float],
    at_z_tol_mm: float,
) -> bool:
    if at_z_mm is not None:
        pt = vertex.get("point")
        if pt is None:
            return False
        z_mm = pt[2] * 1000.0
        if abs(z_mm - at_z_mm) > at_z_tol_mm:
            return False
    return True


_FACE_FRAMES_FS = """
function(context is Context, queries) {
    var out = {};
    var faces = evaluateQuery(context, qOwnedByBody(qAllNonMeshSolidBodies(), EntityType.FACE));
    for (var face in faces) {
        var faceId = transientQueriesToStrings(face);
        try {
            var plane = evFaceTangentPlane(context, {
                "face": face,
                "parameter": vector(0.5, 0.5)
            });
            // Plane struct carries origin/normal/x; Y axis is derived via
            // right-hand rule so the sketch frame is orthonormal.
            var yAxis = cross(plane.normal, plane.x);
            // Pack as a flat 9-element vector [nx, ny, nz, xx, xy, xz, yx, yy, yz]
            // so the response parser only has to handle one value-kind
            // (BTFSValueArray of numbers) per face.
            out[faceId] = [
                plane.normal[0], plane.normal[1], plane.normal[2],
                plane.x[0], plane.x[1], plane.x[2],
                yAxis[0], yAxis[1], yAxis[2]
            ];
        } catch (e) {
            // Non-evaluable faces (degenerate, parametrically odd) -- skip;
            // caller falls back to plane-defining normal_axis.
        }
    }
    return out;
}
""".strip()


def _parse_fs_frame_map(
    fs_response: Dict[str, Any],
) -> Dict[str, Dict[str, List[float]]]:
    """Pull face_id -> {normal, x, y} out of an FSValueMap response.

    Onshape returns FS map values as a list of `{key: {value: <id>}, value:
    {value: [{value: n}, ...]}}` entries under `result.value`. The FS script
    packs each face's frame as a flat 9-element array; we unpack here.
    Tolerant of unexpected shapes — anything malformed gets skipped so one
    bad face never blocks the rest.
    """
    out: Dict[str, Dict[str, List[float]]] = {}
    result = fs_response.get("result") or {}
    entries = result.get("value") if isinstance(result.get("value"), list) else []
    for ent in entries:
        key_obj = ent.get("key") if isinstance(ent, dict) else None
        face_id = (key_obj or {}).get("value") if isinstance(key_obj, dict) else None
        if not isinstance(face_id, str):
            continue
        val_obj = ent.get("value") if isinstance(ent, dict) else None
        comp_list = val_obj.get("value") if isinstance(val_obj, dict) else None
        if not isinstance(comp_list, list) or len(comp_list) != 9:
            continue
        comps: List[float] = []
        for c in comp_list:
            v = c.get("value") if isinstance(c, dict) else c
            if isinstance(v, (int, float)):
                comps.append(float(v))
        if len(comps) != 9:
            continue
        out[face_id] = {
            "normal": comps[0:3],
            "x": comps[3:6],
            "y": comps[6:9],
        }
    return out


class EntityManager:
    """Enumerate faces, edges, vertices, bodies with deterministic IDs.

    Claude calls this after every mutation before picking geometry for the
    next feature. IDs returned here are stable enough to drop into feature
    payloads as BTMIndividualQuery-138 deterministicIds.
    """

    def __init__(self, client: OnshapeClient):
        self.client = client

    async def _fetch_face_frames(
        self, document_id: str, workspace_id: str, element_id: str
    ) -> Dict[str, Dict[str, List[float]]]:
        """Run FeatureScript to get face_id -> {normal, x, y} world-frame.

        `evFaceTangentPlane` returns a BTPlane with `.normal` (body-outward
        direction), `.x` (in-plane U axis), and `.y` (in-plane V axis). All
        three are world-space unit vectors. We pull them for every face so
        a caller sketching on a vertical side face can map `(sx, sy)` in
        sketch coords to `sx * plane.x + sy * plane.y + origin` in world
        coords — no more "sketch X goes... which way on this face?"

        Returns an empty dict on failure so the caller can fall back to
        plane-defining normals; frame enrichment is best-effort.
        """
        path = (
            f"/api/v8/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/featurescript"
        )
        try:
            resp = await self.client.post(path, data={"script": _FACE_FRAMES_FS})
            return _parse_fs_frame_map(resp)
        except Exception:  # noqa: BLE001
            return {}

    async def list_entities(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        *,
        kinds: Optional[List[str]] = None,
        body_index: Optional[int] = None,
        geometry_type: Optional[str] = None,
        outward_axis: Optional[str] = None,
        at_z_mm: Optional[float] = None,
        at_z_tol_mm: float = 0.5,
        radius_range_mm: Optional[List[float]] = None,
        length_range_mm: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """Return structured, enriched entity lists for all bodies in the PS.

        Filters subset the entity lists BEFORE serialization so response
        payloads stay manageable. Field-dogfood (Raspberry Pi case, 2-part)
        saw raw responses hit 80–100 KB on moderately complex parts and
        pushed Claude into pagination-style workarounds. Every filter is
        independently optional; combine freely.

        Args:
            kinds: subset of {"faces", "edges", "vertices"}. Default: all.
            body_index: 0-based body to limit to. Default: all bodies.
            geometry_type: case-insensitive match against the classified
                `type` field. "PLANE" / "CYLINDER" / "CONE" / "TORUS" for
                faces; "LINE" / "CIRCLE" / "ARC" for edges. Vertices have
                no type so filtering one doesn't drop any vertex.
            outward_axis: "+X" | "-X" | "+Y" | "-Y" | "+Z" | "-Z". Keeps only
                faces whose classified `outward_axis` (body-outward) matches.
                Falls back to `normal_axis` when the FS outward fetch missed
                the face (degenerate/untessellated faces skip the FS probe).
            at_z_mm: keep faces whose origin Z is within `at_z_tol_mm` mm of
                this value; keep edges whose midpoint Z is within tolerance.
                Units: millimeters.
            at_z_tol_mm: tolerance around at_z_mm. Default 0.5 mm — tight
                enough to discriminate adjacent features of a ~mm-thick wall.
            radius_range_mm: [min_mm, max_mm] inclusive. Applies to faces
                with a radius (cylinder/cone/torus) and edges with a radius
                (circle/arc). Entities without a radius are dropped.
            length_range_mm: [min_mm, max_mm] inclusive. Edges only; faces
                have no length field.

        Returns: {"bodies": [{"body_id", "body_type", "faces": [...], ...}],
                 "summary": "...",
                 "filters": { <echoed filter params, for debugging> },
                 "original_counts": { body_id: {"faces": N, "edges": N, ...}},
                 "filtered_counts": { body_id: {"faces": N, "edges": N, ...}}}.

        Faces carry both `normal_axis` (plane-defining normal, sometimes
        ambiguous between top and bottom of a flat body) and `outward_axis`
        (body-outward direction, fetched via FeatureScript). Pick by
        `outward_axis` whenever you mean "the face that points <direction>
        away from the body".
        """
        wanted = set(kinds) if kinds else {"faces", "edges", "vertices"}

        normalized_geometry = (geometry_type or "").strip().upper() or None
        normalized_axis = (outward_axis or "").strip() or None
        if normalized_axis and normalized_axis not in {"+X", "-X", "+Y", "-Y", "+Z", "-Z"}:
            raise ValueError(
                f"outward_axis must be one of +X/-X/+Y/-Y/+Z/-Z, got {outward_axis!r}"
            )
        if radius_range_mm is not None and len(radius_range_mm) != 2:
            raise ValueError("radius_range_mm must be a [min, max] pair")
        if length_range_mm is not None and len(length_range_mm) != 2:
            raise ValueError("length_range_mm must be a [min, max] pair")

        path = (
            f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/bodydetails"
        )
        raw = await self.client.get(path)
        bodies_raw = raw.get("bodies") or []

        face_frames: Dict[str, Dict[str, List[float]]] = (
            await self._fetch_face_frames(document_id, workspace_id, element_id)
            if "faces" in wanted
            else {}
        )

        original_counts: Dict[str, Dict[str, int]] = {}
        filtered_counts: Dict[str, Dict[str, int]] = {}

        out_bodies: List[Dict[str, Any]] = []
        for idx, body in enumerate(bodies_raw):
            if body_index is not None and idx != body_index:
                continue
            body_id = body.get("id") or f"idx{idx}"
            raw_face_count = len(body.get("faces") or [])
            raw_edge_count = len(body.get("edges") or [])
            raw_vertex_count = len(body.get("vertices") or [])
            original_counts[body_id] = {
                "faces": raw_face_count,
                "edges": raw_edge_count,
                "vertices": raw_vertex_count,
            }

            entry: Dict[str, Any] = {
                "body_index": idx,
                "body_id": body.get("id"),
                "body_type": body.get("type"),
            }
            if "faces" in wanted:
                classified = [
                    _classify_face(f, face_frames)
                    for f in (body.get("faces") or [])
                ]
                entry["faces"] = [
                    f for f in classified
                    if _face_passes_filters(
                        f,
                        geometry_type=normalized_geometry,
                        outward_axis=normalized_axis,
                        at_z_mm=at_z_mm,
                        at_z_tol_mm=at_z_tol_mm,
                        radius_range_mm=radius_range_mm,
                    )
                ]
            if "edges" in wanted:
                classified_edges = [_classify_edge(e) for e in (body.get("edges") or [])]
                entry["edges"] = [
                    e for e in classified_edges
                    if _edge_passes_filters(
                        e,
                        geometry_type=normalized_geometry,
                        at_z_mm=at_z_mm,
                        at_z_tol_mm=at_z_tol_mm,
                        radius_range_mm=radius_range_mm,
                        length_range_mm=length_range_mm,
                    )
                ]
            if "vertices" in wanted:
                classified_verts = [
                    _classify_vertex(v) for v in (body.get("vertices") or [])
                ]
                entry["vertices"] = [
                    v for v in classified_verts
                    if _vertex_passes_filters(v, at_z_mm=at_z_mm, at_z_tol_mm=at_z_tol_mm)
                ]

            filtered_counts[body_id] = {
                "faces": len(entry.get("faces", [])) if "faces" in wanted else 0,
                "edges": len(entry.get("edges", [])) if "edges" in wanted else 0,
                "vertices": len(entry.get("vertices", [])) if "vertices" in wanted else 0,
            }
            out_bodies.append(entry)

        summary_lines: List[str] = []
        for b in out_bodies:
            fn = len(b.get("faces", [])) if "faces" in wanted else "-"
            en = len(b.get("edges", [])) if "edges" in wanted else "-"
            vn = len(b.get("vertices", [])) if "vertices" in wanted else "-"
            summary_lines.append(
                f"body[{b['body_index']}] id={b['body_id']} type={b['body_type']} "
                f"faces={fn} edges={en} vertices={vn}"
            )
        filters_echo = {
            "kinds": sorted(wanted),
            "body_index": body_index,
            "geometry_type": normalized_geometry,
            "outward_axis": normalized_axis,
            "at_z_mm": at_z_mm,
            "at_z_tol_mm": at_z_tol_mm if at_z_mm is not None else None,
            "radius_range_mm": list(radius_range_mm) if radius_range_mm else None,
            "length_range_mm": list(length_range_mm) if length_range_mm else None,
        }
        return {
            "bodies": out_bodies,
            "summary": "\n".join(summary_lines) if summary_lines else "no bodies",
            "filters": filters_echo,
            "original_counts": original_counts,
            "filtered_counts": filtered_counts,
        }
