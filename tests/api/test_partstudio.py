"""Unit tests for Part Studio manager."""

import pytest
from unittest.mock import AsyncMock

from onshape_mcp.api.partstudio import PartStudioManager


class TestPartStudioManager:
    """Test PartStudioManager operations."""

    @pytest.fixture
    def partstudio_manager(self, onshape_client):
        """Provide a PartStudioManager instance."""
        return PartStudioManager(onshape_client)

    @pytest.mark.asyncio
    async def test_get_features_success(
        self, partstudio_manager, onshape_client, sample_document_ids
    ):
        """Test getting features from a Part Studio."""
        expected_features = {
            "features": [{"id": "feat1", "type": "sketch"}, {"id": "feat2", "type": "extrude"}]
        }

        onshape_client.get = AsyncMock(return_value=expected_features)

        result = await partstudio_manager.get_features(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
        )

        assert result == expected_features
        onshape_client.get.assert_called_once()

        # Verify correct path construction
        call_args = onshape_client.get.call_args
        path = call_args[0][0]
        assert sample_document_ids["document_id"] in path
        assert sample_document_ids["workspace_id"] in path
        assert sample_document_ids["element_id"] in path
        assert "/features" in path

    @pytest.mark.asyncio
    async def test_add_feature_success(
        self, partstudio_manager, onshape_client, sample_document_ids, sample_feature_response
    ):
        """Test adding a feature to a Part Studio."""
        feature_data = {
            "btType": "BTMFeature-134",
            "feature": {"name": "Test Sketch", "type": "sketch"},
        }

        onshape_client.post = AsyncMock(return_value=sample_feature_response)

        result = await partstudio_manager.add_feature(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            feature_data,
        )

        assert result == sample_feature_response
        onshape_client.post.assert_called_once()

        # Verify feature data was passed correctly
        call_args = onshape_client.post.call_args
        assert call_args[1]["data"] == feature_data

    @pytest.mark.asyncio
    async def test_update_feature_success(
        self, partstudio_manager, onshape_client, sample_document_ids
    ):
        """Test updating an existing feature."""
        feature_id = "feat_123"
        updated_data = {"btType": "BTMFeature-134", "feature": {"name": "Updated Feature"}}

        onshape_client.post = AsyncMock(return_value={"updated": True})

        result = await partstudio_manager.update_feature(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            feature_id,
            updated_data,
        )

        assert result == {"updated": True}

        # Verify feature ID is in the path
        call_args = onshape_client.post.call_args
        path = call_args[0][0]
        assert feature_id in path

    @pytest.mark.asyncio
    async def test_delete_feature_success(
        self, partstudio_manager, onshape_client, sample_document_ids
    ):
        """Test deleting a feature."""
        feature_id = "feat_to_delete"

        onshape_client.delete = AsyncMock(return_value={"deleted": True})

        result = await partstudio_manager.delete_feature(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            feature_id,
        )

        assert result == {"deleted": True}

        # Verify feature ID is in the path
        call_args = onshape_client.delete.call_args
        path = call_args[0][0]
        assert feature_id in path

    @pytest.mark.asyncio
    async def test_get_parts_success(self, partstudio_manager, onshape_client, sample_document_ids):
        """Test getting parts from a Part Studio."""
        expected_parts = [
            {"name": "Part 1", "partId": "part1"},
            {"name": "Part 2", "partId": "part2"},
        ]

        onshape_client.get = AsyncMock(return_value=expected_parts)

        result = await partstudio_manager.get_parts(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
        )

        assert result == expected_parts

        # Verify path includes /parts
        call_args = onshape_client.get.call_args
        path = call_args[0][0]
        assert "/parts/" in path

    @pytest.mark.asyncio
    async def test_create_part_studio_success(
        self, partstudio_manager, onshape_client, sample_document_ids
    ):
        """Test creating a new Part Studio."""
        name = "New Part Studio"
        expected_response = {"id": "new_ps_id", "name": name}

        onshape_client.post = AsyncMock(return_value=expected_response)

        result = await partstudio_manager.create_part_studio(
            sample_document_ids["document_id"], sample_document_ids["workspace_id"], name
        )

        assert result == expected_response

        # Verify name was passed in the data
        call_args = onshape_client.post.call_args
        assert call_args[1]["data"] == {"name": name}

    @pytest.mark.asyncio
    async def test_api_error_handling(
        self, partstudio_manager, onshape_client, sample_document_ids
    ):
        """Test that API errors are propagated correctly."""
        onshape_client.get = AsyncMock(side_effect=Exception("API Error"))

        with pytest.raises(Exception) as exc_info:
            await partstudio_manager.get_features(
                sample_document_ids["document_id"],
                sample_document_ids["workspace_id"],
                sample_document_ids["element_id"],
            )

        assert "API Error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_plane_id_front(self, partstudio_manager, sample_document_ids):
        """Test getting Front plane ID."""
        plane_id = await partstudio_manager.get_plane_id(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            "Front",
        )

        assert plane_id == "JCC"

    @pytest.mark.asyncio
    async def test_get_plane_id_top(self, partstudio_manager, sample_document_ids):
        """Test getting Top plane ID."""
        plane_id = await partstudio_manager.get_plane_id(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            "Top",
        )

        assert plane_id == "JDC"

    @pytest.mark.asyncio
    async def test_get_plane_id_right(self, partstudio_manager, sample_document_ids):
        """Test getting Right plane ID."""
        plane_id = await partstudio_manager.get_plane_id(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            "Right",
        )

        assert plane_id == "JEC"

    @pytest.mark.asyncio
    async def test_get_plane_id_caching(self, partstudio_manager, sample_document_ids):
        """Test that plane IDs are cached."""
        # First call - should compute and cache
        plane_id1 = await partstudio_manager.get_plane_id(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            "Front",
        )

        # Second call - should return cached value
        plane_id2 = await partstudio_manager.get_plane_id(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            "Front",
        )

        assert plane_id1 == plane_id2 == "JCC"

        # Verify cache is populated
        cache_key = f"{sample_document_ids['document_id']}_{sample_document_ids['workspace_id']}_{sample_document_ids['element_id']}_Front"
        assert cache_key in partstudio_manager._plane_id_cache

    @pytest.mark.asyncio
    async def test_get_plane_id_invalid_plane(self, partstudio_manager, sample_document_ids):
        """Test that invalid plane name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid plane name"):
            await partstudio_manager.get_plane_id(
                sample_document_ids["document_id"],
                sample_document_ids["workspace_id"],
                sample_document_ids["element_id"],
                "InvalidPlane",
            )

    @pytest.mark.asyncio
    async def test_get_part_bounding_box_success(
        self, partstudio_manager, onshape_client, sample_document_ids
    ):
        """Test getting bounding box for a specific part."""
        part_id = "JHD"
        expected_bbox = {
            "lowX": -0.01, "lowY": -0.02, "lowZ": -0.03,
            "highX": 0.01, "highY": 0.02, "highZ": 0.03,
        }

        onshape_client.get = AsyncMock(return_value=expected_bbox)

        result = await partstudio_manager.get_part_bounding_box(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            part_id,
        )

        assert result == expected_bbox
        onshape_client.get.assert_called_once()

        call_args = onshape_client.get.call_args
        path = call_args[0][0]
        assert part_id in path
        assert "/boundingboxes" in path

    @pytest.mark.asyncio
    async def test_get_plane_id_cache_different_contexts(self, partstudio_manager):
        """Test that different documents/workspaces get different cache entries."""
        # Different document
        plane_id1 = await partstudio_manager.get_plane_id("doc1", "ws1", "elem1", "Front")

        # Different workspace
        plane_id2 = await partstudio_manager.get_plane_id("doc1", "ws2", "elem1", "Front")

        # Both should be same value but cached separately
        assert plane_id1 == plane_id2 == "JCC"
        assert len(partstudio_manager._plane_id_cache) == 2
