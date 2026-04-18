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

**Grader design**: layered pass/fail stack using PythonOCC. L0 body exists → L1 volume ±5% → L2 bbox ±5% → L3 topology signature → L4 Boolean IoU ≥0.90 → L5 Chamfer distance ≤0.02×diag. Weights 0/0.15/0.15/0.15/0.35/0.20. Composite ∈ [0, 1].

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
