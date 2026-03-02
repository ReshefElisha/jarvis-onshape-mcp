# Onshape MCP Server

Enhanced Model Context Protocol (MCP) server for programmatic CAD modeling with Onshape.

## Features

This MCP server provides comprehensive programmatic access to Onshape's REST API, enabling:

### Core Capabilities (45 tools)

- **Document Discovery** - Search and list projects, find Part Studios, navigate workspaces
- **Parametric Sketches** - Rectangles, circles, lines, and arcs on standard planes
- **Feature Management** - Extrude, revolve, thicken, fillet, chamfer, boolean, and pattern features
- **Assembly Management** - Create assemblies, add instances, position parts, create mates (fastened, slider, revolute, cylindrical)
- **Assembly Analysis** - Interference checking, position verification, face coordinate systems, body details
- **Variable Tables** - Read and write Onshape variable tables for parametric designs
- **FeatureScript** - Evaluate FeatureScript expressions, get bounding boxes
- **Export** - Export Part Studios and Assemblies to STL, STEP, PARASOLID, GLTF, OBJ
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

### Document & Navigation Tools

| Tool | Description |
|------|-------------|
| `list_documents` | List documents with filtering and sorting |
| `search_documents` | Search documents by name or description |
| `get_document` | Get detailed document information |
| `get_document_summary` | Get comprehensive summary with workspaces and elements |
| `find_part_studios` | Find Part Studios with optional name filtering |
| `get_elements` | Get all elements (Part Studios, Assemblies, BOMs) in a workspace |
| `get_parts` | Get all parts from a Part Studio |
| `create_document` | Create a new Onshape document |
| `create_part_studio` | Create a new Part Studio in a document |

### Assembly Tools

| Tool | Description |
|------|-------------|
| `create_assembly` | Create a new Assembly in a document |
| `add_assembly_instance` | Add a part or sub-assembly instance to an assembly |
| `get_assembly` | Get assembly structure with instances and occurrences |
| `transform_instance` | Apply a relative transform (inches/degrees). Fails on fixed instances. |
| `set_instance_position` | Set absolute position (resets rotation). Fails on fixed instances. |
| `align_instance_to_face` | Align one instance flush against a face of another |
| `create_mate_connector` | Create an explicit mate connector on a face with offsets |
| `create_fastened_mate` | Create a rigid (fastened) mate between two instances |
| `create_slider_mate` | Create a linear motion mate. First instance slides relative to second. |
| `create_revolute_mate` | Create a rotational mate. First instance rotates relative to second. |
| `create_cylindrical_mate` | Create a slide+rotate mate. First instance moves relative to second. |
| `delete_feature` | Delete a feature (mate, mate connector, etc.) from an assembly or Part Studio |

### Assembly Analysis Tools

| Tool | Description |
|------|-------------|
| `get_assembly_positions` | Get positions, sizes, and bounds of all instances (in inches) |
| `get_assembly_features` | Get all features with their state (OK/ERROR/SUPPRESSED) |
| `get_body_details` | Get face IDs, surface types, normals, and origins for all parts |
| `get_face_coordinate_system` | Query the outward-facing coordinate system for a specific face |
| `check_assembly_interference` | Check for overlapping/interfering parts using bounding box detection |

### Sketch Tools

| Tool | Description |
|------|-------------|
| `create_sketch_rectangle` | Rectangle with optional variable references for width/height |
| `create_sketch_circle` | Circle with center point and radius |
| `create_sketch_line` | Line from start point to end point |
| `create_sketch_arc` | Arc with center, radius, start angle, and end angle |

All sketch tools support `plane` (Front/Top/Right) and `name` parameters. Dimensions are in inches.

### Feature Tools

| Tool | Description |
|------|-------------|
| `create_extrude` | Extrude a sketch with depth, optional variable reference, and operation type |
| `create_thicken` | Thicken a sketch into a solid with optional midplane/opposite direction |
| `create_revolve` | Revolve a sketch around an axis (X/Y/Z) with angle and operation type |
| `create_fillet` | Round edges by edge IDs with radius (supports variable references) |
| `create_chamfer` | Bevel edges by edge IDs with distance (supports variable references) |
| `create_linear_pattern` | Repeat features along an axis (X/Y/Z) with distance and count |
| `create_circular_pattern` | Repeat features around an axis with count and angle spread |
| `create_boolean` | Union, subtract, or intersect bodies by deterministic IDs |

