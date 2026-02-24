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

# Load environment variables from .env file before local imports read them.
# Look for .env in the package directory (where this server.py lives).
_package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_package_dir, ".env"))

from .api.client import OnshapeClient, OnshapeCredentials
from .api.partstudio import PartStudioManager
from .api.variables import VariableManager
from .api.documents import DocumentManager
from .builders.sketch import SketchBuilder, SketchPlane
from .builders.extrude import ExtrudeBuilder, ExtrudeType
from .builders.thicken import ThickenBuilder, ThickenType
from .api.assemblies import AssemblyManager
from .api.featurescript import FeatureScriptManager
from .api.export import ExportManager
from .builders.mate import MateBuilder, MateConnectorBuilder, MateType, build_transform_matrix
from .builders.fillet import FilletBuilder
from .builders.chamfer import ChamferBuilder, ChamferType
from .builders.revolve import RevolveBuilder, RevolveType
from .builders.pattern import LinearPatternBuilder, CircularPatternBuilder
from .builders.boolean import BooleanBuilder, BooleanType
from .analysis.interference import check_assembly_interference, format_interference_result
from .analysis.positioning import get_assembly_positions, set_absolute_position, align_to_face

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
_ak = os.getenv("ONSHAPE_ACCESS_KEY", "")
_sk = os.getenv("ONSHAPE_SECRET_KEY", "")
credentials = OnshapeCredentials(access_key=_ak, secret_key=_sk)
client = OnshapeClient(credentials)
partstudio_manager = PartStudioManager(client)
variable_manager = VariableManager(client)
document_manager = DocumentManager(client)
assembly_manager = AssemblyManager(client)
featurescript_manager = FeatureScriptManager(client)
export_manager = ExportManager(client)


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
            name="delete_feature",
            description="Delete a feature from a Part Studio",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "featureId": {"type": "string", "description": "Feature ID to delete"},
                },
                "required": ["documentId", "workspaceId", "elementId", "featureId"],
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
        # === Assembly Tools ===
        Tool(
            name="create_assembly",
            description="Create a new Assembly in an existing document",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "name": {"type": "string", "description": "Name for the new Assembly"},
                },
                "required": ["documentId", "workspaceId", "name"],
            },
        ),
        Tool(
            name="add_assembly_instance",
            description="Add a part or sub-assembly instance to an assembly",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "partStudioElementId": {
                        "type": "string",
                        "description": "Element ID of the Part Studio or Assembly to instance",
                    },
                    "partId": {
                        "type": "string",
                        "description": "Optional specific part ID. If omitted, instances entire Part Studio.",
                    },
                    "isAssembly": {
                        "type": "boolean",
                        "description": "Whether to instance an assembly (vs a part studio)",
                        "default": False,
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "partStudioElementId"],
            },
        ),
        Tool(
            name="transform_instance",
            description="Position/rotate an assembly instance using translation (inches) and rotation (degrees)",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "instanceId": {"type": "string", "description": "Instance ID to transform"},
                    "translateX": {"type": "number", "description": "X translation in inches", "default": 0},
                    "translateY": {"type": "number", "description": "Y translation in inches", "default": 0},
                    "translateZ": {"type": "number", "description": "Z translation in inches", "default": 0},
                    "rotateX": {"type": "number", "description": "X rotation in degrees", "default": 0},
                    "rotateY": {"type": "number", "description": "Y rotation in degrees", "default": 0},
                    "rotateZ": {"type": "number", "description": "Z rotation in degrees", "default": 0},
                },
                "required": ["documentId", "workspaceId", "elementId", "instanceId"],
            },
        ),
        Tool(
            name="create_fastened_mate",
            description="Create a fastened (rigid) mate between two assembly instances",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "name": {"type": "string", "description": "Mate name", "default": "Fastened mate"},
                    "firstInstanceId": {"type": "string", "description": "First instance ID"},
                    "secondInstanceId": {"type": "string", "description": "Second instance ID"},
                },
                "required": ["documentId", "workspaceId", "elementId", "firstInstanceId", "secondInstanceId"],
            },
        ),
        Tool(
            name="create_revolute_mate",
            description="Create a revolute (rotation) mate between two assembly instances",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "name": {"type": "string", "description": "Mate name", "default": "Revolute mate"},
                    "firstInstanceId": {"type": "string", "description": "First instance ID"},
                    "secondInstanceId": {"type": "string", "description": "Second instance ID"},
                    "minLimit": {"type": "number", "description": "Optional minimum rotation limit in degrees"},
                    "maxLimit": {"type": "number", "description": "Optional maximum rotation limit in degrees"},
                },
                "required": ["documentId", "workspaceId", "elementId", "firstInstanceId", "secondInstanceId"],
            },
        ),
        Tool(
            name="create_slider_mate",
            description="Create a slider (linear motion) mate between two assembly instances. The slide direction follows the mate connector's Z-axis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "name": {"type": "string", "description": "Mate name", "default": "Slider mate"},
                    "firstInstanceId": {"type": "string", "description": "First instance ID"},
                    "secondInstanceId": {"type": "string", "description": "Second instance ID"},
                    "minLimit": {"type": "number", "description": "Optional minimum travel limit in inches"},
                    "maxLimit": {"type": "number", "description": "Optional maximum travel limit in inches"},
                },
                "required": ["documentId", "workspaceId", "elementId", "firstInstanceId", "secondInstanceId"],
            },
        ),
        Tool(
            name="create_cylindrical_mate",
            description="Create a cylindrical (slide + rotate) mate between two assembly instances",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "name": {"type": "string", "description": "Mate name", "default": "Cylindrical mate"},
                    "firstInstanceId": {"type": "string", "description": "First instance ID"},
                    "secondInstanceId": {"type": "string", "description": "Second instance ID"},
                    "minLimit": {"type": "number", "description": "Optional minimum axial travel limit in inches"},
                    "maxLimit": {"type": "number", "description": "Optional maximum axial travel limit in inches"},
                },
                "required": ["documentId", "workspaceId", "elementId", "firstInstanceId", "secondInstanceId"],
            },
        ),
        Tool(
            name="create_mate_connector",
            description="Create an explicit mate connector on an assembly instance with optional axis orientation. Use this to control the slide direction for slider mates.",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "instanceId": {"type": "string", "description": "Instance ID to attach the connector to"},
                    "name": {"type": "string", "description": "Mate connector name", "default": "Mate connector"},
                    "originX": {"type": "number", "description": "X origin offset in inches", "default": 0},
                    "originY": {"type": "number", "description": "Y origin offset in inches", "default": 0},
                    "originZ": {"type": "number", "description": "Z origin offset in inches", "default": 0},
                    "axis": {
                        "type": "string",
                        "enum": ["X", "Y", "Z"],
                        "description": "Primary axis direction. The connector's Z-axis aligns with this world axis. Controls slide direction for slider mates.",
                        "default": "Z",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "instanceId"],
            },
        ),
        # === Sketch Tools ===
        Tool(
            name="create_sketch_circle",
            description="Create a circular sketch on a standard plane",
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
                    "centerX": {"type": "number", "description": "Center X in inches", "default": 0},
                    "centerY": {"type": "number", "description": "Center Y in inches", "default": 0},
                    "radius": {"type": "number", "description": "Radius in inches"},
                },
                "required": ["documentId", "workspaceId", "elementId", "radius"],
            },
        ),
        Tool(
            name="create_sketch_line",
            description="Create a line sketch on a standard plane",
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
                    "startPoint": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "Start point [x, y] in inches",
                    },
                    "endPoint": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "End point [x, y] in inches",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "startPoint", "endPoint"],
            },
        ),
        Tool(
            name="create_sketch_arc",
            description="Create an arc sketch on a standard plane",
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
                    "centerX": {"type": "number", "description": "Center X in inches", "default": 0},
                    "centerY": {"type": "number", "description": "Center Y in inches", "default": 0},
                    "radius": {"type": "number", "description": "Radius in inches"},
                    "startAngle": {
                        "type": "number",
                        "description": "Start angle in degrees (0 = positive X)",
                        "default": 0,
                    },
                    "endAngle": {
                        "type": "number",
                        "description": "End angle in degrees",
                        "default": 180,
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "radius"],
            },
        ),
        # === Feature Tools ===
        Tool(
            name="create_fillet",
            description="Create a fillet (rounded edge) on one or more edges",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "name": {"type": "string", "description": "Fillet name", "default": "Fillet"},
                    "radius": {"type": "number", "description": "Fillet radius in inches"},
                    "edgeIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Deterministic IDs of edges to fillet",
                    },
                    "variableRadius": {"type": "string", "description": "Optional variable name for radius"},
                },
                "required": ["documentId", "workspaceId", "elementId", "radius", "edgeIds"],
            },
        ),
        Tool(
            name="create_chamfer",
            description="Create a chamfer (beveled edge) on one or more edges",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "name": {"type": "string", "description": "Chamfer name", "default": "Chamfer"},
                    "distance": {"type": "number", "description": "Chamfer distance in inches"},
                    "edgeIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Deterministic IDs of edges to chamfer",
                    },
                    "variableDistance": {"type": "string", "description": "Optional variable name for distance"},
                },
                "required": ["documentId", "workspaceId", "elementId", "distance", "edgeIds"],
            },
        ),
        Tool(
            name="create_revolve",
            description="Create a revolve feature by rotating a sketch around an axis",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "name": {"type": "string", "description": "Revolve name", "default": "Revolve"},
                    "sketchFeatureId": {"type": "string", "description": "ID of sketch to revolve"},
                    "axis": {
                        "type": "string",
                        "enum": ["X", "Y", "Z"],
                        "description": "Axis of revolution",
                        "default": "Y",
                    },
                    "angle": {"type": "number", "description": "Revolve angle in degrees", "default": 360},
                    "operationType": {
                        "type": "string",
                        "enum": ["NEW", "ADD", "REMOVE", "INTERSECT"],
                        "description": "Revolve operation type",
                        "default": "NEW",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "sketchFeatureId"],
            },
        ),
        Tool(
            name="create_linear_pattern",
            description="Create a linear pattern of features",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "name": {"type": "string", "description": "Pattern name", "default": "Linear pattern"},
                    "featureIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Feature IDs to pattern",
                    },
                    "distance": {"type": "number", "description": "Distance between instances in inches"},
                    "count": {"type": "integer", "description": "Total number of instances", "default": 2},
                    "direction": {
                        "type": "string",
                        "enum": ["X", "Y", "Z"],
                        "description": "Pattern direction axis",
                        "default": "X",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "featureIds", "distance"],
            },
        ),
        Tool(
            name="create_circular_pattern",
            description="Create a circular pattern of features around an axis",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "name": {"type": "string", "description": "Pattern name", "default": "Circular pattern"},
                    "featureIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Feature IDs to pattern",
                    },
                    "count": {"type": "integer", "description": "Total number of instances"},
                    "angle": {"type": "number", "description": "Total angle spread in degrees", "default": 360},
                    "axis": {
                        "type": "string",
                        "enum": ["X", "Y", "Z"],
                        "description": "Pattern axis",
                        "default": "Z",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "featureIds", "count"],
            },
        ),
        Tool(
            name="create_boolean",
            description="Perform a boolean operation (union, subtract, intersect) on bodies",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "name": {"type": "string", "description": "Boolean name", "default": "Boolean"},
                    "booleanType": {
                        "type": "string",
                        "enum": ["UNION", "SUBTRACT", "INTERSECT"],
                        "description": "Boolean operation type",
                    },
                    "toolBodyIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Deterministic IDs of tool bodies",
                    },
                    "targetBodyIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Deterministic IDs of target bodies (for SUBTRACT/INTERSECT)",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "booleanType", "toolBodyIds"],
            },
        ),
        # === FeatureScript Tools ===
        Tool(
            name="eval_featurescript",
            description="Evaluate a FeatureScript expression in a Part Studio (read-only, for querying geometry)",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "script": {"type": "string", "description": "FeatureScript lambda expression to evaluate"},
                },
                "required": ["documentId", "workspaceId", "elementId", "script"],
            },
        ),
        Tool(
            name="get_bounding_box",
            description="Get the tight bounding box of all parts in a Part Studio",
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
        # === Export Tools ===
        Tool(
            name="export_part_studio",
            description="Export a Part Studio to STL, STEP, or other format",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "format": {
                        "type": "string",
                        "enum": ["STL", "STEP", "PARASOLID", "GLTF", "OBJ"],
                        "description": "Export format",
                        "default": "STL",
                    },
                    "partId": {"type": "string", "description": "Optional specific part ID to export"},
                },
                "required": ["documentId", "workspaceId", "elementId"],
            },
        ),
        Tool(
            name="export_assembly",
            description="Export an Assembly to STL, STEP, or other format",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "format": {
                        "type": "string",
                        "enum": ["STL", "STEP", "GLTF"],
                        "description": "Export format",
                        "default": "STL",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId"],
            },
        ),
        Tool(
            name="check_assembly_interference",
            description="Check for overlapping/interfering parts in an assembly using bounding box detection. Returns which parts overlap and by how much.",
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
            name="get_assembly_positions",
            description="Get positions, sizes, and world-space bounds of all instances in an assembly (in inches)",
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
            name="set_instance_position",
            description="Set an instance to an ABSOLUTE position in inches (unlike transform_instance which is relative). Resets rotation to identity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "instanceId": {"type": "string", "description": "Instance ID to position"},
                    "x": {"type": "number", "description": "Absolute X position in inches"},
                    "y": {"type": "number", "description": "Absolute Y position in inches"},
                    "z": {"type": "number", "description": "Absolute Z position in inches"},
                },
                "required": ["documentId", "workspaceId", "elementId", "instanceId", "x", "y", "z"],
            },
        ),
        Tool(
            name="align_instance_to_face",
            description="Position source instance flush against a face of target instance. Faces: front (min Y), back (max Y), left (min X), right (max X), bottom (min Z), top (max Z). Only moves the perpendicular axis; other axes stay unchanged.",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "sourceInstanceId": {"type": "string", "description": "Instance ID to move"},
                    "targetInstanceId": {"type": "string", "description": "Instance ID to align against"},
                    "face": {
                        "type": "string",
                        "enum": ["front", "back", "left", "right", "top", "bottom"],
                        "description": "Face of target to align source against",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "sourceInstanceId", "targetInstanceId", "face"],
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

    elif name == "delete_feature":
        try:
            result = await partstudio_manager.delete_feature(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"], arguments["featureId"],
            )
            return [TextContent(type="text", text=f"Deleted feature {arguments['featureId']}")]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error deleting feature: API returned {e.response.status_code}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error deleting feature: {str(e)}")]

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
            assembly_data = await assembly_manager.get_assembly_definition(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
            )

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

    elif name == "create_assembly":
        try:
            result = await assembly_manager.create_assembly(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                name=arguments["name"],
            )
            element_id = result.get("id", "unknown")
            return [
                TextContent(
                    type="text",
                    text=f"Created Assembly '{arguments['name']}'\nElement ID: {element_id}",
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error creating assembly: {e.response.status_code}")
            return [TextContent(type="text", text=f"Error creating assembly: API returned {e.response.status_code}.")]
        except Exception as e:
            logger.exception("Unexpected error creating assembly")
            return [TextContent(type="text", text=f"Error creating assembly: {str(e)}")]

    elif name == "add_assembly_instance":
        try:
            result = await assembly_manager.add_instance(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                part_studio_element_id=arguments["partStudioElementId"],
                part_id=arguments.get("partId"),
                is_assembly=arguments.get("isAssembly", False),
            )
            instance_id = result.get("id", "unknown")
            instance_name = result.get("name", "unnamed")
            return [
                TextContent(
                    type="text",
                    text=f"Added instance '{instance_name}' to assembly.\nInstance ID: {instance_id}",
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error adding instance: {e.response.status_code}")
            return [TextContent(type="text", text=f"Error adding instance: API returned {e.response.status_code}.")]
        except Exception as e:
            logger.exception("Unexpected error adding instance")
            return [TextContent(type="text", text=f"Error adding instance: {str(e)}")]

    elif name == "transform_instance":
        try:
            transform = build_transform_matrix(
                tx=arguments.get("translateX", 0),
                ty=arguments.get("translateY", 0),
                tz=arguments.get("translateZ", 0),
                rx=arguments.get("rotateX", 0),
                ry=arguments.get("rotateY", 0),
                rz=arguments.get("rotateZ", 0),
            )
            occurrences = [{"path": [arguments["instanceId"]], "transform": transform}]
            await assembly_manager.transform_occurrences(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                occurrences=occurrences,
            )
            return [TextContent(type="text", text=f"Transformed instance {arguments['instanceId']}.")]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error transforming instance: {e.response.status_code}")
            return [TextContent(type="text", text=f"Error transforming instance: API returned {e.response.status_code}.")]
        except Exception as e:
            logger.exception("Unexpected error transforming instance")
            return [TextContent(type="text", text=f"Error transforming instance: {str(e)}")]

    elif name == "create_fastened_mate":
        try:
            mate = MateBuilder(name=arguments.get("name", "Fastened mate"), mate_type=MateType.FASTENED)
            mate.set_first_occurrence([arguments["firstInstanceId"]])
            mate.set_second_occurrence([arguments["secondInstanceId"]])
            result = await assembly_manager.add_feature(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                feature_data=mate.build(),
            )
            feature_id = result.get("feature", {}).get("featureId", "unknown")
            return [TextContent(type="text", text=f"Created fastened mate '{arguments.get('name', 'Fastened mate')}'. Feature ID: {feature_id}")]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error creating mate: {e.response.status_code}")
            return [TextContent(type="text", text=f"Error creating mate: API returned {e.response.status_code}.")]
        except Exception as e:
            logger.exception("Unexpected error creating mate")
            return [TextContent(type="text", text=f"Error creating mate: {str(e)}")]

    elif name == "create_revolute_mate":
        try:
            mate = MateBuilder(name=arguments.get("name", "Revolute mate"), mate_type=MateType.REVOLUTE)
            mate.set_first_occurrence([arguments["firstInstanceId"]])
            mate.set_second_occurrence([arguments["secondInstanceId"]])
            if "minLimit" in arguments and "maxLimit" in arguments:
                mate.set_limits(arguments["minLimit"], arguments["maxLimit"])
            result = await assembly_manager.add_feature(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                feature_data=mate.build(),
            )
            feature_id = result.get("feature", {}).get("featureId", "unknown")
            return [TextContent(type="text", text=f"Created revolute mate '{arguments.get('name', 'Revolute mate')}'. Feature ID: {feature_id}")]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error creating mate: {e.response.status_code}")
            return [TextContent(type="text", text=f"Error creating mate: API returned {e.response.status_code}.")]
        except Exception as e:
            logger.exception("Unexpected error creating mate")
            return [TextContent(type="text", text=f"Error creating mate: {str(e)}")]

    elif name == "create_slider_mate":
        try:
            mate = MateBuilder(name=arguments.get("name", "Slider mate"), mate_type=MateType.SLIDER)
            mate.set_first_occurrence([arguments["firstInstanceId"]])
            mate.set_second_occurrence([arguments["secondInstanceId"]])
            if "minLimit" in arguments and "maxLimit" in arguments:
                mate.set_limits(arguments["minLimit"], arguments["maxLimit"])
            result = await assembly_manager.add_feature(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                feature_data=mate.build(),
            )
            feature_id = result.get("feature", {}).get("featureId", "unknown")
            return [TextContent(type="text", text=f"Created slider mate '{arguments.get('name', 'Slider mate')}'. Feature ID: {feature_id}")]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error creating mate: {e.response.status_code}")
            return [TextContent(type="text", text=f"Error creating mate: API returned {e.response.status_code}.")]
        except Exception as e:
            logger.exception("Unexpected error creating mate")
            return [TextContent(type="text", text=f"Error creating mate: {str(e)}")]

    elif name == "create_cylindrical_mate":
        try:
            mate = MateBuilder(name=arguments.get("name", "Cylindrical mate"), mate_type=MateType.CYLINDRICAL)
            mate.set_first_occurrence([arguments["firstInstanceId"]])
            mate.set_second_occurrence([arguments["secondInstanceId"]])
            if "minLimit" in arguments and "maxLimit" in arguments:
                mate.set_limits(arguments["minLimit"], arguments["maxLimit"])
            result = await assembly_manager.add_feature(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                feature_data=mate.build(),
            )
            feature_id = result.get("feature", {}).get("featureId", "unknown")
            return [TextContent(type="text", text=f"Created cylindrical mate '{arguments.get('name', 'Cylindrical mate')}'. Feature ID: {feature_id}")]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error creating mate: {e.response.status_code}")
            return [TextContent(type="text", text=f"Error creating mate: API returned {e.response.status_code}.")]
        except Exception as e:
            logger.exception("Unexpected error creating mate")
            return [TextContent(type="text", text=f"Error creating mate: {str(e)}")]

    elif name == "create_mate_connector":
        try:
            mc = MateConnectorBuilder(
                name=arguments.get("name", "Mate connector"),
                origin_x=arguments.get("originX", 0),
                origin_y=arguments.get("originY", 0),
                origin_z=arguments.get("originZ", 0),
                axis=arguments.get("axis", "Z"),
            )
            mc.set_occurrence([arguments["instanceId"]])
            result = await assembly_manager.add_feature(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                feature_data=mc.build(),
            )
            feature_id = result.get("feature", {}).get("featureId", "unknown")
            return [TextContent(type="text", text=f"Created mate connector '{arguments.get('name', 'Mate connector')}' on instance {arguments['instanceId']}. Feature ID: {feature_id}")]
        except ValueError as e:
            return [TextContent(type="text", text=f"Invalid input: {str(e)}")]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error creating mate connector: {e.response.status_code}")
            return [TextContent(type="text", text=f"Error creating mate connector: API returned {e.response.status_code}.")]
        except Exception as e:
            logger.exception("Unexpected error creating mate connector")
            return [TextContent(type="text", text=f"Error creating mate connector: {str(e)}")]

    elif name == "create_sketch_circle":
        try:
            plane_name = arguments.get("plane", "Front")
            plane = SketchPlane[plane_name.upper()]
            plane_id = await partstudio_manager.get_plane_id(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"], plane_name,
            )
            sketch = SketchBuilder(name=arguments.get("name", "Sketch"), plane=plane, plane_id=plane_id)
            sketch.add_circle(
                center=(arguments.get("centerX", 0), arguments.get("centerY", 0)),
                radius=arguments["radius"],
            )
            feature_data = sketch.build()
            result = await partstudio_manager.add_feature(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"], feature_data,
            )
            feature_id = result.get("feature", {}).get("featureId", "unknown")
            return [TextContent(type="text", text=f"Created sketch with circle on {plane_name} plane. Feature ID: {feature_id}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error creating sketch circle: {str(e)}")]

    elif name == "create_sketch_line":
        try:
            plane_name = arguments.get("plane", "Front")
            plane = SketchPlane[plane_name.upper()]
            plane_id = await partstudio_manager.get_plane_id(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"], plane_name,
            )
            sketch = SketchBuilder(name=arguments.get("name", "Sketch"), plane=plane, plane_id=plane_id)
            sketch.add_line(
                start=tuple(arguments["startPoint"]),
                end=tuple(arguments["endPoint"]),
            )
            feature_data = sketch.build()
            result = await partstudio_manager.add_feature(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"], feature_data,
            )
            feature_id = result.get("feature", {}).get("featureId", "unknown")
            return [TextContent(type="text", text=f"Created sketch with line on {plane_name} plane. Feature ID: {feature_id}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error creating sketch line: {str(e)}")]

    elif name == "create_sketch_arc":
        try:
            plane_name = arguments.get("plane", "Front")
            plane = SketchPlane[plane_name.upper()]
            plane_id = await partstudio_manager.get_plane_id(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"], plane_name,
            )
            sketch = SketchBuilder(name=arguments.get("name", "Sketch"), plane=plane, plane_id=plane_id)
            sketch.add_arc(
                center=(arguments.get("centerX", 0), arguments.get("centerY", 0)),
                radius=arguments["radius"],
                start_angle=arguments.get("startAngle", 0),
                end_angle=arguments.get("endAngle", 180),
            )
            feature_data = sketch.build()
            result = await partstudio_manager.add_feature(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"], feature_data,
            )
            feature_id = result.get("feature", {}).get("featureId", "unknown")
            return [TextContent(type="text", text=f"Created sketch with arc on {plane_name} plane. Feature ID: {feature_id}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error creating sketch arc: {str(e)}")]

    elif name == "create_fillet":
        try:
            fillet = FilletBuilder(name=arguments.get("name", "Fillet"), radius=arguments["radius"])
            for edge_id in arguments["edgeIds"]:
                fillet.add_edge(edge_id)
            if arguments.get("variableRadius"):
                fillet.set_radius(arguments["radius"], variable_name=arguments["variableRadius"])
            feature_data = fillet.build()
            result = await partstudio_manager.add_feature(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"], feature_data,
            )
            feature_id = result.get("feature", {}).get("featureId", result.get("featureId", "unknown"))
            return [TextContent(type="text", text=f"Created fillet. Feature ID: {feature_id}")]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error creating fillet: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error creating fillet: {str(e)}")]

    elif name == "create_chamfer":
        try:
            chamfer_type = ChamferType[arguments.get("chamferType", "EQUAL_OFFSETS")]
            chamfer = ChamferBuilder(name=arguments.get("name", "Chamfer"), distance=arguments["distance"], chamfer_type=chamfer_type)
            for edge_id in arguments["edgeIds"]:
                chamfer.add_edge(edge_id)
            if arguments.get("variableDistance"):
                chamfer.set_distance(arguments["distance"], variable_name=arguments["variableDistance"])
            feature_data = chamfer.build()
            result = await partstudio_manager.add_feature(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"], feature_data,
            )
            feature_id = result.get("feature", {}).get("featureId", result.get("featureId", "unknown"))
            return [TextContent(type="text", text=f"Created chamfer. Feature ID: {feature_id}")]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error creating chamfer: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error creating chamfer: {str(e)}")]

    elif name == "create_revolve":
        try:
            op_type = RevolveType[arguments.get("operationType", "NEW")]
            revolve = RevolveBuilder(
                name=arguments.get("name", "Revolve"),
                sketch_feature_id=arguments["sketchFeatureId"],
                axis=arguments.get("axis", "Y"),
                angle=arguments.get("angle", 360.0),
                operation_type=op_type,
            )
            feature_data = revolve.build()
            result = await partstudio_manager.add_feature(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"], feature_data,
            )
            feature_id = result.get("feature", {}).get("featureId", result.get("featureId", "unknown"))
            return [TextContent(type="text", text=f"Created revolve. Feature ID: {feature_id}")]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error creating revolve: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error creating revolve: {str(e)}")]

    elif name == "create_linear_pattern":
        try:
            pattern = LinearPatternBuilder(
                name=arguments.get("name", "Linear pattern"),
                distance=arguments["distance"],
                count=arguments.get("count", 2),
            )
            for fid in arguments["featureIds"]:
                pattern.add_feature(fid)
            pattern.set_direction(arguments.get("direction", "X"))
            feature_data = pattern.build()
            result = await partstudio_manager.add_feature(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"], feature_data,
            )
            feature_id = result.get("feature", {}).get("featureId", result.get("featureId", "unknown"))
            return [TextContent(type="text", text=f"Created linear pattern. Feature ID: {feature_id}")]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error creating pattern: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error creating pattern: {str(e)}")]

    elif name == "create_circular_pattern":
        try:
            pattern = CircularPatternBuilder(
                name=arguments.get("name", "Circular pattern"),
                count=arguments["count"],
            )
            pattern.set_angle(arguments.get("angle", 360.0))
            pattern.set_axis(arguments.get("axis", "Z"))
            for fid in arguments["featureIds"]:
                pattern.add_feature(fid)
            feature_data = pattern.build()
            result = await partstudio_manager.add_feature(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"], feature_data,
            )
            feature_id = result.get("feature", {}).get("featureId", result.get("featureId", "unknown"))
            return [TextContent(type="text", text=f"Created circular pattern. Feature ID: {feature_id}")]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error creating pattern: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error creating pattern: {str(e)}")]

    elif name == "create_boolean":
        try:
            bool_type = BooleanType[arguments["booleanType"]]
            boolean = BooleanBuilder(name=arguments.get("name", "Boolean"), boolean_type=bool_type)
            for body_id in arguments["toolBodyIds"]:
                boolean.add_tool_body(body_id)
            for body_id in arguments.get("targetBodyIds", []):
                boolean.add_target_body(body_id)
            feature_data = boolean.build()
            result = await partstudio_manager.add_feature(
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"], feature_data,
            )
            feature_id = result.get("feature", {}).get("featureId", result.get("featureId", "unknown"))
            return [TextContent(type="text", text=f"Created boolean {arguments['booleanType'].lower()}. Feature ID: {feature_id}")]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error creating boolean: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error creating boolean: {str(e)}")]

    elif name == "eval_featurescript":
        try:
            result = await featurescript_manager.evaluate(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                script=arguments["script"],
            )
            import json
            return [TextContent(type="text", text=f"FeatureScript result:\n{json.dumps(result, indent=2)}")]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error evaluating FeatureScript: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error evaluating FeatureScript: {str(e)}")]

    elif name == "get_bounding_box":
        try:
            result = await featurescript_manager.get_bounding_box(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
            )
            import json
            return [TextContent(type="text", text=f"Bounding box:\n{json.dumps(result, indent=2)}")]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error getting bounding box: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error getting bounding box: {str(e)}")]

    elif name == "export_part_studio":
        try:
            result = await export_manager.export_part_studio(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                format_name=arguments.get("format", "STL"),
                part_id=arguments.get("partId"),
            )
            translation_id = result.get("id", "unknown")
            state = result.get("requestState", "unknown")
            return [TextContent(type="text", text=f"Export started. Translation ID: {translation_id}\nState: {state}")]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error exporting: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error exporting: {str(e)}")]

    elif name == "export_assembly":
        try:
            result = await export_manager.export_assembly(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                format_name=arguments.get("format", "STL"),
            )
            translation_id = result.get("id", "unknown")
            state = result.get("requestState", "unknown")
            return [TextContent(type="text", text=f"Export started. Translation ID: {translation_id}\nState: {state}")]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error exporting: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error exporting: {str(e)}")]

    elif name == "check_assembly_interference":
        try:
            result = await check_assembly_interference(
                assembly_manager=assembly_manager,
                partstudio_manager=partstudio_manager,
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
            )
            return [TextContent(type="text", text=format_interference_result(result))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error checking interference: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error checking interference: {str(e)}")]

    elif name == "get_assembly_positions":
        try:
            report = await get_assembly_positions(
                assembly_manager=assembly_manager,
                partstudio_manager=partstudio_manager,
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
            )
            return [TextContent(type="text", text=report)]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error getting positions: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error getting positions: {str(e)}")]

    elif name == "set_instance_position":
        try:
            msg = await set_absolute_position(
                assembly_manager=assembly_manager,
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                instance_id=arguments["instanceId"],
                x_inches=arguments["x"],
                y_inches=arguments["y"],
                z_inches=arguments["z"],
            )
            return [TextContent(type="text", text=msg)]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error setting position: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error setting position: {str(e)}")]

    elif name == "align_instance_to_face":
        try:
            msg = await align_to_face(
                assembly_manager=assembly_manager,
                partstudio_manager=partstudio_manager,
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                source_instance_id=arguments["sourceInstanceId"],
                target_instance_id=arguments["targetInstanceId"],
                face=arguments["face"],
            )
            return [TextContent(type="text", text=msg)]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error aligning instance: API returned {e.response.status_code}.")]
        except ValueError as e:
            return [TextContent(type="text", text=f"Invalid input: {str(e)}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error aligning instance: {str(e)}")]

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
