# v006-crop-the-callouts

- parent: `v005-drawing-dim-crosscheck`
- created: 1776574128
- source: `eval/variants/v005-drawing-dim-crosscheck/skills/onshape/SKILL.md`

## Mutation

Add SKILL guidance: use new load_local_image MCP tool to push brief's reference drawing into image cache, then crop_image on each callout region at native resolution to read the numeric dimension. Targets scale-reading failure: drawing PNG is 1980x1530 but inline-base64 attachment is too downsampled for Claude to reliably read tiny dimension numbers.

## Metadata (JSON)

```json
{
  "variant_id": "v006-crop-the-callouts",
  "parent_variant_id": "v005-drawing-dim-crosscheck",
  "created_at": 1776574128,
  "mutation_description": "Add SKILL guidance: use new load_local_image MCP tool to push brief's reference drawing into image cache, then crop_image on each callout region at native resolution to read the numeric dimension. Targets scale-reading failure: drawing PNG is 1980x1530 but inline-base64 attachment is too downsampled for Claude to reliably read tiny dimension numbers.",
  "source_skill": "eval/variants/v005-drawing-dim-crosscheck/skills/onshape/SKILL.md"
}
```
