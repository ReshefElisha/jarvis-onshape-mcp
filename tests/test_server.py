"""Tests for the MCP server."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import httpx
from mcp.types import Tool, TextContent

# Import the server module components
from onshape_mcp.server import app, list_tools, call_tool
from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.variables import Variable
from onshape_mcp.api.documents import DocumentInfo, ElementInfo


class TestListTools:
    """Test the list_tools handler."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_all_tools(self):
        """Test that list_tools returns all defined tools."""
        tools = await list_tools()

        assert isinstance(tools, list)
        assert len(tools) > 0
        assert all(isinstance(tool, Tool) for tool in tools)

    @pytest.mark.asyncio
    async def test_list_tools_includes_sketch_tool(self):
        """Test that create_sketch_rectangle tool is included."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]

        assert "create_sketch_rectangle" in tool_names

    @pytest.mark.asyncio
    async def test_list_tools_includes_extrude_tool(self):
        """Test that create_extrude tool is included."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]

        assert "create_extrude" in tool_names

    @pytest.mark.asyncio
    async def test_list_tools_includes_thicken_tool(self):
        """Test that create_thicken tool is included."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]

        assert "create_thicken" in tool_names

    @pytest.mark.asyncio
    async def test_list_tools_includes_variable_tools(self):
        """Test that variable management tools are included."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]

        assert "get_variables" in tool_names
        assert "set_variable" in tool_names

    @pytest.mark.asyncio
    async def test_list_tools_includes_document_tools(self):
        """Test that document management tools are included."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]

        assert "list_documents" in tool_names
        assert "search_documents" in tool_names
        assert "get_document" in tool_names
        assert "get_document_summary" in tool_names
        assert "find_part_studios" in tool_names

    @pytest.mark.asyncio
    async def test_list_tools_includes_partstudio_tools(self):
        """Test that Part Studio tools are included."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]

        assert "get_features" in tool_names
        assert "get_parts" in tool_names
        assert "get_elements" in tool_names
        assert "get_assembly" in tool_names

    @pytest.mark.asyncio
    async def test_tool_schema_structure(self):
        """Test that tools have proper schema structure."""
        tools = await list_tools()

        for tool in tools:
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert hasattr(tool, "inputSchema")
            assert isinstance(tool.inputSchema, dict)
            assert "type" in tool.inputSchema
            assert "properties" in tool.inputSchema


