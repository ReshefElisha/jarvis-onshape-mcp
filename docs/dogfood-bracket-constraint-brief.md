# Dogfood brief: 2-slot mounting bracket with keyhole

Second dogfood for the constraint-first sketch surface (228kto1m runs the
clevis transcription brief in parallel). Smaller scope than the clevis but
forces every constraint type the lead enumerated AND the `edit_sketch`
iteration path on a realistic second pass.

## The brief (what Shef pastes in)

> Build an aluminum mounting bracket as a single Part Studio. Plate
> footprint 80 × 40 × 6 mm. Machine the following features into the top
> face, all parametric (use a Variable Studio for the dimensions named in
> brackets):
>
> - Two **parallel slots**, axes running the long way of the plate.
>   Each slot is `[slot_length=30 mm]` long, `[slot_width=8 mm]` wide
>   (full radius ends, no flats). The slot **centers** sit 10 mm in from
>   each long edge and 12 mm in from each short edge — i.e. the two slot
>   axes are parallel to the plate's long edge, 20 mm apart, centered on
>   the plate's short axis. Define them with proper TANGENT/CONCENTRIC
>   constraints between the side lines and the end arcs, not by raw
>   coordinates.
> - **Plate corner fillets** R `[corner_r=5 mm]`.
> - A centered **keyhole** in the middle of the plate: a circular hole of
>   `[key_d=10 mm]` diameter coincident with the plate's geometric
>   center, with a tangent slot extending 12 mm to one side
>   (4 mm wide). The keyhole is added in a **second pass via
>   `edit_sketch`**, not in the first sketch — explicitly to exercise
>   the iteration surface.
>
> Verify each step with `describe_part_studio` and a render. After the
> bracket is verified, change `slot_width` from 8 mm to 6 mm and
> `key_d` from 10 to 12 via `set_variable` and re-render to confirm
> the parametric chain still drives the geometry.

## Constraint coverage matrix

| Constraint | Where it shows up |
|---|---|
| **DIAMETER** | `key_d` on the keyhole circle; sets size of slot end arcs (via radius = slot_width/2). |
| **DISTANCE** | Slot end-to-end length (= `slot_length`); slot-axis to plate edge (= 10 mm both sides); slot-end to short edge (= 12 mm both sides). |
| **TANGENT** | Slot side line to slot end arc (8 tangencies per slot × 2 = 16); keyhole circle to keyhole-extension slot side lines. |
| **COINCIDENT** | Slot side line endpoints to slot end arc endpoints; corner-fillet endpoints; keyhole circle center on plate center. |
| **HORIZONTAL** | Slot axes (parallel-to-long-edge); plate top/bottom outline lines. |
| **CONCENTRIC** | Slot end arcs share an axis (one arc per end, two arcs per slot — both centers on the slot axis). |
| **OFFSET** | Slot side lines = OFFSET from the slot axis (construction line) by `slot_width/2`. |

## Why this brief, not just the clevis

- **Mirror the clevis on a simpler topology.** The clevis is a real
  engineering drawing that 228kto1m is transcribing. This brief is
  invented but covers the same constraint types. If both
  succeed, the surface is robust. If only the bracket succeeds, the
  failure mode is in clevis-specific geometry (Y-fork tangent computation),
  not the constraint surface.
- **Force the `edit_sketch` iteration path.** The keyhole arrives in a
  second pass. That's the literal point of the new tool — exercise it
  on something we know we'd want to add after seeing the first render.
- **Force the parametric retest.** `set_variable` after the build
  confirms that the constraint solver actually rebuilt geometry from
  variable changes, not just from initial coordinates. This was the
  load-bearing thing that broke in the variableCenter dogfood.

## Success criteria (what counts as a pass)

1. **First sketch lands as ONE BTMSketch-151** with both slots + outline +
   corner fillet sub-entities, regen status `OK`. Constraint count ≥ 30
   (8 tangencies/slot × 2 + 4 distance + 4 coincident corners + 2
   horizontal + 2 concentric + at least the OFFSET dimensions).
2. **`edit_sketch` adds keyhole** without re-uploading the slots. Returned
   `cascaded_removals` is empty (we're only adding). `added_entity_ids`
   contains the keyhole circle + slot-extension lines/arcs.
3. **Top face render** shows: plate outline with R5 corners, both slots
   centered correctly relative to the plate edges, keyhole at the middle
   with a tangent slot extending to one side. No floating geometry.
4. **Parametric retest**: `set_variable("slot_width", "6 mm")` → re-render
   shows narrower slots; `set_variable("key_d", "12 mm")` → larger
   keyhole circle. Both without rebuilding the sketch.

## Failure modes worth recording

(For when the dogfood logs go into `scratchpad/sketch-constraints-evidence.md`
the way `fs-failure-evidence.md` did for the prior round.)

- **Degenerate constraint count**: solver lands with regen OK but the
  sketch is fully unconstrained (drag-test would move geometry). This
  is the "looks right, isn't right" failure that the warning-enrich
  fix is supposed to surface. Watch for `WARNING` status with
  `SKETCH_CONSTRAINT_DOF` or similar enums.
- **Sub-point reference rejected**: an `entities: ["line1.start"]`
  reference comes back as `INCOMPATIBLE_FACE_ENTITY` or
  `SKETCH_MISSING_LOCAL_REFERENCE`. Means the serializer's sub-point
  handling needs a probe.
- **`edit_sketch` cascade surprise**: addEntities lands a constraint
  that triggers cascade-remove of an unrelated existing constraint
  because the cascade detector mismatched ids. The
  `cascaded_removals` field is the audit log — Claude should notice.
- **Variable retest no-op**: `set_variable` succeeds, regen succeeds,
  but render shows unchanged geometry. Indicates the dimension
  Quantity isn't bound to the variable expression even though the
  constraint claims to be. (This was the variableCenter bug.)

## Run procedure

```
uv run python tools/agent_sdk_loop.py \
    --brief "$(cat docs/dogfood-bracket-constraint-brief.md | head -40 | tail -25)" \
    --max-turns 50
```

Save the run dir; if anything fails write a per-attempt block in
`scratchpad/sketch-constraints-evidence.md` matching the `fs-failure-evidence.md`
template.
