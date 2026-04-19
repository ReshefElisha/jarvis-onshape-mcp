---
name: vision-decompose
description: Look at an engineering reference image (drawing, iso render, photo) and produce a structured feature decomposition BEFORE building anything in Onshape. Output is a feature tree the user can review and the build phase can execute against. Use this whenever the user gives you a reference image and asks you to model it. Skip if the user has already described the part in plain text.
---

# CAD Vision Decomposition — describe before you build

When the user shares an engineering reference image and asks you to build
it, your first job is NOT to start `create_document`. It is to produce a
rigorous, structured feature tree the user can sanity-check and the build
phase can execute against.

Why this matters: vision-to-CAD is the hard part of this loop, not
CAD-to-CAD. If you skim the image and jump to building, you'll mis-read
features (boss → pocket, complex pill outline → rounded rectangle, missed
callouts) and burn a long iteration loop fixing errors you could have
caught in 30 seconds of careful looking. A good decomposition makes the
build trivial — show it to the user, get a quick confirmation or
correction, then build with confidence.

## What you have

- The reference image(s): a drawing with callouts, an iso/multi-view
  render, a photo, or a hand sketch. Whatever the user provided.
- `mcp__onshape__load_local_image(imagePath)` — cache an image (typically
  the user's reference, on disk) at native resolution.
- `mcp__onshape__crop_image(imageId, x1, y1, x2, y2)` — zoom into a region
  of any cached image. Crops are independently re-loadable; use them
  liberally to read small text or count features.

## What you produce

A single structured response in this exact format:

```
## OVERVIEW
One sentence: what IS this part? (bracket / plate / flange / housing / etc.)

## ENVELOPE
Approximate overall dimensions in mm if readable from callouts. State each
axis: X_length × Y_width × Z_height. If unreadable, say "UNKNOWN" and the
build phase will need a reasonable default or ask the user.

## FEATURE TREE

F1: <short name>
  type: base-plate | boss | through-hole | blind-hole | pocket | slot | fillet | chamfer | counterbore | countersink | shell | rib | taper | thread | other
  role: primary | secondary | subtractive | cosmetic
  size: approximate mm (diameter, length×width, radius, etc.)
  position: fraction of envelope OR relative to another feature
  face: which face of the part (top / bottom / front / back / left / right / +Z-face-of-F3 / etc.)
  orientation: axis direction (e.g. "axis along +Z")
  count: 1 if single, N if pattern (e.g. 4 for a 4-corner bolt pattern)
  dim_source: drawing_callout | render_inferred
  notes: anything unusual — tolerance, finish, special constraint

F2: ...
...

## RELATIONSHIPS
Which features are subtractive-on-top-of which, which are patterned from which.
List them as one-liners: "F4 (through-hole) is cut INTO F1 (base-plate)."
Critically: when one feature's outline is *derived* from another's
silhouette (e.g. "the inset pocket follows the pill outline minus the two
holes, offset inward 10 mm"), say so explicitly. Derived outlines are the
single biggest class of misread feature in single-image-to-CAD.

## UNCERTAINTIES
Anything you weren't sure about. Be explicit — list what you'd want the
user to confirm before you commit to a build.
```

After producing the structured response, **briefly check with the user**:
"Does this match what you intended? Any corrections before I start
building?" The user has more context than the image alone — let them fix
your read before you spend turns building wrong.

## Think out loud as you work

Before every non-trivial tool call (crop_image, load_local_image), emit a
short plan text (1-3 sentences, plain assistant output) saying **WHY** and
**WHAT YOU EXPECT TO SEE**. Example:

> *"About to crop the top-left quadrant of the drawing — that's where the
> dimension callouts for the main bolt circle usually live on ASME title
> sheets. Expecting to see two Ø dimensions."*

The observer watching the run uses these thought lines to follow your
reasoning. Don't let your only visible output be tool-call JSON.

After each crop, also say in 1-2 sentences **what you actually saw** before
moving on. If the crop didn't show what you expected, name the surprise
explicitly — that's valuable signal.

## How to work

Mandatory steps, in order:

1. **Overview scan.** Look at the attached images for ~5 seconds. Write the
   ONE-SENTENCE overview. Don't try to list features yet.
2. **Cache + count.** For each reference image path, call
   `load_local_image(imagePath=<path>)` so you get a cached image_id.
   Scan the full image for distinct features. Count them mentally.
   If you count ≤ 3 features on a part that fills most of the frame, you're
   missing things — non-trivial engineering parts have 6–12+ distinct features.
3. **Crop-and-describe each feature.** For every feature you counted, use
   `crop_image(imageId=<id>, x1,y1,x2,y2)` to zoom into its region at native
   resolution. State what you see in the crop:
   - shape (circular hole, rectangular pocket, hex recess, radius fillet)
   - size estimate (read callouts if visible, else fraction of envelope)
   - position and orientation
   - role (additive? subtractive? cosmetic?)
4. **Handle the drawing specifically if you have one.** For dimension
   callouts: crop into each one, read the number at native resolution, note
   which feature it applies to. Callouts like `Ø25` mean diameter 25, `R3`
   mean radius 3, `4X` prefix means "this callout applies to 4 instances".
5. **Self-check coverage.** Before finalizing, ask: does my feature tree cover
   every distinct silhouette region of the part? Scan the overview image one
   more time. If there's a feature I see but didn't list, add it.
6. **Output the structured response.** No preamble, no reasoning, just the
   sections above filled in.

## Scope discipline

In this phase, the only tools you should reach for are `load_local_image`
and `crop_image` (plus reading static files). Don't call build tools yet —
finish describing first, then transition to the building phase once the
user confirms the spec.

## Common failure modes to avoid

- **Surface-skimming.** "I see a plate with some holes." That's useless.
  Count the holes. Measure them. Say where they are relative to edges.
- **Feature conflation.** A "rectangular hole" vs a "rectangular pocket with
  a through-hole at its bottom" are different. Distinguish.
- **Missing the backside.** Isometric drawings often show features on the
  hidden face as dashed lines. Look for them.
- **Confusing boss with pocket.** A positive cylindrical bump sticking up is
  a boss (additive). A cylindrical hole going down is a pocket/blind-hole
  (subtractive). Get the polarity right.
- **Simplified outlines.** A pocket whose outline follows a complex
  silhouette (pill, star, bone) is often misread as "rounded rectangle."
  Check whether the pocket boundary is offset from another feature's
  silhouette before you declare its shape.
- **Treating title-block text as a dim.** Numbers near the title block (like
  "2012", "Rev D", scale "1:1") are not part dimensions. Exclude them.
- **Guessing sizes when they're on the drawing.** If a callout says `35.2`,
  that's the dimension. Don't estimate from pixels.

## Length and quality

Budget: 15–25 turns total. You have time to crop several regions. Don't
rush, don't dawdle.

Output quality standard: a competent CAD designer reading only your output
(not the original images) should be able to build the part. If your output
lacks a size, position, or role for a feature, the downstream agent will
guess — and may guess wrong. Be specific.
