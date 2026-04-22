---
name: onshape
description: Protocols for driving Onshape CAD via the onshape-mcp plugin. Render-first and entity-first workflows, unit + coordinate conventions, iteration discipline, when to reach for FeatureScript, and the gotchas (REMOVE-on-face auto-flip, Variable Studios as separate elements, deterministic ID remapping). Load before building anything in Onshape — the plugin's MCP tool surface makes more sense with this doc in context.
---

# Jarvis Onshape MCP — Claude Skill Guide

Loaded as context for any Claude session driving the Jarvis Onshape MCP plugin.
Encodes the protocols that keep CAD builds from silently failing. Short, imperative.

## Think out loud

Before every non-trivial tool call (sketch, extrude, boolean, fillet,
chamfer, describe, export), emit a short plan text (1-3 sentences, plain
assistant output) saying **WHY** you're making this call and **WHAT you
expect to see / build**. Example before an extrude:

> *"Extruding the base rectangle 30 mm up. Expect a flat plate with the
> four corner arcs intact, bbox (500, 780, 30)."*

After each result, also say 1-2 sentences about **what actually happened**
— especially if the result surprised you. If a describe_part_studio shows
a feature at the wrong Z, name that out loud before deciding how to fix.

Don't let your only visible output be tool-call JSON. The observer watching
the run relies on these thought lines to catch bugs in your reasoning.

## Units

Onshape's API works in meters. Two safe ways to pass lengths:

- **String with explicit suffix**: `"30 mm"`, `"0.5 in"`, `"15 deg"`. Always unambiguous; prefer this form.
- **Bare number**: treated as millimeters by default (CAD industry norm). `60` means 60 mm.

**Never assume inches** when reading a tool's schema even if the legacy description says "in inches." The builders were ported from an inch-default codebase; the bare-number default is now mm. When a tool response shows unexpected geometry sizes, suspect units first.

This applies on the assembly side too: `transform_instance` translations, `set_instance_position` x/y/z, and every `create_*_mate` / `create_mate_connector` offset accept bare numbers as mm or explicit unit strings. Slider / cylindrical mate `minLimit`/`maxLimit` are lengths (mm-default). Revolute `minLimit`/`maxLimit` are ANGLES in degrees (float). `get_assembly_positions` returns mm in its report text.

## Coordinate frames

- **Top plane** = XY, normal +Z. `corner1: [0, 0]` in a Top-plane sketch is on the world origin.
- **Front plane** = XZ, normal **-Y**. Note the sign flip (classic trap).
- **Right plane** = YZ, normal +X.

When sketching on a picked face (`faceId` from `list_entities`), the sketch-local axes are defined by that face's own coordinate system. Geometry you sketch is interpreted in the face's plane, not world space.

## The render-first protocol

After every feature that creates or modifies visible geometry:

1. Call `describe_part_studio` (not individual `render_` calls — describe gives structured text + images in one shot).
2. **Verify against expectations in the text** first: is the new feature present in `FEATURE TREE` with status `OK`/`INFO`? Are the expected new faces/edges in `BODIES`? Does `MASS PROPERTIES: volume` line up with what you predicted?
3. If text checks out, glance at the iso view for anything visually off (asymmetric when should be symmetric, missing material, flipped direction).
4. If suspicious, `crop_image` on the specific area. Normalized `[x1,y1,x2,y2]` in `[0,1]`.

Text checks catch arithmetic and counting errors (my weak spot). Image checks catch orientation and topology errors. Neither alone is sufficient.

## Sketches: coordinate-first vs constraint-first

`create_sketch` has two surfaces. The right one depends on what you're
modeling.

### Coordinate-first (simple sketches, 1-3 primitives)

Pass entity dicts without `id` and no `constraints`. Positions are what
you type.

```json
{
  "entities": [
    {"type": "circle", "center": [0, 0], "radius": "25 mm"},
    {"type": "circle", "center": [100, 0], "radius": "12 mm"}
  ]
}
```

Fast. Use for mounting plates, single holes, obvious rectangles. Don't
use this when the drawing specifies tangencies, concentricities, or
dimensional chains — the solver makes those easy, hand-computed
coordinates don't round-trip cleanly.

