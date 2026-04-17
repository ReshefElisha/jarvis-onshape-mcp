"""Real-API test for WARNING error_message enrichment.

Before #37: a sketch that came back with `featureStatus: WARNING` left the
caller with `error_message = '{"btType": "BTFeatureState-1688",
"featureStatus": "WARNING", "inactive": false}'` -- an empty blob, nothing
to act on.

Fix: when `featureStatus` is non-OK, `apply_feature_and_check` calls
`getFeatureStatus(context, id)` via `/featurescript` to pull the FS-level
diagnostic enum (`SKETCH_DIMENSION_MISSING_PARAMETER`, etc.) and prepends
it to `error_message`.

Fixture: a sketch that references a non-existent variable name via
`variableRadius`. This is the same failure mode that bit the earlier
parametric dogfood and took ~20 min to bisect through opaque WARNINGs.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.feature_apply import apply_feature_and_check
from onshape_mcp.api.partstudio import PartStudioManager
from onshape_mcp.builders.sketch import SketchBuilder, SketchPlane


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (
            (os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY"))
            and (os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET"))
        ),
        reason="Requires Onshape credentials in env",
    ),
]


def _creds() -> OnshapeCredentials:
    ak = os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY", "")
    sk = os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET", "")
    return OnshapeCredentials(access_key=ak, secret_key=sk)


@pytest.mark.asyncio
async def test_warning_error_message_carries_fs_status_enum():
    async with OnshapeClient(_creds()) as client:
        docs = DocumentManager(client)
        ps_mgr = PartStudioManager(client)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        doc = await docs.create_document(name=f"dyna-mcp warn enrich {ts}")
        did = doc.id
        try:
            wid = (await docs.get_workspaces(did))[0].id
            eid = (await ps_mgr.create_part_studio(did, wid, name="ps"))["id"]
            top_id = await ps_mgr.get_plane_id(did, wid, eid, "Top")

            # Fixture: a variable_radius referencing a variable that doesn't
            # exist in any VS. Onshape returns WARNING with statusEnum=
            # SKETCH_DIMENSION_MISSING_PARAMETER.
            sk = SketchBuilder(plane=SketchPlane.TOP, plane_id=top_id, name="Bad")
            sk.add_circle(center=(0, 0), radius=3, variable_radius="does_not_exist_xyz")
            r = await apply_feature_and_check(client, did, wid, eid, sk.build())

            assert r.status == "WARNING", f"expected WARNING, got {r.status}"
            assert r.error_message, "error_message must not be empty on WARNING"
            # The statusEnum is the actionable part. Must not be the old empty-
            # blob output (`{"btType": "BTFeatureState-1688", ...}`).
            assert r.error_message.startswith(
                "SKETCH_DIMENSION_MISSING_PARAMETER"
            ), (
                f"error_message should lead with the FS status enum, got "
                f"{r.error_message!r}"
            )
            # statusType should be appended in parens for readability.
            assert "(WARNING)" in r.error_message

            # Happy-path regression: a clean sketch must still return
            # error_message=None.
            sk2 = SketchBuilder(plane=SketchPlane.TOP, plane_id=top_id, name="OK")
            sk2.add_rectangle(corner1=(0, 0), corner2=(10, 10))
            r2 = await apply_feature_and_check(client, did, wid, eid, sk2.build())
            assert r2.status == "OK"
            assert r2.error_message is None

        finally:
            try:
                await client.delete(f"/api/v6/documents/{did}")
            except Exception:  # noqa: BLE001
                pass
