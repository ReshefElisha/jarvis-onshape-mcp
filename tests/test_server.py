"""Tests for the MCP server."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import httpx
from mcp.types import Tool, TextContent

# Import the server module components
from onshape_mcp.server import list_tools, call_tool
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
        assert "create_document" in tool_names
        assert "create_part_studio" in tool_names

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
    async def test_list_tools_includes_assembly_tools(self):
        """Test that assembly management tools are included."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]

        assert "create_assembly" in tool_names
        assert "add_assembly_instance" in tool_names
        assert "transform_instance" in tool_names
        assert "create_fastened_mate" in tool_names
        assert "create_revolute_mate" in tool_names
        assert "create_slider_mate" in tool_names
        assert "create_cylindrical_mate" in tool_names
        assert "create_mate_connector" in tool_names

    @pytest.mark.asyncio
    async def test_list_tools_includes_feature_tools(self):
        """Test that feature builder tools are included."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]

        assert "create_sketch_circle" in tool_names
        assert "create_sketch_line" in tool_names
        assert "create_sketch_arc" in tool_names
        assert "create_fillet" in tool_names
        assert "create_chamfer" in tool_names
        assert "create_revolve" in tool_names
        assert "create_linear_pattern" in tool_names
        assert "create_circular_pattern" in tool_names
        assert "create_boolean" in tool_names

    @pytest.mark.asyncio
    async def test_list_tools_includes_featurescript_tools(self):
        """Test that FeatureScript tools are included."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]

        assert "eval_featurescript" in tool_names
        assert "get_bounding_box" in tool_names

    @pytest.mark.asyncio
    async def test_list_tools_includes_export_tools(self):
        """Test that export tools are included."""
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]

        assert "export_part_studio" in tool_names
        assert "export_assembly" in tool_names

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
    @patch("onshape_mcp.server.assembly_manager")
    async def test_get_assembly_success(self, mock_asm):
        """Test successful assembly retrieval."""
        mock_assembly = {
            "rootAssembly": {
                "instances": [{"id": "inst1", "name": "Instance 1"}],
                "occurrences": [{"path": ["occ1"]}],
            }
        }
        mock_asm.get_assembly_definition = AsyncMock(return_value=mock_assembly)

        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
        }

        result = await call_tool("get_assembly", arguments)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "Instance 1" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_get_assembly_error(self, mock_asm):
        """Test error handling in assembly retrieval."""
        mock_asm.get_assembly_definition = AsyncMock(side_effect=Exception("API Error"))

        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
        }

        result = await call_tool("get_assembly", arguments)

        assert isinstance(result, list)
        assert "Error" in result[0].text


class TestCreateDocumentTool:
    """Test create_document tool handler."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.document_manager")
    async def test_create_document_success(self, mock_document_manager):
        """Test successful document creation via tool."""
        from datetime import datetime

        mock_doc = DocumentInfo(
            id="new_doc_123",
            name="New Document",
            createdAt=datetime(2024, 1, 1),
            modifiedAt=datetime(2024, 1, 1),
            ownerId="user1",
        )
        mock_document_manager.create_document = AsyncMock(return_value=mock_doc)

        arguments = {"name": "New Document"}

        result = await call_tool("create_document", arguments)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "New Document" in result[0].text
        assert "new_doc_123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.document_manager")
    async def test_create_document_with_options(self, mock_document_manager):
        """Test document creation with description and isPublic."""
        from datetime import datetime

        mock_doc = DocumentInfo(
            id="new_doc_456",
            name="Public Doc",
            createdAt=datetime(2024, 1, 1),
            modifiedAt=datetime(2024, 1, 1),
            ownerId="user1",
            public=True,
            description="A public document",
        )
        mock_document_manager.create_document = AsyncMock(return_value=mock_doc)

        arguments = {
            "name": "Public Doc",
            "description": "A public document",
            "isPublic": True,
        }

        result = await call_tool("create_document", arguments)

        assert isinstance(result, list)
        assert "Public Doc" in result[0].text
        mock_document_manager.create_document.assert_called_once_with(
            name="Public Doc",
            description="A public document",
            is_public=True,
        )

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.document_manager")
    async def test_create_document_http_error(self, mock_document_manager):
        """Test document creation with HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_document_manager.create_document = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Forbidden", request=Mock(), response=mock_response
            )
        )

        arguments = {"name": "Forbidden Doc"}

        result = await call_tool("create_document", arguments)

        assert isinstance(result, list)
        assert "Error" in result[0].text
        assert "403" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.document_manager")
    async def test_create_document_generic_error(self, mock_document_manager):
        """Test document creation with generic error."""
        mock_document_manager.create_document = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        arguments = {"name": "Error Doc"}

        result = await call_tool("create_document", arguments)

        assert isinstance(result, list)
        assert "Error" in result[0].text


