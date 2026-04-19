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

## 2026-04-18 — v002 result + direction change

v002 (grader-awareness + decompose-and-count) on medium tier:
- ctc_04: 0.15 (same as baseline + v001)
- ctc_05: 0.28 (v001 had 0.29)
- ftc_06: 0.13 (baseline 0.15, v001 0.15 — slight REGRESSION)
- **mean 0.189** vs v001 0.196 → REVERTED

Diagnostics on per-layer scores:
- **L4 Boolean IoU = 0 on all three briefs, every variant.** Even with
  bbox-center alignment, the agent's features never occupy the same
  3D regions as the reference. That's the real ceiling on medium tier.
  Agent cannot infer exact feature positions from an isometric render.
- L3 topology went UP on ctc_05 (0.25 → 0.10) — agent built FEWER faces
  in v002, which is strange given the "count at least N features"
  instruction. One hypothesis: grader-awareness text talked about
  "feature count" and agent conflated SKILL "features" (kernel-level
  faces/edges) with Onshape "features" (sketches+extrudes), and so
  built fewer Onshape features thinking that's what was being scored.
- L1 volume improved slightly on ctc_04 (7.9M→9.7M closer to 17.5M ref).
  Over-build instruction had some bite. Not enough to move composite
  because L1 contributes only 15% and L4/L5 still zero.

**Direction change:** SKILL.md-level mutations on prompt content are
hitting a ceiling because the bottleneck is positional/geometric
interpretation of the render, not feature-count awareness. The agent
already knows "more features = better" from v002's text and still
can't place them.

**Next mutation candidates (pick one):**
1. Push `crop_image` hard: force per-region inspection before placing
   each feature. Tell the agent to crop the render to a quadrant, count
   features in that quadrant, then place them with coordinates read
   from the cropped view.
2. Reference-render-after-each-feature loop: `render_part_studio_views`
   after every feature, call crop_image on matching regions of the
   reference, visually compare.
3. Widen mutation scope to server.py's _INSTRUCTIONS block (Phase 5+).
   Not yet — haven't plateaued on SKILL.md.

Leaning toward #2. The failure is *feedback*, not *planning*. Cost: more
turns per brief (already at 60-95/100). Might need to raise cap to 150.

Scoreboard:
  baseline (medium)       : 0.155
  v001-plan-from-render   : 0.196  KEPT (tentative, no noise floor)
  v002-grader-aware-count : 0.189  REVERTED

**Still need: medium-tier noise floor.** n=1 samples of each variant.
With only 3 briefs per iteration and stdev likely ~0.04, we can't
distinguish real gains from noise until we have repeats.

## 2026-04-18 — noise floor + 100-turn cap was the real problem

Ran v001 2× more for noise floor. Raw stdev: 0.054 (2σ = 0.109).
That would wipe out v001's apparent gain. But inspecting the three runs:

| run      | means | turns | notes |
|----------|-------|-------|-------|
| 77536557 | 0.196 | 68/76/73 | original |
| 77540649 | 0.189 | 45/97/84 | clean repeat |
| 77542569 | 0.098 | 48/101/100 | **hit 100-turn cap on 2 briefs** |

The third run's 0.098 is almost entirely harness-caused: 2 of 3 briefs
hit the 100-turn cap before exporting STEP → composite=0 for those. The
cap is biting at the exact boundary where a brief "would have finished."

Non-cap-hit noise floor: stdev 0.0046, 2σ = 0.0093. With that bound,
**v001's +0.041 gain over baseline IS significant** (4× above noise).

Fix: bumped max_turns default 100 → 150 everywhere (run_brief, run_eval_set,
their CLI defaults). 50-turn headroom means less frequent cap-hits; the
ones we still get are actually-stuck briefs, not just slow ones.

**Keep v001 as best-of-breed.** Current best for mutation tree:
  v001-plan-from-render (mean 0.193 over 2 clean runs)

## 2026-04-18 — v003 reverted; SKILL.md-text plateau hypothesis