### Constraint-first (drawing transcription)

Give each entity a user-level `id`, list `constraints`. Onshape's
solver resolves positions from the constraints.

```json
{
  "entities": [
    {"id": "hub",   "type": "circle", "center": [0, 0],   "radius": "25 mm"},
    {"id": "tip",   "type": "circle", "center": [100, 0], "radius": "12 mm"},
    {"id": "upper", "type": "line",   "start": [0, 25], "end": [100, 12]}
  ],
  "constraints": [
    {"type": "DIAMETER", "entity": "hub", "value": "50 mm"},
    {"type": "DIAMETER", "entity": "tip", "value": "24 mm"},
    {"type": "DISTANCE", "entities": ["hub.center", "tip.center"], "value": "100 mm", "direction": "HORIZONTAL"},
    {"type": "COINCIDENT", "entities": ["upper.start", "hub"]},
    {"type": "COINCIDENT", "entities": ["upper.end", "tip"]},
    {"type": "TANGENT", "entities": ["upper", "hub"]},
    {"type": "TANGENT", "entities": ["upper", "tip"]}
  ]
}
```

Entity refs are ids with optional sub-point suffixes: `line.start`,
`line.end`, `circle.center`, `arc.center`. Seed positions (center,
radius on circles/arcs; start/end on lines are optional) are just
solver starting guesses — the constraints drive final geometry.

### 14 constraint types

Entity-ref only (no value): `HORIZONTAL`, `VERTICAL` (lines only),
`COINCIDENT`, `TANGENT`, `CONCENTRIC`, `PARALLEL`, `PERPENDICULAR`,
`EQUAL`, `MIDPOINT`.

Dimensioned (require `value`): `DIAMETER`, `RADIUS`,
`DISTANCE` (with `direction`: `MINIMUM | HORIZONTAL | VERTICAL`),
`ANGLE` (value in degrees default; `"90 deg"` / `"1.57 rad"` for units).

Binary pair: `OFFSET` (offset entity ↔ master; pair with a `DISTANCE`
constraint on the same two entities for the offset length).

Aliases: `HORIZONTAL_DISTANCE` → `DISTANCE(direction=HORIZONTAL)`,
`VERTICAL_DISTANCE` → `DISTANCE(direction=VERTICAL)`, `LENGTH` →
`DISTANCE(direction=MINIMUM)` (for line length or slot end-to-end).
`POINT_ON` is rejected — use `COINCIDENT` with a point sub-ref.

### Pinning to the sketch origin

There's no magic `origin` keyword. To anchor a sketch to the plane
origin (prevents drift on parametric resize), add an explicit point
entity at `[0, 0]` and `COINCIDENT` the geometry you want anchored
to it:

```json
{
  "entities": [
    {"id": "origin", "type": "point", "at": [0, 0]},
    {"id": "hub",    "type": "circle", "center": [0, 0], "radius": "25 mm"}
  ],
  "constraints": [
    {"type": "COINCIDENT", "entities": ["hub.center", "origin"]},
    {"type": "DIAMETER",   "entity": "hub", "value": "50 mm"}
  ]
}
```

The sketch-local origin point acts as a fixed anchor. Without it,
dimensions parametrize fine but positions drift when variables
change — hub.center can slide ~1 mm when you retarget dimensions.

### Gotchas

- **HORIZONTAL/VERTICAL work on LINE entities only.** On a POINT
  (like `hub.center`), use `DISTANCE(direction=VERTICAL, value="0 mm")`
  to pin to the horizontal axis.
- **Circle + arc seeds are required.** Onshape's solver needs a
  starting guess even when DIAMETER/RADIUS will drive final values.
- **Arcs default to the short way.** `arc` specs take `start_angle`
  and `end_angle` (degrees default; strings `"38 deg"` / `"1.5 rad"`
  for explicit units). If the CCW sweep from start to end exceeds
  180°, the builder silently swaps endpoints so the arc goes the
  shorter way — matches Onshape UI's three-point-arc default. Need
  the long way? Pass `"short_arc": false` on the arc entity.
- **Entity IDs must be unique within a sketch.** Duplicate id → raise.
- **Sub-point refs aren't validated.** `circle.start` makes no sense
  but the builder won't catch it; Onshape rejects at solve time.
