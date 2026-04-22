"""Structured inspection of a BTMSketch-151 feature.

Purpose: give callers a compact, constraint-authorable view of a sketch's
entities and constraints without having to parse the raw /features JSON.
Pairs with `add_sketch_constraints` — the entity ids and sub-points returned
here are exactly the strings that tool's `localFirst`/`localSecond` accept.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


def _param_map(params: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for p in params or []:
        if isinstance(p, dict) and p.get("parameterId"):
            out[p["parameterId"]] = p
    return out


def _extract_param_value(p: Dict[str, Any]) -> Any:
    """Unwrap a single BTMParameter-* into a plain Python value."""
    btt = p.get("btType", "")
    if btt == "BTMParameterString-149":
        return p.get("value", "")
    if btt == "BTMParameterQuantity-147":
        # expression is the Onshape-editable form; value is cached meters.
        return p.get("expression") or p.get("value", 0.0)
    if btt == "BTMParameterEnum-145":
        return p.get("value", "")
    if btt == "BTMParameterQueryList-148":
        ids: List[str] = []
        for q in p.get("queries") or []:
            ids.extend(q.get("deterministicIds") or [])
        return ids
    if btt == "BTMParameterBoolean-144":
        return bool(p.get("value", False))
    return p.get("value")


def _line_endpoints(geom: Dict[str, Any], start_param: float, end_param: float) -> Tuple[Tuple[float, float], Tuple[float, float], float]:
    px = float(geom.get("pntX", 0.0))
    py = float(geom.get("pntY", 0.0))
    dx = float(geom.get("dirX", 1.0))
    dy = float(geom.get("dirY", 0.0))
    start = (px + dx * start_param, py + dy * start_param)
    end = (px + dx * end_param, py + dy * end_param)
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    return start, end, length


def _arc_endpoints(geom: Dict[str, Any], start_param: float, end_param: float) -> Tuple[Tuple[float, float], Tuple[float, float], float, float, float]:
    cx = float(geom.get("xCenter", 0.0))
    cy = float(geom.get("yCenter", 0.0))
    r = float(geom.get("radius", 0.0))
    # xDir/yDir define the reference frame for the arc's angular parameters.
    # For the common case (xDir=1, yDir=0) param is just the angle from +X.
    xdx = float(geom.get("xDir", 1.0))
    xdy = float(geom.get("yDir", 0.0))
    # Build perpendicular for rotation: (ydx, ydy) = rot90(xdir) if CCW.
    clockwise = bool(geom.get("clockwise", False))
    sign = -1.0 if clockwise else 1.0

    def _point_at(t: float) -> Tuple[float, float]:
        cos_t = math.cos(t)
        sin_t = math.sin(t) * sign
        # rotate (r*cos_t, r*sin_t) into frame (xdir, ydir=perp(xdir))
        x = cx + r * (cos_t * xdx - sin_t * xdy)
        y = cy + r * (cos_t * xdy + sin_t * xdx)
        return x, y

    start = _point_at(start_param)
    end = _point_at(end_param)
    sweep = abs(end_param - start_param)
    return start, end, r, sweep, (cx, cy)


def _mm(x: float) -> str:
    return f"{x*1000:.2f}"


def _summarize_entity(entity: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a compact, human-readable row for one sketch entity."""
    eid = entity.get("entityId") or ""
    btt = entity.get("btType", "")
    geom = entity.get("geometry") or {}
    gtype = geom.get("btType", "")
    is_construction = bool(entity.get("isConstruction"))

    out: Dict[str, Any] = {
        "id": eid,
        "btType": btt,
        "isConstruction": is_construction,
        "startPointId": entity.get("startPointId") or None,
        "endPointId": entity.get("endPointId") or None,
        "centerId": entity.get("centerId") or None,
    }

    if gtype == "BTCurveGeometryLine-117":
        start_param = float(entity.get("startParam", 0.0))
        end_param = float(entity.get("endParam", 0.0))
        start, end, length = _line_endpoints(geom, start_param, end_param)
        out.update({
            "kind": "line",
            "start_mm": (start[0] * 1000, start[1] * 1000),
            "end_mm": (end[0] * 1000, end[1] * 1000),
            "length_mm": length * 1000,
        })
        out["summary"] = (
            f"line  id={eid}  ({_mm(start[0])}, {_mm(start[1])}) -> "
            f"({_mm(end[0])}, {_mm(end[1])}) mm  [{_mm(length)} mm]"
            + ("  construction" if is_construction else "")
        )
    elif gtype == "BTCurveGeometryCircle-115":
        start_param = float(entity.get("startParam", 0.0))
        end_param = float(entity.get("endParam", 0.0))
        start, end, r, sweep, center = _arc_endpoints(geom, start_param, end_param)
        # Full-circle detection: either the wrapper is BTMSketchCurve-4
        # (single-entity circle topology, no start/end params), or the
        # swept BTMSketchCurveSegment-155 arc spans ~2*pi.
        is_full = btt == "BTMSketchCurve-4" or abs(sweep - 2 * math.pi) < 1e-6
        if is_full:
            out.update({
                "kind": "circle",
                "center_mm": (center[0] * 1000, center[1] * 1000),
                "radius_mm": r * 1000,
            })
            out["summary"] = (
                f"circle id={eid}  center=({_mm(center[0])}, {_mm(center[1])}) "
                f"r={_mm(r)} mm"
                + ("  construction" if is_construction else "")
            )
        else:
            out.update({
                "kind": "arc",
                "center_mm": (center[0] * 1000, center[1] * 1000),
                "radius_mm": r * 1000,
                "start_mm": (start[0] * 1000, start[1] * 1000),
                "end_mm": (end[0] * 1000, end[1] * 1000),
                "sweep_deg": math.degrees(sweep),
            })
            out["summary"] = (
                f"arc   id={eid}  center=({_mm(center[0])}, {_mm(center[1])}) "
                f"r={_mm(r)} mm  sweep={math.degrees(sweep):.1f} deg"
                + ("  construction" if is_construction else "")
            )
    elif btt == "BTMSketchPoint-279":
        out.update({
            "kind": "point",
            "point_mm": (
                float(entity.get("x", 0.0)) * 1000,
                float(entity.get("y", 0.0)) * 1000,
            ),
        })
        out["summary"] = (
            f"point id={eid}  ({entity.get('x', 0.0)*1000:.2f}, "
            f"{entity.get('y', 0.0)*1000:.2f}) mm"
        )
    else:
        out["kind"] = "other"
        out["summary"] = f"other id={eid}  btType={btt}  geom={gtype}"

    return out