class TestCreateSketchRectangle:
    """Test the create_sketch_rectangle tool handler."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_sketch_rectangle_success(self, mock_partstudio):
        """Test successful sketch rectangle creation."""
        mock_partstudio.get_plane_id = AsyncMock(return_value="plane123")
        mock_partstudio.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "feature123"}}
        )

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
            "name": "TestSketch",
            "plane": "Front",
            "corner1": [0, 0],
            "corner2": [10, 10],
        }

        result = await call_tool("create_sketch_rectangle", arguments)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "TestSketch" in result[0].text
        assert "feature123" in result[0].text

        mock_partstudio.get_plane_id.assert_called_once()
        mock_partstudio.add_feature.assert_called_once()

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_sketch_rectangle_with_variables(self, mock_partstudio):
        """Test sketch creation with variable references."""
        mock_partstudio.get_plane_id = AsyncMock(return_value="plane123")
        mock_partstudio.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "feature123"}}
        )

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
            "corner1": [0, 0],
            "corner2": [10, 10],
            "variableWidth": "width",
            "variableHeight": "height",
        }

        result = await call_tool("create_sketch_rectangle", arguments)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_sketch_rectangle_error_handling(self, mock_partstudio):
        """Test error handling in sketch creation."""
        mock_partstudio.get_plane_id = AsyncMock(side_effect=Exception("API Error"))

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
            "corner1": [0, 0],
            "corner2": [10, 10],
        }

        result = await call_tool("create_sketch_rectangle", arguments)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_sketch_rectangle_default_plane(self, mock_partstudio):
        """Test sketch creation with default plane."""
        mock_partstudio.get_plane_id = AsyncMock(return_value="plane123")
        mock_partstudio.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "feature123"}}
        )

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
            "corner1": [0, 0],
            "corner2": [10, 10],
        }

        result = await call_tool("create_sketch_rectangle", arguments)

        assert isinstance(result, list)
        # Should use default "Front" plane
        mock_partstudio.get_plane_id.assert_called_once()
        call_args = mock_partstudio.get_plane_id.call_args
        assert call_args[0][3] == "Front"  # plane_name argument


class TestCreateExtrude:
    """Test the create_extrude tool handler."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_extrude_success(self, mock_partstudio):
        """Test successful extrude creation."""
        mock_partstudio.add_feature = AsyncMock(return_value={"featureId": "extrude123"})

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
            "name": "TestExtrude",
            "sketchFeatureId": "sketch123",
            "depth": 5.0,
        }

        result = await call_tool("create_extrude", arguments)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "TestExtrude" in result[0].text
        assert "extrude123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_extrude_with_variable_depth(self, mock_partstudio):
        """Test extrude creation with variable depth."""
        mock_partstudio.add_feature = AsyncMock(return_value={"featureId": "extrude123"})

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
            "sketchFeatureId": "sketch123",
            "depth": 5.0,
            "variableDepth": "extrude_depth",
        }

        result = await call_tool("create_extrude", arguments)

        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_extrude_with_operation_type(self, mock_partstudio):
        """Test extrude creation with different operation types."""
        mock_partstudio.add_feature = AsyncMock(return_value={"featureId": "extrude123"})

        for op_type in ["NEW", "ADD", "REMOVE", "INTERSECT"]:
            arguments = {
                "documentId": "doc123",
                "workspaceId": "workspace123",
                "elementId": "element123",
                "sketchFeatureId": "sketch123",
                "depth": 5.0,
                "operationType": op_type,
            }

            result = await call_tool("create_extrude", arguments)
            assert isinstance(result, list)
            assert len(result) == 1

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_extrude_http_error(self, mock_partstudio):
        """Test extrude creation with HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Sketch not found"
        mock_partstudio.add_feature = AsyncMock(
            side_effect=httpx.HTTPStatusError("Not Found", request=Mock(), response=mock_response)
        )

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
            "sketchFeatureId": "invalid",
            "depth": 5.0,
        }

        result = await call_tool("create_extrude", arguments)

        assert isinstance(result, list)
        assert "Error" in result[0].text
        assert "404" in result[0].text

    @pytest.mark.asyncio
    async def test_create_extrude_invalid_operation_type(self):
        """Test extrude creation with invalid operation type."""
        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
            "sketchFeatureId": "sketch123",
            "depth": 5.0,
            "operationType": "INVALID",
        }

        result = await call_tool("create_extrude", arguments)

        assert isinstance(result, list)
        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_extrude_value_error(self, mock_partstudio):
        """Test extrude creation with value error."""
        mock_partstudio.add_feature = AsyncMock(side_effect=ValueError("Invalid depth"))

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
            "sketchFeatureId": "sketch123",
            "depth": -5.0,
        }

        result = await call_tool("create_extrude", arguments)

        assert isinstance(result, list)
        assert "Error" in result[0].text


class TestCreateThicken:
    """Test the create_thicken tool handler."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_thicken_success(self, mock_partstudio):
        """Test successful thicken creation."""
        mock_partstudio.add_feature = AsyncMock(return_value={"featureId": "thicken123"})

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
            "name": "TestThicken",
            "sketchFeatureId": "sketch123",
            "thickness": 0.5,
        }

        result = await call_tool("create_thicken", arguments)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "TestThicken" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_thicken_with_options(self, mock_partstudio):
        """Test thicken creation with midplane and opposite direction."""
        mock_partstudio.add_feature = AsyncMock(return_value={"featureId": "thicken123"})

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
            "sketchFeatureId": "sketch123",
            "thickness": 0.5,
            "midplane": True,
            "oppositeDirection": True,
        }

        result = await call_tool("create_thicken", arguments)

        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_thicken_error_handling(self, mock_partstudio):
        """Test error handling in thicken creation."""
        mock_partstudio.add_feature = AsyncMock(side_effect=Exception("API Error"))

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
            "sketchFeatureId": "sketch123",
            "thickness": 0.5,
        }

        result = await call_tool("create_thicken", arguments)

        assert isinstance(result, list)
        assert "Error" in result[0].text


