"""Unit tests for Mate and MateConnector builders."""

import math

import pytest

from onshape_mcp.builders.mate import (
    MateType,
    MateConnectorBuilder,
    MateBuilder,
    build_transform_matrix,
)


class TestMateType:
    """Test MateType enum."""

    def test_mate_type_values(self):
        assert MateType.FASTENED.value == "FASTENED"
        assert MateType.REVOLUTE.value == "REVOLUTE"
        assert MateType.SLIDER.value == "SLIDER"
        assert MateType.CYLINDRICAL.value == "CYLINDRICAL"

    def test_mate_type_by_name(self):
        assert MateType["FASTENED"] == MateType.FASTENED
        assert MateType["REVOLUTE"] == MateType.REVOLUTE


class TestMateConnectorBuilder:
    """Test MateConnectorBuilder functionality."""

    def test_initialization_with_defaults(self):
        mc = MateConnectorBuilder()
        assert mc.name == "Mate connector"
        assert mc.origin_x == 0.0
        assert mc.origin_y == 0.0
        assert mc.origin_z == 0.0
        assert mc.occurrence_path is None

    def test_initialization_with_custom_values(self):
        mc = MateConnectorBuilder(name="MC1", origin_x=1.0, origin_y=2.0, origin_z=3.0)
        assert mc.name == "MC1"
        assert mc.origin_x == 1.0
        assert mc.origin_y == 2.0
        assert mc.origin_z == 3.0

    def test_set_origin(self):
        mc = MateConnectorBuilder()
        result = mc.set_origin(5.0, 10.0, 15.0)
        assert result is mc
        assert mc.origin_x == 5.0
        assert mc.origin_y == 10.0
        assert mc.origin_z == 15.0

    def test_set_occurrence(self):
        mc = MateConnectorBuilder()
        result = mc.set_occurrence(["inst1", "inst2"])
        assert result is mc
        assert mc.occurrence_path == ["inst1", "inst2"]

    def test_method_chaining(self):
        mc = (
            MateConnectorBuilder(name="Chained")
            .set_origin(1.0, 2.0, 3.0)
            .set_occurrence(["inst1"])
        )
        assert mc.name == "Chained"
        assert mc.origin_x == 1.0
        assert mc.occurrence_path == ["inst1"]

    def test_build_structure(self):
        mc = MateConnectorBuilder(name="TestMC")
        result = mc.build()

        assert "feature" in result
        feature = result["feature"]
        assert feature["btType"] == "BTMFeature-134"
        assert feature["featureType"] == "mateConnector"
        assert feature["name"] == "TestMC"
        assert feature["suppressed"] is False
        assert "parameters" in feature

    def test_build_converts_inches_to_meters(self):
        mc = MateConnectorBuilder(origin_x=1.0, origin_y=2.0, origin_z=3.0)
        result = mc.build()
        params = result["feature"]["parameters"]

        tx = next(p for p in params if p["parameterId"] == "translationX")
        ty = next(p for p in params if p["parameterId"] == "translationY")
        tz = next(p for p in params if p["parameterId"] == "translationZ")

        assert f"{1.0 * 0.0254} m" in tx["expression"]
        assert f"{2.0 * 0.0254} m" in ty["expression"]
        assert f"{3.0 * 0.0254} m" in tz["expression"]

    def test_build_with_occurrence_path(self):
        mc = MateConnectorBuilder()
        mc.set_occurrence(["inst1"])
        result = mc.build()
        params = result["feature"]["parameters"]

        origin_query = next(p for p in params if p["parameterId"] == "originQuery")
        query = origin_query["queries"][0]
        assert query["btType"] == "BTMIndividualOccurrenceQuery-626"
        assert query["path"] == ["inst1"]

    def test_build_without_occurrence_path(self):
        mc = MateConnectorBuilder()
        result = mc.build()
        params = result["feature"]["parameters"]

        origin_query = next(p for p in params if p["parameterId"] == "originQuery")
        assert origin_query["queries"][0]["path"] == []


