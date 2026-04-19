# v009-prompt-side-ocr

- parent: `baseline`
- created: 1776581883
- source: `skills/onshape/SKILL.md`

## Mutation

Runner-side change only: harness pre-runs Tesseract OCR on every drawing brief and stamps extracted dim callouts into the prompt as text. Agent gets dims from turn 0 — no tool round-trips, no growing context, no SKILL changes. Tests whether removing the vision-bottleneck (by giving the agent ground-truth callouts) helps the score gap on hard tier.

## Metadata (JSON)

```json
{
  "variant_id": "v009-prompt-side-ocr",
  "parent_variant_id": "baseline",
  "created_at": 1776581883,
  "mutation_description": "Runner-side change only: harness pre-runs Tesseract OCR on every drawing brief and stamps extracted dim callouts into the prompt as text. Agent gets dims from turn 0 \u2014 no tool round-trips, no growing context, no SKILL changes. Tests whether removing the vision-bottleneck (by giving the agent ground-truth callouts) helps the score gap on hard tier.",
  "source_skill": "skills/onshape/SKILL.md"
}
```