- **Over-constraint surfaces as `SKETCH_SOLVE_FAILED` /
  `SKETCH_UNSOLVABLE_CONSTRAINT` WARNING.** Onshape's REST API does
  NOT return per-constraint diagnostics — silence is a platform
  limitation. Recovery is client-side bisection: give every
  `addConstraint` an explicit `id`, and when a solve fails use
  `edit_sketch` with `removeIds` to drop half the last-added
  constraints, re-POST, and binary-search. Typical culprits:
  mutually exclusive pairs (PARALLEL + PERPENDICULAR on the same
  two lines), redundant positional constraints (COINCIDENT chain
  over-specifying endpoints), or tangent-line geometry that forces
  an arc into an impossible shape.

### Iteration with edit_sketch

Don't delete-and-rebuild a sketch. `edit_sketch` takes a
`sketchFeatureId` + `addEntities` / `addConstraints` / `removeIds`
and splices.

```json
edit_sketch({
  "sketchFeatureId": "Fabc_0",
  "addEntities": [{"id": "bore", "type": "circle", "center": [0,0], "radius": "18 mm"}],
  "addConstraints": [
    {"id": "d_bore", "type": "DIAMETER", "entity": "bore", "value": "36 mm"},
    {"id": "c_bore", "type": "CONCENTRIC", "entities": ["bore", "hub"]}
  ]
})
```

Removing an entity cascades: any constraint referencing it (directly
or via sub-point) gets auto-dropped and reported in
`cascaded_removals: [{constraint_id, referenced}]`. Read that field
— otherwise a silent 48→12 constraint scrub bites three turns later.

## The entity-first protocol

**Never** sketch on a face, fillet an edge, chamfer an edge, or mate to a face without calling `list_entities` or `describe_part_studio` first and picking the entity by reading its description.

Good picks:
- "the top face of the plate" → filter `type == "PLANE" and normal_axis == "+Z"`, then `max(by origin[2])`.
- "the cylindrical hole" → filter `type == "CYLINDER"`, then by radius.
- "the outer edges of the top face" → filter edges by `direction_axis in ("+X","+Y","-X","-Y")` at `z_max`.

Face/edge IDs are strings like `JHK`, `JNC`, `JHl`. Drop them verbatim into tool args as `faceId` or `edgeIds: ["JHK", ...]`.

## The regen-check protocol

`apply_feature_and_check` (used by every mutating tool) returns `{ok, status, feature_id, feature_name, error_message}`. Interpret:

- `status == "OK"` → feature built cleanly.
- `status == "INFO"` → Onshape auto-adjusted something. `ok=True` but READ `error_message`: common notes include "extrude was through-all auto-clamped" (fine) and "nothing was cut" (bad — you probably got the extrude direction wrong).
- `status == "WARNING"` → feature built but Onshape is concerned. Read and decide.
- `status == "ERROR"` → feature did not build. Do NOT add more features on top of it. Either fix the parameters and re-POST via `update_feature`, or `delete_feature_by_name` and retry.

Mate handlers (`create_fastened_mate` / `create_revolute_mate` / `create_slider_mate` / `create_cylindrical_mate` / `create_mate_connector`) share the same `{ok, status, ...}` contract via `apply_assembly_feature_and_check`. A mate that silently flips an instance still shows up as `status="ERROR"` or `"WARNING"` on the mate-level response — no need to visually check every mate just to catch a solver rejection. The 4-mate-for-2-part bracket dogfood burned ~50 turns to the now-fixed prose-return of this path.

## Extrude-on-face direction trap

Cutting a hole from a +Z face (e.g. sketch on the top of a plate, then REMOVE-extrude to make a hole): the default direction is the sketch normal, which points **away from the material** (+Z into air). The cut removes nothing; Onshape returns `INFO: nothing was cut`.

**Auto-default (current):** when `create_extrude` sees `operationType=REMOVE` on a sketch placed on a picked face (any non-standard plane), it now defaults `oppositeDirection=true` so the cut goes INTO the material. The structured response includes a `notes` entry like `"auto-set oppositeDirection=true because this REMOVE extrude is sketched on a picked face -- cutting INTO the material, not out into air"` so you know what got auto-decided.