def _summarize_constraint(constraint: Dict[str, Any]) -> Dict[str, Any]:
    ctype = constraint.get("constraintType", "?")
    cid = constraint.get("entityId") or ""
    pmap = _param_map(constraint.get("parameters") or [])

    def _s(pid: str) -> Optional[str]:
        p = pmap.get(pid)
        return None if p is None else _extract_param_value(p)

    out: Dict[str, Any] = {
        "id": cid,
        "constraintType": ctype,
        "localFirst": _s("localFirst"),
        "localSecond": _s("localSecond"),
        "externalFirst": _s("externalFirst"),
        "externalSecond": _s("externalSecond"),
    }
    length_expr = _s("length")
    angle_expr = _s("angle")
    direction = _s("direction")
    if length_expr is not None:
        out["length"] = length_expr
    if angle_expr is not None:
        out["angle"] = angle_expr
    if direction is not None:
        out["direction"] = direction

    # Build a one-line human summary.
    lf = out["localFirst"]
    ls = out["localSecond"]
    ext = out["externalFirst"] or out["externalSecond"]
    parts = [f"{ctype:12s}"]
    if ctype in ("DISTANCE", "LENGTH"):
        refs = lf if ls is None else f"{lf} <-> {ls}"
        parts.append(refs)
        if direction and direction != "MINIMUM":
            parts.append(f"({direction})")
        parts.append(f"= {length_expr}")
    elif ctype in ("DIAMETER", "RADIUS"):
        parts.append(f"{lf}  = {length_expr}")
    elif ctype == "ANGLE":
        parts.append(f"{lf} <-> {ls}  = {angle_expr}")
    elif ctype == "CONCENTRIC":
        parts.append(f"external={ext}  local={ls}")
    elif ctype in ("HORIZONTAL", "VERTICAL", "FIX"):
        parts.append(str(lf))
        if ext:
            parts.append(f"(external={ext})")
    else:
        refs = lf if ls is None else f"{lf} <-> {ls}"
        parts.append(refs)
    out["summary"] = "  ".join(p for p in parts if p)
    return out


