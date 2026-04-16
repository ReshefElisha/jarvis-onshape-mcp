"""Claude-driven CAD agent loop — the "same capability as coding" dogfood.

`cad_driver.py` is me (a human using Python) driving the MCP tools via
hardcoded steps. THIS module is a fresh Claude API instance driving the
same tools autonomously from only a natural-language brief. No step list.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    uv run python tools/agent_loop.py \\
        --brief "Build a 40x40x10mm plate with a central 8mm through-hole."

The loop:
    1. Create a throwaway Onshape doc + Part Studio.
    2. Seed Claude with the SKILL.md protocols + document/workspace/element
       IDs + the brief.
    3. Claude picks tool calls. We execute them via server.call_tool().
       Tool results — including rendered PNGs from describe_part_studio —
       go back into the conversation as tool_result blocks.
    4. Loop until Claude outputs a stop reason other than tool_use (i.e.
       ends the conversation) or we hit MAX_TURNS.
    5. Every tool call + response is logged; every rendered image is
       saved to the session output directory so the run is post-mortemable.

The agent sees the exact same tools any future MCP client of this
server would see, via the server's own list_tools() output. No custom
tool schema duplication.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv(REPO.parent.parent / ".env")
load_dotenv(REPO / ".env")

from loguru import logger  # noqa: E402

from onshape_mcp import server as S  # noqa: E402
from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials  # noqa: E402
from onshape_mcp.api.documents import DocumentManager  # noqa: E402
from onshape_mcp.api.partstudio import PartStudioManager  # noqa: E402


SKILL_PATH = REPO.parent.parent / "SKILL.md"

# Tools we want the agent to see. Deliberately a subset: focus on Part
# Studio authoring + describe/measure + utilities; skip the assembly tools
# (the agent-loop demos are single-part). Expand this list when demo scope
# grows.
AGENT_TOOLS = [
    "create_sketch_rectangle",
    "create_sketch_circle",
    "create_sketch_line",
    "create_sketch_arc",
    "create_extrude",
    "create_revolve",
    "create_thicken",
    "create_fillet",
    "create_chamfer",
    "create_boolean",
    "create_linear_pattern",
    "create_circular_pattern",
    "update_feature",
    "delete_feature_by_name",
    "list_entities",
    "describe_part_studio",
    "measure",
    "get_mass_properties",
    "render_part_studio_views",
    "crop_image",
    "list_cached_images",
    "export_part_studio",
]


def _load_skill_md() -> str:
    try:
        return SKILL_PATH.read_text()
    except OSError:
        return "(SKILL.md not found — running without skill guide)"


def _strip_default_from_schema(schema: Any) -> Any:
    """Anthropic's tool-use `input_schema` rejects `default` keys in some
    strict-validation contexts. Strip recursively; the MCP schemas use
    them liberally."""
    if isinstance(schema, dict):
        return {
            k: _strip_default_from_schema(v)
            for k, v in schema.items()
            if k != "default"
        }
    if isinstance(schema, list):
        return [_strip_default_from_schema(x) for x in schema]
    return schema


async def _mcp_tools_as_anthropic_tools() -> List[Dict[str, Any]]:
    mcp_tools = await S.list_tools()
    filtered = [t for t in mcp_tools if t.name in AGENT_TOOLS]
    out = []
    for t in filtered:
        out.append({
            "name": t.name,
            "description": t.description,
            "input_schema": _strip_default_from_schema(t.inputSchema),
        })
    return out


def _tool_result_blocks(
    tool_use_id: str, result_blocks: list, out_dir: Path, step_ix: int
) -> List[Dict[str, Any]]:
    """Convert MCP tool response (TextContent + ImageContent) into Anthropic
    `tool_result` content. Save each image to disk too, so the run is
    post-mortemable from the filesystem."""
    content: List[Dict[str, Any]] = []
    img_ix = 0
    for block in result_blocks:
        btype = getattr(block, "type", None)
        if btype == "text":
            content.append({"type": "text", "text": block.text})
        elif btype == "image":
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": block.mimeType,
                    "data": block.data,
                },
            })
            try:
                png_bytes = base64.b64decode(block.data)
                out_path = out_dir / f"{step_ix:02d}_tool{img_ix}.png"
                out_path.write_bytes(png_bytes)
                img_ix += 1
            except Exception as e:
                logger.warning(f"failed to save tool image: {e}")
    return [{
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
    }]


async def run_agent(
    brief: str,
    out_dir: Path,
    *,
    model: str = "claude-opus-4-7",
    max_turns: int = 30,
) -> Dict[str, Any]:
    """Run the agent loop. Returns a summary dict."""

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. The agent-loop needs API access. "
            "Export the key and retry."
        )

    try:
        from anthropic import Anthropic
    except ImportError:
        raise RuntimeError(
            "anthropic SDK not installed. Run: uv add anthropic"
        )

    ak = os.getenv("ONSHAPE_API_KEY") or os.getenv("ONSHAPE_ACCESS_KEY", "")
    sk = os.getenv("ONSHAPE_API_SECRET") or os.getenv("ONSHAPE_SECRET_KEY", "")
    creds = OnshapeCredentials(access_key=ak, secret_key=sk)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "brief.txt").write_text(brief)
    transcript_path = out_dir / "transcript.jsonl"
    transcript_path.write_text("")

    def _log_event(kind: str, data: Dict[str, Any]) -> None:
        with transcript_path.open("a") as f:
            f.write(json.dumps({"kind": kind, **data}, default=str) + "\n")

    async with OnshapeClient(creds) as client:
        dm = DocumentManager(client)
        doc_name = f"dyna-agent {int(time.time())}"
        doc = await dm.create_document(doc_name)
        did = doc.id
        workspaces = await dm.get_workspaces(did)
        wid = next((w.id for w in workspaces if w.is_main), workspaces[0].id)
        psm = PartStudioManager(client)
        ps = await psm.create_part_studio(did, wid, "agent ps")
        eid = ps["id"] if isinstance(ps, dict) else ps.id
        doc_url = f"https://cad.onshape.com/documents/{did}/w/{wid}/e/{eid}"
        logger.info(f"agent doc: {doc_url}")
        _log_event("doc_created", {"did": did, "wid": wid, "eid": eid, "url": doc_url})

        anthropic_tools = await _mcp_tools_as_anthropic_tools()
        skill = _load_skill_md()

        system_prompt = (
            "You are an engineering CAD designer driving an Onshape Part Studio "
            "through a tool interface. Your job is to build the part described by "
            "the user's brief.\n\n"
            "Design context:\n"
            f"  documentId = {did}\n"
            f"  workspaceId = {wid}\n"
            f"  elementId = {eid}\n"
            f"  (pass these into every tool call's documentId/workspaceId/elementId fields)\n\n"
            "Protocol guide (MUST follow):\n" + skill + "\n\n"
            "Work iteratively: (1) decide the next feature, (2) call the tool, "
            "(3) describe_part_studio after any non-trivial change, (4) verify "
            "in the returned text + render, (5) fix or proceed. When the part "
            "is complete and verified, call export_part_studio once to produce "
            "a STEP file, then state DONE in plain text and stop using tools."
        )

        client_anthropic = Anthropic()
        messages: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": f"Brief: {brief}\n\nBegin. Use tools. Describe after every mutation."
            }
        ]

        turn = 0
        while turn < max_turns:
            turn += 1
            logger.info(f"=== TURN {turn} ===")
            _log_event("turn_start", {"turn": turn})

            resp = client_anthropic.messages.create(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                tools=anthropic_tools,
                messages=messages,
            )

            assistant_content = resp.content
            messages.append({"role": "assistant", "content": assistant_content})

            # Log every text/tool_use block so the transcript has the narrative.
            for block in assistant_content:
                if block.type == "text":
                    _log_event("assistant_text", {"turn": turn, "text": block.text})
                    logger.info(f"assistant: {block.text[:400]}")
                elif block.type == "tool_use":
                    _log_event("tool_use", {
                        "turn": turn, "tool_use_id": block.id,
                        "name": block.name, "input": block.input,
                    })
                    logger.info(f"tool_use: {block.name}({json.dumps(block.input, default=str)[:200]})")

            if resp.stop_reason != "tool_use":
                logger.info(f"stop_reason={resp.stop_reason} -- ending loop")
                _log_event("stop", {"reason": resp.stop_reason})
                break

            # Execute every tool_use in the assistant response.
            tool_results: List[Dict[str, Any]] = []
            for block in assistant_content:
                if block.type != "tool_use":
                    continue
                try:
                    result_blocks = await S.call_tool(block.name, block.input)
                except Exception as e:
                    result_blocks = [
                        type("_", (), {
                            "type": "text",
                            "text": f"tool raised: {type(e).__name__}: {e}"
                        })()
                    ]
                tr = _tool_result_blocks(block.id, result_blocks, out_dir, turn)
                tool_results.extend(tr)
                _log_event("tool_result", {
                    "turn": turn,
                    "tool_use_id": block.id,
                    "text_preview": "".join(
                        c.get("text", "")[:300] for c in tr[0]["content"]
                        if c.get("type") == "text"
                    ),
                })

            messages.append({"role": "user", "content": tool_results})

        summary = {
            "doc_url": doc_url,
            "document_id": did,
            "turns": turn,
            "stop_reason": resp.stop_reason if turn else None,
            "out_dir": str(out_dir),
        }
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        return summary


def _cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief", required=True, help="Natural-language CAD brief")
    parser.add_argument("--model", default="claude-opus-4-7")
    parser.add_argument("--max-turns", type=int, default=30)
    parser.add_argument(
        "--out",
        default=str(REPO.parent.parent / "scratchpad" / "agent-runs"),
        help="Directory root for per-run output",
    )
    args = parser.parse_args()
    ts = int(time.time())
    out_dir = Path(args.out) / f"run-{ts}"

    summary = asyncio.run(run_agent(
        brief=args.brief,
        out_dir=out_dir,
        model=args.model,
        max_turns=args.max_turns,
    ))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
