"""Unit tests for Thicken builder."""

import pytest
from onshape_mcp.builders.thicken import ThickenBuilder, ThickenType


class TestThickenType:
    """Test ThickenType enum."""

    def test_thicken_type_values(self):
        """Test that ThickenType enum has correct values."""
        assert ThickenType.NEW.value == "NEW"
        assert ThickenType.ADD.value == "ADD"
        assert ThickenType.REMOVE.value == "REMOVE"
        assert ThickenType.INTERSECT.value == "INTERSECT"

    def test_thicken_type_by_name(self):
        """Test accessing ThickenType by name."""
        assert ThickenType["NEW"] == ThickenType.NEW
        assert ThickenType["ADD"] == ThickenType.ADD
        assert ThickenType["REMOVE"] == ThickenType.REMOVE
        assert ThickenType["INTERSECT"] == ThickenType.INTERSECT


class TestThickenBuilder:
    """Test ThickenBuilder functionality."""

    def test_initialization_with_defaults(self):
        """Test creating a thicken builder with minimum parameters."""
        thicken = ThickenBuilder(name="MyThicken", sketch_feature_id="sketch123")

        assert thicken.name == "MyThicken"
        assert thicken.sketch_feature_id == "sketch123"
        assert thicken.operation_type == ThickenType.NEW
        assert thicken.thickness_value is None
        assert thicken.thickness_variable is None
        assert thicken.midplane is False
        assert thicken.opposite_direction is False

    def test_initialization_with_custom_operation_type(self):
        """Test creating a thicken builder with custom operation type."""
        thicken = ThickenBuilder(
            name="MyThicken", sketch_feature_id="sketch123", operation_type=ThickenType.ADD
        )

        assert thicken.operation_type == ThickenType.ADD

    def test_set_thickness_basic(self):
        """Test setting thickness without variable."""
        thicken = ThickenBuilder(name="Test", sketch_feature_id="sketch1")
        result = thicken.set_thickness(0.5)

        # Should return self for chaining
        assert result is thicken
        assert thicken.thickness_value == 0.5
        assert thicken.thickness_variable is None

    def test_set_thickness_with_variable(self):
        """Test setting thickness with variable reference."""
        thicken = ThickenBuilder(name="Test", sketch_feature_id="sketch1")
        thicken.set_thickness(0.75, variable_name="panel_thickness")

        assert thicken.thickness_value == 0.75
        assert thicken.thickness_variable == "panel_thickness"

    def test_set_midplane(self):
        """Test setting midplane option."""
        thicken = ThickenBuilder(name="Test", sketch_feature_id="sketch1")
        result = thicken.set_midplane(True)

        # Should return self for chaining
        assert result is thicken
        assert thicken.midplane is True

    def test_set_midplane_default(self):
        """Test setting midplane with default parameter."""
        thicken = ThickenBuilder(name="Test", sketch_feature_id="sketch1")
        thicken.set_midplane()

        assert thicken.midplane is True

    def test_set_opposite_direction(self):
        """Test setting opposite direction option."""
        thicken = ThickenBuilder(name="Test", sketch_feature_id="sketch1")
        result = thicken.set_opposite_direction(True)

        # Should return self for chaining
        assert result is thicken
        assert thicken.opposite_direction is True

    def test_set_opposite_direction_default(self):
        """Test setting opposite direction with default parameter."""
        thicken = ThickenBuilder(name="Test", sketch_feature_id="sketch1")
        thicken.set_opposite_direction()

        assert thicken.opposite_direction is True

    def test_method_chaining(self):
        """Test that builder methods can be chained."""
        thicken = (
            ThickenBuilder(name="Chained", sketch_feature_id="sketch1")
            .set_thickness(0.25)
            .set_midplane(True)
            .set_opposite_direction(False)
        )

        assert thicken.thickness_value == 0.25
        assert thicken.midplane is True
        assert thicken.opposite_direction is False

    def test_build_raises_error_without_thickness(self):
        """Test that build() raises error if thickness not set."""
        thicken = ThickenBuilder(name="Test", sketch_feature_id="sketch1")

        with pytest.raises(ValueError, match="Thickness must be set"):
            thicken.build()

    def test_build_with_basic_thickness(self):
        """Test building thicken feature with basic thickness value."""
        thicken = ThickenBuilder(name="BasicThicken", sketch_feature_id="sketch123")
        thicken.set_thickness(0.5)

        result = thicken.build()

        # Verify top-level structure
        assert result["btType"] == "BTMFeature-134"
        assert result["name"] == "BasicThicken"
        assert result["featureType"] == "thicken"
        assert result["suppressed"] is False
        assert "parameters" in result

    def test_build_with_variable_thickness(self):
        """Test building thicken feature with variable thickness."""
        thicken = ThickenBuilder(name="VarThicken", sketch_feature_id="sketch123")
        thicken.set_thickness(0.75, variable_name="wall_thickness")

        result = thicken.build()
        parameters = result["parameters"]

        # Find thickness parameter
        thickness_param = next(p for p in parameters if p["parameterId"] == "thickness1")

        assert thickness_param["btType"] == "BTMParameterQuantity-147"
        assert thickness_param["expression"] == "#wall_thickness"

    def test_build_with_literal_thickness_expression(self):
        """Test that literal thickness gets ' in' suffix."""
        thicken = ThickenBuilder(name="Test", sketch_feature_id="sketch1")
        thicken.set_thickness(1.25)

        result = thicken.build()
        parameters = result["parameters"]

        thickness_param = next(p for p in parameters if p["parameterId"] == "thickness1")
        assert thickness_param["expression"] == "1.25 in"

    def test_build_includes_operation_type(self):
        """Test that build() includes operation type parameter."""
        thicken = ThickenBuilder(
            name="Test", sketch_feature_id="sketch1", operation_type=ThickenType.REMOVE
        )
        thicken.set_thickness(0.5)

        result = thicken.build()
        parameters = result["parameters"]

        op_param = next(p for p in parameters if p["parameterId"] == "operationType")

        assert op_param["btType"] == "BTMParameterEnum-145"
        assert op_param["enumName"] == "NewBodyOperationType"
        assert op_param["value"] == "REMOVE"

    def test_build_includes_entities_query(self):
        """Test that build() includes sketch region query."""
        sketch_id = "my_sketch_feature"
        thicken = ThickenBuilder(name="Test", sketch_feature_id=sketch_id)
        thicken.set_thickness(0.5)

        result = thicken.build()
        parameters = result["parameters"]

        entities_param = next(p for p in parameters if p["parameterId"] == "entities")

        assert entities_param["btType"] == "BTMParameterQueryList-148"
        assert len(entities_param["queries"]) == 1

        query = entities_param["queries"][0]
        assert query["btType"] == "BTMIndividualSketchRegionQuery-140"
        assert query["filterInnerLoops"] is True
        assert sketch_id in query["queryString"]
        assert "qSketchRegion" in query["queryString"]
        assert query["featureId"] == sketch_id

    def test_build_includes_midplane_parameter(self):
        """Test that build() includes midplane parameter."""
        thicken = ThickenBuilder(name="Test", sketch_feature_id="sketch1")
        thicken.set_thickness(0.5).set_midplane(True)

        result = thicken.build()
        parameters = result["parameters"]

        midplane_param = next(p for p in parameters if p["parameterId"] == "midplane")

        assert midplane_param["btType"] == "BTMParameterBoolean-144"
        assert midplane_param["value"] is True

    def test_build_includes_opposite_direction_parameter(self):
        """Test that build() includes opposite direction parameter."""
        thicken = ThickenBuilder(name="Test", sketch_feature_id="sketch1")
        thicken.set_thickness(0.5).set_opposite_direction(True)

        result = thicken.build()
        parameters = result["parameters"]

        opposite_param = next(p for p in parameters if p["parameterId"] == "oppositeDirection")

        assert opposite_param["btType"] == "BTMParameterBoolean-144"
        assert opposite_param["value"] is True

    def test_build_midplane_defaults_to_false(self):
        """Test that midplane defaults to False when not set."""
        thicken = ThickenBuilder(name="Test", sketch_feature_id="sketch1")
        thicken.set_thickness(0.5)

        result = thicken.build()
        parameters = result["parameters"]

        midplane_param = next(p for p in parameters if p["parameterId"] == "midplane")
        assert midplane_param["value"] is False

    def test_build_opposite_direction_defaults_to_false(self):
        """Test that opposite direction defaults to False when not set."""
        thicken = ThickenBuilder(name="Test", sketch_feature_id="sketch1")
        thicken.set_thickness(0.5)

        result = thicken.build()
        parameters = result["parameters"]

        opposite_param = next(p for p in parameters if p["parameterId"] == "oppositeDirection")
        assert opposite_param["value"] is False

    def test_build_includes_thickness2_parameter(self):
        """Test that build() includes thickness2 parameter (always 0)."""
        thicken = ThickenBuilder(name="Test", sketch_feature_id="sketch1")
        thicken.set_thickness(0.5)

        result = thicken.build()
        parameters = result["parameters"]

        thickness2_param = next(p for p in parameters if p["parameterId"] == "thickness2")

        assert thickness2_param["btType"] == "BTMParameterQuantity-147"
        assert thickness2_param["expression"] == "0 in"

    def test_build_complete_feature_with_all_options(self):
        """Test building a complete thicken feature with all options set."""
        thicken = (
            ThickenBuilder(
                name="CompleteThicken",
                sketch_feature_id="sketch_xyz",
                operation_type=ThickenType.ADD,
            )
            .set_thickness(0.375, variable_name="sheet_thickness")
            .set_midplane(True)
            .set_opposite_direction(False)
        )

        result = thicken.build()

        # Verify structure
        assert result["btType"] == "BTMFeature-134"
        assert result["name"] == "CompleteThicken"
        assert result["featureType"] == "thicken"
        assert len(result["parameters"]) == 6

        # Verify all parameters are present
        param_ids = [p["parameterId"] for p in result["parameters"]]
        assert "operationType" in param_ids
        assert "entities" in param_ids
        assert "midplane" in param_ids
        assert "thickness1" in param_ids
        assert "oppositeDirection" in param_ids
        assert "thickness2" in param_ids
