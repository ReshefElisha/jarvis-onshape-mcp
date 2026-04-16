"""Real-API proof that create_part_studio surfaces sibling Part Studios.

Fresh Onshape documents ship with an empty default "Part Studio 1".
After this commit the create_part_studio tool returns that default in
`other_part_studios` so downstream callers don't render the empty one
by accident. This test creates a throwaway doc, calls the tool, and
asserts the default Part Studio shows up in the list.

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
async def test_create_part_studio_surfaces_default_sibling(
    client, monkeypatch
):
    """Dogfood #6: default PS isn't destroyed, but is surfaced so callers can target the new id."""
    # The server module constructs module-level managers from env-derived
    # credentials at import time; point them at the freshly built `client`
    # via monkeypatch so this real test uses the fixture's live session.
    from onshape_mcp.api.documents import DocumentManager
    from onshape_mcp.api.partstudio import PartStudioManager

    monkeypatch.setattr(S, "client", client)
    monkeypatch.setattr(S, "document_manager", DocumentManager(client))
    monkeypatch.setattr(S, "partstudio_manager", PartStudioManager(client))

    doc = await DocumentManager(client).create_document(
        name="mcp-create-ps-real (auto)"
    )
    try:
        summary = await S.document_manager.get_document_summary(doc.id)
        workspace = summary["workspaces"][0]

        result_blocks = await S.call_tool("create_part_studio", {
            "documentId": doc.id,
            "workspaceId": workspace.id,
            "name": "Second PS",
        })
        payload = json.loads(result_blocks[0].text)

        assert payload["ok"] is True
        assert payload["status"] == "OK"
        assert payload["element_name"] == "Second PS"
        assert payload["element_id"], "new element id missing"

        sibling_names = [p["name"] for p in payload["other_part_studios"]]
        # The default Onshape creates on doc-create is called "Part Studio 1";
        # assert it's surfaced but don't hard-couple to the exact name — if
        # Onshape ever changes the default, "at least one sibling exists"
        # still carries the contract we care about.
        assert payload["other_part_studios"], (
            f"other_part_studios empty — default PS should be listed. "
            f"full payload: {payload!r}"
        )
        # The new element id must NOT appear in the sibling list.
        sibling_ids = [p["id"] for p in payload["other_part_studios"]]
        assert payload["element_id"] not in sibling_ids
    finally:
        try:
            await DocumentManager(client).delete_document(doc.id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                raise
