# Onshape MCP Server

Enhanced Model Context Protocol (MCP) server for programmatic CAD modeling with Onshape.

## Features

This MCP server provides comprehensive programmatic access to Onshape's REST API, enabling:

### ✨ Core Capabilities

- **Parametric Sketch Creation** - Create sketches with rectangles, circles, and lines
- **Feature Management** - Add extrudes, manage feature trees
- **Variable Tables** - Read and write Onshape variable tables for parametric designs
- **Configuration Support** - Work with Onshape configuration parameters
- **Part Studio Management** - Create and manage Part Studios programmatically

## Installation

### Prerequisites

- Python 3.10 or higher
- Onshape account with API access
- Onshape API keys (access key and secret key)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/hedless/onshape-mcp.git
cd onshape-mcp
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -e .
```

4. Set up environment variables:
```bash
export ONSHAPE_ACCESS_KEY="your_access_key"
export ONSHAPE_SECRET_KEY="your_secret_key"
```

Or create a `.env` file:
```
ONSHAPE_ACCESS_KEY=your_access_key
ONSHAPE_SECRET_KEY=your_secret_key
```

## Getting Onshape API Keys

1. Go to [Onshape Developer Portal](https://dev-portal.onshape.com/)
2. Sign in with your Onshape account
3. Create a new API key
4. Copy the Access Key and Secret Key

## Usage

### Running the Server

```bash
onshape-mcp
```

Or directly with Python:
```bash
python -m onshape_mcp.server
```

### Configuring with Claude Code

Add to your `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "onshape": {
      "command": "python",
      "args": ["-m", "onshape_mcp.server"],
      "cwd": "/path/to/onshape-mcp",
      "env": {
        "ONSHAPE_ACCESS_KEY": "your_access_key",
        "ONSHAPE_SECRET_KEY": "your_secret_key"
      }
    }
  }
}
```

## Available Tools

### create_sketch_rectangle

Create a rectangular sketch with optional variable references.

**Parameters:**
- `documentId` - Onshape document ID
- `workspaceId` - Workspace ID
- `elementId` - Part Studio element ID
- `name` - Sketch name (default: "Sketch")
- `plane` - Sketch plane: "Front", "Top", or "Right"
- `corner1` - First corner [x, y] in inches
- `corner2` - Second corner [x, y] in inches
- `variableWidth` - Optional variable name for width
- `variableHeight` - Optional variable name for height

### create_extrude

Create an extrude feature from a sketch.

**Parameters:**
- `documentId` - Onshape document ID
- `workspaceId` - Workspace ID
- `elementId` - Part Studio element ID
- `name` - Extrude name (default: "Extrude")
- `sketchFeatureId` - ID of sketch to extrude
- `depth` - Extrude depth in inches
- `variableDepth` - Optional variable name for depth
- `operationType` - "NEW", "ADD", "REMOVE", or "INTERSECT"

### get_variables

Get all variables from a Part Studio variable table.

**Parameters:**
- `documentId` - Onshape document ID
- `workspaceId` - Workspace ID
- `elementId` - Part Studio element ID

### set_variable

Set or update a variable in a Part Studio.

**Parameters:**
- `documentId` - Onshape document ID
- `workspaceId` - Workspace ID
- `elementId` - Part Studio element ID
- `name` - Variable name
- `expression` - Variable expression (e.g., "0.75 in")
- `description` - Optional variable description

### get_features

Get all features from a Part Studio.

**Parameters:**
- `documentId` - Onshape document ID
- `workspaceId` - Workspace ID
- `elementId` - Part Studio element ID

## Architecture

```
onshape_mcp/
├── api/
│   ├── client.py         # HTTP client with authentication
│   ├── partstudio.py     # Part Studio management
│   └── variables.py      # Variable table management
├── builders/
│   ├── sketch.py         # Sketch feature builder
│   └── extrude.py        # Extrude feature builder
├── tools/
│   └── __init__.py       # MCP tool definitions
└── server.py             # Main MCP server
```

## Example: Creating a Parametric Cabinet

```python
# Set variables
await set_variable(doc_id, ws_id, elem_id, "width", "39.5 in")
await set_variable(doc_id, ws_id, elem_id, "depth", "16 in")
await set_variable(doc_id, ws_id, elem_id, "height", "67.125 in")
await set_variable(doc_id, ws_id, elem_id, "wall_thickness", "0.75 in")

# Create side panel sketch
await create_sketch_rectangle(
    doc_id, ws_id, elem_id,
    name="Side Panel",
    plane="Front",
    corner1=[0, 0],
    corner2=[16, 67.125],
    variableWidth="depth",
    variableHeight="height"
)

# Extrude to create side
await create_extrude(
    doc_id, ws_id, elem_id,
    name="Side Extrude",
    sketchFeatureId="<sketch_id>",
    depth=0.75,
    variableDepth="wall_thickness"
)
```

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black .
ruff check .
```

## Roadmap

- [ ] Add support for more feature types (fillet, chamfer, revolve)
- [ ] Assembly support
- [ ] Drawing creation
- [ ] Part export (STEP, STL, etc.)
- [ ] Pattern features (linear, circular)
- [ ] Advanced constraints and relations
- [ ] FeatureScript execution

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License

## Acknowledgments

- Inspired by [OnPy](https://github.com/kyle-tennison/onpy)
- Built on the [Model Context Protocol](https://modelcontextprotocol.io/)
- Onshape API documentation: https://onshape-public.github.io/docs/

## Support

For issues and questions:
- GitHub Issues: https://github.com/hedless/onshape-mcp/issues
- Onshape API Forum: https://forum.onshape.com/
