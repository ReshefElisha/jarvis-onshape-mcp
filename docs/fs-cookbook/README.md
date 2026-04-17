# FeatureScript cookbook

Proven, parametric FS recipes for ops that have been observed to fail
under direct LLM authorship. Each entry is a complete `defineFeature(...)`
that you can paste into `write_featurescript_feature`'s `featureScript`
arg, change a few numbers, and ship.

**Use this BEFORE writing a custom FS feature from scratch.** Direct
authorship of less-common ops (opHelix, opBlend, opThicken with non-
trivial bodies) burns 5-15 turns on opaque REGEN_ERRORs. The recipes
here have all been verified end-to-end against the live Onshape API.

| Recipe | When to use |
|---|---|
| [`helix.fs`](helix.fs) | Threads (internal/external), springs (compression/extension), augers, screw conveyors, helical ribs. Anything where a 2D profile sweeps along a helical path. Avoids the broken `opHelix` API in favor of `opFitSpline + opSweep`. |

## Adding a new recipe

When you find an FS pattern that works after >2 failed attempts at the
direct approach, save it here. Format:
- Comment header naming the broken alternative + why the recipe works.
- One `defineFeature(...)` parametric on physically meaningful inputs.
- Worked-example parameter dicts at the bottom (so callers see what
  units / shapes the parameters take).
- A `VERIFIED:` note pointing at the dogfood run + date that confirmed it.

## How `write_featurescript_feature` calls these

```python
write_featurescript_feature(
    documentId=..., workspaceId=..., elementId=...,
    featureType="helicalSweep",          # match `export const <name>`
    featureScript=open("docs/fs-cookbook/helix.fs").read(),
    featureName="M10x1.5 Thread (RH)",
    parameters=[
        {"id": "pitch",        "type": "quantity", "value": "1.5 mm"},
        {"id": "radius",       "type": "quantity", "value": "5 mm"},
        {"id": "length",       "type": "quantity", "value": "40 mm"},
        {"id": "profileDepth", "type": "quantity", "value": "0.92 mm"},
        {"id": "profileWidth", "type": "quantity", "value": "1.06 mm"},
        {"id": "rightHanded",  "type": "boolean",  "value": True},
        {"id": "subtract",     "type": "boolean",  "value": True},
    ],
)
```
