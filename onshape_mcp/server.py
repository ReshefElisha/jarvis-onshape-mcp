"""Main MCP server for Onshape integration."""

import os
import sys
import asyncio
import base64
import json
from typing import Any, Optional
import httpx
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent
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
from .builders.extrude import ExtrudeBuilder, ExtrudeEndType, ExtrudeType
from .builders.thicken import ThickenBuilder, ThickenType
from .api.assemblies import AssemblyManager
from .api.featurescript import FeatureScriptManager
from .api.export import ExportManager
from .api.feature_apply import (
    apply_feature_and_check,
    apply_assembly_feature_and_check,
    update_feature_params_and_check,
    FeatureApplyResult,
)
from .api.entities import EntityManager
from .api.describe import DescribeManager
from .api.measurements import MeasurementManager
from .api.custom_features import CustomFeatureManager, DEFAULT_FS_VERSION
from .api.rendering import (
    ShadedViewManager,
    crop_cached_image,
    get_image,
    get_image_meta,
    list_cached_image_ids,
)
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

# Initialize Onshape client. Accept both naming conventions: upstream uses
# ONSHAPE_ACCESS_KEY/SECRET_KEY, Onshape's developer portal examples use
# ONSHAPE_API_KEY/SECRET. Fall back from the former to the latter.
_ak = os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY", "")
_sk = os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET", "")
credentials = OnshapeCredentials(access_key=_ak, secret_key=_sk)
client = OnshapeClient(credentials)
partstudio_manager = PartStudioManager(client)
variable_manager = VariableManager(client)
document_manager = DocumentManager(client)
assembly_manager = AssemblyManager(client)
featurescript_manager = FeatureScriptManager(client)
export_manager = ExportManager(client)
shaded_view_manager = ShadedViewManager(client)
entity_manager = EntityManager(client)
measurement_manager = MeasurementManager(client)
describe_manager = DescribeManager(client)
custom_feature_manager = CustomFeatureManager(client)


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="create_sketch_rectangle",
            description=(
                "Create a rectangular sketch in a Part Studio. "
                "Sketch location: pass either `plane` (standard datum: Front/Top/Right) "
                "or `faceId` (deterministic ID of a face from `list_entities`). "
                "Pass `faceId` to sketch on an existing part face; if both are given, "
                "`faceId` wins and a warning is returned."
            ),
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
                        "description": "Standard datum plane. Defaults to Front if neither plane nor faceId is given.",
                    },
                    "faceId": {
                        "type": "string",
                        "description": "Deterministic ID of an existing face to sketch on (get from `list_entities`). Mutually exclusive with `plane`; wins if both given.",
                    },
                    "corner1": {
                        "type": "array",
                        "items": {"type": ["number", "string"]},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "First corner [x, y]. Bare numbers are mm; use strings like \"10 mm\" or \"0.5 in\" for explicit units.",
                    },
                    "corner2": {
                        "type": "array",
                        "items": {"type": ["number", "string"]},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "Opposite corner [x, y]. Same convention as corner1.",
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
            name="create_rounded_rectangle_sketch",
            description=(
                "Create a rounded rectangle sketch (4 lines + 4 tangent corner "
                "arcs) in ONE feature. Use instead of hand-rolling 4 lines + 4 "
                "arcs with the per-primitive tools -- fewer turns and no "
                "radians/degrees mistakes. Sketch location: pass either "
                "`plane` (Front/Top/Right) or `faceId` (from `list_entities`). "
                "`faceId` wins when both are given. `cornerRadius` must be > 0 "
                "and no more than half the short side of the bounding rect "
                "(otherwise there'd be no straight segments left)."
            ),
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
                        "description": "Standard datum plane. Defaults to Front if neither plane nor faceId is given.",
                    },
                    "faceId": {
                        "type": "string",
                        "description": "Deterministic ID of an existing face (from `list_entities`). Mutually exclusive with `plane`; wins if both given.",
                    },
                    "corner1": {
                        "type": "array",
                        "items": {"type": ["number", "string"]},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "First corner of the bounding rect [x, y]. Bare numbers are mm; use \"10 mm\" / \"0.5 in\" for explicit units.",
                    },
                    "corner2": {
                        "type": "array",
                        "items": {"type": ["number", "string"]},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "Opposite corner of the bounding rect [x, y]. Same convention as corner1.",
                    },
                    "cornerRadius": {
                        "type": ["number", "string"],
                        "description": "Fillet radius at each corner. Bare numbers are mm; use explicit units for in/cm/m.",
                    },
                },
                "required": [
                    "documentId", "workspaceId", "elementId",
                    "corner1", "corner2", "cornerRadius",
                ],
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
                    "depth": {
                        "type": ["number", "string"],
                        "description": "Extrude depth. Bare numbers are mm (CAD default); use \"15 mm\", \"0.5 in\", \"0.03 m\" etc. for explicit units.",
                    },
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
                    "oppositeDirection": {
                        "type": "boolean",
                        "description": (
                            "If true, extrude in the direction OPPOSITE the sketch normal. "
                            "For REMOVE on a sketched picked face this tool auto-flips to "
                            "true regardless of what you pass — because the default "
                            "(sketch-normal direction) cuts AWAY from the material and "
                            "silently removes nothing (Onshape returns featureStatus=INFO). "
                            "Use `forceOppositeDirection: false` to override the auto-flip "
                            "if you actually need the non-default direction (rare)."
                        ),
                    },
                    "forceOppositeDirection": {
                        "type": "boolean",
                        "description": (
                            "Escape hatch that disables the REMOVE+faceId auto-flip. "
                            "Pass true/false to bypass the heuristic entirely. Only use "
                            "this for the unusual case of deliberately cutting away from "
                            "the picked face (e.g. through from underneath). Leaving this "
                            "absent is correct 99% of the time."
                        ),
                    },
                    "endType": {
                        "type": "string",
                        "enum": ["BLIND", "SYMMETRIC"],
                        "description": (
                            "End condition. BLIND: extrude one direction, `depth` is the "
                            "length. SYMMETRIC: extrude both sides of the sketch plane, "
                            "`depth` is the TOTAL length (depth/2 each side). Use SYMMETRIC "
                            "to avoid building two mirrored BLIND extrudes for features that "
                            "should straddle their sketch plane."
                        ),
                        "default": "BLIND",
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
                    "thickness": {
                        "type": ["number", "string"],
                        "description": "Thickness. Bare numbers are mm; use \"0.25 in\" / \"6 mm\" for explicit units.",
                    },
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
            description=(
                "Get all variables from a Variable Studio (or Part Studio). "
                "Modern Onshape stores variables in dedicated Variable Studio "
                "elements; pass a Variable Studio elementId here to read its "
                "variables. Pass a Part Studio elementId to read the (usually "
                "empty) variables owned by that PS."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {
                        "type": "string",
                        "description": "Variable Studio (preferred) or Part Studio element ID",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId"],
            },
        ),
        Tool(
            name="create_variable_studio",
            description=(
                "Create a Variable Studio element in a workspace. Required "
                "before set_variable on modern Onshape docs -- the legacy "
                "Part Studio /variables write path is read-only. Returns the "
                "new VS element id; use it as elementId for set_variable / "
                "get_variables."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "name": {
                        "type": "string",
                        "description": "Name for the new Variable Studio element",
                    },
                },
                "required": ["documentId", "workspaceId", "name"],
            },
        ),
        Tool(
            name="set_variable",
            description=(
                "Write or update a variable in a Variable Studio. `elementId` "
                "MUST be a Variable Studio element id (from "
                "`create_variable_studio`); writing to a Part Studio /variables "
                "endpoint 404s on modern docs. Other Part Studios in the same "
                "workspace can reference this variable as `#name` in any "
                "expression (sketch dimensions, extrude depths, etc.)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {
                        "type": "string",
                        "description": "Variable Studio element ID (from create_variable_studio)",
                    },
                    "name": {"type": "string", "description": "Variable name (FS identifier rules)"},
                    "expression": {
                        "type": "string",
                        "description": "Variable expression (e.g., '30 mm', '0.75 in', '90 deg')",
                    },
                    "type": {
                        "type": "string",
                        "enum": ["LENGTH", "ANGLE", "NUMBER", "ANY"],
                        "description": "FeatureScript variable type. Defaults to LENGTH.",
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
            description="Delete a feature from a Part Studio or Assembly",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio or Assembly element ID"},
                    "featureId": {"type": "string", "description": "Feature ID to delete"},
                    "elementType": {
                        "type": "string",
                        "enum": ["PARTSTUDIO", "ASSEMBLY"],
                        "description": "Type of element containing the feature",
                        "default": "PARTSTUDIO",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "featureId"],
            },
        ),
        Tool(
            name="delete_feature_by_name",
            description=(
                "Delete a Part Studio feature by its display name (e.g. "
                "'Extrude 10mm', 'Sketch 1') without having to look up the "
                "feature ID first. Returns ERROR if zero or multiple features "
                "match the name so the caller can disambiguate."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "name": {"type": "string", "description": "Exact feature name (case-sensitive)"},
                },
                "required": ["documentId", "workspaceId", "elementId", "name"],
            },
        ),
        Tool(
            name="update_feature",
            description=(
                "Modify parameters on an existing Part Studio feature (for "
                "iteration: 'change the extrude depth from 10mm to 15mm', "
                "'swap the fillet radius to 2mm', 'flip oppositeDirection'). "
                "Updates are keyed by the feature's parameterId (e.g. 'depth', "
                "'radius', 'operationType', 'oppositeDirection'). For quantity "
                "params, set `expression` (\"15 mm\", \"0.5 in\", \"90 deg\"). "
                "For boolean/enum params, set `value`. Returns the standard "
                "{ok, status, feature_id, ...} contract so you can tell if the "
                "patched feature still regenerates."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "featureId": {"type": "string", "description": "ID of the feature to update"},
                    "updates": {
                        "type": "array",
                        "description": "Per-parameter patches to apply",
                        "items": {
                            "type": "object",
                            "properties": {
                                "parameterId": {"type": "string", "description": "Parameter key (e.g. 'depth')"},
                                "expression": {"type": "string", "description": "Dimensional expression (quantity params)"},
                                "value": {"description": "Literal value (enum/boolean params)"},
                            },
                            "required": ["parameterId"],
                        },
                        "minItems": 1,
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "featureId", "updates"],
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
            name="delete_document",
            description=(
                "Move an Onshape document to the trash. Irreversible via the "
                "API; intended for cleanup of throwaway docs created by an "
                "agent (test/iteration runs). Returns {ok, status, document_id}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID to delete"},
                },
                "required": ["documentId"],
            },
        ),
        Tool(
            name="create_part_studio",
            description=(
                "Create a new Part Studio in an existing document. Returns the "
                "new Part Studio's elementId AND a list of other Part Studios "
                "in the same workspace (so callers don't accidentally target "
                "the empty default 'Part Studio 1' that most fresh Onshape "
                "documents ship with). Prefer this tool's returned elementId "
                "over re-enumerating via find_part_studios."
            ),
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
            description="Apply a RELATIVE transform to an assembly instance. Translations: bare numbers = mm; strings like \"20 mm\" / \"0.5 in\" for explicit units. Rotations: degrees. Note: fails on fixed/grounded instances — use get_assembly_positions to check the 'fixed' flag first.",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "instanceId": {"type": "string", "description": "Instance ID to transform"},
                    "translateX": {"type": ["number", "string"], "description": "X translation. Bare numbers = mm; strings like \"10 mm\" / \"0.5 in\" respected.", "default": 0},
                    "translateY": {"type": ["number", "string"], "description": "Y translation. Bare = mm; unit-strings respected.", "default": 0},
                    "translateZ": {"type": ["number", "string"], "description": "Z translation. Bare = mm; unit-strings respected.", "default": 0},
                    "rotateX": {"type": "number", "description": "X rotation in degrees", "default": 0},
                    "rotateY": {"type": "number", "description": "Y rotation in degrees", "default": 0},
                    "rotateZ": {"type": "number", "description": "Z rotation in degrees", "default": 0},
                },
                "required": ["documentId", "workspaceId", "elementId", "instanceId"],
            },
        ),
        Tool(
            name="create_fastened_mate",
            description="Create a fastened (rigid) mate between two assembly instances. Requires face IDs from Part Studio body details to place mate connectors on specific faces. Optional offsets shift connectors from face centers (in the face's local XY plane + Z along normal).",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "name": {"type": "string", "description": "Mate name", "default": "Fastened mate"},
                    "firstInstanceId": {"type": "string", "description": "First instance ID"},
                    "secondInstanceId": {"type": "string", "description": "Second instance ID"},
                    "firstFaceId": {"type": "string", "description": "Face deterministic ID on the first instance (from body details)"},
                    "secondFaceId": {"type": "string", "description": "Face deterministic ID on the second instance (from body details)"},
                    "firstOffsetX": {"type": ["number", "string"], "description": "First connector X offset from face center. Bare = mm; unit-strings respected.", "default": 0},
                    "firstOffsetY": {"type": ["number", "string"], "description": "First connector Y offset from face center. Bare = mm; unit-strings respected.", "default": 0},
                    "firstOffsetZ": {"type": ["number", "string"], "description": "First connector Z offset (along face normal). Bare = mm; unit-strings respected.", "default": 0},
                    "secondOffsetX": {"type": ["number", "string"], "description": "Second connector X offset from face center. Bare = mm; unit-strings respected.", "default": 0},
                    "secondOffsetY": {"type": ["number", "string"], "description": "Second connector Y offset from face center. Bare = mm; unit-strings respected.", "default": 0},
                    "secondOffsetZ": {"type": ["number", "string"], "description": "Second connector Z offset (along face normal). Bare = mm; unit-strings respected.", "default": 0},
                },
                "required": ["documentId", "workspaceId", "elementId", "firstInstanceId", "secondInstanceId", "firstFaceId", "secondFaceId"],
            },
        ),
        Tool(
            name="create_revolute_mate",
            description="Create a revolute (rotation) mate between two assembly instances. The first instance rotates relative to the second around the mate connector Z-axis. Requires face IDs from Part Studio body details. Optional offsets shift connectors from face centers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "name": {"type": "string", "description": "Mate name", "default": "Revolute mate"},
                    "firstInstanceId": {"type": "string", "description": "First instance ID"},
                    "secondInstanceId": {"type": "string", "description": "Second instance ID"},
                    "firstFaceId": {"type": "string", "description": "Face deterministic ID on the first instance"},
                    "secondFaceId": {"type": "string", "description": "Face deterministic ID on the second instance"},
                    "minLimit": {"type": "number", "description": "Optional minimum rotation limit in degrees"},
                    "maxLimit": {"type": "number", "description": "Optional maximum rotation limit in degrees"},
                    "firstOffsetX": {"type": ["number", "string"], "description": "First connector X offset. Bare numbers = mm; strings like \"10 mm\" / \"0.5 in\" respected.", "default": 0},
                    "firstOffsetY": {"type": ["number", "string"], "description": "First connector Y offset. Bare = mm; unit-strings respected.", "default": 0},
                    "firstOffsetZ": {"type": ["number", "string"], "description": "First connector Z offset. Bare = mm; unit-strings respected.", "default": 0},
                    "secondOffsetX": {"type": ["number", "string"], "description": "Second connector X offset. Bare = mm; unit-strings respected.", "default": 0},
                    "secondOffsetY": {"type": ["number", "string"], "description": "Second connector Y offset. Bare = mm; unit-strings respected.", "default": 0},
                    "secondOffsetZ": {"type": ["number", "string"], "description": "Second connector Z offset. Bare = mm; unit-strings respected.", "default": 0},
                },
                "required": ["documentId", "workspaceId", "elementId", "firstInstanceId", "secondInstanceId", "firstFaceId", "secondFaceId"],
            },
        ),
        Tool(
            name="create_slider_mate",
            description="Create a slider (linear motion) mate between two assembly instances. The first instance slides relative to the second — positive travel moves the first instance along the face normal direction away from the second. Swap instance order to reverse slide direction. Requires face IDs from Part Studio body details. Optional offsets shift connectors from face centers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "name": {"type": "string", "description": "Mate name", "default": "Slider mate"},
                    "firstInstanceId": {"type": "string", "description": "First instance ID"},
                    "secondInstanceId": {"type": "string", "description": "Second instance ID"},
                    "firstFaceId": {"type": "string", "description": "Face deterministic ID on the first instance"},
                    "secondFaceId": {"type": "string", "description": "Face deterministic ID on the second instance"},
                    "minLimit": {"type": ["number", "string"], "description": "Optional minimum travel limit. Bare = mm; unit-strings respected."},
                    "maxLimit": {"type": ["number", "string"], "description": "Optional maximum travel limit. Bare = mm; unit-strings respected."},
                    "firstOffsetX": {"type": ["number", "string"], "description": "First connector X offset. Bare numbers = mm; strings like \"10 mm\" / \"0.5 in\" respected.", "default": 0},
                    "firstOffsetY": {"type": ["number", "string"], "description": "First connector Y offset. Bare = mm; unit-strings respected.", "default": 0},
                    "firstOffsetZ": {"type": ["number", "string"], "description": "First connector Z offset. Bare = mm; unit-strings respected.", "default": 0},
                    "secondOffsetX": {"type": ["number", "string"], "description": "Second connector X offset. Bare = mm; unit-strings respected.", "default": 0},
                    "secondOffsetY": {"type": ["number", "string"], "description": "Second connector Y offset. Bare = mm; unit-strings respected.", "default": 0},
                    "secondOffsetZ": {"type": ["number", "string"], "description": "Second connector Z offset. Bare = mm; unit-strings respected.", "default": 0},
                },
                "required": ["documentId", "workspaceId", "elementId", "firstInstanceId", "secondInstanceId", "firstFaceId", "secondFaceId"],
            },
        ),
        Tool(
            name="create_cylindrical_mate",
            description="Create a cylindrical (slide + rotate) mate between two assembly instances. The first instance slides and rotates relative to the second along the mate connector Z-axis. Requires face IDs from Part Studio body details. Optional offsets shift connectors from face centers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "name": {"type": "string", "description": "Mate name", "default": "Cylindrical mate"},
                    "firstInstanceId": {"type": "string", "description": "First instance ID"},
                    "secondInstanceId": {"type": "string", "description": "Second instance ID"},
                    "firstFaceId": {"type": "string", "description": "Face deterministic ID on the first instance"},
                    "secondFaceId": {"type": "string", "description": "Face deterministic ID on the second instance"},
                    "minLimit": {"type": ["number", "string"], "description": "Optional minimum axial travel limit. Bare = mm; unit-strings respected."},
                    "maxLimit": {"type": ["number", "string"], "description": "Optional maximum axial travel limit. Bare = mm; unit-strings respected."},
                    "firstOffsetX": {"type": ["number", "string"], "description": "First connector X offset. Bare numbers = mm; strings like \"10 mm\" / \"0.5 in\" respected.", "default": 0},
                    "firstOffsetY": {"type": ["number", "string"], "description": "First connector Y offset. Bare = mm; unit-strings respected.", "default": 0},
                    "firstOffsetZ": {"type": ["number", "string"], "description": "First connector Z offset. Bare = mm; unit-strings respected.", "default": 0},
                    "secondOffsetX": {"type": ["number", "string"], "description": "Second connector X offset. Bare = mm; unit-strings respected.", "default": 0},
                    "secondOffsetY": {"type": ["number", "string"], "description": "Second connector Y offset. Bare = mm; unit-strings respected.", "default": 0},
                    "secondOffsetZ": {"type": ["number", "string"], "description": "Second connector Z offset. Bare = mm; unit-strings respected.", "default": 0},
                },
                "required": ["documentId", "workspaceId", "elementId", "firstInstanceId", "secondInstanceId", "firstFaceId", "secondFaceId"],
            },
        ),
        Tool(
            name="create_mate_connector",
            description="Create an explicit mate connector on a face of an assembly instance. The connector is placed at the face center with its Z-axis along the face normal. Offsets are in the connector's LOCAL coordinate system (X/Y in-plane, Z along normal). Flipping the Z-axis also reverses the other axes via the right-hand rule, which affects how offset translations map to world space.",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "instanceId": {"type": "string", "description": "Instance ID to attach the connector to"},
                    "faceId": {"type": "string", "description": "Face deterministic ID (from Part Studio body details)"},
                    "name": {"type": "string", "description": "Mate connector name", "default": "Mate connector"},
                    "flipPrimary": {"type": "boolean", "description": "Flip the primary (Z) axis direction", "default": False},
                    "secondaryAxisType": {
                        "type": "string",
                        "enum": ["PLUS_X", "PLUS_Y", "MINUS_X", "MINUS_Y"],
                        "description": "Reorient secondary axis",
                        "default": "PLUS_X",
                    },
                    "offsetX": {"type": ["number", "string"], "description": "X offset from face center. Bare = mm; unit-strings respected.", "default": 0},
                    "offsetY": {"type": ["number", "string"], "description": "Y offset from face center. Bare = mm; unit-strings respected.", "default": 0},
                    "offsetZ": {"type": ["number", "string"], "description": "Z offset (along face normal) from face center. Bare = mm; unit-strings respected.", "default": 0},
                },
                "required": ["documentId", "workspaceId", "elementId", "instanceId", "faceId"],
            },
        ),
        # === Sketch Tools ===
        Tool(
            name="create_sketch_circle",
            description=(
                "Create a circular sketch. Pass either `plane` (Front/Top/Right) or "
                "`faceId` (from `list_entities`) to choose the sketch surface. "
                "`faceId` wins when both are given."
            ),
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
                        "description": "Standard datum plane. Defaults to Front if neither plane nor faceId is given.",
                    },
                    "faceId": {
                        "type": "string",
                        "description": "Deterministic ID of an existing face to sketch on (get from `list_entities`). Mutually exclusive with `plane`; wins if both given.",
                    },
                    "center": {
                        "type": "array",
                        "items": {"type": ["number", "string"]},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "Center point [x, y]. Bare numbers are mm; use \"10 mm\" / \"0.5 in\" for explicit units. Preferred over centerX/centerY.",
                    },
                    "centerX": {"type": ["number", "string"], "description": "Center X (bare=mm). Legacy; prefer `center`.", "default": 0},
                    "centerY": {"type": ["number", "string"], "description": "Center Y (bare=mm). Legacy; prefer `center`.", "default": 0},
                    "radius": {"type": ["number", "string"], "description": "Radius. Bare=mm; use \"5 mm\" / \"0.125 in\" for explicit units."},
                    "variableRadius": {
                        "type": "string",
                        "description": (
                            "Optional variable-table name to drive the radius parametrically. "
                            "Emits a RADIUS dimensional constraint with expression `#<name>` "
                            "so a later set_variable call resizes the hole without touching "
                            "this sketch."
                        ),
                    },
                    "variableCenter": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": (
                            "Optional [x_var, y_var] variable names. Emits HORIZONTAL + "
                            "VERTICAL DISTANCE constraints from the sketch origin to the "
                            "circle center, driven by `#x_var` / `#y_var`."
                        ),
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "radius"],
            },
        ),
        Tool(
            name="create_sketch_line",
            description=(
                "Create a line sketch. Pass either `plane` (Front/Top/Right) or "
                "`faceId` (from `list_entities`) to choose the sketch surface. "
                "`faceId` wins when both are given."
            ),
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
                        "description": "Standard datum plane. Defaults to Front if neither plane nor faceId is given.",
                    },
                    "faceId": {
                        "type": "string",
                        "description": "Deterministic ID of an existing face to sketch on (get from `list_entities`). Mutually exclusive with `plane`; wins if both given.",
                    },
                    "startPoint": {
                        "type": "array",
                        "items": {"type": ["number", "string"]},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "Start point [x, y]. Bare numbers are mm; use \"10 mm\" / \"0.5 in\" for explicit units.",
                    },
                    "endPoint": {
                        "type": "array",
                        "items": {"type": ["number", "string"]},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "End point [x, y]. Same convention as startPoint.",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "startPoint", "endPoint"],
            },
        ),
        Tool(
            name="create_sketch_arc",
            description=(
                "Create an arc sketch. Pass either `plane` (Front/Top/Right) or "
                "`faceId` (from `list_entities`) to choose the sketch surface. "
                "`faceId` wins when both are given."
            ),
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
                        "description": "Standard datum plane. Defaults to Front if neither plane nor faceId is given.",
                    },
                    "faceId": {
                        "type": "string",
                        "description": "Deterministic ID of an existing face to sketch on (get from `list_entities`). Mutually exclusive with `plane`; wins if both given.",
                    },
                    "center": {
                        "type": "array",
                        "items": {"type": ["number", "string"]},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "Center point [x, y]. Bare numbers are mm; use \"10 mm\" / \"0.5 in\" for explicit units. Preferred over centerX/centerY.",
                    },
                    "centerX": {"type": ["number", "string"], "description": "Center X (bare=mm). Legacy; prefer `center`.", "default": 0},
                    "centerY": {"type": ["number", "string"], "description": "Center Y (bare=mm). Legacy; prefer `center`.", "default": 0},
                    "radius": {"type": ["number", "string"], "description": "Radius. Bare=mm; use \"5 mm\" / \"0.125 in\" for explicit units."},
                    "variableRadius": {
                        "type": "string",
                        "description": (
                            "Optional variable-table name to drive the arc radius parametrically. "
                            "Emits a RADIUS constraint with expression `#<name>`."
                        ),
                    },
                    "variableCenter": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": (
                            "Optional [x_var, y_var] variable names. HORIZONTAL + VERTICAL "
                            "DISTANCE constraints from sketch origin to arc center."
                        ),
                    },
                    "startAngle": {
                        "type": ["number", "string"],
                        "description": (
                            "Start angle. Bare number = DEGREES (0 = positive X, "
                            "the CAD convention); pass \"45 deg\" or \"1.5 rad\" "
                            "for explicit units. Bare radians will NOT be detected — "
                            "use the string form to avoid silent near-zero arcs."
                        ),
                        "default": 0,
                    },
                    "endAngle": {
                        "type": ["number", "string"],
                        "description": (
                            "End angle. Bare number = DEGREES; "
                            "pass \"180 deg\" or \"3.14 rad\" for explicit units."
                        ),
                        "default": 180,
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "radius"],
            },
        ),
        Tool(
            name="create_sketch",
            description=(
                "Create ONE sketch feature containing many entities at once. "
                "Use this whenever you need >1 primitive on the same plane/face "
                "(e.g. plate outline + 4 mounting holes, NEMA bolt patterns, etc.) "
                "to avoid feature-tree bloat -- 5 holes = 1 feature here vs 5 with "
                "the per-primitive tools. The per-primitive tools "
                "(create_sketch_rectangle/circle/line/arc) stay available as fast "
                "paths for one-shot sketches.\n\n"
                "Sketch location: pass either `plane` (Front/Top/Right) or `faceId` "
                "(from `list_entities`). `faceId` wins when both are given.\n\n"
                "`entities` is an array of mixed primitives. Each item carries a "
                "`type` discriminator and the type-specific args:\n"
                "  rectangle:         {type, corner1:[x,y], corner2:[x,y], variableWidth?, variableHeight?}\n"
                "  rounded_rectangle: {type, corner1:[x,y], corner2:[x,y], cornerRadius}\n"
                "  circle:            {type, center:[x,y], radius, variableRadius?, variableCenter?:[xv,yv]}\n"
                "  line:              {type, start:[x,y], end:[x,y]}\n"
                "  arc:               {type, center:[x,y], radius, startAngle?, endAngle?, variableRadius?, variableCenter?:[xv,yv]}\n"
                "Bare numbers are mm; pass strings like \"10 mm\" / \"0.5 in\" for "
                "explicit units. Arc startAngle/endAngle default to DEGREES — "
                "pass strings like \"1.5 rad\" when you need radians."
            ),
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
                        "description": "Standard datum plane. Defaults to Front if neither plane nor faceId is given.",
                    },
                    "faceId": {
                        "type": "string",
                        "description": "Deterministic ID of an existing face (from `list_entities`). Mutually exclusive with `plane`; wins if both given.",
                    },
                    "entities": {
                        "type": "array",
                        "minItems": 1,
                        "description": "Mixed list of sketch primitives keyed by `type`.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["rectangle", "rounded_rectangle", "circle", "line", "arc"],
                                },
                            },
                            "required": ["type"],
                        },
                    },
                },
                "required": ["documentId", "workspaceId", "elementId", "entities"],
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
                    "radius": {
                        "type": ["number", "string"],
                        "description": "Fillet radius. Bare numbers are mm (CAD default); use \"2 mm\" / \"0.125 in\" for explicit units.",
                    },
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
                    "distance": {
                        "type": ["number", "string"],
                        "description": "Chamfer distance. Bare numbers are mm; use \"2 mm\" / \"0.125 in\" for explicit units.",
                    },
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
            description=(
                "Create a linear pattern of features. Requires a deterministic edge id "
                "whose direction the pattern will follow — Onshape has no implicit "
                "world-X axis usable here. Workflow: create a reference (a sketch line "
                "on any plane pointing the direction you want, or pick an existing body "
                "edge via list_entities), then pass its id as directionEdgeId."
            ),
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
                    "distance": {
                        "type": ["number", "string"],
                        "description": "Distance between pattern instances. Bare numbers are mm; use \"10 mm\" / \"0.5 in\" for explicit units.",
                    },
                    "count": {"type": "integer", "description": "Total number of instances", "default": 2},
                    "directionEdgeId": {
                        "type": "string",
                        "description": (
                            "Deterministic id of an edge whose direction the pattern "
                            "follows. Get from list_entities(kinds=['edges']) on an "
                            "existing body, or from a sketch line you drew specifically "
                            "as a reference. Required."
                        ),
                    },
                },
                "required": [
                    "documentId", "workspaceId", "elementId",
                    "featureIds", "distance", "directionEdgeId",
                ],
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
            description=(
                "Export a Part Studio to STL, STEP, PARASOLID, GLTF, or OBJ. "
                "Blocks until Onshape finishes the translation, downloads the "
                "bytes, and writes them to /tmp/onshape-mcp-exports/. Returns "
                "the on-disk path, size, and final state so the user can open "
                "the file. Raises an explicit error on FAILED or timeout."
            ),
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
                    "timeoutSeconds": {
                        "type": "number",
                        "description": "Max seconds to wait for translation",
                        "default": 120,
                    },
                    "pollIntervalSeconds": {
                        "type": "number",
                        "description": "Seconds between status polls",
                        "default": 1.0,
                    },
                },
                "required": ["documentId", "workspaceId", "elementId"],
            },
        ),
        Tool(
            name="export_assembly",
            description=(
                "Export an Assembly to STL, STEP, or GLTF. Blocks until "
                "Onshape finishes the translation, downloads the bytes, and "
                "writes them to /tmp/onshape-mcp-exports/. Returns on-disk "
                "path, size, and final state."
            ),
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
                    "timeoutSeconds": {
                        "type": "number",
                        "description": "Max seconds to wait for translation",
                        "default": 120,
                    },
                    "pollIntervalSeconds": {
                        "type": "number",
                        "description": "Seconds between status polls",
                        "default": 1.0,
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
            description="Get positions, sizes, and world-space bounds of all instances in an assembly (in mm).",
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
            description="Set an instance to an ABSOLUTE position (bare numbers = mm; strings like \"20 mm\" / \"0.5 in\" for explicit units). Unlike transform_instance this sets absolute coords and resets rotation to identity. Note: fails on fixed/grounded instances (API returns 400).",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "instanceId": {"type": "string", "description": "Instance ID to position"},
                    "x": {"type": ["number", "string"], "description": "Absolute X position. Bare = mm; unit-strings like \"20 mm\" / \"0.5 in\" respected."},
                    "y": {"type": ["number", "string"], "description": "Absolute Y position. Bare = mm; unit-strings respected."},
                    "z": {"type": ["number", "string"], "description": "Absolute Z position. Bare = mm; unit-strings respected."},
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
        Tool(
            name="get_body_details",
            description="Get face-level geometry details for all parts in a Part Studio. Returns face deterministic IDs, surface types (PLANE, CYLINDER, etc.), and for planar faces: normal vectors and origin points. Use face IDs with mate connector tools.",
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
            name="get_assembly_features",
            description="Get all features (mates, mate connectors, etc.) from an assembly with their current state (OK, ERROR, SUPPRESSED). Useful for inspecting existing mates and debugging assembly issues.",
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
            name="get_face_coordinate_system",
            description=(
                "Query the true outward-facing coordinate system for a face on an assembly instance. "
                "Returns the guaranteed outward normal (Z-axis), tangent axes (X/Y), and origin. "
                "More reliable than body details normals. Use this to verify face orientations before creating mates."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "instanceId": {"type": "string", "description": "Instance ID containing the face"},
                    "faceId": {"type": "string", "description": "Face deterministic ID (from body details)"},
                },
                "required": ["documentId", "workspaceId", "elementId", "instanceId", "faceId"],
            },
        ),
        # === Visual / Rendering Tools (added by dyna-fork) ===
        Tool(
            name="render_part_studio_views",
            description=(
                "Render one or more shaded views of a Part Studio and return the PNGs so "
                "Claude can actually see the 3D result. Use this after every feature that "
                "creates or modifies visible geometry. The returned image_ids can be passed "
                "to crop_image to zoom into suspicious regions. Claude Opus 4.7 spatial "
                "reasoning is weak — always render the view you need rather than mentally "
                "rotating. Default views: iso, top, front, right."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "views": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of named views (iso, top, front, back, left, right, bottom) "
                            "or raw comma-separated 12-float viewMatrix strings."
                        ),
                        "default": ["iso", "top", "front", "right"],
                    },
                    "width": {"type": "integer", "default": 1200, "description": "Output width in pixels"},
                    "height": {"type": "integer", "default": 800, "description": "Output height in pixels"},
                    "edges": {"type": "boolean", "default": True, "description": "Render feature/silhouette edges"},
                },
                "required": ["documentId", "workspaceId", "elementId"],
            },
        ),
        Tool(
            name="render_assembly_views",
            description=(
                "Render shaded views of an Assembly. Same semantics as render_part_studio_views."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Assembly element ID"},
                    "views": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["iso", "top", "front", "right"],
                    },
                    "width": {"type": "integer", "default": 1200},
                    "height": {"type": "integer", "default": 800},
                    "edges": {"type": "boolean", "default": True},
                },
                "required": ["documentId", "workspaceId", "elementId"],
            },
        ),
        Tool(
            name="crop_image",
            description=(
                "Zoom into a region of a cached image by normalized 0..1 bounding box. "
                "Use after render_* when you need to inspect a detail — a specific face, "
                "a feature edge, a suspicious fillet. (0,0) is top-left, (1,1) is "
                "bottom-right. Returns a new image keyed by its own image_id. This is "
                "the pattern behind Anthropic's CharXiv 84.7 -> 91.0% 'with tools' "
                "benchmark result; use it liberally."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "imageId": {"type": "string", "description": "image_id from a previous render_* or crop_image call"},
                    "x1": {"type": "number", "minimum": 0, "maximum": 1, "description": "Left edge (0..1)"},
                    "y1": {"type": "number", "minimum": 0, "maximum": 1, "description": "Top edge (0..1)"},
                    "x2": {"type": "number", "minimum": 0, "maximum": 1, "description": "Right edge (0..1), must be > x1"},
                    "y2": {"type": "number", "minimum": 0, "maximum": 1, "description": "Bottom edge (0..1), must be > y1"},
                },
                "required": ["imageId", "x1", "y1", "x2", "y2"],
            },
        ),
        Tool(
            name="list_entities",
            description=(
                "Enumerate every face, edge, and vertex of every body in a Part Studio "
                "with deterministic IDs you can drop into subsequent feature payloads. "
                "Each entity has a human-readable 'description' like 'plane / outward +Z / "
                "origin (0.0,0.0,15.0) mm' or 'cylinder / radius 5.00 mm / origin ... mm' "
                "so you can pick the right one by reading rather than geometric reasoning. "
                "Call this after ANY feature that creates or modifies bodies, before "
                "sketching on a face, filleting an edge, mating to a face, or otherwise "
                "referencing picked geometry. IDs (JHK, JNC, JHl, ...) are the "
                "'deterministicIds' you put in a BTMIndividualQuery-138 query entry.\n\n"
                "FILTERS (all optional; prune BEFORE serialization so responses stay small "
                "on complex parts): `geometry_type` (PLANE/CYLINDER/LINE/ARC/...), "
                "`outward_axis` (+X/-X/+Y/-Y/+Z/-Z), `at_z_mm` + `at_z_tol_mm` (faces "
                "pick by origin Z; edges pick by midpoint Z), `radius_range_mm` "
                "([min,max] mm; cylinders/arcs/circles), `length_range_mm` ([min,max] mm; "
                "edges only). The response echoes `filters` and reports both "
                "`original_counts` and `filtered_counts` per body so you can see how much "
                "pruning happened."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "kinds": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["faces", "edges", "vertices"]},
                        "description": "Subset to return; defaults to all three.",
                        "default": ["faces", "edges", "vertices"],
                    },
                    "bodyIndex": {
                        "type": "integer",
                        "description": "0-based body index to limit output. Omit for all bodies.",
                    },
                    "geometryType": {
                        "type": "string",
                        "description": (
                            "Case-insensitive type filter. For faces: PLANE, CYLINDER, "
                            "CONE, TORUS, SPHERE, B_SURFACE. For edges: LINE, CIRCLE, "
                            "ARC, B_CURVE. Entities without the named type are pruned."
                        ),
                    },
                    "outwardAxis": {
                        "type": "string",
                        "enum": ["+X", "-X", "+Y", "-Y", "+Z", "-Z"],
                        "description": (
                            "Face filter: keep only faces whose body-outward normal is "
                            "this world axis. Falls back to `normal_axis` for faces the "
                            "FS probe couldn't evaluate."
                        ),
                    },
                    "atZmm": {
                        "type": "number",
                        "description": (
                            "Z cut in mm. Keep only faces whose origin Z (planar) is "
                            "within `atZtolMm` of this value, and edges whose midpoint "
                            "Z is within tolerance."
                        ),
                    },
                    "atZtolMm": {
                        "type": "number",
                        "description": "Tolerance around atZmm in mm; default 0.5.",
                        "default": 0.5,
                    },
                    "radiusRangeMm": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": (
                            "[min_mm, max_mm] inclusive. Keeps only entities with a "
                            "radius in range (cylinders/cones/tori for faces; "
                            "circles/arcs for edges)."
                        ),
                    },
                    "lengthRangeMm": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "Edges only: [min_mm, max_mm] inclusive edge length.",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId"],
            },
        ),
        Tool(
            name="describe_part_studio",
            description=(
                "One-shot snapshot of a Part Studio's entire design state. Returns BOTH a "
                "structured text representation (feature tree with statuses, body topology "
                "with every face and edge classified by type + deterministic ID + "
                "coordinates, bounding box, mass properties) AND the multi-view rendered "
                "images (iso/top/front/right by default). Use this INSTEAD OF chaining "
                "get_features + list_entities + render_part_studio_views + get_mass_properties "
                "after every mutation. The text is what you reason over (reliable for you). "
                "The images catch visual regressions the text misses. Image_ids returned "
                "in the text can be cropped via crop_image."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string"},
                    "workspaceId": {"type": "string"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "views": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["iso", "top", "front", "right"],
                        "description": "Named views to render (iso/top/front/back/left/right/bottom).",
                    },
                    "renderWidth": {"type": "integer", "default": 1200},
                    "renderHeight": {"type": "integer", "default": 800},
                },
                "required": ["documentId", "workspaceId", "elementId"],
            },
        ),
        Tool(
            name="measure",
            description=(
                "Numeric distance + angle between two entities (faces/edges/vertices) "
                "picked by deterministic ID. Use this instead of eyeballing a render when "
                "you need precise geometric facts: 'are these faces parallel?', 'what's "
                "the distance between the top face and the hole floor?', 'is this edge "
                "perpendicular to that plane?'. Input: two IDs from list_entities. Returns "
                "point_distance_m, angle_deg, parallel/perpendicular flags, and when "
                "applicable a projected plane-to-plane or point-to-plane distance. Always "
                "prefer this over visual inspection for precision-sensitive decisions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string"},
                    "workspaceId": {"type": "string"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "entityAId": {"type": "string", "description": "Deterministic ID of entity A"},
                    "entityBId": {"type": "string", "description": "Deterministic ID of entity B"},
                },
                "required": ["documentId", "workspaceId", "elementId", "entityAId", "entityBId"],
            },
        ),
        Tool(
            name="get_mass_properties",
            description=(
                "Mass properties (volume, mass, center of mass, principal inertia, bbox) "
                "for every body in a Part Studio, or a specific part if partId is given. "
                "Values come as [min, mean, max] uncertainty triples. Mass is zero unless "
                "a material is assigned; volume and centroid are always meaningful."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string"},
                    "workspaceId": {"type": "string"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"},
                    "partId": {
                        "type": "string",
                        "description": "Optional specific part ID. Omit for all parts.",
                    },
                },
                "required": ["documentId", "workspaceId", "elementId"],
            },
        ),
        Tool(
            name="list_cached_images",
            description=(
                "List every image currently in the in-process render cache with its "
                "metadata (view, source part studio, dimensions, crop lineage). Use to "
                "recover an image_id you need to crop or re-render, or to audit what "
                "you've looked at so far."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="write_featurescript_feature",
            description=(
                "Paradigm escape hatch. Author an arbitrary FeatureScript custom "
                "feature (threads, helices, shells, drafts, sweeps along a path, "
                "patterns along a curve -- anything our primitives can't express) "
                "and apply it to a Part Studio in one call. The system creates a "
                "Feature Studio element in the same workspace, uploads your source, "
                "confirms it compiles, fetches the sourceMicroversionId, and "
                "instantiates a BTMFeature-134 with the correct "
                "`e{fs_eid}::m{microversion}` namespace.\n\n"
                "`featureScript` is a COMPLETE FS source file. Prelude: "
                "`FeatureScript 2909;\\nimport(path:\"onshape/std/geometry.fs\",version:\"2909.0\");`. "
                "Export exactly one `defineFeature(...)` whose binding name matches "
                "the `featureType` arg. Minimal worked example (offset plane):\n"
                "```\n"
                "FeatureScript 2909;\n"
                "import(path:\"onshape/std/geometry.fs\",version:\"2909.0\");\n"
                "annotation { \"Feature Type Name\" : \"My feat\" }\n"
                "export const myFeat = defineFeature(function(context is Context, id is Id, definition is map)\n"
                "    precondition { annotation{\"Name\":\"Offset\"} isLength(definition.offset, LENGTH_BOUNDS); }\n"
                "    {\n"
                "        opPlane(context, id + \"p\", {\"plane\": plane(vector(0,0,definition.offset), vector(0,0,1), vector(1,0,0))});\n"
                "    });\n"
                "```\n"
                "`parameters` is a list of `{id, type, value}` dicts to bind "
                "precondition variables. type ∈ {quantity, string, boolean, real}. "
                "For quantity, value is a unit-tagged string like \"25 mm\" or \"0.5 in\"."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string"},
                    "workspaceId": {"type": "string"},
                    "elementId": {"type": "string", "description": "Target Part Studio element ID"},
                    "featureType": {
                        "type": "string",
                        "description": "The exported defineFeature binding name. MUST match the `export const <name> = ...` in featureScript.",
                    },
                    "featureScript": {
                        "type": "string",
                        "description": "Complete FS source. Must start with `FeatureScript <N>;` where N is the current std library version (currently 2909).",
                    },
                    "featureName": {
                        "type": "string",
                        "description": "Human-readable name that shows up in the Onshape feature tree.",
                    },
                    "parameters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "type": {
                                    "type": "string",
                                    "enum": ["quantity", "string", "boolean", "real"],
                                },
                                "value": {},
                            },
                            "required": ["id", "type"],
                        },
                        "description": "Bind precondition variables. Omit if the custom feature takes no inputs.",
                    },
                    "fsElementName": {
                        "type": "string",
                        "description": "Optional name for the Feature Studio element that carries the source. Defaults to ClaudeFS_<featureType>.",
                    },
                },
                "required": [
                    "documentId", "workspaceId", "elementId",
                    "featureType", "featureScript", "featureName",
                ],
            },
        ),
    ]


