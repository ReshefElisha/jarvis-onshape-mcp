# Assembly Workflow Guide

Methodology for building Onshape assemblies using the MCP server tools. Derived from real-world testing on multi-part assemblies (cabinets, drawers with slider mates).

## Assembly Planning

### 1. Understand the Design

Before calling any tools, plan the assembly:

- **Identify all parts** and which Part Studios they come from
- **Choose a reference part** — typically the largest or most central part (e.g., a back panel, base plate)
- **Plan the mate order** — work inside-out from the reference part
- **Identify mate types** — fastened for rigid connections, slider/revolute/cylindrical for motion

### 2. Ground a Reference Part

Every assembly needs one fixed (grounded) reference part. This anchors the solver.

- The first instance added to an assembly is grounded by default
- All other parts are positioned relative to this reference
- **Critical**: Fixed/grounded instances cannot be moved via the API (`transform_instance` and `set_instance_position` both fail with 400 errors)
- If the reference part is at the wrong position, you must unfix it in the Onshape UI, reposition, then re-fix

### 3. Work in Batches

Don't create all mates at once. Work in batches and verify between each:

1. Add all instances to the assembly
2. Position the first group of parts near their target locations
3. Create fastened mates for rigid connections
4. Verify positions with `get_assembly_positions`
5. Move to the next group (e.g., drawers, moving parts)
6. Create motion mates (slider, revolute)
7. Verify final positions

## Positioning Parts

### Absolute vs Relative Positioning

- **`transform_instance`** — Applies a RELATIVE transform (delta from current position)
- **`set_instance_position`** — Sets an ABSOLUTE position (resets rotation to identity)
- **`align_instance_to_face`** — Aligns one instance flush against a face of another

### Reference-Part Awareness

Absolute positions are in world coordinates, not relative to any part. If your reference part is at position (10, 50, -20), a part that should be 5 inches to the right needs an absolute position of (15, 50, -20), not (5, 0, 0).

**Always check the reference part position first:**

```
1. Call get_assembly_positions
2. Find the reference part's position
3. Calculate absolute = reference_position + desired_relative_offset
4. Call set_instance_position with the calculated absolute position
```

### Positioning and Mates Interaction

When you create a mate, the Onshape solver may reposition parts to satisfy the constraint. Two approaches:

**Approach A: Position then mate** (recommended for fastened mates)
1. Position parts at approximate locations
2. Create fastened mates — solver will fine-tune positions
3. Verify positions after mating

**Approach B: Mate then verify** (recommended for motion mates)
1. Position parts at their correct locations (accounting for reference part position)
2. Create the motion mate — solver should keep parts near their current position
3. Verify positions — if wrong, delete mate, reposition, recreate

## Mate Connectors

### Face IDs

Get face IDs using `get_body_details` on the Part Studio (not the assembly). Face deterministic IDs (e.g., "JHW") are stable and reusable across all assembly instances of the same part.

### Local Coordinate System

Each mate connector has a local coordinate system:
- **Z-axis**: Along the face normal (outward)
- **X-axis**: In-plane, determined by `secondaryAxisType`
- **Y-axis**: Completes the right-hand system

**Offsets are in local coordinates:**
- `offsetX` / `offsetY`: Move within the face plane
- `offsetZ`: Move along the face normal

### Flipping the Primary Axis

`flipPrimary: true` reverses the Z-axis direction. Because of the right-hand rule, this also changes the X and Y axis directions. If you were using Y-offset translations, flipping Z means the Y-offset now maps to the opposite world-space direction.

**Rule of thumb**: If you flip the primary axis and use translations, test with one instance first and verify positions before applying to a batch.

## Fastened Mate Face Selection

### The Anti-Parallel Problem

Fastened mates work by aligning the coordinate frames of two mate connectors. When you pick two faces that are **anti-parallel** (facing each other, like a face-to-face contact), the MC Z-axes point in opposite directions. The solver must rotate one part 180° to make the frames match.

**When this works**: If one part is grounded (fixed), the solver rotates the free part around the MC point. Since the grounded part can't move, the result is usually correct.

**When this fails**: If both parts are free-floating, the solver may rotate either part, or both, producing unexpected positions. For example, a drawer left panel may flip from Y=[-16, -2] to Y=[-30, -16] — a 180° rotation around the MC point at Y=-16.

### Same-Direction Face Technique (Recommended)

Instead of picking faces that touch (anti-parallel), pick faces on both parts that have the **same outward normal direction**:

```
WRONG (anti-parallel):
  Part A face: normal = (0, -1, 0)   ← faces toward Part B
  Part B face: normal = (0, +1, 0)   ← faces toward Part A
  Result: Solver rotates Part B 180° to align Z-axes

RIGHT (same direction):
  Part A face: normal = (0, -1, 0)   ← faces same direction
  Part B face: normal = (0, -1, 0)   ← faces same direction
  Result: MC frames already match, solver only translates
```