v003 (per-feature render-compare loop) on medium:
- ctc_04: 0.15  (same)
- ctc_05: 0.16  (down from v001's 0.29 — regression)
- ftc_06: 0.15  (same)
- **mean 0.155** = same as baseline. REVERTED.

Diagnostics:
- v003 DID call describe_part_studio more: 4/3/5 vs v001's 1/2/2.
  Mutation landed as intended.
- **But L4 IoU = 0 on all 3 briefs, every variant, every time.** This is
  a hard wall. Even with feedback, the agent can't infer exact feature
  positions from a single iso render.
- ctc_05 regressed because v003 made the agent build a LARGER volume
  (19M vs 12.7M ref) to match more features from the render — trading
  L1 (volume) for more L3 (topology). Neither ended up covering L4.

**Plateau hypothesis: SKILL.md-text mutations cannot break the L4=0
ceiling on envelope-only medium-tier briefs.** The failure is positional
accuracy, which depends on either:
- **Explicit dimensions** → hard tier (drawings with GD&T) might unstick.
- **Better vision-to-3D inference** → model-level, not prompt-level.
- **Measurable tool feedback** → would need harness changes (Phase 5+).

Scoreboard update:
  baseline      : 0.155  (n=1)
  v001          : 0.193  (n=2 clean, KEPT as best)
  v002          : 0.189  (n=1) REVERTED
  v003          : 0.155  (n=1) REVERTED

**Next:** sample hard tier at baseline to see if drawings unstick the
L4=0 wall. If they do, SKILL mutations are useful there; if they
don't, the wall is positional accuracy overall and we should expand
mutation scope to server.py _INSTRUCTIONS (Phase 5) or add tool-level
help (a sanity-check measure? a harness hint?).

## 2026-04-18 — v004 compare_to_reference tool + hard tier results

Scope-widening: first tool-level mutation. Built `compare_to_reference`
MCP tool (onshape_mcp/api/rendering.py + server.py). Returns one
composite image: reference on top, agent's iso/top/front/right below.
Runner injects the reference absolute path into the agent prompt.

v004 on hard tier (nist_ctc_01/02/03 drawings):
- ctc_01: 0.064  (baseline 0.046)
- ctc_02: 0.0    (no export; likely cap or error)
- ctc_03: 0.019  (baseline 0.015)
- **mean 0.028** vs baseline 0.020 (+0.008)

Tool was used: 5/2/6 compare_to_reference calls per brief.
Agent substituted compare_to_reference for describe_part_studio (calls
dropped to 3/1/1).

**Two new problems the tool didn't solve:**

1. **Scale misreading.** Agent built ctc_01 at 200×37×100 mm vs ref
   800×450×150. That's 4× under-scaled. ctc_03 similar (172×228×1.5 vs
   320×534×163 — agent built a flat pancake). L2 bbox fails, not L4.
   Drawings specify dims numerically but the agent doesn't sanity-check.

2. **Tool bug in my composite**: `compose_reference_comparison` RESIZES
   the reference to match the agent-row width. That hides scale
   mismatch — a 800mm reference and a 200mm agent render look the same
   visual size in the composite. Need to either keep native scale or
   annotate each image with its dimensions.

**Shef's rotation-invariance point stands too**: some runs do have
correct-but-rotated parts that grader v4 marks at 0. Haven't hit that
case in hard tier (scale is dominating), but it's real.

**Scoreboard:**
```
medium baseline      : 0.155 (n=1)
medium v001          : 0.193 (n=2 clean, KEPT)
medium v002          : 0.189 (n=1, REVERTED)
medium v003          : 0.155 (n=1, REVERTED)
hard baseline        : 0.020 (n=1)
hard v004 (tool)     : 0.028 (n=1, marginal)
```

**Next:**
- Fix compose_reference_comparison to show dimensions + preserve scale
  ratios (annotate "REF 800×450×150 mm" / "YOU 200×37×100 mm" on the
  composite labels).
- Add rotation-invariant IoU to the grader (principal-axis
  canonicalization + try cubic symmetry rotations). Grader v5.
- Add explicit "verify your bbox dims against the drawing" to SKILL.

## 2026-04-18 — grader v5 (rotation invariance) + composite fix

Grader v5: L4 Boolean IoU and L5 Chamfer now try all 24 proper rotations
of the cube (axis permutations × sign flips with det = +1). Picks the
rotation that maximizes IoU. Shapes whose sorted bbox dims don't match
within 25% skip the rotation search (fast-path).

