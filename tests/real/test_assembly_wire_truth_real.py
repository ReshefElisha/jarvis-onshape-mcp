"""Real-API proof that the assembly mutators return structured JSON.

Replays a compressed version of the assembly dogfood flow:
  1. disposable doc + 1 Part Studio + 1 Assembly element
  2. a simple body in the PS
  3. add_assembly_instance returns {ok, instance_id, ...}
  4. create_mate_connector returns {ok, status, feature_id, ...}
  5. set_instance_position returns {ok, position_mm, ...}
  6. get_assembly_positions output renders in mm (not inches)

The goal is status-plumbing correctness — we don't need two parts and four
mates to prove every mate handler; the shared `_create_mate` helper is unit-
tested and the mate handlers are thin wrappers.

Auto-skipped without credentials.
"""

from __future__ import annotations

import json
import os

import httpx
import pytest

from onshape_mcp import server as S
from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import DocumentManager

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (
            (os.getenv("ONSHAPE_ACCESS_KEY") or os.getenv("ONSHAPE_API_KEY"))
            and (os.getenv("ONSHAPE_SECRET_KEY") or os.getenv("ONSHAPE_API_SECRET"))
        ),
        reason="Requires ONSHAPE_ACCESS_KEY/ONSHAPE_SECRET_KEY (or ONSHAPE_API_KEY/SECRET) in env",
    ),
]


@pytest.fixture
async def client():
    access_key = os.environ.get("ONSHAPE_ACCESS_KEY") or os.environ["ONSHAPE_API_KEY"]
    secret_key = os.environ.get("ONSHAPE_SECRET_KEY") or os.environ["ONSHAPE_API_SECRET"]
    creds = OnshapeCredentials(access_key=access_key, secret_key=secret_key)
    async with OnshapeClient(creds) as c:
        yield c


@pytest.mark.asyncio
async def test_assembly_wire_truth_end_to_end(client, monkeypatch):
    """Thread the assembly mutators; assert every return is structured JSON."""
    from onshape_mcp.api.documents import DocumentManager
    from onshape_mcp.api.partstudio import PartStudioManager
    from onshape_mcp.api.assemblies import AssemblyManager
    from onshape_mcp.api.feature_apply import apply_feature_and_check
    from onshape_mcp.builders.sketch import SketchBuilder, SketchPlane
    from onshape_mcp.builders.extrude import ExtrudeBuilder

    monkeypatch.setattr(S, "client", client)
    monkeypatch.setattr(S, "document_manager", DocumentManager(client))
    monkeypatch.setattr(S, "partstudio_manager", PartStudioManager(client))
    monkeypatch.setattr(S, "assembly_manager", AssemblyManager(client))

    dm = S.document_manager
    ps = S.partstudio_manager

    doc = await dm.create_document(name="mcp-asm-wire-truth-real (auto)")
    try:
        summary = await dm.get_document_summary(doc.id)
        ws = summary["workspaces"][0]
        part_elem = (await ps.create_part_studio(doc.id, ws.id, "widget"))["id"]

        # Build a tiny 20x20x6 mm body in the PS so get_body_details
        # returns at least one face id for the mate connector.
        top = await ps.get_plane_id(doc.id, ws.id, part_elem, "Top")
        sk = SketchBuilder(plane=SketchPlane.TOP, plane_id=top)
        sk.add_rectangle(corner1=(0, 0), corner2=(20, 20))
        sr = await apply_feature_and_check(client, doc.id, ws.id, part_elem, sk.build())
        assert sr.ok
        ex = ExtrudeBuilder(sketch_feature_id=sr.feature_id, depth=6)
        er = await apply_feature_and_check(client, doc.id, ws.id, part_elem, ex.build())
        assert er.ok

        # ---- create_assembly: structured JSON + element_id ----
        ca_blocks = await S.call_tool("create_assembly", {
            "documentId": doc.id, "workspaceId": ws.id, "name": "asm",
        })
        ca = json.loads(ca_blocks[0].text)
        assert ca["ok"] is True and ca["status"] == "OK"
        asm_eid = ca["element_id"]
        assert asm_eid

        # ---- add_assembly_instance: diff-populates instance_id ----
        add_blocks = await S.call_tool("add_assembly_instance", {
            "documentId": doc.id, "workspaceId": ws.id, "elementId": asm_eid,
            "partStudioElementId": part_elem,
        })
        add = json.loads(add_blocks[0].text)
        assert add["ok"] is True and add["status"] == "OK"
        assert add["instance_id"], f"no instance_id returned: {add!r}"

        # ---- get_body_details: need a face id for create_mate_connector ----
        details = await ps.get_body_details(doc.id, ws.id, part_elem)
        face_id = details["bodies"][0]["faces"][0]["id"]

        # ---- create_mate_connector: structured JSON with featureStatus ----
        mc_blocks = await S.call_tool("create_mate_connector", {
            "documentId": doc.id, "workspaceId": ws.id, "elementId": asm_eid,
            "instanceId": add["instance_id"],
            "faceId": face_id,
            "name": "probeMC",
        })
        mc = json.loads(mc_blocks[0].text)
        assert mc["ok"] is True, f"MC failed: {mc!r}"
        assert mc["status"] == "OK"
        assert mc["feature_id"]
        assert mc["feature_type"] == "mateConnector"
        assert mc["feature_name"] == "probeMC"

        # ---- set_instance_position: mm-default roundtrip ----
        # First instance is auto-grounded; put the instance at an absolute
        # position. Use an explicit unit string to prove parsing works at
        # the real-transport layer.
        sp_blocks = await S.call_tool("set_instance_position", {
            "documentId": doc.id, "workspaceId": ws.id, "elementId": asm_eid,
            "instanceId": add["instance_id"],
            "x": "20 mm", "y": 0, "z": 0,
        })
        sp = json.loads(sp_blocks[0].text)
        # Grounded-instance rejection is valid too (API 400); accept either
        # ok=True or a clean EXCEPTION with the 400 inline — the contract
        # we're testing is "structured JSON always", not whether Onshape
        # allowed the move.
        assert sp["status"] in ("OK", "EXCEPTION")
        if sp["status"] == "OK":
            assert sp["position_mm"]["x"] == pytest.approx(20.0)
            assert sp["position_mm"]["y"] == pytest.approx(0.0)

        # ---- get_assembly_positions: mm in the output text ----
        gp_blocks = await S.call_tool("get_assembly_positions", {
            "documentId": doc.id, "workspaceId": ws.id, "elementId": asm_eid,
        })
        # Positions tool returns a formatted text (not JSON) — assert it
        # prints mm, not inches.
        gp_text = gp_blocks[0].text
        assert " mm" in gp_text, f"assembly positions not in mm: {gp_text[:200]!r}"
        # And no stray inch marks.
        assert '"' not in gp_text.replace('**', '')  # no stray " suffixes
    finally:
        try:
            await dm.delete_document(doc.id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                raise
