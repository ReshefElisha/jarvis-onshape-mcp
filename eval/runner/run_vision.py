"""Run the vision-decomposition sub-agent on a brief.

Separate Claude Agent SDK session from the CAD runner. Model: Opus 4.7
(same as CAD agent — per Shef ruling 2026-04-18, the whole premise is
that Opus 4.7 is best at visual reasoning, so using a smaller model here
would defeat the purpose).

Tools allowed: ONLY load_local_image, crop_image (plus harmless reads like
get_document_summary if the SDK ships it). All CAD-mutation tools are
disallowed via the same mechanism as the CAD runner.

Output:
- stdout: pretty-printed agent turns + final structured feature spec
- eval/vision_outputs/<brief_id>.txt: final spec only, for feeding into
  a downstream CAD run or for manual review

Usage (standalone):
    eval/.venv/bin/python eval/runner/run_vision.py --brief-id mm_2019_phase1_drawing
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
from typing import Any, Optional

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

load_dotenv(REPO / ".env")

MANIFEST_PATH = REPO / "eval" / "datasets" / "MANIFEST.json"
VISION_SKILL_PATH = REPO / "eval" / "skills" / "vision" / "SKILL.md"
OUTPUT_DIR = REPO / "eval" / "vision_outputs"


def _load_brief(brief_id: str) -> dict:
    briefs = json.loads(MANIFEST_PATH.read_text())["briefs"]
    for b in briefs:
        if b["brief_id"] == brief_id:
            return b
    raise KeyError(f"brief_id not in MANIFEST: {brief_id}")


def _compose_vision_prompt(brief: dict) -> list[dict]:
    """User message content: text instructions + attached images.

    Attaches BOTH the drawing and the iso render if present, so the agent
    can cross-reference. Includes absolute paths so the agent can call
    load_local_image on them for native-resolution crops.
    """
    blocks: list[dict] = []
    parts = []

    iso_rel = brief.get("reference_png_path")
    drawing_rel = brief.get("brief_image_path")
    attached_paths: list[str] = []
    if iso_rel:
        p = MANIFEST_PATH.parent / iso_rel
        if p.exists():
            attached_paths.append(str(p.resolve()))
    if drawing_rel and drawing_rel != iso_rel:
        p = MANIFEST_PATH.parent / drawing_rel
        if p.exists():
            attached_paths.append(str(p.resolve()))

    text = (
        f"BRIEF: {brief.get('brief_text','(no text)')}\n\n"
        f"Reference image(s) attached below. Filesystem paths for load_local_image:\n"
    )
    for p in attached_paths:
        text += f"  {p}\n"
    text += (
        "\nProduce a structured feature decomposition per the SKILL output "
        "format. No building, no Onshape mutations. Output only the OVERVIEW "
        "/ ENVELOPE / FEATURE TREE / RELATIONSHIPS / UNCERTAINTIES sections, "
        "filled in."
    )
    blocks.append({"type": "text", "text": text})

    for p in attached_paths:
        blocks.append({"type": "text", "text": f"\n[attached: {p}]"})
        blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(Path(p).read_bytes()).decode(),
            },
        })
    return blocks


async def _run_vision(brief: dict, out_dir: Path, max_turns: int = 30) -> dict:
    from claude_agent_sdk import (
        query,
        ClaudeAgentOptions,
        AssistantMessage,
        ResultMessage,
        SystemMessage,
        UserMessage,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = out_dir / "transcript.jsonl"
    transcript_path.write_text("")
    live_log = REPO / "eval" / "vision_live.log"

    def _log(kind: str, data: dict) -> None:
        with transcript_path.open("a") as f:
            f.write(json.dumps({"kind": kind, **data}, default=str) + "\n")

    def _live(line: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        with live_log.open("a") as f:
            f.write(f"{stamp} [{brief['brief_id']}|vision] {line}\n")

    # Keep Onshape env so MCP server starts, but the agent will be tool-disallowed
    # from the mutation tools. Cheapest way to reuse the existing MCP surface
    # for just load_local_image + crop_image.
    mcp_env = {}
    for name in ("PATH", "HOME", "ONSHAPE_API_KEY", "ONSHAPE_API_SECRET"):
        if os.getenv(name):
            mcp_env[name] = os.environ[name]

    skill = VISION_SKILL_PATH.read_text()
    system_prompt = (
        "You are a vision-decomposition analyst. Follow the SKILL below "
        "exactly. Do NOT build anything, do NOT call any Onshape mutation "
        "tool, do NOT export. Output the structured feature tree only.\n\n"
        + skill
    )

    options = ClaudeAgentOptions(
        mcp_servers={
            "onshape": {
                "type": "stdio",
                "command": "uv",
                "args": ["--directory", str(REPO), "run", "onshape-mcp"],
                **({"env": mcp_env} if mcp_env else {}),
            }
        },
        # Disallow anything that could mutate. Allow only load_local_image +
        # crop_image from the Onshape MCP server, and safe reads.
        disallowed_tools=[
            # CAD build/export — all blocked
            "mcp__onshape__create_*",
            "mcp__onshape__update_feature",
            "mcp__onshape__delete_*",
            "mcp__onshape__export_*",
            "mcp__onshape__write_featurescript_feature",
            "mcp__onshape__set_*",
            "mcp__onshape__transform_*",
            "mcp__onshape__add_assembly_instance",
            "mcp__onshape__align_instance_to_face",
            "mcp__onshape__render_part_studio_views",
            "mcp__onshape__render_assembly_views",
            "mcp__onshape__describe_part_studio",
            "mcp__onshape__get_*",
            "mcp__onshape__find_*",
            "mcp__onshape__list_*",
            "mcp__onshape__measure",
            "mcp__onshape__eval_featurescript",
            "mcp__onshape__check_assembly_interference",
            "mcp__onshape__compare_to_reference",
            "mcp__onshape__extract_drawing_dimensions",
            # System tools not relevant
            "Bash", "Edit", "MultiEdit", "Write", "WebFetch", "WebSearch",
            "Task", "NotebookEdit", "KillShell", "BashOutput",
            "mcp__claude.ai_*", "mcp__plugin_*",
        ],
        permission_mode="bypassPermissions",
        system_prompt=system_prompt,
        max_turns=max_turns,
        setting_sources=[],
        thinking={"type": "enabled", "budget_tokens": 8192},
        max_buffer_size=16 * 1024 * 1024,
    )

    prompt_blocks = _compose_vision_prompt(brief)
    print(f"[vision] brief={brief['brief_id']}", flush=True)
    _live(f"START ({len(prompt_blocks)} prompt blocks)")

    turn_ix = 0
    last_result: Any = None
    final_text_chunks: list[str] = []

    async def _prompts():
        yield {"type": "user", "message": {"role": "user", "content": prompt_blocks}}

    async for message in query(prompt=_prompts(), options=options):
        if isinstance(message, SystemMessage):
            _log("system", {"subtype": message.subtype, "data": message.data})
            continue

        if isinstance(message, AssistantMessage):
            turn_ix += 1
            if turn_ix > max_turns:
                _log("hard_turn_cap", {"turn": turn_ix, "cap": max_turns})
                _live(f"t{turn_ix} ⛔ hard turn cap (max={max_turns})")
                break
            for block in message.content:
                btype = getattr(block, "type", None) or block.__class__.__name__
                if btype in ("text", "TextBlock"):
                    text = getattr(block, "text", "")
                    _log("assistant_text", {"turn": turn_ix, "text": text})
                    if text.strip():
                        print(f"\n[turn {turn_ix}] 💬 {text}\n", flush=True)
                        _live(f"t{turn_ix} 💬 {text.strip()[:500]}")
                        final_text_chunks.append(text)
                elif btype in ("tool_use", "ToolUseBlock"):
                    name = getattr(block, "name", "?")
                    inp = getattr(block, "input", {})
                    _log("tool_use", {"turn": turn_ix, "name": name, "input": inp})
                    preview = json.dumps(inp, default=str)[:180]
                    print(f"[turn {turn_ix}] → {name}({preview})", flush=True)
                    _live(f"t{turn_ix} → {name}({preview})")
            continue

        if isinstance(message, UserMessage):
            for block in getattr(message, "content", []) or []:
                btype = getattr(block, "type", None) or block.__class__.__name__
                if btype in ("tool_result", "ToolResultBlock"):
                    content = getattr(block, "content", "")
                    text_preview = ""
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                text_preview += c.get("text", "")
                    elif isinstance(content, str):
                        text_preview = content
                    _log("tool_result", {"turn": turn_ix,
                                         "text_preview": text_preview[:1200]})
                    short = text_preview.strip().splitlines()[0] if text_preview.strip() else ""
                    print(f"[turn {turn_ix}] ← {short[:200]}", flush=True)
                    _live(f"t{turn_ix} ← {short[:200]}")
            continue

        if isinstance(message, ResultMessage):
            _log("result", {
                "subtype": message.subtype,
                "result": getattr(message, "result", None),
                "usage": getattr(message, "usage", None),
            })
            last_result = message

    # The "final output" is the last assistant_text chunk that contains
    # the structured sections (look for "## OVERVIEW" anchor).
    final_spec = ""
    for chunk in reversed(final_text_chunks):
        if "## OVERVIEW" in chunk or "## FEATURE TREE" in chunk:
            final_spec = chunk
            break
    if not final_spec and final_text_chunks:
        # Fall back: concatenate all chunks in order
        final_spec = "\n\n".join(final_text_chunks)

    return {
        "turns": turn_ix,
        "final_spec": final_spec,
        "subtype": getattr(last_result, "subtype", None) if last_result else None,
    }


def run_vision(brief_id: str, out_root: Optional[Path] = None,
               max_turns: int = 30) -> dict:
    brief = _load_brief(brief_id)
    out_root = out_root or OUTPUT_DIR
    out_root.mkdir(parents=True, exist_ok=True)

    ts = int(time.time())
    run_tag = f"{ts}-vision-{brief_id}"
    run_dir = out_root / run_tag
    t0 = time.monotonic()
    summary = asyncio.run(_run_vision(brief=brief, out_dir=run_dir,
                                      max_turns=max_turns))
    elapsed = time.monotonic() - t0

    # Save final spec at a predictable path (brief_id.txt in OUTPUT_DIR)
    spec_path = OUTPUT_DIR / f"{brief_id}.txt"
    spec_path.write_text(summary["final_spec"] or "(no structured spec produced)")

    # Also save summary metadata.
    (run_dir / "summary.json").write_text(json.dumps({
        "brief_id": brief_id,
        "turns": summary["turns"],
        "elapsed_s": round(elapsed, 1),
        "final_spec_chars": len(summary["final_spec"] or ""),
        "final_spec_path": str(spec_path.relative_to(REPO)),
    }, indent=2))

    print(f"\n[vision] done in {elapsed:.1f}s, {summary['turns']} turns")
    print(f"[vision] final spec: {spec_path}")
    return summary


def _cli() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--brief-id", required=True)
    p.add_argument("--max-turns", type=int, default=30)
    args = p.parse_args()
    run_vision(brief_id=args.brief_id, max_turns=args.max_turns)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
