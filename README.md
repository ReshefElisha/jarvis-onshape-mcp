# Jarvis Onshape MCP

Claude Code plugin that lets Claude drive real Onshape CAD: sketches, extrudes,
fillets, mates, parametric iteration via Variable Studios, custom FeatureScript
features. Every mutating tool returns a structured truth: what changed, what
warnings the regenerator raised, and hints for the next move. Multi-view PNG
renders come back as image content so Claude can actually see the part.

Includes a vision-decomposition skill that walks Claude through reading an
engineering reference image *before* building. See `RESEARCH.md` for the
benchmark data behind that workflow.

> "felt dramatically more like writing code than anything I've tried with an LLM CAD tool."

## What you get

- **Truth-telling on every mutation.** Every tool returns `{ok, status,
  feature_id, feature_name, error_message, changes?, hints?}`. Silent regen
  failures are surfaced, warnings are enriched with actionable fixes.
- **Vision.** `render_part_studio_views` and `render_assembly_views` return
  shaded PNGs (front/top/right/iso). `crop_image` zooms in on regions.
  `load_local_image` caches a reference image (drawing, photo, sketch) the
  user shares so you can crop into it the same way. `compare_to_reference`
  renders your in-progress part and composites it directly under the
  reference for side-by-side visual diff in a single image.
- **Vision-decomposition skill.** `/skill vision-decompose` — when the
  user gives you a reference image and asks you to build it, this skill
  walks you through a structured zoom-and-describe pass *before* you start
  building. Produces a feature tree the user can sanity-check. We measured
  this turns "agent skims image and builds the wrong shape" into "agent
  reads image carefully, asks the user to confirm, then builds." See the
  research writeup below.
- **Drawing OCR.** `extract_drawing_dimensions` runs Tesseract on an
  engineering drawing and returns every numeric callout (length / radius /
  diameter / thread / angle / count) grouped by kind, with pixel positions.
  Use it on hard-to-read drawing PNGs where small dim text gets clobbered
  by Claude's vision downsampling.
- **Entity discovery with outward normals.** `list_entities` returns deterministic
  face IDs, surface types, and normals so follow-up features can target geometry
  without guessing.
- **Per-feature geometric diffs.** After each feature, you get a `changes:`
  block with bbox delta, part count delta, mass delta — you see the effect
  before rendering.
- **Parametric iteration.** First-class Variable Studios. `set_variable` is
  upsert-by-name, so reparametrizing NEMA 17 → NEMA 23 is a few values away.
- **FeatureScript escape hatch.** `write_featurescript_feature` lets Claude
  write a custom feature directly (helices, swept threads, shells with
  parameters) when the tool-per-primitive surface isn't enough. Regen errors
  surface FS notice text.
- **Hints rotation.** When a feature fails with a known pattern, hints point
  at the fix (`BOOLEAN_SUBTRACT_NO_OP → oppositeDirection`,
  `SKETCH_DIMENSION_MISSING_PARAMETER → add missing variable`, …).
- **Assembly.** Fastened, slider, revolute, cylindrical mates; face-coordinate
  systems; instance alignment; bounding-box interference checks.

## Install

```
/plugin install github:ReshefElisha/jarvis-onshape-mcp
```

Claude Code will prompt you for:

- `ONSHAPE_API_KEY` — the "Access Key" from the Onshape developer portal.
- `ONSHAPE_API_SECRET` — the "Secret Key" shown once when you create the key pair.

