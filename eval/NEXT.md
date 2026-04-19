# Where to pick up — pre-compaction handoff (2026-04-19)

**CRITICAL**: Context was at 56% when this was written, compaction imminent.
Read this + SESSION_NOTES.md + CLAUDE.md before doing ANYTHING. Do not
re-derive state from `scoreboard.jsonl` alone — that misses the pivot.

---

## The one-paragraph summary

We spent a long session building SKILL/tool/dataset mutations (v001 → v009) and learned that the **agent's visual reasoning about engineering drawings is the bottleneck**, not CAD generation. Concretely: when Opus 4.7 gets the reference image decomposition right, it builds a decent part; when it doesn't, it builds something unrelated. v001 (plan-from-render SKILL) is the only kept mutation. Hard tier remains flat ~0.03 across everything we tried.

Shef's insight that drove the current pivot: "the main issue is image understanding more than CAD generation at this point. everything it generates is somewhat OK, but understanding WHAT it needs to do is not amazing." He proposed a sub-skill that does rigorous zoom/pan decomposition as a vision-only phase, separate from the CAD-building phase. We built it. It's NOT YET RUN END-TO-END — Shef wants to manually check the vision output on the test scripts before feeding into a full CAD run.

## Current state of the repo (autoresearch branch)

```
autoresearch
├── eval/
│   ├── skills/vision/SKILL.md              ← NEW: sub-skill for vision-only agent
│   ├── runner/
│   │   ├── run_brief.py                    ← CAD agent runner (existing)
│   │   └── run_vision.py                   ← NEW: vision-only sub-agent runner
│   ├── tests/
│   │   ├── _run_vision.sh                  ← NEW: shared runner helper
│   │   └── test_vision_<brief_id>.sh       ← NEW: one per non-seed brief
│   ├── vision_outputs/                     ← Vision specs land here (brief_id.txt)
│   ├── datasets/
│   │   ├── MANIFEST.json                   ← brief list (sealed)
│   │   ├── EVAL_SET.json                   ← eval_v3, MM-led hard tier
│   │   └── {seed,nist_pmi,modelmania}/     ← STEPs + PNGs
│   ├── grader/                             ← LOCKED v5 (rotation + translation invariant)
│   ├── variants/v001-...v009-...           ← variant SKILL.md trees
│   └── runs/<ts>-<variant>/<brief>/        ← per-run scores + transcripts
├── onshape_mcp/                            ← product MCP. DO NOT TOUCH unless a tool is missing.
│   └── api/
│       ├── rendering.py                    ← compose_reference_comparison, load_local_image, crop_cached_image
│       └── drawing_ocr.py                  ← Tesseract OCR (not-currently-used-in-v009+ but kept)
└── CLAUDE.md                               ← read this EVERY fresh session
```

## What the vision sub-skill does (newly shipped, UNTESTED end-to-end)

Separate Claude Agent SDK session. Model: Opus 4.7 (NOT Haiku — per Shef: "the whole premise is that Claude Opus 4.7 is better at visual reasoning"). Tools allowed: `load_local_image` + `crop_image` only (all mutation tools explicitly disallowed via a wildcard ban list in run_vision.py).

**Mandatory output format** (enforced by SKILL):
```
## OVERVIEW — one sentence about what the part IS
## ENVELOPE — approximate overall dims in mm (or "UNKNOWN")
## FEATURE TREE
F1: <name>
  type: base-plate | boss | through-hole | blind-hole | pocket | slot | fillet | chamfer | counterbore | countersink | shell | rib | taper | thread | other
  role: primary | secondary | subtractive | cosmetic
  size: mm (diameter / length×width / radius)
  position: fraction of envelope OR relative to another feature
  face: top/bottom/front/back/left/right/+Z-face-of-F3
  orientation: axis direction
  count: 1 or N for patterns
  dim_source: drawing_callout | render_inferred
  notes: tolerance / finish / anything unusual
F2: ...
## RELATIONSHIPS — F4 (hole) is cut INTO F1 (plate), etc.
## UNCERTAINTIES — what the agent wasn't sure about (important signal)
```

## How Shef will test vision quality (the immediate next step)

He wants to MANUALLY run individual briefs through the vision sub-agent and look at the output. The scripts:

```bash
./eval/tests/test_vision_mm_2021_drawing.sh        # Model Mania 2021 drawing
./eval/tests/test_vision_nist_ctc_01_drawing.sh    # NIST CTC 01 (the bad one from before)
./eval/tests/test_vision_mm_2019_envelope.sh       # MM 2019 envelope-only
# etc — 30 scripts, one per non-seed brief
```

Each script prints the agent turn-by-turn to stdout and dumps the final structured spec to `eval/vision_outputs/<brief_id>.txt`. Default turn budget: 30 (agent should finish well under this). Pass a number as $1 to override.

