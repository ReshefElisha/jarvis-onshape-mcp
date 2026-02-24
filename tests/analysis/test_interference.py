"""Unit tests for assembly interference detection."""

import math

import pytest
from unittest.mock import AsyncMock

from onshape_mcp.analysis.interference import (
    BoundingBox,
    InterferenceResult,
    OverlapInfo,
    check_assembly_interference,
    check_overlap,
    format_interference_result,
    get_world_aabb,
    transform_point,
)


class TestTransformPoint:
    """Test the transform_point function."""

    def test_identity_transform(self):
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        result = transform_point(identity, (1.0, 2.0, 3.0))
        assert result == pytest.approx((1.0, 2.0, 3.0))

    def test_translation_only(self):
        matrix = [1, 0, 0, 0.1, 0, 1, 0, 0.2, 0, 0, 1, 0.3, 0, 0, 0, 1]
        result = transform_point(matrix, (0.0, 0.0, 0.0))
        assert result == pytest.approx((0.1, 0.2, 0.3))

    def test_translation_with_existing_point(self):
        matrix = [1, 0, 0, 0.5, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        result = transform_point(matrix, (1.0, 2.0, 3.0))
        assert result == pytest.approx((1.5, 2.0, 3.0))

    def test_90_degree_rotation_z(self):
        c, s = math.cos(math.pi / 2), math.sin(math.pi / 2)
        matrix = [c, -s, 0, 0, s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        result = transform_point(matrix, (1.0, 0.0, 0.0))
        assert result[0] == pytest.approx(0.0, abs=1e-10)
        assert result[1] == pytest.approx(1.0, abs=1e-10)
        assert result[2] == pytest.approx(0.0, abs=1e-10)


class TestGetWorldAABB:
    """Test the get_world_aabb function."""

    def test_identity_preserves_bbox(self):
        bbox = BoundingBox(0, 0, 0, 1, 1, 1)
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        result = get_world_aabb(bbox, identity)
        assert result.low_x == pytest.approx(0)
        assert result.low_y == pytest.approx(0)
        assert result.low_z == pytest.approx(0)
        assert result.high_x == pytest.approx(1)
        assert result.high_y == pytest.approx(1)
        assert result.high_z == pytest.approx(1)

    def test_translation_shifts_bbox(self):
        bbox = BoundingBox(0, 0, 0, 1, 1, 1)
        matrix = [1, 0, 0, 5, 0, 1, 0, 3, 0, 0, 1, 0, 0, 0, 0, 1]
        result = get_world_aabb(bbox, matrix)
        assert result.low_x == pytest.approx(5)
        assert result.low_y == pytest.approx(3)
        assert result.high_x == pytest.approx(6)
        assert result.high_y == pytest.approx(4)

    def test_rotation_expands_bbox(self):
        bbox = BoundingBox(0, 0, 0, 1, 0.1, 1)
        angle = math.pi / 4
        c, s = math.cos(angle), math.sin(angle)
        matrix = [c, -s, 0, 0, s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        result = get_world_aabb(bbox, matrix)
        # Rotation in XY plane expands the Y extent beyond original 0.1
        assert (result.high_y - result.low_y) > 0.5
        # Z should be unchanged (rotation only in XY)
        assert (result.high_z - result.low_z) == pytest.approx(1.0)


class TestCheckOverlap:
    """Test the check_overlap function."""

    def test_no_overlap_separated_x(self):
        a = BoundingBox(0, 0, 0, 1, 1, 1)
        b = BoundingBox(2, 0, 0, 3, 1, 1)
        assert check_overlap(a, b) is None

    def test_no_overlap_touching(self):
        a = BoundingBox(0, 0, 0, 1, 1, 1)
        b = BoundingBox(1, 0, 0, 2, 1, 1)
        assert check_overlap(a, b) is None

    def test_overlap_all_axes(self):
        a = BoundingBox(0, 0, 0, 2, 2, 2)
        b = BoundingBox(1, 1, 1, 3, 3, 3)
        result = check_overlap(a, b)
        assert result is not None
        assert result == pytest.approx((1.0, 1.0, 1.0))

    def test_overlap_only_two_axes_returns_none(self):
        a = BoundingBox(0, 0, 0, 2, 2, 1)
        b = BoundingBox(1, 1, 2, 3, 3, 3)
        assert check_overlap(a, b) is None

    def test_full_containment(self):
        a = BoundingBox(0, 0, 0, 10, 10, 10)
        b = BoundingBox(2, 2, 2, 4, 4, 4)
        result = check_overlap(a, b)
        assert result is not None
        assert result == pytest.approx((2.0, 2.0, 2.0))

    def test_small_overlap(self):
        a = BoundingBox(0, 0, 0, 1, 1, 1)
        b = BoundingBox(0.9, 0.9, 0.9, 2, 2, 2)
        result = check_overlap(a, b)
        assert result is not None
        assert result == pytest.approx((0.1, 0.1, 0.1))


class TestBoundingBoxFromAPI:
    """Test BoundingBox.from_api_response."""

    def test_parses_api_response(self):
        api_data = {
            "lowX": -0.01, "lowY": -0.02, "lowZ": -0.03,
            "highX": 0.01, "highY": 0.02, "highZ": 0.03,
        }
        bbox = BoundingBox.from_api_response(api_data)
        assert bbox.low_x == -0.01
        assert bbox.high_z == 0.03


class TestFormatInterferenceResult:
    """Test the format_interference_result function."""

    def test_no_overlaps(self):
        result = InterferenceResult(total_instances=3, total_pairs_checked=3)
        text = format_interference_result(result)
        assert "No overlaps" in text
        assert "3 instances" in text

    def test_with_overlaps(self):
        result = InterferenceResult(
            total_instances=2,
            total_pairs_checked=1,
            overlaps=[
                OverlapInfo("Part A", "id_a", "Part B", "id_b", 0.75, 0.5, 24.0, 9.0)
            ],
        )
        text = format_interference_result(result)
        assert "FOUND 1 OVERLAP" in text
        assert "Part A" in text
        assert "Part B" in text

    def test_with_warnings(self):
        result = InterferenceResult(
            total_instances=1,
            total_pairs_checked=0,
            warnings=["Need at least 2 instances for interference check."],
        )
        text = format_interference_result(result)
        assert "Warning" in text

    def test_suggests_smallest_axis(self):
        result = InterferenceResult(
            total_instances=2,
            total_pairs_checked=1,
            overlaps=[
                OverlapInfo("A", "a", "B", "b", 0.5, 10.0, 20.0, 100.0)
            ],
        )
        text = format_interference_result(result)
        assert "0.500\" along X" in text


class TestCheckAssemblyInterference:
    """Test the async orchestration function."""

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
        """Create bbox API response from inch values (converted to meters)."""
        m = 0.0254
        return {
            "lowX": lx * m, "lowY": ly * m, "lowZ": lz * m,
            "highX": hx * m, "highY": hy * m, "highZ": hz * m,
        }

    @pytest.mark.asyncio
    async def test_two_overlapping_instances(self):
        mock_asm = AsyncMock()
        mock_ps = AsyncMock()

        mock_asm.get_assembly_definition.return_value = self._make_assembly_data(
            instances=[
                self._make_instance("i1", "Part A", "p1"),
                self._make_instance("i2", "Part B", "p1"),
            ],
            occurrences=[
                self._make_occurrence("i1", tx=0),
                self._make_occurrence("i2", tx=0.5 * 0.0254),  # 0.5" overlap
            ],
        )
        mock_ps.get_part_bounding_box.return_value = self._inch_bbox(0, 0, 0, 1, 1, 1)

        result = await check_assembly_interference(mock_asm, mock_ps, "d", "w", "e")

        assert result.total_instances == 2
        assert result.total_pairs_checked == 1
        assert len(result.overlaps) == 1
        assert result.overlaps[0].overlap_x_inches == pytest.approx(0.5, abs=0.01)

    @pytest.mark.asyncio
    async def test_non_overlapping_instances(self):
        mock_asm = AsyncMock()
        mock_ps = AsyncMock()

        mock_asm.get_assembly_definition.return_value = self._make_assembly_data(
            instances=[
                self._make_instance("i1", "Part A", "p1"),
                self._make_instance("i2", "Part B", "p1"),
            ],
            occurrences=[
                self._make_occurrence("i1", tx=0),
                self._make_occurrence("i2", tx=2 * 0.0254),  # 2" apart, 1" wide parts
            ],
        )
        mock_ps.get_part_bounding_box.return_value = self._inch_bbox(0, 0, 0, 1, 1, 1)

        result = await check_assembly_interference(mock_asm, mock_ps, "d", "w", "e")

        assert len(result.overlaps) == 0

    @pytest.mark.asyncio
    async def test_single_instance_returns_early(self):
        mock_asm = AsyncMock()
        mock_ps = AsyncMock()

        mock_asm.get_assembly_definition.return_value = self._make_assembly_data(
            instances=[self._make_instance("i1", "Only Part", "p1")],
            occurrences=[],
        )

        result = await check_assembly_interference(mock_asm, mock_ps, "d", "w", "e")

        assert result.total_pairs_checked == 0
        assert len(result.warnings) > 0
        mock_ps.get_part_bounding_box.assert_not_called()

    @pytest.mark.asyncio
    async def test_bbox_caching_same_part(self):
        mock_asm = AsyncMock()
        mock_ps = AsyncMock()

        mock_asm.get_assembly_definition.return_value = self._make_assembly_data(
            instances=[
                self._make_instance("i1", "Part A", "p1"),
                self._make_instance("i2", "Part A copy", "p1"),
                self._make_instance("i3", "Part A copy 2", "p1"),
            ],
            occurrences=[
                self._make_occurrence("i1", tx=0),
                self._make_occurrence("i2", tx=5 * 0.0254),
                self._make_occurrence("i3", tx=10 * 0.0254),
            ],
        )
        mock_ps.get_part_bounding_box.return_value = self._inch_bbox(0, 0, 0, 1, 1, 1)

        await check_assembly_interference(mock_asm, mock_ps, "d", "w", "e")

        # Same (doc, elem, part) = only 1 API call
        assert mock_ps.get_part_bounding_box.call_count == 1

    @pytest.mark.asyncio
    async def test_suppressed_instances_skipped(self):
        mock_asm = AsyncMock()
        mock_ps = AsyncMock()

        mock_asm.get_assembly_definition.return_value = self._make_assembly_data(
            instances=[
                self._make_instance("i1", "Active", "p1"),
                {**self._make_instance("i2", "Suppressed", "p1"), "suppressed": True},
            ],
            occurrences=[
                self._make_occurrence("i1"),
                self._make_occurrence("i2"),
            ],
        )
        mock_ps.get_part_bounding_box.return_value = self._inch_bbox(0, 0, 0, 1, 1, 1)

        result = await check_assembly_interference(mock_asm, mock_ps, "d", "w", "e")

        assert result.total_instances == 1
        assert result.total_pairs_checked == 0
