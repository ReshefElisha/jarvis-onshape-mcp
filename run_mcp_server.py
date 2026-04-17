#!/usr/bin/env python3
"""
Development runner for Onshape MCP Server.

This script runs the MCP server in a way that can be debugged in VSCode
and connected to from Claude Code without restarting Claude Code every time.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set up environment variables (replace with your actual keys or use environment variables)
os.environ.setdefault("ONSHAPE_ACCESS_KEY", "your_access_key_here")
os.environ.setdefault("ONSHAPE_SECRET_KEY", "your_secret_key_here")

# Import and run the server
from onshape_mcp.server import main

if __name__ == "__main__":
    print("🚀 Starting Onshape MCP Server in development mode...")
    print(f"📂 Working directory: {project_root}")
    print(f"🔑 Using API credentials from environment")
    print("🐛 Debug mode: Ready for VSCode debugger")
    print("=" * 60)

    asyncio.run(main())
