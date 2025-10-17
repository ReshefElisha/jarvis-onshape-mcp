# Onshape MCP Server

Enhanced Model Context Protocol (MCP) server for programmatic CAD modeling with Onshape.

## Features

This MCP server provides comprehensive programmatic access to Onshape's REST API, enabling:

### ✨ Core Capabilities

- **🔍 Document Discovery** - Search and list projects, find Part Studios, navigate workspaces
- **📐 Parametric Sketch Creation** - Create sketches with rectangles, circles, and lines
- **⚙️ Feature Management** - Add extrudes, manage feature trees
- **📊 Variable Tables** - Read and write Onshape variable tables for parametric designs
- **🔧 Configuration Support** - Work with Onshape configuration parameters
- **🗂️ Part Studio Management** - Create and manage Part Studios programmatically

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
      "command": "/absolute/path/to/onshape-mcp/venv/bin/python",
      "args": ["-m", "onshape_mcp.server"],
      "env": {
        "ONSHAPE_ACCESS_KEY": "your_access_key_here",
        "ONSHAPE_SECRET_KEY": "your_secret_key_here"
      }
    }
  }
}
```

**Important Notes:**
- Use the **absolute path** to your virtual environment's Python executable
- Find your path: `cd onshape-mcp && pwd` to get the directory path
- On Windows: Use `C:/path/to/onshape-mcp/venv/Scripts/python.exe`
- Replace the API keys with your actual keys from [Onshape Developer Portal](https://dev-portal.onshape.com/)
- **Restart Claude Code** after editing `mcp.json`

**Verify it works:**
Ask Claude Code: "Can you list my Onshape documents?"

For complete setup instructions, see [docs/QUICK_START.md](docs/QUICK_START.md).

## Available Tools

### 🔍 Document Discovery Tools

#### list_documents
List documents in your Onshape account with filtering and sorting.

**Parameters:**
- `filterType` - "all", "owned", "created", "shared" (optional)
- `sortBy` - "name", "modifiedAt", "createdAt" (optional)
- `sortOrder` - "asc", "desc" (optional)
- `limit` - Maximum number of results (optional)

#### search_documents
Search for documents by name or description.

**Parameters:**
- `query` - Search query string (required)
- `limit` - Maximum number of results (optional)

#### get_document
Get detailed information about a specific document.

**Parameters:**
- `documentId` - Onshape document ID (required)

#### get_document_summary
Get comprehensive document summary including all workspaces and elements.

**Parameters:**
- `documentId` - Onshape document ID (required)

#### find_part_studios
Find Part Studio elements in a workspace, with optional name filtering.

**Parameters:**
- `documentId` - Onshape document ID (required)
- `workspaceId` - Workspace ID (required)
- `namePattern` - Optional name pattern to filter by (case-insensitive)

#### get_elements
Get all elements (Part Studios, Assemblies, BOMs, etc.) in a workspace.

**Parameters:**
- `documentId` - Onshape document ID (required)
- `workspaceId` - Workspace ID (required)
- `elementType` - Optional filter by element type (e.g., 'PARTSTUDIO', 'ASSEMBLY')

#### get_parts
Get all parts from a Part Studio element.

**Parameters:**
- `documentId` - Onshape document ID (required)
- `workspaceId` - Workspace ID (required)
- `elementId` - Part Studio element ID (required)

#### get_assembly
Get assembly structure including instances and occurrences.

**Parameters:**
- `documentId` - Onshape document ID (required)
- `workspaceId` - Workspace ID (required)
- `elementId` - Assembly element ID (required)

### 📐 Sketch and Feature Tools

#### create_sketch_rectangle

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
│   ├── documents.py      # Document discovery & navigation
│   ├── partstudio.py     # Part Studio management
│   └── variables.py      # Variable table management
├── builders/
│   ├── sketch.py         # Sketch feature builder
│   └── extrude.py        # Extrude feature builder
├── tools/
│   └── __init__.py       # MCP tool definitions
└── server.py             # Main MCP server (13 tools)
```

## Examples

### Example 1: Finding and Working on a Project

```python
# Search for your project
documents = await search_documents(query="robot arm", limit=5)

# Get the first matching document
doc_id = documents[0].id

# Get comprehensive summary
summary = await get_document_summary(doc_id)

# Find Part Studios in main workspace
workspace_id = summary['workspaces'][0].id
part_studios = await find_part_studios(doc_id, workspace_id, namePattern="base")

# Now work with the Part Studio
elem_id = part_studios[0].id
```

### Example 2: Creating a Parametric Cabinet

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

The project has comprehensive test coverage with **93 unit tests**.

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov

