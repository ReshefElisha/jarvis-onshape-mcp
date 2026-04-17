"""Real-API test for the Variable Studio + variable-driven sketch flow.

Covers dogfooder bug #1 (z5rz5fhl): set_variable used to 404 because it
posted to the Part Studio /variables endpoint, which is read-only on
modern Onshape docs. Modern flow:

    1. create_variable_studio  -> VS element id
    2. set_variable on the VS  -> writes a length variable
    3. sketch with variableWidth="<name>"  -> resolves #name from VS
    4. update set_variable     -> Part Studio re-resolves, width changes

The end-to-end test exercises all 4 steps plus get_variables read-back.

Skipped automatically when ONSHAPE_ACCESS_KEY is missing.

Probe + endpoint discovery: scratchpad/variables-probe-2.md.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.entities import EntityManager
from onshape_mcp.api.feature_apply import apply_feature_and_check
from onshape_mcp.api.partstudio import PartStudioManager
from onshape_mcp.api.variables import VariableManager
from onshape_mcp.builders.extrude import ExtrudeBuilder, ExtrudeType
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


def _plate_extent_x(snap_bodies: list) -> float:
    """X-extent (mm) of the first body's bounding box. Reads body face origins
    to back out width without assuming a particular face id."""
    faces = snap_bodies[0]["faces"]
    plane_xs = [
        f["origin"][0] * 1000
        for f in faces
        if f.get("type") == "PLANE"
        and f.get("normal_axis") in ("+X", "-X")
        and f.get("origin") is not None
    ]
    return max(plane_xs) - min(plane_xs)


@pytest.fixture
async def client():
    async with OnshapeClient(_creds()) as c:
        yield c


@pytest.mark.asyncio
async def test_variable_drives_sketch_width(client):
    docs = DocumentManager(client)
    ps_mgr = PartStudioManager(client)
    vars_mgr = VariableManager(client)
    ents = EntityManager(client)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    doc = await docs.create_document(name=f"dyna-mcp vars test {ts}")
    did = doc.id
    try:
        wid = (await docs.get_workspaces(did))[0].id

        # 1. Create a Variable Studio in the workspace.
        vs_eid = await vars_mgr.create_variable_studio(did, wid, name="VS")
        assert vs_eid

        # 2. Write `width = 30 mm` into it.
        await vars_mgr.set_variable(did, wid, vs_eid, "width", "30 mm")

        # 2a. Read back via get_variables (proves the flatten fix works too).
        vars_back = await vars_mgr.get_variables(did, wid, vs_eid)
        assert any(v.name == "width" and v.expression == "30 mm" for v in vars_back), (
            f"width=30mm not surfaced by get_variables: {vars_back!r}"
        )

        # 3. Create a Part Studio + sketch a rect whose width references #width.
        ps = await ps_mgr.create_part_studio(did, wid, name="PS")
        ps_eid = ps["id"]
        top_plane_id = await ps_mgr.get_plane_id(did, wid, ps_eid, "Top")

        rect = SketchBuilder(plane=SketchPlane.TOP, plane_id=top_plane_id, name="Rect")
        # 30 mm wide (driven by #width) x 20 mm tall (literal). Builder writes
        # the variable name into both the corners and a width parameter.
        rect.add_rectangle(
            corner1=(0, 0),
            corner2=("30 mm", 20),
            variable_width="width",
        )
        rect_r = await apply_feature_and_check(client, did, wid, ps_eid, rect.build())
        assert rect_r.status == "OK", rect_r.error_message

        ext = ExtrudeBuilder(
            name="Extrude", sketch_feature_id=rect_r.feature_id,
            depth=5, operation_type=ExtrudeType.NEW,
        )
        ext_r = await apply_feature_and_check(client, did, wid, ps_eid, ext.build())
        assert ext_r.status == "OK", ext_r.error_message

        # 3a. Confirm the body is 30 mm wide via list_entities.
        snap = await ents.list_entities(did, wid, ps_eid)
        width_before = _plate_extent_x(snap["bodies"])
        assert abs(width_before - 30.0) < 0.5, (
            f"expected 30 mm wide before update, got {width_before:.3f} mm"
        )

        # 4. Update the variable to 50 mm; re-describe; expect the rect to grow.
        await vars_mgr.set_variable(did, wid, vs_eid, "width", "50 mm")
        snap2 = await ents.list_entities(did, wid, ps_eid)
        width_after = _plate_extent_x(snap2["bodies"])
        assert abs(width_after - 50.0) < 0.5, (
            f"expected 50 mm wide after variable update, got {width_after:.3f} mm "
            f"(width_before={width_before:.3f})"
        )

    finally:
        try:
            await client.delete(f"/api/v6/documents/{did}")
        except Exception:  # noqa: BLE001
            pass


@pytest.mark.asyncio
async def test_set_variable_upserts_by_name(client):
    """set_variable must be upsert-by-name, not wholesale replace.

    Regression for the parametric-reparametrize dogfood bug: the underlying
    Onshape /variables POST endpoint replaces the VS's entire contents with
    the posted list, so naive single-var writes silently drop every other
    variable. Downstream `#name` references in sketches then resolve to
    nothing and Onshape returns `featureStatus: WARNING` with no message.

    Asserts: after set A=1, set B=2, set C=3 (three separate set_variable
    calls), the VS contains all three. Pre-fix, only `C` would remain.
    """
    vars_mgr = VariableManager(client)
    docs = DocumentManager(client)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    doc = await docs.create_document(name=f"dyna-mcp upsert test {ts}")
    did = doc.id
    try:
        wid = (await docs.get_workspaces(did))[0].id
        vs_eid = await vars_mgr.create_variable_studio(did, wid, name="VS")

        await vars_mgr.set_variable(did, wid, vs_eid, "alpha", "10 mm")
        await vars_mgr.set_variable(did, wid, vs_eid, "beta", "20 mm")
        await vars_mgr.set_variable(did, wid, vs_eid, "gamma", "30 mm")

        got = await vars_mgr.get_variables(did, wid, vs_eid)
        by_name = {v.name: v.expression for v in got}
        assert by_name == {
            "alpha": "10 mm",
            "beta": "20 mm",
            "gamma": "30 mm",
        }, f"upsert should preserve all three variables, got {by_name!r}"

        # Updating an existing variable should keep the rest intact.
        await vars_mgr.set_variable(did, wid, vs_eid, "alpha", "15 mm")
        got = await vars_mgr.get_variables(did, wid, vs_eid)
        by_name = {v.name: v.expression for v in got}
        assert by_name == {
            "alpha": "15 mm",
            "beta": "20 mm",
            "gamma": "30 mm",
        }, f"updating alpha shouldn't drop beta/gamma, got {by_name!r}"

    finally:
        try:
            await client.delete(f"/api/v6/documents/{did}")
        except Exception:  # noqa: BLE001
            pass
