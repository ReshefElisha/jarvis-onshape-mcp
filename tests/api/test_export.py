"""Unit tests for Export manager."""

import pytest
from unittest.mock import AsyncMock

from onshape_mcp.api.export import ExportManager


class TestExportManager:
    """Test ExportManager operations."""

    @pytest.fixture
    def export_manager(self, onshape_client):
        """Provide an ExportManager instance."""
        return ExportManager(onshape_client)

    @pytest.mark.asyncio
    async def test_export_part_studio_stl(
        self, export_manager, onshape_client, sample_document_ids
    ):
        """Test exporting a Part Studio to STL format."""
        expected_response = {
            "id": "translation_123",
            "requestState": "ACTIVE",
        }

        onshape_client.post = AsyncMock(return_value=expected_response)

        result = await export_manager.export_part_studio(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            format_name="STL",
        )

        assert result == expected_response
        onshape_client.post.assert_called_once()

        call_args = onshape_client.post.call_args
        body = call_args[1]["data"]
        assert body["formatName"] == "STL"

        path = call_args[0][0]
        assert sample_document_ids["document_id"] in path
        assert sample_document_ids["workspace_id"] in path
        assert sample_document_ids["element_id"] in path

    @pytest.mark.asyncio
    async def test_export_part_studio_with_part_id(
        self, export_manager, onshape_client, sample_document_ids
    ):
        """Test exporting a specific part by part ID."""
        part_id = "JHD"
        expected_response = {"id": "translation_456", "requestState": "ACTIVE"}

        onshape_client.post = AsyncMock(return_value=expected_response)

        result = await export_manager.export_part_studio(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            format_name="STEP",
            part_id=part_id,
        )

        assert result == expected_response
        onshape_client.post.assert_called_once()

        call_args = onshape_client.post.call_args
        body = call_args[1]["data"]
        assert body["partId"] == part_id
        assert body["formatName"] == "STEP"

    @pytest.mark.asyncio
    async def test_export_assembly_success(
        self, export_manager, onshape_client, sample_document_ids
    ):
        """Test exporting an assembly POSTs to the assemblies path."""
        expected_response = {"id": "translation_789", "requestState": "ACTIVE"}

        onshape_client.post = AsyncMock(return_value=expected_response)

        result = await export_manager.export_assembly(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            format_name="STL",
        )

        assert result == expected_response
        onshape_client.post.assert_called_once()

        call_args = onshape_client.post.call_args
        path = call_args[0][0]
        assert "assemblies" in path
        assert sample_document_ids["document_id"] in path
        assert sample_document_ids["workspace_id"] in path
        assert sample_document_ids["element_id"] in path

        body = call_args[1]["data"]
        assert body["formatName"] == "STL"

    @pytest.mark.asyncio
    async def test_get_translation_status(
        self, export_manager, onshape_client
    ):
        """Test checking the status of a translation by ID."""
        translation_id = "trans_id_abc123"
        expected_response = {
            "id": translation_id,
            "requestState": "DONE",
            "resultExternalDataIds": ["file_data_id_xyz"],
        }

        onshape_client.get = AsyncMock(return_value=expected_response)

        result = await export_manager.get_translation_status(translation_id)

        assert result == expected_response
        onshape_client.get.assert_called_once()

        call_args = onshape_client.get.call_args
        path = call_args[0][0]
        assert translation_id in path
