# Session notes — AutoResearch harness

Running stream-of-consciousness between wake-ups. Write every interesting observation, even reverted mutations. This is the research record.

## 2026-04-18 — kickoff

Shef asked for the pivot. Research done in parent session:

**Karpathy AutoResearch** (github.com/karpathy/autoresearch, March 2026): minimal single-GPU nanochat loop where an external coding agent edits `train.py`, trains 5 min, grades val_bpb, keeps or reverts, "NEVER STOPs". Key guardrails — locked grader, single scalar, fixed budget, single editable file. Warnings: budget gaming, noise-driven keeps, early-step bias, prompt injection via logs. Karpathy is silent on LLM-judge; silence is a signal (don't use as primary).

**CAD eval datasets**:
- Text2CAD (HF `SadilKhan/Text2CAD`, CC BY-NC-SA) — 170k models × 4 NL tiers. Primary. Convert JSON→STEP via DeepCAD's `export2step.py`.
- CADPrompt (200 briefs, CadQuery scripts) — hand-curated, held-out sanity set.
- Fusion360 Gallery Reconstruction — has native STEP but no NL briefs; fallback.
- Model Mania — drawings public, solutions NOT. Hand-build a few.
- Rejected: ABC, SketchGraphs, CAD-SIGNet, CADTalk, CAD-Llama — all wrong shape.

**Grader design**: layered pass/fail stack using `cadquery-ocp`. L0 body exists → L1 volume ±5% → L2 bbox ±5% → L3 topology signature → L4 Boolean IoU ≥0.90 → L5 Chamfer distance ≤0.02×diag. Weights 0/0.15/0.15/0.15/0.35/0.20. Composite ∈ [0, 1].

**Dependency policy**: pure pip in `eval/.venv`. Datasets via direct `git clone` of source repos (DeepCAD, Text2CAD, CADPrompt). No other install steps.

**Community leaderboard**: does not exist. We're building the first honest "LLM-agent → real CAD kernel → STEP" benchmark.

CLAUDE.md + eval/README.md now pinned. Directory scaffold in place. Next cold-session wake: start Phase 0 bootstrap.

## Decisions locked

- Branch `autoresearch` off main. Stays separate from sketch-constraints PR.
- First mutation scope: `skills/onshape/SKILL.md` only. Widen AFTER plateaus.
- Grader LOCKED after Phase 1 seal. Hash-check every run.
- 50-turn per-brief cap.
- 50-brief eval set in v1 manifest. Room to grow.

## Open questions (for Shef, non-blocking)

- License: Text2CAD is CC-BY-NC-SA. Commercial eventual? If so, we can keep Text2CAD-only for internal research but would need a commercial-clean set for public claims. Rebuild with Fusion360 Gallery + hand-curated NL annotations is the likely path.
- Compute budget: each Onshape CAD build is ~5–15 min real wall clock. 50-brief run × 3 variants × N iterations adds up. Shef OK with the Onshape API rate burn?
- Should Shef want visibility into the loop's progress without reading scoreboard.jsonl? Minimal dashboard (e.g. matplotlib-render to HTML every N iterations) is cheap to add later. Not Phase 0.

## Rulings from Shef

- **2026-04-18**: pip-only eval deps (`cadquery-ocp`). Datasets via direct `git clone`.

## 2026-04-18 — Phase 3 first baseline run, found dataset bug

First real baseline run (1776533407-baseline) on seed_04, 05, 06.
- seed_04_plate_one_hole: composite 1.0
- seed_05_plate_four_holes: composite 1.0
- seed_06_washer: composite 0.3 **due to dataset bug**, not agent failure

Two dataset bugs in seed_06_washer:

1. `build_kwargs={"h": 0.003}` — thickness was 3 micrometers instead
   of 3 mm. Reference washer volume was 1.59 mm³; agent built a proper
   1590 mm³ washer and was marked wrong. Fix: `h: 3.0`.

2. Brief said "Axis along world Z, centered on origin." The reference
   generator (cylinder + subtract) extrudes z=[0, h], not z=[-h/2, h/2].
   Agent sensibly interpreted "centered on origin" as fully centered
   (z=-1.5 to 1.5) while the reference was bottom-on-XY-plane. Disagreement
   shows up as L4 IoU ≈ 0.33 (volumes match, positions offset by h/2).
   Fix: tightened brief to match the standoff brief's phrasing
   ("base on the XY plane centered on origin").

Also: bootstrap_seed.py rewrites MANIFEST.json wholesale when rerun.
That clobbers the NIST + Model Mania entries. Left as known issue;
patched seed_06 surgically in MANIFEST instead of letting bootstrap
overwrite. TODO: make bootstrap_seed.py merge rather than replace.

First scoreboard entry (1776533407) flagged `invalid: true`. Launching
rerun next.

**Lesson for the loop**: regressions in the dataset are invisible to
the loop agent and corrupt the signal. The grader catches agent bugs;
only human review catches reference bugs. Phase 3's manual-read pass
is load-bearing.

## 2026-04-18 — grader v4: bbox-center alignment for L4/L5

Instead of tightening brief wording to force position agreement
(seed_06 "centered on origin" vs seed_08 Y-placement), fixed the grader:
`boolean_iou` and `chamfer_distance` now translate A so its bbox center
sits on top of B's before computing. Captures the principle: a brief
describes a shape, not its world-frame placement — two agents that
build the same part at different translations should score the same.

Rotation is NOT canceled out — briefs typically specify orientation
(e.g. "axis along Z"), so a wrong-axis build is still a real failure.

Grader version 3 → 4. GRADER_HASH updated. All prior run artifacts
regraded in place (`scores.json` rewritten, `mean_composite` in
scoreboard.jsonl updated, `regraded_with_grader_version: 4` added).

Final baseline picture on easy tier (2 runs, 6 briefs, 1 overlap with
the invalid first entry):

| run       | brief_set                                         | mean  |
|-----------|---------------------------------------------------|-------|
| 177653407 | plate_one_hole, plate_four_holes, washer          | 1.000 |
| 177654049 | standoff, l_bracket, slotted_strap                | 0.978 |

6/6 easy-tier briefs covered. Only non-1.0 is l_bracket at 0.933
— topology mismatch (agent: 8 faces, ref: 14 faces — agent's union
left fewer internal faces). That's a real topology difference,
picked up by L3 and L5. Not a grader bug.

Noise floor: with only 2 samples we can't compute variance properly,
but easy-tier baseline is clearly at/near the ceiling. That's what
Phase 3 was supposed to tell us. **Verdict: easy tier is effectively
solved by baseline; promote to medium tier before running more
baseline characterization.**

## 2026-04-18 — v001 results + agent interview

v001-plan-from-render on medium tier (3 NIST envelope briefs):
- nist_ctc_04: 0.15 (no change from baseline 0.15)
- nist_ctc_05: 0.29 (up from 0.17; volume within 0.67 L1 band)
- nist_ftc_06: 0.15 (no change from baseline 0.15; volume now 2.18× ref, was under)
- **mean 0.196** vs baseline 0.155 (+0.04, n=1, no noise floor → not yet significant)

**Agent-interview findings (tool-call counts per brief):**
- `describe_part_studio`: called only **1–2 times per brief** despite SKILL
  doc telling agents to call it "after every feature". The agent builds
  4–5 features end-to-end, then describes once near the end. That's the
  single biggest missed lever — without intermediate feedback small
  geometric errors compound and there's no path to catch them.
- `Read` of STEP paths: still 5–7 per brief even in v001. These runs were
  launched before my prompt-cleanup commit (d3898fc) that tells the agent
  the harness auto-copies the STEP. Future runs will save ~4 turns/brief.
- `ToolSearch`: 3–5 per brief. Agent repeatedly looks up Bash (disallowed)
  and tool schemas. Some of this is legit; Bash-escape is not.

**Why v001 didn't help much**: the render-planning section told agents to
list features before building but did not reinforce verify-after-each-feature.
ctc_05 got volume closer because planning helped proportion estimation;
ftc_06 got *farther* on volume because the agent enumerated features
from the render and over-estimated their sizes with no feedback loop.

**Next candidate mutation (v002)**: tighten describe_part_studio cadence
to a strict "after every feature that adds/removes volume" and lay out
what the agent should LOOK at in the output (bbox vs expectation, feature
count vs plan, new faces vs previous count).