class TestMateBuilder:
    """Test MateBuilder functionality."""

    def test_initialization_with_defaults(self):
        mb = MateBuilder()
        assert mb.name == "Mate"
        assert mb.mate_type == MateType.FASTENED
        assert mb.first_path == []
        assert mb.second_path == []

    def test_initialization_with_custom_values(self):
        mb = MateBuilder(name="RevMate", mate_type=MateType.REVOLUTE)
        assert mb.name == "RevMate"
        assert mb.mate_type == MateType.REVOLUTE

    def test_set_first_occurrence(self):
        mb = MateBuilder()
        result = mb.set_first_occurrence(["inst1"])
        assert result is mb
        assert mb.first_path == ["inst1"]

    def test_set_second_occurrence(self):
        mb = MateBuilder()
        result = mb.set_second_occurrence(["inst2"])
        assert result is mb
        assert mb.second_path == ["inst2"]

    def test_method_chaining(self):
        mb = (
            MateBuilder(name="Chained", mate_type=MateType.SLIDER)
            .set_first_occurrence(["a"])
            .set_second_occurrence(["b"])
        )
        assert mb.first_path == ["a"]
        assert mb.second_path == ["b"]

    def test_build_structure(self):
        mb = MateBuilder(name="TestMate")
        mb.set_first_occurrence(["inst1"])
        mb.set_second_occurrence(["inst2"])
        result = mb.build()

        assert "feature" in result
        feature = result["feature"]
        assert feature["btType"] == "BTMFeature-134"
        assert feature["featureType"] == "mate"
        assert feature["name"] == "TestMate"
        assert feature["suppressed"] is False

    def test_build_mate_type_parameter(self):
        for mt in MateType:
            mb = MateBuilder(mate_type=mt)
            result = mb.build()
            params = result["feature"]["parameters"]
            type_param = next(p for p in params if p["parameterId"] == "mateType")
            assert type_param["value"] == mt.value

    def test_build_mate_connectors(self):
        mb = MateBuilder()
        mb.set_first_occurrence(["inst1"])
        mb.set_second_occurrence(["inst2"])
        result = mb.build()
        params = result["feature"]["parameters"]

        connector_list = next(
            p for p in params if p["parameterId"] == "mateConnectorsQuery"
        )
        assert connector_list["btType"] == "BTMParameterMateConnectorList-2020"
        assert len(connector_list["mateConnectors"]) == 2

        first = connector_list["mateConnectors"][0]
        assert first["implicitQuery"]["path"] == ["inst1"]
        second = connector_list["mateConnectors"][1]
        assert second["implicitQuery"]["path"] == ["inst2"]


class TestBuildTransformMatrix:
    """Test build_transform_matrix function."""

    def test_identity_transform(self):
        matrix = build_transform_matrix()
        expected = [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]
        for actual, exp in zip(matrix, expected):
            assert abs(actual - exp) < 1e-10

    def test_translation_only(self):
        matrix = build_transform_matrix(tx=1.0, ty=2.0, tz=3.0)
        assert len(matrix) == 16
        # Translation in meters
        assert abs(matrix[3] - 1.0 * 0.0254) < 1e-10
        assert abs(matrix[7] - 2.0 * 0.0254) < 1e-10
        assert abs(matrix[11] - 3.0 * 0.0254) < 1e-10
        # Rotation part should be identity
        assert abs(matrix[0] - 1.0) < 1e-10
        assert abs(matrix[5] - 1.0) < 1e-10
        assert abs(matrix[10] - 1.0) < 1e-10
        # Bottom row
        assert matrix[12] == 0.0
        assert matrix[13] == 0.0
        assert matrix[14] == 0.0
        assert matrix[15] == 1.0

    def test_rotation_90_degrees_z(self):
        matrix = build_transform_matrix(rz=90.0)
        # Rz(90): [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
        assert abs(matrix[0] - 0.0) < 1e-10  # cos(90)
        assert abs(matrix[1] - (-1.0)) < 1e-10  # -sin(90)
        assert abs(matrix[4] - 1.0) < 1e-10  # sin(90)
        assert abs(matrix[5] - 0.0) < 1e-10  # cos(90)

    def test_matrix_length(self):
        matrix = build_transform_matrix(tx=1, ty=2, tz=3, rx=45, ry=30, rz=60)
        assert len(matrix) == 16

    def test_bottom_row_always_0001(self):
        matrix = build_transform_matrix(tx=5, ry=45, rz=90)
        assert matrix[12] == 0.0
        assert matrix[13] == 0.0
        assert matrix[14] == 0.0
        assert matrix[15] == 1.0


