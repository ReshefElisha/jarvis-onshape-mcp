"""Unit tests for the edit_sketch merge logic.

Pure-shape tests around `_merge` so cz3cmn1y's serializer slice can
land alongside without breaking the splice/cascade contract. No
OnshapeClient required.
"""

from __future__ import annotations

import pytest

from onshape_mcp.api.sketch_edit import (
    _merge,
    _strip_subpoint,
    wire_constraint_refs,
    wire_entity_id,
)


# ---- existing-sketch fixtures ---------------------------------------------
# Mirror BTMSketchCurveSegment-155 + BTMSketchConstraint-2 conventions used
# by the existing SketchBuilder: `entityId` is the user-visible id field,
# constraint references nest under `parameters[].value`. The merger should
# treat user-facing dicts (`{"id": ..., "entities": [...]}`) and wire-shape
# dicts the same.

LINE1 = {"btType": "BTMSketchCurveSegment-155", "entityId": "line1"}
LINE2 = {"btType": "BTMSketchCurveSegment-155", "entityId": "line2"}
CIRCLE1 = {"btType": "BTMSketchCurve-4", "entityId": "circle1"}

# Constraint that references line1 and circle1 via wire-shape parameters.
WIRE_TANGENT = {
    "btType": "BTMSketchConstraint-2",
    "entityId": "tang_line1_circle1",
    "constraintType": "TANGENT",
    "parameters": [
        {"btType": "BTMParameterString-149", "parameterId": "localFirst", "value": "line1"},
        {"btType": "BTMParameterString-149", "parameterId": "localSecond", "value": "circle1"},
    ],
}
# Sub-point reference: a coincident on line1.start.
WIRE_COINCIDENT = {
    "btType": "BTMSketchConstraint-2",
    "entityId": "coin_line1start_line2start",
    "constraintType": "COINCIDENT",
    "parameters": [
        {"btType": "BTMParameterString-149", "parameterId": "localFirst", "value": "line1.start"},
        {"btType": "BTMParameterString-149", "parameterId": "localSecond", "value": "line2.start"},
    ],
}
# Standalone constraint: doesn't reference anything in the fixture entities.
WIRE_HORIZONTAL_STANDALONE = {
    "btType": "BTMSketchConstraint-2",
    "entityId": "horiz_lineX",
    "constraintType": "HORIZONTAL",
    "parameters": [
        {"btType": "BTMParameterString-149", "parameterId": "localFirst", "value": "lineX"},
    ],
}


def test_strip_subpoint():
    assert _strip_subpoint("line1.start") == "line1"
    assert _strip_subpoint("circle1") == "circle1"
    assert _strip_subpoint("line1.start.x") == "line1"  # only first split


def test_wire_entity_id_reads_entityId_or_id():
    assert wire_entity_id({"entityId": "foo"}) == "foo"
    # constraint-first surface uses bare `id`; serializer will round-trip it
    # but until then the merger should accept both.
    assert wire_entity_id({"id": "bar"}) == "bar"
    assert wire_entity_id({"entityId": "foo", "id": "bar"}) == "foo"
    assert wire_entity_id({}) is None
    assert wire_entity_id("not-a-dict") is None


def test_wire_constraint_refs_recognizes_user_facing_shape():
    """User-facing shape (cz3cmn1y's surface, before serialization)."""
    assert wire_constraint_refs(
        {"type": "TANGENT", "entities": ["line1", "circle1"]}
    ) == {"line1", "circle1"}
    assert wire_constraint_refs(
        {"type": "DIAMETER", "entity": "circle1", "value": "50 mm"}
    ) == {"circle1"}  # `value` at top level is the dimension, not a ref
    # A constraint with no refs at all returns empty.
    assert wire_constraint_refs({"type": "FOO"}) == set()


def test_wire_constraint_refs_recognizes_wire_shape():
    """BTMSketchConstraint-2 wire shape with nested parameter strings."""
    refs = wire_constraint_refs(WIRE_TANGENT)
    assert "line1" in refs and "circle1" in refs
    refs2 = wire_constraint_refs(WIRE_COINCIDENT)
    assert "line1.start" in refs2
    assert "line2.start" in refs2


def test_merge_appends_new_entities_and_constraints():
    me, mc, removed_c, cascaded = _merge(
        existing_entities=[LINE1, LINE2],
        existing_constraints=[],
        add_entities=[{"id": "circle_new", "type": "circle", "center": [0, 0], "radius": 5}],
        add_constraints=[{"id": "diam_new", "type": "DIAMETER", "entity": "circle_new", "value": "10 mm"}],
        remove_ids=[],
    )
    assert wire_entity_id(me[-1]) == "circle_new"
    assert wire_entity_id(mc[-1]) == "diam_new"
    assert removed_c == []
    assert cascaded == []


def test_merge_collision_on_entity_id_raises():
    with pytest.raises(ValueError, match="collides"):
        _merge(
            existing_entities=[LINE1],
            existing_constraints=[],
            add_entities=[{"id": "line1", "type": "line"}],
            add_constraints=[],
            remove_ids=[],
        )


def test_merge_collision_on_constraint_id_raises():
    with pytest.raises(ValueError, match="collides"):
        _merge(
            existing_entities=[],
            existing_constraints=[WIRE_TANGENT],
            add_entities=[],
            add_constraints=[{"id": "tang_line1_circle1", "type": "TANGENT"}],
            remove_ids=[],
        )


