"""Real-API integration test for the export pipeline.

Exports the reserved smoke-test document as STEP end-to-end: start
translation, poll to DONE, download bytes. Asserts the bytes are a valid
STEP file (starts with the ISO-10303-21 magic header) and larger than 1KB
(the smoke doc has a real part in it, so a trivial-sized response would
mean the pipeline downloaded the wrong thing).

Skipped automatically when ONSHAPE_ACCESS_KEY is not set, so inert in the
default pytest run.

Evidence the starter's export was fire-and-forget:
/Users/shef/projects/onshape-mcp/scratchpad/smoke-test.md
"""

from __future__ import annotations

import os

import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.export import ExportManager, TranslationResult

# Reserved smoke-test document.
DOC_ID = "c287a50857bf10a5be2320c5"
WS_ID = "24098a6dfa377ad0daa8e665"
ELEM_ID = "e3c89e99b01c0eb6fbfdc773"

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
    """OnshapeClient configured from env with either naming convention."""
    access_key = os.environ.get("ONSHAPE_ACCESS_KEY") or os.environ["ONSHAPE_API_KEY"]
    secret_key = os.environ.get("ONSHAPE_SECRET_KEY") or os.environ["ONSHAPE_API_SECRET"]
    creds = OnshapeCredentials(access_key=access_key, secret_key=secret_key)
    async with OnshapeClient(creds) as c:
        yield c


@pytest.mark.asyncio
async def test_export_part_studio_as_step_produces_valid_file(client, tmp_path):
    """End-to-end: start STEP translation, poll, download, validate bytes."""
    manager = ExportManager(client)

    result = await manager.export_part_studio_and_download(
        document_id=DOC_ID,
        workspace_id=WS_ID,
        element_id=ELEM_ID,
        format_name="STEP",
        timeout_seconds=120.0,
        poll_interval_seconds=1.0,
    )

    assert isinstance(result, TranslationResult)
    assert result.ok is True, (
        f"Expected ok=True, got state={result.state!r} "
        f"error={result.error_message!r}"
    )
    assert result.state == "DONE"
    assert result.format_name == "STEP"
    assert result.translation_id
    assert result.data is not None

    # STEP files are ISO-10303-21; the magic header is literally that string.
    assert result.data.startswith(b"ISO-10303-21"), (
        f"Bytes don't look like STEP. First 64 bytes: {result.data[:64]!r}"
    )
    # Smoke doc has actual geometry; a 1KB floor rules out an empty/error body.
    assert len(result.data) > 1024, (
        f"STEP payload too small ({len(result.data)} bytes) — probably not the real export"
    )

    # Verify the bytes also round-trip through disk (the MCP handler writes
    # them to /tmp/...; re-use the same flow here so the test doesn't need a
    # separate codepath to mirror the handler).
    out = tmp_path / (result.filename or "smoke-export.step")
    out.write_bytes(result.data)
    assert out.exists() and out.stat().st_size == len(result.data)
    with out.open("rb") as f:
        head = f.read(32)
    assert head.startswith(b"ISO-10303-21")