class TestVariableOperations:
    """Test variable management tool handlers."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.variable_manager")
    async def test_get_variables_success(self, mock_variable_manager):
        """Test successful retrieval of variables."""
        mock_variables = [
            Variable(name="width", expression="10 in", description="Width"),
            Variable(name="height", expression="5 in", description="Height"),
        ]
        mock_variable_manager.get_variables = AsyncMock(return_value=mock_variables)

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
        }

        result = await call_tool("get_variables", arguments)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "width" in result[0].text
        assert "height" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.variable_manager")
    async def test_get_variables_empty(self, mock_variable_manager):
        """Test retrieval when no variables exist."""
        mock_variable_manager.get_variables = AsyncMock(return_value=[])

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
        }

        result = await call_tool("get_variables", arguments)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "No variables" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.variable_manager")
    async def test_set_variable_success(self, mock_variable_manager):
        """Test successful variable creation/update."""
        mock_variable_manager.set_variable = AsyncMock(return_value={"success": True})

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
            "name": "depth",
            "expression": "2.5 in",
            "description": "Extrude depth",
        }

        result = await call_tool("set_variable", arguments)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "depth" in result[0].text
        assert "2.5 in" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.variable_manager")
    async def test_set_variable_without_description(self, mock_variable_manager):
        """Test variable creation without description."""
        mock_variable_manager.set_variable = AsyncMock(return_value={"success": True})

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
            "name": "depth",
            "expression": "2.5 in",
        }

        result = await call_tool("set_variable", arguments)

        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.variable_manager")
    async def test_variable_operations_error(self, mock_variable_manager):
        """Test error handling in variable operations."""
        mock_variable_manager.get_variables = AsyncMock(side_effect=Exception("API Error"))

        arguments = {
            "documentId": "doc123",
            "workspaceId": "workspace123",
            "elementId": "element123",
        }

        result = await call_tool("get_variables", arguments)

        assert isinstance(result, list)
        assert "Error" in result[0].text


class TestDocumentOperations:
    """Test document management tool handlers."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.document_manager")
    async def test_list_documents_success(self, mock_document_manager):
        """Test successful document listing."""
        from datetime import datetime
        mock_docs = [
            DocumentInfo(
                id="doc1",
                name="Document 1",
                createdAt=datetime(2024, 1, 1),
                modifiedAt=datetime(2024, 1, 1),
                ownerId="user1",
            ),
            DocumentInfo(
                id="doc2",
                name="Document 2",
                createdAt=datetime(2024, 1, 2),
                modifiedAt=datetime(2024, 1, 2),
                ownerId="user2",
            ),
        ]
        mock_document_manager.list_documents = AsyncMock(return_value=mock_docs)

        arguments = {}

        result = await call_tool("list_documents", arguments)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "Document 1" in result[0].text
        assert "Document 2" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.document_manager")
    async def test_list_documents_with_filters(self, mock_document_manager):
        """Test document listing with filters."""
        mock_document_manager.list_documents = AsyncMock(return_value=[])

        arguments = {
            "filterType": "owned",
            "sortBy": "name",
            "sortOrder": "asc",
            "limit": 10,
        }

        result = await call_tool("list_documents", arguments)

        assert isinstance(result, list)
        mock_document_manager.list_documents.assert_called_once()

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.document_manager")
    async def test_search_documents_success(self, mock_document_manager):
        """Test successful document search."""
        from datetime import datetime
        mock_docs = [
            DocumentInfo(
                id="doc1",
                name="Test Document",
                createdAt=datetime(2024, 1, 1),
                modifiedAt=datetime(2024, 1, 1),
                ownerId="user1",
            )
        ]
        mock_document_manager.search_documents = AsyncMock(return_value=mock_docs)

        arguments = {"query": "test", "limit": 20}

        result = await call_tool("search_documents", arguments)

        assert isinstance(result, list)
        assert "Test Document" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.document_manager")
    async def test_get_document_success(self, mock_document_manager):
        """Test successful document retrieval."""
        from datetime import datetime
        mock_doc = DocumentInfo(
            id="doc123",
            name="Test Document",
            createdAt=datetime(2024, 1, 1),
            modifiedAt=datetime(2024, 1, 1),
            ownerId="user1",
        )
        mock_document_manager.get_document = AsyncMock(return_value=mock_doc)

        arguments = {"documentId": "doc123"}

        result = await call_tool("get_document", arguments)

        assert isinstance(result, list)
        assert "Test Document" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.document_manager")
    async def test_get_document_summary_success(self, mock_document_manager):
        """Test successful document summary retrieval."""
        from datetime import datetime
        # get_document_summary returns a structured dict with document and workspace details
        mock_summary = {
            "document": DocumentInfo(
                id="doc123",
                name="Test Document",
                createdAt=datetime(2024, 1, 1),
                modifiedAt=datetime(2024, 1, 1),
                ownerId="user1",
            ),
            "workspaces": [],
            "workspace_details": [],
        }
        mock_document_manager.get_document_summary = AsyncMock(return_value=mock_summary)

        arguments = {"documentId": "doc123"}

        result = await call_tool("get_document_summary", arguments)

        assert isinstance(result, list)
        assert "Test Document" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.document_manager")
    async def test_find_part_studios_success(self, mock_document_manager):
        """Test finding Part Studios."""
        mock_studios = [
            ElementInfo(id="ps1", name="Part Studio 1", elementType="PARTSTUDIO"),
            ElementInfo(id="ps2", name="Part Studio 2", elementType="PARTSTUDIO"),
        ]
        mock_document_manager.find_part_studios = AsyncMock(return_value=mock_studios)

        arguments = {"documentId": "doc123", "workspaceId": "ws123"}

        result = await call_tool("find_part_studios", arguments)

        assert isinstance(result, list)
        assert "Part Studio 1" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.document_manager")
    async def test_document_operations_error(self, mock_document_manager):
        """Test error handling in document operations."""
        mock_document_manager.list_documents = AsyncMock(side_effect=Exception("API Error"))

        arguments = {}

        result = await call_tool("list_documents", arguments)

        assert isinstance(result, list)
        assert "Error" in result[0].text


