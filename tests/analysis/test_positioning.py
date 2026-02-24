"""Unit tests for assembly positioning tools."""

import pytest
from unittest.mock import AsyncMock

from onshape_mcp.analysis.interference import BoundingBox
from onshape_mcp.analysis.positioning import (
    InstancePositionInfo,
    align_to_face,
    build_absolute_translation_matrix,
    compute_aligned_position,
    extract_occurrence_transforms,
    format_positions_report,
    get_assembly_positions,
    get_position_from_transform,
    set_absolute_position,
)


class TestExtractOccurrenceTransforms:
    """Test the extract_occurrence_transforms function."""

    def test_extracts_single_instance(self):
        data = {
            "rootAssembly": {
                "occurrences": [
                    {
                        "path": ["inst1"],
                        "transform": [1, 0, 0, 0.1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                    }
                ]
            }
        }
        result = extract_occurrence_transforms(data)
        assert "inst1" in result
        assert result["inst1"][3] == 0.1

    def test_ignores_nested_occurrences(self):
        data = {
            "rootAssembly": {
                "occurrences": [
                    {"path": ["inst1", "sub1"], "transform": [1] * 16},
                ]
            }
        }
        result = extract_occurrence_transforms(data)
        assert len(result) == 0

    def test_empty_assembly(self):
        data = {"rootAssembly": {"occurrences": []}}
        result = extract_occurrence_transforms(data)
        assert result == {}

    def test_missing_transform_uses_identity(self):
        data = {
            "rootAssembly": {
                "occurrences": [{"path": ["inst1"]}]
            }
        }
        result = extract_occurrence_transforms(data)
        assert result["inst1"] == [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


class TestGetPositionFromTransform:
    """Test the get_position_from_transform function."""

    def test_identity_returns_origin(self):
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        result = get_position_from_transform(identity)
        assert result == (0, 0, 0)

    def test_translated_matrix(self):
        matrix = [1, 0, 0, 0.254, 0, 1, 0, -0.4064, 0, 0, 1, 0.0762, 0, 0, 0, 1]
        result = get_position_from_transform(matrix)
        assert result == pytest.approx((0.254, -0.4064, 0.0762))


class TestBuildAbsoluteTranslationMatrix:
    """Test the build_absolute_translation_matrix function."""

    def test_zero_position(self):
        result = build_absolute_translation_matrix(0, 0, 0)
        assert result == [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]

    def test_converts_inches_to_meters(self):
        result = build_absolute_translation_matrix(10, -5, 3)
        assert result[3] == pytest.approx(10 * 0.0254)
        assert result[7] == pytest.approx(-5 * 0.0254)
        assert result[11] == pytest.approx(3 * 0.0254)

    def test_rotation_is_identity(self):
        result = build_absolute_translation_matrix(1, 2, 3)
        # Diagonal elements (rotation) should be 1
        assert result[0] == 1.0
        assert result[5] == 1.0
        assert result[10] == 1.0
        # Off-diagonal rotation elements should be 0
        assert result[1] == 0.0
        assert result[2] == 0.0
        assert result[4] == 0.0
        assert result[6] == 0.0
        assert result[8] == 0.0
        assert result[9] == 0.0

    def test_last_row(self):
        result = build_absolute_translation_matrix(1, 2, 3)
        assert result[12:] == [0.0, 0.0, 0.0, 1.0]


class TestComputeAlignedPosition:
    """Test the compute_aligned_position function."""

    def test_front_alignment(self):
        # Source: 1m box at local origin, currently at (5, 5, 0)
        source_bbox = BoundingBox(0, 0, 0, 1, 1, 1)
        source_pos = (5.0, 5.0, 0.0)
        # Target: world AABB at Y=[2, 4]
        target_aabb = BoundingBox(0, 2, 0, 1, 4, 1)

        result = compute_aligned_position(source_bbox, source_pos, target_aabb, "front")

        # Source max Y (1.0) should touch target min Y (2.0)
        # new_y = 2.0 - 1.0 = 1.0
        assert result == pytest.approx((5.0, 1.0, 0.0))

    def test_back_alignment(self):
        source_bbox = BoundingBox(0, 0, 0, 1, 1, 1)
        source_pos = (5.0, 5.0, 0.0)
        target_aabb = BoundingBox(0, 2, 0, 1, 4, 1)

        result = compute_aligned_position(source_bbox, source_pos, target_aabb, "back")

        # Source min Y (0.0) should touch target max Y (4.0)
        # new_y = 4.0 - 0.0 = 4.0
        assert result == pytest.approx((5.0, 4.0, 0.0))

    def test_left_alignment(self):
        source_bbox = BoundingBox(0, 0, 0, 1, 1, 1)
        source_pos = (5.0, 3.0, 0.0)
        target_aabb = BoundingBox(2, 0, 0, 4, 1, 1)

        result = compute_aligned_position(source_bbox, source_pos, target_aabb, "left")

        # Source max X (1.0) should touch target min X (2.0)
        # new_x = 2.0 - 1.0 = 1.0
        assert result == pytest.approx((1.0, 3.0, 0.0))

    def test_right_alignment(self):
        source_bbox = BoundingBox(0, 0, 0, 1, 1, 1)
        source_pos = (5.0, 3.0, 0.0)
        target_aabb = BoundingBox(2, 0, 0, 4, 1, 1)

        result = compute_aligned_position(source_bbox, source_pos, target_aabb, "right")

        # Source min X (0.0) should touch target max X (4.0)
        # new_x = 4.0 - 0.0 = 4.0
        assert result == pytest.approx((4.0, 3.0, 0.0))

    def test_top_alignment(self):
        source_bbox = BoundingBox(0, 0, 0, 1, 1, 1)
        source_pos = (5.0, 3.0, 0.0)
        target_aabb = BoundingBox(0, 0, 2, 1, 1, 4)

        result = compute_aligned_position(source_bbox, source_pos, target_aabb, "top")

        # Source min Z (0.0) should touch target max Z (4.0)
        # new_z = 4.0 - 0.0 = 4.0
        assert result == pytest.approx((5.0, 3.0, 4.0))

    def test_bottom_alignment(self):
        source_bbox = BoundingBox(0, 0, 0, 1, 1, 1)
        source_pos = (5.0, 3.0, 7.0)
        target_aabb = BoundingBox(0, 0, 2, 1, 1, 4)

        result = compute_aligned_position(source_bbox, source_pos, target_aabb, "bottom")

        # Source max Z (1.0) should touch target min Z (2.0)
        # new_z = 2.0 - 1.0 = 1.0
        assert result == pytest.approx((5.0, 3.0, 1.0))

    def test_preserves_other_axes(self):
        source_bbox = BoundingBox(0, 0, 0, 1, 1, 1)
        source_pos = (10.0, 20.0, 30.0)
        target_aabb = BoundingBox(0, 5, 0, 1, 10, 1)

        result = compute_aligned_position(source_bbox, source_pos, target_aabb, "front")

        # X and Z should be unchanged from source_pos
        assert result[0] == pytest.approx(10.0)
        assert result[2] == pytest.approx(30.0)

    def test_invalid_face_raises(self):
        source_bbox = BoundingBox(0, 0, 0, 1, 1, 1)
        with pytest.raises(ValueError, match="Invalid face"):
            compute_aligned_position(source_bbox, (0, 0, 0), source_bbox, "middle")

    def test_asymmetric_bbox(self):
        # Source bbox not centered at origin: Y goes from -2 to 0
        source_bbox = BoundingBox(0, -2, 0, 1, 0, 1)
        source_pos = (0.0, 0.0, 0.0)
        target_aabb = BoundingBox(0, 5, 0, 1, 10, 1)

        result = compute_aligned_position(source_bbox, source_pos, target_aabb, "front")

        # Source max Y (0.0) should touch target min Y (5.0)
        # new_y = 5.0 - 0.0 = 5.0
        assert result == pytest.approx((0.0, 5.0, 0.0))


class TestFormatPositionsReport:
    """Test the format_positions_report function."""

    def test_empty_positions(self):
        result = format_positions_report([])
        assert "No instances" in result

    def test_single_position_formatting(self):
        pos = InstancePositionInfo(
            name="Test Part",
            instance_id="id1",
            position_x_inches=10.0,
            position_y_inches=-5.0,
            position_z_inches=0.0,
            size_x_inches=2.0,
            size_y_inches=3.0,
            size_z_inches=4.0,
            world_low_x_inches=9.0,
            world_low_y_inches=-6.5,
            world_low_z_inches=-2.0,
            world_high_x_inches=11.0,
            world_high_y_inches=-3.5,
            world_high_z_inches=2.0,
        )
        result = format_positions_report([pos])
        assert "Test Part" in result
        assert "id1" in result
        assert "10.000" in result
        assert "-5.000" in result
        assert '2.000" W' in result
        assert '3.000" D' in result
        assert '4.000" H' in result

    def test_multiple_positions(self):
        positions = [
            InstancePositionInfo("A", "a", 0, 0, 0, 1, 1, 1, 0, 0, 0, 1, 1, 1),
            InstancePositionInfo("B", "b", 5, 5, 5, 2, 2, 2, 4, 4, 4, 6, 6, 6),
        ]
        result = format_positions_report(positions)
        assert "2 instance(s)" in result
        assert "**A**" in result
        assert "**B**" in result


class TestGetAssemblyPositions:
    """Test the async get_assembly_positions orchestration."""

    def _make_assembly_data(self, instances, occurrences):
        return {"rootAssembly": {"instances": instances, "occurrences": occurrences}}

    def _make_instance(self, inst_id, name, part_id, elem_id="e1", doc_id="d"):
        return {
            "id": inst_id, "name": name, "type": "Part",
            "documentId": doc_id, "elementId": elem_id, "partId": part_id,
        }

    def _make_occurrence(self, inst_id, tx=0, ty=0, tz=0):
        return {
            "path": [inst_id],
            "transform": [1, 0, 0, tx, 0, 1, 0, ty, 0, 0, 1, tz, 0, 0, 0, 1],
        }

    def _inch_bbox(self, lx, ly, lz, hx, hy, hz):
        m = 0.0254
        return {
            "lowX": lx * m, "lowY": ly * m, "lowZ": lz * m,
            "highX": hx * m, "highY": hy * m, "highZ": hz * m,
        }

    @pytest.mark.asyncio
    async def test_returns_positions_for_two_parts(self):
        mock_asm = AsyncMock()
        mock_ps = AsyncMock()

        mock_asm.get_assembly_definition.return_value = self._make_assembly_data(
            instances=[
                self._make_instance("i1", "Panel A", "p1"),
                self._make_instance("i2", "Panel B", "p2"),
            ],
            occurrences=[
                self._make_occurrence("i1", tx=0),
                self._make_occurrence("i2", ty=-0.4064),  # -16"
            ],
        )
        mock_ps.get_part_bounding_box.side_effect = [
            self._inch_bbox(0, 0, 0, 1, 1, 1),
            self._inch_bbox(0, 0, 0, 2, 2, 2),
        ]

        result = await get_assembly_positions(mock_asm, mock_ps, "d", "w", "e")

        assert "Panel A" in result
        assert "Panel B" in result
        assert "2 instance(s)" in result

    @pytest.mark.asyncio
    async def test_caches_bbox_for_same_part(self):
        mock_asm = AsyncMock()
        mock_ps = AsyncMock()

        mock_asm.get_assembly_definition.return_value = self._make_assembly_data(
            instances=[
                self._make_instance("i1", "Part A", "p1"),
                self._make_instance("i2", "Part A copy", "p1"),
                self._make_instance("i3", "Part A copy 2", "p1"),
            ],
            occurrences=[
                self._make_occurrence("i1"),
                self._make_occurrence("i2", tx=0.254),
                self._make_occurrence("i3", tx=0.508),
            ],
        )
        mock_ps.get_part_bounding_box.return_value = self._inch_bbox(0, 0, 0, 1, 1, 1)

        await get_assembly_positions(mock_asm, mock_ps, "d", "w", "e")

        # Same (doc, elem, part) = only 1 API call
        assert mock_ps.get_part_bounding_box.call_count == 1

    @pytest.mark.asyncio
    async def test_skips_suppressed_instances(self):
        mock_asm = AsyncMock()
        mock_ps = AsyncMock()

        mock_asm.get_assembly_definition.return_value = self._make_assembly_data(
            instances=[
                self._make_instance("i1", "Active", "p1"),
                {**self._make_instance("i2", "Suppressed", "p2"), "suppressed": True},
            ],
            occurrences=[self._make_occurrence("i1")],
        )
        mock_ps.get_part_bounding_box.return_value = self._inch_bbox(0, 0, 0, 1, 1, 1)

        result = await get_assembly_positions(mock_asm, mock_ps, "d", "w", "e")

        assert "Active" in result
        assert "Suppressed" not in result
        assert "1 instance(s)" in result

    @pytest.mark.asyncio
    async def test_empty_assembly(self):
        mock_asm = AsyncMock()
        mock_ps = AsyncMock()

        mock_asm.get_assembly_definition.return_value = self._make_assembly_data(
            instances=[], occurrences=[],
        )

        result = await get_assembly_positions(mock_asm, mock_ps, "d", "w", "e")

        assert "No instances" in result


class TestSetAbsolutePosition:
    """Test the async set_absolute_position function."""

    @pytest.mark.asyncio
    async def test_calls_transform_with_absolute(self):
        mock_asm = AsyncMock()
        mock_asm.transform_occurrences.return_value = {}

        await set_absolute_position(mock_asm, "d", "w", "e", "inst1", 10.0, -5.0, 3.0)

        mock_asm.transform_occurrences.assert_called_once()
        _, kwargs = mock_asm.transform_occurrences.call_args
        assert kwargs.get("is_relative") is False

    @pytest.mark.asyncio
    async def test_correct_matrix_values(self):
        mock_asm = AsyncMock()
        mock_asm.transform_occurrences.return_value = {}

        await set_absolute_position(mock_asm, "d", "w", "e", "inst1", 10.0, -5.0, 3.0)

        args = mock_asm.transform_occurrences.call_args
        occurrences = args[0][3]  # 4th positional arg
        transform = occurrences[0]["transform"]
        assert transform[3] == pytest.approx(10.0 * 0.0254)
        assert transform[7] == pytest.approx(-5.0 * 0.0254)
        assert transform[11] == pytest.approx(3.0 * 0.0254)

    @pytest.mark.asyncio
    async def test_returns_confirmation_message(self):
        mock_asm = AsyncMock()
        mock_asm.transform_occurrences.return_value = {}

        result = await set_absolute_position(mock_asm, "d", "w", "e", "inst1", 10.0, -5.0, 3.0)

        assert "inst1" in result
        assert "10.000" in result
        assert "-5.000" in result
        assert "3.000" in result


class TestAlignToFace:
    """Test the async align_to_face orchestration."""

    def _make_assembly_data(self, instances, occurrences):
        return {"rootAssembly": {"instances": instances, "occurrences": occurrences}}

    def _make_instance(self, inst_id, name, part_id, elem_id="e1", doc_id="d"):
        return {
            "id": inst_id, "name": name, "type": "Part",
            "documentId": doc_id, "elementId": elem_id, "partId": part_id,
        }

    def _make_occurrence(self, inst_id, tx=0, ty=0, tz=0):
        return {
            "path": [inst_id],
            "transform": [1, 0, 0, tx, 0, 1, 0, ty, 0, 0, 1, tz, 0, 0, 0, 1],
        }

    def _meter_bbox(self, lx, ly, lz, hx, hy, hz):
        return {
            "lowX": lx, "lowY": ly, "lowZ": lz,
            "highX": hx, "highY": hy, "highZ": hz,
        }

    @pytest.mark.asyncio
    async def test_align_front_computes_correct_position(self):
        mock_asm = AsyncMock()
        mock_ps = AsyncMock()

        # Target side panel at Y=0, local bbox Y: -0.4064 to 0 (16" deep)
        # Source door at Y=0, local bbox Y: -0.01905 to 0 (0.75" thick)
        mock_asm.get_assembly_definition.return_value = self._make_assembly_data(
            instances=[
                self._make_instance("door", "Door", "p1", elem_id="e1"),
                self._make_instance("side", "Side", "p2", elem_id="e2"),
            ],
            occurrences=[
                self._make_occurrence("door", ty=0),
                self._make_occurrence("side", ty=0),
            ],
        )
        mock_ps.get_part_bounding_box.side_effect = [
            self._meter_bbox(0, -0.01905, 0, 0.6096, 0, 0.762),  # door
            self._meter_bbox(0, -0.4064, 0, 0.01905, 0, 0.762),  # side
        ]
        mock_asm.transform_occurrences.return_value = {}

        result = await align_to_face(
            mock_asm, mock_ps, "d", "w", "e", "door", "side", "front"
        )

        # Side front face (min Y) = -0.4064m
        # Door should be placed so its high_y (0) touches side's low_y (-0.4064)
        # new_y = -0.4064 - 0 = -0.4064m = -16"
        assert "Aligned" in result
        assert "front" in result
        assert "-16.000" in result

        # Verify transform_occurrences was called with correct position
        call_args = mock_asm.transform_occurrences.call_args
        occurrences = call_args[0][3]
        transform = occurrences[0]["transform"]
        assert transform[7] == pytest.approx(-0.4064, abs=1e-6)

    @pytest.mark.asyncio
    async def test_source_not_found_raises(self):
        mock_asm = AsyncMock()
        mock_ps = AsyncMock()

        mock_asm.get_assembly_definition.return_value = self._make_assembly_data(
            instances=[self._make_instance("target", "Target", "p1")],
            occurrences=[self._make_occurrence("target")],
        )

        with pytest.raises(ValueError, match="Source instance"):
            await align_to_face(
                mock_asm, mock_ps, "d", "w", "e", "missing", "target", "front"
            )

    @pytest.mark.asyncio
    async def test_target_not_found_raises(self):
        mock_asm = AsyncMock()
        mock_ps = AsyncMock()

        mock_asm.get_assembly_definition.return_value = self._make_assembly_data(
            instances=[self._make_instance("source", "Source", "p1")],
            occurrences=[self._make_occurrence("source")],
        )

        with pytest.raises(ValueError, match="Target instance"):
            await align_to_face(
                mock_asm, mock_ps, "d", "w", "e", "source", "missing", "front"
            )

    @pytest.mark.asyncio
    async def test_invalid_face_raises(self):
        mock_asm = AsyncMock()
        mock_ps = AsyncMock()

        mock_asm.get_assembly_definition.return_value = self._make_assembly_data(
            instances=[
                self._make_instance("s", "Source", "p1"),
                self._make_instance("t", "Target", "p2"),
            ],
            occurrences=[],
        )

        with pytest.raises(ValueError, match="Invalid face"):
            await align_to_face(
                mock_asm, mock_ps, "d", "w", "e", "s", "t", "diagonal"
            )

    @pytest.mark.asyncio
    async def test_preserves_unchanged_axes(self):
        mock_asm = AsyncMock()
        mock_ps = AsyncMock()

        # Source at X=0.254, Y=0, Z=0 (10" in X)
        mock_asm.get_assembly_definition.return_value = self._make_assembly_data(
            instances=[
                self._make_instance("src", "Source", "p1", elem_id="e1"),
                self._make_instance("tgt", "Target", "p2", elem_id="e2"),
            ],
            occurrences=[
                self._make_occurrence("src", tx=0.254, tz=0.127),  # 10" X, 5" Z
                self._make_occurrence("tgt"),
            ],
        )
        mock_ps.get_part_bounding_box.side_effect = [
            self._meter_bbox(0, 0, 0, 0.1, 0.1, 0.1),
            self._meter_bbox(0, -1, 0, 0.1, 0, 0.1),
        ]
        mock_asm.transform_occurrences.return_value = {}

        await align_to_face(
            mock_asm, mock_ps, "d", "w", "e", "src", "tgt", "front"
        )

        call_args = mock_asm.transform_occurrences.call_args
        transform = call_args[0][3][0]["transform"]
        # X and Z should be unchanged from source position
        assert transform[3] == pytest.approx(0.254)   # X preserved
        assert transform[11] == pytest.approx(0.127)   # Z preserved

    @pytest.mark.asyncio
    async def test_returns_confirmation_message(self):
        mock_asm = AsyncMock()
        mock_ps = AsyncMock()

        mock_asm.get_assembly_definition.return_value = self._make_assembly_data(
            instances=[
                self._make_instance("s", "Door", "p1", elem_id="e1"),
                self._make_instance("t", "Cabinet", "p2", elem_id="e2"),
            ],
            occurrences=[
                self._make_occurrence("s"),
                self._make_occurrence("t"),
            ],
        )
        mock_ps.get_part_bounding_box.side_effect = [
            self._meter_bbox(0, 0, 0, 1, 1, 1),
            self._meter_bbox(0, 0, 0, 1, 1, 1),
        ]
        mock_asm.transform_occurrences.return_value = {}

        result = await align_to_face(
            mock_asm, mock_ps, "d", "w", "e", "s", "t", "back"
        )

        assert "Aligned" in result
        assert "Door" in result
        assert "back" in result
        assert "Cabinet" in result
