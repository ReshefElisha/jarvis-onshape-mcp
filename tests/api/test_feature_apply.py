"""Unit tests for update_feature_params_and_check.

apply_feature_and_check itself is covered end-to-end by
tests/real/test_feature_apply_real.py; these tests pin the
param-merge behavior of the update helper without hitting Onshape.
"""

from unittest.mock import AsyncMock

import pytest

from onshape_mcp.api.feature_apply import (
    update_feature_params_and_check,
    FeatureApplyResult,
)


def _extrude_feature(
    feature_id: str = "fId",
    depth_expr: str = "10 mm",
    depth_value: float = 0.01,
) -> dict:
    return {
        "featureId": feature_id,
        "name": "Extrude 10mm",
        "featureType": "extrude",
        "parameters": [
            {
                "btType": "BTMParameterQuantity-147",
                "parameterId": "depth",
                "expression": depth_expr,
                "value": depth_value,
                "units": "meter",
            },
            {
                "btType": "BTMParameterBoolean-144",
                "parameterId": "oppositeDirection",
                "value": False,
            },
            {
                "btType": "BTMParameterEnum-145",
                "parameterId": "operationType",
                "value": "NEW",
            },
        ],
    }


@pytest.mark.asyncio
async def test_update_merges_expression_and_clears_numeric(onshape_client):
    """Quantity update with only `expression` must zero stale numeric value."""
    onshape_client.get = AsyncMock(
        return_value={"features": [_extrude_feature(depth_expr="10 mm", depth_value=0.01)]}
    )
    onshape_client.post = AsyncMock(
        return_value={
            "feature": {"featureId": "fId", "name": "Extrude 10mm", "featureType": "extrude"},
            "featureState": {"featureStatus": "OK"},
        }
    )

    result = await update_feature_params_and_check(
        onshape_client, "d", "w", "e", "fId",
        [{"parameterId": "depth", "expression": "15 mm"}],
    )

    assert isinstance(result, FeatureApplyResult)
    assert result.ok is True
    sent_payload = onshape_client.post.await_args[1]["data"]
    depth_param = next(
        p for p in sent_payload["feature"]["parameters"]
        if p["parameterId"] == "depth"
    )
    assert depth_param["expression"] == "15 mm"
    # Stale numeric cleared so Onshape re-evaluates.
    assert depth_param["value"] == 0.0
    # Other params untouched.
    assert sent_payload["feature"]["parameters"][1]["value"] is False


@pytest.mark.asyncio
async def test_update_preserves_explicit_value(onshape_client):
    """If the caller passes `value` along with `expression`, keep both as given."""
    onshape_client.get = AsyncMock(
        return_value={"features": [_extrude_feature(depth_expr="10 mm", depth_value=0.01)]}
    )
    onshape_client.post = AsyncMock(
        return_value={
            "feature": {"featureId": "fId"},
            "featureState": {"featureStatus": "OK"},
        }
    )

    await update_feature_params_and_check(
        onshape_client, "d", "w", "e", "fId",
        [{"parameterId": "depth", "expression": "20 mm", "value": 0.02}],
    )
    sent = onshape_client.post.await_args[1]["data"]
    depth = next(p for p in sent["feature"]["parameters"] if p["parameterId"] == "depth")
    assert depth["expression"] == "20 mm"
    assert depth["value"] == 0.02


@pytest.mark.asyncio
async def test_update_boolean_and_enum(onshape_client):
    """Non-quantity updates write `value` straight through."""
    onshape_client.get = AsyncMock(
        return_value={"features": [_extrude_feature()]}
    )
    onshape_client.post = AsyncMock(
        return_value={
            "feature": {"featureId": "fId"},
            "featureState": {"featureStatus": "OK"},
        }
    )

    await update_feature_params_and_check(
        onshape_client, "d", "w", "e", "fId",
        [
            {"parameterId": "oppositeDirection", "value": True},
            {"parameterId": "operationType", "value": "ADD"},
        ],
    )
    sent = onshape_client.post.await_args[1]["data"]
    by_id = {p["parameterId"]: p for p in sent["feature"]["parameters"]}
    assert by_id["oppositeDirection"]["value"] is True
    assert by_id["operationType"]["value"] == "ADD"
    # depth expression left alone.
    assert by_id["depth"]["expression"] == "10 mm"


@pytest.mark.asyncio
async def test_update_hits_update_path(onshape_client):
    """POST must go to the featureid update path, not the list path."""
    onshape_client.get = AsyncMock(return_value={"features": [_extrude_feature()]})
    onshape_client.post = AsyncMock(
        return_value={
            "feature": {"featureId": "fId"},
            "featureState": {"featureStatus": "OK"},
        }
    )

    await update_feature_params_and_check(
        onshape_client, "d", "w", "e", "fId",
        [{"parameterId": "depth", "expression": "15 mm"}],
    )
    posted_path = onshape_client.post.await_args[0][0]
    assert posted_path.endswith("/features/featureid/fId")


@pytest.mark.asyncio
async def test_update_raises_for_unknown_feature(onshape_client):
    onshape_client.get = AsyncMock(return_value={"features": []})
    onshape_client.post = AsyncMock()
    with pytest.raises(ValueError) as exc:
        await update_feature_params_and_check(
            onshape_client, "d", "w", "e", "missing",
            [{"parameterId": "depth", "expression": "15 mm"}],
        )
    assert "not found" in str(exc.value)
    onshape_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_update_raises_for_unknown_parameter(onshape_client):
    """parameterId that doesn't exist on the feature is a driver error."""
    onshape_client.get = AsyncMock(return_value={"features": [_extrude_feature()]})
    onshape_client.post = AsyncMock()
    with pytest.raises(ValueError) as exc:
        await update_feature_params_and_check(
            onshape_client, "d", "w", "e", "fId",
            [{"parameterId": "nope", "expression": "15 mm"}],
        )
    assert "nope" in str(exc.value)
    onshape_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_update_rejects_missing_fields(onshape_client):
    onshape_client.get = AsyncMock(return_value={"features": [_extrude_feature()]})
    onshape_client.post = AsyncMock()

    with pytest.raises(ValueError):
        await update_feature_params_and_check(
            onshape_client, "d", "w", "e", "fId", [{"expression": "15 mm"}],
        )
    with pytest.raises(ValueError):
        await update_feature_params_and_check(
            onshape_client, "d", "w", "e", "fId", [],
        )
    with pytest.raises(ValueError):
        await update_feature_params_and_check(
            onshape_client, "d", "w", "e", "", [{"parameterId": "depth"}],
        )
    onshape_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_update_reports_post_error_status(onshape_client):
    """If the post-patch featureStatus is ERROR, ok=False bubbles through."""
    onshape_client.get = AsyncMock(return_value={"features": [_extrude_feature()]})
    onshape_client.post = AsyncMock(
        return_value={
            "feature": {"featureId": "fId"},
            "featureState": {
                "featureStatus": "ERROR",
                "message": "Depth must be positive",
            },
        }
    )

    result = await update_feature_params_and_check(
        onshape_client, "d", "w", "e", "fId",
        [{"parameterId": "depth", "expression": "-15 mm"}],
    )
    assert result.ok is False
    assert result.status == "ERROR"
    assert "positive" in (result.error_message or "")
