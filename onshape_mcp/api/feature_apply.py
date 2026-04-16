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
    """

    ok: bool
    status: FeatureStatus
    feature_id: str
    feature_name: str
    feature_type: str
    error_message: Optional[str] = None
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
        error_message = _extract_error_message(state or {})

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


def _extract_error_message(state: Dict[str, Any]) -> str:
    """Pull a useful error string out of a BTFeatureState blob.

    Onshape may populate `message`, `feedback` (a list of `{severity, message, ...}`),
    both, or neither. If neither, serialize the whole state so the LLM-facing layer
    at least sees raw data.
    """

    message = state.get("message")
    feedback = state.get("feedback")

    parts: List[str] = []
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

    # Nothing structured — dump raw state so callers aren't blind.
    return json.dumps(state, default=str)
