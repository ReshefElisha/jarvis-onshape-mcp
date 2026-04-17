"""Unit tests for sketch_constraints.serialize.

Pure shape-level assertions. Every constraint type we emit to the wire is
checked against: constraintType field, parameter ids present, parameter
btTypes, entity-ref values, dimension expressions, enum values. Live API
contract lives in scripts/probe_*.py — these just prevent regressions in
the serializer output.
"""

from __future__ import annotations

import pytest

from onshape_mcp.builders.sketch_constraints import (
    serialize,
    validate_entity_refs,
)


def _param(result, parameter_id):
    for p in result["parameters"]:
        if p.get("parameterId") == parameter_id:
            return p
    pytest.fail(f"parameter {parameter_id!r} not found; got {result['parameters']!r}")


def _refs(result):
    return [p["value"] for p in result["parameters"]
            if p.get("btType") == "BTMParameterString-149"]


def test_envelope_defaults():
    r = serialize("HORIZONTAL", entity="line1")
    assert r["btType"] == "BTMSketchConstraint-2"
    assert r["namespace"] == ""
    assert r["helpParameters"] == []
    assert r["hasOffsetData1"] is False
    assert r["hasPierceParameter"] is False


# -- Single-ref constraints --

@pytest.mark.parametrize("ctype", ["HORIZONTAL", "VERTICAL"])
def test_single_ref_constraints_on_line(ctype):
    r = serialize(ctype, entity="line1")
    assert r["constraintType"] == ctype
    assert _refs(r) == ["line1"]


def test_single_ref_rejects_pair_input():
    with pytest.raises(ValueError, match="exactly 1 entity"):
        serialize("HORIZONTAL", entities=["a", "b"])


# -- Pair-ref constraints --

@pytest.mark.parametrize("ctype", [
    "COINCIDENT", "TANGENT", "CONCENTRIC", "PARALLEL", "PERPENDICULAR",
    "EQUAL", "MIDPOINT",
])
def test_pair_ref_constraints(ctype):
    r = serialize(ctype, entities=["a", "b"])
    assert r["constraintType"] == ctype
    assert _refs(r) == ["a", "b"]
    assert _param(r, "localFirst")["value"] == "a"
    assert _param(r, "localSecond")["value"] == "b"


def test_coincident_with_subpoint():
    r = serialize("COINCIDENT", entities=["line1.start", "circle1"])
    assert _param(r, "localFirst")["value"] == "line1.start"
    assert _param(r, "localSecond")["value"] == "circle1"


def test_pair_ref_rejects_single():
    with pytest.raises(ValueError, match="exactly 2 entity"):
        serialize("TANGENT", entity="a")


# -- Dimensioned constraints --

def test_diameter():
    r = serialize("DIAMETER", entity="hub", value="50 mm")
    assert r["constraintType"] == "DIAMETER"
    assert _param(r, "localFirst")["value"] == "hub"
    length = _param(r, "length")
    assert length["btType"] == "BTMParameterQuantity-147"
    assert length["expression"] == "50 mm"
    assert length["value"] == 0.0  # Onshape evaluates the expression


def test_radius():
    r = serialize("RADIUS", entity="fillet", value="5 mm")
    assert r["constraintType"] == "RADIUS"
    assert _param(r, "length")["expression"] == "5 mm"


def test_distance_default_direction_is_minimum():
    r = serialize("DISTANCE", entities=["a.center", "b.center"], value="100 mm")
    assert r["constraintType"] == "DISTANCE"
    assert _param(r, "direction")["value"] == "MINIMUM"
    assert _param(r, "direction")["enumName"] == "DimensionDirection"
    assert _param(r, "alignment")["value"] == "ALIGNED"
    assert _param(r, "length")["expression"] == "100 mm"


def test_distance_horizontal_direction():
    r = serialize("DISTANCE", entities=["a", "b"], value="100 mm",
                  direction="HORIZONTAL")
    assert _param(r, "direction")["value"] == "HORIZONTAL"