class TestPartStudioOperations:
    """Test Part Studio tool handlers."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_get_features_success(self, mock_partstudio):
        """Test successful feature retrieval."""
        mock_features = [
            {"featureId": "f1", "name": "Sketch 1"},
            {"featureId": "f2", "name": "Extrude 1"},
        ]
        mock_partstudio.get_features = AsyncMock(return_value=mock_features)

        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "el123",
        }

        result = await call_tool("get_features", arguments)

        assert isinstance(result, list)
        assert "Sketch 1" in result[0].text
        assert "Extrude 1" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_get_parts_success(self, mock_partstudio):
        """Test successful parts retrieval."""
        mock_parts = [
            {"partId": "p1", "name": "Part 1"},
            {"partId": "p2", "name": "Part 2"},
        ]
        mock_partstudio.get_parts = AsyncMock(return_value=mock_parts)

        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "el123",
        }

        result = await call_tool("get_parts", arguments)

        assert isinstance(result, list)
        assert "Part 1" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.document_manager")
    async def test_get_elements_success(self, mock_document_manager):
        """Test successful element retrieval."""
        mock_elements = [
            ElementInfo(id="el1", name="Part Studio", elementType="PARTSTUDIO"),
            ElementInfo(id="el2", name="Assembly", elementType="ASSEMBLY"),
        ]
        mock_document_manager.get_elements = AsyncMock(return_value=mock_elements)

        arguments = {"documentId": "doc123", "workspaceId": "ws123"}

        result = await call_tool("get_elements", arguments)

        assert isinstance(result, list)
        assert "Part Studio" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.document_manager")
    async def test_get_elements_with_type_filter(self, mock_document_manager):
        """Test element retrieval with type filter."""
        mock_document_manager.get_elements = AsyncMock(return_value=[])

        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementType": "PARTSTUDIO",
        }

        result = await call_tool("get_elements", arguments)

        assert isinstance(result, list)


class TestGetAssembly:
    """Test get_assembly tool handler."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.client")
    async def test_get_assembly_success(self, mock_client):
        """Test successful assembly retrieval."""
        mock_assembly = {
            "rootAssembly": {
                "instances": [{"id": "inst1", "name": "Instance 1"}],
                "occurrences": [{"path": ["occ1"]}],
            }
        }
        mock_client.get = AsyncMock(return_value=mock_assembly)

        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
        }

        result = await call_tool("get_assembly", arguments)

        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.client")
    async def test_get_assembly_error(self, mock_client):
        """Test error handling in assembly retrieval."""
        mock_client.get = AsyncMock(side_effect=Exception("API Error"))

        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
        }

        result = await call_tool("get_assembly", arguments)

        assert isinstance(result, list)
        assert "Error" in result[0].text


class TestUnknownTool:
    """Test handling of unknown tools."""

    @pytest.mark.asyncio
    async def test_unknown_tool_name(self):
        """Test calling an unknown tool."""
        with pytest.raises(ValueError, match="Unknown tool"):
            await call_tool("unknown_tool", {})
