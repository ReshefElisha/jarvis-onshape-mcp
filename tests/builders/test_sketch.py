"""Unit tests for Sketch builder - Corrected for actual Onshape API structure."""

import math

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


class TestSketchBuilderCircle:
    """Test add_circle functionality."""

    def test_add_circle_returns_self(self):
        sketch = SketchBuilder()
        result = sketch.add_circle(center=(5, 5), radius=3)
        assert result is sketch

    def test_add_circle_creates_two_arcs(self):
        sketch = SketchBuilder()
        sketch.add_circle(center=(5, 5), radius=3)
        assert len(sketch.entities) == 2

        for entity in sketch.entities:
            assert entity["btType"] == "BTMSketchCurveSegment-155"
            assert entity["geometry"]["btType"] == "BTCurveGeometryCircle-115"
            assert entity["isConstruction"] is False

    def test_add_circle_arcs_form_full_circle(self):
        sketch = SketchBuilder()
        sketch.add_circle(center=(0, 0), radius=1)

        arc1, arc2 = sketch.entities
        assert arc1["startParam"] == 0.0
        assert abs(arc1["endParam"] - math.pi) < 1e-10
        assert abs(arc2["startParam"] - math.pi) < 1e-10
        assert abs(arc2["endParam"] - 2.0 * math.pi) < 1e-10

    def test_add_circle_converts_to_meters(self):
        sketch = SketchBuilder()
        sketch.add_circle(center=(1.0, 2.0), radius=3.0)

        geo = sketch.entities[0]["geometry"]
        assert abs(geo["xCenter"] - 1.0 * 0.0254) < 1e-10
        assert abs(geo["yCenter"] - 2.0 * 0.0254) < 1e-10
        assert abs(geo["radius"] - 3.0 * 0.0254) < 1e-10

    def test_add_circle_adds_coincident_constraints(self):
        sketch = SketchBuilder()
        sketch.add_circle(center=(0, 0), radius=1)
        assert len(sketch.constraints) == 2
        assert sketch.constraints[0]["constraintType"] == "COINCIDENT"
        assert sketch.constraints[1]["constraintType"] == "COINCIDENT"

    def test_add_circle_construction(self):
        sketch = SketchBuilder()
        sketch.add_circle(center=(0, 0), radius=1, is_construction=True)
        assert sketch.entities[0]["isConstruction"] is True
        assert sketch.entities[1]["isConstruction"] is True


class TestSketchBuilderArc:
    """Test add_arc functionality."""

    def test_add_arc_returns_self(self):
        sketch = SketchBuilder()
        result = sketch.add_arc(center=(0, 0), radius=5, start_angle=0, end_angle=90)
        assert result is sketch

    def test_add_arc_creates_entity(self):
        sketch = SketchBuilder()
        sketch.add_arc(center=(1, 2), radius=3, start_angle=0, end_angle=180)
        assert len(sketch.entities) == 1

        entity = sketch.entities[0]
        assert entity["btType"] == "BTMSketchCurveSegment-155"
        assert entity["geometry"]["btType"] == "BTCurveGeometryCircle-115"

    def test_add_arc_converts_angles_to_radians(self):
        sketch = SketchBuilder()
        sketch.add_arc(center=(0, 0), radius=1, start_angle=45, end_angle=135)

        entity = sketch.entities[0]
        assert abs(entity["startParam"] - math.radians(45)) < 1e-10
        assert abs(entity["endParam"] - math.radians(135)) < 1e-10

    def test_add_arc_construction(self):
        sketch = SketchBuilder()
        sketch.add_arc(center=(0, 0), radius=1, is_construction=True)
        assert sketch.entities[0]["isConstruction"] is True


class TestSketchBuilderLine:
    """Test add_line functionality."""

    def test_add_line_returns_self(self):
        sketch = SketchBuilder()
        result = sketch.add_line(start=(0, 0), end=(10, 10))
        assert result is sketch

    def test_add_line_creates_entity(self):
        sketch = SketchBuilder()
        sketch.add_line(start=(0, 0), end=(10, 0))
        assert len(sketch.entities) == 1

        entity = sketch.entities[0]
        assert entity["btType"] == "BTMSketchCurveSegment-155"
        assert entity["geometry"]["btType"] == "BTCurveGeometryLine-117"
        assert entity["isConstruction"] is False

    def test_add_line_direction_horizontal(self):
        sketch = SketchBuilder()
        sketch.add_line(start=(0, 0), end=(10, 0))

        geo = sketch.entities[0]["geometry"]
        assert abs(geo["dirX"] - 1.0) < 1e-10
        assert abs(geo["dirY"] - 0.0) < 1e-10

    def test_add_line_direction_vertical(self):
        sketch = SketchBuilder()
        sketch.add_line(start=(0, 0), end=(0, 5))

        geo = sketch.entities[0]["geometry"]
        assert abs(geo["dirX"] - 0.0) < 1e-10
        assert abs(geo["dirY"] - 1.0) < 1e-10

    def test_add_line_construction(self):
        sketch = SketchBuilder()
        sketch.add_line(start=(0, 0), end=(10, 10), is_construction=True)
        assert sketch.entities[0]["isConstruction"] is True

    def test_add_line_zero_length_raises(self):
        sketch = SketchBuilder()
        with pytest.raises(ValueError, match="Line start and end points must be different"):
            sketch.add_line(start=(5, 5), end=(5, 5))


class TestSketchBuilderPolygon:
    """Test add_polygon functionality."""

    def test_add_polygon_returns_self(self):
        sketch = SketchBuilder()
        result = sketch.add_polygon(center=(0, 0), sides=6, radius=5)
        assert result is sketch

    def test_add_polygon_triangle(self):
        sketch = SketchBuilder()
        sketch.add_polygon(center=(0, 0), sides=3, radius=5)
        assert len(sketch.entities) == 3

    def test_add_polygon_hexagon(self):
        sketch = SketchBuilder()
        sketch.add_polygon(center=(0, 0), sides=6, radius=5)
        assert len(sketch.entities) == 6

    def test_add_polygon_all_lines(self):
        sketch = SketchBuilder()
        sketch.add_polygon(center=(0, 0), sides=4, radius=5)
        for entity in sketch.entities:
            assert entity["geometry"]["btType"] == "BTCurveGeometryLine-117"

    def test_add_polygon_less_than_3_sides_raises(self):
        sketch = SketchBuilder()
        with pytest.raises(ValueError, match="Polygon must have at least 3 sides"):
            sketch.add_polygon(center=(0, 0), sides=2, radius=5)

    def test_add_polygon_construction(self):
        sketch = SketchBuilder()
        sketch.add_polygon(center=(0, 0), sides=4, radius=5, is_construction=True)
        for entity in sketch.entities:
            assert entity["isConstruction"] is True

    def test_mixed_entities(self):
        """Test combining different entity types in one sketch."""
        sketch = SketchBuilder(plane_id="plane1")
        sketch.add_rectangle((0, 0), (10, 5))
        sketch.add_circle((5, 2.5), 1)
        sketch.add_line((0, 0), (10, 5))

        # 4 rect lines + 2 circle arcs + 1 line
        assert len(sketch.entities) == 7

        result = sketch.build()
        assert len(result["feature"]["entities"]) == 7
