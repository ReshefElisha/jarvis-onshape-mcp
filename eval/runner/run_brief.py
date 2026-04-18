"""Run ONE eval brief end-to-end.

Flow:
  1. Load brief from MANIFEST.json by brief_id.
  2. Gather context the agent should see:
       - brief text
       - brief_image_path (drawing sheet, if any)
       - reference_png_path (iso multi-view render, always)
  3. Load the variant's SKILL.md (falls back to plugin's current skill).
  4. Spawn Claude Agent SDK against the onshape MCP subprocess with that
     context + skill, cap at 50 turns.
  5. The agent builds the part in a fresh Onshape doc. Ends by exporting
     a STEP via mcp__onshape__export_part_studio and writing the STEP
     bytes to a known path we told it about.
  6. Load agent's STEP + reference STEP, call the grader, write scores.json.
  7. Append one line to scoreboard.jsonl.

Output dir layout:
  eval/runs/<timestamp>-<variant>/<brief_id>/
    transcript.jsonl     — full agent message log
    brief.txt            — the text portion of the brief (+ image list)
    agent.step           — agent's final STEP
    reference.step       — symlink or copy of the manifest reference
    scores.json          — {composite, layers, notes} from the grader
    summary.json         — turn count, agent subtype, doc ids, mcp stats
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
load_dotenv(REPO / ".env")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Force line-buffered stdout so `tail -F` sees output in real time even when
# this process's stdout is a pipe (e.g. backgrounded via shell redirection).
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

from eval.grader.rubric import score_step_pair


MANIFEST_PATH = REPO / "eval" / "datasets" / "MANIFEST.json"
DEFAULT_SKILL_PATH = REPO / "skills" / "onshape" / "SKILL.md"
SCOREBOARD_PATH = REPO / "eval" / "scoreboard.jsonl"
GRADER_HASH_PATH = REPO / "eval" / "grader" / "GRADER_HASH"


def _load_brief(brief_id: str) -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text())
    for b in manifest["briefs"]:
        if b["brief_id"] == brief_id:
            return b
    raise KeyError(f"brief_id {brief_id!r} not in manifest")


def _resolve_skill(variant_id: Optional[str]) -> str:
    """Load the SKILL.md the agent will operate under.

    If `variant_id` is set, look for `variants/<variant_id>/skills/onshape/SKILL.md`;
    else fall back to the plugin's current skill.
    """
    if variant_id and variant_id != "baseline":
        p = REPO / "eval" / "variants" / variant_id / "skills" / "onshape" / "SKILL.md"
        if p.exists():
            return p.read_text()
    return DEFAULT_SKILL_PATH.read_text()


def _grader_hash() -> str:
    return GRADER_HASH_PATH.read_text() if GRADER_HASH_PATH.exists() else "unknown"


def _compose_prompt(brief: dict, agent_step_target: Path) -> list[dict]:
    """Build the user prompt as a list of content blocks (text + images).

    Every available image attaches: brief_image_path (drawing) + reference_png_path
    (iso multi-view render). Agent gets max context.
    """
    blocks: list[dict] = []

    # Text goes first so the image(s) land under it in the agent's view.
    text = brief["brief_text"] + (
        "\n\n"
        "WHEN FINISHED: call mcp__onshape__export_part_studio to produce a STEP "
        "file, then write the STEP bytes returned by that tool to the local path "
        f"{agent_step_target!s} using the Write tool. Then reply DONE in plain "
        "text and stop using tools. Do NOT skip the local Write — the grader "
        "reads the STEP from disk, not from Onshape."
    )
    blocks.append({"type": "text", "text": text})

    # Attach drawing sheet (if this brief has one).
    drawing_rel = brief.get("brief_image_path")
    if drawing_rel:
        dp = MANIFEST_PATH.parent / drawing_rel
        if dp.exists():
            blocks.append({
                "type": "text",
                "text": f"\n[attached: engineering drawing sheet — {drawing_rel}]",
            })
            blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(dp.read_bytes()).decode(),
                },
            })

    # Always attach the iso render so the agent has a 3D reference.
    iso_rel = brief.get("reference_png_path")
    if iso_rel:
        ip = MANIFEST_PATH.parent / iso_rel
        if ip.exists() and (not drawing_rel or iso_rel != drawing_rel):
            blocks.append({
                "type": "text",
                "text": f"\n[attached: reference iso/front/top/right multi-view — {iso_rel}]",
            })
            blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(ip.read_bytes()).decode(),
                },
            })

    return blocks


async def _run_agent(
    brief: dict,
    variant_id: Optional[str],
    out_dir: Path,
    agent_step_target: Path,
    max_turns: int,
) -> dict:
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
    # Canonical pretty-formatted event log. `tail -F eval/live.log` from
    # anywhere = watch the currently-running agent's thought stream.
    live_log = REPO / "eval" / "live.log"
    live_log.parent.mkdir(parents=True, exist_ok=True)

    def _log(kind: str, data: dict) -> None:
        with transcript_path.open("a") as f:
            f.write(json.dumps({"kind": kind, **data}, default=str) + "\n")

    def _live(line: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        with live_log.open("a") as f:
            f.write(f"{stamp} [{brief['brief_id']}|{variant_id or 'baseline'}] {line}\n")

    skill = _resolve_skill(variant_id)
    system = (
        "You are an engineering CAD designer driving Onshape through MCP tools.\n"
        "First call create_document + create_part_studio to set up a fresh "
        "workspace. Thread (documentId, workspaceId, elementId) through every "
        "subsequent tool call.\n"
        "Iterate: propose feature → call tool → describe_part_studio to verify "
        "→ fix or proceed. When the part matches the brief, export STEP and "
        "write it to disk per the user's instructions.\n"
        "Protocol (follow strictly):\n\n" + skill
    )

    mcp_env: dict[str, str] = {}
    for name in ("ONSHAPE_ACCESS_KEY", "ONSHAPE_SECRET_KEY",
                 "ONSHAPE_API_KEY", "ONSHAPE_API_SECRET"):
        if os.getenv(name):
            mcp_env[name] = os.environ[name]

    options = ClaudeAgentOptions(
        mcp_servers={
            "onshape": {
                "type": "stdio",
                "command": "uv",
                "args": ["--directory", str(REPO), "run", "onshape-mcp"],
                **({"env": mcp_env} if mcp_env else {}),
            }
        },
        disallowed_tools=[
            "Bash", "Edit", "MultiEdit", "WebFetch", "WebSearch",
            "Task", "NotebookEdit", "KillShell", "BashOutput",
            "mcp__claude.ai_*", "mcp__plugin_*",
        ],
        # Write IS allowed — the agent needs it to save the final STEP.
        permission_mode="bypassPermissions",
        system_prompt=system,
        max_turns=max_turns,
        setting_sources=[],
        # Enable extended thinking so we can watch the agent reason before
        # each action. 8192 tokens is plenty for CAD-build reasoning.
        # SDK expects a dict shape, not a bare bool.
        thinking={"type": "enabled", "budget_tokens": 8192},
    )

    prompt_blocks = _compose_prompt(brief, agent_step_target)
    (out_dir / "brief.txt").write_text(
        brief["brief_text"] + "\n\n--- images attached ---\n"
        + "\n".join(b.get("text", "<image>") for b in prompt_blocks if b.get("type") in ("text", "image"))
    )

    print(f"[run] brief={brief['brief_id']} variant={variant_id or 'baseline'}", flush=True)

    turn_ix = 0
    last_result: Any = None
    doc_ids: dict[str, Optional[str]] = {"document_id": None,
                                          "workspace_id": None,
                                          "part_studio_id": None}

    async def _prompts():
        yield {
            "type": "user",
            "message": {"role": "user", "content": prompt_blocks},
        }

    async for message in query(prompt=_prompts(), options=options):
        if isinstance(message, SystemMessage):
            _log("system", {"subtype": message.subtype, "data": message.data})
            continue

        if isinstance(message, AssistantMessage):
            turn_ix += 1
            if turn_ix > max_turns:
                # Belt-and-suspenders cap: the SDK's max_turns isn't reliably
                # enforced across CLI versions. Hard-stop here so one runaway
                # brief can't burn the whole budget.
                _log("hard_turn_cap", {"turn": turn_ix, "cap": max_turns})
                _live(f"t{turn_ix} ⛔ hard turn cap (max={max_turns})")
                break
            for block in message.content:
                btype = getattr(block, "type", None) or block.__class__.__name__
                if btype in ("thinking", "ThinkingBlock"):
                    thinking = getattr(block, "thinking", "") or ""
                    _log("thinking", {"turn": turn_ix, "thinking": thinking})
                    if thinking.strip():
                        print(f"\n[turn {turn_ix}] 🧠 thinking:\n{thinking}\n", flush=True)
                        _live(f"t{turn_ix} 🧠 {thinking.strip()[:800]}")
                elif btype in ("text", "TextBlock"):
                    text = getattr(block, "text", "")
                    _log("assistant_text", {"turn": turn_ix, "text": text})
                    if text.strip():
                        print(f"\n[turn {turn_ix}] 💬 assistant:\n{text}\n", flush=True)
                        _live(f"t{turn_ix} 💬 {text.strip()[:500]}")
                elif btype in ("tool_use", "ToolUseBlock"):
                    name = getattr(block, "name", "?")
                    inp = getattr(block, "input", {})
                    _log("tool_use", {"turn": turn_ix, "name": name, "input": inp})
                    preview = json.dumps(inp, default=str)[:180]
                    print(f"[turn {turn_ix}] → {name}({preview})", flush=True)
                    _live(f"t{turn_ix} → {name}({preview})")
                    # Scrape out the doc IDs the moment we see them.
                    if isinstance(inp, dict):
                        for k in ("documentId", "workspaceId", "elementId"):
                            if inp.get(k) and not doc_ids.get(
                                {"documentId": "document_id",
                                 "workspaceId": "workspace_id",
                                 "elementId": "part_studio_id"}[k]
                            ):
                                doc_ids[{"documentId": "document_id",
                                         "workspaceId": "workspace_id",
                                         "elementId": "part_studio_id"}[k]] = inp[k]
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

    return {
        "turns": turn_ix,
        "subtype": getattr(last_result, "subtype", None) if last_result else None,
        "doc_ids": doc_ids,
    }


def _grade(agent_step: Path, reference_step: Path) -> dict:
    if not agent_step.exists():
        return {
            "composite": 0.0,
            "layers": {},
            "notes": [f"agent STEP not found at {agent_step}"],
        }
    r = score_step_pair(agent_step, reference_step)
    return r.to_dict()


def run_brief(
    brief_id: str,
    variant_id: Optional[str] = None,
    out_root: Optional[Path] = None,
    max_turns: int = 50,
) -> dict:
    brief = _load_brief(brief_id)
    ref_step = MANIFEST_PATH.parent / brief["reference_step_path"]
    if not ref_step.exists():
        raise FileNotFoundError(f"reference STEP missing: {ref_step}")

    ts = int(time.time())
    run_tag = f"{ts}-{variant_id or 'baseline'}"
    out_dir = (out_root or (REPO / "eval" / "runs" / run_tag)) / brief_id
    out_dir.mkdir(parents=True, exist_ok=True)
    agent_step = out_dir / "agent.step"

    t0 = time.monotonic()
    summary = asyncio.run(_run_agent(
        brief=brief,
        variant_id=variant_id,
        out_dir=out_dir,
        agent_step_target=agent_step,
        max_turns=max_turns,
    ))
    elapsed_s = time.monotonic() - t0

    # Reference the manifest STEP alongside the agent STEP for eyeball diffs.
    try:
        (out_dir / "reference.step").write_bytes(ref_step.read_bytes())
    except Exception:
        pass

    scores = _grade(agent_step, ref_step)

    (out_dir / "scores.json").write_text(json.dumps(scores, indent=2, default=str))
    (out_dir / "summary.json").write_text(json.dumps({
        "brief_id": brief_id,
        "variant_id": variant_id,
        "elapsed_s": elapsed_s,
        **summary,
        "composite": scores.get("composite"),
    }, indent=2, default=str))
    return {
        "brief_id": brief_id,
        "variant_id": variant_id,
        "composite": scores.get("composite"),
        "elapsed_s": elapsed_s,
        "turns": summary.get("turns"),
        "subtype": summary.get("subtype"),
        "out_dir": str(out_dir),
        "scores": scores,
    }


def _cli() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--brief-id", required=True)
    p.add_argument("--variant-id", default=None, help="Variant id; omit for baseline.")
    p.add_argument("--max-turns", type=int, default=50)
    args = p.parse_args()
    result = run_brief(
        brief_id=args.brief_id,
        variant_id=args.variant_id,
        max_turns=args.max_turns,
    )
    print(json.dumps({k: v for k, v in result.items() if k != "scores"},
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