def find_sketch(
    features_doc: Dict[str, Any],
    *,
    sketch_feature_id: Optional[str] = None,
    sketch_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Locate one BTMSketch-151 feature in a /features response.

    Resolution order: `sketch_feature_id` wins if given; otherwise match by
    exact `name`. Raises ValueError with the full available-id/name list if
    no match (to make wrong lookups easy to debug).
    """
    features: List[Dict[str, Any]] = features_doc.get("features") or []
    candidates = [f for f in features if f.get("btType") == "BTMSketch-151"]

    if sketch_feature_id:
        for f in features:
            if f.get("featureId") == sketch_feature_id:
                if f.get("btType") != "BTMSketch-151":
                    raise ValueError(
                        f"feature {sketch_feature_id!r} is not a sketch "
                        f"(btType={f.get('btType')!r})"
                    )
                return f
        raise ValueError(
            f"sketchFeatureId {sketch_feature_id!r} not found. Available "
            f"feature ids: {[f.get('featureId') for f in features]}"
        )

    if sketch_name:
        matches = [f for f in candidates if f.get("name") == sketch_name]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(
                f"multiple sketches named {sketch_name!r}; pass sketchFeatureId "
                f"instead. Matches: {[f.get('featureId') for f in matches]}"
            )
        raise ValueError(
            f"no sketch named {sketch_name!r}. Available sketches: "
            f"{[(f.get('name'), f.get('featureId')) for f in candidates]}"
        )

    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(
        f"pass sketchFeatureId or sketchName. "
        f"Available sketches: {[(f.get('name'), f.get('featureId')) for f in candidates]}"
    )


def inspect_sketch(
    features_doc: Dict[str, Any],
    *,
    sketch_feature_id: Optional[str] = None,
    sketch_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Produce a compact structured + text summary of one sketch.

    Returns a dict with:
        name, feature_id, status, plane_query, entities, constraints, text
    where `entities` and `constraints` are lists of per-item summary dicts
    (see `_summarize_entity` / `_summarize_constraint`) and `text` is a
    ready-to-display multi-line string.
    """
    feature = find_sketch(
        features_doc,
        sketch_feature_id=sketch_feature_id,
        sketch_name=sketch_name,
    )
    fid = feature.get("featureId") or ""
    name = feature.get("name") or ""
    states = features_doc.get("featureStates") or {}
    status = (states.get(fid) or {}).get("featureStatus", "?")

    # sketchPlane parameter carries a BTMParameterQueryList with the target
    # plane/face deterministic ids. Surface those so callers know what the
    # sketch is sitting on.
    plane_ids: List[str] = []
    for p in feature.get("parameters") or []:
        if isinstance(p, dict) and p.get("parameterId") == "sketchPlane":
            val = _extract_param_value(p)
            if isinstance(val, list):
                plane_ids = val

    entities = [_summarize_entity(e) for e in feature.get("entities") or []]
    constraints = [_summarize_constraint(c) for c in feature.get("constraints") or []]

    # Group entities by kind for a tidier display.
    header = (
        f'SKETCH "{name}"  id={fid}  status={status}\n'
        f"  plane deterministicIds: {plane_ids or '(none)'}\n"
    )
    if entities:
        entity_lines = ["ENTITIES ({}):".format(len(entities))]
        for e in entities:
            entity_lines.append(f"  {e['summary']}")
    else:
        entity_lines = ["ENTITIES: none"]

    if constraints:
        con_lines = ["CONSTRAINTS ({}):".format(len(constraints))]
        for c in constraints:
            con_lines.append(f"  {c['summary']}  (entityId={c['id']})")
    else:
        con_lines = ["CONSTRAINTS: none"]

    text = "\n".join([header] + entity_lines + [""] + con_lines)

    return {
        "name": name,
        "feature_id": fid,
        "status": status,
        "plane_query": plane_ids,
        "entities": entities,
        "constraints": constraints,
        "text": text,
    }


def list_sketches(features_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return a light summary of every BTMSketch-151 feature in the element."""
    out: List[Dict[str, Any]] = []
    states = features_doc.get("featureStates") or {}
    for f in features_doc.get("features") or []:
        if f.get("btType") != "BTMSketch-151":
            continue
        fid = f.get("featureId") or ""
        entities = f.get("entities") or []
        constraints = f.get("constraints") or []
        out.append({
            "feature_id": fid,
            "name": f.get("name") or "",
            "status": (states.get(fid) or {}).get("featureStatus", "?"),
            "entity_count": len(entities),
            "constraint_count": len(constraints),
        })
    return out
