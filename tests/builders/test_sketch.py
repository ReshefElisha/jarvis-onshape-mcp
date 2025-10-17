"""Unit tests for Sketch builder."""

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

        # Should create 4 line entities
        assert len(sketch.entities) == 4

        # Verify each entity is a line
        for entity in sketch.entities:
            assert entity["type"] == "BTCurveGeometryLine"
            assert "startPoint" in entity
            assert "endPoint" in entity
            assert entity["isConstruction"] is False

    def test_add_rectangle_forms_closed_loop(self):
        """Test that rectangle lines form a closed loop."""
        sketch = SketchBuilder()
        sketch.add_rectangle(corner1=(1, 2), corner2=(6, 8))

        entities = sketch.entities

        # Bottom line: (1,2) to (6,2)
        assert entities[0]["startPoint"] == [1, 2]
        assert entities[0]["endPoint"] == [6, 2]

        # Right line: (6,2) to (6,8)
        assert entities[1]["startPoint"] == [6, 2]
        assert entities[1]["endPoint"] == [6, 8]

        # Top line: (6,8) to (1,8)
        assert entities[2]["startPoint"] == [6, 8]
        assert entities[2]["endPoint"] == [1, 8]

        # Left line: (1,8) to (1,2)
        assert entities[3]["startPoint"] == [1, 8]
        assert entities[3]["endPoint"] == [1, 2]

    def test_add_rectangle_with_variable_width(self):
        """Test adding rectangle with width variable."""
        sketch = SketchBuilder()
        sketch.add_rectangle(corner1=(0, 0), corner2=(10, 5), variable_width="box_width")

        # Should have a constraint for width
        assert len(sketch.constraints) == 1
        assert sketch.constraints[0]["type"] == "horizontal"
        assert sketch.constraints[0]["value"] == 10
        assert sketch.constraints[0]["expression"] == "#box_width"

    def test_add_rectangle_with_variable_height(self):
        """Test adding rectangle with height variable."""
        sketch = SketchBuilder()
        sketch.add_rectangle(corner1=(0, 0), corner2=(10, 5), variable_height="box_height")

        # Should have a constraint for height
        assert len(sketch.constraints) == 1
        assert sketch.constraints[0]["type"] == "vertical"
        assert sketch.constraints[0]["value"] == 5
        assert sketch.constraints[0]["expression"] == "#box_height"

    def test_add_rectangle_with_both_variables(self):
        """Test adding rectangle with both width and height variables."""
        sketch = SketchBuilder()
        sketch.add_rectangle(
            corner1=(0, 0), corner2=(10, 5), variable_width="width", variable_height="height"
        )

        # Should have 2 constraints
        assert len(sketch.constraints) == 2
        assert any(c["expression"] == "#width" for c in sketch.constraints)
        assert any(c["expression"] == "#height" for c in sketch.constraints)

    def test_add_circle_basic(self):
        """Test adding a basic circle."""
        sketch = SketchBuilder()
        result = sketch.add_circle(center=(5, 5), radius=3)

        # Should return self for chaining
        assert result is sketch

        # Should create 1 circle entity
        assert len(sketch.entities) == 1

        circle = sketch.entities[0]
        assert circle["type"] == "BTCurveGeometryCircle"
        assert circle["center"] == [5, 5]
        assert circle["radius"] == 3
        assert circle["isConstruction"] is False

    def test_add_circle_with_variable(self):
        """Test adding circle with radius variable."""
        sketch = SketchBuilder()
        sketch.add_circle(center=(5, 5), radius=3, variable_radius="circle_radius")

        # Should have a constraint for radius
        assert len(sketch.constraints) == 1
        assert sketch.constraints[0]["type"] == "radius"
        assert sketch.constraints[0]["value"] == 3
        assert sketch.constraints[0]["expression"] == "#circle_radius"

    def test_add_line_basic(self):
        """Test adding a basic line."""
        sketch = SketchBuilder()
        result = sketch.add_line(start=(0, 0), end=(10, 10))

        # Should return self for chaining
        assert result is sketch

        # Should create 1 line entity
        assert len(sketch.entities) == 1

        line = sketch.entities[0]
        assert line["type"] == "BTCurveGeometryLine"
        assert line["startPoint"] == [0, 0]
        assert line["endPoint"] == [10, 10]
        assert line["isConstruction"] is False

    def test_add_line_construction(self):
        """Test adding a construction line."""
        sketch = SketchBuilder()
        sketch.add_line(start=(0, 0), end=(10, 10), is_construction=True)

        line = sketch.entities[0]
        assert line["isConstruction"] is True

    def test_method_chaining(self):
        """Test that builder methods can be chained."""
        sketch = (
            SketchBuilder(name="Chained")
            .add_rectangle((0, 0), (10, 5))
            .add_circle((5, 2.5), 1)
            .add_line((0, 0), (10, 5), is_construction=True)
        )

        # Should have rectangle (4 lines) + circle (1) + line (1) = 6 entities
        assert len(sketch.entities) == 6

    def test_build_returns_valid_structure(self):
        """Test that build() returns valid Onshape feature structure."""
        sketch = SketchBuilder(name="TestSketch", plane=SketchPlane.FRONT)
        sketch.add_rectangle((0, 0), (5, 5))

        result = sketch.build()

        # Verify top-level structure
        assert result["btType"] == "BTMFeature-134"
        assert "feature" in result

        feature = result["feature"]
        assert feature["btType"] == "BTMSketch-151"
        assert feature["name"] == "TestSketch"
        assert "parameters" in feature
        assert "constraints" in feature
        assert "entities" in feature

    def test_build_includes_plane_parameter(self):
        """Test that build() includes correct plane parameter."""
        sketch = SketchBuilder(plane=SketchPlane.TOP)
        result = sketch.build()

        parameters = result["feature"]["parameters"]
        assert len(parameters) > 0

        plane_param = parameters[0]
        assert plane_param["parameterId"] == "sketchPlane"
        assert "queries" in plane_param

    def test_build_plane_mapping(self):
        """Test that each plane maps to correct deterministic ID."""
        plane_id_map = {SketchPlane.FRONT: "JHD", SketchPlane.TOP: "JHC", SketchPlane.RIGHT: "JHB"}

        for plane, expected_id in plane_id_map.items():
            sketch = SketchBuilder(plane=plane)
            result = sketch.build()

            query = result["feature"]["parameters"][0]["queries"][0]
            assert query["deterministicIds"] == [expected_id]

    def test_build_includes_entities_and_constraints(self):
        """Test that build() includes all entities and constraints."""
        sketch = SketchBuilder()
        sketch.add_rectangle((0, 0), (10, 5), variable_width="w", variable_height="h")
        sketch.add_circle((5, 2.5), 2)

        result = sketch.build()

        feature = result["feature"]
        assert len(feature["entities"]) == 5  # 4 rectangle lines + 1 circle
        assert len(feature["constraints"]) == 2  # width + height

    def test_negative_dimensions(self):
        """Test handling rectangles with negative dimensions."""
        sketch = SketchBuilder()
        sketch.add_rectangle(corner1=(10, 10), corner2=(0, 0), variable_width="width")

        # Constraint should use absolute value
        constraint = sketch.constraints[0]
        assert constraint["value"] == 10  # abs(10 - 0)
