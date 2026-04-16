"""Second-pair-of-eyes critic for rendered CAD.

Claude's own visual reasoning missed a non-trivial number of build defects
during dogfood (the lead logged 4 no-op cuts even with the iso render in
hand). Gemini's image understanding is stronger on this class of task, so
every time we claim a feature built we route the render through Gemini
first and surface disagreements before the tool layer reports success.

Design:
    critique_render(brief, images, claimed_features) -> CritiqueResult

    brief              natural-language description of what the build should be
    images             one or more PNG bytes (iso + top etc.)
    claimed_features   checklist of features the caller says landed

    CritiqueResult has matches_brief (nullable), missing, wrong, notes.
    matches_brief is None when the critic can't run — e.g. no GEMINI_API_KEY
    — so callers distinguish "critic disagrees" from "critic wasn't available".

No-op when GEMINI_API_KEY is absent, so test suites and local runs without
the credential still pass cleanly. Real calls hit `gemini-2.5-pro` with
`response_schema` structured output so we parse JSON, never free text.
"""

from __future__ import annotations

import os
from typing import List, Optional

from loguru import logger
from pydantic import BaseModel, Field


DEFAULT_MODEL = "gemini-2.5-pro"


class CritiqueResult(BaseModel):
    """Structured verdict from a render review.

    `matches_brief` is None when the critic couldn't run (missing API key,
    network failure, or schema parse failure). Callers should treat None as
    "no signal" rather than "pass" — don't silently claim success.
    """

    matches_brief: Optional[bool] = None
    missing: List[str] = Field(default_factory=list)
    wrong: List[str] = Field(default_factory=list)
    notes: str = ""


# ---- Internal schema the model returns ------------------------------------

class _GeminiVerdict(BaseModel):
    """Shape the model returns. Kept separate from CritiqueResult so we can
    change the wire schema without breaking callers."""

    matches_brief: bool
    missing: List[str] = Field(default_factory=list)
    wrong: List[str] = Field(default_factory=list)
    notes: str = ""


_SYSTEM_INSTRUCTION = (
    "You are an experienced mechanical-CAD reviewer. You are given: (1) a "
    "natural-language brief describing what the part should be, (2) a list "
    "of features the author claims were built, and (3) one or more rendered "
    "images of the part. Your job is to decide whether the render actually "
    "matches the brief. Be strict — missing holes, wrong counts, wrong "
    "orientations, and no-op cuts that failed to remove material are the "
    "common failures.\n\n"
    "Return a structured verdict:\n"
    "- matches_brief: true only if every feature in the brief is visibly "
    "present in the render. When in doubt, return false.\n"
    "- missing: short phrases describing features the brief asks for that "
    "you do not see in the render (e.g. '4 mounting holes', 'chamfer on "
    "top edge').\n"
    "- wrong: short phrases describing features that are present but do "
    "not match (e.g. 'hole placed at center, brief asks for corners').\n"
    "- notes: one or two sentences summarising your reasoning. Keep it "
    "concise — the caller is an LLM, not a human reader."
)


def _build_user_prompt(brief: str, claimed_features: List[str]) -> str:
    features_block = (
        "\n".join(f"- {f}" for f in claimed_features)
        if claimed_features
        else "(none listed)"
    )
    return (
        f"BRIEF:\n{brief.strip()}\n\n"
        f"CLAIMED FEATURES:\n{features_block}\n\n"
        "Review the attached render(s) and return your verdict."
    )


async def critique_render(
    brief: str,
    images: List[bytes],
    claimed_features: List[str],
    *,
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
) -> CritiqueResult:
    """Ask Gemini to judge whether `images` match `brief` + `claimed_features`.

    Args:
        brief: natural-language description of what the part should be
        images: one or more PNG bytes — iso + top + front etc.
        claimed_features: checklist the caller believes landed, for Gemini
            to cross-check against what it actually sees
        model: Gemini model id (default: gemini-2.5-pro)
        api_key: explicit key; falls back to GEMINI_API_KEY env var. When
            neither is set, the critic is a no-op.

    Returns:
        CritiqueResult with matches_brief / missing / wrong / notes, or a
        no-op result (matches_brief=None) when the critic can't run.
    """

    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        logger.info("GEMINI_API_KEY not set — critique_render is a no-op")
        return CritiqueResult(
            matches_brief=None,
            notes="no GEMINI_API_KEY set — critic skipped",
        )

    if not images:
        return CritiqueResult(
            matches_brief=None,
            notes="no images provided — critic skipped",
        )

    # Import inside the function so the module is importable without the
    # google-genai SDK installed (the no-op path above still works).
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        logger.warning(f"google-genai not available: {e}")
        return CritiqueResult(
            matches_brief=None,
            notes=f"google-genai not installed: {e}",
        )

    parts = [types.Part.from_bytes(data=png, mime_type="image/png") for png in images]
    parts.append(types.Part.from_text(text=_build_user_prompt(brief, claimed_features)))

    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=_GeminiVerdict,
        temperature=0.0,
    )

    client = genai.Client(api_key=key)

    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=parts)],
            config=config,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Gemini call failed: {type(e).__name__}: {e}")
        return CritiqueResult(
            matches_brief=None,
            notes=f"gemini call failed: {type(e).__name__}: {e}",
        )

    text = getattr(response, "text", None)
    if not text:
        return CritiqueResult(
            matches_brief=None,
            notes="gemini returned empty response",
        )

    try:
        verdict = _GeminiVerdict.model_validate_json(text)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Gemini response didn't match schema: {e}; raw={text[:400]!r}")
        return CritiqueResult(
            matches_brief=None,
            notes=f"gemini response schema mismatch: {e}",
        )

    return CritiqueResult(
        matches_brief=verdict.matches_brief,
        missing=verdict.missing,
        wrong=verdict.wrong,
        notes=verdict.notes,
    )
