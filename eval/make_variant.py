"""Seed a new variant directory from the current baseline SKILL.md.

Usage:
    eval/.venv/bin/python eval/make_variant.py v001-describe-after-every-feature \
        --parent baseline \
        --desc "SKILL: elevate describe_part_studio from 'after every feature' to a hard-stop requirement"

Creates:
    eval/variants/v001-.../skills/onshape/SKILL.md       (copy of parent's SKILL.md)
    eval/variants/v001-.../VARIANT.md                    (mutation description + parent + timestamp)

Then you edit the SKILL.md in-place and run run_eval_set.py --variant-id v001-...
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VARIANTS = REPO / "eval" / "variants"
BASELINE_SKILL = REPO / "skills" / "onshape" / "SKILL.md"


def _resolve_parent_skill(parent_id: str) -> Path:
    if parent_id == "baseline":
        return BASELINE_SKILL
    p = VARIANTS / parent_id / "skills" / "onshape" / "SKILL.md"
    if not p.exists():
        raise SystemExit(f"parent variant not found: {p}")
    return p


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("variant_id", help="e.g. v001-describe-after-every-feature")
    p.add_argument("--parent", default="baseline",
                   help="variant_id of the parent to fork from (default: baseline)")
    p.add_argument("--desc", required=True, help="One-line mutation description")
    args = p.parse_args()

    target = VARIANTS / args.variant_id
    if target.exists():
        raise SystemExit(f"variant dir already exists: {target}")

    src = _resolve_parent_skill(args.parent)
    dst = target / "skills" / "onshape" / "SKILL.md"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

    meta = {
        "variant_id": args.variant_id,
        "parent_variant_id": args.parent,
        "created_at": int(time.time()),
        "mutation_description": args.desc,
        "source_skill": str(src.relative_to(REPO)),
    }
    (target / "VARIANT.md").write_text(
        f"# {args.variant_id}\n\n"
        f"- parent: `{args.parent}`\n"
        f"- created: {meta['created_at']}\n"
        f"- source: `{meta['source_skill']}`\n\n"
        f"## Mutation\n\n{args.desc}\n\n"
        f"## Metadata (JSON)\n\n```json\n{json.dumps(meta, indent=2)}\n```\n"
    )
    print(f"created {target.relative_to(REPO)}")
    print(f"  skill: {dst.relative_to(REPO)}")
    print(f"edit the skill, then:")
    print(f"  eval/.venv/bin/python eval/runner/run_eval_set.py \\")
    print(f"      --variant-id {args.variant_id} --parent-variant-id {args.parent} \\")
    print(f"      --mutation-description {json.dumps(args.desc)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