Regressions passed: a 90°-rotated copy of a reference STEP now scores
IoU 1.0 (vs 0.188 on grader v4). Reverse case (intentionally different
shapes) unaffected.

Regraded all runs. **No score changes** — none of the historical agent
builds were "correct-but-rotated." Shef's flag about CTC01 was either
fixed by the agent before export, or the part was wrong enough that
even rotation-aware IoU is 0. Still useful capability to have.

compose_reference_comparison fix: composite label now warns
"REFERENCE — dims from drawing callouts (NOT pixel size)" and stamps
"bbox X × Y × Z mm" on the agent row. Server handler fetches bbox in
parallel with rendering so no extra latency. This addresses the
200mm-agent-vs-800mm-ref scale-hiding bug I found after v004.

Grader hash bumped to v5. All prior scoreboard entries carry
`regraded_with_grader_version: 5` now. v001 still best on medium
(mean 0.193 over 2 clean runs).

## 2026-04-18 — v006 abandoned; pivoting

v006 (crop-the-callouts) hit two harness bugs:
1. Image dim limit (multi-image ≤ 2000px/side) — fixed by capping at 1568.
2. SDK stdout buffer 1MB cap — properly fixed by setting
   ClaudeAgentOptions.max_buffer_size=16MB on the runner side.

The fixed-fixed v006 run was killed before completing. Latest scored
v006 entry on scoreboard reflects the broken-fix attempt (mean 0.025
with 2/3 briefs erroring). **Not a valid signal — ignore for KEEP/REVERT.**

Decision: stop iterating on v006. The crop-the-callouts loop costs many
turns and the gains on the one brief that DID complete (ctc_01 0.075 vs
baseline 0.046) don't justify the regression risk on the others.

What we have learned end-to-end:
- SKILL-text mutations on medium tier cap out at v001 (~0.04 above
  baseline, n=2 clean).
- Tool-level additions (compare_to_reference, load_local_image) work
  but have integration costs (size limits, multi-image accumulation).
- Hard tier (drawings) baseline is near zero; gains on individual
  briefs are within noise.

**Next direction options:**
1. Re-run **v004** (compare_to_reference) on **medium tier** — it was
   designed for hard but the visual diff might also help on medium
   where L4=0 is the dominant failure.
2. Build a **v007** that drops the heavy crop loop and just uses
   compare_to_reference at strategic checkpoints.
3. Step back and add **MORE seed briefs** to lift the noise floor and
   give the loop more failure modes to mine.

## 2026-04-18 — session wrap: pivot from autoresearch loop

Bigger architectural moves made this session (per Shef ruling that this isn't
vanilla 5-min-iter Karpathy):

1. **CLAUDE.md** updated with the "this is not Karpathy" framing so future
   sessions don't slavishly tweak SKILL.md.
2. **MCP tool: `compare_to_reference`** — composites reference + agent build
   into one image, annotated with bbox-mm.
3. **MCP tool: `load_local_image`** — caches a filesystem image so the agent
   can `crop_image` into it at native resolution.
4. **MCP tool: `extract_drawing_dimensions`** — Tesseract OCR + grouping +
   kind classification (length/radius/diameter/thread/angle/count).
5. **Grader v5** — bbox-center alignment + 24-rotation-invariant L4/L5.
6. **Dataset rebalance v3** — hard tier led by Model Mania, NIST PMI dropped
   except one stretch brief. Per OCR diagnostic, NIST has 5-13 callouts/
   drawing (mostly lengths) vs Model Mania's 17-34 with radii/threads/etc.
   NIST PMI is genuinely too tortuous for agent eval.

**End-state scoreboard (regraded with grader v5):**
```
medium baseline      : 0.155 (n=1)
medium v001          : 0.193 (n=2 clean, KEPT)
medium v002          : 0.189 (n=1, REVERTED)
medium v003          : 0.155 (n=1, REVERTED)
hard baseline        : 0.030 (n=1)
hard v004            : 0.042 (n=1)
hard v005            : 0.035 (n=1)
hard v006            : 0.000 / 0.025 (broken; abandoned)
hard v007 (skipped)
hard v008            : did not complete (agent grinding 10+ min/turn
                       on bloated context, killed)
```

