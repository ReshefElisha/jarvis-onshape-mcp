"""Unit tests for Chamfer builder."""

import pytest

from onshape_mcp.builders.chamfer import ChamferType, ChamferBuilder


class TestChamferType:
    """Test ChamferType enum."""

    def test_chamfer_type_values(self):
        assert ChamferType.EQUAL_OFFSETS.value == "EQUAL_OFFSETS"
        assert ChamferType.TWO_OFFSETS.value == "TWO_OFFSETS"
        assert ChamferType.OFFSET_ANGLE.value == "OFFSET_ANGLE"


class TestChamferBuilder:
    """Test ChamferBuilder functionality."""

    def test_initialization_with_defaults(self):
        chamfer = ChamferBuilder()
        assert chamfer.name == "Chamfer"
        assert chamfer.distance == 0.1
        assert chamfer.chamfer_type == ChamferType.EQUAL_OFFSETS
        assert chamfer.distance_variable is None
        assert chamfer.edge_queries == []

    def test_initialization_with_custom_values(self):
        chamfer = ChamferBuilder(
            name="MyChamfer", distance=0.5, chamfer_type=ChamferType.TWO_OFFSETS
        )
        assert chamfer.name == "MyChamfer"
        assert chamfer.distance == 0.5
        assert chamfer.chamfer_type == ChamferType.TWO_OFFSETS

    def test_set_distance(self):
        chamfer = ChamferBuilder()
        result = chamfer.set_distance(0.3)
        assert result is chamfer
        assert chamfer.distance == 0.3
        assert chamfer.distance_variable is None

    def test_set_distance_with_variable(self):
        chamfer = ChamferBuilder()
        chamfer.set_distance(0.3, variable_name="chamfer_d")
        assert chamfer.distance == 0.3
        assert chamfer.distance_variable == "chamfer_d"

    def test_add_edge(self):
        chamfer = ChamferBuilder()
        result = chamfer.add_edge("edge1")
        assert result is chamfer
        assert chamfer.edge_queries == ["edge1"]

    def test_build_requires_edges(self):
        chamfer = ChamferBuilder()
        with pytest.raises(ValueError, match="At least one edge must be added"):
            chamfer.build()

    def test_build_structure(self):
        chamfer = ChamferBuilder(name="TestChamfer")
        chamfer.add_edge("edge1")
        result = chamfer.build()

        assert result["btType"] == "BTFeatureDefinitionCall-1406"
        feature = result["feature"]
        assert feature["btType"] == "BTMFeature-134"
        assert feature["featureType"] == "chamfer"
        assert feature["name"] == "TestChamfer"

    def test_build_chamfer_type_parameter(self):
        for ct in ChamferType:
            chamfer = ChamferBuilder(chamfer_type=ct)
            chamfer.add_edge("edge1")
            result = chamfer.build()
            params = result["feature"]["parameters"]
            type_param = next(p for p in params if p["parameterId"] == "chamferType")
            assert type_param["value"] == ct.value

    def test_build_distance_without_variable(self):
        chamfer = ChamferBuilder(distance=0.5)
        chamfer.add_edge("edge1")
        result = chamfer.build()
        params = result["feature"]["parameters"]

        width_param = next(p for p in params if p["parameterId"] == "width")
        assert width_param["expression"] == "0.5 in"
        assert width_param["value"] == 0.5

    def test_build_distance_with_variable(self):
        chamfer = ChamferBuilder()
        chamfer.set_distance(0.2, variable_name="d")
        chamfer.add_edge("edge1")
        result = chamfer.build()
        params = result["feature"]["parameters"]

        width_param = next(p for p in params if p["parameterId"] == "width")
        assert width_param["expression"] == "#d"

    def test_method_chaining(self):
        chamfer = (
            ChamferBuilder(name="Chained")
            .set_distance(0.4)
            .add_edge("e1")
            .add_edge("e2")
        )
        assert chamfer.name == "Chained"
        assert chamfer.distance == 0.4
        assert len(chamfer.edge_queries) == 2
