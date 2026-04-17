// FS COOKBOOK: helical sweep (threads, springs, augers, etc.)
//
// WHY THIS RECIPE EXISTS:
// `opHelix` (the named std-library helix op) has been a reliable failure
// source in agent-driven dogfood: opaque REGEN_ERROR with no surfaced
// arg-shape diagnostic (its definition map shape is non-obvious -- it
// wants `bodyType`/`startMode`/`endMode` enums, not the more intuitive
// `interval` + `clockwise` pair). Two independent dogfood runs
// (run-1776408083 + run-1776408311) both rediscovered the same
// `opFitSpline` + `opSweep` workaround after 5-15 wasted turns. Don't
// repeat that loop -- adapt this instead.
//
// PATTERN (works for any thread/spring/auger):
//   1. Sample N points along a parametric helix:
//        x = R*cos(theta),  y = R*sin(theta),  z = pitch * t
//      where theta = +/- 2*pi*turns*t  (sign chooses handedness).
//      Right-handed (advance +Z, viewed from +Z is clockwise) needs
//      theta = -2*pi*turns*t.
//   2. opFitSpline through those points -> a single curve edge.
//   3. Sketch the profile (V for thread, circle for spring, etc.) on a
//      plane perpendicular to the helix axis at the helix START.
//   4. opSweep that profile along the spline edge.
//   5. opBoolean (SUBTRACTION for threads, UNION for springs) to merge
//      with the existing shaft body. Use SUBTRACTION here: the swept
//      V-profile is the trench, not the thread crest.
//
// GOTCHAS:
//   - Strip units (`x / meter`) before doing trig, then re-apply
//     `* meter` when assembling vectors. Mixing units inside trig
//     silently produces NaN.
//   - Overshoot the helix at both ends (extra turns) so the sweep cuts
//     past the shaft endcaps, otherwise the boolean leaves slivers.
//   - 48 sample points per turn is plenty for 1.5 mm pitch. Drop to 24
//     if regen feels slow on long threads; bump to 96 only if visual
//     facets appear.
//   - V-profile is in the X-Z plane (sketch local x = radial, sketch
//     local y = axial). The plane normal vector(0,-1,0) flips the local
//     y-axis to point in +Z. Get this wrong and the V points the wrong
//     way -- harmless, but gives a non-symmetric thread.
//
// VERIFIED: M10x1.5 thread on a ø10x40 mm shaft, render-confirmed
// (run-1776408083 turn 58, 2026-04-17).

FeatureScript 2931;
import(path : "onshape/std/geometry.fs", version : "2931.0");