class TestMateConnectorBuilderOrientation:
    """Test MateConnectorBuilder orientation/axis support."""

    def test_default_axis_is_z(self):
        mc = MateConnectorBuilder()
        assert mc._rotation0 == 0.0
        assert mc._rotation1 == 0.0
        assert mc._rotation2 == 0.0

    def test_axis_y_sets_rotations(self):
        mc = MateConnectorBuilder(axis="Y")
        assert mc._rotation0 == -90.0
        assert mc._rotation1 == 90.0
        assert mc._rotation2 == 0.0

    def test_axis_x_sets_rotations(self):
        mc = MateConnectorBuilder(axis="X")
        assert mc._rotation0 == 180.0
        assert mc._rotation1 == 90.0
        assert mc._rotation2 == 0.0

    def test_set_axis_method_chaining(self):
        mc = MateConnectorBuilder()
        result = mc.set_axis("Y")
        assert result is mc
        assert mc._rotation1 == 90.0

    def test_set_axis_invalid_raises_error(self):
        mc = MateConnectorBuilder()
        with pytest.raises(ValueError, match="axis must be"):
            mc.set_axis("W")

    def test_set_axis_case_insensitive(self):
        mc = MateConnectorBuilder()
        mc.set_axis("y")
        assert mc._rotation0 == -90.0
        assert mc._rotation1 == 90.0

    def test_set_rotation_direct(self):
        mc = MateConnectorBuilder()
        result = mc.set_rotation(10.0, 20.0, 30.0)
        assert result is mc
        assert mc._rotation0 == 10.0
        assert mc._rotation1 == 20.0
        assert mc._rotation2 == 30.0

    def test_build_includes_rotation_parameters(self):
        mc = MateConnectorBuilder(axis="Y")
        result = mc.build()
        params = result["feature"]["parameters"]

        r0 = next(p for p in params if p["parameterId"] == "rotation0")
        r1 = next(p for p in params if p["parameterId"] == "rotation1")
        r2 = next(p for p in params if p["parameterId"] == "rotation2")

        assert "rad" in r0["expression"]
        assert "rad" in r1["expression"]
        assert "rad" in r2["expression"]

    def test_build_default_rotation_is_zero(self):
        mc = MateConnectorBuilder()
        result = mc.build()
        params = result["feature"]["parameters"]

        r0 = next(p for p in params if p["parameterId"] == "rotation0")
        assert "0.0 rad" in r0["expression"]

    def test_build_rotation_values_correct(self):
        mc = MateConnectorBuilder(axis="Y")
        result = mc.build()
        params = result["feature"]["parameters"]

        r0 = next(p for p in params if p["parameterId"] == "rotation0")
        r1 = next(p for p in params if p["parameterId"] == "rotation1")

        assert f"{math.radians(-90.0)} rad" in r0["expression"]
        assert f"{math.radians(90.0)} rad" in r1["expression"]


class TestMateBuilderLimits:
    """Test MateBuilder limit support."""

    def test_default_no_limits(self):
        mb = MateBuilder()
        assert mb.min_limit is None
        assert mb.max_limit is None

    def test_set_limits(self):
        mb = MateBuilder(mate_type=MateType.SLIDER)
        result = mb.set_limits(-5.0, 10.0)
        assert result is mb
        assert mb.min_limit == -5.0
        assert mb.max_limit == 10.0

    def test_build_without_limits_no_limit_params(self):
        mb = MateBuilder(mate_type=MateType.SLIDER)
        mb.set_first_occurrence(["a"])
        mb.set_second_occurrence(["b"])
        result = mb.build()
        params = result["feature"]["parameters"]
        param_ids = [p["parameterId"] for p in params]
        assert "limitsEnabled" not in param_ids

    def test_build_slider_with_limits(self):
        mb = MateBuilder(mate_type=MateType.SLIDER)
        mb.set_first_occurrence(["a"])
        mb.set_second_occurrence(["b"])
        mb.set_limits(-2.0, 5.0)
        result = mb.build()
        params = result["feature"]["parameters"]

        limits_enabled = next(p for p in params if p["parameterId"] == "limitsEnabled")
        assert limits_enabled["value"] is True

        min_param = next(p for p in params if p["parameterId"] == "limitAxialZMin")
        max_param = next(p for p in params if p["parameterId"] == "limitAxialZMax")
        assert f"{-2.0 * 0.0254} m" in min_param["expression"]
        assert f"{5.0 * 0.0254} m" in max_param["expression"]

    def test_build_revolute_with_limits(self):
        mb = MateBuilder(mate_type=MateType.REVOLUTE)
        mb.set_first_occurrence(["a"])
        mb.set_second_occurrence(["b"])
        mb.set_limits(-45.0, 90.0)
        result = mb.build()
        params = result["feature"]["parameters"]

        min_param = next(p for p in params if p["parameterId"] == "limitRotationMin")
        max_param = next(p for p in params if p["parameterId"] == "limitRotationMax")
        assert "rad" in min_param["expression"]
        assert "rad" in max_param["expression"]

    def test_build_cylindrical_with_limits(self):
        mb = MateBuilder(mate_type=MateType.CYLINDRICAL)
        mb.set_first_occurrence(["a"])
        mb.set_second_occurrence(["b"])
        mb.set_limits(0, 12.0)
        result = mb.build()
        params = result["feature"]["parameters"]

        min_param = next(p for p in params if p["parameterId"] == "limitAxialZMin")
        max_param = next(p for p in params if p["parameterId"] == "limitAxialZMax")
        assert f"{0 * 0.0254} m" in min_param["expression"]
        assert f"{12.0 * 0.0254} m" in max_param["expression"]

    def test_build_fastened_with_limits_no_crash(self):
        """Fastened mates don't have limits, but setting them should not crash."""
        mb = MateBuilder(mate_type=MateType.FASTENED)
        mb.set_first_occurrence(["a"])
        mb.set_second_occurrence(["b"])
        mb.set_limits(0, 10)
        result = mb.build()
        params = result["feature"]["parameters"]
        param_ids = [p["parameterId"] for p in params]
        # limitsEnabled is added but no limit value params for FASTENED
        assert "limitsEnabled" in param_ids
        assert "limitAxialZMin" not in param_ids
        assert "limitRotationMin" not in param_ids
