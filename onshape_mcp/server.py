"""Main MCP server for Onshape integration."""

import os
import asyncio
from typing import Any
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .api.client import OnshapeClient, OnshapeCredentials
from .api.partstudio import PartStudioManager
from .api.variables import VariableManager
from .builders.sketch import SketchBuilder, SketchPlane
from .builders.extrude import ExtrudeBuilder, ExtrudeType


# Initialize server
app = Server("onshape-mcp")

# Initialize Onshape client
credentials = OnshapeCredentials(
    access_key=os.getenv("ONSHAPE_ACCESS_KEY", ""),
    secret_key=os.getenv("ONSHAPE_SECRET_KEY", "")
)
client = OnshapeClient(credentials)
partstudio_manager = PartStudioManager(client)
variable_manager = VariableManager(client)


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
                        "default": "Front"
                    },
                    "corner1": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "First corner [x, y] in inches"
                    },
                    "corner2": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "Second corner [x, y] in inches"
                    },
                    "variableWidth": {
                        "type": "string",
                        "description": "Optional variable name for width"
                    },
                    "variableHeight": {
                        "type": "string",
                        "description": "Optional variable name for height"
                    }
                },
                "required": ["documentId", "workspaceId", "elementId", "corner1", "corner2"]
            }
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
                    "variableDepth": {"type": "string", "description": "Optional variable name for depth"},
                    "operationType": {
                        "type": "string",
                        "enum": ["NEW", "ADD", "REMOVE", "INTERSECT"],
                        "description": "Extrude operation type",
                        "default": "NEW"
                    }
                },
                "required": ["documentId", "workspaceId", "elementId", "sketchFeatureId", "depth"]
            }
        ),
        Tool(
            name="get_variables",
            description="Get all variables from a Part Studio variable table",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"}
                },
                "required": ["documentId", "workspaceId", "elementId"]
            }
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
                    "expression": {"type": "string", "description": "Variable expression (e.g., '0.75 in')"},
                    "description": {"type": "string", "description": "Optional variable description"}
                },
                "required": ["documentId", "workspaceId", "elementId", "name", "expression"]
            }
        ),
        Tool(
            name="get_features",
            description="Get all features from a Part Studio",
            inputSchema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string", "description": "Document ID"},
                    "workspaceId": {"type": "string", "description": "Workspace ID"},
                    "elementId": {"type": "string", "description": "Part Studio element ID"}
                },
                "required": ["documentId", "workspaceId", "elementId"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""

    if name == "create_sketch_rectangle":
        # Build sketch with rectangle
        plane = SketchPlane[arguments.get("plane", "Front").upper()]
        sketch = SketchBuilder(
            name=arguments.get("name", "Sketch"),
            plane=plane
        )

        sketch.add_rectangle(
            corner1=tuple(arguments["corner1"]),
            corner2=tuple(arguments["corner2"]),
            variable_width=arguments.get("variableWidth"),
            variable_height=arguments.get("variableHeight")
        )

        # Add feature to Part Studio
        feature_data = sketch.build()
        result = await partstudio_manager.add_feature(
            arguments["documentId"],
            arguments["workspaceId"],
            arguments["elementId"],
            feature_data
        )

        return [TextContent(
            type="text",
            text=f"Created sketch '{arguments.get('name', 'Sketch')}' with rectangle. Feature ID: {result.get('featureId', 'unknown')}"
        )]

    elif name == "create_extrude":
        # Build extrude
        op_type = ExtrudeType[arguments.get("operationType", "NEW")]
        extrude = ExtrudeBuilder(
            name=arguments.get("name", "Extrude"),
            sketch_feature_id=arguments["sketchFeatureId"],
            operation_type=op_type
        )

        extrude.set_depth(
            arguments["depth"],
            variable_name=arguments.get("variableDepth")
        )

        # Add feature to Part Studio
        feature_data = extrude.build()
        result = await partstudio_manager.add_feature(
            arguments["documentId"],
            arguments["workspaceId"],
            arguments["elementId"],
            feature_data
        )

        return [TextContent(
            type="text",
            text=f"Created extrude '{arguments.get('name', 'Extrude')}'. Feature ID: {result.get('featureId', 'unknown')}"
        )]

    elif name == "get_variables":
        variables = await variable_manager.get_variables(
            arguments["documentId"],
            arguments["workspaceId"],
            arguments["elementId"]
        )

        var_list = "\n".join([
            f"- {var.name} = {var.expression}" + (f" ({var.description})" if var.description else "")
            for var in variables
        ])

        return [TextContent(
            type="text",
            text=f"Variables in Part Studio:\n{var_list}" if var_list else "No variables found"
        )]

    elif name == "set_variable":
        result = await variable_manager.set_variable(
            arguments["documentId"],
            arguments["workspaceId"],
            arguments["elementId"],
            arguments["name"],
            arguments["expression"],
            arguments.get("description")
        )

        return [TextContent(
            type="text",
            text=f"Set variable '{arguments['name']}' = {arguments['expression']}"
        )]

    elif name == "get_features":
        features = await partstudio_manager.get_features(
            arguments["documentId"],
            arguments["workspaceId"],
            arguments["elementId"]
        )

        return [TextContent(
            type="text",
            text=f"Features data: {features}"
        )]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
