"""Apply a feature (create or update) and return a structured result including
the real Onshape `featureStatus`.

Fixes the #1 starter bug: every mutating tool currently returns "success" text
even when Onshape's response body says `featureState.featureStatus == "ERROR"`.
Routing every feature mutation through `apply_feature_and_check` gives callers
(and the LLM layer) a reliable signal of whether the feature actually built.

Evidence for the response shape used here is captured in
`scratchpad/smoke-test.md` and `scratchpad/probe-patch-and-shadedviews.md`
in the parent project (`/Users/shef/projects/onshape-mcp/`).

Also serializes the mutating POST per (document, workspace, element) — see
`_get_element_lock`. Onshape's feature-tree endpoint applies each write
against a base microversion and regenerates downstream features from there;
firing concurrent mutating calls at the same Part Studio (e.g. a batch of
parallel renames) lets them race on that base and corrupts the tree even
though each individual call is a no-op on geometry. Confirmed live: 20
parallel `rename_feature` calls against one Part Studio put 21 of 23
features into ERROR/WARNING and visibly collapsed the model (recovered via
Onshape's version history). Reads aren't locked, only the write.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any, Dict, List, Literal, Optional, Tuple

from loguru import logger
from pydantic import BaseModel, Field

from .client import OnshapeClient
from .sketch_inspect import assess_sketch_risk


FeatureStatus = Literal["OK", "INFO", "WARNING", "ERROR", "BLOCKED", "UNKNOWN"]

# One lock per (document_id, workspace_id, element_id), created lazily.
# defaultdict's __getitem__ is a single synchronous dict op with no `await`
# inside, so it's safe to call from multiple concurrent asyncio tasks without
# its own lock — no two tasks can interleave mid-lookup on one event loop.
_element_locks: "defaultdict[Tuple[str, str, str], asyncio.Lock]" = defaultdict(
    asyncio.Lock
)


def _get_element_lock(document_id: str, workspace_id: str, element_id: str) -> asyncio.Lock:
    """Return the lock guarding mutating writes to this Part Studio/Assembly."""
    return _element_locks[(document_id, workspace_id, element_id)]


class FeatureApplyResult(BaseModel):
    """Structured result of applying (create/update) a feature.

    `ok` is True iff `status == "OK"`. For WARNING, the feature built but
    Onshape has a concern worth surfacing; `error_message` will carry it.

    `changes` (when set) is a git-diff-style summary of what the feature
    altered in the part — volume delta, faces added/removed, bbox change,
    anomalies. Only populated when the caller passed `track_changes=True`.
    """

    ok: bool
    status: FeatureStatus
    feature_id: str
    feature_name: str
    feature_type: str
    error_message: Optional[str] = None
    changes: Optional[Dict[str, Any]] = None
    raw: Dict[str, Any] = Field(default_factory=dict)


async def apply_feature_and_check(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
    feature_payload: Dict[str, Any],
    *,
    operation: Literal["create", "update"] = "create",
    feature_id: Optional[str] = None,
    track_changes: bool = False,
) -> FeatureApplyResult:
    """Apply a feature to a Part Studio and return its Onshape-reported status.

    Args:
        client: Active OnshapeClient (reused, not closed here).
        document_id: Onshape document id.
        workspace_id: Onshape workspace id.
        element_id: Part Studio element id.
        feature_payload: Body to POST. Typically
            `{"feature": {...}, "serializationVersion": ..., "sourceMicroversion": ...}`.
            The starter's existing builders return just the inner feature dict; callers
            can wrap it as `{"feature": feature_dict}` before calling.
        operation: "create" (POST /features) or "update"
            (POST /features/featureid/{feature_id}).
        feature_id: Required when `operation="update"`.

    Returns:
        FeatureApplyResult with the real featureStatus, never "unknown" feature_id,
        and `error_message` populated whenever status is non-OK.

    Raises:
        ValueError: operation="update" without feature_id.
        httpx.HTTPStatusError: on HTTP 4xx/5xx (malformed request, auth, etc.).
            NOT raised for HTTP 200 responses carrying an ERROR featureStatus —
            those flow through as structured results.
    """

    if operation == "update" and not feature_id:
        raise ValueError("feature_id is required when operation='update'")
    if operation not in {"create", "update"}:
        raise ValueError(f"operation must be 'create' or 'update', got {operation!r}")

    base = (
        f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/features"
    )
    path = base if operation == "create" else f"{base}/featureid/{feature_id}"

    # Snapshot bodies before the feature if caller wants a git-diff-style
    # `changes` block. Failures to snapshot don't block the feature apply —
    # we just skip the diff and log.
    bodies_before = None
    mass_before: Optional[Dict[str, Any]] = None
    if track_changes:
        try:
            bd = await client.get(
                f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/bodydetails"
            )
            bodies_before = bd.get("bodies") or []
            mass_before = await client.get(
                f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/massproperties"
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"track_changes: before-snapshot failed ({e}); skipping diff")
            bodies_before = None

    async with _get_element_lock(document_id, workspace_id, element_id):
        response = await client.post(path, data=feature_payload)

    # Primary source: top-level featureState in the POST response.
    state = response.get("featureState") if isinstance(response, dict) else None
    feature = response.get("feature", {}) if isinstance(response, dict) else {}

    real_feature_id = feature.get("featureId") or feature_id or ""
    feature_name = feature.get("name", "")
    # feature_type: BTMFeature-134 uses "featureType" (e.g. "extrude"); BTMSketch-151
    # does not and is identified by btType.
    feature_type = feature.get("featureType") or feature.get("btType", "")

    if not state:
        # Fallback: re-fetch /features and pull from top-level featureStates map.
        logger.warning(
            "apply_feature_and_check: POST response missing featureState; "
            "falling back to /features featureStates map"
        )
        try:
            feats = await client.get(base)
            state = (feats.get("featureStates") or {}).get(real_feature_id)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Fallback /features GET failed: {e}")
            state = None

    raw_status: str = (state or {}).get("featureStatus", "UNKNOWN")
    status: FeatureStatus = (
        raw_status if raw_status in ("OK", "INFO", "WARNING", "ERROR") else "UNKNOWN"
    )
    # INFO means Onshape auto-adjusted something (e.g. extrude depth clamped to
    # through-all), but the feature built correctly and downstream geometry is
    # valid. Treat it as success; error_message still gets populated below so
    # Claude can learn from the note.
    ok = status in ("OK", "INFO")

    error_message: Optional[str] = None
    if status != "OK":
        fs_status = await _fetch_feature_status_enum(
            client, document_id, workspace_id, element_id, real_feature_id
        )
        error_message = _extract_error_message(state or {}, fs_status=fs_status)

    # After-snapshot + diff. Only if caller asked AND before-snapshot succeeded
    # AND the feature actually built (diffing after an ERROR would likely just
    # show the pre-feature state unchanged).
    changes: Optional[Dict[str, Any]] = None
    if track_changes and bodies_before is not None and ok:
        try:
            bd_after = await client.get(
                f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/bodydetails"
            )
            bodies_after = bd_after.get("bodies") or []
            mass_after = await client.get(
                f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/massproperties"
            )
            from .geometry_diff import compute_diff
            changes = compute_diff(
                bodies_before, bodies_after,
                mass_before=mass_before, mass_after=mass_after,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"track_changes: diff failed ({e}); skipping")
            changes = None

    return FeatureApplyResult(
        ok=ok,
        status=status,
        feature_id=real_feature_id,
        feature_name=feature_name,
        feature_type=feature_type,
        error_message=error_message,
        changes=changes,
        raw=response if isinstance(response, dict) else {},
    )


async def apply_assembly_feature_and_check(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
    feature_payload: Dict[str, Any],
    *,
    operation: Literal["create", "update"] = "create",
    feature_id: Optional[str] = None,
) -> FeatureApplyResult:
    """Apply a feature to an Assembly and return its Onshape-reported status.

    Mirror of `apply_feature_and_check` that targets the assemblies endpoint
    instead of partstudios. Mate connectors, mates (fastened / revolute /
    slider / cylindrical), and any other assembly feature ride through this
    helper so callers see `status=ERROR` when the solver rejects a mate,
    instead of the silent "Created fastened mate 'foo'. Feature ID: bar"
    prose the old path returned.

    Response shape on the assembly side is identical to the PS side
    (`{featureState, feature, ...}`) — verified via live probe — so the
    same parsing works.
    """
    if operation == "update" and not feature_id:
        raise ValueError("feature_id is required when operation='update'")
    if operation not in {"create", "update"}:
        raise ValueError(f"operation must be 'create' or 'update', got {operation!r}")

    base = (
        f"/api/v9/assemblies/d/{document_id}/w/{workspace_id}/e/{element_id}/features"
    )
    path = base if operation == "create" else f"{base}/featureid/{feature_id}"

    async with _get_element_lock(document_id, workspace_id, element_id):
        response = await client.post(path, data=feature_payload)

    state = response.get("featureState") if isinstance(response, dict) else None
    feature = response.get("feature", {}) if isinstance(response, dict) else {}

    real_feature_id = feature.get("featureId") or feature_id or ""
    feature_name = feature.get("name", "")
    feature_type = feature.get("featureType") or feature.get("btType", "")

    if not state:
        # Fallback: re-read /features and pick this feature's state out of the
        # map. Onshape has been reliable about including `featureState` inline
        # on assembly POSTs, but the belt-and-suspenders path matches the PS
        # helper and is cheap.
        logger.warning(
            "apply_assembly_feature_and_check: POST response missing featureState; "
            "falling back to /features featureStates map"
        )
        try:
            feats = await client.get(base)
            state = (feats.get("featureStates") or {}).get(real_feature_id)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Fallback /features GET failed: {e}")
            state = None

    raw_status: str = (state or {}).get("featureStatus", "UNKNOWN")
    status: FeatureStatus = (
        raw_status if raw_status in ("OK", "INFO", "WARNING", "ERROR") else "UNKNOWN"
    )
    ok = status in ("OK", "INFO")

    error_message: Optional[str] = None
    if status != "OK":
        # Assembly contexts don't expose getFeatureStatus via FS (there's no
        # Part Studio context for eval), so this returns None and we fall
        # through to the legacy blob dump -- keeps the surface consistent.
        fs_status = await _fetch_feature_status_enum(
            client, document_id, workspace_id, element_id, real_feature_id,
            is_assembly=True,
        )
        error_message = _extract_error_message(state or {}, fs_status=fs_status)

    return FeatureApplyResult(
        ok=ok,
        status=status,
        feature_id=real_feature_id,
        feature_name=feature_name,
        feature_type=feature_type,
        error_message=error_message,
        raw=response if isinstance(response, dict) else {},
    )


async def update_feature_params_and_check(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
    feature_id: str,
    updates: List[Dict[str, Any]],
    *,
    override_safety_check: bool = False,
) -> FeatureApplyResult:
    """Patch a specific feature's parameters and report the real Onshape status.

    Onshape does not have a granular parameter-patch endpoint; updates are done
    by re-POSTing the whole feature to
    `/api/v9/partstudios/.../features/featureid/{feature_id}`. This helper hides
    that round-trip: it GETs the current /features list, finds the feature by
    id, merges the caller's `updates` into the matching parameters by
    `parameterId`, and POSTs the modified feature through
    `apply_feature_and_check` so the same structured status comes out.

    Args:
        client: Active OnshapeClient.
        document_id, workspace_id, element_id: Usual triple.
        feature_id: Feature to patch.
        updates: List of parameter patches. Each entry MUST include
            `parameterId`. Any other keys are merged into the matching
            parameter dict, overwriting. For BTMParameterQuantity-147 set
            `expression` (e.g. `"15 mm"`, `"90 deg"`) and the helper clears the
            stale numeric `value` so Onshape re-evaluates. For booleans / enums
            (BTMParameterBoolean-144 / BTMParameterEnum-145) just set `value`.
        override_safety_check: If the target is a sketch with external
            geometry references (non-default plane, or a constraint bound
            to geometry outside the sketch's own entities), this call is
            blocked by default (see `assess_sketch_risk`) — that pattern is
            confirmed to corrupt the model when re-POSTed via this
            mechanism. Pass True to force it through anyway.

    Returns:
        FeatureApplyResult with the post-update featureStatus. ok=False if
        the feature errors after the patch (so Claude learns the tweak was
        wrong), or status="BLOCKED" if the safety check refused to send it.

    Raises:
        ValueError: feature_id not found, or an `updates` entry has no
            matching parameterId, or `updates` is empty — all of these are
            programmer/driver errors, not API failures.
    """
    if not feature_id:
        raise ValueError("feature_id is required")
    if not updates:
        raise ValueError("updates must be a non-empty list")

    base = (
        f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/features"
    )
    features_doc = await client.get(base)
    features: List[Dict[str, Any]] = features_doc.get("features", []) or []

    target: Optional[Dict[str, Any]] = None
    for feat in features:
        if feat.get("featureId") == feature_id:
            target = feat
            break
    if target is None:
        raise ValueError(
            f"feature_id {feature_id!r} not found in element. "
            f"Available ids: {[f.get('featureId') for f in features]}"
        )

    if not override_safety_check:
        risk = assess_sketch_risk(features_doc, feature_id)
        if risk and risk["risky"]:
            return FeatureApplyResult(
                ok=False,
                status="BLOCKED",
                feature_id=feature_id,
                feature_name=target.get("name") or "",
                feature_type=target.get("featureType") or target.get("btType") or "",
                error_message=(
                    f"BLOCKED by safety check (nothing was sent to Onshape): "
                    f"{risk['summary']} Onshape's REST feature-patch mechanism "
                    f"(GET the full feature, patch one field, POST it back "
                    f"unchanged otherwise) is confirmed to corrupt sketches "
                    f"like this one. Call inspect_sketch on featureId "
                    f"{feature_id!r} to review the exact plane/constraint "
                    f"references, then retry with override_safety_check=True "
                    f"if you still want to proceed."
                ),
            )

    params = target.get("parameters") or []
    param_by_id: Dict[str, Dict[str, Any]] = {
        p.get("parameterId"): p for p in params if isinstance(p, dict)
    }

    missing: List[str] = []
    for upd in updates:
        if not isinstance(upd, dict) or "parameterId" not in upd:
            raise ValueError(
                f"each update must be a dict with a 'parameterId' key, got {upd!r}"
            )
        pid = upd["parameterId"]
        target_param = param_by_id.get(pid)
        if target_param is None:
            missing.append(pid)
            continue
        # Merge all other fields into the parameter dict.
        for k, v in upd.items():
            if k == "parameterId":
                continue
            target_param[k] = v
        # For Quantity params: if caller set expression but didn't set value,
        # clear the numeric value so Onshape re-evaluates the expression
        # instead of preferring the stale numeric.
        if (
            target_param.get("btType") == "BTMParameterQuantity-147"
            and "expression" in upd
            and "value" not in upd
        ):
            target_param["value"] = 0.0

    if missing:
        existing = sorted(param_by_id.keys())
        raise ValueError(
            f"parameterId(s) not found on feature: {missing!r}. "
            f"Feature has parameters: {existing}"
        )

    return await apply_feature_and_check(
        client,
        document_id,
        workspace_id,
        element_id,
        {"feature": target},
        operation="update",
        feature_id=feature_id,
    )


async def rename_feature_and_check(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
    feature_id: str,
    new_name: str,
    *,
    override_safety_check: bool = False,
) -> FeatureApplyResult:
    """Rename a Part Studio feature (the label in the feature tree, e.g.
    'Extrude 1' -> 'Boss extrude').

    Same re-POST-the-whole-feature mechanism as
    `update_feature_params_and_check`, except it patches the feature's
    top-level `name` field instead of an entry in `parameters`.

    Args:
        client: Active OnshapeClient.
        document_id, workspace_id, element_id: Usual triple.
        feature_id: Feature to rename.
        new_name: New display name.
        override_safety_check: If the target is a sketch with external
            geometry references, this call is blocked by default (see
            `assess_sketch_risk`) — confirmed to corrupt the model when
            re-POSTed via this mechanism. Pass True to force it through.

    Returns:
        FeatureApplyResult with the post-rename featureStatus (renaming
        doesn't change geometry, so this should always be OK/INFO unless the
        feature was already broken), or status="BLOCKED" if the safety
        check refused to send it.

    Raises:
        ValueError: feature_id not found in the element.
    """
    if not feature_id:
        raise ValueError("feature_id is required")

    base = (
        f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/features"
    )
    features_doc = await client.get(base)
    features: List[Dict[str, Any]] = features_doc.get("features", []) or []

    target: Optional[Dict[str, Any]] = None
    for feat in features:
        if feat.get("featureId") == feature_id:
            target = feat
            break
    if target is None:
        raise ValueError(
            f"feature_id {feature_id!r} not found in element. "
            f"Available ids: {[f.get('featureId') for f in features]}"
        )

    if not override_safety_check:
        risk = assess_sketch_risk(features_doc, feature_id)
        if risk and risk["risky"]:
            return FeatureApplyResult(
                ok=False,
                status="BLOCKED",
                feature_id=feature_id,
                feature_name=target.get("name") or "",
                feature_type=target.get("featureType") or target.get("btType") or "",
                error_message=(
                    f"BLOCKED by safety check (nothing was sent to Onshape): "
                    f"{risk['summary']} Onshape's REST feature-patch mechanism "
                    f"(GET the full feature, patch one field, POST it back "
                    f"unchanged otherwise) is confirmed to corrupt sketches "
                    f"like this one. Call inspect_sketch on featureId "
                    f"{feature_id!r} to review the exact plane/constraint "
                    f"references, then retry with override_safety_check=True "
                    f"if you still want to proceed."
                ),
            )

    target["name"] = new_name

    return await apply_feature_and_check(
        client,
        document_id,
        workspace_id,
        element_id,
        {"feature": target},
        operation="update",
        feature_id=feature_id,
    )


async def batch_rename_features_and_check(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
    renames: List[Dict[str, str]],
    *,
    override_safety_check: bool = False,
) -> List[Dict[str, Any]]:
    """Rename multiple Part Studio features in one call.

    Executes sequentially (`for` + `await`, not `asyncio.gather`) — one
    caller-visible tool call driving one sequential loop structurally cannot
    reproduce the parallel-write race that firing N separate rename_feature
    calls at once can (see the per-element lock in `apply_feature_and_check`
    for the general-purpose fix; this is belt-and-suspenders by construction
    for the specific "batch rename" use case).

    Each item is attempted independently via `rename_feature_and_check`
    (so it gets the same safety-check gate): a risky sketch (status=BLOCKED)
    or an Onshape-side error on one item does not abort the rest of the
    batch. Each item does its own fresh GET+POST (not a shared
    pre-fetched features_doc), so an N-item batch costs N GETs + N POSTs —
    accepted cost; the upside is each rename sees the freshest
    post-previous-mutation state within the same batch.

    Args:
        client: Active OnshapeClient.
        document_id, workspace_id, element_id: Usual triple.
        renames: Ordered list of {"featureId": ..., "newName": ...} dicts.
        override_safety_check: Applies to every item in the batch.

    Returns:
        List of per-item result dicts: {featureId, requestedName, ok,
        status, feature_name, error_message}, one per input item, in order.
    """
    results: List[Dict[str, Any]] = []
    for item in renames:
        feature_id = item.get("featureId") if isinstance(item, dict) else None
        new_name = item.get("newName") if isinstance(item, dict) else None
        if not feature_id or not new_name:
            results.append({
                "featureId": feature_id,
                "requestedName": new_name,
                "ok": False,
                "status": "ERROR",
                "feature_name": "",
                "error_message": (
                    f"each renames[] item must have non-empty featureId and "
                    f"newName, got {item!r}"
                ),
            })
            continue
        try:
            result = await rename_feature_and_check(
                client,
                document_id,
                workspace_id,
                element_id,
                feature_id,
                new_name,
                override_safety_check=override_safety_check,
            )
            results.append({
                "featureId": feature_id,
                "requestedName": new_name,
                "ok": result.ok,
                "status": result.status,
                "feature_name": result.feature_name,
                "error_message": result.error_message,
            })
        except Exception as e:  # noqa: BLE001
            results.append({
                "featureId": feature_id,
                "requestedName": new_name,
                "ok": False,
                "status": "ERROR",
                "feature_name": "",
                "error_message": str(e),
            })
    return results


def _extract_error_message(
    state: Dict[str, Any],
    fs_status: Optional[Dict[str, Any]] = None,
) -> str:
    """Pull a useful error string out of a BTFeatureState blob.

    Onshape's `featureState` wire field only carries `{btType, featureStatus,
    inactive}` on most sketch/extrude warnings -- no `message`, no `feedback`.
    The diagnostic (`SKETCH_DIMENSION_MISSING_PARAMETER`, etc.) lives inside
    the FS runtime and is only reachable by calling `getFeatureStatus(context,
    id)` via `/featurescript`. `fs_status` is the unwrapped result of that
    call, carrying `{statusEnum?, statusType}`. We prefer it over the blob
    because the enum is a machine-readable, greppable handle callers can act
    on.

    Fall-through order:
      1. `fs_status.statusEnum` + `statusType` (new, always actionable)
      2. `state.message` (rarely populated in practice)
      3. `state.feedback[].{severity, message}` (rarely populated)
      4. Raw JSON dump of `state` (last resort so callers see something)
    """

    parts: List[str] = []

    if isinstance(fs_status, dict):
        enum_val = fs_status.get("statusEnum")
        type_val = fs_status.get("statusType")
        if enum_val:
            # Machine-readable. Keep it prominent but include a human hint.
            parts.append(
                f"{enum_val} ({type_val})" if type_val else str(enum_val)
            )

    message = state.get("message")
    feedback = state.get("feedback")

    if isinstance(message, str) and message.strip():
        parts.append(message.strip())

    if isinstance(feedback, list):
        for item in feedback:
            if not isinstance(item, dict):
                continue
            sev = item.get("severity") or item.get("level") or ""
            msg = item.get("message") or item.get("text") or ""
            if msg:
                parts.append(f"[{sev}] {msg}" if sev else str(msg))

    if parts:
        return " | ".join(parts)

    # Nothing structured -- dump raw state so callers aren't blind.
    return json.dumps(state, default=str)


async def _fetch_feature_status_enum(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    element_id: str,
    feature_id: str,
    *,
    is_assembly: bool = False,
) -> Optional[Dict[str, Any]]:
    """Call FS `getFeatureStatus(context, id)` for a specific feature and
    return the unwrapped `{statusEnum, statusType}` map (or None on failure).

    Only runs on non-OK statuses; the happy path never pays for this. On any
    error (bad response shape, network blip, assembly context that can't run
    FS) returns None so the caller falls back to the blob dump -- enrichment
    is best-effort, it must never fail the write.
    """
    if not feature_id:
        return None
    kind = "assemblies" if is_assembly else "partstudios"
    path = f"/api/v8/{kind}/d/{document_id}/w/{workspace_id}/e/{element_id}/featurescript"
    # Escape double quotes / backslashes in the id for safety, though real
    # Onshape featureIds never contain those.
    safe_id = feature_id.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        "function(context is Context, queries) {\n"
        f'    return getFeatureStatus(context, ["{safe_id}"] as Id);\n'
        "}"
    )
    try:
        resp = await client.post(path, data={"script": script})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"getFeatureStatus FS call failed: {e}")
        return None

    return _unwrap_fsvalue(resp.get("result"))


def _unwrap_fsvalue(v: Any) -> Any:
    """Convert a BTFSValue* tree back to plain Python.

    FS returns all values wrapped in `{btType: "...BTFSValue<kind>", value: ...}`.
    Maps nest further as lists of `{key, value}` entries. Arrays are lists of
    wrapped values. Scalars (string/bool/number/undefined) carry the value
    directly on the wrapper. This is a narrow-scope helper for the enrichment
    path; the full rendering module has its own unwrapper.
    """
    if not isinstance(v, dict):
        return v
    btt = v.get("btType", "")
    if "ValueMap" in btt:
        out: Dict[Any, Any] = {}
        for ent in v.get("value") or []:
            if not isinstance(ent, dict):
                continue
            k = _unwrap_fsvalue(ent.get("key"))
            out[k] = _unwrap_fsvalue(ent.get("value"))
        return out
    if "ValueArray" in btt:
        return [_unwrap_fsvalue(x) for x in (v.get("value") or [])]
    if "ValueUndefined" in btt:
        return None
    # Scalars (string, boolean, number, value-with-units) expose the payload
    # directly under `value`.
    return v.get("value")
