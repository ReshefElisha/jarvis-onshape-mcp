# CLAUDE.md — autoresearch branch

**Purpose of this file**: persist enough state across sessions (including after `/clear`, context compaction, and cold-start fresh clones) that a Claude you've never seen before can pick up the self-improvement loop and make real progress without asking Shef to re-explain. Read this BEFORE touching anything. Then read `eval/README.md` and `scoreboard.jsonl`.

---

## ⚠️ Important: this is NOT vanilla Karpathy AutoResearch (Shef ruling 2026-04-18)

The Karpathy `autoresearch` repo optimizes a **non-agentic** training loop where each iteration is **5 minutes of code execution**. That setting tolerates fast N+1 hyperparameter tweaks because cost is low.

**Our setting is fundamentally different:**

- Each iteration runs an LLM **agent** for ~10 minutes per brief × 3 briefs = **~30 minutes** real wall time. Onshape API quota burns alongside.
- We're optimizing the **prompt + tool surface around an agent**, not weights or hyperparams.
- A small SKILL.md word-tweak that costs 30 minutes to evaluate is **bad ROI** when noise floor is wide.

**Implications for how to run the loop:**

1. **Bias toward bigger architectural variations**, not surface-text edits. New MCP tools, new measurement loops, new dataset rebalancing. Each iteration must earn its 30 minutes.
2. **A no-op variation is not free.** If your gut says "this might shave 0.02 off composite," skip it — the noise floor is wider than that.
3. **Tool/MCP changes are first-class mutations.** Phase 5+ in the original plan put SKILL.md ahead of tool changes. **Reordered: feel free to touch onshape_mcp/ tool code at any phase if it unlocks a real capability.**
4. **Datasets are not sacred.** If a tier saturates (easy) or is too brutal to be informative (NIST PMI hard), re-tier or rebalance. Bump manifest version when you do.
5. **The single-scalar-metric rule still applies** — don't game the metric, but DO improve the grader if it's blind to a class of correctness (rotation invariance, scale-invariant shape, etc.). Bump grader version + regrade history.
6. **Karpathy's "single-file mutation" discipline does NOT apply.** Combine multiple changes per variant if they're synergistic. Just describe them in the variant's `mutation_description`.

Per-Shef framing: "the Karpathy autoloop is for non-agentic improvement (hyperparameters and code, it's running code not an agent) and is time-bound to 5min per iteration so we can't go 100% like karpathy here."

Karpathy's load-bearing rules we DO keep:
- LOCKED grader during a comparison batch (rev with discipline + regrade)
- One scalar composite ordering runs
- Variants that don't beat baseline by > noise floor get reverted
- Always log mutations even if reverted — the variant tree is the research record

---

## Current pivot (Shef 2026-04-19): vision decomposition is the bottleneck

Session to-date finding: after 8 variants, **Opus 4.7's visual reasoning
about engineering drawings is the bottleneck**, not CAD generation. When
Opus correctly decomposes the reference, it builds a decent part. When it
misreads the image, it builds something unrelated. v001 is the only kept
SKILL mutation (+0.04 medium tier, 4× above noise).

