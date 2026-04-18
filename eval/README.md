# eval/ — AutoResearch harness for the Onshape MCP CAD agent

Read `../CLAUDE.md` first. This file is the phase-specific operational guide.

## Current phase

**Phase 0 — Bootstrap.** No scoreboard entries yet. Dataset fetch + STEP conversion is the first task.

## Install

Use a dedicated venv so eval deps don't pollute the plugin's `uv` env.

```bash
cd /Users/shef/projects/claude-onshape-mcp
python3.11 -m venv eval/.venv
source eval/.venv/bin/activate
pip install cadquery-ocp trimesh numpy
pip install build123d      # optional wrapper API over OCP; convenient for ad-hoc STEP work
```

`cadquery-ocp` is the OCP (OpenCascade) kernel CadQuery and Build123D both ship on top of. Pip-installable, works on macOS arm64, gives you everything you need for STEP I/O, booleans, mass properties, and tessellation.

**Onshape credentials.** `.env` is gitignored — cold clone won't have it. Ask Shef or copy from `/Users/shef/projects/onshape-mcp/.env` if that dir exists locally. Required keys: `ONSHAPE_API_KEY`, `ONSHAPE_API_SECRET`.

## Datasets

Plain `git clone` from the source repos — no registry / auth / login / dataset-loader crap.

- `https://github.com/rundiwu/DeepCAD` — sketch+extrude JSON sequences + `export2step.py` converter. Primary STEP source.
- `https://github.com/SadilKhan/Text2CAD` — NL annotations joinable to DeepCAD model ids by filename. Use for higher-quality briefs than LLM-labeled.
- `https://github.com/OmorFaruqueSany/CADPrompt` — 200-brief hand-curated NL+CadQuery set. Held-out sanity.
- `https://github.com/AutodeskAILab/Fusion360GalleryDataset` — optional STEP fallback, no briefs.
- Model Mania (drawing-tier): hand-built STEP, `datasets/modelmania/PROVENANCE.md` tracks each.

## Phase 0 checklist

- [ ] Set up the pip venv (see Install section above).
- [ ] Clone the dataset repos listed in the Datasets section into `eval/datasets/<name>-repo/`.
- [ ] Write `bootstrap.py` that:
  - [ ] Samples 50 models from DeepCAD with seeded RNG. Dump sequences + inferred brief text (hand-curated or LLM-annotated — if the latter, mark the briefs as `source_dataset: "deepcad+llm-annotated"` so we don't confuse them with real human annotations).
  - [ ] Runs DeepCAD's `export2step.py` on each to produce `datasets/text2cad/step/<brief_id>.step`.
  - [ ] Executes CADPrompt's 200 reference scripts under CadQuery, dumps STEP to `datasets/cadprompt/step/<brief_id>.step`. Some may fail — mark failures, skip in manifest.
  - [ ] Writes `datasets/MANIFEST.json` — list of `{brief_id, brief_text, brief_image_path or null, reference_step_path, source_dataset, difficulty_tier}`. Hash each brief's text + image bytes; seal with a manifest-version number.
- [ ] Hand-build `datasets/modelmania/PROVENANCE.md` stub. Real STEPs come later; leave the tier empty but wire it into the MANIFEST.
- [ ] Verify: `jq '.briefs | length' datasets/MANIFEST.json` ≥ 50. Commit MANIFEST.json (small). Don't commit the STEPs (large, gitignored).

**Brief-text source**: for DeepCAD models, Text2CAD's annotations save the LLM-labeling step — clone the Text2CAD repo and join annotations to DeepCAD model ids by filename before falling back to LLM-generated briefs. Track the provenance field honestly.

When Phase 0 is done: flip the README to Phase 1 and commit.

### Phase 0 day-1 commands (literally)

```bash
source eval/.venv/bin/activate

git clone https://github.com/rundiwu/DeepCAD              eval/datasets/deepcad-repo
git clone https://github.com/SadilKhan/Text2CAD           eval/datasets/text2cad-repo
git clone https://github.com/OmorFaruqueSany/CADPrompt    eval/datasets/cadprompt-repo

# Then (write this — see checklist):
python eval/bootstrap.py --source deepcad --n-samples 50
python eval/bootstrap.py --source cadprompt --all

# Check:
jq '.briefs | length' eval/datasets/MANIFEST.json
```

### The runner you will need (Phase 2)

`tools/agent_sdk_loop.py` already exists — it spawns Claude Agent SDK against the `onshape-mcp` MCP server, takes a `--brief` string, runs until `--max-turns` (default 40; WE WANT 50 per budget spec), writes transcript to an output dir. Your `eval/runner/run_brief.py` should wrap this + handle per-brief image attachments (some Text2CAD and Model Mania briefs include drawing PNGs) + call the grader + export STEP via `mcp__onshape__export_part_studio`.

Read `tools/agent_sdk_loop.py` in full before writing the runner. Don't reinvent it.

## Phase 1 checklist

- [ ] `grader/compare_step.py` (imports from `OCP`, the `cadquery-ocp` package):
  - [ ] `load_step(path) -> TopoDS_Shape` via `OCP.STEPControl.STEPControl_Reader`
  - [ ] `volume(shape) -> float_m3` via `OCP.GProp.GProp_GProps` + `OCP.BRepGProp.BRepGProp.VolumeProperties_s`
  - [ ] `bbox(shape)` via `OCP.Bnd.Bnd_Box` + `OCP.BRepBndLib.BRepBndLib.Add_s`
  - [ ] `topology_signature(shape)` — walk `OCP.TopExp.TopExp_Explorer` by type
  - [ ] `boolean_iou(a, b) -> float_in_0_1`:
    - `inter = OCP.BRepAlgoAPI.BRepAlgoAPI_Common(a, b).Shape()`, `union = ... BRepAlgoAPI_Fuse(a, b).Shape()`.
    - `iou = volume(inter) / volume(union)`. Handle zero-volume edge cases → 0.
  - [ ] `chamfer_distance(a, b, n_samples=10000) -> float_m`:
    - Tesselate both via `OCP.BRepMesh.BRepMesh_IncrementalMesh`, collect vertex clouds.
    - `trimesh.proximity.closest_point` both directions, mean.
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
