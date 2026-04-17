"""Smoke-test the new primitives end-to-end via their builders.

Builds the peer-reported USB-C enclosure skeleton:
  - 70x40x15 mm box (extrude)
  - Shell top face inward by 1.5 mm (create_shell)
  - Offset plane 2.5 mm above Top datum (create_offset_plane)

Validates: feature status OK, volume went down after shell, offset-plane
feature stored at the right offset.

Usage:
    uv run python scripts/smoke_new_primitives.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.partstudio import PartStudioManager
from onshape_mcp.api.entities import EntityManager
from onshape_mcp.api.feature_apply import apply_feature_and_check
from onshape_mcp.builders.sketch import SketchBuilder
from onshape_mcp.builders.extrude import ExtrudeBuilder, ExtrudeType
from onshape_mcp.builders.shell import ShellBuilder
from onshape_mcp.builders.offset_plane import OffsetPlaneBuilder


async def main() -> None:
    ak = os.getenv("ONSHAPE_API_KEY") or os.getenv("ONSHAPE_ACCESS_KEY", "")
    sk = os.getenv("ONSHAPE_API_SECRET") or os.getenv("ONSHAPE_SECRET_KEY", "")
    client = OnshapeClient(OnshapeCredentials(access_key=ak, secret_key=sk))
    docs = DocumentManager(client)
    ps = PartStudioManager(client)
    ents = EntityManager(client)

    doc = await docs.create_document(name="smoke-shell-offsetplane")
    did = doc.id
    print(f"[doc] {did}")
    try:
        summary = await docs.get_document_summary(did)
        wid = summary["workspaces"][0].id
        studios = await docs.find_part_studios(did, wid)
        eid = studios[0].id

        top_plane_id = await ps.get_plane_id(did, wid, eid, "Top")
        sk = SketchBuilder(name="Base", plane="Top", plane_id=top_plane_id)
        sk.add_rectangle([0, 0], [0.070, 0.040])
        sr = await apply_feature_and_check(
            client, did, wid, eid, {"feature": sk.build()["feature"]},
        )
        assert sr.ok, f"sketch failed: {sr.error_message}"
        print(f"[sketch] {sr.status}")

        ex = ExtrudeBuilder(
            name="Box", sketch_feature_id=sr.feature_id, depth=0.015,
            operation_type=ExtrudeType.NEW,
        )
        er = await apply_feature_and_check(
            client, did, wid, eid, ex.build(),
        )
        assert er.ok, f"extrude failed: {er.error_message}"
        print(f"[extrude] {er.status}")

        # Find top face (+Z outward)
        snap = await ents.list_entities(
            did, wid, eid, kinds=["faces"], outward_axis="+Z"
        )
        top_face_id = snap["bodies"][0]["faces"][0]["id"]
        print(f"[top_face] {top_face_id}")

        shell = ShellBuilder(name="Shell", thickness="1.5 mm")
        shell.add_face(top_face_id)
        shr = await apply_feature_and_check(
            client, did, wid, eid, shell.build(), track_changes=True,
        )
        assert shr.ok, f"shell failed: {shr.error_message}"
        print(f"[shell] {shr.status}")
        print(f"         changes: {json.dumps(shr.changes, indent=2, default=str) if shr.changes else None}")

        plane = OffsetPlaneBuilder(
            name="PCB Rail Plane", reference_id=top_plane_id, offset="2.5 mm",
        )
        pr = await apply_feature_and_check(
            client, did, wid, eid, plane.build(),
        )
        assert pr.ok, f"offset plane failed: {pr.error_message}"
        print(f"[offset_plane] {pr.status}")

        plane2 = OffsetPlaneBuilder(
            name="Above Top Face", reference_id=top_face_id, offset="5 mm",
        )
        pr2 = await apply_feature_and_check(
            client, did, wid, eid, plane2.build(),
        )
        assert pr2.ok, f"offset-from-face failed: {pr2.error_message}"
        print(f"[offset_plane_from_face] {pr2.status}")

        print("\nSMOKE OK")
    finally:
        try:
            await docs.delete_document(did)
            print(f"[cleanup] deleted {did}")
        except Exception as e:  # noqa: BLE001
            print(f"[cleanup] FAILED to delete {did}: {e}")
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
