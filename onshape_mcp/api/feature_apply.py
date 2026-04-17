"""Apply a feature (create or update) and return a structured result including
the real Onshape `featureStatus`.

Fixes the #1 starter bug: every mutating tool currently returns "success" text
even when Onshape's response body says `featureState.featureStatus == "ERROR"`.
Routing every feature mutation through `apply_feature_and_check` gives callers
(and the LLM layer) a reliable signal of whether the feature actually built.

Evidence for the response shape used here is captured in
`scratchpad/smoke-test.md` and `scratchpad/probe-patch-and-shadedviews.md`
in the parent project (`/Users/shef/projects/onshape-mcp/`).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

from loguru import logger
from pydantic import BaseModel, Field

from .client import OnshapeClient


FeatureStatus = Literal["OK", "INFO", "WARNING", "ERROR", "UNKNOWN"]


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

    Returns:
        FeatureApplyResult with the post-update featureStatus. ok=False if the
        feature errors after the patch (so Claude learns the tweak was wrong).

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