class TestCreatePartStudioTool:
    """Test create_part_studio tool handler."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_part_studio_success(self, mock_partstudio):
        """Test successful Part Studio creation via tool."""
        mock_partstudio.create_part_studio = AsyncMock(
            return_value={"id": "new_ps_123", "name": "My Part Studio"}
        )

        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "name": "My Part Studio",
        }

        result = await call_tool("create_part_studio", arguments)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "My Part Studio" in result[0].text
        assert "new_ps_123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_part_studio_http_error(self, mock_partstudio):
        """Test Part Studio creation with HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Document not found"
        mock_partstudio.create_part_studio = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Not Found", request=Mock(), response=mock_response
            )
        )

        arguments = {
            "documentId": "invalid_doc",
            "workspaceId": "ws123",
            "name": "Part Studio",
        }

        result = await call_tool("create_part_studio", arguments)

        assert isinstance(result, list)
        assert "Error" in result[0].text
        assert "404" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_part_studio_generic_error(self, mock_partstudio):
        """Test Part Studio creation with generic error."""
        mock_partstudio.create_part_studio = AsyncMock(
            side_effect=Exception("Unexpected error")
        )

        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "name": "Part Studio",
        }

        result = await call_tool("create_part_studio", arguments)

        assert isinstance(result, list)
        assert "Error" in result[0].text


