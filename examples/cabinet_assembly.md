# Example: Cabinet Assembly with Sliding Drawers

A complete worked example of assembling a cabinet with a rigid frame and 3 sliding drawers using the Onshape MCP server.

## Design Overview

### Parts

**Cabinet frame** (6 parts from one Part Studio):
- Back panel (reference part — grounded)
- Left panel, Right panel
- Bottom shelf, Top shelf
- Door

**Each drawer** (5 parts per drawer, 3 drawers, from separate Part Studios):
- Front panel
- Left side, Right side
- Back panel
- Bottom panel

**Total**: 21 instances, 60 features (51 fastened mates + 9 slider features)

### Assembly Strategy

1. Ground the back panel as the reference
2. Attach frame parts with fastened mates (5 mates = 15 features: 10 MCs + 5 mates)
3. Add drawer instances and position them
4. Attach drawer parts internally with fastened mates (12 mates per drawer = 36 features)
5. Create slider mates between drawers and cabinet (3 sliders = 9 features)

## Step 1: Set Up the Assembly

```
1. create_document → get documentId
2. create_assembly → get assemblyId (elementId)
3. Add all instances from Part Studios using add_assembly_instance
```

The first instance added (back panel) is automatically grounded.

## Step 2: Get Face IDs

Before creating any mates, get the face IDs from each Part Studio:

```
get_body_details(documentId, workspaceId, partStudioElementId)
```

This returns face deterministic IDs like "JHW", "JKG", etc. These IDs are stable — the same face ID works for every instance of that part in the assembly.

**Tip**: Map out which faces you'll use for each mate before starting. For the cabinet:
- Back panel front face → mates with Left, Right, Bottom, Top
- Left panel inner face → mates with drawer left panels (for sliders)

## Step 3: Assemble the Frame (Fastened Mates)

Position frame parts near their targets, then create fastened mates:

```
create_fastened_mate(
    firstInstanceId=back_panel_id,
    secondInstanceId=left_panel_id,
    firstFaceId="JHW",      # back panel left edge face
    secondFaceId="JKG",      # left panel back edge face
    firstOffsetX=0, firstOffsetY=0, firstOffsetZ=0,
    secondOffsetX=0, secondOffsetY=0, secondOffsetZ=0,
)
```

After each batch of mates, verify:

```
get_assembly_features → all features should be "OK"
get_assembly_positions → check relative positions against design
```

### Choosing Faces for Fastened Mates

**When mating to a grounded part** (e.g., the back panel):
- Anti-parallel faces (face-to-face contact) work fine since the grounded part anchors the solver
- Pick the touching faces and the solver rotates the free part into position

**When mating two free-floating parts** (e.g., drawer front → drawer left):
- **Do NOT use anti-parallel faces** — the solver rotates parts 180° to align opposite MC Z-axes
- Instead, use **same-direction faces** (same outward normal on both parts)
- Use `offsetZ` to bridge the gap between the non-coplanar parallel faces

```
# Same-direction technique: both faces have normal (0, -1, 0)
create_fastened_mate(
    firstInstanceId=drawer_front_id,
    secondInstanceId=drawer_left_id,
    firstFaceId="JHK",          # -Y face on front panel
    secondFaceId="JHK",         # -Y face on left panel (same direction!)
    firstOffsetZ=-0.75,         # Bridge the 0.75" gap
)
```

See `knowledge_base/assembly_workflow_guide.md` → "Fastened Mate Face Selection" for full explanation.

## Step 4: Assemble Drawers (Internal Fastened Mates)

Each drawer has 4 internal fastened mates (front→left, front→right, front→back, front→bottom).

Since all 3 drawers use the same Part Studio, the face IDs are identical:

```python
# Same face IDs work for all 3 drawers
DRAWER_FRONT_LEFT_FACE = "ABC"
DRAWER_LEFT_BACK_FACE = "DEF"
```

**Workflow for each drawer:**
1. Position the drawer front panel at the correct absolute location
2. Create fastened mates from front → left, right, back, bottom
3. Verify all 5 drawer parts are correctly positioned

## Step 5: Create Slider Mates

This is the most nuanced step. Key decisions:

### Choosing MC Faces

For a drawer sliding in/out of a cabinet:
- **Cabinet face**: Inner face of the left (or right) panel — the face the drawer slides against
- **Drawer face**: Outer face of the drawer's left (or right) panel — the face that touches the cabinet

### Instance Order (Controls Direction)

**This is critical.** The first instance slides relative to the second:

```
# Drawer first → positive travel = drawer slides OUT (forward)
create_slider_mate(
    firstInstanceId=drawer_left_id,     # ← moving part
    secondInstanceId=cabinet_left_id,   # ← fixed reference
    firstFaceId=drawer_left_face,
    secondFaceId=cabinet_left_face,
)
```

