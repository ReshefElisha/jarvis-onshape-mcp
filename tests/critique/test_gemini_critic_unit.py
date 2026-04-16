"""Unit tests for the Gemini critic that don't hit the real API."""

from __future__ import annotations

import pytest

from onshape_mcp.critique.gemini_critic import CritiqueResult, critique_render


@pytest.mark.asyncio
async def test_no_api_key_is_noop(monkeypatch):
    """When GEMINI_API_KEY is unset, critic must return matches_brief=None
    with a clear note — never a fabricated True/False."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = await critique_render(
        brief="any brief",
        images=[b"\x89PNG\r\n\x1a\n"],  # any bytes; critic returns before sending
        claimed_features=["any"],
        api_key=None,
    )
    assert isinstance(result, CritiqueResult)
    assert result.matches_brief is None
    assert "GEMINI_API_KEY" in result.notes
    assert result.missing == []
    assert result.wrong == []


@pytest.mark.asyncio
async def test_empty_images_is_noop(monkeypatch):
    """Empty image list short-circuits even when a key is set."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    result = await critique_render(
        brief="any brief",
        images=[],
        claimed_features=["any"],
    )
    assert result.matches_brief is None
    assert "no images" in result.notes.lower()
