"""Unit tests for Pattern builders."""

import pytest

from onshape_mcp.builders.pattern import (
    PatternType,
    LinearPatternBuilder,
    CircularPatternBuilder,
)


class TestPatternType:
    """Test PatternType enum."""

    def test_pattern_type_values(self):
        assert PatternType.PART.value == "PART"
        assert PatternType.FEATURE.value == "FEATURE"
        assert PatternType.FACE.value == "FACE"


class TestLinearPatternBuilder:
    """Test LinearPatternBuilder functionality."""

    def test_initialization_with_defaults(self):
        lp = LinearPatternBuilder()
        assert lp.name == "Linear pattern"
        assert lp.distance == 1.0
        assert lp.count == 2
        assert lp.distance_variable is None
        assert lp.feature_queries == []
        assert lp.direction_axis == "X"

    def test_initialization_with_custom_values(self):
        lp = LinearPatternBuilder(name="MyPattern", distance=2.5, count=5)
        assert lp.name == "MyPattern"
        assert lp.distance == 2.5
        assert lp.count == 5

    def test_set_distance(self):
        lp = LinearPatternBuilder()
        result = lp.set_distance(3.0)
        assert result is lp
        assert lp.distance == 3.0

    def test_set_distance_with_variable(self):
        lp = LinearPatternBuilder()
        lp.set_distance(3.0, variable_name="spacing")
        assert lp.distance_variable == "spacing"

    def test_set_count(self):
        lp = LinearPatternBuilder()
        result = lp.set_count(10)
        assert result is lp
        assert lp.count == 10

    def test_add_feature(self):
        lp = LinearPatternBuilder()
        result = lp.add_feature("feat1")
        assert result is lp
        assert lp.feature_queries == ["feat1"]

    def test_set_direction(self):
        lp = LinearPatternBuilder()
        result = lp.set_direction("Z")
        assert result is lp
        assert lp.direction_axis == "Z"

    def test_build_requires_features(self):
        lp = LinearPatternBuilder()
        with pytest.raises(ValueError, match="At least one feature must be added"):
            lp.build()

    def test_build_structure(self):
        lp = LinearPatternBuilder(name="TestLP")
        lp.add_feature("feat1")
        result = lp.build()

        assert result["btType"] == "BTFeatureDefinitionCall-1406"
        feature = result["feature"]
        assert feature["btType"] == "BTMFeature-134"
        assert feature["featureType"] == "linearPattern"
        assert feature["name"] == "TestLP"

    def test_build_entities_parameter(self):
        lp = LinearPatternBuilder()
        lp.add_feature("f1").add_feature("f2")
        result = lp.build()
        params = result["feature"]["parameters"]

        entities = next(p for p in params if p["parameterId"] == "entities")
        assert entities["queries"][0]["deterministicIds"] == ["f1", "f2"]

    def test_build_direction_mapping(self):
        for axis, expected in [("X", "RIGHT"), ("Y", "TOP"), ("Z", "FRONT")]:
            lp = LinearPatternBuilder()
            lp.add_feature("f1").set_direction(axis)
            result = lp.build()
            params = result["feature"]["parameters"]
            dir_param = next(p for p in params if p["parameterId"] == "directionQuery")
            assert expected in dir_param["queries"][0]["queryString"]

    def test_build_distance_without_variable(self):
        lp = LinearPatternBuilder(distance=2.5)
        lp.add_feature("f1")
        result = lp.build()
        params = result["feature"]["parameters"]

        dist = next(p for p in params if p["parameterId"] == "distance")
        assert dist["expression"] == "2.5 in"
        assert dist["value"] == 2.5

    def test_build_distance_with_variable(self):
        lp = LinearPatternBuilder()
        lp.set_distance(2.0, variable_name="d")
        lp.add_feature("f1")
        result = lp.build()
        params = result["feature"]["parameters"]

        dist = next(p for p in params if p["parameterId"] == "distance")
        assert dist["expression"] == "#d"

    def test_build_count_parameter(self):
        lp = LinearPatternBuilder(count=5)
        lp.add_feature("f1")
        result = lp.build()
        params = result["feature"]["parameters"]

        count_param = next(p for p in params if p["parameterId"] == "instanceCount")
        assert count_param["value"] == 5
        assert count_param["isInteger"] is True
        assert count_param["expression"] == "5"

    def test_build_pattern_type_is_feature(self):
        lp = LinearPatternBuilder()
        lp.add_feature("f1")
        result = lp.build()
        params = result["feature"]["parameters"]

        pt = next(p for p in params if p["parameterId"] == "patternType")
        assert pt["value"] == "FEATURE"


