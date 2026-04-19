# Where to pick up — next session

Status as of 2026-04-19 wrap:
- Working tree clean. All commits pushed locally to `autoresearch`.
- v001-plan-from-render is the only KEPT mutation (medium tier).
- Hard tier flat at 0.020-0.042 across baseline + 5 variants.
- Loop iteration cost has crept up (30+ min/brief on bigger variants); $5-20 in API quota per iteration.

## Highest-leverage things to try next (in priority order)

### 1. v010-polish-pass (cheap, predicted +0.05-0.10 on medium)

**Diagnostic**: ctc_05 v001 build has 0 torus, 0 cone, 0 sphere faces vs reference's 6 / 13 / 4. Entire fillet/chamfer/round-boss surface family is missing.

**Mutation**: SKILL.md addition that REQUIRES the agent to do a polish pass at the end of every build:
- Enumerate all sharp edges
- Apply fillets (R3 default if no callout) to ALL outer body edges
- Apply small chamfers to inner-bore openings

This is a small SKILL change but targets a verifiable structural gap, not a vague hint. Build it on v001 parent.

### 2. v011-prompt-side-ocr-retry (untested due to API issue)

v009 was the right idea but never produced a scoreboard line. Retry it on a calm-API morning. The runner already pre-extracts callouts into the prompt text — just relaunch:
```
eval/.venv/bin/python eval/runner/run_eval_set.py \
    --variant-id v009-prompt-side-ocr \
    --parent-variant-id baseline \
    --mutation-description "harness pre-extracts OCR callouts into prompt text"
```

### 3. v012 = v001 + v010 + v009 (the synthesis)

If both v009 and v010 individually move the needle, combine them into v012 with all three architectural changes layered. This is the KEEP-track-best result for the curriculum.

## What NOT to do

- More SKILL-text word-tweaks. Per Shef ruling 2026-04-18 (in CLAUDE.md): the 30-min/iter cost makes small variations bad ROI. Keep variations to architectural moves (new tool, new feedback loop, new dataset cut).
- Don't try to crack hard tier from this branch. The single-iso-render → 3D inference is a vision-model bottleneck not a prompt bottleneck. Hard tier should be a leaderboard sanity check, not an optimization target.
- Don't relax the grader to make scores look better. The L4=0 wall is honest signal.

## Quick health checks before any new run

```
# 1. API responsive?
echo "test" | timeout 30 claude -p "hi" --max-turns 1 --tools "" --output-format json | jq .duration_ms
# Expect < 5000

# 2. Eval venv intact?
eval/.venv/bin/python -c "from eval.grader.compare_step import load_step; print('ok')"

# 3. Latest scoreboard (sanity check tier/scores)
tail -3 eval/scoreboard.jsonl | python3 -c "import sys,json
for ln in sys.stdin:
    d = json.loads(ln)
    print(f\"{d['timestamp']} {d['variant_id']} mean={d['mean_composite']:.3f}\")"
```

## Cost discipline

A full hard-tier run is ~3 briefs × 60-100 turns × Opus 4.7 1M context.
Cache-creation input alone runs $0.30-0.50 per FRESH call. Output tokens
+ thinking budget add multiples on top. Estimate: $10-30 per variant
evaluation. **Always confirm with Shef before launching variants in a
session — don't burn quota on speculation.**