### Variable & Feature Tools

| Tool | Description |
|------|-------------|
| `get_variables` | Get all variables from a Part Studio variable table |
| `set_variable` | Set or update a variable (e.g., `"0.75 in"`) |
| `get_features` | Get all features from a Part Studio |

### FeatureScript Tools

| Tool | Description |
|------|-------------|
| `eval_featurescript` | Evaluate a FeatureScript lambda expression (read-only) |
| `get_bounding_box` | Get the tight bounding box of all parts in a Part Studio |

### Export Tools

| Tool | Description |
|------|-------------|
| `export_part_studio` | Export to STL, STEP, PARASOLID, GLTF, or OBJ (optional `partId` filter) |
| `export_assembly` | Export to STL, STEP, or GLTF |

## Architecture

```
onshape_mcp/
├── api/
│   ├── client.py         # HTTP client with HMAC authentication
│   ├── documents.py      # Document discovery & navigation
│   ├── partstudio.py     # Part Studio management
│   ├── variables.py      # Variable table management
│   ├── assemblies.py     # Assembly lifecycle, mates & features
│   ├── export.py         # Part Studio & Assembly export
│   └── featurescript.py  # FeatureScript evaluation
├── builders/
│   ├── sketch.py         # Sketch builder (rectangle, circle, line, arc, polygon)
│   ├── extrude.py        # Extrude feature builder
│   ├── revolve.py        # Revolve feature builder
│   ├── fillet.py         # Fillet feature builder
│   ├── chamfer.py        # Chamfer feature builder
│   ├── boolean.py        # Boolean operations (union, subtract, intersect)
│   ├── pattern.py        # Linear & circular pattern builders
│   ├── mate.py           # Mate connector & mate builders (face-based)
│   └── thicken.py        # Thicken feature builder
├── analysis/
│   ├── interference.py   # Bounding-box interference detection
│   ├── positioning.py    # Instance position queries & alignment
│   └── face_cs.py        # Face coordinate system queries
├── tools/
│   └── __init__.py       # MCP tool definitions
└── server.py             # Main MCP server (45 tools)
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

The project has comprehensive test coverage with **471 unit tests**.

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
ruff format .
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

### Knowledge Base & Examples

- **[knowledge_base/assembly_workflow_guide.md](knowledge_base/assembly_workflow_guide.md)** - Comprehensive assembly methodology (positioning, mates, solver behavior)
- **[examples/cabinet_assembly.md](examples/cabinet_assembly.md)** - Complete worked example: cabinet with sliding drawers
- **[knowledge_base/](knowledge_base/)** - Onshape feature examples and research

## Roadmap

### Current Status

- Document discovery and navigation (10 tools)
- Sketch creation with rectangles, circles, lines, and arcs
- Feature tools: extrude, revolve, thicken, fillet, chamfer, boolean, patterns
- Full assembly management: fastened, slider, revolute, and cylindrical mates with face-based mate connectors
- Assembly analysis: interference checking, position verification, face coordinate systems
- Variable table management
- FeatureScript evaluation and bounding box queries
- Export to STL, STEP, PARASOLID, GLTF, OBJ
- 471 comprehensive unit tests
- Live-tested on multi-part assemblies (25-instance cabinet with 66 features)

### In Research

- **Geometry-referenced sketch planes** - Create sketches on faces from existing features (see [docs/SKETCH_PLANE_REFERENCE_GUIDE.md](docs/SKETCH_PLANE_REFERENCE_GUIDE.md))
- Query API investigation - How to programmatically reference geometry
- Entity ID mapping - Understanding Onshape's internal ID system

### Near-Term Priorities

- [ ] Implement `create_sketch_on_geometry()` for carpentry-correct cabinet assembly
- [ ] Sketch constraints (coincident, parallel, tangent, etc.)
- [ ] Pocket cuts and profiles for joinery (dados, rabbets)

### Long-Term Goals

- [ ] Drawing creation
- [ ] Bill of Materials (BOM) generation
- [ ] Advanced constraints and relations
- [ ] Configuration parameter support

### Woodworking-Specific Features

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