If you put the cabinet first, positive travel pushes the drawer backward (into the cabinet wall).

### Offset Translations on Cabinet MC

When multiple drawers slide against the same cabinet panel, each needs a different MC position on that panel. Use offsets to place the cabinet MC at the correct height for each drawer:

```
# D1 (bottom drawer): offset to lower position on cabinet left face
create_mate_connector(
    instanceId=cabinet_left_id,
    faceId=cabinet_left_face,
    offsetX=0.875,    # in from edge
    offsetY=10.5,     # height for bottom drawer (in MC local coords)
    offsetZ=0,
)

# D2 (middle drawer): different Y offset
create_mate_connector(..., offsetY=1.0, ...)

# D3 (top drawer): different Y offset
create_mate_connector(..., offsetY=-8.5, ...)
```

**Remember**: Offsets are in the MC's **local** coordinate system, not world space. The Y offset on a face pointing in the +X world direction maps to a different world axis than Y offset on a face pointing in +Z.

### Skip Limits Initially

Create slider mates **without** `minLimit`/`maxLimit` first. Limits trigger the Onshape solver to re-evaluate from scratch, which can flip parts to unexpected orientations.

```
# Good: no limits, verify animation works first
create_slider_mate(
    firstInstanceId=drawer_left, secondInstanceId=cabinet_left,
    firstFaceId="JHG", secondFaceId="JKG",
    name="D1 Slider",
    # minLimit and maxLimit omitted
)
```

After verifying the slider works correctly (drawer slides in the right direction, animation works), add limits manually in the Onshape UI if needed.

## Step 6: Verify the Assembly

### Feature Health Check

```
get_assembly_features → expect all 60 features "OK"
```

### Position Verification

```
get_assembly_positions → for each instance:
    relative_pos = instance_pos - back_panel_pos
    compare against expected design positions
```

Expected relative positions (from back panel):
```
Left:     ( 0.00, 16.00,  0.00)    Right:    (23.25, 16.00,  0.00)
Bottom:   ( 0.00,  0.00,  0.00)    Top:      ( 0.00,  0.00, 29.25)
D1-Front: ( 0.75, 16.75,  0.75)    D1-Left:  ( 1.00, 16.00,  0.75)
D2-Front: ( 0.75, 16.75, 10.25)    D2-Left:  ( 1.00, 16.00, 10.25)
D3-Front: ( 0.75, 16.75, 19.75)    D3-Left:  ( 1.00, 16.00, 19.75)
```

### Animation Test

In the Onshape UI:
1. Right-click a slider mate → "Animate"
2. Set the end value (e.g., 10 inches)
3. Verify the drawer slides forward (out of the cabinet)
4. If it slides backward, swap the instance order in the slider mate

## Gotchas and Lessons Learned

### 1. MC Order Determines Slide Direction
The order of instances in `create_slider_mate` determines which direction is "positive." For drawers, put the **drawer first** (moving part) and **cabinet second** (fixed reference) so positive = outward.

### 2. Limits Can Break Animation
API-set limits cause the solver to re-evaluate from scratch. Without limits, the solver uses the current position as a hint. Create mates without limits, verify everything works, then add limits in the UI.

### 3. Fixed Instances Can't Be Moved via API
If the reference part is at the wrong position and is grounded, you can't move it with `transform_instance` or `set_instance_position`. Unfix it in the Onshape UI first.

### 4. Absolute Positions Need Reference Offset
When the back panel is at (100, 200, 300) instead of (0, 0, 0), a drawer at relative (0.75, 16.75, 0.75) needs absolute position (100.75, 216.75, 300.75).

### 5. Same Face IDs Across Instances
Parts from the same Part Studio share face IDs. If the drawer left panel's outer face is "JHG" for drawer 1, it's also "JHG" for drawers 2 and 3.

### 6. Verify Between Batches
Don't create all 60 features at once. Create the frame mates (15 features), verify, then drawer mates (36 features), verify, then sliders (9 features), verify. Much easier to debug 3 features than 60.

### 7. The Solver Can Flip Parts
If you click "Solve" or add limits, the solver may find a valid but wrong configuration (e.g., drawer upside down). This happens because face-centered MCs on symmetric faces don't uniquely determine orientation.

### 8. Anti-Parallel Faces Flip Free-Floating Parts
Using face-to-face contact surfaces (opposite normals) for fastened mates between two free-floating parts causes the solver to rotate one part 180° to align the MC coordinate frames. A drawer left panel at Y=[-16, -2] can flip to Y=[-30, -16]. **Fix**: Use same-direction faces (same outward normal on both parts) with `offsetZ` to bridge the gap. Anti-parallel is only safe when one part is grounded.
