"""Real-API test for FS REGEN-error enrichment.

Before this fix: a FeatureScript custom feature that compiled but failed at
REGEN came back with `error_message = "REGEN_ERROR (ERROR)"`. The actual
diagnostic ("Function opThisDoesNotExist with 3 argument(s) not found")
lived only on the body of the user's `defineFeature(function...)` and
required re-evaluation via `/featurescript` to surface.

This test uploads a custom FS feature whose body calls a non-existent
function. It asserts the `error_message` carries:
    - the original status enum (REGEN_ERROR)
    - a `FS NOTICES:` block
    - the actual failing symbol name (`opThisDoesNotExist`)

Live-probed channels (probe_fs_diag2.py, 2026-04-17): only inline-body
re-eval surfaced the symbol; getFeatureStatus, getFeatureError,
featurespecs response, and direct-instantiate response all carry only the
opaque enum.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.custom_features import CustomFeatureManager, DEFAULT_FS_VERSION
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.partstudio import PartStudioManager


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


# A FS source that compiles cleanly (so featurespecs is non-empty) but the
# body call resolves to a function that doesn't exist in std. This is the
# canonical failure mode for FS that survives compile-check but blows up at
# REGEN. The opaque status enum we'd return without enrichment is
# REGEN_ERROR; the real diagnostic names `opThisDoesNotExist`.
BAD_FUNC_FS = f"""\
FeatureScript {DEFAULT_FS_VERSION};
import(path : "onshape/std/geometry.fs", version : "{DEFAULT_FS_VERSION}.0");

annotation {{ "Feature Type Name" : "Bad Function" }}
export const badFunc = defineFeature(function(context is Context, id is Id, definition is map)
    precondition {{ }}
    {{
        opThisDoesNotExist(context, id + "x", {{ }});
    }});
"""


@pytest.mark.asyncio
async def test_fs_regen_error_carries_notice_text():
    async with OnshapeClient(_creds()) as client:
        docs = DocumentManager(client)
        ps_mgr = PartStudioManager(client)
        custom = CustomFeatureManager(client)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        doc = await docs.create_document(name=f"dyna-mcp fs-error-enrich {ts}")
        did = doc.id
        try:
            wid = (await docs.get_workspaces(did))[0].id
            ps = await ps_mgr.create_part_studio(did, wid, name="ps")
            ps_eid = ps["id"] if isinstance(ps, dict) else ps.id

            out = await custom.apply_featurescript_feature(
                did,
                wid,
                ps_eid,
                feature_type="badFunc",
                feature_script=BAD_FUNC_FS,
                feature_name="bad func",
            )
            r = out["apply_result"]

            # The feature compiled (non-empty featurespecs) but failed at
            # regen. We expect ERROR with the enum-prefixed message, plus an
            # appended FS NOTICES block naming the failing call.
            assert r.status == "ERROR", (
                f"expected ERROR, got status={r.status!r} "
                f"error_message={r.error_message!r}"
            )
            assert r.error_message, "error_message must be populated on ERROR"
            # Prior enrichment (warning-enrich) lead: status enum.
            assert "REGEN_ERROR" in r.error_message, (
                f"expected REGEN_ERROR in error_message, got {r.error_message!r}"
            )
            # New enrichment (this fix): the FS NOTICES block must be present
            # and must name the failing symbol so Claude can act on it
            # without spending diagnostic-eval turns.
            assert "FS NOTICES:" in r.error_message, (
                f"expected 'FS NOTICES:' block in error_message, got "
                f"{r.error_message!r}"
            )
            assert "opThisDoesNotExist" in r.error_message, (
                f"expected failing symbol 'opThisDoesNotExist' in "
                f"error_message, got {r.error_message!r}"
            )

        finally:
            try:
                await client.delete(f"/api/v6/documents/{did}")
            except Exception:  # noqa: BLE001
                pass


@pytest.mark.asyncio
async def test_fs_ok_path_skips_enrichment():
    """Happy path regression: a clean FS feature must NOT carry an
    error_message and must NOT trigger the body re-eval round-trip. The OK
    path's wire shape should be unchanged from before this fix."""
    async with OnshapeClient(_creds()) as client:
        docs = DocumentManager(client)
        ps_mgr = PartStudioManager(client)
        custom = CustomFeatureManager(client)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        doc = await docs.create_document(name=f"dyna-mcp fs-ok-regression {ts}")
        did = doc.id
        try:
            wid = (await docs.get_workspaces(did))[0].id
            ps = await ps_mgr.create_part_studio(did, wid, name="ps")
            ps_eid = ps["id"] if isinstance(ps, dict) else ps.id

            ok_fs = f"""\
FeatureScript {DEFAULT_FS_VERSION};
import(path : "onshape/std/geometry.fs", version : "{DEFAULT_FS_VERSION}.0");

annotation {{ "Feature Type Name" : "Good Plane" }}
export const goodPlane = defineFeature(function(context is Context, id is Id, definition is map)
    precondition {{ }}
    {{
        opPlane(context, id + "p", {{
            "plane" : plane(vector(0, 0, 0.01) * meter, vector(0, 0, 1))
        }});
    }});
"""
            out = await custom.apply_featurescript_feature(
                did, wid, ps_eid,
                feature_type="goodPlane",
                feature_script=ok_fs,
                feature_name="good plane",
            )
            r = out["apply_result"]
            assert r.ok is True, f"expected OK, got {r.status} {r.error_message!r}"
            assert r.error_message is None

        finally:
            try:
                await client.delete(f"/api/v6/documents/{did}")
            except Exception:  # noqa: BLE001
                pass
