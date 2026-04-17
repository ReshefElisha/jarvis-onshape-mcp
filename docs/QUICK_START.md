# Quick Start Guide - Onshape MCP Server

## 🚀 Getting Started with Claude Code

The fastest way to use this server is with **Claude Code** - an AI assistant that can design CAD models through natural conversation.

### 1. Install

```bash
git clone https://github.com/hedless/onshape-mcp.git
cd onshape-mcp
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

### 2. Get Onshape API Keys

1. Go to [Onshape Developer Portal](https://dev-portal.onshape.com/)
2. Sign in with your Onshape account
3. Create a new API key
4. Copy the Access Key and Secret Key

### 3. Configure Claude Code

Add this to your `~/.claude/mcp.json` file:

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

**Important:** Replace `/absolute/path/to/onshape-mcp` with the actual full path. To find it:
```bash
cd onshape-mcp
pwd  # Copy this path
```

On Windows, the command path would be:
```
"C:/path/to/onshape-mcp/venv/Scripts/python.exe"
```

### 4. Restart Claude Code

After saving `mcp.json`, restart Claude Code for the changes to take effect.

### 5. Verify It Works

In Claude Code, try asking:
```
"Can you list my Onshape documents?"
```

If successful, Claude Code will show your Onshape projects!

## ✅ Testing (Optional for Developers)

```bash
pytest
# Should show: 93 passed in ~2s ✅
```

## 💬 Using with Claude Code

Once configured, just talk to Claude Code naturally! Here are examples:

### Finding Your Projects

**You say:**
```
"Search for my robot arm project"
```

**Claude Code will:**
- Use `search_documents` to find projects matching "robot arm"
- Show you the results with document IDs
- Ask which one you want to work with

### Exploring Project Structure

**You say:**
```
"Show me what's inside document abc123"
```

**Claude Code will:**
- Use `get_document_summary` to get the overview
- List all workspaces and Part Studios
- Help you identify which elements to work with

### Creating a Parametric Model

**You say:**
```
"Create a 10x5x3 inch parametric box in my project"
```

**Claude Code will:**
1. Search for your project
2. Find the appropriate Part Studio
3. Create variables for width, height, depth
4. Create a rectangular sketch
5. Extrude it to the specified depth
6. Link everything to the variables

### Updating Existing Designs

**You say:**
```
"In my cabinet project, change the width variable to 48 inches"
```

**Claude Code will:**
- Search for the cabinet project
- Find the Part Studio with the width variable
- Update the variable using `set_variable`
- Confirm the change

## 📐 Example Conversations

### Example 1: Simple Box

```
You: "I need to create a simple box in my 'Test Parts' document.
     Make it 10 inches wide, 5 inches tall, and 3 inches deep."

Claude: I'll help you create that box. Let me find your Test Parts document...
        [Uses search_documents, find_part_studios]

        I found your document. Now I'll create the parametric box...
        [Creates variables, sketch, and extrude]

        Done! Created a 10"x5"x3" parametric box with variables
        for easy adjustment.
```

### Example 2: Finding and Modifying

```
You: "Find my robot arm project and show me all the variables"

Claude: Let me search for that...
        [Uses search_documents]

        Found "Robot Arm v2". Here are the current variables:
        - base_diameter: 4 in
        - arm_length: 12 in
        - joint_radius: 0.5 in
        - wall_thickness: 0.25 in

You: "Change the arm length to 15 inches"

Claude: Updated arm_length to 15 in. The model will regenerate
        with the new dimension.
```

## 🛠️ All Available Tools

### 🔍 Document Discovery (5 tools)

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `list_documents` | List all documents | `filterType`, `sortBy`, `limit` |
| `search_documents` | Search by name | `query`, `limit` |
| `get_document` | Get document details | `documentId` |
| `get_document_summary` | Full document overview | `documentId` |
| `find_part_studios` | Find Part Studios | `documentId`, `workspaceId`, `namePattern` |

### 📐 CAD Operations (5 tools)

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `create_sketch_rectangle` | Create rectangular sketch | `corner1`, `corner2`, variables |
| `create_extrude` | Extrude sketch | `sketchFeatureId`, `depth` |
| `get_variables` | List variables | `documentId`, `workspaceId`, `elementId` |
| `set_variable` | Set/update variable | `name`, `expression` |
| `get_features` | List all features | `documentId`, `workspaceId`, `elementId` |

## 💡 Common Workflows

### Workflow 1: Start New Design

**You say:** "I want to create a new part in my project"

**Claude Code does:**
1. Searches/lists your documents
2. Gets workspace and Part Studio info
3. Creates variables for your dimensions
4. Creates sketches
5. Adds extrudes
6. Links features to variables

### Workflow 2: Find Existing Design

**You say:** "Show me my cabinet project parameters"

**Claude Code does:**
1. Searches for "cabinet" in your documents
2. Gets the document summary
3. Finds Part Studios
4. Lists all variables and their values
5. Shows existing features

### Workflow 3: Update Parameters

**You say:** "Change the cabinet width to 48 inches"

**Claude Code does:**
1. Finds your cabinet project
2. Locates the Part Studio
3. Reviews current variable values
4. Updates the width variable
5. Confirms the change

## 🧪 Testing

```bash
# Run all tests (93 tests)
pytest

