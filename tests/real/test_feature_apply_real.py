"""Real-API test for `apply_feature_and_check`.

Creates a deliberately-broken fillet (same failure mode as the smoke test:
filleting a sketch-curve id instead of a body edge) against the reserved
smoke-test document. Asserts the helper surfaces `status=="ERROR"` with a
populated `error_message`, not the silent "success" the starter tools produce
today.

Skipped automatically when `ONSHAPE_ACCESS_KEY` is not set in the environment,
so this file is inert in the default CI / `pytest` run.

Evidence: /Users/shef/projects/onshape-mcp/scratchpad/smoke-test.md
"""

from __future__ import annotations

import os

import pytest

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.feature_apply import (
    FeatureApplyResult,
    apply_feature_and_check,
)

# Reserved smoke-test document in Shef's Onshape account.
DOC_ID = "c287a50857bf10a5be2320c5"
WS_ID = "24098a6dfa377ad0daa8e665"
ELEM_ID = "e3c89e99b01c0eb6fbfdc773"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (os.getenv("ONSHAPE_ACCESS_KEY") and os.getenv("ONSHAPE_SECRET_KEY")),
        reason="Requires ONSHAPE_ACCESS_KEY/ONSHAPE_SECRET_KEY in env",
    ),
]


def _broken_fillet_payload(bad_entity_id: str, name: str) -> dict:
    """A fillet feature whose entity query points at a non-edge id.

    Matches the shape the existing `FilletBuilder` emits; keeping the test
    independent of that builder so it still exercises the helper if the builder
    changes.
    """
    return {
        "feature": {
            "btType": "BTMFeature-134",
            "featureType": "fillet",
            "name": name,
            "suppressed": False,
            "namespace": "",
            "parameters": [
                {
                    "btType": "BTMParameterQueryList-148",
                    "parameterId": "entities",
                    "queries": [
                        {
                            "btType": "BTMIndividualQuery-138",
                            "deterministicIds": [bad_entity_id],
                        }
                    ],
                },
                {
                    "btType": "BTMParameterQuantity-147",
                    "parameterId": "radius",
                    "isInteger": False,
                    "value": 0.002,
                    "units": "meter",
                    "expression": "2 mm",
                },
            ],
        }
    }


@pytest.fixture
async def client():
    creds = OnshapeCredentials(
        access_key=os.environ["ONSHAPE_ACCESS_KEY"],
        secret_key=os.environ["ONSHAPE_SECRET_KEY"],
    )
    async with OnshapeClient(creds) as c:
        yield c


async def _delete_feature(client: OnshapeClient, feature_id: str) -> None:
    path = (
        f"/api/v9/partstudios/d/{DOC_ID}/w/{WS_ID}/e/{ELEM_ID}"
        f"/features/featureid/{feature_id}"
    )
    try:
        await client.delete(path)
    except Exception:  # noqa: BLE001
        # Best-effort cleanup — if Onshape already refused the feature or
        # something else removed it, that's fine.
        pass


@pytest.mark.asyncio
async def test_broken_fillet_returns_error_status(client):
    """A fillet on a non-edge id must surface as status=ERROR, not silent success."""
    # "JCB" is the id that failed the original smoke run: a sketch-curve id
    # from qEverything(EntityType.EDGE), which also returns sketch geometry.
    payload = _broken_fillet_payload("JCB", "feature_apply_test_broken_fillet")

    result = await apply_feature_and_check(
        client, DOC_ID, WS_ID, ELEM_ID, payload, operation="create"
    )

    try:
        assert isinstance(result, FeatureApplyResult)
        assert result.status == "ERROR", (
            f"Expected ERROR from Onshape, got {result.status}. "
            f"raw featureState: {result.raw.get('featureState')!r}"
        )
        assert result.ok is False
        assert result.feature_id and result.feature_id != "unknown", (
            "feature_id should be the real id from response['feature']['featureId']"
        )
        assert result.feature_name == "feature_apply_test_broken_fillet"
        assert result.feature_type == "fillet"
        assert result.error_message, (
            "error_message must be populated on ERROR "
            "(via message, feedback, or raw state dump)"
        )
    finally:
        if result.feature_id:
            await _delete_feature(client, result.feature_id)


@pytest.mark.asyncio
async def test_update_requires_feature_id(client):
    """operation='update' without feature_id must raise ValueError locally — no HTTP."""
    with pytest.raises(ValueError):
        await apply_feature_and_check(
            client, DOC_ID, WS_ID, ELEM_ID, {"feature": {}}, operation="update"
        )