**Expected cost**: each run is ONE Opus conversation, maybe 10-20 turns of crop_image calls + some thinking. No Onshape API, no STEP exports. Should be maybe 3-8 minutes and $1-3 per brief. Way cheaper than a full CAD run.

## What we did NOT yet do

1. **Hook the vision spec into the CAD agent.** The vision output is saved to a file; nothing currently prepends it to a CAD run's prompt. That's the next implementation step AFTER Shef validates the spec quality manually.
2. **Run any vision test end-to-end.** The runner imports cleanly and the prompt composes; but no test script has been executed yet. Shef may want to run a handful and look at outputs before we commit more.
3. **Handle the vision spec → CAD handoff format.** Current plan: once specs look good, modify `eval/runner/run_brief.py` to (a) call `run_vision` as phase 1 if the variant's config says so, and (b) prepend the `eval/vision_outputs/<brief_id>.txt` content to the CAD agent's user prompt as "VISION REPORT (authoritative)".

## If a test produces a bad spec

Likely causes, in order of probability:
1. Agent didn't crop — it just did overview. Fix: tighten SKILL's step 3 more.
2. Agent tried to build. Fix: check the disallowed_tools list actually caught the call; if not, add the missing tool name.
3. Agent ran out of turns mid-description. Fix: raise --max-turns or reduce the crop target count in SKILL.
4. Output was free-form prose not the structured format. Fix: SKILL's "output only the structured response" isn't strong enough — maybe require JSON schema constrained output.

Don't chase these until we have a failed run to look at. Premature abstraction.

## Scoreboard state (unchanged from earlier today)

```
easy baseline                  : 0.978-1.00 (saturated)
medium baseline                : 0.155 (n=1)
medium v001-plan-from-render   : 0.193 (n=2 clean, KEPT — only real win)
medium v002 grader-aware-count : 0.189 (REVERTED)
medium v003 render-compare-loop: 0.155 (REVERTED)
hard baseline                  : 0.030 (n=1)
hard v004 compare_to_ref tool  : 0.042 (n=1, marginal)
hard v005 dim-crosscheck       : 0.035 (n=1)
hard v006 crop-the-callouts    : broken/abandoned
hard v008 OCR-tool + dataset   : did not complete (API slowness)
hard v009 prompt-side-OCR      : killed mid-startup, untested
```

## Anti-patterns to avoid (hard-earned this session)

- **Don't bloat SKILL.md.** v008 had a 30-line new section → agent grinds 10+ min/turn on accumulated context.
- **Don't add more tools the agent "might use."** Every tool in the allowlist increases per-turn decision cost. Be surgical.
- **Don't re-test a variant in the same session you proposed it** — quota and time. Queue for manual review.
- **Don't chase the grader.** L4=0 on hard is HONEST signal that the build is wrong, not a grader flaw. Already fixed rotation + translation invariance in grader v5; no more grader twiddles without a concrete-bad case.
- **Don't use Haiku for vision.** Per Shef: the premise of this project is that Opus 4.7 is best at visual reasoning. Downgrading the vision model defeats the point.

## Env + health checks before running anything

```bash
cd /Users/shef/projects/claude-onshape-mcp
git log --oneline -5                                    # recent commits
test -f .env && echo "env OK" || echo "env MISSING"
eval/.venv/bin/python -c "import claude_agent_sdk, anthropic, pytesseract, PIL; print('deps OK')"
# Quick API responsiveness probe (~2s, costs a few cents):
echo "test" | timeout 30 claude -p "hi" --max-turns 1 --tools "" --output-format json | jq .duration_ms
# Should return < 5000ms. If hanging or much slower, upstream is having a bad day.
```

## Git state / branch

- Branch: `autoresearch`
- Last commit: vision sub-skill + sub-agent runner + CLI test scripts (77ce2ac-ish)
- Main branch: untouched (we never merge TO main from here)
- Sketch-constraints branch: an unrelated product PR; leave alone

## If starting completely fresh

1. Read `CLAUDE.md` top to bottom. Especially the "NOT vanilla Karpathy" section.
2. Read `eval/SESSION_NOTES.md` (long but load-bearing).
3. Read this file.
4. Run the env check above.
5. Pick ONE test script and run it. Watch the output. Decide with Shef whether the spec is usable.
6. Iterate on SKILL.md / runner one change at a time. Do not batch multiple speculative changes.

## Anchors / files to never break

- `eval/datasets/MANIFEST.json` — sealed brief set
- `eval/grader/*` — LOCKED v5 (don't touch without bumping version + regrading)
- `eval/grader/GRADER_HASH` — version file
- `onshape_mcp/api/*` — product code; only grow tools if a vision phase needs them
- `.env` — gitignored, contains Onshape creds
