"""Real-API test for enum-specific `hints` advice in tool responses.

When the FS statusEnum carries a known error code (BOOLEAN_SUBTRACT_NO_OP,
SKETCH_DIMENSION_MISSING_PARAMETER), `_hints_for_result` should prepend a
targeted recovery hint BEFORE the generic status-based hints. The generic
"read error_message" advice would otherwise waste >=3 turns rediscovering
what the enum already names.

Trigger: REMOVE extrude on a picked face with `forceOppositeDirection:
False`. That bypasses the auto-flip the extrude handler normally applies
on REMOVE+faceId, so the cut points away from the material and Onshape
returns INFO with statusEnum=BOOLEAN_SUBTRACT_NO_OP.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.entities import EntityManager
from onshape_mcp.api.feature_apply import apply_feature_and_check
from onshape_mcp.api.partstudio import PartStudioManager
from onshape_mcp.builders.extrude import ExtrudeBuilder, ExtrudeType
from onshape_mcp.builders.sketch import SketchBuilder, SketchPlane
from onshape_mcp.server import call_tool


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
async def test_boolean_subtract_no_op_hint_names_force_opposite_direction():
    """Build a plate, then a REMOVE extrude on the top face with the auto-flip
    overridden off -- the cut points up into air, removes 0 volume, Onshape
    returns INFO with BOOLEAN_SUBTRACT_NO_OP. Assert the response's hints
    array contains a string referencing forceOppositeDirection."""
    async with OnshapeClient(_creds()) as client:
        docs = DocumentManager(client)
        ps_mgr = PartStudioManager(client)
        ents = EntityManager(client)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        doc = await docs.create_document(name=f"dyna-mcp hints-enum {ts}")
        did = doc.id
        try:
            wid = (await docs.get_workspaces(did))[0].id
            eid = (await ps_mgr.create_part_studio(did, wid, name="ps"))["id"]
            top_id = await ps_mgr.get_plane_id(did, wid, eid, "Top")

            # Plate 30x30x10.
            plate_sk = SketchBuilder(plane=SketchPlane.TOP, plane_id=top_id, name="plate")
            plate_sk.add_rectangle(corner1=(0, 0), corner2=(30, 30))
            ps = await apply_feature_and_check(client, did, wid, eid, plate_sk.build())
            assert ps.status == "OK"
            plate_ext = ExtrudeBuilder(
                name="plate", sketch_feature_id=ps.feature_id,
                depth=10, operation_type=ExtrudeType.NEW,
            )
            await apply_feature_and_check(client, did, wid, eid, plate_ext.build())

            # Find the +Z top face.
            snap0 = await ents.list_entities(did, wid, eid)
            top_face = next(
                f for f in snap0["bodies"][0]["faces"]
                if f.get("type") == "PLANE"
                and f.get("outward_axis") == "+Z"
                and f.get("origin") and abs(f["origin"][2] * 1000 - 10.0) < 0.5
            )

            # Sketch a circle on the top face. Then run the cut THROUGH the
            # MCP tool handler (not the builder directly) so the
            # forceOppositeDirection bypass + the hints assembly both fire
            # exactly as Claude would see them.
            hole_sk = SketchBuilder(plane=SketchPlane.TOP, plane_id=top_face["id"], name="hole")
            hole_sk.add_circle(center=(15, 15), radius=4)
            hr = await apply_feature_and_check(client, did, wid, eid, hole_sk.build())
            assert hr.status == "OK"

            # Now invoke create_extrude through the MCP handler with
            # forceOppositeDirection=False, which bypasses the auto-flip and
            # makes the cut point AWAY from the material.
            content_blocks = await call_tool(
                "create_extrude",
                {
                    "documentId": did,
                    "workspaceId": wid,
                    "elementId": eid,
                    "sketchFeatureId": hr.feature_id,
                    "name": "no-op cut",
                    "depth": 5,
                    "operationType": "REMOVE",
                    "forceOppositeDirection": False,  # the trigger
                },
            )
            assert content_blocks, "no response from create_extrude"
            payload = json.loads(content_blocks[0].text)

            # The cut should still complete (Onshape regen succeeds, just
            # produces no volume change). It comes back as INFO with the
            # BOOLEAN_SUBTRACT_NO_OP enum.
            assert payload["status"] in ("INFO", "OK"), (
                f"expected INFO/OK status from a no-op cut, got "
                f"{payload['status']}: {payload.get('error_message')}"
            )
            err_msg = payload.get("error_message") or ""
            assert "BOOLEAN_SUBTRACT_NO_OP" in err_msg, (
                f"trigger missed: this fixture should produce "
                f"BOOLEAN_SUBTRACT_NO_OP, got {err_msg!r}. "
                f"If Onshape changed behavior here, update the fixture."
            )

            hints = payload.get("hints") or []
            joined = " ".join(hints)
            assert (
                "forceOppositeDirection" in joined
                or "oppositeDirection" in joined
            ), (
                f"BOOLEAN_SUBTRACT_NO_OP hint should reference "
                f"forceOppositeDirection / oppositeDirection. hints={hints!r}"
            )
            # The enum-specific hint should come FIRST so Claude reads it
            # before the generic status hint.
            assert "BOOLEAN_SUBTRACT_NO_OP" in hints[0] or (
                "forceOppositeDirection" in hints[0]
            ), f"enum-specific hint should be first; got hints[0]={hints[0]!r}"

        finally:
            try:
                await client.delete(f"/api/v6/documents/{did}")
            except Exception:  # noqa: BLE001
                pass


@pytest.mark.asyncio
async def test_sketch_dimension_missing_parameter_hint_names_create_variable_studio():
    """Sketch a circle with `variable_radius` referencing an undefined name.
    Onshape returns WARNING with SKETCH_DIMENSION_MISSING_PARAMETER. The
    enum-specific hint should name `create_variable_studio` + `set_variable`
    rather than just generic 'check error_message' advice.
    """
    async with OnshapeClient(_creds()) as client:
        docs = DocumentManager(client)
        ps_mgr = PartStudioManager(client)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        doc = await docs.create_document(name=f"dyna-mcp hints-vs {ts}")
        did = doc.id
        try:
            wid = (await docs.get_workspaces(did))[0].id
            eid = (await ps_mgr.create_part_studio(did, wid, name="ps"))["id"]
            top_id = await ps_mgr.get_plane_id(did, wid, eid, "Top")

            sk = SketchBuilder(plane=SketchPlane.TOP, plane_id=top_id, name="bad")
            sk.add_circle(center=(0, 0), radius=3, variable_radius="not_a_real_var_xyz")
            r = await apply_feature_and_check(client, did, wid, eid, sk.build())

            assert r.status == "WARNING"
            assert "SKETCH_DIMENSION_MISSING_PARAMETER" in (r.error_message or "")

            # Pull hints via _hints_for_result directly (no need to round-
            # trip through a tool handler -- the helper is the unit under
            # test).
            from onshape_mcp.server import _hints_for_result
            hints = _hints_for_result(r)
            joined = " ".join(hints)
            assert "create_variable_studio" in joined, (
                f"hint should name create_variable_studio. hints={hints!r}"
            )
            assert "set_variable" in joined
            # Enum-specific hint comes first.
            assert "SKETCH_DIMENSION_MISSING_PARAMETER" in hints[0]

        finally:
            try:
                await client.delete(f"/api/v6/documents/{did}")
            except Exception:  # noqa: BLE001
                pass
