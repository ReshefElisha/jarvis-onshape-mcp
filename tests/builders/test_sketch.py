"""Unit tests for Sketch builder - Corrected for actual Onshape API structure."""

import pytest
from onshape_mcp.builders.sketch import SketchBuilder, SketchPlane


class TestSketchPlane:
    """Test SketchPlane enum."""

    def test_sketch_plane_values(self):
        """Test that SketchPlane enum has correct values."""
        assert SketchPlane.FRONT.value == "Front"
        assert SketchPlane.TOP.value == "Top"
        assert SketchPlane.RIGHT.value == "Right"

    def test_sketch_plane_by_name(self):
        """Test accessing SketchPlane by name."""
        assert SketchPlane["FRONT"] == SketchPlane.FRONT
        assert SketchPlane["TOP"] == SketchPlane.TOP
        assert SketchPlane["RIGHT"] == SketchPlane.RIGHT


class TestSketchBuilder:
    """Test SketchBuilder functionality."""

    def test_initialization_with_defaults(self):
        """Test creating a sketch builder with default parameters."""
        sketch = SketchBuilder()

        assert sketch.name == "Sketch"
        assert sketch.plane == SketchPlane.FRONT
        assert sketch.entities == []
        assert sketch.constraints == []

    def test_initialization_with_custom_values(self):
        """Test creating a sketch builder with custom parameters."""
        sketch = SketchBuilder(name="MySketch", plane=SketchPlane.TOP)

        assert sketch.name == "MySketch"
        assert sketch.plane == SketchPlane.TOP

    def test_add_rectangle_basic(self):
        """Test adding a basic rectangle."""
        sketch = SketchBuilder()
        result = sketch.add_rectangle(corner1=(0, 0), corner2=(10, 5))

        # Should return self for chaining
        assert result is sketch

        # Should create 4 line entities (bottom, right, top, left)
        assert len(sketch.entities) == 4

        # Verify each entity has proper Onshape API structure
        for entity in sketch.entities:
            assert entity["btType"] == "BTMSketchCurveSegment-155"
            assert entity["geometry"]["btType"] == "BTCurveGeometryLine-117"
            assert entity["isConstruction"] is False
            assert "entityId" in entity
            assert "startPointId" in entity
            assert "endPointId" in entity

    def test_add_rectangle_creates_constraints(self):
        """Test that adding rectangle creates geometric constraints."""
        sketch = SketchBuilder()
        sketch.add_rectangle(corner1=(0, 0), corner2=(10, 5))

        # Should create multiple constraints (perpendicular, parallel, horizontal, coincident)
        assert len(sketch.constraints) > 0

        # All constraints should have proper Onshape API structure
        for constraint in sketch.constraints:
            assert constraint["btType"] == "BTMSketchConstraint-2"
            assert "constraintType" in constraint
            assert "entityId" in constraint
            assert "parameters" in constraint

    def test_add_rectangle_with_variable_width(self):
        """Test adding rectangle with width variable."""
        sketch = SketchBuilder()
        sketch.add_rectangle(corner1=(0, 0), corner2=(10, 5), variable_width="box_width")

        # Should have additional LENGTH constraint for width
        length_constraints = [c for c in sketch.constraints if c["constraintType"] == "LENGTH"]
        assert len(length_constraints) == 1

        # Check the constraint uses the variable
        width_constraint = length_constraints[0]
        params = width_constraint["parameters"]
        quantity_param = next(p for p in params if p["btType"] == "BTMParameterQuantity-147")
        assert quantity_param["expression"] == "#box_width"

    def test_add_rectangle_with_variable_height(self):
        """Test adding rectangle with height variable."""
        sketch = SketchBuilder()
        sketch.add_rectangle(corner1=(0, 0), corner2=(10, 5), variable_height="box_height")

        # Should have additional LENGTH constraint for height
        length_constraints = [c for c in sketch.constraints if c["constraintType"] == "LENGTH"]
        assert len(length_constraints) == 1

        # Check the constraint uses the variable
        height_constraint = length_constraints[0]
        params = height_constraint["parameters"]
        quantity_param = next(p for p in params if p["btType"] == "BTMParameterQuantity-147")
        assert quantity_param["expression"] == "#box_height"

    def test_add_rectangle_with_both_variables(self):
        """Test adding rectangle with both width and height variables."""
        sketch = SketchBuilder()
        sketch.add_rectangle(
            corner1=(0, 0), corner2=(10, 5), variable_width="width", variable_height="height"
        )

        # Should have 2 LENGTH constraints
        length_constraints = [c for c in sketch.constraints if c["constraintType"] == "LENGTH"]
        assert len(length_constraints) == 2

        # Check both variables are used
        expressions = []
        for constraint in length_constraints:
            params = constraint["parameters"]
            quantity_param = next(p for p in params if p["btType"] == "BTMParameterQuantity-147")
            expressions.append(quantity_param["expression"])

        assert "#width" in expressions
        assert "#height" in expressions

    def test_method_chaining(self):
        """Test that builder methods can be chained."""
        sketch = SketchBuilder(name="Chained").add_rectangle((0, 0), (10, 5))

        # Should have 4 rectangle lines
        assert len(sketch.entities) == 4
        assert sketch.name == "Chained"

    def test_build_requires_plane_id(self):
        """Test that build() requires plane_id to be provided."""
        sketch = SketchBuilder(name="TestSketch", plane=SketchPlane.FRONT)
        sketch.add_rectangle((0, 0), (5, 5))

        # Should raise error if no plane_id provided
        with pytest.raises(ValueError, match="plane_id must be provided"):
            sketch.build()

    def test_build_with_plane_id(self):
        """Test that build() works when plane_id is provided."""
        sketch = SketchBuilder(name="TestSketch", plane=SketchPlane.FRONT)
        sketch.add_rectangle((0, 0), (5, 5))

        result = sketch.build(plane_id="test_plane_id")

        # Verify top-level structure
        assert "feature" in result

        feature = result["feature"]
        assert feature["btType"] == "BTMSketch-151"
        assert feature["name"] == "TestSketch"
        assert "parameters" in feature
        assert "constraints" in feature
        assert "entities" in feature

        # Verify plane parameter
        assert len(feature["parameters"]) > 0
        plane_param = feature["parameters"][0]
        assert plane_param["parameterId"] == "sketchPlane"
        assert plane_param["queries"][0]["deterministicIds"] == ["test_plane_id"]

    def test_build_includes_entities_and_constraints(self):
        """Test that build() includes all entities and constraints."""
        sketch = SketchBuilder(plane_id="test_plane")
        sketch.add_rectangle((0, 0), (10, 5), variable_width="w", variable_height="h")

        result = sketch.build()

        feature = result["feature"]
        # 4 rectangle lines
        assert len(feature["entities"]) == 4
        # Multiple constraints (geometric + 2 dimensional)
        assert len(feature["constraints"]) > 2


# Tests for unimplemented features - mark as skipped
class TestSketchBuilderFutureFeatures:
    """Tests for features not yet implemented."""

    @pytest.mark.skip(reason="add_circle not yet implemented")
    def test_add_circle_basic(self):
        """Test adding a basic circle."""
        sketch = SketchBuilder()
        result = sketch.add_circle(center=(5, 5), radius=3)
        assert result is sketch

    @pytest.mark.skip(reason="add_circle not yet implemented")
    def test_add_circle_with_variable(self):
        """Test adding circle with radius variable."""
        sketch = SketchBuilder()
        sketch.add_circle(center=(5, 5), radius=3, variable_radius="circle_radius")
        assert len(sketch.constraints) >= 1

    @pytest.mark.skip(reason="add_line not yet implemented")
    def test_add_line_basic(self):
        """Test adding a basic line."""
        sketch = SketchBuilder()
        result = sketch.add_line(start=(0, 0), end=(10, 10))
        assert result is sketch

    @pytest.mark.skip(reason="add_line not yet implemented")
    def test_add_line_construction(self):
        """Test adding a construction line."""
        sketch = SketchBuilder()
        sketch.add_line(start=(0, 0), end=(10, 10), is_construction=True)
        assert len(sketch.entities) == 1