# Run with coverage
pytest --cov

# Run specific module
pytest tests/api/test_documents.py -v

# Quick test (no coverage)
pytest --no-cov
```

## 📚 Documentation

- **[DOCUMENT_DISCOVERY.md](DOCUMENT_DISCOVERY.md)** - Document discovery feature guide
- **[TESTING.md](TESTING.md)** - Complete testing guide
- **[README.md](README.md)** - Full project documentation
- **[FEATURE_SUMMARY.md](FEATURE_SUMMARY.md)** - Implementation details

## 🔧 Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Format code
make format

# Run linter
make lint

# Run all checks
make check-all

# Clean build artifacts
make clean
```

## ⚡ Quick Tips

### For Claude Code Users:

1. **Be specific** - "Find my robot arm project" is better than "find project"
2. **Use project names** - Claude remembers document IDs during the conversation
3. **Ask to see first** - "Show me the variables" before asking to change them
4. **Natural language** - No need to know API details, just describe what you want

### For Developers:

1. **Use async/await** - All API calls are async
2. **Handle errors** - Not all documents may be accessible
3. **Test thoroughly** - Run tests after changes
4. **Follow patterns** - Look at existing code for examples

### For Direct API Usage:

1. **Create .env file** - Keep credentials secure when running standalone
2. **Test connection** - Run `list_documents` to verify API access
3. **Start simple** - Try search and summary first
4. **Use examples** - Follow the workflow examples above

## 🎯 Next Steps

### Beginner (Using Claude Code):
1. Ask: "List my Onshape documents"
2. Ask: "Search for [project name]"
3. Ask: "Show me what's in that document"

### Intermediate:
1. Ask: "Create a simple box 10x5x3 inches"
2. Ask: "Show me the variables in my project"
3. Ask: "Change the width to 12 inches"

### Advanced:
1. Design complete parametric assemblies through conversation
2. Modify multiple parameters at once
3. Create complex multi-part designs

## 🆘 Troubleshooting

### Claude Code can't see the MCP server?
1. Check `~/.claude/mcp.json` exists and is valid JSON
2. Verify the Python path is absolute (use `pwd` in the project directory)
3. Restart Claude Code after editing `mcp.json`
4. Check credentials are in `mcp.json`, not `.env`

### Can't find documents?
- Verify API credentials in `~/.claude/mcp.json`
- Check your Onshape account has documents
- Ask Claude: "List all my documents" to see everything

### Search returns nothing?
- Use partial names: "robot" instead of "robot arm assembly v2"
- Search is case-insensitive
- Try asking: "List my documents" to browse instead

### IDs not working?
- Don't manually copy IDs - let Claude find them
- Ask Claude to search and navigate for you
- If stuck, ask: "Show me the document summary"

### Server won't start?
- Make sure you activated the virtual environment
- Run `pip install -e ".[dev]"` again
- Check Python version: `python --version` (needs 3.10+)

## 📊 Statistics

- **10 MCP Tools** - Full CAD and discovery capabilities
- **93 Unit Tests** - Comprehensive test coverage
- **~2 second** test execution - Fast feedback
- **5 API modules** - Well-organized codebase

---

**Ready to go!** Open Claude Code and ask: "Can you list my Onshape documents?" 🚀

## 🔧 Standalone Usage (Advanced)

If you want to use the server directly without Claude Code:

1. Create `.env` file:
```bash
ONSHAPE_ACCESS_KEY=your_access_key
ONSHAPE_SECRET_KEY=your_secret_key
```

2. Run the server:
```bash
onshape-mcp
```

Note: This is for developers integrating the MCP server into their own tools. Most users should use Claude Code instead.
