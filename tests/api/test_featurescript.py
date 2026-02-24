"""Unit tests for FeatureScript manager."""

import pytest
from unittest.mock import AsyncMock

from onshape_mcp.api.featurescript import FeatureScriptManager


class TestFeatureScriptManager:
    """Test FeatureScriptManager operations."""

    @pytest.fixture
    def featurescript_manager(self, onshape_client):
        """Provide a FeatureScriptManager instance."""
        return FeatureScriptManager(onshape_client)

    @pytest.mark.asyncio
    async def test_evaluate_success(
        self, featurescript_manager, onshape_client, sample_document_ids
    ):
        """Test evaluating a FeatureScript expression returns the result."""
        script = "function(context is Context, queries) { return 42; }"
        expected_response = {"result": {"BTType": "BTFSValueWithUnits", "value": 42}}

        onshape_client.post = AsyncMock(return_value=expected_response)

        result = await featurescript_manager.evaluate(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            script,
        )

        assert result == expected_response
        onshape_client.post.assert_called_once()

        call_args = onshape_client.post.call_args
        assert call_args[1]["data"]["script"] == script

    @pytest.mark.asyncio
    async def test_evaluate_path_uses_v8(
        self, featurescript_manager, onshape_client, sample_document_ids
    ):
        """Test that the evaluate endpoint uses the /api/v8/ path."""
        script = "function(context is Context, queries) { return true; }"

        onshape_client.post = AsyncMock(return_value={"result": {}})

        await featurescript_manager.evaluate(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            script,
        )

        call_args = onshape_client.post.call_args
        path = call_args[0][0]
        assert "/api/v8/" in path
        assert sample_document_ids["document_id"] in path
        assert sample_document_ids["workspace_id"] in path
        assert sample_document_ids["element_id"] in path
        assert "featurescript" in path

    @pytest.mark.asyncio
    async def test_get_bounding_box_success(
        self, featurescript_manager, onshape_client, sample_document_ids
    ):
        """Test that get_bounding_box calls evaluate and returns bounding box data."""
        expected_response = {
            "result": {
                "minCorner": {"x": 0.0, "y": 0.0, "z": 0.0},
                "maxCorner": {"x": 0.1, "y": 0.05, "z": 0.02},
            }
        }

        onshape_client.post = AsyncMock(return_value=expected_response)

        result = await featurescript_manager.get_bounding_box(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
        )

        assert result == expected_response
        # get_bounding_box delegates to evaluate, which calls client.post
        onshape_client.post.assert_called_once()

        call_args = onshape_client.post.call_args
        body = call_args[1]["data"]
        assert "script" in body
        assert len(body["script"]) > 0