**Honest read on direction:**

- Easy tier saturated.
- Medium tier: only v001 plan-from-render is meaningfully above noise. All
  other variants in the noise band.
- Hard tier: every variant 0.020-0.042. Vision-to-3D ceiling on single
  iso/drawing renders is the wall — no SKILL or MCP-tool addition has
  moved a brief past 0.08.

**Why the loop is stalling**: the agent is bottlenecked on positional /
scale inference from a single rendered view. We're optimizing prompts and
tools around a vision-bottlenecked agent. Bigger architectural moves
(more tools, more compare cycles) don't help the underlying inference
gap and instead grow the context per turn, slowing the API and pushing
iteration time toward 30+ min/brief.

**Productive next directions (require bigger pivots, not more variants):**

1. **Use the eval as a benchmark, not a self-improvement loop.** Lock the
   dataset + grader, freeze the variant tree, ship the leaderboard so
   any model+SKILL combo can be scored. Stop trying to crack hard tier
   from this branch.
2. **Multi-agent / decomposition.** Have one agent extract dims, another
   plan, another build. Each gets a focused context. May fix the
   bloated-context problem.
3. **Test-time compute scaling.** Try N candidate builds per brief, score
   each, keep the best. Higher cost but might unlock parts of the score
   surface unreachable at N=1.
4. **Wait for vision model improvements** — the bottleneck is the
   underlying drawing-to-3D inference, not the prompt around it.

**This session: stopped iterating after v008 was killed. Recording all
findings, leaving v001 as the only kept mutation, marking subsequent
v002-v008 as either reverted or didn't-help.**

## 2026-04-18→19 — final diagnostic: face-kind diff

For ctc_05 (the brief where v001 helped most, 0.166 → 0.288):

| face kind | reference | v001 build | delta |
|-----------|-----------|------------|-------|
| cylinder  | 67        | 16         | -51   |
| plane     | 62        | 44         | -18   |
| sphere    | 4         | 0          | -4    |
| torus     | 6         | 0          | -6    |
| cone      | 13        | 0          | -13   |
| other     | 4         | 0          | -4    |

Agent built 50% of planes but 24% of cylinders, ZERO fillets (torus),
ZERO chamfers (cone), ZERO spherical features. The whole "rounded
transition" surface family is missing.

**Concrete future direction**: a "polish pass" SKILL section + tool —
after the agent's primary build, it must enumerate edges and propose
fillets/chamfers based on the reference. Even if the dimensions are
slightly off, having torus/cone faces present would lift L3 topology
+ L4 IoU (more surface coverage in the cut/intersect).

Combined with the OCR dim-extract harness pre-fill (v009's idea, just
not tested due to API slowness tonight), this could be a productive
v010 in a future session.

## 2026-04-19 — pivot to vision sub-skill (in progress, untested)

Shef reviewed build outputs vs references side-by-side and called it:
the bottleneck is image understanding, not CAD generation. A post-build
polish pass wouldn't help when the agent got the base shape topology
wrong (hex sitting ON instead of IN, T-extensions missing entirely,
giant through-holes instead of bolt-hole-within-boss, etc.).

Shef's proposed fix: a vision-only sub-skill that does rigorous zoom/
pan/describe BEFORE any CAD. NOT a one-shot Gemini-style description
(he tried that, it was worse than nothing). Structured multi-pass:
overview → count → zoom into each feature → describe role/size/
position → self-check coverage.

Briefly considered: use Haiku 4.5 to offload vision (cheaper, faster).
REJECTED per Shef: "the whole premise of building this is that Claude
Opus 4.7 is better at visual reasoning." Downgrading the vision model
undermines the bet. Keep Opus 4.7 for both phases, separate context.

**Shipped this commit:**
- `eval/skills/vision/SKILL.md` — sub-skill: hard rules (no build, no
  Onshape mutation), mandatory output format (OVERVIEW/ENVELOPE/TREE/
  RELATIONSHIPS/UNCERTAINTIES), workflow (overview → count → crop each
  → self-check → output), scope discipline (minimal allowlist).
