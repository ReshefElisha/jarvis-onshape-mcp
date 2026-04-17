# Development Setup Guide

This guide shows you how to develop and debug the Onshape MCP server without constantly restarting Claude Code.

## Quick Start

### Option 1: Run in VSCode with Debugger (Recommended)

1. **Open the project in VSCode**:
   ```bash
   code /path/to/onshape-mcp
   ```

2. **Press F5** or go to Run → Start Debugging

3. **The server will start** with:
   - ✅ Full debugging support (breakpoints, step-through, etc.)
   - ✅ Environment variables loaded
   - ✅ Console output visible
   - ✅ Auto-reload when you make changes (just restart with F5)

### Option 2: Run from Terminal

```bash
cd /path/to/onshape-mcp
python run_mcp_server.py
```

## Configuring Claude Code

**Important**: You only need to configure this ONCE. After that, you can restart the MCP server as many times as you want without touching Claude Code.

### Update `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "onshape": {
      "command": "python",
      "args": ["-m", "onshape_mcp.server"],
      "cwd": "/absolute/path/to/onshape-mcp",
      "env": {
        "ONSHAPE_ACCESS_KEY": "your_access_key_here",
        "ONSHAPE_SECRET_KEY": "your_secret_key_here"
      }
    }
  }
}
```

**Important**: Replace `/absolute/path/to/onshape-mcp` with the actual absolute path to your cloned repository.

## Development Workflow

### When Making Changes:

1. **Edit your code** in VSCode
2. **Stop the server** (Ctrl+C or stop debugger)
3. **Restart the server** (F5 or `python run_mcp_server.py`)
4. **Claude Code will automatically reconnect** when you ask it to use a tool

### You DO NOT need to:
- ❌ Restart Claude Code
- ❌ Reload VSCode
- ❌ Edit `mcp.json` again

### Testing Your Changes:

1. Make your code changes
2. Restart the MCP server (F5)
3. In Claude Code, ask: "Can you list my Onshape documents?"
4. Claude Code will use your updated server!

## Debugging Tips

### Setting Breakpoints:

1. Click in the left margin of any `.py` file to set a breakpoint (red dot appears)
2. When Claude Code calls that tool, execution will pause
3. You can:
   - Inspect variables
   - Step through code (F10 = step over, F11 = step into)
   - View the call stack
   - Evaluate expressions in the Debug Console

### Viewing Output:

- **Terminal Output**: Shows server startup and MCP protocol messages
- **Debug Console**: Shows Python print statements and errors
- **Variables Panel**: Shows current variable values when paused

### Common Debugging Scenarios:

**Scenario 1: Tool not working as expected**
- Set breakpoint in the tool handler (e.g., line 539 for `get_parts`)
- Run the tool from Claude Code
- Step through the code to see what's happening

**Scenario 2: API call failing**
- Set breakpoint in the API client (`onshape_mcp/api/client.py`)
- Inspect the request URL and headers
- Check the response data

**Scenario 3: Data parsing issues**
- Set breakpoint where you parse the API response
- Inspect the raw data structure
- Check the data models in the Variables panel

## Files Created

- **`.vscode/launch.json`** - VSCode debugger configuration
- **`run_mcp_server.py`** - Development runner script with environment setup
- **`DEV_SETUP.md`** - This guide

## Advanced: Using with Docker (Optional)

If you prefer Docker, you can create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install -e .

ENV ONSHAPE_ACCESS_KEY=your_access_key_here
ENV ONSHAPE_SECRET_KEY=your_secret_key_here

CMD ["python", "-m", "onshape_mcp.server"]
```

Then update `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "onshape": {
      "command": "docker",
      "args": ["run", "-i", "onshape-mcp"]
    }
  }
}
```

## Troubleshooting

### Server won't start:
- Check Python version: `python --version` (needs 3.10+)
- Verify virtual environment: `which python`
- Install dependencies: `pip install -e ".[dev]"`

### Claude Code can't connect:
- Make sure the server is running (you should see startup messages)
- Check that `cwd` in `mcp.json` points to the correct directory
- Try asking Claude Code: "List my Onshape documents" to trigger reconnection

### Debugger not stopping at breakpoints:
- Make sure `justMyCode` is `false` in `launch.json`
- Verify the breakpoint is on an executable line (not a comment or blank line)
- Check that the code path is actually being executed

### Changes not taking effect:
- Make sure you restarted the server after making changes
- Check the terminal output to confirm the server restarted
- Try asking Claude Code to use a different tool, then retry

## Next Steps

1. **Test the setup**: Press F5 to start debugging
2. **Make a change**: Edit a tool handler to add a print statement
3. **Test it**: Restart server, ask Claude Code to use that tool
4. **See the output**: Check the Debug Console

Happy debugging! 🎉