def test_merge_collision_within_addEntities_itself_raises():
    """Two addEntities with the same id in the same call also collide."""
    with pytest.raises(ValueError, match="collides"):
        _merge(
            existing_entities=[],
            existing_constraints=[],
            add_entities=[
                {"id": "a", "type": "line"},
                {"id": "a", "type": "circle"},
            ],
            add_constraints=[],
            remove_ids=[],
        )


def test_merge_missing_id_on_add_raises():
    with pytest.raises(ValueError, match="non-empty `id`"):
        _merge(
            existing_entities=[],
            existing_constraints=[],
            add_entities=[{"type": "line"}],  # no id
            add_constraints=[],
            remove_ids=[],
        )


def test_merge_remove_entity_cascades_referencing_constraints():
    """Remove `line1` -> the TANGENT (refs line1+circle1) drops, the
    COINCIDENT (refs line1.start+line2.start) drops, the standalone
    HORIZONTAL stays."""
    me, mc, direct_removed, cascaded = _merge(
        existing_entities=[LINE1, LINE2, CIRCLE1],
        existing_constraints=[WIRE_TANGENT, WIRE_COINCIDENT, WIRE_HORIZONTAL_STANDALONE],
        add_entities=[],
        add_constraints=[],
        remove_ids=["line1"],
    )
    # Entity removed.
    remaining_entity_ids = {wire_entity_id(e) for e in me}
    assert "line1" not in remaining_entity_ids
    assert remaining_entity_ids == {"line2", "circle1"}

    # Constraints: tang + coincident gone, horizontal stays.
    remaining_constraint_ids = {wire_entity_id(c) for c in mc}
    assert remaining_constraint_ids == {"horiz_lineX"}

    assert direct_removed == []  # nothing in remove_ids was a constraint id
    cascaded_pairs = {(c.constraint_id, c.referenced) for c in cascaded}
    assert ("tang_line1_circle1", "line1") in cascaded_pairs
    assert ("coin_line1start_line2start", "line1") in cascaded_pairs


def test_merge_remove_id_matches_constraint_id_directly():
    """removeIds is a single bag; if you name a constraint id it just drops
    that constraint (no cascade since no entity is implied)."""
    me, mc, direct_removed, cascaded = _merge(
        existing_entities=[LINE1, LINE2],
        existing_constraints=[WIRE_TANGENT, WIRE_HORIZONTAL_STANDALONE],
        add_entities=[],
        add_constraints=[],
        remove_ids=["horiz_lineX"],
    )
    assert direct_removed == ["horiz_lineX"]
    assert cascaded == []
    remaining_constraint_ids = {wire_entity_id(c) for c in mc}
    assert remaining_constraint_ids == {"tang_line1_circle1"}


def test_merge_unmatched_remove_id_is_no_op_not_error():
    """If a removeId names something that isn't on the wire, the call still
    succeeds (no-op for that id) and the rest of the diff applies. The
    warning is logged for visibility but not raised."""
    me, mc, direct_removed, cascaded = _merge(
        existing_entities=[LINE1],
        existing_constraints=[],
        add_entities=[{"id": "line2_new", "type": "line"}],
        add_constraints=[],
        remove_ids=["does_not_exist"],
    )
    assert direct_removed == []
    assert cascaded == []
    # The add still landed.
    assert {wire_entity_id(e) for e in me} == {"line1", "line2_new"}


def test_merge_same_call_retarget_by_id():
    """Tool description says "To retarget an id, removeIds it first and then
    addEntities it back." Regression from peer ot0309vt clevis dogfood —
    the collision check used to run BEFORE removeIds took effect, so the
    documented pattern raised. Fixed by computing post-remove state first
    then validating adds against that."""
    me, mc, direct_removed, cascaded = _merge(
        existing_entities=[LINE1],
        existing_constraints=[],
        add_entities=[{"id": "line1", "type": "line", "start": [0, 0], "end": [5, 5]}],
        add_constraints=[],
        remove_ids=["line1"],
    )
    remaining_ids = {wire_entity_id(e) for e in me}
    assert remaining_ids == {"line1"}
    new_line = [e for e in me if wire_entity_id(e) == "line1"][0]
    # The new one is the one we added (seed at [0,0]), not the original LINE1.
    assert new_line.get("start") == [0, 0]


def test_merge_combined_diff_in_one_call():
    """Realistic scenario: drop a wrong line, add the corrected one + its
    coincident constraint, all in one edit_sketch call."""
    me, mc, direct_removed, cascaded = _merge(
        existing_entities=[LINE1, LINE2],
        existing_constraints=[WIRE_COINCIDENT],
        add_entities=[{"id": "line1_v2", "type": "line", "start": [0, 0], "end": [10, 0]}],
        add_constraints=[
            {"id": "coin_v2", "type": "COINCIDENT",
             "entities": ["line1_v2.start", "line2.start"]},
        ],
        remove_ids=["line1"],
    )
    remaining_entity_ids = {wire_entity_id(e) for e in me}
    assert remaining_entity_ids == {"line2", "line1_v2"}
    # Old coincident cascaded out (referenced removed line1), new one lands.
    remaining_constraint_ids = {wire_entity_id(c) for c in mc}
    assert remaining_constraint_ids == {"coin_v2"}
    assert any(c.referenced == "line1" for c in cascaded)
