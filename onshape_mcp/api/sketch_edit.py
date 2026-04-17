"""Fetch / merge / post plumbing for `edit_sketch`.

Iteration on a sketch — addEntities, addConstraints, removeIds — without
having to rebuild and re-POST the whole feature from scratch. The flow:

    1. GET /features and find the BTMSketch-151 by featureId.
    2. Read its `feature.entities` and `feature.constraints` lists.
    3. Validate addEntity/addConstraint ids don't collide with existing ids.
    4. Cascade-remove: any constraint that references an entity in
       `removeIds` (directly or via `entityId.subpoint` form like
       `line1.start`) gets dropped too — surfaced in `cascaded_removals`
       so callers see exactly what got pulled.
    5. Splice the lists (remove + append) and POST the whole feature
       back via apply_feature_and_check(operation="update").

What this module does NOT do: serialize user-facing entity/constraint
dicts into BTM* wire shape. That's the constraint-first surface lead
(cz3cmn1y) is building separately. This scaffolding passes
addEntities/addConstraints THROUGH unchanged so when the serializer
lands on the same branch it just wires into `wire_entity_id` /
`wire_constraint_refs` below and everything else flows.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger
from pydantic import BaseModel, Field

from .client import OnshapeClient
from .feature_apply import FeatureApplyResult, apply_feature_and_check


class CascadedRemoval(BaseModel):
    """One constraint that got auto-dropped because an entity it referenced
    was in the user's removeIds. Surfaced in EditSketchResult so Claude
    sees the silent cleanup -- otherwise a 48->12 constraint scrub is the
    kind of thing that bites three turns later when the next addConstraint
    references a constraint id that no longer exists."""

    constraint_id: str
    referenced: str  # the removed entity id that triggered the cascade


class EditSketchResult(BaseModel):
    """edit_sketch return shape: the underlying apply result plus the
    diff bookkeeping (what got added, removed, cascaded) so the caller
    can verify the sketch tree matches their mental model.
    """

    apply: FeatureApplyResult
    added_entity_ids: List[str] = Field(default_factory=list)
    added_constraint_ids: List[str] = Field(default_factory=list)
    removed_entity_ids: List[str] = Field(default_factory=list)
    removed_constraint_ids: List[str] = Field(default_factory=list)
    cascaded_removals: List[CascadedRemoval] = Field(default_factory=list)


# ---- shape helpers ---------------------------------------------------------
#
# These are the two seams the serializer (cz3cmn1y's slice) plugs into.
# Today they read the conventions used by the existing SketchBuilder
# (BTMSketchCurveSegment-155 etc carry `entityId`; BTMSketchConstraint-2
# carries `entityId` too, references live nested under `parameters[]`).
# When the serializer formalizes those shapes, swap these helpers for
# the authoritative lookups -- nothing else in this module changes.


def wire_entity_id(wire_entry: Dict[str, Any]) -> Optional[str]:
    """The user-id of an entity already on the wire. SketchBuilder convention
    is `entityId` on BTM* dicts; check both that and a bare `id` so the
    constraint-first surface (which uses `id`) round-trips cleanly once the
    serializer writes it."""
    if not isinstance(wire_entry, dict):
        return None
    return wire_entry.get("entityId") or wire_entry.get("id")


def wire_constraint_refs(wire_constraint: Dict[str, Any]) -> Set[str]:
    """The set of entity ids a wire-shape constraint references.

    Best-effort scan today: walks the constraint dict looking for a
    `value: <str>` deep inside `parameters[].value` (BTMParameterString-149
    holds entity refs in that slot in the existing builder). Once the
    serializer formalizes its constraint payload, replace this with an
    authoritative lookup -- the rest of the merge logic is shape-agnostic.

    Also recognizes the user-facing shape (`entities: [...]` or `entity:
    "..."` directly on the dict) so addConstraints that haven't been
    serialized yet still cascade correctly when their ref disappears.
    """
    if not isinstance(wire_constraint, dict):
        return set()

    refs: Set[str] = set()

    # User-facing shape (cz3cmn1y's surface): {type, entities: [...]} or
    # {type, entity: "..."}.
    ent = wire_constraint.get("entity")
    if isinstance(ent, str):
        refs.add(ent)
    ents = wire_constraint.get("entities")
    if isinstance(ents, list):
        for e in ents:
            if isinstance(e, str):
                refs.add(e)

    # BTMSketchConstraint-2 wire shape: parameters carry references as
    # BTMParameterString-149 entries with `parameterId` like "localFirst",
    # "localSecond", "entityId". Walk and collect string `value`s under
    # those parameters.
    for p in wire_constraint.get("parameters") or []:
        if not isinstance(p, dict):
            continue
        # Parameter-string entity ref.
        v = p.get("value")
        if isinstance(v, str) and v:
            refs.add(v)
    return refs


def _strip_subpoint(ref: str) -> str:
    """`"line1.start"` -> `"line1"`. Sub-point references count as
    referencing the parent entity for cascade purposes."""
    return ref.split(".", 1)[0] if "." in ref else ref


def _merge(
    existing_entities: List[Dict[str, Any]],
    existing_constraints: List[Dict[str, Any]],
    add_entities: List[Dict[str, Any]],
    add_constraints: List[Dict[str, Any]],
    remove_ids: List[str],
) -> Tuple[
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[str],
    List[CascadedRemoval],
]:
    """Pure merge logic. Splits out for unit testing without an OnshapeClient.

    Returns (merged_entities, merged_constraints, removed_constraint_ids_direct,
    cascaded_removals).

    Raises ValueError on any id collision (add* uses an id that already
    lives on the wire).
    """
    # Index existing ids.
    existing_entity_ids = {
        wire_entity_id(e) for e in existing_entities if wire_entity_id(e)
    }
    existing_constraint_ids = {
        wire_entity_id(c) for c in existing_constraints if wire_entity_id(c)
    }

    # Validate addEntities don't collide.
    add_entity_ids: List[str] = []
    for i, e in enumerate(add_entities):
        eid = e.get("id") if isinstance(e, dict) else None
        if not isinstance(eid, str) or not eid:
            raise ValueError(
                f"addEntities[{i}] must carry a non-empty `id` string; got {e!r}"
            )
        if eid in existing_entity_ids or eid in add_entity_ids:
            raise ValueError(
                f"addEntities[{i}].id={eid!r} collides with an existing or "
                f"earlier-added entity. removeIds it first if you want to "
                f"retarget that id."
            )
        add_entity_ids.append(eid)

    add_constraint_ids: List[str] = []
    for i, c in enumerate(add_constraints):
        cid = c.get("id") if isinstance(c, dict) else None
        if not isinstance(cid, str) or not cid:
            raise ValueError(
                f"addConstraints[{i}] must carry a non-empty `id` string; got {c!r}"
            )
        if cid in existing_constraint_ids or cid in add_constraint_ids:
            raise ValueError(
                f"addConstraints[{i}].id={cid!r} collides with an existing or "
                f"earlier-added constraint."
            )
        add_constraint_ids.append(cid)

    # removeIds: take effect against entity ids AND constraint ids
    # (callers want a single bag for "drop these"). Anything that doesn't
    # match either is reported back to the caller as a diff inconsistency.
    remove_set = set(remove_ids)
    removed_entity_ids = remove_set & existing_entity_ids
    removed_constraint_ids_direct = remove_set & existing_constraint_ids

    # Cascade: any existing constraint that references one of the removed
    # entity ids also gets dropped. Sub-point refs ("line1.start") count
    # as referencing "line1".
    cascaded: List[CascadedRemoval] = []
    cascaded_constraint_ids: Set[str] = set()
    for c in existing_constraints:
        cid = wire_entity_id(c)
        if not cid or cid in removed_constraint_ids_direct:
            continue
        for ref in wire_constraint_refs(c):
            base = _strip_subpoint(ref)
            if base in removed_entity_ids:
                cascaded.append(CascadedRemoval(constraint_id=cid, referenced=base))
                cascaded_constraint_ids.add(cid)
                break

    # Splice.
    drop_entity = removed_entity_ids
    drop_constraint = removed_constraint_ids_direct | cascaded_constraint_ids

    merged_entities: List[Dict[str, Any]] = [
        e for e in existing_entities if wire_entity_id(e) not in drop_entity
    ] + list(add_entities)
    merged_constraints: List[Dict[str, Any]] = [
        c for c in existing_constraints if wire_entity_id(c) not in drop_constraint
    ] + list(add_constraints)

    # Surface unmatched removeIds as a warning the caller can act on.
    unmatched = remove_set - existing_entity_ids - existing_constraint_ids
    if unmatched:
        logger.warning(
            f"edit_sketch: removeIds did not match anything on the sketch: "
            f"{sorted(unmatched)!r}. Maybe a typo or already-removed id?"
        )

    return (
        merged_entities,
        merged_constraints,
        sorted(removed_constraint_ids_direct),
        cascaded,
    )


async def edit_sketch(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
    sketch_feature_id: str,
    *,
    add_entities: Optional[List[Dict[str, Any]]] = None,
    add_constraints: Optional[List[Dict[str, Any]]] = None,
    remove_ids: Optional[List[str]] = None,
) -> EditSketchResult:
    """Fetch + merge + post a sketch edit.

    Args:
        client: live OnshapeClient.
        document_id, workspace_id, element_id: target Part Studio.
        sketch_feature_id: the BTMSketch-151 feature to edit.
        add_entities: list of entity dicts to append (each must carry `id`).
        add_constraints: list of constraint dicts to append (each must
            carry `id`).
        remove_ids: list of user ids to drop. Matches against entity ids
            AND constraint ids; any constraint referencing a removed
            entity (directly or via `id.subpoint`) cascades out and is
            reported in `cascaded_removals`.

    Returns:
        EditSketchResult with the underlying apply outcome plus a
        per-id diff log.

    Raises:
        ValueError: id collision on addEntities / addConstraints, or no
            features list found, or the target featureId isn't a
            BTMSketch-151 feature in this Part Studio.
        httpx.HTTPStatusError: on 4xx/5xx from /features fetch or update.
    """
    add_entities = add_entities or []
    add_constraints = add_constraints or []
    remove_ids = remove_ids or []
    if not (add_entities or add_constraints or remove_ids):
        raise ValueError(
            "edit_sketch called with no diff: pass at least one of "
            "addEntities, addConstraints, removeIds."
        )

    base = (
        f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}"
        f"/e/{element_id}/features"
    )
    features_doc = await client.get(base)
    features: List[Dict[str, Any]] = features_doc.get("features") or []

    target: Optional[Dict[str, Any]] = None
    for feat in features:
        if isinstance(feat, dict) and feat.get("featureId") == sketch_feature_id:
            target = feat
            break
    if target is None:
        raise ValueError(
            f"sketch_feature_id={sketch_feature_id!r} not found in element. "
            f"Available featureIds: "
            f"{[f.get('featureId') for f in features if isinstance(f, dict)]}"
        )
    if target.get("btType") != "BTMSketch-151":
        raise ValueError(
            f"feature {sketch_feature_id!r} is btType={target.get('btType')!r}, "
            f"not BTMSketch-151 -- edit_sketch only edits sketch features."
        )

    existing_entities = list(target.get("entities") or [])
    existing_constraints = list(target.get("constraints") or [])

    (
        merged_entities,
        merged_constraints,
        direct_removed_constraint_ids,
        cascaded,
    ) = _merge(
        existing_entities,
        existing_constraints,
        add_entities,
        add_constraints,
        remove_ids,
    )

    # Mutate a copy of the target feature with the spliced lists, then
    # round-trip via apply_feature_and_check(update).
    merged_target = dict(target)
    merged_target["entities"] = merged_entities
    merged_target["constraints"] = merged_constraints

    apply_result = await apply_feature_and_check(
        client,
        document_id,
        workspace_id,
        element_id,
        {"feature": merged_target},
        operation="update",
        feature_id=sketch_feature_id,
    )

    # Recompute removed_entity_ids from the diff for the bookkeeping
    # field so the caller sees exactly what disappeared (mirrors what
    # _merge already used internally).
    existing_entity_id_set = {
        wire_entity_id(e) for e in existing_entities if wire_entity_id(e)
    }
    removed_entity_ids = sorted(set(remove_ids) & existing_entity_id_set)

    return EditSketchResult(
        apply=apply_result,
        added_entity_ids=[
            e["id"] for e in add_entities if isinstance(e, dict) and "id" in e
        ],
        added_constraint_ids=[
            c["id"] for c in add_constraints if isinstance(c, dict) and "id" in c
        ],
        removed_entity_ids=removed_entity_ids,
        removed_constraint_ids=direct_removed_constraint_ids,
        cascaded_removals=cascaded,
    )
