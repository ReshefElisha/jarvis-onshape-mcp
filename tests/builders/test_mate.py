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
        assert mc.face_id is None
        assert mc.occurrence_path is None
        assert mc._flip_primary is False
        assert mc._secondary_axis_type == "PLUS_X"
        assert mc._transform_enabled is False

    def test_initialization_with_custom_values(self):
        mc = MateConnectorBuilder(
            name="MC1", face_id="JHW", occurrence_path=["inst1"]
        )
        assert mc.name == "MC1"
        assert mc.face_id == "JHW"
        assert mc.occurrence_path == ["inst1"]

    def test_set_face(self):
        mc = MateConnectorBuilder()
        result = mc.set_face("JKW")
        assert result is mc
        assert mc.face_id == "JKW"

    def test_set_occurrence(self):
        mc = MateConnectorBuilder()
        result = mc.set_occurrence(["inst1", "inst2"])
        assert result is mc
        assert mc.occurrence_path == ["inst1", "inst2"]

    def test_set_flip_primary(self):
        mc = MateConnectorBuilder()
        result = mc.set_flip_primary(True)
        assert result is mc
        assert mc._flip_primary is True

    def test_set_secondary_axis(self):
        mc = MateConnectorBuilder()
        result = mc.set_secondary_axis("MINUS_Y")
        assert result is mc
        assert mc._secondary_axis_type == "MINUS_Y"

    def test_set_secondary_axis_invalid_raises(self):
        mc = MateConnectorBuilder()
        with pytest.raises(ValueError, match="axis_type must be"):
            mc.set_secondary_axis("INVALID")

    def test_set_translation(self):
        mc = MateConnectorBuilder()
        result = mc.set_translation(1.0, 2.0, 3.0)
        assert result is mc
        assert mc._transform_enabled is True
        assert mc._translation_x == 1.0
        assert mc._translation_y == 2.0
        assert mc._translation_z == 3.0

    def test_set_rotation(self):
        mc = MateConnectorBuilder()
        result = mc.set_rotation("ABOUT_Y", 45.0)
        assert result is mc
        assert mc._transform_enabled is True
        assert mc._rotation_type == "ABOUT_Y"
        assert mc._rotation_angle == 45.0

    def test_set_rotation_invalid_axis_raises(self):
        mc = MateConnectorBuilder()
        with pytest.raises(ValueError, match="axis must be"):
            mc.set_rotation("ABOUT_W", 45.0)

    def test_method_chaining(self):
        mc = (
            MateConnectorBuilder(name="Chained")
            .set_face("JHW")
            .set_occurrence(["inst1"])
            .set_flip_primary(True)
            .set_secondary_axis("PLUS_Y")
        )
        assert mc.name == "Chained"
        assert mc.face_id == "JHW"
        assert mc.occurrence_path == ["inst1"]
        assert mc._flip_primary is True
        assert mc._secondary_axis_type == "PLUS_Y"

    def test_build_structure(self):
        mc = MateConnectorBuilder(
            name="TestMC", face_id="JHW", occurrence_path=["inst1"]
        )
        result = mc.build()

        assert "feature" in result
        feature = result["feature"]
        assert feature["btType"] == "BTMMateConnector-66"
        assert feature["featureType"] == "mateConnector"
        assert feature["name"] == "TestMC"
        assert feature["suppressed"] is False
        assert "parameters" in feature

    def test_build_has_origin_type(self):
        mc = MateConnectorBuilder(face_id="JHW", occurrence_path=["inst1"])
        result = mc.build()
        params = result["feature"]["parameters"]

        origin_type = next(p for p in params if p["parameterId"] == "originType")
        assert origin_type["btType"] == "BTMParameterEnum-145"
        assert origin_type["enumName"] == "Origin type"
        assert origin_type["value"] == "ON_ENTITY"

    def test_build_has_inference_query(self):
        mc = MateConnectorBuilder(face_id="JHW", occurrence_path=["inst1"])
        result = mc.build()
        params = result["feature"]["parameters"]

        origin_query = next(p for p in params if p["parameterId"] == "originQuery")
        assert origin_query["btType"] == "BTMParameterQueryWithOccurrenceList-67"
        query = origin_query["queries"][0]
        assert query["btType"] == "BTMInferenceQueryWithOccurrence-1083"
        assert query["inferenceType"] == "CENTROID"
        assert query["path"] == ["inst1"]
        assert query["deterministicIds"] == ["JHW"]

    def test_build_without_face_id(self):
        mc = MateConnectorBuilder(occurrence_path=["inst1"])
        result = mc.build()
        params = result["feature"]["parameters"]

        origin_query = next(p for p in params if p["parameterId"] == "originQuery")
        query = origin_query["queries"][0]
        assert query["deterministicIds"] == []

    def test_build_without_occurrence_path(self):
        mc = MateConnectorBuilder(face_id="JHW")
        result = mc.build()
        params = result["feature"]["parameters"]

        origin_query = next(p for p in params if p["parameterId"] == "originQuery")
        query = origin_query["queries"][0]
        assert query["path"] == []

    def test_build_default_no_flip_or_secondary(self):
        mc = MateConnectorBuilder(face_id="JHW", occurrence_path=["inst1"])
        result = mc.build()
        params = result["feature"]["parameters"]
        param_ids = [p["parameterId"] for p in params]

        assert "flipPrimary" not in param_ids
        assert "secondaryAxisType" not in param_ids

    def test_build_with_flip_primary(self):
        mc = MateConnectorBuilder(face_id="JHW", occurrence_path=["inst1"])
        mc.set_flip_primary(True)
        result = mc.build()
        params = result["feature"]["parameters"]

        flip = next(p for p in params if p["parameterId"] == "flipPrimary")
        assert flip["btType"] == "BTMParameterBoolean-144"
        assert flip["value"] is True

    def test_build_with_secondary_axis(self):
        mc = MateConnectorBuilder(face_id="JHW", occurrence_path=["inst1"])
        mc.set_secondary_axis("MINUS_X")
        result = mc.build()
        params = result["feature"]["parameters"]

        secondary = next(p for p in params if p["parameterId"] == "secondaryAxisType")
        assert secondary["btType"] == "BTMParameterEnum-145"
        assert secondary["enumName"] == "Reorient secondary axis"
        assert secondary["value"] == "MINUS_X"

    def test_build_default_no_transform(self):
        mc = MateConnectorBuilder(face_id="JHW", occurrence_path=["inst1"])
        result = mc.build()
        params = result["feature"]["parameters"]
        param_ids = [p["parameterId"] for p in params]

        assert "transform" not in param_ids
        assert "translationX" not in param_ids
        assert "rotation" not in param_ids

    def test_build_with_translation(self):
        mc = MateConnectorBuilder(face_id="JHW", occurrence_path=["inst1"])
        mc.set_translation(1.0, 2.0, 3.0)
        result = mc.build()
        params = result["feature"]["parameters"]

        transform = next(p for p in params if p["parameterId"] == "transform")
        assert transform["value"] is True

        tx = next(p for p in params if p["parameterId"] == "translationX")
        ty = next(p for p in params if p["parameterId"] == "translationY")
        tz = next(p for p in params if p["parameterId"] == "translationZ")
        assert f"{1.0 * 0.0254} m" in tx["expression"]
        assert f"{2.0 * 0.0254} m" in ty["expression"]
        assert f"{3.0 * 0.0254} m" in tz["expression"]

    def test_build_with_rotation(self):
        mc = MateConnectorBuilder(face_id="JHW", occurrence_path=["inst1"])
        mc.set_rotation("ABOUT_Y", 90.0)
        result = mc.build()
        params = result["feature"]["parameters"]

        rot_type = next(p for p in params if p["parameterId"] == "rotationType")
        assert rot_type["value"] == "ABOUT_Y"

        rot = next(p for p in params if p["parameterId"] == "rotation")
        assert f"{math.radians(90.0)} rad" in rot["expression"]


