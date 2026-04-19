# v008-extract-then-build

- parent: `v001-plan-from-render`
- created: 1776579279
- source: `eval/variants/v001-plan-from-render/skills/onshape/SKILL.md`

## Mutation

ARCHITECTURAL: new MCP tool extract_drawing_dimensions runs Tesseract OCR on the brief's drawing and returns numeric callouts grouped by kind (length/radius/diameter/thread/angle). SKILL tells the agent to call it FIRST on hard-tier briefs before estimating any dimension. Plus eval_set rebalanced (eval_v3): NIST PMI dropped from hard tier (too tortuous, designed for software PMI extraction not agent evaluation), Model Mania drawings lead. Per Shef ruling 2026-04-18.

## Metadata (JSON)

```json
{
  "variant_id": "v008-extract-then-build",
  "parent_variant_id": "v001-plan-from-render",
  "created_at": 1776579279,
  "mutation_description": "ARCHITECTURAL: new MCP tool extract_drawing_dimensions runs Tesseract OCR on the brief's drawing and returns numeric callouts grouped by kind (length/radius/diameter/thread/angle). SKILL tells the agent to call it FIRST on hard-tier briefs before estimating any dimension. Plus eval_set rebalanced (eval_v3): NIST PMI dropped from hard tier (too tortuous, designed for software PMI extraction not agent evaluation), Model Mania drawings lead. Per Shef ruling 2026-04-18.",
  "source_skill": "eval/variants/v001-plan-from-render/skills/onshape/SKILL.md"
}
```
