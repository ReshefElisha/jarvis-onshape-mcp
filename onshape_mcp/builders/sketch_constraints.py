"""Serializer for BTMSketchConstraint-2 payloads.

Shape derived from a live probe of Onshape's /features endpoint on a
UI-built sketch (see scratchpad/sketch-constraint-payloads.md).

Every constraint wraps in BTMSketchConstraint-2 with a `constraintType`
discriminator. Parameters are per-type. Entity references inside
parameters are BTMParameterString-149 with `value` = entity ID,
optionally with a sub-point suffix like ".start", ".end", ".center", or
".<N>" (offset-chain). Dimension values are BTMParameterQuantity-147
with `expression` set to the unit string ("50 mm") — Onshape evaluates
server-side.

Entity-ref-only constraints (no dimension):
    HORIZONTAL, VERTICAL, COINCIDENT, TANGENT, CONCENTRIC,
    PARALLEL, PERPENDICULAR, EQUAL, POINT_ON, MIDPOINT

Dimensioned constraints (ref + `length` or `angle` Quantity):
    DIAMETER, RADIUS, DISTANCE, HORIZONTAL_DISTANCE, VERTICAL_DISTANCE, ANGLE

Binary-pair constraint (ref + enum, no Quantity):
    OFFSET  (bound to a DISTANCE constraint on the same pair)

Types confirmed against the clevis probe: HORIZONTAL, COINCIDENT,
TANGENT, CONCENTRIC, DIAMETER, RADIUS, DISTANCE, OFFSET. The other 9
are educated guesses mirroring symmetric shapes and will be validated
by the live probe loop before we ship.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ._units import parse_length


_CONSTRAINT_DEFAULTS = {
    "btType": "BTMSketchConstraint-2",
    "namespace": "",
    "name": "",
    "helpParameters": [],
    "hasOffsetData1": False,
    "offsetOrientation1": False,
    "offsetDistance1": 0.0,
    "hasOffsetData2": False,
    "offsetOrientation2": False,
    "offsetDistance2": 0.0,
    "hasPierceParameter": False,
    "pierceParameter": 0.0,
    "index": 1,
}


def _ref_param(parameter_id: str, entity_ref: str) -> Dict[str, Any]:
    """Build a local-entity reference parameter (BTMParameterString-149).

    `entity_ref` is either a bare entity id ("KTaZYOC2ES0V") or an id
    with a sub-point suffix ("KTaZYOC2ES0V.center", "utTOQfstgXyH.start").
    """
    return {
        "btType": "BTMParameterString-149",
        "value": entity_ref,
        "parameterId": parameter_id,
        "parameterName": "",
        "libraryRelationType": "NONE",
    }


def _quantity_param(parameter_id: str, expression: str) -> Dict[str, Any]:
    """Build a dimension-value parameter (BTMParameterQuantity-147).

    Expression is a unit string like "50 mm", "0.5 in", "90 deg".
    Onshape evaluates the expression server-side; `value` stays 0.0.
    """
    return {
        "btType": "BTMParameterQuantity-147",
        "isInteger": False,
        "value": 0.0,
        "units": "",
        "expression": expression,
        "parameterId": parameter_id,
        "parameterName": "",
        "libraryRelationType": "NONE",
    }


def _enum_param(parameter_id: str, enum_name: str, value: str) -> Dict[str, Any]:
    return {
        "btType": "BTMParameterEnum-145",
        "namespace": "",
        "enumName": enum_name,
        "value": value,
        "parameterId": parameter_id,
        "parameterName": "",
        "libraryRelationType": "NONE",
    }


def _wrap(constraint_type: str, parameters: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        **_CONSTRAINT_DEFAULTS,
        "constraintType": constraint_type,
        "parameters": parameters,
    }


# -----------------------------------------------------------------------
# Entity-ref constraints (no dimension value)
# -----------------------------------------------------------------------

def _single_ref(ctype: str, refs: List[str]) -> Dict[str, Any]:
    if len(refs) != 1:
        raise ValueError(f"{ctype} takes exactly 1 entity ref; got {len(refs)}")
    return _wrap(ctype, [_ref_param("localFirst", refs[0])])


def _pair_ref(ctype: str, refs: List[str]) -> Dict[str, Any]:
    if len(refs) != 2:
        raise ValueError(f"{ctype} takes exactly 2 entity refs; got {len(refs)}")
    return _wrap(
        ctype,
        [
            _ref_param("localFirst", refs[0]),
            _ref_param("localSecond", refs[1]),
        ],
    )


# -----------------------------------------------------------------------
# Dimensioned constraints (ref + length/angle Quantity)
# -----------------------------------------------------------------------

def _diameter(refs: List[str], value: str) -> Dict[str, Any]:
    if len(refs) != 1:
        raise ValueError(f"DIAMETER takes 1 entity ref; got {len(refs)}")
    expr = _expr_length(value)
    return _wrap(
        "DIAMETER",
        [
            _ref_param("localFirst", refs[0]),
            _quantity_param("length", expr),
        ],
    )


def _radius(refs: List[str], value: str) -> Dict[str, Any]:
    if len(refs) != 1:
        raise ValueError(f"RADIUS takes 1 entity ref; got {len(refs)}")
    expr = _expr_length(value)
    return _wrap(
        "RADIUS",
        [
            _ref_param("localFirst", refs[0]),
            _quantity_param("length", expr),
        ],
    )


def _distance(refs: List[str], value: str,
              direction: str = "MINIMUM") -> Dict[str, Any]:
    """Distance between two entities/points.

    `direction` is a DimensionDirection enum: MINIMUM (aligned), HORIZONTAL,
    or VERTICAL. The clevis probe shows DIRECTION=HORIZONTAL for the
    hub-to-tip center distance, suggesting the UI picked HORIZONTAL because
    both centers were on the x-axis. Default here: MINIMUM (least opinionated).
    """
    if len(refs) != 2:
        raise ValueError(f"DISTANCE takes 2 entity refs; got {len(refs)}")
    if direction.upper() not in {"MINIMUM", "HORIZONTAL", "VERTICAL"}:
        raise ValueError(
            f"DISTANCE direction must be MINIMUM|HORIZONTAL|VERTICAL; got {direction!r}"
        )
    expr = _expr_length(value)
    return _wrap(
        "DISTANCE",
        [
            _ref_param("localFirst", refs[0]),
            _ref_param("localSecond", refs[1]),
            _enum_param("direction", "DimensionDirection", direction.upper()),
            _quantity_param("length", expr),
            _enum_param("alignment", "DimensionAlignment", "ALIGNED"),
        ],
    )


def _horizontal_distance(refs: List[str], value: str) -> Dict[str, Any]:
    return _distance(refs, value, direction="HORIZONTAL")


def _vertical_distance(refs: List[str], value: str) -> Dict[str, Any]:
    return _distance(refs, value, direction="VERTICAL")


def _angle(refs: List[str], value: str) -> Dict[str, Any]:
    if len(refs) != 2:
        raise ValueError(f"ANGLE takes 2 entity refs; got {len(refs)}")
    # Angle expressions should carry a unit ("90 deg", "1.57 rad"); bare
    # numbers default to degrees because CAD users expect degrees.
    expr = _expr_angle(value)
    return _wrap(
        "ANGLE",
        [
            _ref_param("localFirst", refs[0]),
            _ref_param("localSecond", refs[1]),
            _quantity_param("angle", expr),
        ],
    )


# -----------------------------------------------------------------------
# Binary-pair constraint (OFFSET)
# -----------------------------------------------------------------------

def _offset(refs: List[str], value: Optional[str] = None) -> Dict[str, Any]:
    """OFFSET pairs an offset-chain entity with its master.

    `refs[0]` is the offset entity (the construction copy, e.g.
    "cpZBS8Rt1aLi.0"). `refs[1]` is the master (the source real entity,
    e.g. "r9ZJeHjaMPIC"). The actual offset distance lives on a separate
    DISTANCE constraint between the two — OFFSET itself carries no
    dimension. If a `value` is given, the caller should ALSO add a
    DISTANCE constraint; we do NOT emit one here (keeps the primitive
    honest).
    """
    if len(refs) != 2:
        raise ValueError(f"OFFSET takes 2 entity refs (offset, master); got {len(refs)}")
    if value is not None:
        raise ValueError(
            "OFFSET does not carry a dimension; pair it with a separate "
            "DISTANCE constraint on the same two entities for the offset length"
        )
    return _wrap(
        "OFFSET",
        [
            _ref_param("localOffset", refs[0]),
            _ref_param("localMaster", refs[1]),
            _enum_param("sketchToolType", "SketchToolType", "OFFSET"),
        ],
    )


# -----------------------------------------------------------------------
# Expression helpers
# -----------------------------------------------------------------------

def _expr_length(value: Any) -> str:
    """Normalize a length value into an Onshape-ready expression string."""
    if isinstance(value, str):
        # Treat bare-numeric strings as mm (matches our feature-builder convention).
        try:
            float(value)
            return f"{value} mm"
        except ValueError:
            return value  # already has a unit or is a variable ref
    return parse_length(value).expression


def _expr_angle(value: Any) -> str:
    if isinstance(value, str):
        try:
            float(value)
            return f"{value} deg"
        except ValueError:
            return value
    return f"{value} deg"


# -----------------------------------------------------------------------
# Public dispatch
# -----------------------------------------------------------------------

_ENTITY_REF_ONLY = {
    # HORIZONTAL/VERTICAL on a LINE constrains the line to that axis.
    # Fixture probe confirmed Onshape accepts single localFirst with no
    # externalSecond backfill. HORIZONTAL/VERTICAL on a POINT (like
    # `hub.center`) is NOT supported here — Onshape requires an axis
    # externalSecond we don't have. Use DISTANCE with direction=VERTICAL
    # and value=0 for "pin point to horizontal axis."
    "HORIZONTAL": "single",
    "VERTICAL": "single",
    "COINCIDENT": "pair",
    "TANGENT": "pair",
    "CONCENTRIC": "pair",
    "PARALLEL": "pair",
    "PERPENDICULAR": "pair",
    # EQUAL accepts two lines (equal length) OR two circles/arcs
    # (equal radius) — no type marker, same wire shape.
    "EQUAL": "pair",
    # MIDPOINT: localFirst is a point sub-ref (.start/.end/etc), localSecond
    # is a curve entity. Pins the point to the curve's midpoint.
    "MIDPOINT": "pair",
    # POINT_ON is intentionally NOT a distinct type — it's just COINCIDENT
    # with a point sub-ref as the first arg. Callers should use COINCIDENT.
    # We reject the alias explicitly in serialize() to keep the surface small.
}

_DIMENSIONED = {
    "DIAMETER": _diameter,
    "RADIUS": _radius,
    # HORIZONTAL_DISTANCE / VERTICAL_DISTANCE are aliases handled at the
    # dispatch level — they both map to DISTANCE with a direction enum.
    "DISTANCE": _distance,
    "ANGLE": _angle,
}

_BINARY_PAIR = {
    "OFFSET": _offset,
}


def serialize(
    constraint_type: str,
    *,
    entities: Optional[List[str]] = None,
    entity: Optional[str] = None,
    value: Optional[Any] = None,
    direction: Optional[str] = None,
    constraint_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Turn a user-level constraint spec into BTMSketchConstraint-2 JSON.

    Args:
        constraint_type: Constraint name (case-insensitive). See module
            docstring for the full list.
        entities: List of entity refs (strings). Required for pair-ref
            constraints; mutually exclusive with `entity`.
        entity: Single entity ref. Shorthand for 1-element `entities`.
        value: Dimension value (string like "50 mm" or number).
            Required for DIAMETER, RADIUS, DISTANCE, HORIZONTAL_DISTANCE,
            VERTICAL_DISTANCE, ANGLE.
        direction: DISTANCE direction enum override (MINIMUM | HORIZONTAL | VERTICAL).
            Only read for DISTANCE.
        constraint_id: Optional stable user-level id for this constraint.
            Stamped onto the wire dict's `entityId` field so edit_sketch can
            find + remove this constraint by that id later. Leave None for
            one-shot create_sketch constraints that won't be edited.
    """
    ctype = constraint_type.upper().replace("-", "_").replace(" ", "_")
    if entity is not None:
        if entities is not None:
            raise ValueError("pass `entities` OR `entity`, not both")
        entities = [entity]
    refs = entities or []

    if ctype == "POINT_ON":
        raise ValueError(
            "POINT_ON is not a distinct constraint type. Use "
            "COINCIDENT with a point sub-ref instead: "
            "{'type': 'COINCIDENT', 'entities': ['line.start', 'circle']}"
        )
    if ctype == "HORIZONTAL_DISTANCE":
        ctype = "DISTANCE"
        direction = "HORIZONTAL"
    elif ctype == "VERTICAL_DISTANCE":
        ctype = "DISTANCE"
        direction = "VERTICAL"

    if ctype in _ENTITY_REF_ONLY:
        if value is not None:
            raise ValueError(f"{ctype} does not take a dimension value")
        shape = _ENTITY_REF_ONLY[ctype]
        if shape == "single":
            out = _single_ref(ctype, refs)
        else:
            out = _pair_ref(ctype, refs)
    elif ctype in _DIMENSIONED:
        if value is None:
            raise ValueError(f"{ctype} requires a dimension value")
        fn = _DIMENSIONED[ctype]
        if ctype == "DISTANCE" and direction:
            out = _distance(refs, value, direction=direction)
        else:
            out = fn(refs, value)
    elif ctype in _BINARY_PAIR:
        out = _BINARY_PAIR[ctype](refs, value)
    else:
        raise ValueError(
            f"Unknown constraint type: {constraint_type!r}. "
            f"Supported: {sorted(list(_ENTITY_REF_ONLY) + list(_DIMENSIONED) + list(_BINARY_PAIR))}"
        )

    if constraint_id:
        out["entityId"] = constraint_id
    return out


def validate_entity_refs(
    refs: List[str],
    known_entity_ids: set,
) -> None:
    """Verify every ref resolves to a known entity (base id lookup).

    Raises ValueError listing any refs whose base id is not in the set.
    Sub-point suffixes (".start", ".end", ".center", ".<N>") are
    stripped before the lookup — we don't enforce sub-point validity
    here because a ".center" on a line makes no sense and Onshape will
    reject it at solve time with a clear error.
    """
    missing = []
    for ref in refs:
        base = ref.split(".", 1)[0]
        if base not in known_entity_ids:
            missing.append(ref)
    if missing:
        raise ValueError(
            f"Constraint references unknown entity IDs: {missing}. "
            f"Known IDs: {sorted(known_entity_ids)}"
        )
