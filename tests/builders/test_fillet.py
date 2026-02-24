"""Unit tests for Fillet builder."""

import pytest

from onshape_mcp.builders.fillet import FilletBuilder


class TestFilletBuilder:
    """Test FilletBuilder functionality."""

    def test_initialization_with_defaults(self):
        fillet = FilletBuilder()
        assert fillet.name == "Fillet"
        assert fillet.radius == 0.1
        assert fillet.radius_variable is None
        assert fillet.edge_queries == []

    def test_initialization_with_custom_values(self):
        fillet = FilletBuilder(name="MyFillet", radius=0.5)
        assert fillet.name == "MyFillet"
        assert fillet.radius == 0.5

    def test_set_radius(self):
        fillet = FilletBuilder()
        result = fillet.set_radius(0.25)
        assert result is fillet
        assert fillet.radius == 0.25
        assert fillet.radius_variable is None

    def test_set_radius_with_variable(self):
        fillet = FilletBuilder()
        fillet.set_radius(0.25, variable_name="fillet_r")
        assert fillet.radius == 0.25
        assert fillet.radius_variable == "fillet_r"

    def test_add_edge(self):
        fillet = FilletBuilder()
        result = fillet.add_edge("edge1")
        assert result is fillet
        assert fillet.edge_queries == ["edge1"]

    def test_add_multiple_edges(self):
        fillet = FilletBuilder()
        fillet.add_edge("edge1").add_edge("edge2").add_edge("edge3")
        assert fillet.edge_queries == ["edge1", "edge2", "edge3"]

    def test_build_requires_edges(self):
        fillet = FilletBuilder()
        with pytest.raises(ValueError, match="At least one edge must be added"):
            fillet.build()

    def test_build_structure(self):
        fillet = FilletBuilder(name="TestFillet", radius=0.25)
        fillet.add_edge("edge1")
        result = fillet.build()

        assert result["btType"] == "BTFeatureDefinitionCall-1406"
        feature = result["feature"]
        assert feature["btType"] == "BTMFeature-134"
        assert feature["featureType"] == "fillet"
        assert feature["name"] == "TestFillet"

    def test_build_entities_parameter(self):
        fillet = FilletBuilder()
        fillet.add_edge("edge1").add_edge("edge2")
        result = fillet.build()
        params = result["feature"]["parameters"]

        entities = next(p for p in params if p["parameterId"] == "entities")
        assert entities["btType"] == "BTMParameterQueryList-148"
        assert entities["queries"][0]["deterministicIds"] == ["edge1", "edge2"]

    def test_build_radius_without_variable(self):
        fillet = FilletBuilder(radius=0.5)
        fillet.add_edge("edge1")
        result = fillet.build()
        params = result["feature"]["parameters"]

        radius_param = next(p for p in params if p["parameterId"] == "radius")
        assert radius_param["expression"] == "0.5 in"
        assert radius_param["value"] == 0.5

    def test_build_radius_with_variable(self):
        fillet = FilletBuilder()
        fillet.set_radius(0.25, variable_name="r")
        fillet.add_edge("edge1")
        result = fillet.build()
        params = result["feature"]["parameters"]

        radius_param = next(p for p in params if p["parameterId"] == "radius")
        assert radius_param["expression"] == "#r"
        assert radius_param["value"] == 0.25

    def test_method_chaining(self):
        fillet = (
            FilletBuilder(name="Chained")
            .set_radius(0.3, variable_name="r")
            .add_edge("e1")
            .add_edge("e2")
        )
        assert fillet.name == "Chained"
        assert fillet.radius == 0.3
        assert fillet.radius_variable == "r"
        assert len(fillet.edge_queries) == 2
