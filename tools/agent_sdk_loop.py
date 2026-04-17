"""Claude Agent SDK driven CAD loop — the REAL dogfood.

Replaces `tools/agent_loop.py`, which called `server.call_tool(...)` in
process and so didn't exercise the MCP transport. A peer doing their
own dogfood imitated that pattern; end-user Claude via Claude Code /
Desktop / API always goes through MCP transport, so tests that skip
it are lying about the integration surface.

This harness:
  1. Launches `uv run onshape-mcp` as a stdio MCP subprocess.
  2. Connects Claude to it via the Claude Agent SDK.
  3. Uses the user's existing Claude Code CLI credentials — no
     ANTHROPIC_API_KEY required.
  4. Auto-grants all MCP tools via `allowed_tools=["mcp__onshape__*"]`.
  5. Streams messages to stdout + writes full transcript + any
     ImageContent blocks to the per-run output dir.

Usage:
    uv run python tools/agent_sdk_loop.py \\
        --brief "60x40x8 mm plate with 4 ø4 mm mounting holes 6 mm in from the corners."

Requires:
    uv add claude-agent-sdk
    claude-code CLI installed + logged in (`claude login`)
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


SKILL_PATH = REPO.parent.parent / "SKILL.md"


def _load_skill_md() -> str:
    try:
        return SKILL_PATH.read_text()
    except OSError:
        return "(SKILL.md not found)"


async def run(brief: str, out_dir: Path, *, max_turns: int = 40) -> dict:
    try:
        from claude_agent_sdk import (
            query,
            ClaudeAgentOptions,
            AssistantMessage,
            ResultMessage,
            SystemMessage,
            UserMessage,
        )
    except ImportError as e:
        raise RuntimeError(
            "claude-agent-sdk not installed. Run: "
            "cd references/hedless-onshape-mcp && uv add claude-agent-sdk"
        ) from e

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "brief.txt").write_text(brief)
    transcript_path = out_dir / "transcript.jsonl"
    transcript_path.write_text("")

    def _log(kind: str, data: dict) -> None:
        with transcript_path.open("a") as f:
            f.write(json.dumps({"kind": kind, **data}, default=str) + "\n")

    skill = _load_skill_md()
    system = (
        "You are an engineering CAD designer driving an Onshape Part Studio "
        "through MCP tools. Build the part described in the user's brief.\n\n"
        "FIRST STEP: call the MCP tools to create a new Onshape document and "
        "Part Studio — there is NOT one already created for you. Use the "
        "create_document then create_part_studio tools to set up your "
        "workspace. After that, thread documentId/workspaceId/elementId "
        "through every subsequent tool call.\n\n"
        "Iterate: propose feature -> call tool -> describe_part_studio to "
        "verify status + topology + render -> fix or proceed. When the part "
        "is complete and verified, call export_part_studio to produce a STEP "
        "file, then reply DONE in plain text and stop using tools.\n\n"
        "Protocol guide (follow strictly):\n" + skill
    )

    # Block the dangerous built-in tools. allowed_tools is ignored under
    # bypassPermissions, so use disallowed_tools to keep Claude out of
    # Bash / Edit / WebFetch / etc. (It still needs Read/Write to think
    # on paper.)
    # Propagate Onshape credentials to the MCP subprocess. The project .env
    # uses the ONSHAPE_API_KEY/SECRET names; the starter's server reads
    # ONSHAPE_ACCESS_KEY/SECRET_KEY first and falls back to API_KEY/SECRET.
    # Pass both explicitly so the subprocess doesn't need the shell to have
    # pre-exported them (lgvhcnlr hit a 401 on first run because of this).
    mcp_env: dict[str, str] = {}
    for name in (
        "ONSHAPE_ACCESS_KEY", "ONSHAPE_SECRET_KEY",
        "ONSHAPE_API_KEY", "ONSHAPE_API_SECRET",
    ):
        if os.getenv(name):
            mcp_env[name] = os.environ[name]

    options = ClaudeAgentOptions(
        mcp_servers={
            "onshape": {
                "type": "stdio",
                "command": "uv",
                "args": [
                    "--directory", str(REPO),
                    "run", "onshape-mcp",
                ],
                **({"env": mcp_env} if mcp_env else {}),
            }
        },
        disallowed_tools=[
            "Bash", "Edit", "MultiEdit", "WebFetch", "WebSearch",
            "Task", "NotebookEdit", "KillShell", "BashOutput",
            # Block any other MCP servers the user has configured in
            # ~/.claude.json -- their tools leak through despite
            # setting_sources=[]. Our agent should only talk to onshape.
            "mcp__claude.ai_*",
            "mcp__plugin_*",
        ],
        permission_mode="bypassPermissions",
        system_prompt=system,
        max_turns=max_turns,
        # Skip loading user/project/local .claude settings so this run is
        # reproducible regardless of what's on disk.
        setting_sources=[],
    )

    print(f"Launching agent loop. Output dir: {out_dir}")
    print(f"Brief: {brief}\n")

    turn_ix = 0
    image_ix = 0
    last_result: Any = None

    async for message in query(prompt=brief, options=options):
        if isinstance(message, SystemMessage):
            _log("system", {"subtype": message.subtype, "data": message.data})
            if message.subtype == "init":
                servers = message.data.get("mcp_servers", [])
                print(f"MCP servers: {servers}")
            continue

        if isinstance(message, AssistantMessage):
            turn_ix += 1
            for block in message.content:
                btype = getattr(block, "type", None) or block.__class__.__name__
                if btype in ("text", "TextBlock"):
                    text = getattr(block, "text", "")
                    _log("assistant_text", {"turn": turn_ix, "text": text})
                    print(f"\n[assistant]: {text}\n")
                elif btype in ("tool_use", "ToolUseBlock"):
                    name = getattr(block, "name", "?")
                    inp = getattr(block, "input", {})
                    _log("tool_use", {
                        "turn": turn_ix, "id": getattr(block, "id", None),
                        "name": name, "input": inp,
                    })
                    preview = json.dumps(inp, default=str)[:160]
                    print(f"  -> {name}({preview})")
            continue

        if isinstance(message, UserMessage):
            # tool_result blocks come back as user messages in the SDK.
            for block in getattr(message, "content", []) or []:
                btype = getattr(block, "type", None) or block.__class__.__name__
                if btype in ("tool_result", "ToolResultBlock"):
                    content = getattr(block, "content", "")
                    # content is list[dict] or plain string depending on tool.
                    text_preview = ""
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict):
                                if c.get("type") == "text":
                                    text_preview = (text_preview + c.get("text", ""))[:600]
                                elif c.get("type") == "image":
                                    src = c.get("source") or {}
                                    if src.get("type") == "base64" and src.get("data"):
                                        try:
                                            png = base64.b64decode(src["data"])
                                            p = out_dir / f"{turn_ix:02d}_{image_ix:02d}.png"
                                            p.write_bytes(png)
                                            image_ix += 1
                                        except Exception:
                                            pass
                    elif isinstance(content, str):
                        text_preview = content[:600]
                    _log("tool_result", {
                        "turn": turn_ix,
                        "tool_use_id": getattr(block, "tool_use_id", None),
                        "text_preview": text_preview,
                    })
                    print(f"  <- {text_preview[:300]}")
            continue

        if isinstance(message, ResultMessage):
            _log("result", {
                "subtype": message.subtype,
                "result": getattr(message, "result", None),
                "usage": getattr(message, "usage", None),
            })
            last_result = message
            print(f"\n=== result: {message.subtype} ===")
            if message.subtype == "success":
                res = getattr(message, "result", None)
                if res:
                    print(res)

    summary = {
        "out_dir": str(out_dir),
        "turns": turn_ix,
        "images_saved": image_ix,
        "subtype": getattr(last_result, "subtype", None) if last_result else None,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary


def _cli() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--brief", required=True, help="Natural-language CAD brief")
    p.add_argument("--max-turns", type=int, default=40)
    p.add_argument(
        "--out",
        default=str(REPO.parent.parent / "scratchpad" / "agent-sdk-runs"),
    )
    args = p.parse_args()
    ts = int(time.time())
    out_dir = Path(args.out) / f"run-{ts}"
    summary = asyncio.run(run(args.brief, out_dir, max_turns=args.max_turns))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
