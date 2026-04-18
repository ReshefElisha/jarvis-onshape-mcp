# eval/ — AutoResearch harness for the Onshape MCP CAD agent

Read `../CLAUDE.md` first. This file is the phase-specific operational guide.

## Current phase

**Phase 0 — Bootstrap.** No scoreboard entries yet. Dataset fetch + STEP conversion is the first task.

## Phase 0 checklist

- [ ] `pip install pythonocc-core trimesh datasets huggingface_hub` in a fresh venv. (`uv` in this repo uses a different resolver; isolate the heavy deps so they don't pollute the plugin's runtime env. Target path: `eval/.venv`.)
- [ ] Write `bootstrap.py` that:
  - [ ] Downloads Text2CAD from HF Hub (`SadilKhan/Text2CAD`). Cache to `datasets/text2cad/raw/`.
  - [ ] Samples 50 expert-tier briefs (seeded RNG for reproducibility). Dump brief text + DeepCAD sequence to `datasets/text2cad/samples/`.
  - [ ] Clones DeepCAD (`rundiwu/DeepCAD`) and uses `export2step.py` to convert each sample's sequence to STEP. Cache under `datasets/text2cad/step/`.
  - [ ] Clones CADPrompt repo, executes the 200 reference scripts under CadQuery, dumps STEP. Cache under `datasets/cadprompt/step/`.
  - [ ] Writes `datasets/MANIFEST.json` — list of `{brief_id, brief_text, brief_image_path or null, reference_step_path, source_dataset, difficulty_tier}`. Hash each brief's text + image bytes; seal with a manifest-version number.
- [ ] Hand-build `datasets/modelmania/PROVENANCE.md` stub. Real STEPs come later; leave the tier empty but wire it into the MANIFEST.
- [ ] Verify: `jq '.briefs | length' datasets/MANIFEST.json` ≥ 50. Commit MANIFEST.json (small). Don't commit the STEPs (large, gitignored).

When Phase 0 is done: flip the README to Phase 1 and commit.

## Phase 1 checklist

- [ ] `grader/compare_step.py`:
  - [ ] `load_step(path) -> TopoDS_Shape` (PythonOCC)
  - [ ] `volume(shape) -> float_m3` via `GProp_GProps` + `BRepGProp.VolumeProperties`
  - [ ] `bbox(shape) -> (xmin, ymin, zmin, xmax, ymax, zmax)` via `Bnd_Box`
  - [ ] `topology_signature(shape) -> {n_faces, n_edges, n_vertices, n_solids}` via `TopExp.MapShapesAndAncestors` or walking `TopExp_Explorer`.
  - [ ] `boolean_iou(a, b) -> float_in_0_1`:
    - `inter = BRepAlgoAPI_Common(a, b).Shape()`, `union = BRepAlgoAPI_Fuse(a, b).Shape()`.
    - `iou = volume(inter) / volume(union)`. Handle zero-volume edge cases → 0.
  - [ ] `chamfer_distance(a, b, n_samples=10000) -> float_m`:
    - Tesselate both via `BRepMesh_IncrementalMesh`, export vertex clouds.
    - `trimesh.points.distance_to_surface` both directions, mean.
- [ ] `grader/rubric.py`:
  - [ ] Weights + tolerances exactly as in CLAUDE.md. Composite = weighted sum with L0 as a hard gate.
  - [ ] `score(agent_step, reference_step) -> {composite, layers, details}`.
- [ ] `grader/requirements.txt` with pinned versions. Pin python-occ-core, trimesh, numpy.
- [ ] Self-test: `python -m grader.selftest` — grade each reference STEP against itself. Every one should return composite=1.0. Run on all briefs in MANIFEST.
- [ ] `grader/GRADER_HASH` = `sha256sum *.py | sha256sum`. Commit.
- [ ] **LOCK.** Add `grader/` to pre-commit hook or at minimum document the rule: nobody edits `grader/` without a Shef review + explicit grader-version bump.

## Phase 2 checklist

- [ ] `runner/run_brief.py`: CLI `--brief-id X --variant Y --out-dir Z`. Spawns `tools/agent_sdk_loop.py` against a fresh Onshape doc, gives it the brief text (+ brief image if any), lets it build until done or 50-turn cap. On exit: `export_part_studio(format="STEP")` the final Part Studio, save to out-dir. Capture the full transcript JSONL. Call grader, write `scores.json`.
- [ ] `runner/run_eval_set.py`: reads MANIFEST, calls run_brief in parallel (or serial — parallel only if Shef's Onshape account doesn't throttle). Tallies aggregate, writes scoreboard.jsonl line.
- [ ] Smoke: run on 3 random briefs with `baseline` variant. Verify all three produce a STEP + scores.json, and scoreboard appends one valid line.

## Phase 3 (baseline characterization)

- [ ] 3 repeat runs of the baseline (all 50 briefs). Compute `noise_floor` = std of mean_composite across the 3. Save to scoreboard.
- [ ] Pull the 5 lowest-scoring briefs across all 3 runs. Read transcripts. Classify failure mode.
- [ ] Write `FAILURE_MODES.md` — categorized failure taxonomy with example brief_id per mode.

## Phase 4 (the meta-loop)

See CLAUDE.md § Phase 4.

## Non-goals

- Don't benchmark throughput. Wall-clock minutes-per-run is a secondary metric, logged but not optimized.
- Don't compete with paper results on Text2CAD/CADPrompt. We use the datasets as ground truth; our metric (agent-driven MCP → STEP) is different from theirs (model-predicted sequence → STEP).
- Don't build a leaderboard UI. A JSONL scoreboard + tail/jq is sufficient signal.