class TestAssemblyTools:
    """Test assembly tool handlers."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_assembly_success(self, mock_asm):
        """Test successful assembly creation."""
        mock_asm.create_assembly = AsyncMock(return_value={"id": "asm123"})

        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "name": "TestAssembly",
        }

        result = await call_tool("create_assembly", arguments)

        assert isinstance(result, list)
        assert "TestAssembly" in result[0].text
        assert "asm123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_assembly_error(self, mock_asm):
        """Test assembly creation error."""
        mock_asm.create_assembly = AsyncMock(side_effect=Exception("API Error"))

        result = await call_tool("create_assembly", {
            "documentId": "d", "workspaceId": "w", "name": "A",
        })

        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_add_assembly_instance_success(self, mock_asm):
        """Test adding an instance to assembly."""
        mock_asm.add_instance = AsyncMock(return_value={"id": "inst1", "name": "Part 1"})

        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
            "partStudioElementId": "ps123",
            "partId": "part1",
        }

        result = await call_tool("add_assembly_instance", arguments)

        assert "Part 1" in result[0].text
        assert "inst1" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_add_assembly_instance_error(self, mock_asm):
        """Test add instance error."""
        mock_asm.add_instance = AsyncMock(side_effect=Exception("fail"))

        result = await call_tool("add_assembly_instance", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "partStudioElementId": "ps",
        })

        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_transform_instance_success(self, mock_asm):
        """Test transforming an instance."""
        mock_asm.transform_occurrences = AsyncMock(return_value={})

        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
            "instanceId": "inst1",
            "translateX": 5.0,
            "translateY": 0.0,
            "translateZ": 0.0,
        }

        result = await call_tool("transform_instance", arguments)

        assert "Transformed" in result[0].text
        assert "inst1" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_transform_instance_error(self, mock_asm):
        """Test transform instance error."""
        mock_asm.transform_occurrences = AsyncMock(side_effect=Exception("fail"))

        result = await call_tool("transform_instance", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "instanceId": "i",
        })

        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_fastened_mate_success(self, mock_asm):
        """Test creating a fastened mate."""
        mock_asm.add_feature = AsyncMock(
            side_effect=[
                {"feature": {"featureId": "mc1_id"}},
                {"feature": {"featureId": "mc2_id"}},
                {"feature": {"featureId": "mate123"}},
            ]
        )

        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
            "firstInstanceId": "inst1",
            "secondInstanceId": "inst2",
            "firstFaceId": "JHW",
            "secondFaceId": "JKW",
            "name": "MyMate",
        }

        result = await call_tool("create_fastened_mate", arguments)

        assert "MyMate" in result[0].text
        assert "mate123" in result[0].text
        assert mock_asm.add_feature.call_count == 3

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_fastened_mate_error(self, mock_asm):
        """Test fastened mate error."""
        mock_asm.add_feature = AsyncMock(side_effect=Exception("fail"))

        result = await call_tool("create_fastened_mate", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "firstInstanceId": "a", "secondInstanceId": "b",
            "firstFaceId": "f1", "secondFaceId": "f2",
        })

        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_revolute_mate_success(self, mock_asm):
        """Test creating a revolute mate."""
        mock_asm.add_feature = AsyncMock(
            side_effect=[
                {"feature": {"featureId": "mc1_id"}},
                {"feature": {"featureId": "mc2_id"}},
                {"feature": {"featureId": "rmate123"}},
            ]
        )

        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
            "firstInstanceId": "inst1",
            "secondInstanceId": "inst2",
            "firstFaceId": "JHW",
            "secondFaceId": "JKW",
        }

        result = await call_tool("create_revolute_mate", arguments)

        assert "Revolute mate" in result[0].text
        assert "rmate123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_slider_mate_success(self, mock_asm):
        """Test creating a slider mate."""
        mock_asm.add_feature = AsyncMock(
            side_effect=[
                {"feature": {"featureId": "mc1_id"}},
                {"feature": {"featureId": "mc2_id"}},
                {"feature": {"featureId": "slide123"}},
            ]
        )
        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
            "firstInstanceId": "inst1",
            "secondInstanceId": "inst2",
            "firstFaceId": "JHW",
            "secondFaceId": "JKW",
            "name": "Drawer Slide",
        }
        result = await call_tool("create_slider_mate", arguments)
        assert "Drawer Slide" in result[0].text
        assert "slide123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_slider_mate_error(self, mock_asm):
        """Test slider mate error."""
        mock_asm.add_feature = AsyncMock(side_effect=Exception("fail"))
        result = await call_tool("create_slider_mate", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "firstInstanceId": "a", "secondInstanceId": "b",
            "firstFaceId": "f1", "secondFaceId": "f2",
        })
        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_slider_mate_with_limits(self, mock_asm):
        """Test slider mate with travel limits."""
        mock_asm.add_feature = AsyncMock(
            side_effect=[
                {"feature": {"featureId": "mc1_id"}},
                {"feature": {"featureId": "mc2_id"}},
                {"feature": {"featureId": "slide456"}},
            ]
        )
        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
            "firstInstanceId": "inst1",
            "secondInstanceId": "inst2",
            "firstFaceId": "JHW",
            "secondFaceId": "JKW",
            "minLimit": -14.0,
            "maxLimit": 0.0,
        }
        result = await call_tool("create_slider_mate", arguments)
        assert "slide456" in result[0].text
        # Third call is the mate itself (after 2 mate connectors)
        call_args = mock_asm.add_feature.call_args
        feature_data = call_args.kwargs["feature_data"]
        params = feature_data["feature"]["parameters"]
        param_ids = [p["parameterId"] for p in params]
        assert "limitsEnabled" in param_ids

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_cylindrical_mate_success(self, mock_asm):
        """Test creating a cylindrical mate."""
        mock_asm.add_feature = AsyncMock(
            side_effect=[
                {"feature": {"featureId": "mc1_id"}},
                {"feature": {"featureId": "mc2_id"}},
                {"feature": {"featureId": "cyl123"}},
            ]
        )
        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
            "firstInstanceId": "inst1",
            "secondInstanceId": "inst2",
            "firstFaceId": "JHW",
            "secondFaceId": "JKW",
        }
        result = await call_tool("create_cylindrical_mate", arguments)
        assert "Cylindrical mate" in result[0].text
        assert "cyl123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_cylindrical_mate_error(self, mock_asm):
        """Test cylindrical mate error."""
        mock_asm.add_feature = AsyncMock(side_effect=Exception("fail"))
        result = await call_tool("create_cylindrical_mate", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "firstInstanceId": "a", "secondInstanceId": "b",
            "firstFaceId": "f1", "secondFaceId": "f2",
        })
        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_mate_connector_success(self, mock_asm):
        """Test creating a mate connector."""
        mock_asm.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "mc123"}}
        )
        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
            "instanceId": "inst1",
            "faceId": "JHW",
            "name": "Slide Connector",
        }
        result = await call_tool("create_mate_connector", arguments)
        assert "Slide Connector" in result[0].text
        assert "mc123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_mate_connector_default_values(self, mock_asm):
        """Test mate connector with defaults."""
        mock_asm.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "mc456"}}
        )
        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
            "instanceId": "inst1",
            "faceId": "JKW",
        }
        result = await call_tool("create_mate_connector", arguments)
        assert "mc456" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_mate_connector_error(self, mock_asm):
        """Test mate connector error."""
        mock_asm.add_feature = AsyncMock(side_effect=Exception("fail"))
        result = await call_tool("create_mate_connector", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "instanceId": "i", "faceId": "f1",
        })
        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_revolute_mate_with_limits(self, mock_asm):
        """Test revolute mate with rotation limits."""
        mock_asm.add_feature = AsyncMock(
            side_effect=[
                {"feature": {"featureId": "mc1_id"}},
                {"feature": {"featureId": "mc2_id"}},
                {"feature": {"featureId": "rev456"}},
            ]
        )
        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
            "firstInstanceId": "inst1",
            "secondInstanceId": "inst2",
            "firstFaceId": "JHW",
            "secondFaceId": "JKW",
            "minLimit": -45.0,
            "maxLimit": 90.0,
        }
        result = await call_tool("create_revolute_mate", arguments)
        assert "rev456" in result[0].text
        # Third call is the mate itself (after 2 mate connectors)
        call_args = mock_asm.add_feature.call_args
        feature_data = call_args.kwargs["feature_data"]
        params = feature_data["feature"]["parameters"]
        param_ids = [p["parameterId"] for p in params]
        assert "limitsEnabled" in param_ids
        assert "limitRotationMin" in param_ids
        assert "limitRotationMax" in param_ids
        min_param = next(p for p in params if p["parameterId"] == "limitRotationMin")
        assert "rad" in min_param["expression"]

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_revolute_mate_error(self, mock_asm):
        """Test revolute mate error."""
        mock_asm.add_feature = AsyncMock(side_effect=Exception("fail"))
        result = await call_tool("create_revolute_mate", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "firstInstanceId": "a", "secondInstanceId": "b",
            "firstFaceId": "f1", "secondFaceId": "f2",
        })
        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_cylindrical_mate_with_limits(self, mock_asm):
        """Test cylindrical mate with axial travel limits."""
        mock_asm.add_feature = AsyncMock(
            side_effect=[
                {"feature": {"featureId": "mc1_id"}},
                {"feature": {"featureId": "mc2_id"}},
                {"feature": {"featureId": "cyl456"}},
            ]
        )
        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
            "firstInstanceId": "inst1",
            "secondInstanceId": "inst2",
            "firstFaceId": "JHW",
            "secondFaceId": "JKW",
            "minLimit": 0.0,
            "maxLimit": 12.0,
        }
        result = await call_tool("create_cylindrical_mate", arguments)
        assert "cyl456" in result[0].text
        # Third call is the mate itself
        call_args = mock_asm.add_feature.call_args
        feature_data = call_args.kwargs["feature_data"]
        params = feature_data["feature"]["parameters"]
        param_ids = [p["parameterId"] for p in params]
        assert "limitsEnabled" in param_ids
        assert "limitAxialZMin" in param_ids
        assert "limitAxialZMax" in param_ids

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_slider_mate_feature_data_structure(self, mock_asm):
        """Test that slider mate sends correct mate type in feature data."""
        mock_asm.add_feature = AsyncMock(
            side_effect=[
                {"feature": {"featureId": "mc1_id"}},
                {"feature": {"featureId": "mc2_id"}},
                {"feature": {"featureId": "s789"}},
            ]
        )
        await call_tool("create_slider_mate", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "firstInstanceId": "a", "secondInstanceId": "b",
            "firstFaceId": "f1", "secondFaceId": "f2",
        })
        # Third call is the mate itself
        call_args = mock_asm.add_feature.call_args
        feature_data = call_args.kwargs["feature_data"]
        params = feature_data["feature"]["parameters"]
        type_param = next(p for p in params if p["parameterId"] == "mateType")
        assert type_param["value"] == "SLIDER"

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_mate_connector_feature_data_structure(self, mock_asm):
        """Test mate connector sends correct feature data structure."""
        mock_asm.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "mc789"}}
        )
        arguments = {
            "documentId": "doc123",
            "workspaceId": "ws123",
            "elementId": "asm123",
            "instanceId": "inst1",
            "faceId": "JHW",
        }
        result = await call_tool("create_mate_connector", arguments)
        assert "mc789" in result[0].text
        call_args = mock_asm.add_feature.call_args
        feature_data = call_args.kwargs["feature_data"]
        params = feature_data["feature"]["parameters"]
        origin_type = next(p for p in params if p["parameterId"] == "originType")
        assert origin_type["value"] == "ON_ENTITY"
        origin_query = next(p for p in params if p["parameterId"] == "originQuery")
        query = origin_query["queries"][0]
        assert query["btType"] == "BTMInferenceQueryWithOccurrence-1083"
        assert query["inferenceType"] == "CENTROID"
        assert query["path"] == ["inst1"]
        assert query["deterministicIds"] == ["JHW"]

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_mate_connector_with_flip_primary(self, mock_asm):
        """Test mate connector flipPrimary parameter flows to feature data."""
        mock_asm.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "mc_flip"}}
        )
        arguments = {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "instanceId": "inst1",
            "faceId": "JHW",
            "flipPrimary": True,
        }
        result = await call_tool("create_mate_connector", arguments)
        assert "mc_flip" in result[0].text
        call_args = mock_asm.add_feature.call_args
        feature_data = call_args.kwargs["feature_data"]
        params = feature_data["feature"]["parameters"]
        flip = next(p for p in params if p["parameterId"] == "flipPrimary")
        assert flip["value"] is True

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.assembly_manager")
    async def test_create_fastened_mate_http_error(self, mock_asm):
        """Test fastened mate with HTTP status error includes details."""
        import httpx
        response = Mock()
        response.status_code = 400
        response.text = "Bad request: invalid instance"
        # Error on first add_feature call (mate connector creation)
        mock_asm.add_feature = AsyncMock(
            side_effect=httpx.HTTPStatusError("error", request=Mock(), response=response)
        )
        result = await call_tool("create_fastened_mate", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "firstInstanceId": "a", "secondInstanceId": "b",
            "firstFaceId": "f1", "secondFaceId": "f2",
        })
        assert "400" in result[0].text
        assert "Bad request" in result[0].text


class TestFeatureTools:
    """Test feature builder tool handlers."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_sketch_circle_success(self, mock_ps):
        """Test creating a sketch circle."""
        mock_ps.get_plane_id = AsyncMock(return_value="plane1")
        mock_ps.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "circ123"}}
        )

        arguments = {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "radius": 2.0,
        }

        result = await call_tool("create_sketch_circle", arguments)

        assert "circle" in result[0].text.lower()
        assert "circ123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_sketch_circle_error(self, mock_ps):
        """Test sketch circle error."""
        mock_ps.get_plane_id = AsyncMock(side_effect=Exception("fail"))

        result = await call_tool("create_sketch_circle", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "radius": 1.0,
        })

        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_sketch_line_success(self, mock_ps):
        """Test creating a sketch line."""
        mock_ps.get_plane_id = AsyncMock(return_value="plane1")
        mock_ps.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "line123"}}
        )

        arguments = {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "startPoint": [0, 0], "endPoint": [10, 10],
        }

        result = await call_tool("create_sketch_line", arguments)

        assert "line" in result[0].text.lower()
        assert "line123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_sketch_arc_success(self, mock_ps):
        """Test creating a sketch arc."""
        mock_ps.get_plane_id = AsyncMock(return_value="plane1")
        mock_ps.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "arc123"}}
        )

        arguments = {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "radius": 1.5, "startAngle": 0, "endAngle": 90,
        }

        result = await call_tool("create_sketch_arc", arguments)

        assert "arc" in result[0].text.lower()
        assert "arc123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_sketch_arc_error(self, mock_ps):
        """Test sketch arc error."""
        mock_ps.get_plane_id = AsyncMock(side_effect=Exception("fail"))

        result = await call_tool("create_sketch_arc", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "radius": 1.0,
        })

        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_fillet_success(self, mock_ps):
        """Test creating a fillet."""
        mock_ps.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "fillet123"}}
        )

        arguments = {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "radius": 0.25, "edgeIds": ["edge1", "edge2"],
        }

        result = await call_tool("create_fillet", arguments)

        assert "fillet" in result[0].text.lower()
        assert "fillet123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_fillet_error(self, mock_ps):
        """Test fillet error."""
        mock_ps.add_feature = AsyncMock(side_effect=Exception("fail"))

        result = await call_tool("create_fillet", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "radius": 0.1, "edgeIds": ["e1"],
        })

        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_chamfer_success(self, mock_ps):
        """Test creating a chamfer."""
        mock_ps.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "chamfer123"}}
        )

        arguments = {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "distance": 0.1, "edgeIds": ["edge1"],
        }

        result = await call_tool("create_chamfer", arguments)

        assert "chamfer" in result[0].text.lower()

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_revolve_success(self, mock_ps):
        """Test creating a revolve."""
        mock_ps.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "rev123"}}
        )

        arguments = {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "sketchFeatureId": "sketch1", "axis": "Y", "angle": 360,
        }

        result = await call_tool("create_revolve", arguments)

        assert "revolve" in result[0].text.lower()
        assert "rev123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_revolve_error(self, mock_ps):
        """Test revolve error."""
        mock_ps.add_feature = AsyncMock(side_effect=Exception("fail"))

        result = await call_tool("create_revolve", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "sketchFeatureId": "s1",
        })

        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_linear_pattern_success(self, mock_ps):
        """Test creating a linear pattern."""
        mock_ps.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "lp123"}}
        )

        arguments = {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "distance": 2.0, "count": 5, "featureIds": ["f1"],
            "direction": "X",
        }

        result = await call_tool("create_linear_pattern", arguments)

        assert "pattern" in result[0].text.lower()
        assert "lp123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_circular_pattern_success(self, mock_ps):
        """Test creating a circular pattern."""
        mock_ps.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "cp123"}}
        )

        arguments = {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "count": 6, "featureIds": ["f1"],
        }

        result = await call_tool("create_circular_pattern", arguments)

        assert "pattern" in result[0].text.lower()
        assert "cp123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_boolean_success(self, mock_ps):
        """Test creating a boolean operation."""
        mock_ps.add_feature = AsyncMock(
            return_value={"feature": {"featureId": "bool123"}}
        )

        arguments = {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "booleanType": "UNION", "toolBodyIds": ["b1", "b2"],
        }

        result = await call_tool("create_boolean", arguments)

        assert "union" in result[0].text.lower()
        assert "bool123" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.partstudio_manager")
    async def test_create_boolean_error(self, mock_ps):
        """Test boolean error."""
        mock_ps.add_feature = AsyncMock(side_effect=Exception("fail"))

        result = await call_tool("create_boolean", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "booleanType": "SUBTRACT", "toolBodyIds": ["b1"],
            "targetBodyIds": ["t1"],
        })

        assert "Error" in result[0].text


