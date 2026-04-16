"""Real-API test for the FS paradigm tool.

First live exercise of `CustomFeatureManager.apply_featurescript_feature`
since cz3cmn1y's [fs-paradigm] unblock (commit aefc322) landed the three
research fixes:
    - FS prelude bumped from stale 2242 -> current 2909
    - Namespace format `e{fs_eid}::m{microversion}` (no `::` between
      prefix and id)
    - /featurespecs compile-check + microversion fetch from the spec entry

This test wraps a single Onshape standard-library primitive -- `opPlane`
-- in a custom FS feature and instantiates it. opPlane is about the
smallest call that creates a visible feature, so any error here is in
the orchestration plumbing rather than the FS code itself.

Skipped automatically when ONSHAPE_ACCESS_KEY is missing so the default
suite stays clean.

Evidence:
    scratchpad/fs-custom-feature-research-2.md
    scratchpad/custom-feature-research.md (round 1, including dead ends)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.custom_features import CustomFeatureManager, DEFAULT_FS_VERSION
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.feature_apply import FeatureApplyResult
from onshape_mcp.api.partstudio import PartStudioManager


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (os.getenv("ONSHAPE_ACCESS_KEY") and os.getenv("ONSHAPE_SECRET_KEY")),
        reason="Requires ONSHAPE_ACCESS_KEY/ONSHAPE_SECRET_KEY in env",
    ),
]


# Minimal custom feature: an offset construction plane. Pure standard-library
# call (`opPlane` from onshape/std/geometry.fs), single quantity parameter,
# zero geometry to compute. If the orchestration is right, this lands. If it
# doesn't, the failure mode points at plumbing, not FS.
FS_OFFSET_PLANE = f"""\
FeatureScript {DEFAULT_FS_VERSION};
import(path : "onshape/std/geometry.fs", version : "{DEFAULT_FS_VERSION}.0");

annotation {{ "Feature Type Name" : "Claude Offset Plane" }}
export const claudeOffsetPlane = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {{
        annotation {{ "Name" : "Offset" }}
        isLength(definition.offset, LENGTH_BOUNDS);
    }}
    {{
        opPlane(context, id + "plane1", {{
            "plane" : plane(vector(0, 0, 1) * definition.offset, vector(0, 0, 1))
        }});
    }});
"""


@pytest.fixture
async def client():
    creds = OnshapeCredentials(
        access_key=os.environ["ONSHAPE_ACCESS_KEY"],
        secret_key=os.environ["ONSHAPE_SECRET_KEY"],
    )
    async with OnshapeClient(creds) as c:
        yield c


@pytest.mark.asyncio
async def test_offset_plane_custom_feature_lands(client):
    """End-to-end: write a tiny custom FS feature, instantiate it, confirm
    Onshape regen returns OK.

    Asserts:
        - apply_result.status == "OK"
        - apply_result.feature_type matches the FS export name
        - a real (non-"unknown") feature_id comes back
        - the orchestrator returns the FS element id + microversion so the
          caller can introspect or delete the FS later
    """
    docs = DocumentManager(client)
    ps_mgr = PartStudioManager(client)
    custom = CustomFeatureManager(client)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    doc = await docs.create_document(name=f"dyna-mcp fs-paradigm test {ts}")
    did = doc.id
    try:
        wid = (await docs.get_workspaces(did))[0].id
        ps = await ps_mgr.create_part_studio(did, wid, name="fs paradigm ps")
        ps_eid = ps["id"] if isinstance(ps, dict) else ps.id

        out = await custom.apply_featurescript_feature(
            did,
            wid,
            ps_eid,
            feature_type="claudeOffsetPlane",
            feature_script=FS_OFFSET_PLANE,
            feature_name="claude offset plane",
            parameters=[{"id": "offset", "type": "quantity", "value": "10 mm"}],
        )

        result: FeatureApplyResult = out["apply_result"]
        assert result.status == "OK", (
            f"FS feature regen status={result.status!r} "
            f"error={result.error_message!r} "
            f"fs_element_id={out.get('fs_element_id')!r} "
            f"source_microversion_id={out.get('source_microversion_id')!r}"
        )
        assert result.ok is True
        assert result.feature_type == "claudeOffsetPlane", (
            f"feature_type should match the FS export name; got {result.feature_type!r}"
        )
        assert result.feature_id and result.feature_id != "unknown", (
            f"feature_id should be the real id from the response, got {result.feature_id!r}"
        )

        # Orchestrator returns enough metadata for follow-up calls (param
        # tweaks, deletion, debugging the uploaded FS).
        assert out.get("fs_element_id"), "missing fs_element_id in result"
        assert out.get("source_microversion_id"), "missing source_microversion_id"
        # NB: libraryVersion comes back 0 even on a clean compile (observed
        # 2026-04-16 against FS 2909) -- it is NOT a reliable "compiled"
        # signal. featurespecs being non-empty is the real check; that's
        # already guarded inside apply_featurescript_feature. We just verify
        # the field is surfaced and is an int.
        assert "fs_library_version" in out, "missing fs_library_version key"
        assert isinstance(out["fs_library_version"], int)

    finally:
        try:
            await client.delete(f"/api/v6/documents/{did}")
        except Exception:  # noqa: BLE001
            pass