Get a key pair at [dev-portal.onshape.com](https://dev-portal.onshape.com/).
Both values are stored in the OS keychain and never written to disk in plaintext.

### Requirements

- [uv](https://docs.astral.sh/uv/) on your PATH (`brew install uv` or the
  official installer). The plugin launches its MCP server via `uv run`.
- Claude Code desktop or CLI with plugin support.
- An Onshape account.

## Quick start

Once installed, restart Claude Code and try:

> "Create a new Onshape document, add a Part Studio, and build me a
>  60×40×8 mm mounting plate with four ø4 mm holes 6 mm in from the corners."

Claude will render the result, show you the bbox delta, and surface any
regen warnings. If it takes a wrong direction on an extrude, the
`BOOLEAN_SUBTRACT_NO_OP` hint will kick in and it'll self-correct.

## Protocol guide

Two plugin skills auto-discovered by Claude Code:

- `skills/onshape/SKILL.md` — **CAD build skill**. Loaded into every Onshape
  session. Covers units (bare numbers in mm), coordinate frames (Front is XZ
  with a Y-normal sign flip), render-first and entity-first workflows,
  iteration discipline, when to reach for `write_featurescript_feature`,
  and the gotchas (REMOVE-on-face auto-flip, Variable Studios as separate
  elements, deterministic ID remapping).

- `skills/vision-decompose/SKILL.md` — **Vision decomposition**. Use this
  *before* building when the user shares a reference image. Walks the agent
  through overview → cache → zoom-into-each-feature → structured spec.
  Output is a feature tree (type, role, size, position, face) the user can
  review before committing turns to the build. See "Recommended workflow"
  below.

You can load either into any Claude session as a system prompt to get the
same behavior outside the plugin context.

## Recommended workflow

The plugin works best as a copilot, not an autocomplete. Two modes:

**Mode A — text-first design.** Describe the part in plain text ("a 100×60×30
mm aluminum heat sink with 1mm fins on 3mm pitch and 4 corner Ø3.5 mounting
holes") and let Claude build. This works well — the bottleneck is not CAD
execution, it's image interpretation.

**Mode B — image reference.** Drop in a drawing, photo, sketch, or
competition prompt and ask Claude to build it.

1. Invoke the vision-decomposition skill: `/skill vision-decompose`.
2. Claude produces a structured feature tree from the image.
3. Review it — fix mis-reads, fill in things the image didn't make obvious.
4. Tell Claude "build to that spec." It runs the CAD pipeline against the
   confirmed tree.

Mode B with a careful human review beats letting Claude attempt the whole
thing autonomously. See `RESEARCH.md` for the experimental data behind that
recommendation.

## Tool surface

Roughly 60 tools across these groups:

| Group | Highlights |
|-------|-----------|
| Document | `create_document`, `find_part_studios`, `get_elements` |
| Sketch | `create_sketch` (multi-entity), plus rectangle / circle / line / arc / rounded rect primitives |
| Feature | `create_extrude`, `create_revolve`, `create_thicken`, `create_fillet`, `create_chamfer`, `create_boolean`, `create_linear_pattern`, `create_circular_pattern` |
| Assembly | `add_assembly_instance`, `create_fastened_mate`, `create_slider_mate`, `create_revolute_mate`, `create_cylindrical_mate`, `align_instance_to_face`, `check_assembly_interference` |
| Introspection | `describe_part_studio`, `list_entities`, `get_body_details`, `get_bounding_box`, `get_mass_properties`, `measure`, `get_face_coordinate_system` |
| Variables | `create_variable_studio`, `set_variable`, `get_variables` |
| FeatureScript | `eval_featurescript`, `write_featurescript_feature` |
| Rendering | `render_part_studio_views`, `render_assembly_views`, `crop_image`, `load_local_image`, `compare_to_reference`, `extract_drawing_dimensions` |
| Export | `export_part_studio`, `export_assembly` (STL / STEP / GLTF / …) |

Full schemas are discoverable from Claude via `ToolSearch` — no separate
docs to read.

## Known limitations

- **Section views are blocked** at the Onshape platform level. The REST API
  has no section-view endpoint; only the UI `Shift+X` works.
- `create_fillet` with `variableCenter` currently hits a phantom-reference
  bug on Onshape's side. Bare radius works.
- `opHelix` standard-library call is flaky in some contexts; cookbook uses
  `opFitSpline` as a workaround.

## Development

```
git clone https://github.com/ReshefElisha/jarvis-onshape-mcp
cd jarvis-onshape-mcp
uv sync
export ONSHAPE_API_KEY=...
export ONSHAPE_API_SECRET=...
uv run onshape-mcp         # launch the MCP server on stdio
uv run pytest              # unit tests
```

## Attribution

Scaffolding (Onshape REST client + HMAC auth, BTMFeature-134 /
BTMParameterQuantity-147 / BTMIndividualQuery-138 payload builders, and the
first-pass tool-per-primitive MCP surface) was forked from
[hedless/onshape-mcp](https://github.com/hedless/onshape-mcp) — thanks to
hedless for getting that off the ground. Everything built on top of that
(truth-telling, vision, entity discovery, parametric Variable Studios,
FeatureScript orchestration, per-feature geometric diffs, the hints rotation,
iterative agent harness via Claude Agent SDK, and most of the current tool
surface) was built here. See `NOTICE` and `git log` for the full trail.

## License

MIT. See `LICENSE`.
