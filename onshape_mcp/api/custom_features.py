"""Paradigm-level tool surface: author a FeatureScript custom feature and
instantiate it in a Part Studio in one call.

STATUS 2026-04-16: **not yet working end-to-end.** The 3-step orchestration
runs without HTTP errors through step 2 (FS element create + upload), but
step 3 (BTMFeature-134 instantiation) fails on every `namespace` string I
have tried with `Feature <fid> has an invalid namespace`. Root cause traced
to `/featurespecs` returning `featureSpecs: []` — the uploaded FS is stored
but the `export const = defineFeature(...)` symbol is never registered. See
`scratchpad/custom-feature-research.md` for the full probe log. Awaiting
peer input on the correct FS-version prelude / upload metadata / compile
trigger before the tool can be safely exposed.

The inline "paste a FS snippet and run it" path does not exist in Onshape's
public API. `/partstudios/.../featurescript` is read-only eval; mutating the
feature tree requires a BTMFeature-134 that references an exported function
defined in a Feature Studio element via `{featureType, namespace}`.

So `CustomFeatureManager.apply_featurescript_feature` orchestrates the
3-step dance behind a single call:

    1. Create (or reuse) a Feature Studio element in the same document.
    2. Upload the FS source as a BTFeatureStudioContents-2239 body.
    3. POST a BTMFeature-134 into the Part Studio with
       `namespace="{docId}::ws::{workspaceId}"` (same-doc workspace form).
       Routed through `apply_feature_and_check` so regen status is surfaced.

References for shapes:
    https://github.com/onshape-public/go-client/blob/main/onshape/docs/BTMFeature134.md
    https://github.com/onshape-public/go-client/blob/main/onshape/docs/BTFeatureDefinitionCall1406.md
    https://github.com/onshape-public/go-client/blob/main/onshape/api_feature_studio.go
    https://onshape-public.github.io/docs/api-adv/fs/
    https://forum.onshape.com/discussion/26720/

Research notes live in
`/Users/shef/projects/onshape-mcp/scratchpad/custom-feature-research.md`.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from loguru import logger

from .client import OnshapeClient
from .feature_apply import FeatureApplyResult, apply_feature_and_check


# Default FeatureScript language version. Recent enough that std/geometry.fs
# primitives like fCuboid / fCylinder / fSphere are all available. The same
# version string must appear in both the `FeatureScript <N>;` prelude line
# and each `import(..., version : "<N>.0")` statement the snippet uses.
DEFAULT_FS_VERSION = "2242"


_VALID_FEATURE_TYPE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class CustomFeatureManager:
    """Create + apply ad-hoc FeatureScript custom features in a Part Studio."""

    def __init__(self, client: OnshapeClient):
        self.client = client

    # ---- Feature Studio element lifecycle ---------------------------------

    async def create_feature_studio(
        self, document_id: str, workspace_id: str, name: str
    ) -> str:
        """Create a new Feature Studio element in a document/workspace.

        Returns the new element's id.
        """
        path = f"/api/v9/featurestudios/d/{document_id}/w/{workspace_id}"
        response = await self.client.post(path, data={"name": name})
        element_id = response.get("id")
        if not element_id:
            raise RuntimeError(
                f"Feature Studio creation returned no id: {response!r}"
            )
        return element_id

    async def upload_fs_source(
        self,
        document_id: str,
        workspace_id: str,
        fs_element_id: str,
        contents: str,
    ) -> Dict[str, Any]:
        """Write FS source into an existing Feature Studio element.

        On first write we omit `serializationVersion` and `sourceMicroversion`
        — Onshape fills them in. For subsequent rewrites a caller would need
        to pass the latest microversion to avoid a 409 skew.
        """
        path = f"/api/v9/featurestudios/d/{document_id}/w/{workspace_id}/e/{fs_element_id}"
        body = {
            "btType": "BTFeatureStudioContents-2239",
            "contents": contents,
        }
        return await self.client.post(path, data=body)

    # ---- Instantiation ---------------------------------------------------

    async def instantiate_custom_feature(
        self,
        document_id: str,
        workspace_id: str,
        part_studio_element_id: str,
        *,
        fs_document_id: str,
        fs_workspace_id: str,
        fs_element_id: str,
        feature_type: str,
        feature_name: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
    ) -> FeatureApplyResult:
        """POST a BTMFeature-134 that invokes `feature_type` from the given
        Feature Studio. Routed through `apply_feature_and_check` so regen
        status comes back cleanly.

        `parameters` is a list of `{id, type, value}` dicts — we convert each
        to the BTMParameterQuantity / BTMParameterString / BTMParameterBoolean
        shape that BTMFeature-134 expects.
        """
        if not _VALID_FEATURE_TYPE_RE.fullmatch(feature_type):
            raise ValueError(
                f"feature_type must be a valid FS identifier, got {feature_type!r}"
            )

        namespace = _same_doc_namespace(fs_document_id, fs_workspace_id, fs_element_id)
        onshape_params = [
            _to_onshape_parameter(p) for p in (parameters or [])
        ]

        payload = {
            "btType": "BTFeatureDefinitionCall-1406",
            "feature": {
                "btType": "BTMFeature-134",
                "featureType": feature_type,
                "name": feature_name,
                "namespace": namespace,
                "suppressed": False,
                "parameters": onshape_params,
            },
        }

        logger.debug(
            "instantiate_custom_feature featureType={} namespace={!r} "
            "param_count={}",
            feature_type,
            namespace,
            len(onshape_params),
        )

        return await apply_feature_and_check(
            self.client,
            document_id,
            workspace_id,
            part_studio_element_id,
            payload,
            operation="create",
        )

    # ---- One-call convenience -------------------------------------------

    async def apply_featurescript_feature(
        self,
        document_id: str,
        workspace_id: str,
        part_studio_element_id: str,
        *,
        feature_type: str,
        feature_script: str,
        feature_name: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        fs_element_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """End-to-end: create a fresh FS element, write the source, and
        instantiate the feature. Returns a dict carrying both the regen
        FeatureApplyResult and the FS element id (so callers can inspect
        the uploaded source if debugging).

        `feature_script` must be a complete FS source file — it should start
        with `FeatureScript <version>;` and export a `defineFeature(...)` with
        a top-level name equal to `feature_type`. The worked example in the
        tool description shows the minimum boilerplate.
        """
        fs_name = fs_element_name or f"ClaudeFS_{feature_type}"
        fs_eid = await self.create_feature_studio(
            document_id, workspace_id, fs_name
        )
        await self.upload_fs_source(document_id, workspace_id, fs_eid, feature_script)

        apply_result = await self.instantiate_custom_feature(
            document_id,
            workspace_id,
            part_studio_element_id,
            fs_document_id=document_id,
            fs_workspace_id=workspace_id,
            fs_element_id=fs_eid,
            feature_type=feature_type,
            feature_name=feature_name,
            parameters=parameters,
        )

        return {
            "apply_result": apply_result,
            "fs_element_id": fs_eid,
        }


# ---- helpers ---------------------------------------------------------------


def _same_doc_namespace(
    document_id: str, workspace_id: str, fs_element_id: str
) -> str:
    """Construct the `namespace` string for an in-same-document FS import.

    Onshape accepts `<document_id>::ws::<workspace_id>::e::<fs_element_id>`
    for within-workspace custom features (no version required). Cross-doc
    use requires `<document_id>::v::<version_id>::e::<fs_element_id>`, which
    is out of scope for this first cut — we can add a `create_version`
    companion when that becomes necessary.
    """
    return f"{document_id}::ws::{workspace_id}::e::{fs_element_id}"


def _to_onshape_parameter(param: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a caller-friendly parameter descriptor to BTMParameter* JSON.

    Input shape: `{"id": "<name>", "type": "quantity|string|boolean|real", "value": <val>}`

    - quantity: value is a string like "5 mm" or "0.5 in"; becomes BTMParameterQuantity-147
    - string:   BTMParameterString-149
    - boolean:  BTMParameterBoolean-144
    - real:     BTMParameterQuantity-147 without units

    Unknown types raise ValueError so bad inputs fail loudly.
    """
    pid = param.get("id")
    ptype = (param.get("type") or "").lower()
    value = param.get("value")
    if not pid:
        raise ValueError(f"parameter missing id: {param!r}")

    if ptype == "quantity":
        expression = value if isinstance(value, str) else f"{value}"
        return {
            "btType": "BTMParameterQuantity-147",
            "parameterId": pid,
            "expression": expression,
        }
    if ptype == "string":
        return {
            "btType": "BTMParameterString-149",
            "parameterId": pid,
            "value": "" if value is None else str(value),
        }
    if ptype == "boolean":
        return {
            "btType": "BTMParameterBoolean-144",
            "parameterId": pid,
            "value": bool(value),
        }
    if ptype == "real":
        return {
            "btType": "BTMParameterQuantity-147",
            "parameterId": pid,
            "isInteger": False,
            "value": float(value) if value is not None else 0.0,
            "expression": str(value) if value is not None else "0",
        }
    raise ValueError(
        f"unsupported parameter type {ptype!r} for id={pid!r}; "
        "use quantity | string | boolean | real"
    )