annotation { "Feature Type Name" : "Helical Sweep" }
export const helicalSweep = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Pitch (axial advance per turn)" }
        isLength(definition.pitch, LENGTH_BOUNDS);
        annotation { "Name" : "Helix radius" }
        isLength(definition.radius, LENGTH_BOUNDS);
        annotation { "Name" : "Length along axis" }
        isLength(definition.length, LENGTH_BOUNDS);
        annotation { "Name" : "Profile depth (radial)" }
        isLength(definition.profileDepth, LENGTH_BOUNDS);
        annotation { "Name" : "Profile crest width (axial)" }
        isLength(definition.profileWidth, LENGTH_BOUNDS);
        annotation { "Name" : "Right-handed (false = left-handed)" }
        definition.rightHanded is boolean;
        annotation { "Name" : "Subtract from existing bodies (false = leave as standalone solid)" }
        definition.subtract is boolean;
    }
    {
        // --- Strip units for trig math, reapply * meter on vector build.
        const Pm = definition.pitch / meter;
        const rm = definition.radius / meter;
        const Lm = definition.length / meter;
        const hm = definition.profileDepth / meter;
        const wm = definition.profileWidth / meter;

        // --- Overshoot ends by 2 turns so the sweep clears the shaft.
        const extra = 2;
        const zStartM = -extra * Pm;
        const zEndM   = Lm + extra * Pm;
        const totalLenM = zEndM - zStartM;
        const totalTurns = totalLenM / Pm;

        // --- Sample the helix as N points and fit a spline through them.
        // theta sign: -2*pi for right-handed (advance +Z), +2*pi for left.
        const handSign = if (definition.rightHanded) -1 else 1;
        const nPerTurn = 48;
        const nPts = floor(totalTurns * nPerTurn) + 1;
        var pts = [];
        for (var i = 0; i < nPts; i += 1)
        {
            const t = i / (nPts - 1);
            const zM = zStartM + t * totalLenM;
            const theta = handSign * 2 * PI * totalTurns * t;
            pts = append(pts,
                vector(rm * cos(theta * radian), rm * sin(theta * radian), zM) * meter);
        }
        opFitSpline(context, id + "helix", { "points" : pts });

        // --- V-profile in the X-Z plane at the helix start.
        // Plane: origin at z=zStart, normal -Y, local x-axis +X.
        // That makes sketch local-y point in +Z (axial direction).
        const r = definition.radius;
        const h = definition.profileDepth;
        const w = definition.profileWidth;
        const zStart = zStartM * meter;
        var sketch = newSketchOnPlane(context, id + "profile", {
            "sketchPlane" : plane(
                vector(0 * meter, 0 * meter, zStart),
                vector(0, -1, 0),
                vector(1, 0, 0))
        });
        // Triangle: tip at radius (r-h), crest from (r, +w/2) to (r, -w/2).
        skLineSegment(sketch, "l1", { "start" : vector(r - h, 0 * meter), "end" : vector(r,  w / 2) });
        skLineSegment(sketch, "l2", { "start" : vector(r,  w / 2),        "end" : vector(r, -w / 2) });
        skLineSegment(sketch, "l3", { "start" : vector(r, -w / 2),        "end" : vector(r - h, 0 * meter) });
        skSolve(sketch);

        // --- Sweep V along helix to make the trench (or rib) solid.
        opSweep(context, id + "sweep", {
            "profiles" : qSketchRegion(id + "profile"),
            "path"     : qCreatedBy(id + "helix", EntityType.EDGE)
        });

        // --- Optional boolean: subtract trench from existing shaft body.
        if (definition.subtract)
        {
            opBoolean(context, id + "cut", {
                "tools"         : qCreatedBy(id + "sweep", EntityType.BODY),
                "targets"       : qSubtraction(qAllNonMeshSolidBodies(),
                                               qCreatedBy(id + "sweep", EntityType.BODY)),
                "operationType" : BooleanOperationType.SUBTRACTION
            });
        }
    });

// ----------------------------------------------------------------------------
// USAGE EXAMPLES (set as `parameters` on write_featurescript_feature call):
//
// M10x1.5 right-handed external thread (cut from a ø10x40 shaft):
//   featureType: "helicalSweep"
//   parameters: [
//     {id: "pitch",        type: "quantity", value: "1.5 mm"},
//     {id: "radius",       type: "quantity", value: "5 mm"},   // ø10 -> r5
//     {id: "length",       type: "quantity", value: "40 mm"},
//     {id: "profileDepth", type: "quantity", value: "0.92 mm"}, // 0.6134*pitch (ISO)
//     {id: "profileWidth", type: "quantity", value: "1.06 mm"}, // crest 0.706*pitch
//     {id: "rightHanded",  type: "boolean",  value: true},
//     {id: "subtract",     type: "boolean",  value: true},
//   ]
//
// 1/4-20 UNC right-handed external thread:
//   pitch=1.27 mm (1"/20), radius=3.175 mm (ø1/4 / 2),
//   profileDepth=0.78 mm, profileWidth=0.9 mm.
//
// Compression spring (round wire wrapped helically, no shaft):
//   Replace the V-profile sketch with skCircle of wire radius. Pass
//   subtract=false. Drop the V-profile lines and put one skCircle in the
//   sketchPlane: skCircle(sketch, "wire", {"center": vector(r, 0*meter),
//   "radius": wireRadius}).