class TestCircularPatternBuilder:
    """Test CircularPatternBuilder functionality."""

    def test_initialization_with_defaults(self):
        cp = CircularPatternBuilder()
        assert cp.name == "Circular pattern"
        assert cp.count == 4
        assert cp.angle == 360.0
        assert cp.angle_variable is None
        assert cp.feature_queries == []
        assert cp.axis == "Z"

    def test_initialization_with_custom_values(self):
        cp = CircularPatternBuilder(name="MyCircular", count=8)
        assert cp.name == "MyCircular"
        assert cp.count == 8

    def test_set_count(self):
        cp = CircularPatternBuilder()
        result = cp.set_count(6)
        assert result is cp
        assert cp.count == 6

    def test_set_angle(self):
        cp = CircularPatternBuilder()
        result = cp.set_angle(180.0)
        assert result is cp
        assert cp.angle == 180.0

    def test_set_angle_with_variable(self):
        cp = CircularPatternBuilder()
        cp.set_angle(120.0, variable_name="spread")
        assert cp.angle == 120.0
        assert cp.angle_variable == "spread"

    def test_add_feature(self):
        cp = CircularPatternBuilder()
        result = cp.add_feature("feat1")
        assert result is cp
        assert cp.feature_queries == ["feat1"]

    def test_set_axis(self):
        cp = CircularPatternBuilder()
        result = cp.set_axis("X")
        assert result is cp
        assert cp.axis == "X"

    def test_build_requires_features(self):
        cp = CircularPatternBuilder()
        with pytest.raises(ValueError, match="At least one feature must be added"):
            cp.build()

    def test_build_structure(self):
        cp = CircularPatternBuilder(name="TestCP")
        cp.add_feature("f1")
        result = cp.build()

        assert result["btType"] == "BTFeatureDefinitionCall-1406"
        feature = result["feature"]
        assert feature["btType"] == "BTMFeature-134"
        assert feature["featureType"] == "circularPattern"
        assert feature["name"] == "TestCP"

    def test_build_axis_mapping(self):
        for axis, expected in [("X", "RIGHT"), ("Y", "TOP"), ("Z", "FRONT")]:
            cp = CircularPatternBuilder()
            cp.add_feature("f1").set_axis(axis)
            result = cp.build()
            params = result["feature"]["parameters"]
            axis_param = next(p for p in params if p["parameterId"] == "axisQuery")
            assert expected in axis_param["queries"][0]["queryString"]

    def test_build_angle_without_variable(self):
        cp = CircularPatternBuilder()
        cp.add_feature("f1")
        result = cp.build()
        params = result["feature"]["parameters"]

        angle = next(p for p in params if p["parameterId"] == "angle")
        assert angle["expression"] == "360.0 deg"

    def test_build_angle_with_variable(self):
        cp = CircularPatternBuilder()
        cp.set_angle(180.0, variable_name="ang")
        cp.add_feature("f1")
        result = cp.build()
        params = result["feature"]["parameters"]

        angle = next(p for p in params if p["parameterId"] == "angle")
        assert angle["expression"] == "#ang"

    def test_build_count_parameter(self):
        cp = CircularPatternBuilder(count=6)
        cp.add_feature("f1")
        result = cp.build()
        params = result["feature"]["parameters"]

        count_param = next(p for p in params if p["parameterId"] == "instanceCount")
        assert count_param["value"] == 6
        assert count_param["isInteger"] is True

    def test_method_chaining(self):
        cp = (
            CircularPatternBuilder(name="Chained")
            .set_count(8)
            .set_angle(270.0, variable_name="a")
            .set_axis("Y")
            .add_feature("f1")
        )
        assert cp.count == 8
        assert cp.angle == 270.0
        assert cp.axis == "Y"
        assert len(cp.feature_queries) == 1
