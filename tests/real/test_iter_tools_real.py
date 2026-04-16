"""Real-API tests for the iteration tools: update_feature, delete_feature_by_name,
delete_document.

Two scenarios:
1. `test_update_feature_and_delete_by_name_flow` creates a throwaway document,
   runs the Adam-CAD-style iteration loop (sketch → extrude → patch-depth →
   delete-by-name) against it, and asserts each step's structured status.
   Document cleanup is best-effort because some API keys lack the Delete scope
   and return 403 (see next test); the leftover trash is harmless.
2. `test_delete_document_best_effort` is a separate, tiny test that gates on
   delete scope: on 403 it pytest.skip()s with a clear scope hint rather than
   failing the whole iter-tools suite.

Auto-skipped without credentials.
"""

from __future__ import annotations

import os

import httpx
import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.partstudio import PartStudioManager
from onshape_mcp.api.feature_apply import (
    apply_feature_and_check,
    update_feature_params_and_check,
)
from onshape_mcp.builders.sketch import SketchBuilder, SketchPlane
from onshape_mcp.builders.extrude import ExtrudeBuilder, ExtrudeType

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


async def _disposable_doc(client: OnshapeClient) -> tuple[str, str, str]:
    """Create a doc + the (auto) default Part Studio, return (doc, ws, elem)."""
    docs = DocumentManager(client)
    ps = PartStudioManager(client)

    doc = await docs.create_document(name="mcp-iter-tools-real (auto)")
    summary = await docs.get_document_summary(doc.id)
    workspace = summary["workspaces"][0]
    elements = summary["workspace_details"][0]["elements"]
    part_studios = [e for e in elements if e.element_type.replace(" ", "").upper() == "PARTSTUDIO"]
    if not part_studios:
        # Onshape sometimes creates empty docs; add one.
        created = await ps.create_part_studio(doc.id, workspace.id, name="Part Studio 1")
        return doc.id, workspace.id, created["id"]
    return doc.id, workspace.id, part_studios[0].id


@pytest.mark.asyncio
async def test_update_feature_and_delete_by_name_flow(client):
    """End-to-end iteration loop.

    1. Create disposable document.
    2. Sketch a 10x10 mm square, extrude 10 mm.
    3. Patch the extrude depth to 15 mm via update_feature_params_and_check;
       assert featureStatus=OK and that the sketch still shows the patch.
    4. Delete the extrude by name (via the underlying manager; the tool handler
       is covered by the mocked unit test).
    5. Best-effort delete the document (may 403 — see the scope-gated test below).
    """
    doc_id, ws_id, elem_id = await _disposable_doc(client)

    try:
        ps = PartStudioManager(client)

        # --- build a sketch ------------------------------------------------
        plane_id = await ps.get_plane_id(doc_id, ws_id, elem_id, "Top")
        sketch = SketchBuilder(name="Square", plane=SketchPlane.TOP, plane_id=plane_id)
        sketch.add_rectangle(corner1=(0, 0), corner2=(0.4, 0.4))  # inches
        sketch_result = await apply_feature_and_check(
            client, doc_id, ws_id, elem_id, sketch.build(),
        )
        assert sketch_result.ok, f"sketch failed: {sketch_result.error_message}"
        sketch_fid = sketch_result.feature_id

        # --- build an extrude --------------------------------------------
        extrude = ExtrudeBuilder(
            name="Iter Extrude",
            sketch_feature_id=sketch_fid,
            operation_type=ExtrudeType.NEW,
        )
        extrude.set_depth(0.4)  # inches
        extrude_result = await apply_feature_and_check(
            client, doc_id, ws_id, elem_id, extrude.build(),
        )
        assert extrude_result.ok, f"extrude failed: {extrude_result.error_message}"
        extrude_fid = extrude_result.feature_id

        # --- patch depth -> 15 mm ----------------------------------------
        patched = await update_feature_params_and_check(
            client, doc_id, ws_id, elem_id, extrude_fid,
            [{"parameterId": "depth", "expression": "15 mm"}],
        )
        assert patched.ok, f"patch failed: {patched.error_message}"
        assert patched.feature_id == extrude_fid

        # Fetch current features to confirm the depth expression actually changed.
        feats = await ps.get_features(doc_id, ws_id, elem_id)
        patched_feat = next(
            f for f in feats.get("features", []) if f.get("featureId") == extrude_fid
        )
        depth_param = next(
            p for p in patched_feat.get("parameters", [])
            if p.get("parameterId") == "depth"
        )
        assert depth_param.get("expression") == "15 mm"

        # --- delete extrude by name --------------------------------------
        target_name = patched_feat.get("name", "Iter Extrude")
        all_feat_ids_before = {f.get("featureId") for f in feats.get("features", [])}
        # Reuse the underlying helper directly (the tool handler logic is
        # mocked-unit-tested; here we just want to prove the full flow).
        matches = [f for f in feats.get("features", []) if f.get("name") == target_name]
        assert len(matches) == 1
        await ps.delete_feature(doc_id, ws_id, elem_id, matches[0]["featureId"])

        feats_after = await ps.get_features(doc_id, ws_id, elem_id)
        all_feat_ids_after = {f.get("featureId") for f in feats_after.get("features", [])}
        assert extrude_fid not in all_feat_ids_after
        assert extrude_fid in all_feat_ids_before
    finally:
        # Always attempt cleanup, but don't fail the test on permission
        # errors — API keys without Delete scope 403 here, and the feature
        # assertions above are the real contract being tested.
        try:
            docs = DocumentManager(client)
            await docs.delete_document(doc_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                raise


@pytest.mark.asyncio
async def test_delete_document_best_effort(client):
    """Scope-gated test for delete_document.

    Creates a throwaway doc, deletes it, asserts the hit succeeded. If the API
    key lacks Delete scope (403), skip with a clear message rather than fail —
    this is an environmental constraint, not a tool bug.
    """
    docs = DocumentManager(client)
    doc = await docs.create_document(name="mcp-iter-tools-real delete-smoke (auto)")
    try:
        await docs.delete_document(doc.id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            pytest.skip(
                "Onshape API key lacks Delete scope (403). The DocumentManager "
                "wrapper is shape-correct per unit tests; grant OAuth2Delete "
                "scope to this key on https://dev-portal.onshape.com/ to run "
                "this integration test."
            )
        raise