class TestFeatureScriptTools:
    """Test FeatureScript tool handlers."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.featurescript_manager")
    async def test_eval_featurescript_success(self, mock_fs):
        """Test evaluating FeatureScript."""
        mock_fs.evaluate = AsyncMock(return_value={"result": {"value": 42}})

        arguments = {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "script": "function(context, queries) { return 42; }",
        }

        result = await call_tool("eval_featurescript", arguments)

        assert "42" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.featurescript_manager")
    async def test_eval_featurescript_error(self, mock_fs):
        """Test FeatureScript evaluation error."""
        mock_fs.evaluate = AsyncMock(side_effect=Exception("parse error"))

        result = await call_tool("eval_featurescript", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "script": "bad",
        })

        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.featurescript_manager")
    async def test_get_bounding_box_success(self, mock_fs):
        """Test getting bounding box."""
        mock_fs.get_bounding_box = AsyncMock(
            return_value={"result": {"minCorner": [0, 0, 0], "maxCorner": [1, 1, 1]}}
        )

        arguments = {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
        }

        result = await call_tool("get_bounding_box", arguments)

        assert "bounding box" in result[0].text.lower() or "Bounding" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.featurescript_manager")
    async def test_get_bounding_box_error(self, mock_fs):
        """Test bounding box error."""
        mock_fs.get_bounding_box = AsyncMock(side_effect=Exception("fail"))

        result = await call_tool("get_bounding_box", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
        })

        assert "Error" in result[0].text


class TestExportTools:
    """Test export tool handlers."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.export_manager")
    async def test_export_part_studio_success(self, mock_export):
        """Test exporting a part studio."""
        mock_export.export_part_studio = AsyncMock(
            return_value={"id": "trans123", "requestState": "ACTIVE"}
        )

        arguments = {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "format": "STL",
        }

        result = await call_tool("export_part_studio", arguments)

        assert "trans123" in result[0].text
        assert "ACTIVE" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.export_manager")
    async def test_export_part_studio_error(self, mock_export):
        """Test export part studio error."""
        mock_export.export_part_studio = AsyncMock(side_effect=Exception("fail"))

        result = await call_tool("export_part_studio", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
        })

        assert "Error" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.export_manager")
    async def test_export_assembly_success(self, mock_export):
        """Test exporting an assembly."""
        mock_export.export_assembly = AsyncMock(
            return_value={"id": "trans456", "requestState": "ACTIVE"}
        )

        arguments = {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "format": "STEP",
        }

        result = await call_tool("export_assembly", arguments)

        assert "trans456" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.export_manager")
    async def test_export_assembly_error(self, mock_export):
        """Test export assembly error."""
        mock_export.export_assembly = AsyncMock(side_effect=Exception("fail"))

        result = await call_tool("export_assembly", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
        })

        assert "Error" in result[0].text