# Run specific module tests
pytest tests/api/test_documents.py -v

# Use make commands
make test
make test-cov
make coverage-html
```

For detailed testing documentation, see [docs/TESTING.md](docs/TESTING.md).

### Code Formatting

```bash
black .
ruff check .
```

## Documentation

### Getting Started
- **[docs/QUICK_START.md](docs/QUICK_START.md)** - Quick start guide for Claude Code users
- **[docs/DEV_SETUP.md](docs/DEV_SETUP.md)** - Development environment setup with SSE mode and debugging

### Development & Testing
- **[docs/TESTING.md](docs/TESTING.md)** - Testing guide and best practices
- **[docs/TEST_SUMMARY.md](docs/TEST_SUMMARY.md)** - Test suite overview
- **[docs/FEATURE_SUMMARY.md](docs/FEATURE_SUMMARY.md)** - Implementation details and statistics

### API & Implementation
- **[docs/ONSHAPE_API_IMPROVEMENTS.md](docs/ONSHAPE_API_IMPROVEMENTS.md)** - API format fixes and BTMSketch-151 implementation
- **[docs/SKETCH_PLANE_REFERENCE_GUIDE.md](docs/SKETCH_PLANE_REFERENCE_GUIDE.md)** - Advanced: Geometry-referenced sketch planes
- **[docs/NEXT_STEPS_GEOMETRY_REFERENCES.md](docs/NEXT_STEPS_GEOMETRY_REFERENCES.md)** - Roadmap for geometry reference implementation
- **[docs/DOCUMENT_DISCOVERY.md](docs/DOCUMENT_DISCOVERY.md)** - Complete guide to document discovery features
- **[docs/PARTS_ASSEMBLY_TOOLS.md](docs/PARTS_ASSEMBLY_TOOLS.md)** - Parts and assembly tool documentation

### Project Analysis & Research
- **[docs/CARPENTRY_PRINCIPLES_FOR_CAD.md](docs/CARPENTRY_PRINCIPLES_FOR_CAD.md)** - How to think like a carpenter in CAD
- **[docs/LEARNING_SUMMARY.md](docs/LEARNING_SUMMARY.md)** - Summary of side panel analysis and learnings
- **[docs/DISPLAY_CABINETS_ANALYSIS_SUMMARY.md](docs/DISPLAY_CABINETS_ANALYSIS_SUMMARY.md)** - Analysis of display cabinets project
- **[docs/AGENT_CREATION_GUIDE.md](docs/AGENT_CREATION_GUIDE.md)** - Guide for creating CAD agents
- **[docs/CREATING_CAD_EXPERT_AGENT.md](docs/CREATING_CAD_EXPERT_AGENT.md)** - Creating specialized CAD expert agents

### Knowledge Base
- **[knowledge_base/](knowledge_base/)** - Onshape feature examples and research

## Roadmap

### Current Status ✅
- ✅ Document discovery and navigation (5 tools)
- ✅ Basic sketch creation on standard planes (Front/Top/Right)
- ✅ Variable table management
- ✅ Extrude features with parametric depth
- ✅ Proper Onshape API format (BTMSketch-151)
- ✅ 93 comprehensive unit tests

### In Research 🔬
- 🔬 **Geometry-referenced sketch planes** - Create sketches on faces from existing features (see [docs/SKETCH_PLANE_REFERENCE_GUIDE.md](docs/SKETCH_PLANE_REFERENCE_GUIDE.md))
- 🔬 Query API investigation - How to programmatically reference geometry
- 🔬 Entity ID mapping - Understanding Onshape's internal ID system

### Near-Term Priorities 📋
- [ ] Implement `create_sketch_on_geometry()` for carpentry-correct cabinet assembly
- [ ] Add support for more sketch entities (circles, arcs)
- [ ] Implement more constraint types
- [ ] Pattern features (linear, circular) for shelves and hardware holes
- [ ] Pocket cuts and profiles for joinery (dados, rabbets)

### Long-Term Goals 🎯
- [ ] Assembly support and mate connectors
- [ ] Advanced feature types (fillet, chamfer, revolve)
- [ ] Drawing creation
- [ ] Part export (STEP, STL, etc.)
- [ ] Advanced constraints and relations
- [ ] FeatureScript execution
- [ ] Bill of Materials (BOM) generation

### Woodworking-Specific Features 🪚
- [ ] Joinery library (dado, rabbet, mortise & tenon, dovetail)
- [ ] Standard hardware patterns (shelf pins, drawer slides)
- [ ] Cut list generation
- [ ] Material optimization (sheet layout)
- [ ] Assembly instructions generation

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