Since same-direction faces are not coplanar (they're on opposite sides of the parts), use `offsetZ` to bridge the gap:

```
create_fastened_mate(
    firstInstanceId=front_panel,
    secondInstanceId=left_panel,
    firstFaceId="JHK",          # -Y face on front panel
    secondFaceId="JHK",         # -Y face on left panel (same direction!)
    firstOffsetZ=-0.75,         # Bridge the 0.75" gap between faces
)
```

### When to Use Each Approach

| Scenario | Approach | Why |
|----------|----------|-----|
| Mating to grounded part | Anti-parallel OK | Grounded part anchors the solver |
| Mating two free parts | Same-direction required | Prevents 180° rotation |
| Symmetric parts | Same-direction + offsets | Avoids ambiguous solutions |

## Directional Mates (Slider, Revolute, Cylindrical)

### Instance Order Determines Direction

For all directional mates, the **first instance moves relative to the second**:

- **Slider**: First instance slides along the MC Z-axis. Positive travel = away from second instance along the face normal.
- **Revolute**: First instance rotates around the MC Z-axis relative to the second.
- **Cylindrical**: First instance slides and rotates relative to the second.

**To reverse the direction**, swap the instance order (swap `firstInstanceId`/`secondInstanceId` and their corresponding face IDs).

**Example — Drawer slider:**
- If cabinet is first, drawer is second → positive = pushes drawer backward into cabinet
- If drawer is first, cabinet is second → positive = pulls drawer forward out of cabinet

### Motion Limits

Limits constrain the range of motion:
- Slider/Cylindrical: `minLimit` and `maxLimit` in inches
- Revolute: `minLimit` and `maxLimit` in degrees

**Known limitation**: API-set limits may cause the Onshape solver to re-evaluate the assembly from scratch rather than using the current position as a starting hint. This can result in:
- Parts flipping to unexpected orientations
- Animation failing with "Unable to compute any steps for this animation"

**Workaround**: Create mates without limits first, verify positions and animation work correctly, then add limits manually in the Onshape UI if needed.

## Solver Behavior

### How the Solver Works

When you create or modify a mate, the Onshape solver recalculates all part positions to satisfy all constraints simultaneously.

**Without limits**: The solver uses the current part position as a "hint" and finds the nearest valid solution. This usually preserves the intended configuration.

**With limits**: The solver may re-evaluate from scratch, potentially finding a mathematically valid but visually wrong solution (e.g., a drawer flipped upside down).

### The "Solve" Button

Clicking "Solve" in the Onshape UI forces a full re-solve. If mate connectors don't uniquely determine the part orientation (e.g., face-centered MCs on symmetric faces), the solver may find a different valid configuration than intended.

### Debugging Solver Issues

1. **Check feature states** with `get_assembly_features` — look for ERROR or SUPPRESSED features
2. **Check positions** with `get_assembly_positions` — compare against expected relative positions
3. **Delete and recreate** problematic mates — sometimes the solver state needs a reset
4. **Simplify** — if a complex mate fails, try a simpler one first (fastened instead of slider) to verify the MC setup is correct

## Verification Methodology

### Always Verify After Mating

After creating any mate, verify the assembly:

```
1. get_assembly_features → check all features are OK (no errors)
2. get_assembly_positions → check all instance positions
3. Calculate relative positions: instance_pos - reference_pos
4. Compare against expected relative positions (tolerance ~0.5 inches for rough check)
```

### Position Checks

When verifying positions, always compute **relative to the reference part**, not absolute positions. The reference part may be at an arbitrary absolute position.

```
relative_x = instance_x - reference_x
relative_y = instance_y - reference_y
relative_z = instance_z - reference_z
```

### Feature State Checks

After batch operations, verify all features are healthy:

```
get_assembly_features → for each feature:
  - "OK" = working correctly
  - "ERROR" = constraint cannot be satisfied
  - "SUPPRESSED" = intentionally disabled
```

## Common Mistakes

### 1. Forgetting Reference Part Offset
Setting `set_instance_position(x=5, y=10, z=0)` when the reference part is at (100, 200, 300) — the part ends up far from the assembly.

### 2. Wrong Instance Order for Directional Mates
Putting the cabinet first and drawer second in a slider mate, then wondering why positive travel pushes the drawer backward.

### 3. Creating Mates Before Positioning
Creating a slider mate before positioning the drawer correctly. The solver may use a far-away position as the starting hint, producing unexpected results.

### 4. Not Verifying Between Batches
Creating 10 mates at once and then finding positions are all wrong. Much harder to debug than creating 2-3 at a time with verification in between.

### 5. Trying to Move Fixed Instances
Using `transform_instance` or `set_instance_position` on a grounded part. The API returns a 400 error: "Attempt to transform a fixed instance(s) failed."

### 6. Assuming Symmetric Faces Have Unique Solutions

A mate connector at the center of a square face has multiple valid orientations. The solver may pick any of them. Use offsets or asymmetric faces when orientation matters.

### 7. Using Anti-Parallel Faces Between Free-Floating Parts

Picking face-to-face contact surfaces (opposite normals) for fastened mates between two free-floating parts. The solver rotates one part 180° to align the MC frames. Use same-direction faces instead (see "Fastened Mate Face Selection" above).

## Tool Quick Reference

| Task | Tool | Notes |
|------|------|-------|
| Find face IDs | `get_body_details` | Use Part Studio element ID, not assembly |
| Check current positions | `get_assembly_positions` | Returns absolute positions in inches |
| Check feature health | `get_assembly_features` | Shows OK/ERROR/SUPPRESSED states |
| Rigid connection | `create_fastened_mate` | No motion, locks all 6 DOF |
| Linear motion | `create_slider_mate` | 1 DOF, first instance slides |
| Rotational motion | `create_revolute_mate` | 1 DOF, first instance rotates |
| Slide + rotate | `create_cylindrical_mate` | 2 DOF, first instance moves |
| Custom MC placement | `create_mate_connector` | For advanced mate setups |
| Move part (relative) | `transform_instance` | Delta from current position |
| Move part (absolute) | `set_instance_position` | Resets rotation; fails on fixed parts |
| Align to face | `align_instance_to_face` | Moves one axis only |
| Interference check | `check_assembly_interference` | Bounding-box based overlap detection |