class TestMateBuilder:
    """Test MateBuilder functionality."""

    def test_initialization_with_defaults(self):
        mb = MateBuilder()
        assert mb.name == "Mate"
        assert mb.mate_type == MateType.FASTENED
        assert mb.first_mc_id is None
        assert mb.second_mc_id is None

    def test_initialization_with_custom_values(self):
        mb = MateBuilder(name="RevMate", mate_type=MateType.REVOLUTE)
        assert mb.name == "RevMate"
        assert mb.mate_type == MateType.REVOLUTE

    def test_set_first_connector(self):
        mb = MateBuilder()
        result = mb.set_first_connector("mc_feat_1")
        assert result is mb
        assert mb.first_mc_id == "mc_feat_1"

    def test_set_second_connector(self):
        mb = MateBuilder()
        result = mb.set_second_connector("mc_feat_2")
        assert result is mb
        assert mb.second_mc_id == "mc_feat_2"

    def test_method_chaining(self):
        mb = (
            MateBuilder(name="Chained", mate_type=MateType.SLIDER)
            .set_first_connector("mc_a")
            .set_second_connector("mc_b")
        )
        assert mb.first_mc_id == "mc_a"
        assert mb.second_mc_id == "mc_b"

    def test_build_structure(self):
        mb = MateBuilder(name="TestMate")
        mb.set_first_connector("mc1")
        mb.set_second_connector("mc2")
        result = mb.build()

        assert "feature" in result
        feature = result["feature"]
        assert feature["btType"] == "BTMMate-64"
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
        mb.set_first_connector("mc_feat_1")
        mb.set_second_connector("mc_feat_2")
        result = mb.build()
        params = result["feature"]["parameters"]

        connector_list = next(
            p for p in params if p["parameterId"] == "mateConnectorsQuery"
        )
        assert connector_list["btType"] == "BTMParameterQueryWithOccurrenceList-67"
        assert len(connector_list["queries"]) == 2

        first = connector_list["queries"][0]
        assert first["btType"] == "BTMFeatureQueryWithOccurrence-157"
        assert first["featureId"] == "mc_feat_1"
        assert first["path"] == []
        assert first["queryData"] == ""
        second = connector_list["queries"][1]
        assert second["btType"] == "BTMFeatureQueryWithOccurrence-157"
        assert second["featureId"] == "mc_feat_2"
        assert second["path"] == []
        assert second["queryData"] == ""


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
        mb.set_first_connector("mc_a")
        mb.set_second_connector("mc_b")
        result = mb.build()
        params = result["feature"]["parameters"]
        param_ids = [p["parameterId"] for p in params]
        assert "limitsEnabled" not in param_ids

    def test_build_slider_with_limits(self):
        mb = MateBuilder(mate_type=MateType.SLIDER)
        mb.set_first_connector("mc_a")
        mb.set_second_connector("mc_b")
        mb.set_limits(-2.0, 5.0)
        result = mb.build()
        params = result["feature"]["parameters"]

        limits_enabled = next(p for p in params if p["parameterId"] == "limitsEnabled")
        assert limits_enabled["value"] is True

        min_param = next(p for p in params if p["parameterId"] == "limitZMin")
        max_param = next(p for p in params if p["parameterId"] == "limitZMax")
        assert min_param["btType"] == "BTMParameterNullableQuantity-807"
        assert min_param["isNull"] is False
        assert f"{-2.0 * 0.0254} m" in min_param["expression"]
        assert f"{5.0 * 0.0254} m" in max_param["expression"]

    def test_build_revolute_with_limits(self):
        mb = MateBuilder(mate_type=MateType.REVOLUTE)
        mb.set_first_connector("mc_a")
        mb.set_second_connector("mc_b")
        mb.set_limits(-45.0, 90.0)
        result = mb.build()
        params = result["feature"]["parameters"]

        min_param = next(p for p in params if p["parameterId"] == "limitAxialZMin")
        max_param = next(p for p in params if p["parameterId"] == "limitAxialZMax")
        assert min_param["btType"] == "BTMParameterNullableQuantity-807"
        assert min_param["isNull"] is False
        assert "rad" in min_param["expression"]
        assert "rad" in max_param["expression"]

    def test_build_cylindrical_with_limits(self):
        mb = MateBuilder(mate_type=MateType.CYLINDRICAL)
        mb.set_first_connector("mc_a")
        mb.set_second_connector("mc_b")
        mb.set_limits(0, 12.0)
        result = mb.build()
        params = result["feature"]["parameters"]

        min_param = next(p for p in params if p["parameterId"] == "limitZMin")
        max_param = next(p for p in params if p["parameterId"] == "limitZMax")
        assert min_param["btType"] == "BTMParameterNullableQuantity-807"
        assert min_param["isNull"] is False
        assert f"{0 * 0.0254} m" in min_param["expression"]
        assert f"{12.0 * 0.0254} m" in max_param["expression"]

    def test_build_fastened_with_limits_no_crash(self):
        """Fastened mates don't have limits, but setting them should not crash."""
        mb = MateBuilder(mate_type=MateType.FASTENED)
        mb.set_first_connector("mc_a")
        mb.set_second_connector("mc_b")
        mb.set_limits(0, 10)
        result = mb.build()
        params = result["feature"]["parameters"]
        param_ids = [p["parameterId"] for p in params]
        # limitsEnabled is added but no limit value params for FASTENED
        assert "limitsEnabled" in param_ids
        assert "limitZMin" not in param_ids
        assert "limitAxialZMin" not in param_ids