def test_distance_rejects_bad_direction():
    with pytest.raises(ValueError, match="MINIMUM|HORIZONTAL|VERTICAL"):
        serialize("DISTANCE", entities=["a", "b"], value="100 mm",
                  direction="DIAGONAL")


def test_horizontal_distance_alias():
    r = serialize("HORIZONTAL_DISTANCE", entities=["a", "b"], value="50 mm")
    assert r["constraintType"] == "DISTANCE"
    assert _param(r, "direction")["value"] == "HORIZONTAL"
    assert _param(r, "length")["expression"] == "50 mm"


def test_vertical_distance_alias():
    r = serialize("VERTICAL_DISTANCE", entities=["a", "b"], value="10 mm")
    assert r["constraintType"] == "DISTANCE"
    assert _param(r, "direction")["value"] == "VERTICAL"


def test_angle_degrees_default():
    r = serialize("ANGLE", entities=["line1", "line2"], value="90")
    assert r["constraintType"] == "ANGLE"
    angle = _param(r, "angle")
    assert angle["expression"] == "90 deg"


def test_angle_explicit_unit():
    r = serialize("ANGLE", entities=["line1", "line2"], value="1.57 rad")
    assert _param(r, "angle")["expression"] == "1.57 rad"


def test_dimensioned_rejects_no_value():
    with pytest.raises(ValueError, match="requires a dimension value"):
        serialize("DIAMETER", entity="hub")


def test_entity_ref_rejects_value():
    with pytest.raises(ValueError, match="does not take a dimension value"):
        serialize("COINCIDENT", entities=["a", "b"], value="10 mm")


# -- Binary-pair (OFFSET) --

def test_offset():
    r = serialize("OFFSET", entities=["hub_offset", "hub"])
    assert r["constraintType"] == "OFFSET"
    assert _param(r, "localOffset")["value"] == "hub_offset"
    assert _param(r, "localMaster")["value"] == "hub"
    tool = _param(r, "sketchToolType")
    assert tool["btType"] == "BTMParameterEnum-145"
    assert tool["enumName"] == "SketchToolType"
    assert tool["value"] == "OFFSET"


def test_offset_rejects_value():
    with pytest.raises(ValueError, match="does not carry a dimension"):
        serialize("OFFSET", entities=["a", "b"], value="8 mm")


# -- Rejections / aliases --

def test_point_on_rejected_with_helpful_error():
    with pytest.raises(ValueError, match="COINCIDENT with a point sub-ref"):
        serialize("POINT_ON", entities=["line.start", "circle"])


def test_unknown_type_rejected():
    with pytest.raises(ValueError, match="Unknown constraint type"):
        serialize("NONSENSE", entities=["a", "b"])


def test_case_insensitive():
    r_low = serialize("tangent", entities=["a", "b"])
    r_up = serialize("TANGENT", entities=["a", "b"])
    r_mix = serialize("Tangent", entities=["a", "b"])
    assert r_low["constraintType"] == r_up["constraintType"] == r_mix["constraintType"] == "TANGENT"


# -- constraint_id stamping --

def test_constraint_id_stamped_on_entity_id():
    r = serialize("DIAMETER", entity="hub", value="50 mm", constraint_id="d_hub")
    assert r["entityId"] == "d_hub"


def test_no_constraint_id_no_entity_id_field():
    r = serialize("DIAMETER", entity="hub", value="50 mm")
    assert "entityId" not in r


# -- validate_entity_refs --

def test_validate_accepts_known_ids():
    validate_entity_refs(["hub", "tip.center"], known_entity_ids={"hub", "tip"})


def test_validate_rejects_unknown():
    with pytest.raises(ValueError, match="unknown entity IDs"):
        validate_entity_refs(["hub", "ghost"], known_entity_ids={"hub", "tip"})


def test_validate_strips_subpoint_on_lookup():
    # "tip.center" base is "tip", which IS known — no raise.
    validate_entity_refs(["tip.center"], known_entity_ids={"tip"})
