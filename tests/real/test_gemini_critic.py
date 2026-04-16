"""Real-API test for the Gemini critic.

Uses the motor-mount v1 / v2 renders captured during the lead's dogfood
run (scratchpad/dogfood-renders{,-v2}/motor-mount-*.png):

    v1 (WRONG)  - iso + top renders missing the 4 corner mounting holes
    v2 (CORRECT) - same part with all 4 corner holes present

Asserts:
    v1 render + brief claiming 4 mounting holes  -> matches_brief == False
                                                    and `missing` names the holes
    v2 render + same brief                       -> matches_brief == True

Auto-skipped when GEMINI_API_KEY is absent so `pytest tests/` stays clean.
Also skipped when the dogfood fixture files aren't present (different
checkouts may not have them).

Evidence & context for the fixtures: scratchpad/dogfood-findings.md
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from onshape_mcp.critique.gemini_critic import CritiqueResult, critique_render


BRIEF = (
    "Motor mount. 60x40mm base plate, 6mm thick. Cylindrical boss 20mm "
    "diameter, 8mm tall, centered. 5mm through-hole down the center for "
    "motor shaft. Four 3mm mounting holes in the corners, 6mm from each "
    "edge."
)
CLAIMED_FEATURES = [
    "60x40mm base plate, 6mm thick",
    "20mm-diameter boss, 8mm tall, centered",
    "5mm through-hole for motor shaft (centered)",
    "4 mounting holes (3mm) in the corners",
]

PROJECT_ROOT = Path("/Users/shef/projects/onshape-mcp")
V1_DIR = PROJECT_ROOT / "scratchpad" / "dogfood-renders"
V2_DIR = PROJECT_ROOT / "scratchpad" / "dogfood-renders-v2"
V1_PATHS = [V1_DIR / "motor-mount-iso.png", V1_DIR / "motor-mount-top.png"]
V2_PATHS = [V2_DIR / "motor-mount-v2-iso.png", V2_DIR / "motor-mount-v2-top.png"]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("GEMINI_API_KEY"),
        reason="Requires GEMINI_API_KEY in env",
    ),
    pytest.mark.skipif(
        not all(p.exists() for p in V1_PATHS + V2_PATHS),
        reason=(
            "Motor-mount dogfood fixtures missing from scratchpad/dogfood-renders*/"
        ),
    ),
]


def _load(paths: list[Path]) -> list[bytes]:
    return [p.read_bytes() for p in paths]


@pytest.mark.asyncio
async def test_v1_flags_missing_mounting_holes():
    """v1 renders show boss + shaft only — critic must not claim success."""
    result: CritiqueResult = await critique_render(
        brief=BRIEF,
        images=_load(V1_PATHS),
        claimed_features=CLAIMED_FEATURES,
    )

    # If the API key was set but the call failed for any reason the helper
    # returns matches_brief=None rather than a bogus True/False. That's
    # "no signal", not a test failure; retry-later-is-fine.
    if result.matches_brief is None:
        pytest.skip(f"critic returned no signal: {result.notes}")

    assert result.matches_brief is False, (
        f"v1 render is missing 4 mounting holes but critic approved it. "
        f"notes={result.notes!r} missing={result.missing!r} wrong={result.wrong!r}"
    )
    assert result.missing, "critic said matches_brief=False but listed nothing in missing"

    joined = " ".join(result.missing).lower()
    assert ("mounting" in joined) or ("corner" in joined) or ("hole" in joined), (
        f"expected missing list to mention mounting/corner/hole, got {result.missing!r}"
    )


@pytest.mark.asyncio
async def test_v2_approves_corrected_mount():
    """v2 renders show all 4 corner holes — critic should approve."""
    result: CritiqueResult = await critique_render(
        brief=BRIEF,
        images=_load(V2_PATHS),
        claimed_features=CLAIMED_FEATURES,
    )

    if result.matches_brief is None:
        pytest.skip(f"critic returned no signal: {result.notes}")

    assert result.matches_brief is True, (
        f"v2 render has all 4 corner holes + boss + shaft but critic still "
        f"disapproved. notes={result.notes!r} "
        f"missing={result.missing!r} wrong={result.wrong!r}"
    )