METERS_TO_INCHES = 1 / 0.0254

EXPORT_DIR = "/tmp/onshape-mcp-exports"


def _write_export_to_disk(result, element_id: str) -> str:
    """Persist a successful TranslationResult to EXPORT_DIR and return the path.

    Filename is prefixed with a timestamp + element ID prefix so a user running
    many exports can tell artifacts apart without relying on the translation id.
    Raises if called on a non-ok result.
    """
    import os
    import time

    if not result.ok or result.data is None:
        raise ValueError("Cannot write a failed translation result to disk")

    os.makedirs(EXPORT_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    base = result.filename or f"{result.translation_id}.{result.format_name.lower()}"
    # Keep filenames short and recognizable.
    short_elem = element_id[:8] if element_id else "x"
    safe_base = base.replace("/", "_").replace(" ", "_")
    out_path = os.path.join(EXPORT_DIR, f"{ts}-{short_elem}-{safe_base}")
    with open(out_path, "wb") as f:
        f.write(result.data)
    return out_path


def _format_export_result(result, element_id: str) -> str:
    """Format a TranslationResult as the text body returned to the MCP client."""
    if not result.ok:
        return (
            f"Export FAILED ({result.state}).\n"
            f"Translation ID: {result.translation_id or '<none>'}\n"
            f"Format: {result.format_name}\n"
            f"Error: {result.error_message or 'unknown'}"
        )
    out_path = _write_export_to_disk(result, element_id)
    size = len(result.data)
    return (
        f"Export DONE.\n"
        f"Path: {out_path}\n"
        f"Size: {size} bytes\n"
        f"Format: {result.format_name}\n"
        f"Filename: {result.filename}\n"
        f"Translation ID: {result.translation_id}"
    )


def _hints_for_result(result: FeatureApplyResult) -> list[str]:
    """Pick the `hints` list to attach to a tool response based on its status.

    Nudges Claude toward the next reflex: inspect what just happened, or
    recover from a failure, or notice when an FS custom feature would be
    cleaner than another layer of primitives. Keep each hint short and
    actionable; the downstream LLM reads these every turn.

    Rotation policy:
      - OK / INFO   -> next-step reflex: describe + mention write_featurescript_feature.
      - WARNING     -> read error_message, check VS for missing vars.
      - ERROR       -> update_feature or delete_feature_by_name + retry.
      - EXCEPTION   -> handled in `_exception_json`, not here.
      - UNKNOWN     -> conservative: suggest describe_part_studio to learn state.
    """
    status = result.status
    if status in ("OK", "INFO"):
        return [
            "To see what changed, call describe_part_studio — the PHYSICAL "
            "SUMMARY + changes block show new topology at a glance.",
            "Doing the same 3-feature pattern twice? write_featurescript_feature "
            "can encapsulate it as a reusable op. See SKILL.md -> When to write "
            "a FeatureScript custom feature.",
        ]
    if status == "WARNING":
        return [
            "Read error_message above for the diagnostic. If it references "
            "a missing variable (SKETCH_DIMENSION_MISSING_PARAMETER), "
            "set_variable it in the Variable Studio first.",
            "The feature IS in the tree with WARNING status — downstream tools "
            "may still build on it, but the parametric binding you intended "
            "may not be driving the geometry. Verify with describe_part_studio.",
        ]
    if status == "ERROR":
        return [
            "Feature did NOT build. Either update_feature the same id with "
            "corrected params, or delete_feature_by_name and retry — do not "
            "add more features on top.",
            "Check error_message for the FS statusEnum (e.g. "
            "SKETCH_MISSING_LOCAL_REFERENCE, INCOMPATIBLE_FACE_ENTITY) — "
            "it names the constraint that rejected the feature.",
        ]
    # UNKNOWN / anything else
    return [
        "Feature status came back unrecognized; call describe_part_studio "
        "to see the current feature tree + body topology before proceeding."
    ]


def _feature_apply_json(
    result: FeatureApplyResult,
    *,
    tool_name: Optional[str] = None,
    warnings: Optional[list[str]] = None,
    notes: Optional[list[str]] = None,
    hints: Optional[list[str]] = None,
) -> str:
    """Serialize a FeatureApplyResult as the structured JSON the MCP tool returns.

    All mutating Part Studio tool handlers route their response through this
    helper so the downstream LLM sees one consistent shape. Fields mirror the
    helper's result model; `raw` is omitted so the Onshape feature-state dump
    doesn't balloon the context window. `tool_name` is included so the LLM can
    tell which call produced a given record when logs get interleaved.

    `warnings` is for misuse signals the caller should heed (e.g. "you passed
    both plane and faceId; using faceId"). `notes` is for informational
    bookkeeping where the tool made a judgment call on the caller's behalf
    (e.g. "auto-set oppositeDirection=true because this REMOVE extrude is
    sketched on a picked face"). `hints` points at the next useful action
    (describe, retry, write_featurescript_feature, etc.) based on status;
    defaults are picked by `_hints_for_result` but callers can pass their
    own. All three are only emitted when non-empty so existing callers see
    a stable shape.
    """
    payload: dict[str, Any] = {
        "ok": result.ok,
        "status": result.status,
        "feature_id": result.feature_id,
        "feature_type": result.feature_type,
        "feature_name": result.feature_name,
        "error_message": result.error_message,
    }
    if tool_name:
        payload["tool"] = tool_name
    if warnings:
        payload["warnings"] = list(warnings)
    if notes:
        payload["notes"] = list(notes)
    if result.changes is not None:
        # "git diff" for CAD — only present when the handler asked the
        # helper to track_changes. Topology-mutating tools default it on;
        # sketches default it off (sketches don't change body topology).
        payload["changes"] = result.changes
    # Default status-based hints if the handler didn't override.
    hints_list = list(hints) if hints else _hints_for_result(result)
    if hints_list:
        payload["hints"] = hints_list
    return json.dumps(payload, indent=2)


# Standard datum plane deterministic ids. Anything else in a sketch's
# `sketchPlane` parameter signals the sketch was placed on a picked face.
_STANDARD_PLANE_IDS = frozenset({"JCC", "JDC", "JEC"})


async def _sketch_is_on_face(
    document_id: str,
    workspace_id: str,
    element_id: str,
    sketch_feature_id: str,
) -> bool:
    """Return True if the named sketch was placed on a picked face (vs a
    standard Front/Top/Right plane).

    Walks the sketch feature's `sketchPlane` parameter and checks whether the
    referenced deterministic id matches a default plane (JCC/JDC/JEC) or
    something else. Returns False on any lookup or shape error so callers
    fall back to legacy behavior rather than crash.
    """
    try:
        feats = await partstudio_manager.get_features(
            document_id, workspace_id, element_id
        )
        sketch = next(
            (
                f for f in feats.get("features", []) or []
                if f.get("featureId") == sketch_feature_id
            ),
            None,
        )
        if not sketch:
            return False
        for p in sketch.get("parameters", []) or []:
            if p.get("parameterId") != "sketchPlane":
                continue
            queries = p.get("queries") or []
            for q in queries:
                ids = q.get("deterministicIds") or []
                for ent_id in ids:
                    if ent_id and ent_id not in _STANDARD_PLANE_IDS:
                        return True
        return False
    except Exception:  # noqa: BLE001
        return False


async def _resolve_sketch_plane_id(
    arguments: dict,
) -> tuple[str, SketchPlane, list[str]]:
    """Figure out which deterministic ID to sketch on.

    Returns (plane_id, plane_enum, warnings). `faceId` wins when both are
    given. When `faceId` is used the enum is set to FRONT as a neutral
    placeholder — SketchBuilder.build() only consumes `plane_id` for the
    BTMIndividualQuery-138 parameter.
    """
    face_id = arguments.get("faceId")
    warnings: list[str] = []
    if face_id:
        if arguments.get("plane"):
            warnings.append(
                "Both `plane` and `faceId` provided; using `faceId`."
            )
        return face_id, SketchPlane.FRONT, warnings
    plane_name = arguments.get("plane", "Front")
    plane_enum = SketchPlane[plane_name.upper()]
    plane_id = await partstudio_manager.get_plane_id(
        arguments["documentId"],
        arguments["workspaceId"],
        arguments["elementId"],
        plane_name,
    )
    return plane_id, plane_enum, warnings


def _exception_json(
    error: BaseException,
    *,
    tool_name: Optional[str] = None,
    status_code: Optional[int] = None,
    hints: Optional[list[str]] = None,
) -> str:
    """Serialize an unexpected exception as the same structured shape.

    Used by mutating-tool handlers so clients never have to branch on whether
    the response was free text or JSON. `status` is "EXCEPTION" so callers can
    distinguish an Onshape-reported failure ("ERROR") from a plumbing failure.

    Default hints point Claude at `describe_part_studio` to rediscover the
    tree's current state -- an exception here usually means the feature
    wasn't even attempted on Onshape's side, so the prior state is intact.
    """
    msg = str(error)
    if status_code is not None:
        msg = f"HTTP {status_code}: {msg}"
    payload: dict[str, Any] = {
        "ok": False,
        "status": "EXCEPTION",
        "feature_id": "",
        "feature_type": "",
        "feature_name": "",
        "error_message": msg,
    }
    if tool_name:
        payload["tool"] = tool_name
    hints_list = list(hints) if hints else [
        "Tool call raised before Onshape received it -- the feature tree "
        "is unchanged from before this call. Call describe_part_studio to "
        "confirm, then retry with corrected params.",
        "HTTP 4xx usually means a bad tool-arg shape (missing required "
        "field, wrong type). Re-read the tool schema or ToolSearch the "
        "tool name for hints.",
    ]
    if hints_list:
        payload["hints"] = hints_list
    return json.dumps(payload, indent=2)


def _enrich_rectangular_body(
    planar_faces: list[dict],
) -> dict | None:
    """Compute enriched face data for rectangular solids (6 planar faces).

    Groups faces by normal axis, determines true outward normals,
    computes face dimensions, and adds directional labels.

    Returns None if the body doesn't appear to be a rectangular solid.
    """
    if len(planar_faces) != 6:
        return None

    # Group faces by dominant normal axis
    axis_groups: dict[str, list[dict]] = {"x": [], "y": [], "z": []}
    for face in planar_faces:
        abs_nx = abs(face["nx"])
        abs_ny = abs(face["ny"])
        abs_nz = abs(face["nz"])
        if abs_nx >= abs_ny and abs_nx >= abs_nz:
            axis_groups["x"].append(face)
        elif abs_ny >= abs_nx and abs_ny >= abs_nz:
            axis_groups["y"].append(face)
        else:
            axis_groups["z"].append(face)

    # Need exactly 2 faces per axis for a rectangular solid
    if not all(len(g) == 2 for g in axis_groups.values()):
        return None

    # Sort each axis pair by origin coordinate; determine outward normals
    faces_enriched: dict[str, dict] = {}
    bbox: dict[str, float] = {}

    axis_coord = {"x": "ox", "y": "oy", "z": "oz"}
    outward_labels = {
        "x": [("-X", "(-1, 0, 0)"), ("+X", "(+1, 0, 0)")],
        "y": [("-Y", "(0, -1, 0)"), ("+Y", "(0, +1, 0)")],
        "z": [("-Z", "(0, 0, -1)"), ("+Z", "(0, 0, +1)")],
    }

    for axis, group in axis_groups.items():
        coord_key = axis_coord[axis]
        sorted_faces = sorted(group, key=lambda f: f[coord_key])
        bbox[f"{axis}_min"] = sorted_faces[0][coord_key]
        bbox[f"{axis}_max"] = sorted_faces[1][coord_key]

        for i, face in enumerate(sorted_faces):
            label, outward = outward_labels[axis][i]
            faces_enriched[face["id"]] = {
                "label": label,
                "outward_normal": outward,
                "axis": axis,
                "is_max": i == 1,
            }

    # Compute body dimensions in inches
    lx = (bbox["x_max"] - bbox["x_min"]) * METERS_TO_INCHES
    ly = (bbox["y_max"] - bbox["y_min"]) * METERS_TO_INCHES
    lz = (bbox["z_max"] - bbox["z_min"]) * METERS_TO_INCHES

    # Compute face dimensions (the two dimensions perpendicular to face normal)
    face_dims = {"x": (ly, lz), "y": (lx, lz), "z": (lx, ly)}
    for face_id, data in faces_enriched.items():
        w, h = face_dims[data["axis"]]
        data["width"] = w
        data["height"] = h

    return {"dimensions": (lx, ly, lz), "faces": faces_enriched}


def _extract_offsets(arguments: dict, prefix: str) -> tuple[float, float, float] | None:
    """Extract XYZ offset tuple from tool arguments, returning None if all zero."""
    x = arguments.get(f"{prefix}OffsetX", 0)
    y = arguments.get(f"{prefix}OffsetY", 0)
    z = arguments.get(f"{prefix}OffsetZ", 0)
    if x == 0 and y == 0 and z == 0:
        return None
    return (x, y, z)


async def _create_mate(
    onshape_client,
    document_id: str,
    workspace_id: str,
    element_id: str,
    first_instance_id: str,
    second_instance_id: str,
    first_face_id: str,
    second_face_id: str,
    mate_name: str,
    mate_type: MateType,
    min_limit: float | None = None,
    max_limit: float | None = None,
    first_offset: tuple[float, float, float] | None = None,
    second_offset: tuple[float, float, float] | None = None,
) -> FeatureApplyResult:
    """Create a mate between two instances using explicit mate connectors.

    Creates mate connector MC1 on a face of instance 1, mate connector MC2 on
    a face of instance 2, then the BTMMate-64 that binds them. Each POST
    rides through `apply_assembly_feature_and_check`, so a MC or mate that
    the solver rejects surfaces as `status=ERROR` instead of the old prose
    "Created fastened mate ..." silent-success return.

    Fail-fast: if MC1 or MC2 errors at featureStatus level, the function
    returns that result without trying to build the mate on top of broken
    connectors. The returned result carries the feature_id/status of the
    first failing step, so the caller can surface it verbatim.

    Args:
        first_offset: Optional (x, y, z) offset in meters from first face
            centroid. mm-default conversion happens at the tool-handler layer.
        second_offset: Same for the second connector.

    Returns:
        FeatureApplyResult representing the final mate (or the first failing
        MC/mate step if something earlier broke).
    """
    # MC1
    mc1 = MateConnectorBuilder(
        name=f"{mate_name} - MC1",
        face_id=first_face_id,
        occurrence_path=[first_instance_id],
    )
    if first_offset:
        mc1.set_translation(*first_offset)
    mc1_result = await apply_assembly_feature_and_check(
        onshape_client, document_id, workspace_id, element_id, mc1.build(),
    )
    if not mc1_result.ok:
        return mc1_result

    # MC2
    mc2 = MateConnectorBuilder(
        name=f"{mate_name} - MC2",
        face_id=second_face_id,
        occurrence_path=[second_instance_id],
    )
    if second_offset:
        mc2.set_translation(*second_offset)
    mc2_result = await apply_assembly_feature_and_check(
        onshape_client, document_id, workspace_id, element_id, mc2.build(),
    )
    if not mc2_result.ok:
        return mc2_result

    # The mate itself
    mate = MateBuilder(name=mate_name, mate_type=mate_type)
    mate.set_first_connector(mc1_result.feature_id)
    mate.set_second_connector(mc2_result.feature_id)
    if min_limit is not None and max_limit is not None:
        mate.set_limits(min_limit, max_limit)
    return await apply_assembly_feature_and_check(
        onshape_client, document_id, workspace_id, element_id, mate.build(),
    )


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent | ImageContent]:
    """Handle tool calls."""

    if name == "create_sketch_rectangle":
        try:
            plane_id, plane, warnings = await _resolve_sketch_plane_id(arguments)
            sketch = SketchBuilder(
                name=arguments.get("name", "Sketch"), plane=plane, plane_id=plane_id
            )
            sketch.add_rectangle(
                corner1=tuple(arguments["corner1"]),
                corner2=tuple(arguments["corner2"]),
                variable_width=arguments.get("variableWidth"),
                variable_height=arguments.get("variableHeight"),
            )

            result = await apply_feature_and_check(
                client,
                arguments["documentId"],
                arguments["workspaceId"],
                arguments["elementId"],
                sketch.build(),
            )
            return [TextContent(type="text", text=_feature_apply_json(result, tool_name=name, warnings=warnings))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating sketch rectangle")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_rounded_rectangle_sketch":
        try:
            plane_id, plane, warnings = await _resolve_sketch_plane_id(arguments)
            sketch = SketchBuilder(
                name=arguments.get("name", "Sketch"), plane=plane, plane_id=plane_id
            )
            sketch.add_rounded_rectangle(
                corner1=tuple(arguments["corner1"]),
                corner2=tuple(arguments["corner2"]),
                corner_radius=arguments["cornerRadius"],
            )
            result = await apply_feature_and_check(
                client,
                arguments["documentId"],
                arguments["workspaceId"],
                arguments["elementId"],
                sketch.build(),
            )
            return [TextContent(type="text", text=_feature_apply_json(result, tool_name=name, warnings=warnings))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating rounded rectangle sketch")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_extrude":
        try:
            raw_op = arguments.get("operationType", "NEW")
            try:
                op_type = ExtrudeType[raw_op]
            except KeyError:
                return [TextContent(type="text", text=_exception_json(
                    ValueError(
                        f"Invalid operationType {raw_op!r}; must be NEW | ADD | REMOVE | INTERSECT"
                    ),
                    tool_name=name,
                ))]
            raw_end = arguments.get("endType", "BLIND")
            try:
                end_type = ExtrudeEndType[raw_end]
            except KeyError:
                return [TextContent(type="text", text=_exception_json(
                    ValueError(
                        f"Invalid endType {raw_end!r}; must be BLIND | SYMMETRIC"
                    ),
                    tool_name=name,
                ))]
            # Smart default for the silent-no-op trap (dogfooder #7): a REMOVE
            # extrude on a sketch placed on a picked face cuts AWAY from the
            # face by default, which means cutting into air -- Onshape returns
            # `INFO: nothing to cut`, helper reports ok=true, Claude moves on
            # unaware. When `oppositeDirection` isn't passed explicitly AND
            # the operation is REMOVE AND the sketch lives on a picked face,
            # default to True so the cut goes INTO material. Surface a `notes`
            # entry in the response so callers see what got auto-decided.
            # Auto-flip oppositeDirection on REMOVE+faceId. Earlier the check
            # gated on `"oppositeDirection" in arguments` — but MCP clients
            # fill schema defaults before dispatch, so `{oppositeDirection:
            # false}` could arrive even when the LLM omitted the field. We
            # now treat None and absent the same, and auto-flip on REMOVE+
            # faceId unless the caller explicitly opts out via
            # `forceOppositeDirection` (rare override for cutting through
            # from underneath). The tool schema no longer declares a False
            # default so clean clients don't auto-fill.
            opp_raw = arguments.get("oppositeDirection")
            force_flag = arguments.get("forceOppositeDirection")  # explicit override
            opp = bool(opp_raw) if opp_raw is not None else False
            notes: list[str] = []
            if op_type == ExtrudeType.REMOVE and force_flag is None:
                on_face = await _sketch_is_on_face(
                    arguments["documentId"],
                    arguments["workspaceId"],
                    arguments["elementId"],
                    arguments["sketchFeatureId"],
                )
                if on_face:
                    opp = True
                    notes.append(
                        "auto-set oppositeDirection=true because this REMOVE "
                        "extrude is sketched on a picked face — cutting INTO "
                        "the material, not out into air. Pass "
                        "`forceOppositeDirection: false` to override and "
                        "extrude away from the face (e.g. cutting through "
                        "from underneath)."
                    )
            elif force_flag is not None:
                opp = bool(force_flag)
                notes.append(
                    f"forceOppositeDirection={bool(force_flag)} honored explicitly; "
                    "auto-detect skipped. Only use this when you need the non-default "
                    "direction on a REMOVE-on-face cut."
                )

            extrude = ExtrudeBuilder(
                name=arguments.get("name", "Extrude"),
                sketch_feature_id=arguments["sketchFeatureId"],
                operation_type=op_type,
                opposite_direction=opp,
                end_type=end_type,
            )
            extrude.set_depth(arguments["depth"], variable_name=arguments.get("variableDepth"))

            result = await apply_feature_and_check(
                client,
                arguments["documentId"],
                arguments["workspaceId"],
                arguments["elementId"],
                extrude.build(),
                track_changes=bool(arguments.get("trackChanges", True)),
            )
            return [TextContent(type="text", text=_feature_apply_json(
                result, tool_name=name, notes=notes,
            ))]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error creating extrude: {e.response.status_code} - {e.response.text[:500]}")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating extrude")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_thicken":
        try:
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

            # ThickenBuilder returns a bare feature dict; wrap it in {"feature": ...}
            # so apply_feature_and_check POSTs the expected envelope.
            result = await apply_feature_and_check(
                client,
                arguments["documentId"],
                arguments["workspaceId"],
                arguments["elementId"],
                {"feature": thicken.build()},
                track_changes=bool(arguments.get("trackChanges", True)),
            )
            return [TextContent(type="text", text=_feature_apply_json(result, tool_name=name))]
        except KeyError:
            return [TextContent(type="text", text=_exception_json(
                ValueError("Invalid operationType; must be NEW | ADD | REMOVE | INTERSECT"),
                tool_name=name,
            ))]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error creating thicken: {e.response.status_code} - {e.response.text[:500]}")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating thicken")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

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

    elif name == "create_variable_studio":
        try:
            vs_eid = await variable_manager.create_variable_studio(
                arguments["documentId"],
                arguments["workspaceId"],
                arguments["name"],
            )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Created Variable Studio '{arguments['name']}'\n"
                        f"Element ID: {vs_eid}\n"
                        f"Use this ID as elementId for set_variable and get_variables."
                    ),
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(
                f"API error creating Variable Studio: {e.response.status_code} - {e.response.text[:500]}"
            )
            return [
                TextContent(
                    type="text",
                    text=f"Error creating Variable Studio: API returned {e.response.status_code}.",
                )
            ]
        except Exception as e:
            logger.exception("Unexpected error creating Variable Studio")
            return [
                TextContent(
                    type="text",
                    text=f"Error creating Variable Studio: {str(e)}",
                )
            ]

    elif name == "set_variable":
        try:
            await variable_manager.set_variable(
                arguments["documentId"],
                arguments["workspaceId"],
                arguments["elementId"],
                arguments["name"],
                arguments["expression"],
                arguments.get("description"),
                arguments.get("type", "LENGTH"),
            )

            return [
                TextContent(
                    type="text",
                    text=(
                        f"Set variable '{arguments['name']}' = {arguments['expression']} "
                        f"({arguments.get('type', 'LENGTH')}) in Variable Studio "
                        f"{arguments['elementId']}"
                    ),
                )
            ]
        except httpx.HTTPStatusError as e:
            logger.error(
                f"API error setting variable: {e.response.status_code} - {e.response.text[:500]}"
            )
            hint = ""
            if e.response.status_code == 404:
                hint = (
                    " 404 usually means elementId is a Part Studio, not a "
                    "Variable Studio -- call create_variable_studio first."
                )
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Error setting variable: API returned {e.response.status_code}. "
                        f"Check the variable expression format (e.g., '0.75 in').{hint}"
                    ),
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
            element_type = arguments.get("elementType", "PARTSTUDIO")
            if element_type == "ASSEMBLY":
                await assembly_manager.delete_feature(
                    arguments["documentId"], arguments["workspaceId"], arguments["elementId"], arguments["featureId"],
                )
            else:
                await partstudio_manager.delete_feature(
                    arguments["documentId"], arguments["workspaceId"], arguments["elementId"], arguments["featureId"],
                )
            # Delete has no featureStatus to report, but we use the same
            # contract shape as the mutating handlers so LLM callers don't
            # have to branch on whether the response is text vs JSON.
            payload = {
                "ok": True,
                "status": "OK",
                "feature_id": arguments["featureId"],
                "feature_type": element_type.lower(),
                "feature_name": "",
                "error_message": None,
                "tool": name,
            }
            return [TextContent(type="text", text=json.dumps(payload, indent=2))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error deleting feature")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "delete_feature_by_name":
        try:
            target_name = arguments["name"]
            features_doc = await partstudio_manager.get_features(
                arguments["documentId"],
                arguments["workspaceId"],
                arguments["elementId"],
            )
            features = features_doc.get("features") or []
            matches = [
                f for f in features
                if f.get("name") == target_name and f.get("featureId")
            ]
            if not matches:
                available = sorted({f.get("name", "") for f in features if f.get("name")})
                return [TextContent(type="text", text=_exception_json(
                    ValueError(
                        f"No feature named {target_name!r} in this element. "
                        f"Available names: {available}"
                    ),
                    tool_name=name,
                ))]
            if len(matches) > 1:
                ids = [f.get("featureId") for f in matches]
                return [TextContent(type="text", text=_exception_json(
                    ValueError(
                        f"{len(matches)} features named {target_name!r}; "
                        f"cannot disambiguate. Use delete_feature with a "
                        f"specific featureId. Matching ids: {ids}"
                    ),
                    tool_name=name,
                ))]
            deleted = matches[0]
            deleted_fid = deleted["featureId"]
            await partstudio_manager.delete_feature(
                arguments["documentId"],
                arguments["workspaceId"],
                arguments["elementId"],
                deleted_fid,
            )
            payload = {
                "ok": True,
                "status": "OK",
                "feature_id": deleted_fid,
                "feature_type": deleted.get("featureType") or deleted.get("btType", ""),
                "feature_name": target_name,
                "error_message": None,
                "tool": name,
            }
            return [TextContent(type="text", text=json.dumps(payload, indent=2))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error in delete_feature_by_name")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "update_feature":
        try:
            result = await update_feature_params_and_check(
                client,
                arguments["documentId"],
                arguments["workspaceId"],
                arguments["elementId"],
                arguments["featureId"],
                arguments["updates"],
            )
            return [TextContent(type="text", text=_feature_apply_json(result, tool_name=name))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error updating feature")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

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
                if "elementId" in instance:
                    inst_info += f"\n  Element ID: {instance['elementId']}"
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

    elif name == "delete_document":
        try:
            await document_manager.delete_document(arguments["documentId"])
            payload = {
                "ok": True,
                "status": "OK",
                "document_id": arguments["documentId"],
                "error_message": None,
                "tool": name,
            }
            return [TextContent(type="text", text=json.dumps(payload, indent=2))]
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            logger.error(f"API error deleting document: {status_code}")
            return [TextContent(type="text", text=json.dumps({
                "ok": False,
                "status": "EXCEPTION",
                "document_id": arguments["documentId"],
                "error_message": f"HTTP {status_code}: {e}",
                "tool": name,
            }, indent=2))]
        except Exception as e:
            logger.exception("Unexpected error deleting document")
            return [TextContent(type="text", text=json.dumps({
                "ok": False,
                "status": "EXCEPTION",
                "document_id": arguments["documentId"],
                "error_message": str(e),
                "tool": name,
            }, indent=2))]

    elif name == "create_part_studio":
        try:
            result = await partstudio_manager.create_part_studio(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                name=arguments["name"],
            )
            element_id = result.get("id", "unknown")

            # Enumerate every PartStudio now in the workspace and report
            # those OTHER than the one we just created. Most new Onshape
            # documents ship with an empty default "Part Studio 1"; a caller
            # that later uses find_part_studios or get_elements can pick the
            # empty default by accident and render nothing. Returning the
            # list up-front lets the caller either target the new id we
            # surface or clean up the default explicitly.
            other_part_studios: list[dict[str, str]] = []
            try:
                elements = await document_manager.find_part_studios(
                    arguments["documentId"], arguments["workspaceId"],
                )
                other_part_studios = [
                    {"id": e.id, "name": e.name}
                    for e in elements
                    if e.id and e.id != element_id
                ]
            except Exception as enum_err:  # noqa: BLE001
                logger.warning(
                    f"create_part_studio: failed to enumerate siblings: {enum_err}"
                )

            payload = {
                "ok": True,
                "status": "OK",
                "element_id": element_id,
                "element_name": arguments["name"],
                "other_part_studios": other_part_studios,
                "tool": name,
            }
            return [TextContent(type="text", text=json.dumps(payload, indent=2))]
        except httpx.HTTPStatusError as e:
            logger.error(f"API error creating Part Studio: {e.response.status_code}")
            return [TextContent(type="text", text=json.dumps({
                "ok": False,
                "status": "EXCEPTION",
                "element_id": "",
                "element_name": arguments.get("name", ""),
                "other_part_studios": [],
                "error_message": f"HTTP {e.response.status_code}: {e}",
                "tool": name,
            }, indent=2))]
        except Exception as e:
            logger.exception("Unexpected error creating Part Studio")
            return [TextContent(type="text", text=json.dumps({
                "ok": False,
                "status": "EXCEPTION",
                "element_id": "",
                "element_name": arguments.get("name", ""),
                "other_part_studios": [],
                "error_message": str(e),
                "tool": name,
            }, indent=2))]

    elif name == "create_assembly":
        try:
            result = await assembly_manager.create_assembly(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                name=arguments["name"],
            )
            element_id = result.get("id", "")
            payload = {
                "ok": bool(element_id),
                "status": "OK" if element_id else "UNKNOWN",
                "element_id": element_id,
                "element_name": arguments["name"],
                "error_message": None if element_id else "API did not return an element id",
                "tool": name,
            }
            return [TextContent(type="text", text=json.dumps(payload, indent=2))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating assembly")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "add_assembly_instance":
        try:
            # add_instance returns {} (Onshape quirk). Diff the instance list
            # pre/post to surface the new instance id so the caller doesn't
            # have to follow up with get_assembly.
            doc_id = arguments["documentId"]
            ws_id = arguments["workspaceId"]
            asm_eid = arguments["elementId"]
            before = await assembly_manager.get_assembly_definition(doc_id, ws_id, asm_eid)
            before_ids = {
                i.get("id") for i in before.get("rootAssembly", {}).get("instances", [])
            }
            await assembly_manager.add_instance(
                document_id=doc_id,
                workspace_id=ws_id,
                element_id=asm_eid,
                part_studio_element_id=arguments["partStudioElementId"],
                part_id=arguments.get("partId"),
                is_assembly=arguments.get("isAssembly", False),
            )
            after = await assembly_manager.get_assembly_definition(doc_id, ws_id, asm_eid)
            after_instances = after.get("rootAssembly", {}).get("instances", [])
            new_instances = [i for i in after_instances if i.get("id") not in before_ids]
            if new_instances:
                new_inst = new_instances[-1]
                instance_id = new_inst.get("id", "")
                instance_name = new_inst.get("name", "")
            else:
                instance_id, instance_name = "", ""
            payload = {
                "ok": bool(instance_id),
                "status": "OK" if instance_id else "UNKNOWN",
                "instance_id": instance_id,
                "instance_name": instance_name,
                "error_message": None if instance_id else "Could not diff-identify the new instance",
                "tool": name,
            }
            return [TextContent(type="text", text=json.dumps(payload, indent=2))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error adding instance")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

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
            payload = {
                "ok": True,
                "status": "OK",
                "instance_id": arguments["instanceId"],
                "error_message": None,
                "tool": name,
            }
            return [TextContent(type="text", text=json.dumps(payload, indent=2))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error transforming instance")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_fastened_mate":
        try:
            mate_result = await _create_mate(
                client,
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"],
                arguments["firstInstanceId"], arguments["secondInstanceId"],
                arguments["firstFaceId"], arguments["secondFaceId"],
                arguments.get("name", "Fastened mate"), MateType.FASTENED,
                first_offset=_extract_offsets(arguments, "first"),
                second_offset=_extract_offsets(arguments, "second"),
            )
            return [TextContent(type="text", text=_feature_apply_json(mate_result, tool_name=name))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating fastened mate")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_revolute_mate":
        try:
            mate_result = await _create_mate(
                client,
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"],
                arguments["firstInstanceId"], arguments["secondInstanceId"],
                arguments["firstFaceId"], arguments["secondFaceId"],
                arguments.get("name", "Revolute mate"), MateType.REVOLUTE,
                min_limit=arguments.get("minLimit"), max_limit=arguments.get("maxLimit"),
                first_offset=_extract_offsets(arguments, "first"),
                second_offset=_extract_offsets(arguments, "second"),
            )
            return [TextContent(type="text", text=_feature_apply_json(mate_result, tool_name=name))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating revolute mate")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_slider_mate":
        try:
            mate_result = await _create_mate(
                client,
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"],
                arguments["firstInstanceId"], arguments["secondInstanceId"],
                arguments["firstFaceId"], arguments["secondFaceId"],
                arguments.get("name", "Slider mate"), MateType.SLIDER,
                min_limit=arguments.get("minLimit"), max_limit=arguments.get("maxLimit"),
                first_offset=_extract_offsets(arguments, "first"),
                second_offset=_extract_offsets(arguments, "second"),
            )
            return [TextContent(type="text", text=_feature_apply_json(mate_result, tool_name=name))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating slider mate")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_cylindrical_mate":
        try:
            mate_result = await _create_mate(
                client,
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"],
                arguments["firstInstanceId"], arguments["secondInstanceId"],
                arguments["firstFaceId"], arguments["secondFaceId"],
                arguments.get("name", "Cylindrical mate"), MateType.CYLINDRICAL,
                min_limit=arguments.get("minLimit"), max_limit=arguments.get("maxLimit"),
                first_offset=_extract_offsets(arguments, "first"),
                second_offset=_extract_offsets(arguments, "second"),
            )
            return [TextContent(type="text", text=_feature_apply_json(mate_result, tool_name=name))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating cylindrical mate")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_mate_connector":
        try:
            mc = MateConnectorBuilder(
                name=arguments.get("name", "Mate connector"),
                face_id=arguments["faceId"],
                occurrence_path=[arguments["instanceId"]],
            )
            if arguments.get("flipPrimary"):
                mc.set_flip_primary(True)
            secondary = arguments.get("secondaryAxisType")
            if secondary and secondary != "PLUS_X":
                mc.set_secondary_axis(secondary)
            ox = arguments.get("offsetX", 0)
            oy = arguments.get("offsetY", 0)
            oz = arguments.get("offsetZ", 0)
            if ox != 0 or oy != 0 or oz != 0:
                mc.set_translation(ox, oy, oz)
            mc_result = await apply_assembly_feature_and_check(
                client,
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"],
                mc.build(),
            )
            return [TextContent(type="text", text=_feature_apply_json(mc_result, tool_name=name))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating mate connector")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_sketch_circle":
        try:
            plane_id, plane, warnings = await _resolve_sketch_plane_id(arguments)
            sketch = SketchBuilder(name=arguments.get("name", "Sketch"), plane=plane, plane_id=plane_id)
            # Accept either center=[x,y] (matches create_sketch_rectangle's
            # array-of-numbers convention) or centerX/centerY (legacy schema).
            # LLMs reliably mix these up when calling blind; support both.
            if "center" in arguments and arguments["center"] is not None:
                cx, cy = arguments["center"][0], arguments["center"][1]
            else:
                cx = arguments.get("centerX", 0)
                cy = arguments.get("centerY", 0)
            var_center_arg = arguments.get("variableCenter")
            var_center = (
                (var_center_arg[0], var_center_arg[1])
                if isinstance(var_center_arg, (list, tuple)) and len(var_center_arg) == 2
                else None
            )
            sketch.add_circle(
                center=(cx, cy),
                radius=arguments["radius"],
                variable_radius=arguments.get("variableRadius"),
                variable_center=var_center,
            )
            result = await apply_feature_and_check(
                client,
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"],
                sketch.build(),
            )
            return [TextContent(type="text", text=_feature_apply_json(result, tool_name=name, warnings=warnings))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating sketch circle")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_sketch_line":
        try:
            plane_id, plane, warnings = await _resolve_sketch_plane_id(arguments)
            sketch = SketchBuilder(name=arguments.get("name", "Sketch"), plane=plane, plane_id=plane_id)
            sketch.add_line(
                start=tuple(arguments["startPoint"]),
                end=tuple(arguments["endPoint"]),
            )
            result = await apply_feature_and_check(
                client,
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"],
                sketch.build(),
            )
            return [TextContent(type="text", text=_feature_apply_json(result, tool_name=name, warnings=warnings))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating sketch line")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_sketch_arc":
        try:
            plane_id, plane, warnings = await _resolve_sketch_plane_id(arguments)
            sketch = SketchBuilder(name=arguments.get("name", "Sketch"), plane=plane, plane_id=plane_id)
            # Accept center=[x,y] (preferred, matches rectangle) or legacy centerX/centerY.
            if "center" in arguments and arguments["center"] is not None:
                cx, cy = arguments["center"][0], arguments["center"][1]
            else:
                cx = arguments.get("centerX", 0)
                cy = arguments.get("centerY", 0)
            var_center_arg = arguments.get("variableCenter")
            var_center = (
                (var_center_arg[0], var_center_arg[1])
                if isinstance(var_center_arg, (list, tuple)) and len(var_center_arg) == 2
                else None
            )
            sketch.add_arc(
                center=(cx, cy),
                radius=arguments["radius"],
                start_angle=arguments.get("startAngle", 0),
                end_angle=arguments.get("endAngle", 180),
                variable_radius=arguments.get("variableRadius"),
                variable_center=var_center,
            )
            result = await apply_feature_and_check(
                client,
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"],
                sketch.build(),
            )
            return [TextContent(type="text", text=_feature_apply_json(result, tool_name=name, warnings=warnings))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating sketch arc")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_sketch":
        try:
            plane_id, plane, warnings = await _resolve_sketch_plane_id(arguments)
            sketch = SketchBuilder(
                name=arguments.get("name", "Sketch"), plane=plane, plane_id=plane_id
            )

            entities = arguments.get("entities") or []
            if not entities:
                raise ValueError("`entities` must be a non-empty list")

            for i, ent in enumerate(entities):
                if not isinstance(ent, dict):
                    raise ValueError(f"entities[{i}] must be an object, got {type(ent).__name__}")
                etype = (ent.get("type") or "").lower()
                if etype == "rectangle":
                    sketch.add_rectangle(
                        corner1=tuple(ent["corner1"]),
                        corner2=tuple(ent["corner2"]),
                        variable_width=ent.get("variableWidth"),
                        variable_height=ent.get("variableHeight"),
                    )
                elif etype == "rounded_rectangle":
                    sketch.add_rounded_rectangle(
                        corner1=tuple(ent["corner1"]),
                        corner2=tuple(ent["corner2"]),
                        corner_radius=ent["cornerRadius"],
                    )
                elif etype == "circle":
                    var_center = ent.get("variableCenter")
                    var_center_tuple = (
                        (var_center[0], var_center[1])
                        if isinstance(var_center, (list, tuple)) and len(var_center) == 2
                        else None
                    )
                    sketch.add_circle(
                        center=tuple(ent["center"]),
                        radius=ent["radius"],
                        variable_radius=ent.get("variableRadius"),
                        variable_center=var_center_tuple,
                    )
                elif etype == "line":
                    sketch.add_line(
                        start=tuple(ent["start"]),
                        end=tuple(ent["end"]),
                    )
                elif etype == "arc":
                    var_center = ent.get("variableCenter")
                    var_center_tuple = (
                        (var_center[0], var_center[1])
                        if isinstance(var_center, (list, tuple)) and len(var_center) == 2
                        else None
                    )
                    sketch.add_arc(
                        center=tuple(ent["center"]),
                        radius=ent["radius"],
                        start_angle=ent.get("startAngle", 0),
                        end_angle=ent.get("endAngle", 180),
                        variable_radius=ent.get("variableRadius"),
                        variable_center=var_center_tuple,
                    )
                else:
                    raise ValueError(
                        f"entities[{i}].type must be rectangle | rounded_rectangle | circle | line | arc, "
                        f"got {ent.get('type')!r}"
                    )

            result = await apply_feature_and_check(
                client,
                arguments["documentId"],
                arguments["workspaceId"],
                arguments["elementId"],
                sketch.build(),
            )
            return [TextContent(type="text", text=_feature_apply_json(result, tool_name=name, warnings=warnings))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating multi-entity sketch")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_fillet":
        try:
            fillet = FilletBuilder(name=arguments.get("name", "Fillet"), radius=arguments["radius"])
            for edge_id in arguments["edgeIds"]:
                fillet.add_edge(edge_id)
            if arguments.get("variableRadius"):
                fillet.set_radius(arguments["radius"], variable_name=arguments["variableRadius"])
            result = await apply_feature_and_check(
                client,
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"],
                fillet.build(),
                track_changes=bool(arguments.get("trackChanges", True)),
            )
            return [TextContent(type="text", text=_feature_apply_json(result, tool_name=name))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating fillet")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_chamfer":
        try:
            chamfer_type = ChamferType[arguments.get("chamferType", "EQUAL_OFFSETS")]
            chamfer = ChamferBuilder(name=arguments.get("name", "Chamfer"), distance=arguments["distance"], chamfer_type=chamfer_type)
            for edge_id in arguments["edgeIds"]:
                chamfer.add_edge(edge_id)
            if arguments.get("variableDistance"):
                chamfer.set_distance(arguments["distance"], variable_name=arguments["variableDistance"])
            result = await apply_feature_and_check(
                client,
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"],
                chamfer.build(),
                track_changes=bool(arguments.get("trackChanges", True)),
            )
            return [TextContent(type="text", text=_feature_apply_json(result, tool_name=name))]
        except KeyError:
            return [TextContent(type="text", text=_exception_json(
                ValueError("Invalid chamferType; must be EQUAL_OFFSETS | TWO_OFFSETS | OFFSET_ANGLE"),
                tool_name=name,
            ))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating chamfer")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

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
            result = await apply_feature_and_check(
                client,
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"],
                revolve.build(),
                track_changes=bool(arguments.get("trackChanges", True)),
            )
            return [TextContent(type="text", text=_feature_apply_json(result, tool_name=name))]
        except KeyError:
            return [TextContent(type="text", text=_exception_json(
                ValueError("Invalid operationType; must be NEW | ADD | REMOVE | INTERSECT"),
                tool_name=name,
            ))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating revolve")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_linear_pattern":
        try:
            pattern = LinearPatternBuilder(
                name=arguments.get("name", "Linear pattern"),
                distance=arguments["distance"],
                count=arguments.get("count", 2),
                direction_edge_id=arguments["directionEdgeId"],
            )
            for fid in arguments["featureIds"]:
                pattern.add_feature(fid)
            # Legacy `direction` axis still accepted but ignored in favor of the
            # real edge reference; pattern.set_direction is a no-op at build time
            # once direction_edge_id is set.
            if arguments.get("direction"):
                pattern.set_direction(arguments["direction"])
            result = await apply_feature_and_check(
                client,
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"],
                pattern.build(),
                track_changes=bool(arguments.get("trackChanges", True)),
            )
            return [TextContent(type="text", text=_feature_apply_json(result, tool_name=name))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating linear pattern")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

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
            result = await apply_feature_and_check(
                client,
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"],
                pattern.build(),
                track_changes=bool(arguments.get("trackChanges", True)),
            )
            return [TextContent(type="text", text=_feature_apply_json(result, tool_name=name))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating circular pattern")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "create_boolean":
        try:
            bool_type = BooleanType[arguments["booleanType"]]
            boolean = BooleanBuilder(name=arguments.get("name", "Boolean"), boolean_type=bool_type)
            for body_id in arguments["toolBodyIds"]:
                boolean.add_tool_body(body_id)
            for body_id in arguments.get("targetBodyIds", []):
                boolean.add_target_body(body_id)
            result = await apply_feature_and_check(
                client,
                arguments["documentId"], arguments["workspaceId"], arguments["elementId"],
                boolean.build(),
                track_changes=bool(arguments.get("trackChanges", True)),
            )
            return [TextContent(type="text", text=_feature_apply_json(result, tool_name=name))]
        except KeyError:
            return [TextContent(type="text", text=_exception_json(
                ValueError("Invalid booleanType; must be UNION | SUBTRACT | INTERSECT"),
                tool_name=name,
            ))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error creating boolean")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "eval_featurescript":
        try:
            result = await featurescript_manager.evaluate(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                script=arguments["script"],
            )
            # Surface parser/runtime notices upfront. The full result tree
            # (BTFSValueMap-wrapped) is the primary payload but notices live
            # at the top of the response and were getting visually buried
            # mid-debug -- per the agent-SDK FS-frontier transcripts the
            # actual diagnostic was already on the wire and just being
            # ignored. See fs_notices.format_notices.
            from onshape_mcp.api.fs_notices import format_notices
            notices = result.get("notices") if isinstance(result, dict) else None
            prefix = ""
            if notices:
                rendered = format_notices(notices)
                if rendered:
                    prefix = f"NOTICES ({len(notices)}):\n{rendered}\n\n"
            return [TextContent(
                type="text",
                text=f"{prefix}FeatureScript result:\n{json.dumps(result, indent=2)}",
            )]
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
            return [TextContent(type="text", text=f"Bounding box:\n{json.dumps(result, indent=2)}")]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error getting bounding box: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error getting bounding box: {str(e)}")]

    elif name == "export_part_studio":
        try:
            result = await export_manager.export_part_studio_and_download(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                format_name=arguments.get("format", "STL"),
                part_id=arguments.get("partId"),
                timeout_seconds=float(arguments.get("timeoutSeconds", 120)),
                poll_interval_seconds=float(arguments.get("pollIntervalSeconds", 1.0)),
            )
            return [
                TextContent(
                    type="text",
                    text=_format_export_result(result, arguments["elementId"]),
                )
            ]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error exporting: API returned {e.response.status_code}.")]
        except Exception as e:
            logger.exception("Unexpected error exporting Part Studio")
            return [TextContent(type="text", text=f"Error exporting: {str(e)}")]

    elif name == "export_assembly":
        try:
            result = await export_manager.export_assembly_and_download(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                format_name=arguments.get("format", "STL"),
                timeout_seconds=float(arguments.get("timeoutSeconds", 120)),
                poll_interval_seconds=float(arguments.get("pollIntervalSeconds", 1.0)),
            )
            return [
                TextContent(
                    type="text",
                    text=_format_export_result(result, arguments["elementId"]),
                )
            ]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error exporting: API returned {e.response.status_code}.")]
        except Exception as e:
            logger.exception("Unexpected error exporting Assembly")
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
            msg, (x_mm, y_mm, z_mm) = await set_absolute_position(
                assembly_manager=assembly_manager,
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                instance_id=arguments["instanceId"],
                x=arguments["x"],
                y=arguments["y"],
                z=arguments["z"],
            )
            payload = {
                "ok": True,
                "status": "OK",
                "instance_id": arguments["instanceId"],
                "position_mm": {"x": x_mm, "y": y_mm, "z": z_mm},
                "message": msg,
                "error_message": None,
                "tool": name,
            }
            return [TextContent(type="text", text=json.dumps(payload, indent=2))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("Unexpected error setting instance position")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

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
            payload = {
                "ok": True,
                "status": "OK",
                "source_instance_id": arguments["sourceInstanceId"],
                "target_instance_id": arguments["targetInstanceId"],
                "face": arguments["face"],
                "message": msg,
                "error_message": None,
                "tool": name,
            }
            return [TextContent(type="text", text=json.dumps(payload, indent=2))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except ValueError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]
        except Exception as e:
            logger.exception("Unexpected error aligning instance")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

    elif name == "get_body_details":
        try:
            result = await partstudio_manager.get_body_details(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
            )

            bodies = result.get("bodies", [])
            if not bodies:
                return [TextContent(type="text", text="No bodies found in Part Studio.")]

            output_parts = []
            for body in bodies:
                body_id = body.get("id", "N/A")
                body_type = body.get("type", "N/A")

                faces = body.get("faces", [])

                # Collect planar face data for enrichment
                planar_data = []
                for face in faces:
                    surface = face.get("surface", {})
                    if surface.get("type", "").lower() == "plane":
                        normal = surface.get("normal", {})
                        origin = surface.get("origin", {})
                        planar_data.append({
                            "id": face.get("id", "N/A"),
                            "nx": normal.get("x", 0),
                            "ny": normal.get("y", 0),
                            "nz": normal.get("z", 0),
                            "ox": origin.get("x", 0),
                            "oy": origin.get("y", 0),
                            "oz": origin.get("z", 0),
                        })

                enriched = _enrich_rectangular_body(planar_data)

                if enriched:
                    dims = enriched["dimensions"]
                    part_header = f"**Body: {body_id}** (type: {body_type})"
                    part_header += f"\n  Bounding box: {dims[0]:.3f}\" x {dims[1]:.3f}\" x {dims[2]:.3f}\" (X x Y x Z)"

                    faces_info = []
                    for face in faces:
                        face_id = face.get("id", "N/A")
                        surface = face.get("surface", {})
                        surface_type = surface.get("type", "unknown")

                        if face_id in enriched["faces"]:
                            ef = enriched["faces"][face_id]
                            face_line = f"  Face `{face_id}`: {surface_type}"
                            face_line += f" | {ef['label']} face"
                            face_line += f" | {ef['width']:.2f}\" x {ef['height']:.2f}\""
                            face_line += f" | outward normal={ef['outward_normal']}"
                        else:
                            face_line = f"  Face `{face_id}`: {surface_type}"

                        faces_info.append(face_line)

                    faces_info.append("")
                    faces_info.append(
                        "  MC axes: Z=outward normal, X=world+X (for Y/Z faces). "
                        "offsetZ>0 moves AWAY from body, <0 moves INTO body."
                    )

                    output_parts.append(part_header + "\n" + "\n".join(faces_info))
                else:
                    # Fallback to original format for non-rectangular bodies
                    part_header = f"**Body: {body_id}** (type: {body_type})"
                    faces_info = []
                    for face in faces:
                        face_id = face.get("id", "N/A")
                        surface = face.get("surface", {})
                        surface_type = surface.get("type", "unknown")
                        face_line = f"  Face `{face_id}`: {surface_type}"
                        stype_lower = surface_type.lower()
                        if stype_lower == "plane":
                            normal = surface.get("normal", {})
                            origin = surface.get("origin", {})
                            nx = normal.get("x", 0)
                            ny = normal.get("y", 0)
                            nz = normal.get("z", 0)
                            ox = origin.get("x", 0)
                            oy = origin.get("y", 0)
                            oz = origin.get("z", 0)
                            face_line += f" | normal=({nx:.4f}, {ny:.4f}, {nz:.4f})"
                            face_line += f" | origin=({ox:.6f}, {oy:.6f}, {oz:.6f})m"
                        elif stype_lower == "cylinder":
                            radius = surface.get("radius", 0)
                            face_line += f" | radius={radius:.6f}m"
                        faces_info.append(face_line)
                    output_parts.append(part_header + "\n" + "\n".join(faces_info))

            return [
                TextContent(
                    type="text",
                    text=f"Body Details ({len(bodies)} bodies):\n\n" + "\n\n".join(output_parts),
                )
            ]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error getting body details: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error getting body details: {str(e)}")]

    elif name == "get_assembly_features":
        try:
            result = await assembly_manager.get_features(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
            )

            features = result.get("features", [])
            feature_states = result.get("featureStates", {})

            if not features:
                return [TextContent(type="text", text="No features found in assembly.")]

            feature_lines = []
            for i, feat in enumerate(features, 1):
                feat_type = feat.get("typeName", feat.get("btType", "unknown"))
                feat_id = feat.get("featureId", "N/A")
                feat_name = feat.get("name", "Unnamed")
                state_info = feature_states.get(feat_id, {})
                state = state_info.get("featureStatus", "UNKNOWN")

                line = f"{i}. **{feat_name}** ({feat_type})"
                line += f"\n   ID: `{feat_id}` | State: {state}"

                # For mates, show mate type
                if feat_type == "mate" or feat.get("btType") == "BTMMate-64":
                    params = feat.get("parameters", [])
                    for p in params:
                        if p.get("parameterId") == "mateType":
                            line += f" | Type: {p.get('value', 'N/A')}"
                            break

                feature_lines.append(line)

            return [
                TextContent(
                    type="text",
                    text=f"Assembly Features ({len(features)}):\n\n" + "\n\n".join(feature_lines),
                )
            ]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error getting assembly features: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error getting assembly features: {str(e)}")]

    elif name == "get_face_coordinate_system":
        try:
            from .analysis.face_cs import query_face_coordinate_system

            cs = await query_face_coordinate_system(
                assembly_manager=assembly_manager,
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                instance_id=arguments["instanceId"],
                face_id=arguments["faceId"],
            )

            ox, oy, oz = cs.origin_inches
            zx, zy, zz = cs.z_axis
            xx, xy, xz = cs.x_axis
            yx, yy, yz = cs.y_axis

            text = (
                f"Face `{arguments['faceId']}` coordinate system on instance `{arguments['instanceId']}`:\n\n"
                f"  Origin: ({ox:.4f}, {oy:.4f}, {oz:.4f}) inches\n"
                f"  Z-axis (outward normal): ({zx:.6f}, {zy:.6f}, {zz:.6f})\n"
                f"  X-axis: ({xx:.6f}, {xy:.6f}, {xz:.6f})\n"
                f"  Y-axis: ({yx:.6f}, {yy:.6f}, {yz:.6f})"
            )
            return [TextContent(type="text", text=text)]
        except RuntimeError as e:
            return [TextContent(type="text", text=f"Error querying face CS: {str(e)}")]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"Error querying face CS: API returned {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error querying face CS: {str(e)}")]

    # === Visual / Rendering Tools (added by dyna-fork) ===
    elif name in ("render_part_studio_views", "render_assembly_views"):
        try:
            render_fn = (
                shaded_view_manager.render_part_studio_views
                if name == "render_part_studio_views"
                else shaded_view_manager.render_assembly_views
            )
            rendered = await render_fn(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                views=arguments.get("views") or None,
                width=int(arguments.get("width", 1200)),
                height=int(arguments.get("height", 800)),
                edges=bool(arguments.get("edges", True)),
            )
            out: list[TextContent | ImageContent] = [
                TextContent(
                    type="text",
                    text=(
                        f"Rendered {len(rendered)} view(s). image_ids can be passed to "
                        "crop_image. "
                        + ", ".join(
                            f"{r.view}={r.image_id} ({r.width}x{r.height}, {r.bytes}B)"
                            for r in rendered
                        )
                    ),
                )
            ]
            for r in rendered:
                png = get_image(r.image_id)
                out.append(
                    ImageContent(
                        type="image",
                        data=base64.b64encode(png).decode("ascii"),
                        mimeType="image/png",
                    )
                )
            return out
        except httpx.HTTPStatusError as e:
            body = ""
            try:
                body = e.response.text[:400]
            except Exception:
                pass
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Render failed: HTTP {e.response.status_code} on /shadedviews. "
                        f"Body: {body}"
                    ),
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"Render failed: {e}")]

    elif name == "crop_image":
        try:
            rv = crop_cached_image(
                image_id=arguments["imageId"],
                x1=arguments["x1"],
                y1=arguments["y1"],
                x2=arguments["x2"],
                y2=arguments["y2"],
            )
            png = get_image(rv.image_id)
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Cropped {arguments['imageId']} to "
                        f"({arguments['x1']:.3f},{arguments['y1']:.3f})-"
                        f"({arguments['x2']:.3f},{arguments['y2']:.3f}): "
                        f"{rv.width}x{rv.height}px. New image_id: {rv.image_id}"
                    ),
                ),
                ImageContent(
                    type="image",
                    data=base64.b64encode(png).decode("ascii"),
                    mimeType="image/png",
                ),
            ]
        except KeyError:
            return [
                TextContent(
                    type="text",
                    text=f"crop_image: image_id '{arguments.get('imageId')}' not in cache. Call list_cached_images to see what's available.",
                )
            ]
        except ValueError as e:
            return [TextContent(type="text", text=f"crop_image: {e}")]
        except Exception as e:
            return [TextContent(type="text", text=f"crop_image failed: {e}")]

    elif name == "list_entities":
        try:
            result = await entity_manager.list_entities(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                kinds=arguments.get("kinds") or None,
                body_index=arguments.get("bodyIndex"),
                geometry_type=arguments.get("geometryType"),
                outward_axis=arguments.get("outwardAxis"),
                at_z_mm=arguments.get("atZmm"),
                at_z_tol_mm=arguments.get("atZtolMm", 0.5),
                radius_range_mm=arguments.get("radiusRangeMm"),
                length_range_mm=arguments.get("lengthRangeMm"),
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
        except ValueError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]
        except httpx.HTTPStatusError as e:
            return [
                TextContent(
                    type="text",
                    text=f"list_entities failed: HTTP {e.response.status_code} on /bodydetails.",
                )
            ]
        except Exception as e:
            return [TextContent(type="text", text=f"list_entities failed: {e}")]

    elif name == "describe_part_studio":
        try:
            snap = await describe_manager.describe_part_studio(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                views=arguments.get("views") or None,
                render_width=int(arguments.get("renderWidth", 1200)),
                render_height=int(arguments.get("renderHeight", 800)),
            )
            out: list[TextContent | ImageContent] = [
                TextContent(type="text", text=snap.structured_text)
            ]
            for r in snap.views:
                png = get_image(r.image_id)
                out.append(
                    ImageContent(
                        type="image",
                        data=base64.b64encode(png).decode("ascii"),
                        mimeType="image/png",
                    )
                )
            return out
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"describe_part_studio failed: HTTP {e.response.status_code}.")]
        except Exception as e:
            logger.exception("describe_part_studio failed")
            return [TextContent(type="text", text=f"describe_part_studio failed: {e}")]

    elif name == "measure":
        try:
            result = await measurement_manager.measure(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                element_id=arguments["elementId"],
                entity_a_id=arguments["entityAId"],
                entity_b_id=arguments["entityBId"],
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"measure failed: HTTP {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"measure failed: {e}")]

    elif name == "get_mass_properties":
        try:
            if arguments.get("partId"):
                result = await measurement_manager.mass_properties_part(
                    document_id=arguments["documentId"],
                    workspace_id=arguments["workspaceId"],
                    element_id=arguments["elementId"],
                    part_id=arguments["partId"],
                )
            else:
                result = await measurement_manager.mass_properties_part_studio(
                    document_id=arguments["documentId"],
                    workspace_id=arguments["workspaceId"],
                    element_id=arguments["elementId"],
                )
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=f"get_mass_properties failed: HTTP {e.response.status_code}.")]
        except Exception as e:
            return [TextContent(type="text", text=f"get_mass_properties failed: {e}")]

    elif name == "list_cached_images":
        entries = list_cached_image_ids()
        if not entries:
            return [TextContent(type="text", text="No images cached yet. Call render_part_studio_views or render_assembly_views first.")]
        lines = [f"{len(entries)} image(s) in cache:"]
        for e in entries:
            view = e.get("view", "?")
            src = e.get("source", {})
            dims = f"{e.get('width', '?')}x{e.get('height', '?')}"
            crop_of = e.get("crop_of")
            crop_note = f" (crop of {crop_of} bbox={e.get('crop_bbox')})" if crop_of else ""
            lines.append(
                f"  - {e['image_id']}: view={view} source={src.get('kind','?')}:{src.get('eid','?')} {dims} {e['bytes']}B{crop_note}"
            )
        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "write_featurescript_feature":
        try:
            out = await custom_feature_manager.apply_featurescript_feature(
                document_id=arguments["documentId"],
                workspace_id=arguments["workspaceId"],
                part_studio_element_id=arguments["elementId"],
                feature_type=arguments["featureType"],
                feature_script=arguments["featureScript"],
                feature_name=arguments["featureName"],
                parameters=arguments.get("parameters"),
                fs_element_name=arguments.get("fsElementName"),
            )
            apply = out["apply_result"]
            payload = {
                "ok": apply.ok,
                "status": apply.status,
                "feature_id": apply.feature_id,
                "feature_type": apply.feature_type,
                "feature_name": apply.feature_name,
                "error_message": apply.error_message,
                "fs_element_id": out["fs_element_id"],
                "source_microversion_id": out.get("source_microversion_id"),
                "tool": "write_featurescript_feature",
            }
            return [TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]
        except httpx.HTTPStatusError as e:
            return [TextContent(type="text", text=_exception_json(e, tool_name=name, status_code=e.response.status_code))]
        except Exception as e:
            logger.exception("write_featurescript_feature failed")
            return [TextContent(type="text", text=_exception_json(e, tool_name=name))]

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
