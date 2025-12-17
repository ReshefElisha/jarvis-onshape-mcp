"""Main MCP server for Onshape integration."""

import os
import sys
import asyncio
from typing import Any
import httpx
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from loguru import logger

# Load environment variables from .env file
# Look for .env in the package directory (where this server.py lives)
_package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_package_dir, '.env'))

from .api.client import OnshapeClient, OnshapeCredentials
from .api.partstudio import PartStudioManager
from .api.variables import VariableManager
from .api.documents import DocumentManager
from .builders.sketch import SketchBuilder, SketchPlane
from .builders.extrude import ExtrudeBuilder, ExtrudeType
from .builders.thicken import ThickenBuilder, ThickenType

# Configure loguru to output to stderr
logger.remove()  # Remove default handler
logger.add(
    sys.stderr,
    level="DEBUG",
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
)


# Initialize server
app = Server("onshape-mcp")

# Initialize Onshape client
credentials = OnshapeCredentials(
    access_key=os.getenv("ONSHAPE_ACCESS_KEY", ""), secret_key=os.getenv("ONSHAPE_SECRET_KEY", "")
)
client = OnshapeClient(credentials)
partstudio_manager = PartStudioManager(client)
variable_manager = VariableManager(client)
document_manager = DocumentManager(client)


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="create_sketch_rectangle",
            description="Create a rectangular sketch in a Part Studio with optional variable references",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "name": {"type": "string", "description": "Sketch name", "default": "Sketch"},
                    "plane": {
                        "type": "string",
                        "enum": ["Front", "Top", "Right"],
                        "description": "Sketch plane",
                        "default": "Front",
                    },
                    "corner1": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "First corner [x, y] in inches",
                    },
                    "corner2": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "Second corner [x, y] in inches",
                    },
                    "variableWidth": {
                        "type": "string",
                        "description": "Optional variable name for width",
                    },
                    "variableHeight": {
                        "type": "string",
                        "description": "Optional variable name for height",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "corner1", "corner2"],
            },
        ),
        Tool(
            name="create_extrude",
            description="Create an extrude feature from a sketch",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "name": {"type": "string", "description": "Extrude name", "default": "Extrude"},
                    "sketchFeatureId": {"type": "string", "description": "ID of sketch to extrude"},
                    "depth": {"type": "number", "description": "Extrude depth in inches"},
                    "variableDepth": {
                        "type": "string",
                        "description": "Optional variable name for depth",
                    },
                    "operationType": {
                        "type": "string",
                        "enum": ["NEW", "ADD", "REMOVE", "INTERSECT"],
                        "description": "Extrude operation type",
                        "default": "NEW",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "sketchFeatureId", "depth"],
            },
        ),
        Tool(
            name="create_thicken",
            description="Create a thicken feature from a sketch",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "name": {"type": "string", "description": "Thicken name", "default": "Thicken"},
                    "sketchFeatureId": {"type": "string", "description": "ID of sketch to thicken"},
                    "thickness": {"type": "number", "description": "Thickness in inches"},
                    "variableThickness": {
                        "type": "string",
                        "description": "Optional variable name for thickness",
                    },
                    "operationType": {
                        "type": "string",
                        "enum": ["NEW", "ADD", "REMOVE", "INTERSECT"],
                        "description": "Thicken operation type",
                        "default": "NEW",
                    },
                    "midplane": {
                        "type": "boolean",
                        "description": "Thicken symmetrically from sketch plane",
                        "default": False,
                    },
                    "oppositeDirection": {
                        "type": "boolean",
                        "description": "Thicken in opposite direction",
                        "default": False,
                    },
                },
                "required": [
                    "documentId",
                    "workspaceId",
                    "elementId",
                    "sketchFeatureId",
                    "thickness",
                ],
            },
        ),
        Tool(
            name="get_variables",
            description="Get all variables from a Part Studio variable table",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                },
                "required": ["documentId", "workspaceId", "elementId"],
            },
        ),
        Tool(
            name="set_variable",
            description="Set or update a variable in a Part Studio variable table",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "name": {"type": "string", "description": "Variable name"},
                    "expression": {
                        "type": "string",
                        "description": "Variable expression (e.g., '0.75 in')",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional variable description",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "name", "expression"],
            },
        ),
        Tool(
            name="get_features",
            description="Get all features from a Part Studio",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                },
                "required": ["documentId", "workspaceId", "elementId"],
            },
        ),
        Tool(
            name="list_documents",
            description="List documents in your Onshape account with optional filtering and sorting",
            inputSchema={
                "type": "object",
                "properties": {
                    "filterType": {
                        "type": "string",
                        "enum": ["all", "owned", "created", "shared"],
                        "description": "Filter documents by type",
                        "default": "all",
                    },
                    "sortBy": {
                        "type": "string",
                        "enum": ["name", "modifiedAt", "createdAt"],
                        "description": "Sort field",
                        "default": "modifiedAt",
                    },
                    "sortOrder": {
                        "type": "string",
                        "enum": ["asc", "desc"],
                        "description": "Sort order",
                        "default": "desc",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of documents to return",
                        "default": 20,
                    },
                },
            },
        ),
        Tool(
            name="search_documents",
            description="Search for documents by name or description",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string"},
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results",
                        "default": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_document",
            description="Get detailed information about a specific document",
            inputSchema={
                "type": "object",
                "properties": {"documentId": {"type": "string", "description": "Document ID"}},
                "required": ["documentId"],
            },
        ),
        Tool(
            name="get_document_summary",
            description="Get a comprehensive summary of a document including all workspaces and elements",
            inputSchema={
                "type": "object",
                "properties": {"documentId": {"type": "string", "description": "Document ID"}},
                "required": ["documentId"],
            },
        ),
        Tool(
            name="find_part_studios",
            description=(
                "Find Part Studio elements in a specific workspace, " "optionally filtered by name"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "namePattern": {
                        "type": "string",
                        "description": ("Optional name pattern to filter by (case-insensitive)"),
                    },
                },
                "required": ["documentId", "workspaceId"],
            },
        ),
        Tool(
            name="get_parts",
            description="Get all parts from a Part Studio element",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                },
                "required": ["documentId", "workspaceId", "elementId"],
            },
        ),
        Tool(
            name="get_elements",
            description=("Get all elements (Part Studios, Assemblies, etc.) in a workspace"),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementType": {
                        "type": "string",
                        "description": (
                            "Optional filter by element type " "(e.g., 'PARTSTUDIO', 'ASSEMBLY')"
                        ),
                    },
                },
                "required": ["documentId", "workspaceId"],
            },
        ),
        Tool(
            name="get_assembly",
            description="Get assembly structure including instances and occurrences",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                },
                "required": ["documentId", "workspaceId", "elementId"],
            },
        ),
        Tool(
            name="create_document",
            description="Create a new Onshape document",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name for the new document"},
                    "description": {
                        "type": "string",
                        "description": "Optional description for the document",
                    },
                    "isPublic": {
                        "type": "boolean",
                        "description": "Whether the document should be public",
                        "default": False,
                    },
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="create_part_studio",
            description="Create a new Part Studio in an existing document",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "name": {"type": "string", "description": "Name for the new Part Studio"},
                },
                "required": ["documentId", "workspaceId", "name"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""

    if name == "create_sketch_rectangle":
        try:
            # Get the plane name and resolve its ID
            plane_name = arguments.get("plane", "Front")
            plane = SketchPlane[plane_name.upper()]

            # Resolve the plane ID from Onshape
            plane_id = await partstudio_manager.get_plane_id(
                arguments["documentId"],
                arguments["workspaceId"],
                arguments["elementId"],
                plane_name,
            )

            # Build sketch with rectangle
            sketch = SketchBuilder(
                name=arguments.get("name", "Sketch"), plane=plane, plane_id=plane_id
            )

            sketch.add_rectangle(
                corner1=tuple(arguments["corner1"]),
                corner2=tuple(arguments["corner2"]),
                variable_width=arguments.get("variableWidth"),
                variable_height=arguments.get("variableHeight"),
            )

            # Add feature to Part Studio
            feature_data = sketch.build()
            result = await partstudio_manager.add_feature(
                arguments["documentId"],
                arguments["workspaceId"],
                arguments["elementId"],
                feature_data,
            )

            feature_id = result.get("feature", {}).get("featureId", "unknown")
            return [
                TextContent(
                    type="text",
                    text=f"Created sketch '{arguments.get('name', 'Sketch')}' with rectangle on {plane_name} plane. Feature ID: {feature_id}",
                )
            ]

        except Exception as e:
            return [
                TextContent(
                    type="text",
                    text=f"Error creating sketch: {str(e)}\n\nPlease check the document/workspace/element IDs and try again.",
                )
            ]

    elif name == "create_extrude":
        try:
            # Build extrude
            op_type = ExtrudeType[arguments.get("operationType", "NEW")]
            extrude = ExtrudeBuilder(
                name=arguments.get("name", "Extrude"),
                sketch_feature_id=arguments["sketchFeatureId"],
                operation_type=op_type,
            )

            extrude.set_depth(arguments["depth"], variable_name=arguments.get("variableDepth"))

            # Add feature to Part Studio
            feature_data = extrude.build()
            result = await partstudio_manager.add_feature(
                arguments["documentId"],
                arguments["workspaceId"],
                arguments["elementId"],
                feature_data,
            )

            return [
                TextContent(
                    type="text",
                    text=f"Created extrude '{arguments.get('name', 'Extrude')}'. Feature ID: {result.get('featureId', 'unknown')}",
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(
                f"API error creating extrude: {e.response.status_code} - {e.response.text[:500]}"
            )
            return [
                TextContent(
                    type="text",
                    text=f"Error creating extrude: API returned {e.response.status_code}. Check that the sketch feature ID is valid and parameters are correct.",
                )
            ]
        except KeyError:
            return [
                TextContent(
                    type="text",
                    text="Error creating extrude: Invalid operation type. Must be one of: NEW, ADD, REMOVE, INTERSECT.",
                )
            ]
        except ValueError as e:
            return [
                TextContent(
                    type="text",
                    text=f"Error creating extrude: {str(e)}",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error creating extrude")
            return [
                TextContent(
                    type="text",
                    text=f"Error creating extrude: {str(e)}\n\nPlease check the parameters and try again.",
                )
            ]

    elif name == "create_thicken":
        try:
            # Build thicken
            op_type = ThickenType[arguments.get("operationType", "NEW")]
            thicken = ThickenBuilder(
                name=arguments.get("name", "Thicken"),
                sketch_feature_id=arguments["sketchFeatureId"],
                operation_type=op_type,
            )

            thicken.set_thickness(
                arguments["thickness"], variable_name=arguments.get("variableThickness")
            )

            if arguments.get("midplane"):
                thicken.set_midplane(True)

            if arguments.get("oppositeDirection"):
                thicken.set_opposite_direction(True)

            # Add feature to Part Studio
            feature_data = thicken.build()
            result = await partstudio_manager.add_feature(
                arguments["documentId"],
                arguments["workspaceId"],
                arguments["elementId"],
                feature_data,
            )

            return [
                TextContent(
                    type="text",
                    text=f"Created thicken '{arguments.get('name', 'Thicken')}'. Feature ID: {result.get('featureId', 'unknown')}",
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(
                f"API error creating thicken: {e.response.status_code} - {e.response.text[:500]}"
            )
            return [
                TextContent(
                    type="text",
                    text=f"Error creating thicken: API returned {e.response.status_code}. Check that the sketch feature ID is valid and parameters are correct.",
                )
            ]
        except KeyError:
            return [
                TextContent(
                    type="text",
                    text="Error creating thicken: Invalid operation type. Must be one of: NEW, ADD, REMOVE, INTERSECT.",
                )
            ]
        except ValueError as e:
            return [
                TextContent(
                    type="text",
                    text=f"Error creating thicken: {str(e)}",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error creating thicken")
            return [
                TextContent(
                    type="text",
                    text=f"Error creating thicken: {str(e)}\n\nPlease check the parameters and try again.",
                )
            ]

    elif name == "get_variables":
        try:
            variables = await variable_manager.get_variables(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"]
            )

            var_list = "\n".join(
                [
                    f"- {var.name} = {var.expression}"
                    + (f" ({var.description})" if var.description else "")
                    for var in variables
                ]
            )

            return [
                TextContent(
                    type="text",
                    text=(
                        f"Variables in Part Studio:\n{var_list}"
                        if var_list
                        else "No variables found"
                    ),
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(
                f"API error getting variables: {e.response.status_code} - {e.response.text[:500]}"
            )
            return [
                TextContent(
                    type="text",
                    text=f"Error getting variables: API returned {e.response.status_code}. Check that the document/workspace/element IDs are valid.",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error getting variables")
            return [
                TextContent(
                    type="text",
                    text=f"Error getting variables: {str(e)}",
                )
            ]

    elif name == "set_variable":
        try:
            result = await variable_manager.set_variable(
                arguments["documentId"],
                arguments["workspaceId"],
                arguments["elementId"],
                arguments["name"],
                arguments["expression"],
                arguments.get("description"),
            )

            return [
                TextContent(
                    type="text",
                    text=f"Set variable '{arguments['name']}' = {arguments['expression']}",
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(
                f"API error setting variable: {e.response.status_code} - {e.response.text[:500]}"
            )
            return [
                TextContent(
                    type="text",
                    text=f"Error setting variable: API returned {e.response.status_code}. Check the variable expression format (e.g., '0.75 in').",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error setting variable")
            return [
                TextContent(
                    type="text",
                    text=f"Error setting variable: {str(e)}",
                )
            ]

    elif name == "get_features":
        try:
            features = await partstudio_manager.get_features(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"]
            )

            return [TextContent(type="text", text=f"Features data: {features}")]
        except httpx.HTTPStatusError as e:
            logger.error(
                f"API error getting features: {e.response.status_code} - {e.response.text[:500]}"
            )
            return [
                TextContent(
                    type="text",
                    text=f"Error getting features: API returned {e.response.status_code}. Check that the document/workspace/element IDs are valid.",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error getting features")
            return [
                TextContent(
                    type="text",
                    text=f"Error getting features: {str(e)}",
                )
            ]

    elif name == "list_documents":
        try:
            # Map filter type to API value
            filter_map = {"all": None, "owned": "1", "created": "4", "shared": "5"}
            filter_type = filter_map.get(arguments.get("filterType", "all"))

            documents = await document_manager.list_documents(
                filter_type=filter_type,
                sort_by=arguments.get("sortBy", "modifiedAt"),
                sort_order=arguments.get("sortOrder", "desc"),
                limit=arguments.get("limit", 20),
            )

            if not documents:
                return [TextContent(type="text", text="No documents found")]

            doc_list = "\n\n".join(
                [
                    f"**{doc.name}**\n"
                    f"  ID: {doc.id}\n"
                    f"  Modified: {doc.modified_at}\n"
                    f"  Owner: {doc.owner_name or doc.owner_id}"
                    + (f"\n  Description: {doc.description}" if doc.description else "")
                    for doc in documents
                ]
            )

            return [
                TextContent(type="text", text=f"Found {len(documents)} document(s):\n\n{doc_list}")
            ]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error listing documents: {e.response.status_code}")
            return [
                TextContent(
                    type="text",
                    text=f"Error listing documents: API returned {e.response.status_code}. Please check your API credentials.",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error listing documents")
            return [
                TextContent(
                    type="text",
                    text=f"Error listing documents: {str(e)}",
                )
            ]

    elif name == "search_documents":
        try:
            documents = await document_manager.search_documents(
                query=arguments["query"], limit=arguments.get("limit", 20)
            )

            if not documents:
                return [
                    TextContent(
                        type="text", text=f"No documents found matching '{arguments['query']}'"
                    )
                ]

            doc_list = "\n\n".join(
                [
                    f"**{doc.name}**\n" f"  ID: {doc.id}\n" f"  Modified: {doc.modified_at}"
                    for doc in documents
                ]
            )

            return [
                TextContent(
                    type="text",
                    text=f"Found {len(documents)} document(s) matching '{arguments['query']}':\n\n{doc_list}",
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error searching documents: {e.response.status_code}")
            return [
                TextContent(
                    type="text",
                    text=f"Error searching documents: API returned {e.response.status_code}.",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error searching documents")
            return [
                TextContent(
                    type="text",
                    text=f"Error searching documents: {str(e)}",
                )
            ]

    elif name == "get_document":
        try:
            doc = await document_manager.get_document(arguments["documentId"])

            return [
                TextContent(
                    type="text",
                    text=f"**{doc.name}**\n"
                    f"ID: {doc.id}\n"
                    f"Created: {doc.created_at}\n"
                    f"Modified: {doc.modified_at}\n"
                    f"Owner: {doc.owner_name or doc.owner_id}\n"
                    f"Public: {doc.public}"
                    + (f"\nDescription: {doc.description}" if doc.description else ""),
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error getting document: {e.response.status_code}")
            return [
                TextContent(
                    type="text",
                    text=f"Error getting document: API returned {e.response.status_code}. Check that the document ID is valid.",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error getting document")
            return [
                TextContent(
                    type="text",
                    text=f"Error getting document: {str(e)}",
                )
            ]

    elif name == "get_document_summary":
        try:
            summary = await document_manager.get_document_summary(arguments["documentId"])

            doc = summary["document"]
            workspaces = summary["workspaces"]

            # Build summary text
            text_parts = [
                f"**{doc.name}**",
                f"ID: {doc.id}",
                f"Modified: {doc.modified_at}",
                "",
                f"Workspaces: {len(workspaces)}",
            ]

            for ws_detail in summary["workspace_details"]:
                ws = ws_detail["workspace"]
                elements = ws_detail["elements"]

                text_parts.append(f"\n**Workspace: {ws.name}**")
                text_parts.append(f"  ID: {ws.id}")
                text_parts.append(f"  Elements: {len(elements)}")

                if elements:
                    text_parts.append("  Element types:")
                    elem_types = {}
                    for elem in elements:
                        elem_types[elem.element_type] = elem_types.get(elem.element_type, 0) + 1

                    for elem_type, count in elem_types.items():
                        text_parts.append(f"    - {elem_type}: {count}")

            return [TextContent(type="text", text="\n".join(text_parts))]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error getting document summary: {e.response.status_code}")
            return [
                TextContent(
                    type="text",
                    text=f"Error getting document summary: API returned {e.response.status_code}. Check that the document ID is valid.",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error getting document summary")
            return [
                TextContent(
                    type="text",
                    text=f"Error getting document summary: {str(e)}",
                )
            ]

    elif name == "find_part_studios":
        try:
            part_studios = await document_manager.find_part_studios(
                arguments["documentId"],
                arguments["workspaceId"],
                name_pattern=arguments.get("namePattern"),
            )

            if not part_studios:
                pattern_msg = (
                    f" matching '{arguments['namePattern']}'"
                    if arguments.get("namePattern")
                    else ""
                )
                return [TextContent(type="text", text=f"No Part Studios found{pattern_msg}")]

            ps_list = "\n".join([f"- **{ps.name}** (ID: {ps.id})" for ps in part_studios])

            pattern_msg = (
                f" matching '{arguments['namePattern']}'" if arguments.get("namePattern") else ""
            )
            return [
                TextContent(
                    type="text",
                    text=f"Found {len(part_studios)} Part Studio(s){pattern_msg}:\n\n{ps_list}",
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error finding part studios: {e.response.status_code}")
            return [
                TextContent(
                    type="text",
                    text=f"Error finding part studios: API returned {e.response.status_code}. Check that the document/workspace IDs are valid.",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error finding part studios")
            return [
                TextContent(
                    type="text",
                    text=f"Error finding part studios: {str(e)}",
                )
            ]

    elif name == "get_parts":
        try:
            parts = await partstudio_manager.get_parts(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"]
            )

            if not parts:
                return [TextContent(type="text", text="No parts found in Part Studio")]

            parts_list = []
            for i, part in enumerate(parts, 1):
                part_info = f"**Part {i}: {part.get('name', 'Unnamed')}**"
                if "partId" in part:
                    part_info += f"\n  Part ID: {part['partId']}"
                if "bodyType" in part:
                    part_info += f"\n  Body Type: {part['bodyType']}"
                if "state" in part:
                    part_info += f"\n  State: {part['state']}"
                parts_list.append(part_info)

            return [
                TextContent(
                    type="text", text=f"Found {len(parts)} part(s):\n\n" + "\n\n".join(parts_list)
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error getting parts: {e.response.status_code}")
            return [
                TextContent(
                    type="text",
                    text=f"Error getting parts: API returned {e.response.status_code}. Check that the document/workspace/element IDs are valid.",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error getting parts")
            return [
                TextContent(
                    type="text",
                    text=f"Error getting parts: {str(e)}",
                )
            ]

    elif name == "get_elements":
        try:
            elements = await document_manager.get_elements(
                arguments["documentId"],
                arguments["workspaceId"],
                element_type=arguments.get("elementType"),
            )

            if not elements:
                type_msg = (
                    f" of type '{arguments['elementType']}'" if arguments.get("elementType") else ""
                )
                return [TextContent(type="text", text=f"No elements found{type_msg}")]

            elem_list = []
            for elem in elements:
                elem_info = f"**{elem.name}**"
                elem_info += f"\n  ID: {elem.id}"
                elem_info += f"\n  Type: {elem.element_type}"
                if elem.data_type:
                    elem_info += f"\n  Data Type: {elem.data_type}"
                elem_list.append(elem_info)

            type_msg = (
                f" of type '{arguments['elementType']}'" if arguments.get("elementType") else ""
            )
            return [
                TextContent(
                    type="text",
                    text=f"Found {len(elements)} element(s){type_msg}:\n\n"
                    + "\n\n".join(elem_list),
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error getting elements: {e.response.status_code}")
            return [
                TextContent(
                    type="text",
                    text=f"Error getting elements: API returned {e.response.status_code}. Check that the document/workspace IDs are valid.",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error getting elements")
            return [
                TextContent(
                    type="text",
                    text=f"Error getting elements: {str(e)}",
                )
            ]

    elif name == "get_assembly":
        try:
            assembly_path = (
                f"/api/v6/assemblies/d/{arguments['documentId']}"
                f"/w/{arguments['workspaceId']}/e/{arguments['elementId']}"
            )
            assembly_data = await client.get(assembly_path)

            root_assembly = assembly_data.get("rootAssembly", {})
            instances = root_assembly.get("instances", [])

            if not instances:
                return [TextContent(type="text", text="No instances found in assembly")]

            instance_list = []
            for i, instance in enumerate(instances, 1):
                inst_info = f"**Instance {i}: {instance.get('name', 'Unnamed')}**"
                inst_info += f"\n  ID: {instance.get('id', 'N/A')}"
                inst_info += f"\n  Type: {instance.get('type', 'N/A')}"
                if "partId" in instance:
                    inst_info += f"\n  Part ID: {instance['partId']}"
                if "suppressed" in instance:
                    inst_info += f"\n  Suppressed: {instance['suppressed']}"
                instance_list.append(inst_info)

            return [
                TextContent(
                    type="text",
                    text=(
                        f"Assembly Structure:\n\n"
                        f"Found {len(instances)} instance(s):\n\n" + "\n\n".join(instance_list)
                    ),
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error getting assembly: {e.response.status_code}")
            return [
                TextContent(
                    type="text",
                    text=f"Error getting assembly: API returned {e.response.status_code}. Check that the document/workspace/element IDs are valid.",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error getting assembly")
            return [
                TextContent(
                    type="text",
                    text=f"Error getting assembly: {str(e)}",
                )
            ]

    elif name == "create_document":
        try:
            doc = await document_manager.create_document(
                name=arguments["name"],
                description=arguments.get("description"),
                is_public=arguments.get("isPublic", False),
            )

            return [
                TextContent(
                    type="text",
                    text=f"Created document '{doc.name}'\n"
                    f"Document ID: {doc.id}\n"
                    f"Use this ID with other commands to work with this document.",
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error creating document: {e.response.status_code}")
            return [
                TextContent(
                    type="text",
                    text=f"Error creating document: API returned {e.response.status_code}. Check your API credentials and permissions.",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error creating document")
            return [
                TextContent(
                    type="text",
                    text=f"Error creating document: {str(e)}",
                )
            ]

    elif name == "create_part_studio":
        try:
            result = await partstudio_manager.create_part_studio(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                name=arguments["name"],
            )

            element_id = result.get("id", "unknown")
            return [
                TextContent(
                    type="text",
                    text=f"Created Part Studio '{arguments['name']}'\n"
                    f"Element ID: {element_id}\n"
                    f"Use this ID with sketch and feature commands.",
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error creating Part Studio: {e.response.status_code}")
            return [
                TextContent(
                    type="text",
                    text=f"Error creating Part Studio: API returned {e.response.status_code}. Check the document/workspace IDs.",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error creating Part Studio")
            return [
                TextContent(
                    type="text",
                    text=f"Error creating Part Studio: {str(e)}",
                )
            ]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main_stdio():
    """Run the MCP server with stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def create_sse_app():
    """Create SSE ASGI application."""
    from mcp.server.sse import SseServerTransport

    sse = SseServerTransport("/messages")

    async def app_logic(scope, receive, send):
        """Main ASGI app logic."""
        if scope["type"] == "http":
            path = scope["path"]

            if path == "/sse":
                # Handle SSE endpoint
                async with sse.connect_sse(scope, receive, send) as streams:
                    await app.run(streams[0], streams[1], app.create_initialization_options())
            elif path == "/messages" and scope["method"] == "POST":
                # Handle POST messages endpoint
                await sse.handle_post_message(scope, receive, send)
            else:
                # 404 for other paths
                await send(
                    {
                        "type": "http.response.start",
                        "status": 404,
                        "headers": [[b"content-type", b"text/plain"]],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"Not Found",
                    }
                )

    return app_logic


# Create module-level SSE app for uvicorn reload
sse_app = create_sse_app()


def main():
    """Main entry point - run stdio by default."""
    # Check if we should run in SSE mode
    if "--sse" in sys.argv or os.getenv("MCP_TRANSPORT") == "sse":
        import uvicorn

        # Get port from args or env
        port = 3000
        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
        port = int(os.getenv("MCP_PORT", port))

        # Check if reload is requested
        reload = "--reload" in sys.argv or os.getenv("MCP_RELOAD") == "true"

        print(f"Starting Onshape MCP server in SSE mode on port {port}", file=sys.stderr)
        if reload:
            print("Auto-reload enabled - server will restart on code changes", file=sys.stderr)
            # When using reload, we need to pass the module path string
            # and uvicorn will import and re-import on changes
            uvicorn.run(
                "onshape_mcp.server:sse_app",
                host="127.0.0.1",
                port=port,
                reload=True,
                reload_dirs=["./onshape_mcp"],
            )
        else:
            # Without reload, pass the app instance directly
            uvicorn.run(sse_app, host="127.0.0.1", port=port)
    else:
        # Default to stdio
        asyncio.run(main_stdio())


if __name__ == "__main__":
    main()
