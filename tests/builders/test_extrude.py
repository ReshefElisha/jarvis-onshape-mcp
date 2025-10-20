"""Unit tests for Extrude builder."""

import pytest

from onshape_mcp.builders.extrude import ExtrudeBuilder, ExtrudeType


class TestExtrudeType:
    """Test ExtrudeType enum."""

    def test_extrude_type_values(self):
        """Test that ExtrudeType enum has correct values."""
        assert ExtrudeType.NEW.value == "NEW"
        assert ExtrudeType.ADD.value == "ADD"
        assert ExtrudeType.REMOVE.value == "REMOVE"
        assert ExtrudeType.INTERSECT.value == "INTERSECT"

    def test_extrude_type_by_name(self):
        """Test accessing ExtrudeType by name."""
        assert ExtrudeType["NEW"] == ExtrudeType.NEW
        assert ExtrudeType["ADD"] == ExtrudeType.ADD
        assert ExtrudeType["REMOVE"] == ExtrudeType.REMOVE
        assert ExtrudeType["INTERSECT"] == ExtrudeType.INTERSECT


class TestExtrudeBuilder:
    """Test ExtrudeBuilder functionality."""

    def test_initialization_with_defaults(self):
        """Test creating an extrude builder with default parameters."""
        extrude = ExtrudeBuilder()

        assert extrude.name == "Extrude"
        assert extrude.sketch_feature_id is None
        assert extrude.depth == 1.0
        assert extrude.operation_type == ExtrudeType.NEW
        assert extrude.depth_variable is None

    def test_initialization_with_custom_values(self):
        """Test creating an extrude builder with custom parameters."""
        extrude = ExtrudeBuilder(
            name="MyExtrude",
            sketch_feature_id="sketch123",
            depth=5.0,
            operation_type=ExtrudeType.ADD,
        )

        assert extrude.name == "MyExtrude"
        assert extrude.sketch_feature_id == "sketch123"
        assert extrude.depth == 5.0
        assert extrude.operation_type == ExtrudeType.ADD

    def test_set_depth_basic(self):
        """Test setting depth without variable."""
        extrude = ExtrudeBuilder()
        result = extrude.set_depth(3.5)

        # Should return self for chaining
        assert result is extrude
        assert extrude.depth == 3.5
        assert extrude.depth_variable is None

    def test_set_depth_with_variable(self):
        """Test setting depth with variable reference."""
        extrude = ExtrudeBuilder()
        extrude.set_depth(2.0, variable_name="extrude_depth")

        assert extrude.depth == 2.0
        assert extrude.depth_variable == "extrude_depth"

    def test_set_sketch(self):
        """Test setting sketch feature ID."""
        extrude = ExtrudeBuilder()
        result = extrude.set_sketch("sketch_abc123")

        # Should return self for chaining
        assert result is extrude
        assert extrude.sketch_feature_id == "sketch_abc123"

    def test_method_chaining(self):
        """Test that builder methods can be chained."""
        extrude = (
            ExtrudeBuilder(name="Chained")
            .set_sketch("sketch1")
            .set_depth(4.0, variable_name="depth")
        )

        assert extrude.sketch_feature_id == "sketch1"
        assert extrude.depth == 4.0
        assert extrude.depth_variable == "depth"

    def test_build_requires_sketch_feature_id(self):
        """Test that build() raises error if sketch_feature_id not set."""
        extrude = ExtrudeBuilder()

        with pytest.raises(ValueError) as exc_info:
            extrude.build()

        assert "Sketch feature ID must be set" in str(exc_info.value)

    def test_build_with_sketch_succeeds(self):
        """Test that build() succeeds when sketch_feature_id is set."""
        extrude = ExtrudeBuilder(sketch_feature_id="sketch123")

        result = extrude.build()

        assert result is not None
        assert "btType" in result

    def test_build_returns_valid_structure(self):
        """Test that build() returns valid Onshape feature structure."""
        extrude = ExtrudeBuilder(name="TestExtrude", sketch_feature_id="sketch123", depth=2.5)

        result = extrude.build()

        # Verify top-level structure (BTFeatureDefinitionCall wrapper)
        assert result["btType"] == "BTFeatureDefinitionCall-1406"
        assert "feature" in result

        feature = result["feature"]
        assert feature["btType"] == "BTMFeature-134"
        assert feature["featureType"] == "extrude"
        assert feature["name"] == "TestExtrude"
        assert "parameters" in feature

    def test_build_includes_entities_parameter(self):
        """Test that build() includes entities parameter with sketch query."""
        sketch_id = "sketch_abc"
        extrude = ExtrudeBuilder(sketch_feature_id=sketch_id)

        result = extrude.build()
        parameters = result["feature"]["parameters"]

        # Find entities parameter
        entities_param = next(p for p in parameters if p["parameterId"] == "entities")

        assert entities_param["btType"] == "BTMParameterQueryList-148"
        assert len(entities_param["queries"]) > 0

        query = entities_param["queries"][0]
        # The actual implementation uses "queryString" field with qSketchRegion
        assert query["btType"] == "BTMIndividualSketchRegionQuery-140"
        assert "queryString" in query
        assert sketch_id in query["queryString"]
        assert "qSketchRegion" in query["queryString"]

    def test_build_includes_operation_type_parameter(self):
        """Test that build() includes operation type parameter."""
        extrude = ExtrudeBuilder(sketch_feature_id="sketch1", operation_type=ExtrudeType.ADD)

        result = extrude.build()
        parameters = result["feature"]["parameters"]

        op_param = next(p for p in parameters if p["parameterId"] == "operationType")

        assert op_param["btType"] == "BTMParameterEnum-145"
        assert op_param["value"] == "ADD"

    def test_build_depth_parameter_without_variable(self):
        """Test depth parameter when no variable is set."""
        extrude = ExtrudeBuilder(sketch_feature_id="sketch1", depth=3.5)

        result = extrude.build()
        parameters = result["feature"]["parameters"]

        depth_param = next(p for p in parameters if p["parameterId"] == "depth")

        assert depth_param["btType"] == "BTMParameterQuantity-147"
        assert depth_param["expression"] == "3.5 in"
        assert depth_param["value"] == 3.5
        assert depth_param["isInteger"] is False

    def test_build_depth_parameter_with_variable(self):
        """Test depth parameter when variable is set."""
        extrude = ExtrudeBuilder(sketch_feature_id="sketch1")
        extrude.set_depth(2.0, variable_name="part_depth")

        result = extrude.build()
        parameters = result["feature"]["parameters"]

        depth_param = next(p for p in parameters if p["parameterId"] == "depth")

        assert depth_param["expression"] == "#part_depth"
        assert depth_param["value"] == 2.0

    def test_build_includes_opposite_direction_parameter(self):
        """Test that build() includes oppositeDirection parameter."""
        extrude = ExtrudeBuilder(sketch_feature_id="sketch1")

        result = extrude.build()
        parameters = result["feature"]["parameters"]

        opposite_param = next(p for p in parameters if p["parameterId"] == "oppositeDirection")

        assert opposite_param["btType"] == "BTMParameterBoolean-144"
        assert opposite_param["value"] is False

    def test_build_all_operation_types(self):
        """Test build() with all operation types."""
        operation_types = [
            ExtrudeType.NEW,
            ExtrudeType.ADD,
            ExtrudeType.REMOVE,
            ExtrudeType.INTERSECT,
        ]

        for op_type in operation_types:
            extrude = ExtrudeBuilder(sketch_feature_id="sketch1", operation_type=op_type)

            result = extrude.build()
            parameters = result["feature"]["parameters"]

            op_param = next(p for p in parameters if p["parameterId"] == "operationType")

            assert op_param["value"] == op_type.value

    def test_build_with_all_parameters(self):
        """Test build() with all parameters set."""
        extrude = ExtrudeBuilder(
            name="CompleteExtrude",
            sketch_feature_id="sketch_xyz",
            depth=4.25,
            operation_type=ExtrudeType.REMOVE,
        )
        extrude.set_depth(4.25, variable_name="depth_var")

        result = extrude.build()

        assert result["feature"]["name"] == "CompleteExtrude"

        parameters = result["feature"]["parameters"]
        assert len(parameters) == 4  # entities, operationType, depth, oppositeDirection

    def test_zero_depth(self):
        """Test handling zero depth."""
        extrude = ExtrudeBuilder(sketch_feature_id="sketch1", depth=0)

        result = extrude.build()
        parameters = result["feature"]["parameters"]

        depth_param = next(p for p in parameters if p["parameterId"] == "depth")

        assert depth_param["value"] == 0

    def test_negative_depth(self):
        """Test handling negative depth."""
        extrude = ExtrudeBuilder(sketch_feature_id="sketch1", depth=-5.0)

        result = extrude.build()
        parameters = result["feature"]["parameters"]

        depth_param = next(p for p in parameters if p["parameterId"] == "depth")

        assert depth_param["value"] == -5.0
