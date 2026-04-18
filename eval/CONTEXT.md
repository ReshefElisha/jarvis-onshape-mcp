# Prior context snapshot — 2026-04-18

For a cold session picking up this branch without the prior conversation. This is ancillary — `CLAUDE.md` is the load-bearing doc. Read this only if you want the "why."

## Why AutoResearch now

Shef spent April 16–17 with multiple Claude instances driving the Onshape MCP through increasingly complex builds. Manual Model Mania problems (SolidWorks' annual CAD challenges) were the dogfood material: he pasted a drawing + a prompt, watched an agent build, graded it subjectively.

Three signals converged by April 18:
1. The constraint-first sketch surface (sketch-constraints branch, PR #1) demonstrably works. One peer ran a 55-turn parametric bracket end-to-end. Another did a Y-fork clevis from a 2-view engineering drawing — zero FS fallbacks, parametric retest held.
2. But Shef is bottleneck. Every dogfood requires him to pick a brief, paste images, judge output. Doesn't scale past ~10 manual runs per sitting.
3. Karpathy released his `autoresearch` repo in March. Self-playing LLM agent loops are a real pattern now. Mapping it to CAD agent self-improvement is a cheap experiment with outsized upside.

The pivot: formalize the eval. Pull public CAD datasets with STEP ground truth. Build a locked grader. Run a baseline. Then Karpathy-style mutate-the-prompt-and-re-run-the-eval loop.

## What was actually built before this pivot

(For product-code context — these changes are on main and sketch-constraints, NOT autoresearch. Do not touch.)

**main branch additions since v1 package:**
- `create_shell` primitive (native Onshape featureType="shell", inward by default)
- `create_offset_plane` primitive (cPlane with cplaneType=OFFSET, from datum or face)
- `create_document` now returns `(document_id, workspace_id, part_studio_id)` in one shot
- `instructions` block on the MCP server — loads at session init, categorized tool index + gotchas
- Skill promoted from repo-root `SKILL.md` to `skills/onshape/SKILL.md` (Claude Code auto-discovers)

**sketch-constraints branch (PR #1, not merged yet):**
- `create_sketch` extended: entity `id` + `constraints[]` → constraint-first drawing transcription
- `edit_sketch` new: `addEntities` / `addConstraints` / `removeIds` with cascade
- 14 constraint types: HORIZONTAL, VERTICAL (line-only), COINCIDENT, TANGENT, CONCENTRIC, PARALLEL, PERPENDICULAR, EQUAL, MIDPOINT, DIAMETER, RADIUS, DISTANCE, ANGLE, OFFSET
- Aliases: HORIZONTAL_DISTANCE / VERTICAL_DISTANCE / LENGTH → DISTANCE + direction enum; POINT_ON rejected in favor of COINCIDENT+subref
- Single-entity circle topology (replaced 2-arc workaround — `circle.N.center` now resolves)
- `variable_center` origin-phantom fix (injects a real sketch-local origin point entity)
- Arc `short_arc: true` default — CCW sweep > 180° auto-flips to short way (UI parity)
- SKILL.md + instructions block updated with constraint-first protocol + bisection recipe for SKETCH_SOLVE_FAILED

## Known-good prior-art observations for the loop

**From Karpathy research** (SESSION_NOTES.md has full):
- Single scalar metric, ungameable, grader LOCKED
- Single editable file at the start
- Fixed time/turn budget per trial
- "NEVER STOP" instruction
- Cautions: budget gaming, noise-driven keeps, early-step bias, prompt injection via tool-result blocks

**From CAD dataset research** (SESSION_NOTES.md has full):
- Text2CAD (DFKI, NeurIPS 2024) annotations = primary brief source. 170k × 4 NL tiers. License CC-BY-NC-SA (internal use OK). Github-cloneable.
- DeepCAD = sequence source paired with Text2CAD annotations; ships `export2step.py` so we can materialize ground-truth STEPs locally.
- CADPrompt = 200 hand-curated briefs, held-out sanity set.
- Model Mania = hand-built for drawing tier. STEP solutions are NOT public (only PDFs + community reconstructions).
- Rejected: ABC (no briefs), SketchGraphs (2D only), CAD-SIGNet (point cloud input), CADTalk (commenting not generation), CAD-Llama (reuses DeepCAD, no new data).
- OCP-based layered grader (Boolean IoU ≥ 0.90 is the emerging standard). CADSmith and CMT papers converge on this pattern.

## Prior dogfood failure modes (mine-worthy for mutation targets)

From peers who built with the current tool surface:

1. **Agent skips `describe_part_studio` between features.** Common when the build is going well early — agent gets cocky, stops looking, makes one arithmetic mistake in feature 7 that cascades. Fix candidate: SKILL.md's render-first protocol is too "protocol-language," doesn't engage.
2. **Agent reaches for coordinate-first sketches when constraint-first would work.** Default familiarity. Fix candidate: lead with constraint-first in SKILL.md, demote coordinate-first to "for trivial cases only."
3. **Agent doesn't auto-wire up `LENGTH → DISTANCE` alias awareness.** SKILL.md mentions it once. Peer dogfood burned 3 turns on "Unknown constraint type: LENGTH" before realizing the alias exists.
4. **Agent doesn't bisect on SKETCH_SOLVE_FAILED.** The hint is there but it's long. Peer burned 6 turns before the hint rotation landed. Fix candidate: shorter, earlier.
5. **Agent doesn't pin to origin, gets drift on parametric retest.** SKILL.md documents the origin-point pattern but in a gotcha section late in the doc. Fix candidate: move earlier, add a worked example inline.

These are the kinds of mutations the AutoResearch loop should propose and test. Don't treat them as gospel — let the loop surface the real signal. Some of the above may not move the needle; others not on the list might.

## Peer infrastructure (not for AutoResearch use)

Other Claude sessions on this machine are reachable via `claude-peers` MCP (`mcp__claude-peers__list_peers`, `send_message`). Useful for manual dogfood coordination on the PRODUCT branch. **DO NOT use during an AutoResearch loop.** Peers can contaminate signal. The loop is a closed system — brief in, score out.
