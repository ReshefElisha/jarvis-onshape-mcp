"""Run a subset of the eval set for one variant, append scoreboard line.

Sampling policy:
  - Read eval/state.json to learn the current_tier (easy → medium → hard).
  - Sample `per_iteration_sample_size` briefs from that tier, rotating
    round-robin so consecutive iterations cover different briefs.
  - Run each via run_brief, collect composite scores, write aggregate.

Each scoreboard.jsonl line is one variant × one sampling pass:
  {
    "timestamp": "...",
    "variant_id": "v003-...",
    "parent_variant_id": "v002-...",
    "tier": "easy",
    "brief_ids": [...],
    "per_brief_composite": {brief_id: float, ...},
    "mean_composite": 0.73,
    "turns_sum": 120,
    "elapsed_s": 1842,
    "grader_hash_summary": "...",
    "mutation_description": "..."  # optional, set by the loop
  }

Usage:
    python eval/runner/run_eval_set.py --variant-id baseline
    python eval/runner/run_eval_set.py --variant-id v003-... --tier easy
    python eval/runner/run_eval_set.py --variant-id v003-... --full
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from eval.runner.run_brief import run_brief


EVAL_SET_PATH = REPO / "eval" / "datasets" / "EVAL_SET.json"
STATE_PATH = REPO / "eval" / "state.json"
SCOREBOARD_PATH = REPO / "eval" / "scoreboard.jsonl"
GRADER_HASH_PATH = REPO / "eval" / "grader" / "GRADER_HASH"


def _load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {
        "current_tier": "easy",
        "tier_stable_iterations": 0,
        "round_robin_cursor": {"easy": 0, "medium": 0, "hard": 0},
        "iteration": 0,
    }


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


def _pick_briefs(cfg: dict, state: dict, tier_override: Optional[str],
                 full: bool) -> tuple[str, list[str]]:
    tier = tier_override or state["current_tier"]
    pool = cfg["tiers"][tier]["brief_ids"]
    if full:
        return tier, list(pool)
    n = cfg["per_iteration_sample_size"]
    cursor = state["round_robin_cursor"].get(tier, 0)
    picks = []
    for i in range(n):
        picks.append(pool[(cursor + i) % len(pool)])
    state["round_robin_cursor"][tier] = (cursor + n) % len(pool)
    return tier, picks


def _grader_hash_summary() -> str:
    if not GRADER_HASH_PATH.exists():
        return "unknown"
    text = GRADER_HASH_PATH.read_text()
    # Take just the first line of each sha256sum line for compactness.
    lines = [ln for ln in text.splitlines() if ln.startswith("grader_version") or len(ln.split()) == 2]
    return " | ".join(lines)


def run_eval_set(
    variant_id: str,
    tier_override: Optional[str] = None,
    full: bool = False,
    parent_variant_id: Optional[str] = None,
    mutation_description: Optional[str] = None,
    max_turns: int = 100,
) -> dict:
    cfg = json.loads(EVAL_SET_PATH.read_text())
    state = _load_state()
    tier, brief_ids = _pick_briefs(cfg, state, tier_override, full)

    print(f"[eval_set] variant={variant_id} tier={tier} briefs={brief_ids}")

    ts = int(time.time())
    run_tag = f"{ts}-{variant_id}"
    out_root = REPO / "eval" / "runs" / run_tag

    per_brief: dict[str, float] = {}
    per_brief_detail: dict[str, dict] = {}
    turns_sum = 0
    t0 = time.monotonic()
    for bid in brief_ids:
        try:
            r = run_brief(brief_id=bid, variant_id=variant_id,
                          out_root=out_root, max_turns=max_turns)
            per_brief[bid] = r["composite"] or 0.0
            per_brief_detail[bid] = {
                "composite": r["composite"],
                "turns": r["turns"],
                "elapsed_s": r["elapsed_s"],
                "subtype": r["subtype"],
            }
            turns_sum += r["turns"] or 0
        except Exception as e:
            per_brief[bid] = 0.0
            per_brief_detail[bid] = {"error": f"{type(e).__name__}: {e}"}
            print(f"[eval_set] {bid} FAILED: {e}")
    elapsed_s = time.monotonic() - t0

    mean = sum(per_brief.values()) / max(len(per_brief), 1)
    line = {
        "timestamp": ts,
        "variant_id": variant_id,
        "parent_variant_id": parent_variant_id,
        "tier": tier,
        "full": full,
        "eval_set_id": cfg.get("eval_set_id"),
        "brief_ids": brief_ids,
        "per_brief": per_brief_detail,
        "mean_composite": mean,
        "turns_sum": turns_sum,
        "elapsed_s": round(elapsed_s, 1),
        "grader_hash_summary": _grader_hash_summary(),
        "mutation_description": mutation_description,
        "out_dir": str(out_root.relative_to(REPO)),
    }
    with SCOREBOARD_PATH.open("a") as f:
        f.write(json.dumps(line, default=str) + "\n")

    state["iteration"] = state.get("iteration", 0) + 1
    _save_state(state)

    print(f"[eval_set] mean_composite={mean:.3f}  elapsed={elapsed_s:.1f}s")
    return line


def _cli() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--variant-id", default="baseline")
    p.add_argument("--tier", choices=["easy", "medium", "hard"], default=None,
                   help="Override the tier to sample from (default: eval/state.json current_tier).")
    p.add_argument("--full", action="store_true",
                   help="Run every brief in the chosen tier, not just the iteration sample.")
    p.add_argument("--parent-variant-id", default=None)
    p.add_argument("--mutation-description", default=None)
    p.add_argument("--max-turns", type=int, default=100)
    args = p.parse_args()
    run_eval_set(
        variant_id=args.variant_id,
        tier_override=args.tier,
        full=args.full,
        parent_variant_id=args.parent_variant_id,
        mutation_description=args.mutation_description,
        max_turns=args.max_turns,
    )
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
