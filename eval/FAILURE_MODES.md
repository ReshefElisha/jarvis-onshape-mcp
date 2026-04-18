# Failure modes — what trips the baseline agent

Observations from Phase 3 baseline runs. Update as new modes surface.
Each mode should name: the behavior, the layer(s) it drops, and a candidate
SKILL.md-level mitigation that a variant could encode.

## F-01 · Under-built feature count on envelope briefs

**Where:** medium tier, envelope-only briefs (NIST CTC/FTC, Model Mania).
**Symptom:** bbox matches (L2 passes), volume is off by 1.5–2× (L1 fails),
L4 IoU → 0, L5 Chamfer → inf.
**Root cause:** agent picks a rectangular envelope + 2–4 simple features
when the reference render shows 8+ distinct features. Single-image-to-3D is
hard and the baseline SKILL doesn't explicitly force image analysis.
**Mitigation candidate:** SKILL § "Plan from the reference FIRST" —
enumerate features + proportions before calling `create_document`.
**Variant:** v001-plan-from-render.

## F-02 · Bash-escape when blocked on Write

**Where:** every brief, last 2–3 turns.
**Symptom:** agent calls `ToolSearch({"query": "select:Bash"})` hoping to
`cp /tmp/...step <target>` instead of using Write. Bash is disallowed; the
ToolSearch returns empty. Agent falls back to Write after an extended
thinking pause.
**Root cause:** Bash feels natural to the agent for file copies; the SKILL
doesn't say "use the Write tool for the final STEP persistence."
**Mitigation candidate:** SKILL § "Exporting your final STEP" — explicitly
list the two-step Read+Write sequence that works when Bash isn't available.
Cost: a wasted turn + 1–2 min of thinking on every brief. Worth it.
**Variant:** not yet tried.

## F-03 · Topology proliferation vs. reference

**Where:** seed_08_l_bracket and envelope briefs generally.
**Symptom:** L3 topology_signature drops because agent uses a simpler
feature graph (union of two boxes → 8 faces) where the reference has split
internal faces (→ 14 faces). Same volume, same bbox, different B-rep.
**Root cause:** agent takes the shortest path in feature-count terms, not
the topologically-faithful one. This is real geometric difference, but
cosmetic to most humans.
**Mitigation candidate:** uncertain. Could tighten SKILL to encourage
"decompose into individually-extruded features when unsure" — but may
hurt on simple briefs.

## F-04 · Extended-thinking stalls

**Where:** after a tool fails or a reference-image observation contradicts
the agent's model. Most commonly after `describe_part_studio` when the
result doesn't match prediction.
**Symptom:** agent emits one empty thinking block, then nothing for 1–2
minutes. Eventually resumes with a plan or a Bash-escape.
**Root cause:** thinking budget is large (8192 tokens) and the agent uses
it when uncertain. Not a failure per se, but inflates elapsed_s.
**Mitigation candidate:** none in the SKILL. If it becomes the bottleneck,
consider lowering thinking budget in the harness.
