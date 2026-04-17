"""Unit tests for Assembly manager."""

import pytest
from unittest.mock import AsyncMock

from onshape_mcp.api.assemblies import AssemblyManager


class TestAssemblyManager:
    """Test AssemblyManager operations."""

    @pytest.fixture
    def assembly_manager(self, onshape_client):
        """Provide an AssemblyManager instance."""
        return AssemblyManager(onshape_client)

    @pytest.mark.asyncio
    async def test_get_assembly_definition_success(
        self, assembly_manager, onshape_client, sample_document_ids
    ):
        """Test getting the definition of an assembly."""
        expected_response = {
            "instances": [
                {"id": "inst1", "name": "Part 1"},
                {"id": "inst2", "name": "Part 2"},
            ],
            "rootAssembly": {"occurrences": []},
        }

        onshape_client.get = AsyncMock(return_value=expected_response)

        result = await assembly_manager.get_assembly_definition(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
        )

        assert result == expected_response
        assert "instances" in result
        onshape_client.get.assert_called_once()

        call_args = onshape_client.get.call_args
        path = call_args[0][0]
        assert sample_document_ids["document_id"] in path
        assert sample_document_ids["workspace_id"] in path
        assert sample_document_ids["element_id"] in path

    @pytest.mark.asyncio
    async def test_create_assembly_success(
        self, assembly_manager, onshape_client, sample_document_ids
    ):
        """Test creating a new assembly."""
        assembly_name = "My New Assembly"
        expected_response = {"id": "new_asm_id", "name": assembly_name}

        onshape_client.post = AsyncMock(return_value=expected_response)

        result = await assembly_manager.create_assembly(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            assembly_name,
        )

        assert result == expected_response
        onshape_client.post.assert_called_once()

        call_args = onshape_client.post.call_args
        assert call_args[1]["data"] == {"name": assembly_name}

    @pytest.mark.asyncio
    async def test_add_instance_part(
        self, assembly_manager, onshape_client, sample_document_ids
    ):
        """Test adding a specific part instance to an assembly."""
        part_studio_element_id = "ps_elem_abc"
        part_id = "JHD"
        expected_response = {"id": "new_instance_id"}

        onshape_client.post = AsyncMock(return_value=expected_response)

        result = await assembly_manager.add_instance(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            part_studio_element_id,
            part_id=part_id,
        )

        assert result == expected_response
        onshape_client.post.assert_called_once()

        call_args = onshape_client.post.call_args
        body = call_args[1]["data"]
        assert body["documentId"] == sample_document_ids["document_id"]
        assert body["elementId"] == part_studio_element_id
        assert body["partId"] == part_id
        assert body["isWholePartStudio"] is False

    @pytest.mark.asyncio
    async def test_add_instance_whole_part_studio(
        self, assembly_manager, onshape_client, sample_document_ids
    ):
        """Test adding a whole Part Studio instance (no partId) sets isWholePartStudio=True."""
        part_studio_element_id = "ps_elem_abc"
        expected_response = {"id": "new_instance_id"}

        onshape_client.post = AsyncMock(return_value=expected_response)

        result = await assembly_manager.add_instance(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            part_studio_element_id,
        )

        assert result == expected_response
        onshape_client.post.assert_called_once()

        call_args = onshape_client.post.call_args
        body = call_args[1]["data"]
        assert body["documentId"] == sample_document_ids["document_id"]
        assert body["elementId"] == part_studio_element_id
        assert body["isWholePartStudio"] is True

    @pytest.mark.asyncio
    async def test_add_instance_assembly(
        self, assembly_manager, onshape_client, sample_document_ids
    ):
        """Test adding an assembly instance sets isAssembly=True in the body."""
        sub_assembly_element_id = "sub_asm_elem_xyz"
        expected_response = {"id": "new_asm_instance_id"}

        onshape_client.post = AsyncMock(return_value=expected_response)

        result = await assembly_manager.add_instance(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            sub_assembly_element_id,
            is_assembly=True,
        )

        assert result == expected_response
        onshape_client.post.assert_called_once()

        call_args = onshape_client.post.call_args
        body = call_args[1]["data"]
        assert body["documentId"] == sample_document_ids["document_id"]
        assert body["elementId"] == sub_assembly_element_id
        assert body["isAssembly"] is True

    @pytest.mark.asyncio
    async def test_delete_instance_success(
        self, assembly_manager, onshape_client, sample_document_ids
    ):
        """Test deleting an instance from an assembly by node ID."""
        node_id = "node_to_delete_999"
        expected_response = {"deleted": True}

        onshape_client.delete = AsyncMock(return_value=expected_response)

        result = await assembly_manager.delete_instance(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            node_id,
        )

        assert result == expected_response
        onshape_client.delete.assert_called_once()

        call_args = onshape_client.delete.call_args
        path = call_args[0][0]
        assert node_id in path

    @pytest.mark.asyncio
    async def test_transform_occurrences_success(
        self, assembly_manager, onshape_client, sample_document_ids
    ):
        """Test applying transforms to assembly occurrences."""
        transform = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0.1, 0, 0, 1]
        occurrences = [
            {
                "path": ["inst1"],
                "transform": transform,
            },
        ]
        expected_response = {"status": "ok"}

        onshape_client.post = AsyncMock(return_value=expected_response)

        result = await assembly_manager.transform_occurrences(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            occurrences,
        )

        assert result == expected_response
        onshape_client.post.assert_called_once()

        call_args = onshape_client.post.call_args
        body = call_args[1]["data"]
        assert body["isRelative"] is True
        assert body["occurrences"] == [{"path": ["inst1"]}]
        assert body["transform"] == transform

    @pytest.mark.asyncio
    async def test_transform_occurrences_absolute(
        self, assembly_manager, onshape_client, sample_document_ids
    ):
        """Test transform_occurrences with is_relative=False sends absolute transform."""
        transform = [1, 0, 0, 0.254, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        occurrences = [{"path": ["inst1"], "transform": transform}]

        onshape_client.post = AsyncMock(return_value={"status": "ok"})

        await assembly_manager.transform_occurrences(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            occurrences,
            is_relative=False,
        )

        call_args = onshape_client.post.call_args
        body = call_args[1]["data"]
        assert body["isRelative"] is False
        assert body["transform"] == transform

    @pytest.mark.asyncio
    async def test_transform_occurrences_default_is_relative(
        self, assembly_manager, onshape_client, sample_document_ids
    ):
        """Test that default is_relative is True for backward compatibility."""
        transform = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        occurrences = [{"path": ["inst1"], "transform": transform}]

        onshape_client.post = AsyncMock(return_value={"status": "ok"})

        await assembly_manager.transform_occurrences(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            occurrences,
        )

        call_args = onshape_client.post.call_args
        body = call_args[1]["data"]
        assert body["isRelative"] is True

    @pytest.mark.asyncio
    async def test_add_feature_success(
        self, assembly_manager, onshape_client, sample_document_ids
    ):
        """Test adding a feature (mate, mate connector, etc.) to an assembly."""
        feature_data = {
            "btType": "BTMAssemblyFeature-1174",
            "feature": {"name": "Fastened Mate", "featureType": "mate"},
        }
        expected_response = {"featureId": "mate_feat_id", "name": "Fastened Mate"}

        onshape_client.post = AsyncMock(return_value=expected_response)

        result = await assembly_manager.add_feature(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            feature_data,
        )

        assert result == expected_response
        onshape_client.post.assert_called_once()

        call_args = onshape_client.post.call_args
        assert call_args[1]["data"] == feature_data

        path = call_args[0][0]
        assert sample_document_ids["document_id"] in path
        assert sample_document_ids["workspace_id"] in path
        assert sample_document_ids["element_id"] in path
        assert "/features" in path

    @pytest.mark.asyncio
    async def test_get_features_success(
        self, assembly_manager, onshape_client, sample_document_ids
    ):
        """Test getting features from an assembly."""
        expected_response = {
            "features": [
                {"featureId": "mc1", "typeName": "mateConnector"},
                {"featureId": "mate1", "typeName": "mate"},
            ],
            "featureStates": {
                "mc1": {"featureStatus": "OK"},
                "mate1": {"featureStatus": "OK"},
            },
        }

        onshape_client.get = AsyncMock(return_value=expected_response)

        result = await assembly_manager.get_features(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
        )

        assert result == expected_response
        onshape_client.get.assert_called_once()

        call_args = onshape_client.get.call_args
        path = call_args[0][0]
        assert "/features" in path
        assert sample_document_ids["document_id"] in path
