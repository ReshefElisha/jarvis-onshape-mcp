"""Unit tests for assess_sketch_risk (the detector rename_feature /
update_feature / edit_sketch gate on before re-POSTing a sketch).

Fixture shapes are lifted directly from
knowledge_base/api/real_sketch_example.json (a captured real /features
response) rather than hand-invented, so these track the actual Onshape wire
format: sketchPlane is a BTMParameterQueryList-148 with deterministicIds;
an external constraint ref is the same param type under
parameterId="externalFirst"/"externalSecond".
"""

from onshape_mcp.api.sketch_inspect import assess_sketch_risk, STANDARD_PLANE_IDS


def _plane_param(plane_id: str) -> dict:
    return {
        "btType": "BTMParameterQueryList-148",
        "parameterId": "sketchPlane",
        "queries": [
            {
                "btType": "BTMIndividualQuery-138",
                "deterministicIds": [plane_id],
            }
        ],
    }


def _external_distance_constraint(external_id: str) -> dict:
    """Real shape: a DISTANCE constraint from a plane/face to the sketch."""
    return {
        "btType": "BTMSketchConstraint-2",
        "entityId": "vsdypZbUeS39",
        "constraintType": "DISTANCE",
        "parameters": [
            {
                "btType": "BTMParameterQueryList-148",
                "parameterId": "externalFirst",
                "queries": [{"btType": "BTMIndividualQuery-138", "deterministicIds": [external_id]}],
            },
            {
                "btType": "BTMParameterString-149",
                "value": "AjpZLHQCiR3I.right",
                "parameterId": "localSecond",
            },
            {
                "btType": "BTMParameterQuantity-147",
                "expression": "10 mm",
                "parameterId": "length",
            },
        ],
    }


def _local_length_constraint() -> dict:
    """Real shape: a LENGTH constraint referencing only the sketch's own geometry."""
    return {
        "btType": "BTMSketchConstraint-2",
        "entityId": "EVyXR2L6jY1V",
        "constraintType": "LENGTH",
        "parameters": [
            {
                "btType": "BTMParameterString-149",
                "value": "AjpZLHQCiR3I.bottom",
                "parameterId": "localFirst",
            },
            {
                "btType": "BTMParameterQuantity-147",
                "expression": "10 mm",
                "parameterId": "length",
            },
        ],
    }


def _sketch_feature(feature_id: str, plane_id: str, constraints: list) -> dict:
    return {
        "btType": "BTMSketch-151",
        "featureId": feature_id,
        "name": "Sketch 1",
        "parameters": [_plane_param(plane_id)],
        "entities": [],
        "constraints": constraints,
    }


def _features_doc(*features: dict) -> dict:
    return {"features": list(features)}


def _extrude_feature(feature_id: str) -> dict:
    return {
        "btType": "BTMFeature-134",
        "featureId": feature_id,
        "name": "Extrude 1",
        "featureType": "extrude",
        "parameters": [],
    }


class TestAssessSketchRisk:
    def test_safe_sketch_default_plane_local_constraints_only(self):
        doc = _features_doc(
            _sketch_feature("s1", "JCC", [_local_length_constraint(), _local_length_constraint()])
        )
        risk = assess_sketch_risk(doc, "s1")

        assert risk is not None
        assert risk["is_sketch"] is True
        assert risk["risky"] is False
        assert risk["plane_is_default"] is True
        assert risk["plane_ids"] == ["JCC"]
        assert risk["risky_constraints"] == []

    def test_risky_plane_non_default(self):
        """Plane references something other than JCC/JDC/JEC -- e.g. a
        picked/custom-feature-generated face."""
        doc = _features_doc(_sketch_feature("s1", "KeKO", [_local_length_constraint()]))
        risk = assess_sketch_risk(doc, "s1")

        assert risk["risky"] is True
        assert risk["plane_is_default"] is False
        assert risk["plane_ids"] == ["KeKO"]
        assert risk["risky_constraints"] == []
        assert "KeKO" in risk["summary"]

    def test_risky_constraint_external_ref(self):
        """Default plane, but a constraint reaches outside the sketch's own
        entities -- the real-world DISTANCE-from-plane shape."""
        doc = _features_doc(
            _sketch_feature("s1", "JCC", [_external_distance_constraint("JEC")])
        )
        risk = assess_sketch_risk(doc, "s1")

        assert risk["risky"] is True
        assert risk["plane_is_default"] is True
        assert len(risk["risky_constraints"]) == 1
        assert risk["risky_constraints"][0]["constraintType"] == "DISTANCE"
        assert risk["risky_constraints"][0]["externalFirst"] == ["JEC"]

    def test_risky_both_plane_and_constraints(self):
        """The real incident shape: non-default plane AND multiple external
        constraint refs -- Sketch 1 had 12 total external bindings."""
        doc = _features_doc(
            _sketch_feature(
                "s1",
                "KeKO",
                [
                    _external_distance_constraint("Kedg"),
                    _external_distance_constraint("KeRg"),
                    _local_length_constraint(),
                ],
            )
        )
        risk = assess_sketch_risk(doc, "s1")

        assert risk["risky"] is True
        assert risk["plane_is_default"] is False
        assert len(risk["risky_constraints"]) == 2

    def test_no_constraints_and_default_plane_is_safe(self):
        doc = _features_doc(_sketch_feature("s1", "JDC", []))
        risk = assess_sketch_risk(doc, "s1")
        assert risk["risky"] is False

    def test_non_sketch_feature_returns_none(self):
        doc = _features_doc(_extrude_feature("f1"))
        assert assess_sketch_risk(doc, "f1") is None

    def test_unknown_feature_id_returns_none(self):
        doc = _features_doc(_sketch_feature("s1", "JCC", []))
        assert assess_sketch_risk(doc, "does-not-exist") is None

    def test_summary_never_contains_sketch_solve_failed_literal(self):
        """The literal token SKETCH_SOLVE_FAILED must not appear in the
        summary: server.py's _enum_specific_hints pattern-matches that exact
        substring in error_message and would attach the wrong (post-hoc
        solver-failure recovery) hint to what should be a preemptive block."""
        doc = _features_doc(_sketch_feature("s1", "KeKO", [_external_distance_constraint("Kedg")]))
        risk = assess_sketch_risk(doc, "s1")
        assert "SKETCH_SOLVE_FAILED" not in risk["summary"]

    def test_standard_plane_ids_constant(self):
        assert STANDARD_PLANE_IDS == {"JCC", "JDC", "JEC"}