New architecture (shipped, untested end-to-end):
- **Vision sub-agent** (`eval/runner/run_vision.py`) — separate SDK session
  with ONLY `load_local_image` + `crop_image`. Opus 4.7 (same model —
  NOT Haiku per Shef's premise). Produces a structured feature tree.
- **Vision sub-skill** (`eval/skills/vision/SKILL.md`) — dictates the
  OVERVIEW/ENVELOPE/FEATURE-TREE/RELATIONSHIPS/UNCERTAINTIES output.
- **CLI test scripts** (`eval/tests/test_vision_<brief>.sh`) — one per
  non-seed brief. Shef runs them manually to verify spec quality
  before we wire the spec into the CAD runner.

**Next step**: Shef manually runs a handful of `test_vision_*.sh`, reviews
the specs, tells us if the vision quality is worth plumbing into phase-2
CAD runs. Do NOT auto-plumb before his review — premise of this whole
architectural bet is that vision description works; if the specs are
garbage, we learn something else is broken.

See `eval/NEXT.md` for the full pre-compaction handoff.

---

---

## Quickstart: your literal first 10 minutes

```bash
cd /Users/shef/projects/claude-onshape-mcp
git checkout autoresearch                    # if not already there
tail -1 eval/scoreboard.jsonl                # see if any baseline exists
git log --oneline autoresearch -10           # recent activity

# If scoreboard is empty and no eval/bootstrap.py exists → you're in Phase 0.
# Read eval/README.md § "Phase 0 checklist" and start there.

# Sanity check: does the product MCP work in this checkout?
uv sync
uv run onshape-mcp < /dev/null &             # should print nothing + hang — kill it
# If no .env file: ask Shef for ONSHAPE_API_KEY + ONSHAPE_API_SECRET.
# Put them in .env (gitignored) like:
#   ONSHAPE_API_KEY=...
#   ONSHAPE_API_SECRET=...

# Trace how a CAD build actually runs so you understand the runner boundary.
less tools/agent_sdk_loop.py                 # read it in full, ~250 lines

# Read the research record + open questions.
cat eval/SESSION_NOTES.md
```

Key facts a cold session should internalize in these 10 minutes:
- This branch (`autoresearch`) edits the **prompt surface** (SKILL.md et al.). It DOES NOT touch `onshape_mcp/` product code. Never.
- The sketch-constraints branch is a product PR (#1, unrelated to this work). Don't merge it here. Don't rebase onto it. Leave it alone.
- Scratchpad of prior dogfood reports lives in a DIFFERENT directory: `/Users/shef/projects/onshape-mcp/scratchpad/`. Read it ONCE for context (peer reports, design docs) if you want, but the canonical AutoResearch state is here.
- Onshape API has rate limits. One brief build ≈ 5–15 min wall clock + dozens of API calls. A 50-brief run takes ~hours and burns real quota. Don't surprise Shef.

---

## What this repo is

Shipping product: the `onshape-mcp` Claude Code plugin (repo: `github.com/ReshefElisha/claude-onshape-mcp`). Main branch is stable, installable via `/plugin install github:ReshefElisha/claude-onshape-mcp`. The plugin gives Claude sessions real Onshape CAD via MCP tools.

Parallel track: **self-improvement eval harness** (this branch — `autoresearch`). Karpathy-AutoResearch-style: mutate the agent's prompt surface (SKILL.md, instructions block, tool descriptions), re-run a fixed eval set against STEP ground-truth, keep the mutation if aggregate score improved, revert if not. Goal: quantitatively improve CAD-agent performance without touching tool code.

**Do not conflate**. AutoResearch edits the prompt/doc surface ONLY. Product PRs (sketch-constraints, create_shell etc.) land on main via a separate branch + PR flow.

---

## Current state

- **main**: stable, 10 commits ahead of the v1 install. Has `create_shell`, `create_offset_plane`, one-call `create_document`, the instructions block, the `skills/onshape/SKILL.md` plugin skill.
- **sketch-constraints** (separate branch, PR #1 open): constraint-first sketches + `edit_sketch`. 10 commits. Fully dogfooded by peers (bracket + clevis + side-view). Ready to merge to main when Shef pulls the trigger. **Not related to AutoResearch work.**
- **autoresearch** (this branch): where the eval harness lives. Starts from main.

At time of writing, the harness is **not yet built**. You are likely either in Phase 0 (bootstrap), Phase 1 (grader), Phase 2 (runner), or Phase 3+ (meta-loop). Consult `scoreboard.jsonl` to find out.

---

## The AutoResearch design (READ THIS BEFORE CODING)

Source: Karpathy's `autoresearch` repo and tweets, March 2026. Our adaptation:

### Core loop

```
1. Lock a fixed eval set (briefs + ground-truth STEP files).
2. Run the current agent variant across every brief. Export STEP.
3. Grade each output against its reference using a LOCKED comparator.
4. Aggregate to one scalar: mean composite score.
5. Propose ONE mutation to the prompt surface. Commit to a variant branch.
6. Re-run eval. If aggregate score improves, KEEP. Otherwise REVERT (git reset).
7. Append outcome to scoreboard.jsonl. Goto 5. NEVER STOP.
```

### Karpathy's guardrails (all load-bearing — violate any and the loop is invalid)

1. **LOCKED grader**. `eval/grader/` must be read-only to the loop agent. If the agent can edit it, it will game the metric. Enforcement: grader is a separate Python package; the runner imports it by pinned version hash. Any commit touching `eval/grader/` during an AutoResearch loop invalidates that run.

2. **Single scalar metric**. One number per run: `mean_composite_score` ∈ [0, 1]. If improvement is ambiguous without multi-metric interpretation, the metric is wrong — simplify until one number orders runs.

3. **Fixed budget per brief**. 50 turns wall-clock cap via `tools/agent_sdk_loop.py`. Not negotiable during a loop. If the budget is too small, every brief fails uniformly — no signal. If too large, noise drowns signal. 50 is the current target; adjust in Phase 3 if baselines suggest otherwise.

4. **Single-file mutation**. In Karpathy's loop the agent edits only `train.py`. Our equivalent: edit only `skills/onshape/SKILL.md` on a variant. Expand scope LATER (Phase 5+) once single-file mutation stops finding wins. Do not widen early.

5. **NEVER STOP**. The loop agent runs until Shef kills it or it exhausts mutation ideas. Document every proposed mutation in `scoreboard.jsonl` — even reverted ones. That log is the research paper.

### What gets researched in our setting

The **behavior of CAD-building Claude sessions**. Specifically:
- How `SKILL.md` phrases the render-first / entity-first protocols.
- Which gotchas get surfaced, in what order, with what framing.
- Which tool-use patterns the doc encodes explicitly vs. leaves implicit.

What DOES NOT get researched in the loop:
- MCP tool code (builders, serializers, handlers). Those are product changes that land via PR.
- The grader.
- The dataset. New briefs join as a separate manual step, not a loop mutation.

### Cautions (Karpathy's, translated to our setting)

- **Budget gaming**: agent "speedhacks" the budget — shorter answers at cost of quality. Counter: per-brief timeout AND per-brief quality floor (if score < 0.1 the brief counts as a hard fail regardless of score).
- **Noise-driven keeps**: with small eval sets, a 1-brief flip can dominate. Counter: require aggregate delta > noise floor (measured from 3 repeat runs of the baseline). Save repeat-variance to scoreboard.
- **Prompt injection via logs**: agent transcripts include tool_result blocks. Malicious content in an Onshape doc could instruct the next run. Counter: strip non-ASCII and tool-output from transcripts before they feed the meta-agent's mutation step.
- **Early-step bias** (Karpathy calls this "5-min window bias"): the 50-turn cap over-weights sketches that succeed early. Counter: track per-brief turn count and flag if a mutation skewed the distribution even with unchanged aggregate.
- **LLM-judge is NOT the grader**. Karpathy's silence on LLM-judge is pointed. We use it as a SECONDARY signal (qualitative rubric in `scoreboard.jsonl`) but never in the composite score. The composite is OCP geometry, period.

---

## Datasets (confirmed sources from research)

Three eval tiers, different purposes:

### Primary: Text2CAD (DFKI, NeurIPS 2024 Spotlight)
- Annotations repo: `https://github.com/SadilKhan/Text2CAD` — CC BY-NC-SA 4.0 (non-commercial, OK for internal research).
- 170k models × 4 skill tiers of NL annotations. Built on DeepCAD (mined from Onshape).
- Geometry comes from DeepCAD (`https://github.com/rundiwu/DeepCAD`). Convert JSON sequences to STEP via DeepCAD's `export2step.py`. Do this conversion once, cache the STEPs, gitignore the bytes, track MANIFEST hashes.
- Sample 30–50 expert-tier briefs for the v1 eval set. Mix of pure NL and NL+drawing.

### Held-out: CADPrompt
- Hand-curated 200 NL prompts paired with expert-annotated CadQuery scripts. Small enough to eyeball-audit every problem.
- Use as the sanity set — score but never loop-optimize against. Catches if we overfit to Text2CAD.

### Hand-built: SolidWorks Model Mania
- Drawings public, STEP solutions NOT public. Community dump on GrabCAD (2000–2014) quality varies.
- Plan: hand-build 5–10 ground-truth STEPs from the problem PDFs Shef has been pasting. Document conversion provenance per file.
- Use as the "drawing transcription" tier. Only tier where briefs include diagrams.

### Rejected (from research — do NOT chase these)
- ABC Dataset, SketchGraphs, CAD-SIGNet/Recode, CADTalk, CAD-Llama. Wrong shape (no briefs, or wrong modality, or wrong task).

---

## The grader (LOCKED — see Phase 1 for how to build it)

Layered comparator, `eval/grader/compare_step.py`. Each layer is a pass/fail gate; failing early layers zeroes the composite.

| Layer | Check | Tolerance | Weight |
|-------|-------|-----------|--------|
| L0 | Body exists (at least one solid) | — | pass=0.0 default |
| L1 | Volume within ±5% | `abs(v_a - v_b) / v_b < 0.05` | 0.15 |
| L2 | Bounding box within ±5% each axis | — | 0.15 |
| L3 | Topology signature (face/edge/vertex count ratio) | ratio ∈ [0.8, 1.25] | 0.15 |
| L4 | Boolean IoU `vol(A∩B) / vol(A∪B)` | ≥ 0.90 | 0.35 |
| L5 | Chamfer distance on tesselation | ≤ 0.02 × diag | 0.20 |

Composite score = `Σ (weight_i × layer_i_passed)` ∈ [0, 1]. Hard fail (L0) → 0.0. Pass-all → 1.0.

Stack: `cadquery-ocp` (pip-installable OCP / OpenCascade binding) for all booleans, mass/volume, mesh export. `trimesh` for Chamfer. Pure pip in `eval/.venv`. **Pin versions in `eval/grader/requirements.txt` and hash-check on import** — any dep drift and the grader has changed, which means prior scoreboard entries are incomparable.

---

## Directory layout (enforce)

```
eval/
  README.md                    Living design doc. Update with every phase transition.
  bootstrap.py                 One-shot: download Text2CAD + CADPrompt + convert to STEP.
  datasets/                    GITIGNORED — downloaded + converted reference STEPs.
    text2cad/                  reference_00123.step + brief.txt pairs
    cadprompt/
    modelmania/                hand-built ground truths, track provenance per file
    MANIFEST.json              The SEALED list of briefs in the eval set. Hashed into scoreboard.
  grader/                      LOCKED — never edit during a loop.
    compare_step.py            Layered comparator. PythonOCC + trimesh.
    rubric.py                  Weights, tolerances, composite score.
    requirements.txt           Pinned versions.
    GRADER_HASH                Output of `sha256sum grader/*.py`. Check before/after every run.
  runner/                      NOT locked — the runner code is allowed to change. But version-hash every run.
    run_brief.py               Spawn Claude Agent SDK against the MCP, export STEP, call grader.
    run_eval_set.py            Iterate over MANIFEST.json, tally scores.
  variants/                    Each subdir = one candidate mutation of the prompt surface.
    baseline/                  Symlinks to current main `skills/onshape/SKILL.md` + server.py instructions.
    v001-<desc>/               Frozen copies at the time of the run. Git history is the audit trail.
  runs/                        GITIGNORED — per-run artifacts.
    <timestamp>-<variant>/
      briefs/                  Per-brief: agent_transcript.jsonl, exported.step, scores.json
      aggregate.json           Mean composite + per-layer pass rates.
      grader_hash.txt          Hash at time of run — must match GRADER_HASH.
  scoreboard.jsonl             One line per completed run. Append-only. Each line:
                               {timestamp, variant_id, git_sha, grader_hash, n_briefs,
                                mean_composite, per_layer_pass_rate, noise_floor,
                                mutation_description, kept: bool, parent_variant}
```

---

## Phased plan

Check `scoreboard.jsonl` first — your phase is wherever the last-completed phase got to.

### Phase 0: Bootstrap (no scoreboard entries yet)

1. `mkdir -p eval/{grader,runner,variants,runs,datasets}` — already done in branch init.
2. Clone Text2CAD from HF, cache DeepCAD JSON locally, write `bootstrap.py` to run DeepCAD's `export2step.py` on a 50-brief sample. Commit the MANIFEST.json (with brief hashes) but GITIGNORE the STEP artifacts.
3. Pull CADPrompt 200 as-is (scripts execute → STEP).
4. Document Model Mania hand-build procedure in `datasets/modelmania/PROVENANCE.md`. Plan to build ~5 over time as Shef has bandwidth.

Deliverable: `eval/datasets/MANIFEST.json` sealed with brief hashes. Commit.

### Phase 1: Grader (LOCKED)

1. Implement `eval/grader/compare_step.py` with PythonOCC. Functions: `load_step(path) -> Body`, `volume(body)`, `bbox(body)`, `topology_signature(body)`, `boolean_iou(a, b)`, `chamfer_distance(a, b, samples)`.
2. `eval/grader/rubric.py` — layered scoring, returns `{composite, layers: {L0, L1, ..., L5}, details}`.
3. Self-test: grade reference-vs-reference on the MANIFEST → expect composite=1.0 across the set. Commit only after this passes.
4. Compute + commit `GRADER_HASH`.

Deliverable: grader-vs-itself test suite, `GRADER_HASH` file. Commit.

### Phase 2: Runner

1. `eval/runner/run_brief.py`: takes (brief_path, variant_id, output_dir), spawns `tools/agent_sdk_loop.py` against the MCP with the variant's SKILL.md, captures the exported STEP + transcript.
2. `eval/runner/run_eval_set.py`: iterates MANIFEST, calls run_brief per entry, tallies aggregate.
3. Smoke-test on 3 briefs with the `baseline` variant. Verify scoreboard line writes correctly.

Deliverable: first baseline scoreboard entry. Commit run artifacts to `runs/` (gitignored) + scoreboard.jsonl line.

### Phase 3: Baseline characterization

1. Run baseline 3× for noise floor. Expect ~±0.03 variance from model stochasticity. Record as `noise_floor` field in scoreboard.
2. Inspect per-brief scores. Identify the 3 worst briefs — these are candidate mutation targets.
3. Human-read the transcripts of the worst briefs (or use an LLM-judge agent to triage) to classify failure mode: "didn't call describe_part_studio", "used coordinate-first sketch when constraint-first would've worked", "extruded wrong direction", etc.
4. Write up failure-mode taxonomy in `eval/FAILURE_MODES.md`.

Deliverable: scoreboard entries for 3 baseline repeats. `FAILURE_MODES.md`.

### Phase 4: AutoResearch meta-loop (the MAIN EVENT)

Each iteration:
1. Read `scoreboard.jsonl`. Find current best variant.
2. Read `FAILURE_MODES.md`. Pick the most common unaddressed mode.
3. Propose ONE targeted mutation to `skills/onshape/SKILL.md`. Commit to a new branch `variants/v<NNN>-<short-desc>` based on the current best. Short-desc is imperative: `v003-reinforce-entity-first`, `v004-explicit-constraint-bisection`.
4. Run the eval set with this variant. Record scoreboard line with the mutation description + parent variant.
5. If `mean_composite` > best + `2 × noise_floor`, KEEP (set scoreboard `kept: true`; advance "current best" to this variant). Otherwise REVERT (`kept: false`, variant branch stays for historical inspection).
6. Repeat. NEVER STOP.

### Phase 5+: Widen (after Phase 4 plateaus)

Only once the SKILL.md-only loop stops finding wins for 10+ consecutive iterations:
- Expand mutation scope to include `server.py`'s `_INSTRUCTIONS` block.
- Later: tool descriptions.
- NEVER: the grader, the dataset manifest, or the builder code.

---

## How to "keep going" as the loop agent

Every wake-up:

1. Read `CLAUDE.md` (this file).
2. Read `eval/README.md` for phase-specific detail.
3. Run `tail -1 scoreboard.jsonl` to see the last outcome.
4. Run `git log --oneline -10 autoresearch` to see recent activity.
5. If a run is in progress (check `runs/` for a dir without `aggregate.json`), decide whether to resume or abandon.
6. Otherwise: identify the next phase from the plan above. Do ONE concrete unit of work. Commit with a descriptive message. Update this file or `eval/README.md` if the plan changes.
7. If blocked on a decision that needs Shef: write it to `eval/BLOCKERS.md` with full context and drop to idle. Don't guess.

When running the AutoResearch meta-loop (Phase 4+): propose ONE mutation per iteration. Implement. Run the eval. Write the scoreboard line. Don't batch. Don't tune multiple things at once — the single-file / single-mutation discipline is the whole point.

### What to do when you "run out of ideas"

Two paths — both valid:
- Expand dataset. Add 10 more hand-curated briefs (especially drawing-based from Model Mania). This raises the noise floor naturally and gives the loop new failure modes to mine.
- Expand mutation scope (Phase 5+).

Do NOT: change the grader, relax thresholds, or start optimizing secondary metrics. That's the "gaming the metric" failure mode.

---

## Communication discipline

- Shef is likely offline when this branch is running. Work in `/loop` / autonomous mode.
- **Never** message peer Claudes during an AutoResearch iteration — they can contaminate signals. The harness is self-contained.
- **Dogfood peers on the main product** (sketch-constraints branch etc.) operate on a separate channel. Don't coordinate with them while in the loop.
- Use `eval/SESSION_NOTES.md` as a running stream-of-consciousness between wake-ups. Write every interesting observation (even reverted mutations). That's the research record.

---

## Non-negotiables

1. **The grader does not change during a loop.** Period. If the grader is wrong, raise it to Shef, don't silently patch.
2. **One scalar metric orders runs.** Multi-objective reasoning is the road to metric gaming.
3. **One mutation per iteration.** If you can't attribute the delta to a single change, you have no signal.
4. **Every run's grader hash must match GRADER_HASH.** If it doesn't, that run is invalid — note it in scoreboard with `invalid: true` and move on.
5. **Never delete the variants/ branches.** They're the full research history. Even reverted mutations stay.
6. **Never edit the dataset mid-loop.** If you add briefs, bump the MANIFEST version and treat all prior scoreboard entries as using the previous version.

---

## Where to find things

- Sketch-constraints PR (unrelated to AutoResearch): `gh pr view 1`
- Peer reports + old dogfood notes: `/Users/shef/projects/onshape-mcp/scratchpad/`
- Onshape credentials: `.env` in this repo (gitignored)
- Agent SDK harness: `tools/agent_sdk_loop.py`
- Product source: `onshape_mcp/`
- Tests: `tests/`

---

## Session etiquette

- Commit often on the autoresearch branch. Small, labeled commits.
- Never force-push, never rebase main, never merge autoresearch into main.
- If a phase feels wrong, write a 200-word proposal in `eval/DESIGN_QUESTIONS.md` and stop. Shef will pick it up.
