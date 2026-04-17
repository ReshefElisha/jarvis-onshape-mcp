"""Unit tests for Boolean builder."""

import pytest

from onshape_mcp.builders.boolean import BooleanType, BooleanBuilder


class TestBooleanType:
    """Test BooleanType enum."""

    def test_boolean_type_values(self):
        assert BooleanType.UNION.value == "UNION"
        assert BooleanType.SUBTRACT.value == "SUBTRACT"
        assert BooleanType.INTERSECT.value == "INTERSECT"


class TestBooleanBuilder:
    """Test BooleanBuilder functionality."""

    def test_initialization_with_defaults(self):
        b = BooleanBuilder()
        assert b.name == "Boolean"
        assert b.boolean_type == BooleanType.UNION
        assert b.tool_body_queries == []
        assert b.target_body_queries == []

    def test_initialization_with_custom_values(self):
        b = BooleanBuilder(name="MyBool", boolean_type=BooleanType.SUBTRACT)
        assert b.name == "MyBool"
        assert b.boolean_type == BooleanType.SUBTRACT

    def test_add_tool_body(self):
        b = BooleanBuilder()
        result = b.add_tool_body("body1")
        assert result is b
        assert b.tool_body_queries == ["body1"]

    def test_add_multiple_tool_bodies(self):
        b = BooleanBuilder()
        b.add_tool_body("b1").add_tool_body("b2")
        assert b.tool_body_queries == ["b1", "b2"]

    def test_add_target_body(self):
        b = BooleanBuilder()
        result = b.add_target_body("target1")
        assert result is b
        assert b.target_body_queries == ["target1"]

    def test_build_requires_tool_bodies(self):
        b = BooleanBuilder()
        with pytest.raises(ValueError, match="At least one tool body must be added"):
            b.build()

    def test_build_subtract_requires_target(self):
        b = BooleanBuilder(boolean_type=BooleanType.SUBTRACT)
        b.add_tool_body("tool1")
        with pytest.raises(ValueError, match="At least one target body"):
            b.build()

    def test_build_intersect_requires_target(self):
        b = BooleanBuilder(boolean_type=BooleanType.INTERSECT)
        b.add_tool_body("tool1")
        with pytest.raises(ValueError, match="At least one target body"):
            b.build()

    def test_build_union_does_not_require_target(self):
        b = BooleanBuilder(boolean_type=BooleanType.UNION)
        b.add_tool_body("tool1")
        result = b.build()
        assert result is not None

    def test_build_structure(self):
        b = BooleanBuilder(name="TestBool")
        b.add_tool_body("tool1")
        result = b.build()

        assert result["btType"] == "BTFeatureDefinitionCall-1406"
        feature = result["feature"]
        assert feature["btType"] == "BTMFeature-134"
        assert feature["featureType"] == "boolean"
        assert feature["name"] == "TestBool"

    def test_build_boolean_type_parameter(self):
        for bt in BooleanType:
            b = BooleanBuilder(boolean_type=bt)
            b.add_tool_body("tool1")
            if bt != BooleanType.UNION:
                b.add_target_body("target1")
            result = b.build()
            params = result["feature"]["parameters"]
            type_param = next(
                p for p in params if p["parameterId"] == "booleanOperationType"
            )
            assert type_param["value"] == bt.value

    def test_build_tools_parameter(self):
        b = BooleanBuilder()
        b.add_tool_body("t1").add_tool_body("t2")
        result = b.build()
        params = result["feature"]["parameters"]

        tools = next(p for p in params if p["parameterId"] == "tools")
        assert tools["queries"][0]["deterministicIds"] == ["t1", "t2"]

    def test_build_with_targets(self):
        b = BooleanBuilder(boolean_type=BooleanType.SUBTRACT)
        b.add_tool_body("tool1")
        b.add_target_body("tgt1").add_target_body("tgt2")
        result = b.build()
        params = result["feature"]["parameters"]

        targets = next(p for p in params if p["parameterId"] == "targets")
        assert targets["queries"][0]["deterministicIds"] == ["tgt1", "tgt2"]

    def test_build_union_without_targets_has_no_targets_param(self):
        b = BooleanBuilder(boolean_type=BooleanType.UNION)
        b.add_tool_body("tool1")
        result = b.build()
        params = result["feature"]["parameters"]

        target_params = [p for p in params if p["parameterId"] == "targets"]
        assert len(target_params) == 0

    def test_build_union_with_optional_targets(self):
        b = BooleanBuilder(boolean_type=BooleanType.UNION)
        b.add_tool_body("tool1")
        b.add_target_body("tgt1")
        result = b.build()
        params = result["feature"]["parameters"]

        target_params = [p for p in params if p["parameterId"] == "targets"]
        assert len(target_params) == 1

    def test_method_chaining(self):
        b = (
            BooleanBuilder(name="Chained", boolean_type=BooleanType.SUBTRACT)
            .add_tool_body("t1")
            .add_target_body("tgt1")
        )
        assert b.name == "Chained"
        assert len(b.tool_body_queries) == 1
        assert len(b.target_body_queries) == 1
