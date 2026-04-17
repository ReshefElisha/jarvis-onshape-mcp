"""Unit tests for Revolve builder."""

import pytest

from onshape_mcp.builders.revolve import RevolveType, RevolveBuilder


class TestRevolveType:
    """Test RevolveType enum."""

    def test_revolve_type_values(self):
        assert RevolveType.NEW.value == "NEW"
        assert RevolveType.ADD.value == "ADD"
        assert RevolveType.REMOVE.value == "REMOVE"
        assert RevolveType.INTERSECT.value == "INTERSECT"


class TestRevolveBuilder:
    """Test RevolveBuilder functionality."""

    def test_initialization_with_defaults(self):
        revolve = RevolveBuilder()
        assert revolve.name == "Revolve"
        assert revolve.sketch_feature_id is None
        assert revolve.axis == "Y"
        assert revolve.angle == 360.0
        assert revolve.operation_type == RevolveType.NEW
        assert revolve.opposite_direction is False

    def test_initialization_with_custom_values(self):
        revolve = RevolveBuilder(
            name="MyRevolve",
            sketch_feature_id="sketch1",
            axis="X",
            angle=180.0,
            operation_type=RevolveType.ADD,
        )
        assert revolve.name == "MyRevolve"
        assert revolve.sketch_feature_id == "sketch1"
        assert revolve.axis == "X"
        assert revolve.angle == 180.0
        assert revolve.operation_type == RevolveType.ADD

    def test_set_sketch(self):
        revolve = RevolveBuilder()
        result = revolve.set_sketch("sketch_abc")
        assert result is revolve
        assert revolve.sketch_feature_id == "sketch_abc"

    def test_set_angle(self):
        revolve = RevolveBuilder()
        result = revolve.set_angle(90.0)
        assert result is revolve
        assert revolve.angle == 90.0
        assert revolve.angle_variable is None

    def test_set_angle_with_variable(self):
        revolve = RevolveBuilder()
        revolve.set_angle(90.0, variable_name="rev_angle")
        assert revolve.angle == 90.0
        assert revolve.angle_variable == "rev_angle"

    def test_set_axis(self):
        revolve = RevolveBuilder()
        result = revolve.set_axis("Z")
        assert result is revolve
        assert revolve.axis == "Z"

    def test_set_opposite_direction(self):
        revolve = RevolveBuilder()
        result = revolve.set_opposite_direction(True)
        assert result is revolve
        assert revolve.opposite_direction is True

    def test_build_requires_sketch(self):
        revolve = RevolveBuilder()
        with pytest.raises(ValueError, match="Sketch feature ID must be set"):
            revolve.build()

    def test_build_structure(self):
        revolve = RevolveBuilder(name="TestRevolve", sketch_feature_id="sketch1")
        result = revolve.build()

        assert result["btType"] == "BTFeatureDefinitionCall-1406"
        feature = result["feature"]
        assert feature["btType"] == "BTMFeature-134"
        assert feature["featureType"] == "revolve"
        assert feature["name"] == "TestRevolve"

    def test_build_entities_parameter(self):
        revolve = RevolveBuilder(sketch_feature_id="sketch1")
        result = revolve.build()
        params = result["feature"]["parameters"]

        entities = next(p for p in params if p["parameterId"] == "entities")
        assert entities["queries"][0]["btType"] == "BTMIndividualSketchRegionQuery-140"
        assert "sketch1" in entities["queries"][0]["queryString"]

    def test_build_axis_mapping(self):
        for axis, expected in [("X", "RIGHT"), ("Y", "TOP"), ("Z", "FRONT")]:
            revolve = RevolveBuilder(sketch_feature_id="s1", axis=axis)
            result = revolve.build()
            params = result["feature"]["parameters"]
            axis_param = next(p for p in params if p["parameterId"] == "axis")
            assert expected in axis_param["queries"][0]["queryString"]

    def test_build_angle_without_variable(self):
        revolve = RevolveBuilder(sketch_feature_id="s1", angle=180.0)
        result = revolve.build()
        params = result["feature"]["parameters"]

        angle_param = next(p for p in params if p["parameterId"] == "revolveAngle")
        assert angle_param["expression"] == "180.0 deg"
        assert angle_param["value"] == 180.0

    def test_build_angle_with_variable(self):
        revolve = RevolveBuilder(sketch_feature_id="s1")
        revolve.set_angle(90.0, variable_name="a")
        result = revolve.build()
        params = result["feature"]["parameters"]

        angle_param = next(p for p in params if p["parameterId"] == "revolveAngle")
        assert angle_param["expression"] == "#a"

    def test_build_operation_types(self):
        for op in RevolveType:
            revolve = RevolveBuilder(sketch_feature_id="s1", operation_type=op)
            result = revolve.build()
            params = result["feature"]["parameters"]
            op_param = next(p for p in params if p["parameterId"] == "operationType")
            assert op_param["value"] == op.value

    def test_build_opposite_direction(self):
        revolve = RevolveBuilder(sketch_feature_id="s1")
        revolve.set_opposite_direction(True)
        result = revolve.build()
        params = result["feature"]["parameters"]

        opp_param = next(p for p in params if p["parameterId"] == "oppositeDirection")
        assert opp_param["value"] is True

    def test_method_chaining(self):
        revolve = (
            RevolveBuilder(name="Chained")
            .set_sketch("s1")
            .set_axis("X")
            .set_angle(120.0, variable_name="ang")
            .set_opposite_direction(True)
        )
        assert revolve.sketch_feature_id == "s1"
        assert revolve.axis == "X"
        assert revolve.angle == 120.0
        assert revolve.angle_variable == "ang"
        assert revolve.opposite_direction is True