**Override:** pass `oppositeDirection: false` explicitly on `create_extrude` if you actually want to cut away from the face (e.g. cutting through from underneath into a body that hangs below). The auto-flip only fires when `oppositeDirection` is omitted from the tool args.

## When to measure vs when to eyeball

- **Measure**: parallelism, perpendicularity, distances between known faces, hole depth, thickness, concentricity. Always more precise than reading a render.
- **Eyeball** (with the critic if available): overall symmetry, topology sanity ("does it look like a motor mount"), unexpected extra features, missing holes the brief asked for.

`measure(entityAId, entityBId)` returns `point_distance_m` always, `angle_deg`, `parallel`/`perpendicular` flags, and — for the special cases (face-face with parallel normals, face-point) — a `projected_distance_m` which is the actual geometric distance.

## Gemini second opinion

If `GEMINI_API_KEY` is set, every `inspect` step in the CAD driver harness auto-routes the render through Gemini for a strict visual review. Output goes to the snapshot .txt file. If Gemini disagrees (missing or wrong features) and you're confident your text checks pass, go look at the render yourself — Gemini can be wrong but is often right when its signal says "I don't see the ø30 housing".

## Variables

Parametric variables live in a separate **Variable Studio** element, not in the Part Studio itself. Workflow:

1. Call `create_variable_studio(...)` once per document to create a VS element. Reuse its element id across all variable writes in the same workspace.
2. `set_variable(vs_element_id, name, expression)` — writes to the VS element, NOT the Part Studio.
3. Sketch tools accept `variableWidth`/`variableHeight`/`variableRadius`/`variableCenter` args that reference these names as `#name` expressions. The variable resolver walks workspace VS elements, so any Part Studio in the same workspace can use them.

**Trap:** `GET variables` on a Part Studio element id returns `[]` even when variables are set — you must read from the VS element. If a diagnostic says "no variables" after a set, you're reading the wrong element.

**Historical gotcha** (fixed 2026-04-17, commit `[sketch-vars-face]` e6dd198): earlier `set_variable` used a POST that REPLACED the VS contents, so each call silently wiped prior variables. Now it upserts by name. If you see a sketch WARNING referencing `#varname` and think "but I just set that variable," verify the VS still contains ALL the variables you expected — not just the most recent one.

**Known-broken: `variableCenter`.** The per-axis DISTANCE-from-origin constraint references `localFirst: "origin"`, but Onshape sketches don't expose the Part Studio origin as a local sketch entity, so the payload produces `SKETCH_MISSING_LOCAL_REFERENCE (WARNING)` and the center is never actually driven by the variable. Investigation: `scratchpad/signed-variable-center-investigation.md`. Until the helper is fixed to use `externalFirst` with a query of the Origin feature (or a mirror-pattern helper is built):
- Do NOT pass `variableCenter`. It fails silently (sketch still places the seed geometry, so it often *looks* correct until you change the variable).
- For parametric hole positions, use **two explicit coordinates per hole**. Write `#hole_offset` and `#minus_hole_offset` variables, set the second to `-hole_offset` in your VS, and pass them as separate values in each hole's `center` field: `center: ["#hole_offset", "#hole_offset"]` for the +,+ corner, `["#minus_hole_offset", "#hole_offset"]` for -,+, etc. Bare numbers still work for non-parametric cases.
- The `variableRadius` path is safe — it uses a RADIUS constraint that resolves correctly.

## When to use FeatureScript

The plugin wraps sketches, extrudes, revolves, thickens, fillets, chamfers, patterns, booleans, mates, **shells** (`create_shell`), and **offset planes** (`create_offset_plane`). Anything else — threads (ISO, UTS), drafts, lofts, sweeps, helical cuts, patterns along a path, variable-radius fillets — needs FeatureScript via `write_featurescript_feature`.

## When to write a FeatureScript custom feature

**Before writing FS from scratch, check `docs/fs-cookbook/` in this repo for a proven snippet to adapt.** Each cookbook file is a complete `defineFeature(...)` you can paste into `featureScript`, change a few numbers, and ship. Direct authorship of less-common ops burns 5-15 turns on opaque REGEN_ERRORs that the cookbook recipes have already worked through. Today's index: `helix.fs` (threads, springs, augers, helical ribs — avoids the broken `opHelix` API). Add a recipe when you find a pattern that works after >2 failed attempts.