- `eval/runner/run_vision.py` — standalone runner. Same Claude Agent
  SDK + Onshape MCP server (for load_local_image/crop_image), but
  disallowed_tools wildcards out all mutation/build/describe/measure
  tools. 30-turn cap. Final spec → `eval/vision_outputs/<brief_id>.txt`.
- `eval/tests/test_vision_<brief_id>.sh` × 30 — one per non-seed brief.
  Shef can run any of them standalone to manually check what the
  vision agent produces before we plumb the specs into CAD runs.

**Status**: Imports work, prompt composition smoke-tests. NO actual
test run yet — Shef wants to manually inspect vision outputs first.
He said "take extremely good notes as I'm about to compact you" —
hence eval/NEXT.md got a full pre-compaction handoff doc.

**Plumbing to CAD still TODO** — vision spec is saved to a file; the
CAD runner does NOT yet prepend it to phase-2 prompts. Leave this
until vision quality is validated.

## 2026-04-19 01:48 — the decoupling test result: CAD is solved, vision is the wall

v011-handcrafted-spec on mm_2025_phase1_envelope:
- User (Shef) wrote a plain-English spec by hand in scratchpad/mm_2025_human_description.txt
- Runner injects it as authoritative VISION REPORT, agent skips Phase 1
- Result: **composite = 1.000. L1 L2 L3 L4 L5 ALL = 1.0.**
- 57 turns, 392s, 5 sketch + 5 extrude + 1 fillet + 2 compare_to_reference
- Agent volume 345109 mm³ vs ref 345084 mm³ (0.007% diff)

Comparison: baseline/v001-v008 on medium tier all cluster at 0.15-0.30 composite.
Hand-written spec → 1.000 composite.

**The bottleneck is not CAD execution. It's vision decomposition.** Opus
4.7 can execute a correct build from a clean human-grade spec. Everything
we've been doing (render-compare, dim-crosscheck, OCR, compare_to_reference
tool, grader rotation invariance, etc.) was fighting the wrong wall.

Prioritization change: from here on, every effort goes to Phase 1 spec
quality. If we can produce ~human-quality decompositions automatically,
the scores come with them for free.

Concrete implications:
- v010's architecture (vision sub-skill → CAD) is directionally correct.
  The vision skill just needs to be MUCH better than it currently is.
- Investing in the CAD skill is low-ROI until Phase 1 is fixed.
- A useful next experiment: side-by-side the Phase 1 vision output
  (auto-generated) vs the hand-written spec for mm_2025, see what's
  specifically missing or wrong. That gap IS the work to do.

## 2026-04-19 02:30 — full 2×2: handcrafted vs auto Phase 1

Clean apples-to-apples on Model Mania medium tier:

| brief    | spec source  | composite | turns | elapsed |
|----------|--------------|-----------|-------|---------|
| mm_2025  | handcrafted  | **1.000** | 57    | 392s    |
| mm_2025  | auto         | 0.533     | 147   | 2399s   |
| mm_2021  | handcrafted  | **0.615** | 102   | 1628s   |
| mm_2021  | auto         | 0.000     | 151   | 2683s   |
| mm_2019  | auto         | 0.325     | 131   | 2786s   |

**Key findings:**

1. Handcrafted wins on both parts (mm_2025: 1.0 vs 0.53, mm_2021: 0.62
   vs 0.0). mm_2025 wasn't "just easy" — auto with 147 turns of self-
   correction only hit 0.53.
2. mm_2021 auto = 0.0 because agent never reached export — burned all
   151 turns on Phase 1 + building, hit cap before `export_part_studio`.
3. Handcrafted runs are 4-7× faster (mm_2025: 392s vs 2399s; mm_2021:
   1628s vs 2683s).

Implication: auto Phase 1 is expensive enough in turns that complex
briefs can't finish within the cap. Handcrafted both improves spec
quality AND frees budget for Phase 2 + recovery.

**Note**: v010 mm_2025 auto did catch its own pocket-shape error mid-
build via compare_to_reference (Shef observed "Big discrepancy! The
reference pocket has CONCAVE sides..."). The recovery loop works.
Just needs more headroom.
