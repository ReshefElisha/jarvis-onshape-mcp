"""Numeric geometry + mass properties for Claude.

Claude's spatial reasoning is weak; its numeric reasoning is not. Every time
Claude would have to eyeball a render to decide "is this face parallel to that
one" or "is the hole centered," give it a numeric answer instead.

Two primitives:
- measure(entity_a, entity_b): distance + angle between any two faces/edges/
  vertices picked by deterministic ID. Computed client-side from /bodydetails
  coordinates, which is exact for planar faces / linear edges / vertices. For
  curved geometry (cylinders, circular edges) it falls back to origin-to-origin
  or axis-to-axis approximations with a type flag.
- mass_properties(part_studio or part): volume, mass, centroid, inertia, bbox.
  Direct REST call to /partstudios/.../massproperties. No FS roundtrip.

Deliberately avoids FS-based evDistance because `qDeterministicIds` is not a
real FS function (tried it live, SEMANTIC error). FS queries are history-based;
there is no clean bridge from a deterministic-ID string to an FS Query that
covers all entity types. Coordinate math is both simpler and more reliable
for the planar/linear cases Claude cares about 95% of the time.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from .client import OnshapeClient
from .entities import (
    _classify_edge,
    _classify_face,
    _classify_vertex,
    _nearest_axis_label,
    _norm,
    _sub,
    _vec,
)


def _dot(a: List[float], b: List[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: List[float], b: List[float]) -> List[float]:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def _find_entity(
    bodies_raw: List[Dict[str, Any]], entity_id: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[int]]:
    """Find an entity by deterministic ID; return (entity_dict, kind, body_index)."""
    for idx, body in enumerate(bodies_raw):
        for f in body.get("faces") or []:
            if f.get("id") == entity_id:
                return f, "face", idx
        for e in body.get("edges") or []:
            if e.get("id") == entity_id:
                return e, "edge", idx
        for v in body.get("vertices") or []:
            if v.get("id") == entity_id:
                return v, "vertex", idx
    return None, None, None


def _point_of_face(face: Dict[str, Any]) -> Optional[List[float]]:
    """Representative point: plane origin, cylinder origin, etc."""
    surface = face.get("surface") or {}
    return _vec(surface.get("origin"))


def _point_of_edge(edge: Dict[str, Any]) -> Optional[List[float]]:
    geom = edge.get("geometry") or {}
    return _vec(geom.get("midPoint"))


def _point_of_vertex(vertex: Dict[str, Any]) -> Optional[List[float]]:
    return _vec(vertex.get("point"))


def _direction_of_face(face: Dict[str, Any]) -> Tuple[Optional[List[float]], str]:
    """(vector, kind_label). Planes -> normal; cylinders/cones -> axis; else None."""
    surface = face.get("surface") or {}
    stype = (surface.get("type") or "").upper()
    if stype == "PLANE":
        return _vec(surface.get("normal")), "normal"
    if stype in ("CYLINDER", "CONE", "TORUS"):
        return _vec(surface.get("axis")), "axis"
    return None, ""


def _direction_of_edge(edge: Dict[str, Any]) -> Optional[List[float]]:
    geom = edge.get("geometry") or {}
    start = _vec(geom.get("startPoint"))
    end = _vec(geom.get("endPoint"))
    if start is None or end is None:
        return None
    d = _sub(end, start)
    n = _norm(d)
    if n < 1e-12:
        return None
    return [d[0] / n, d[1] / n, d[2] / n]


def _point_and_dir(
    entity: Dict[str, Any], kind: str
) -> Tuple[Optional[List[float]], Optional[List[float]], Optional[str]]:
    """Return (representative_point, direction_unit, dir_kind_label)."""
    if kind == "face":
        p = _point_of_face(entity)
        d, dk = _direction_of_face(entity)
        return p, d, dk
    if kind == "edge":
        p = _point_of_edge(entity)
        d = _direction_of_edge(entity)
        return p, d, "tangent" if d is not None else ""
    if kind == "vertex":
        return _point_of_vertex(entity), None, ""
    return None, None, None


def _angle_between_unit_vectors(a: List[float], b: List[float]) -> float:
    """Acute angle (radians) between two unit vectors, sign-independent."""
    c = max(-1.0, min(1.0, abs(_dot(a, b))))
    return math.acos(c)


def _distance_point_to_plane(
    p: List[float], origin: List[float], normal_unit: List[float]
) -> float:
    return abs(_dot(_sub(p, origin), normal_unit))


def _signed_distance_along(
    p_from: List[float], p_to: List[float], direction_unit: List[float]
) -> float:
    return _dot(_sub(p_to, p_from), direction_unit)


class MeasurementManager:
    """Numeric distance/angle/mass-properties queries."""

    def __init__(self, client: OnshapeClient):
        self.client = client

    async def measure(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        *,
        entity_a_id: str,
        entity_b_id: str,
    ) -> Dict[str, Any]:
        """Distance + angle between two entities picked by deterministic ID.

        Returns a dict with:
          - entity_a, entity_b: echo of what was found (id, kind, description)
          - point_distance_m: Euclidean distance between representative points
          - parallel, perpendicular, coincident: booleans (if directions available)
          - angle_rad, angle_deg: acute angle between their directions
          - projected_distance_m: perpendicular distance in the special cases:
              * face-face with parallel normals: plane-to-plane distance
              * face-vertex or face-edge with planar face: point-to-plane distance
          - notes: list of caveats (non-planar face, curved edge, etc.)
        """
        raw = await self.client.get(
            f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/bodydetails"
        )
        bodies = raw.get("bodies") or []
        a, a_kind, a_bi = _find_entity(bodies, entity_a_id)
        b, b_kind, b_bi = _find_entity(bodies, entity_b_id)
        notes: List[str] = []
        if a is None:
            return {"ok": False, "error": f"entity {entity_a_id} not found"}
        if b is None:
            return {"ok": False, "error": f"entity {entity_b_id} not found"}

        def _describe(ent: Dict[str, Any], kind: str) -> Dict[str, Any]:
            if kind == "face":
                return _classify_face(ent)
            if kind == "edge":
                return _classify_edge(ent)
            return _classify_vertex(ent)

        a_desc = _describe(a, a_kind)
        b_desc = _describe(b, b_kind)

        pa, da, dka = _point_and_dir(a, a_kind)
        pb, db, dkb = _point_and_dir(b, b_kind)

        result: Dict[str, Any] = {
            "ok": True,
            "entity_a": {"id": entity_a_id, "kind": a_kind, **a_desc},
            "entity_b": {"id": entity_b_id, "kind": b_kind, **b_desc},
            "body_indices": [a_bi, b_bi],
        }

        if pa is not None and pb is not None:
            result["point_distance_m"] = _norm(_sub(pb, pa))
            result["point_distance_mm"] = result["point_distance_m"] * 1000.0

        if da is not None and db is not None:
            angle = _angle_between_unit_vectors(da, db)
            result["angle_rad"] = angle
            result["angle_deg"] = math.degrees(angle)
            result["parallel"] = angle < 1e-4
            result["perpendicular"] = abs(angle - math.pi / 2) < 1e-4

            if a_kind == "face" and b_kind == "face" and dka == "normal" and dkb == "normal":
                if result["parallel"] and pa is not None and pb is not None:
                    result["projected_distance_m"] = _distance_point_to_plane(pb, pa, da)
                    result["projected_distance_mm"] = result["projected_distance_m"] * 1000.0
                    notes.append("plane-to-plane perpendicular distance (faces parallel)")
            elif a_kind == "face" and dka == "normal" and pa is not None and pb is not None:
                result["projected_distance_m"] = _distance_point_to_plane(pb, pa, da)
                result["projected_distance_mm"] = result["projected_distance_m"] * 1000.0
                notes.append(f"point-to-plane distance (b is a {b_kind})")
            elif b_kind == "face" and dkb == "normal" and pa is not None and pb is not None:
                result["projected_distance_m"] = _distance_point_to_plane(pa, pb, db)
                result["projected_distance_mm"] = result["projected_distance_m"] * 1000.0
                notes.append(f"point-to-plane distance (a is a {a_kind})")

        surface_a = (a.get("surface") or {}).get("type", "").upper() if a_kind == "face" else None
        surface_b = (b.get("surface") or {}).get("type", "").upper() if b_kind == "face" else None
        if surface_a and surface_a != "PLANE":
            notes.append(f"entity_a is a {surface_a.lower()} face; representative point is its axis origin")
        if surface_b and surface_b != "PLANE":
            notes.append(f"entity_b is a {surface_b.lower()} face; representative point is its axis origin")

        if notes:
            result["notes"] = notes
        return result

    async def mass_properties_part_studio(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
    ) -> Dict[str, Any]:
        """All-parts mass properties for a Part Studio."""
        path = (
            f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/massproperties"
        )
        return await self.client.get(path)

    async def mass_properties_part(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        part_id: str,
    ) -> Dict[str, Any]:
        """Mass properties for a specific part in a Part Studio."""
        path = (
            f"/api/v9/parts/d/{document_id}/w/{workspace_id}/e/{element_id}/partid/{part_id}/massproperties"
        )
        return await self.client.get(path)