class TestListToolsPositioning:
    """Test that positioning tools are registered."""

    @pytest.mark.asyncio
    async def test_includes_get_assembly_positions(self):
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]
        assert "get_assembly_positions" in tool_names

    @pytest.mark.asyncio
    async def test_includes_set_instance_position(self):
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]
        assert "set_instance_position" in tool_names

    @pytest.mark.asyncio
    async def test_includes_align_instance_to_face(self):
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]
        assert "align_instance_to_face" in tool_names


class TestGetAssemblyPositionsTool:
    """Test get_assembly_positions tool handler."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.get_assembly_positions")
    async def test_success(self, mock_fn):
        mock_fn.return_value = "Assembly Instance Positions\nFound 2 instance(s)"
        result = await call_tool("get_assembly_positions", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
        })
        assert isinstance(result, list)
        assert isinstance(result[0], TextContent)
        assert "Positions" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.get_assembly_positions")
    async def test_error(self, mock_fn):
        mock_fn.side_effect = Exception("API failure")
        result = await call_tool("get_assembly_positions", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
        })
        assert "Error" in result[0].text


class TestSetInstancePositionTool:
    """Test set_instance_position tool handler."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.set_absolute_position")
    async def test_success(self, mock_fn):
        mock_fn.return_value = 'Set instance inst1 to absolute position: X=10.000", Y=-5.000", Z=0.000"'
        result = await call_tool("set_instance_position", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "instanceId": "inst1", "x": 10.0, "y": -5.0, "z": 0.0,
        })
        assert isinstance(result[0], TextContent)
        assert "10.000" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.set_absolute_position")
    async def test_error(self, mock_fn):
        mock_fn.side_effect = Exception("fail")
        result = await call_tool("set_instance_position", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "instanceId": "i", "x": 0, "y": 0, "z": 0,
        })
        assert "Error" in result[0].text


