"""Unit tests for Document manager."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock

from onshape_mcp.api.documents import DocumentManager, DocumentInfo, WorkspaceInfo, ElementInfo


class TestDocumentInfo:
    """Test DocumentInfo model."""

    def test_document_info_creation(self):
        """Test creating a DocumentInfo instance."""
        doc = DocumentInfo(
            id="doc123",
            name="Test Document",
            createdAt=datetime.now(),
            modifiedAt=datetime.now(),
            ownerId="user123",
            ownerName="Test User",
            public=False,
            description="Test description",
        )

        assert doc.id == "doc123"
        assert doc.name == "Test Document"
        assert doc.owner_id == "user123"
        assert doc.owner_name == "Test User"
        assert doc.public is False
        assert doc.description == "Test description"

    def test_document_info_with_minimal_fields(self):
        """Test creating DocumentInfo with minimal required fields."""
        doc = DocumentInfo(
            id="doc123",
            name="Test",
            createdAt=datetime.now(),
            modifiedAt=datetime.now(),
            ownerId="user123",
        )

        assert doc.id == "doc123"
        assert doc.owner_name is None
        assert doc.description is None
        assert doc.public is False


class TestWorkspaceInfo:
    """Test WorkspaceInfo model."""

    def test_workspace_info_creation(self):
        """Test creating a WorkspaceInfo instance."""
        ws = WorkspaceInfo(
            id="ws123",
            name="Main Workspace",
            isMain=True,
            createdAt=datetime.now(),
            modifiedAt=datetime.now(),
        )

        assert ws.id == "ws123"
        assert ws.name == "Main Workspace"
        assert ws.is_main is True

    def test_workspace_info_defaults(self):
        """Test WorkspaceInfo with default values."""
        ws = WorkspaceInfo(id="ws123", name="Workspace")

        assert ws.is_main is False
        assert ws.created_at is None
        assert ws.modified_at is None


class TestElementInfo:
    """Test ElementInfo model."""

    def test_element_info_creation(self):
        """Test creating an ElementInfo instance."""
        elem = ElementInfo(
            id="elem123",
            name="Part Studio 1",
            elementType="PARTSTUDIO",
            dataType="partstudios",
            thumbnail="http://example.com/thumb.png",
        )

        assert elem.id == "elem123"
        assert elem.name == "Part Studio 1"
        assert elem.element_type == "PARTSTUDIO"
        assert elem.data_type == "partstudios"
        assert elem.thumbnail == "http://example.com/thumb.png"

    def test_element_info_without_optional_fields(self):
        """Test ElementInfo without optional fields."""
        elem = ElementInfo(id="elem123", name="Assembly", elementType="ASSEMBLY")

        assert elem.data_type is None
        assert elem.thumbnail is None


class TestDocumentManager:
    """Test DocumentManager operations."""

    @pytest.fixture
    def document_manager(self, onshape_client):
        """Provide a DocumentManager instance."""
        return DocumentManager(onshape_client)

    @pytest.fixture
    def sample_documents_response(self):
        """Provide sample documents API response."""
        return {
            "items": [
                {
                    "id": "doc1",
                    "name": "First Document",
                    "createdAt": "2024-01-01T00:00:00Z",
                    "modifiedAt": "2024-01-02T00:00:00Z",
                    "owner": {"id": "user1", "name": "User One"},
                    "public": False,
                    "description": "First test document",
                },
                {
                    "id": "doc2",
                    "name": "Second Document",
                    "createdAt": "2024-01-03T00:00:00Z",
                    "modifiedAt": "2024-01-04T00:00:00Z",
                    "owner": {"id": "user2", "name": "User Two"},
                    "public": True,
                },
            ]
        }

    @pytest.mark.asyncio
    async def test_list_documents_success(
        self, document_manager, onshape_client, sample_documents_response
    ):
        """Test listing documents successfully."""
        onshape_client.get = AsyncMock(return_value=sample_documents_response)

        documents = await document_manager.list_documents()

        assert len(documents) == 2
        assert all(isinstance(doc, DocumentInfo) for doc in documents)
        assert documents[0].name == "First Document"
        assert documents[1].name == "Second Document"

        # Verify API call
        onshape_client.get.assert_called_once()
        call_args = onshape_client.get.call_args
        assert "/documents" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_list_documents_with_parameters(
        self, document_manager, onshape_client, sample_documents_response
    ):
        """Test listing documents with custom parameters."""
        onshape_client.get = AsyncMock(return_value=sample_documents_response)

        documents = await document_manager.list_documents(
            filter_type="1", sort_by="name", sort_order="asc", limit=10, offset=5
        )

        # Verify parameters
        call_args = onshape_client.get.call_args
        params = call_args[1]["params"]
        assert params["filter"] == "1"
        assert params["sortColumn"] == "name"
        assert params["sortOrder"] == "asc"
        assert params["limit"] == 10
        assert params["offset"] == 5

    @pytest.mark.asyncio
    async def test_list_documents_empty_result(self, document_manager, onshape_client):
        """Test listing documents with empty result."""
        onshape_client.get = AsyncMock(return_value={"items": []})

        documents = await document_manager.list_documents()

        assert documents == []

    @pytest.mark.asyncio
    async def test_list_documents_handles_invalid_items(self, document_manager, onshape_client):
        """Test that invalid items are skipped gracefully."""
        response = {
            "items": [
                {
                    "id": "doc1",
                    "name": "Valid Doc",
                    "createdAt": "2024-01-01T00:00:00Z",
                    "modifiedAt": "2024-01-02T00:00:00Z",
                    "owner": {"id": "user1"},
                },
                {"id": "doc2"},  # Missing required fields
                {
                    "id": "doc3",
                    "name": "Another Valid Doc",
                    "createdAt": "2024-01-03T00:00:00Z",
                    "modifiedAt": "2024-01-04T00:00:00Z",
                    "owner": {"id": "user2"},
                },
            ]
        }

        onshape_client.get = AsyncMock(return_value=response)

        documents = await document_manager.list_documents()

        # Should only get valid documents
        assert len(documents) == 2
        assert documents[0].name == "Valid Doc"
        assert documents[1].name == "Another Valid Doc"

    @pytest.mark.asyncio
    async def test_get_document_success(self, document_manager, onshape_client):
        """Test getting a specific document."""
        doc_response = {
            "id": "doc123",
            "name": "Test Document",
            "createdAt": "2024-01-01T00:00:00Z",
            "modifiedAt": "2024-01-02T00:00:00Z",
            "owner": {"id": "user1", "name": "Owner"},
            "public": False,
            "description": "Test",
        }

        onshape_client.get = AsyncMock(return_value=doc_response)

        doc = await document_manager.get_document("doc123")

        assert isinstance(doc, DocumentInfo)
        assert doc.id == "doc123"
        assert doc.name == "Test Document"
        assert doc.owner_name == "Owner"

        # Verify API call
        call_args = onshape_client.get.call_args
        assert "doc123" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_search_documents_success(self, document_manager, onshape_client):
        """Test searching for documents."""
        search_response = {
            "items": [
                {
                    "id": "doc1",
                    "name": "CAD Project",
                    "resourceType": "document",
                    "createdAt": "2024-01-01T00:00:00Z",
                    "modifiedAt": "2024-01-02T00:00:00Z",
                    "owner": {"id": "user1"},
                }
            ]
        }

        onshape_client.get = AsyncMock(return_value=search_response)

        documents = await document_manager.search_documents(query="CAD", limit=10)

        assert len(documents) == 1
        assert documents[0].name == "CAD Project"

        # Verify search parameters
        call_args = onshape_client.get.call_args
        params = call_args[1]["params"]
        assert params["q"] == "CAD"
        assert params["limit"] == 10

    @pytest.mark.asyncio
    async def test_search_documents_filters_non_documents(self, document_manager, onshape_client):
        """Test that search only returns document resources."""
        search_response = {
            "items": [
                {
                    "id": "doc1",
                    "name": "Document",
                    "resourceType": "document",
                    "createdAt": "2024-01-01T00:00:00Z",
                    "modifiedAt": "2024-01-02T00:00:00Z",
                    "owner": {"id": "user1"},
                },
                {"id": "folder1", "name": "Folder", "resourceType": "folder"},
            ]
        }

        onshape_client.get = AsyncMock(return_value=search_response)

        documents = await document_manager.search_documents(query="test")

        # Should only get documents, not folders
        assert len(documents) == 1
        assert documents[0].id == "doc1"

    @pytest.mark.asyncio
    async def test_get_workspaces_success(self, document_manager, onshape_client):
        """Test getting workspaces for a document."""
        workspaces_response = [
            {
                "id": "ws1",
                "name": "Main",
                "isMain": True,
                "createdAt": "2024-01-01T00:00:00Z",
                "modifiedAt": "2024-01-02T00:00:00Z",
            },
            {"id": "ws2", "name": "Branch", "isMain": False},
        ]

        onshape_client.get = AsyncMock(return_value=workspaces_response)

        workspaces = await document_manager.get_workspaces("doc123")

        assert len(workspaces) == 2
        assert all(isinstance(ws, WorkspaceInfo) for ws in workspaces)
        assert workspaces[0].is_main is True
        assert workspaces[1].is_main is False

    @pytest.mark.asyncio
    async def test_get_elements_success(self, document_manager, onshape_client):
        """Test getting elements from a workspace."""
        elements_response = [
            {
                "id": "elem1",
                "name": "Part Studio 1",
                "type": "PARTSTUDIO",
                "dataType": "partstudios",
            },
            {"id": "elem2", "name": "Assembly 1", "type": "ASSEMBLY", "dataType": "assemblies"},
        ]

        onshape_client.get = AsyncMock(return_value=elements_response)

        elements = await document_manager.get_elements("doc123", "ws456")

        assert len(elements) == 2
        assert all(isinstance(elem, ElementInfo) for elem in elements)
        assert elements[0].element_type == "PARTSTUDIO"
        assert elements[1].element_type == "ASSEMBLY"

    @pytest.mark.asyncio
    async def test_get_elements_with_type_filter(self, document_manager, onshape_client):
        """Test getting elements filtered by type."""
        elements_response = [
            {"id": "elem1", "name": "PS1", "type": "PARTSTUDIO"},
            {"id": "elem2", "name": "Asm1", "type": "ASSEMBLY"},
            {"id": "elem3", "name": "PS2", "type": "PARTSTUDIO"},
        ]

        onshape_client.get = AsyncMock(return_value=elements_response)

        elements = await document_manager.get_elements("doc123", "ws456", element_type="PARTSTUDIO")

        # Should only get Part Studios
        assert len(elements) == 2
        assert all(elem.element_type == "PARTSTUDIO" for elem in elements)

    @pytest.mark.asyncio
    async def test_find_part_studios_without_filter(self, document_manager, onshape_client):
        """Test finding all Part Studios."""
        elements_response = [
            {"id": "elem1", "name": "Main Part Studio", "type": "PARTSTUDIO"},
            {"id": "elem2", "name": "Assembly", "type": "ASSEMBLY"},
            {"id": "elem3", "name": "Secondary Part Studio", "type": "PARTSTUDIO"},
        ]

        onshape_client.get = AsyncMock(return_value=elements_response)

        part_studios = await document_manager.find_part_studios("doc123", "ws456")

        assert len(part_studios) == 2
        assert all(ps.element_type == "PARTSTUDIO" for ps in part_studios)

    @pytest.mark.asyncio
    async def test_find_part_studios_with_name_filter(self, document_manager, onshape_client):
        """Test finding Part Studios with name pattern."""
        elements_response = [
            {"id": "elem1", "name": "Main Part Studio", "type": "PARTSTUDIO"},
            {"id": "elem2", "name": "Test Part Studio", "type": "PARTSTUDIO"},
            {"id": "elem3", "name": "Other Part Studio", "type": "PARTSTUDIO"},
        ]

        onshape_client.get = AsyncMock(return_value=elements_response)

        part_studios = await document_manager.find_part_studios(
            "doc123", "ws456", name_pattern="main"
        )

        # Should only get the one matching "main" (case-insensitive)
        assert len(part_studios) == 1
        assert part_studios[0].name == "Main Part Studio"

    @pytest.mark.asyncio
    async def test_get_document_summary_success(self, document_manager, onshape_client):
        """Test getting a comprehensive document summary."""
        doc_response = {
            "id": "doc123",
            "name": "Test Doc",
            "createdAt": "2024-01-01T00:00:00Z",
            "modifiedAt": "2024-01-02T00:00:00Z",
            "owner": {"id": "user1"},
        }

        workspaces_response = [{"id": "ws1", "name": "Main", "isMain": True}]

        elements_response = [{"id": "elem1", "name": "PS1", "type": "PARTSTUDIO"}]

        onshape_client.get = AsyncMock(
            side_effect=[doc_response, workspaces_response, elements_response]
        )

        summary = await document_manager.get_document_summary("doc123")

        assert "document" in summary
        assert "workspaces" in summary
        assert "workspace_details" in summary

        assert summary["document"].id == "doc123"
        assert len(summary["workspaces"]) == 1
        assert len(summary["workspace_details"]) == 1
        assert len(summary["workspace_details"][0]["elements"]) == 1

    @pytest.mark.asyncio
    async def test_api_error_propagation(self, document_manager, onshape_client):
        """Test that API errors are propagated correctly."""
        onshape_client.get = AsyncMock(side_effect=Exception("API Error"))

        with pytest.raises(Exception) as exc_info:
            await document_manager.list_documents()

        assert "API Error" in str(exc_info.value)