Tool responses now include a `hints` list that points at this section; don't ignore it. Three triggers:

1. **You've done the same 3+ feature pattern twice.** Threads (sketch helix + sweep + cosmetic), bolt-circle patterns (variable + sketch + N circles + cut + annotation), standard grooves (offset + sweep-cut + fillet). The second time you write it by hand you're paying a turns-tax that never amortizes.
2. **A primitive tool can't express it.** Helical cut, loft between profiles, draft on a set of faces, sweep along a 3D path, variable-radius fillet, per-face-thickness shell. These have no MCP tool today and won't grow one; FS is the answer. (Uniform-thickness shells DO have a primitive — `create_shell`. Offset construction planes DO too — `create_offset_plane`. Reach for FS only when you need the non-uniform / multi-face version.)
3. **You need per-instance parameters beyond what update_feature handles.** If you want `set_variable(hole_d_m3)` to retarget 8 through-holes and 8 counterbores in one shot, package the pair as a custom feature whose definition takes `hole_d` + `cbore_d` parameters. `update_feature` only tweaks one feature's params; a custom feature lets one variable bump drive the whole chain.

**Minimal template** (copy, adapt, pass as `featureScript` to `write_featurescript_feature`):

```
FeatureScript 2909;
import(path : "onshape/std/geometry.fs", version : "2909.0");

annotation { "Feature Type Name" : "My Custom Feature" }
export const myCustomFeature = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Length" }
        isLength(definition.length, LENGTH_BOUNDS);
        // Add more parameters here: isAngle, isReal, isInteger, isBoolean, etc.
    }
    {
        // Body of the feature -- call op* primitives from onshape/std.
        // opPlane(context, id + "plane1", { "plane" : plane(vector(0,0,1)*definition.length, vector(0,0,1)) });
        // opExtrude(context, id + "ext1", { "entities": ..., "direction": ..., "endBound": ..., "endBoundEntity": ... });
    });
```

Call from the MCP layer:

```
write_featurescript_feature(
  documentId, workspaceId, elementId,
  feature_type="myCustomFeature",
  feature_name="Instance name",
  feature_script="<the FS source above>",
  parameters=[{"id": "length", "type": "quantity", "value": "15 mm"}],
)
```

The orchestrator creates a Feature Studio element, uploads the source, pulls the microversion, and instantiates via BTMFeature-134 with the correct `e<eid>::m<mv>` namespace. You get back a `FeatureApplyResult` with the usual `{status, feature_id, error_message, hints}` contract — regen errors in your FS body propagate through exactly the same way as starter-feature errors.

## ToolSearch efficiency

This MCP server exposes many deferred tools. Every time you call a tool that hasn't been loaded, the runtime spends a round-trip loading the schema. **Batch-load the tool surface in one `ToolSearch` call upfront**:

```
ToolSearch(query="select:mcp__onshape__create_sketch,mcp__onshape__create_sketch_rectangle,mcp__onshape__create_sketch_circle,mcp__onshape__create_extrude,mcp__onshape__create_fillet,mcp__onshape__create_chamfer,mcp__onshape__create_shell,mcp__onshape__create_offset_plane,mcp__onshape__list_entities,mcp__onshape__describe_part_studio,mcp__onshape__measure,mcp__onshape__get_mass_properties,mcp__onshape__export_part_studio,mcp__onshape__create_document,mcp__onshape__create_part_studio", max_results=15)
```

Saves 3-5 individual search calls per session. The multi-entity `create_sketch` collapses a lot of small cases; prefer it over per-primitive tools.

## Iteration discipline

This is a CAD session, not a script. When a feature builds wrong:

1. Don't stack a "fix" feature on top. Diagnose the wrong one.
2. `update_feature` to tweak parameters if the shape is close. `delete_feature_by_name` + re-add if it's the wrong shape entirely.
3. Re-run the same describe + assert you used to catch it.
4. If you're fighting the same feature three times, pause and ask whether the approach is wrong. Maybe you need a FeatureScript custom feature, or the whole build should be re-ordered.