class TestAlignInstanceToFaceTool:
    """Test align_instance_to_face tool handler."""

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.align_to_face")
    async def test_success(self, mock_fn):
        mock_fn.return_value = "Aligned 'Door' to 'front' face of 'Cabinet'."
        result = await call_tool("align_instance_to_face", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "sourceInstanceId": "s1", "targetInstanceId": "t1", "face": "front",
        })
        assert "Aligned" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.align_to_face")
    async def test_invalid_face(self, mock_fn):
        mock_fn.side_effect = ValueError("Invalid face 'middle'")
        result = await call_tool("align_instance_to_face", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "sourceInstanceId": "s1", "targetInstanceId": "t1", "face": "middle",
        })
        assert "Invalid" in result[0].text

    @pytest.mark.asyncio
    @patch("onshape_mcp.server.align_to_face")
    async def test_error(self, mock_fn):
        mock_fn.side_effect = Exception("API fail")
        result = await call_tool("align_instance_to_face", {
            "documentId": "d", "workspaceId": "w", "elementId": "e",
            "sourceInstanceId": "s1", "targetInstanceId": "t1", "face": "front",
        })
        assert "Error" in result[0].text


class TestUnknownTool:
    """Test handling of unknown tools."""

    @pytest.mark.asyncio
    async def test_unknown_tool_name(self):
        """Test calling an unknown tool."""
        with pytest.raises(ValueError, match="Unknown tool"):
            await call_tool("unknown_tool", {})
