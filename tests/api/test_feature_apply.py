"""Unit tests for update_feature_params_and_check.

apply_feature_and_check itself is covered end-to-end by
tests/real/test_feature_apply_real.py; these tests pin the
param-merge behavior of the update helper without hitting Onshape.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from onshape_mcp.api.feature_apply import (
    apply_feature_and_check,
    apply_assembly_feature_and_check,
    update_feature_params_and_check,
    rename_feature_and_check,
    batch_rename_features_and_check,
    FeatureApplyResult,
)


class TestApplyAssemblyFeatureAndCheck:
    """Pin the contract of the assembly-side wire-truth helper."""

    @pytest.mark.asyncio
    async def test_posts_to_assemblies_path(self, onshape_client):
        onshape_client.post = AsyncMock(return_value={
            "feature": {"featureId": "f1", "name": "MC", "featureType": "mateConnector"},
            "featureState": {"featureStatus": "OK"},
        })
        result = await apply_assembly_feature_and_check(
            onshape_client, "docA", "wsA", "asmA", {"feature": {}},
        )
        assert isinstance(result, FeatureApplyResult)
        assert result.ok is True
        assert result.status == "OK"
        assert result.feature_id == "f1"
        assert result.feature_type == "mateConnector"
        # Path targets the assemblies endpoint.
        posted_path = onshape_client.post.await_args[0][0]
        assert "/api/v9/assemblies/d/docA/w/wsA/e/asmA/features" in posted_path

    @pytest.mark.asyncio
    async def test_error_status_surfaces_as_ok_false(self, onshape_client):
        """Onshape-reported featureStatus=ERROR becomes ok=False with message."""
        onshape_client.post = AsyncMock(return_value={
            "feature": {"featureId": "badMate", "name": "m", "featureType": "mate"},
            "featureState": {
                "featureStatus": "ERROR",
                "message": "Solver rejected: over-constrained",
            },
        })
        result = await apply_assembly_feature_and_check(
            onshape_client, "d", "w", "e", {"feature": {}},
        )
        assert result.ok is False
        assert result.status == "ERROR"
        assert "over-constrained" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_update_operation_uses_featureid_path(self, onshape_client):
        onshape_client.post = AsyncMock(return_value={
            "feature": {"featureId": "fixed"},
            "featureState": {"featureStatus": "OK"},
        })
        await apply_assembly_feature_and_check(
            onshape_client, "d", "w", "e", {"feature": {}},
            operation="update", feature_id="fixed",
        )
        posted_path = onshape_client.post.await_args[0][0]
        assert posted_path.endswith("/features/featureid/fixed")

    @pytest.mark.asyncio
    async def test_update_without_feature_id_rejects(self, onshape_client):
        with pytest.raises(ValueError):
            await apply_assembly_feature_and_check(
                onshape_client, "d", "w", "e", {"feature": {}},
                operation="update",
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


@pytest.mark.asyncio
async def test_rename_feature_patches_name_and_reposts(onshape_client):
    """rename_feature_and_check should patch top-level `name`, not `parameters`."""
    onshape_client.get = AsyncMock(
        return_value={"features": [_extrude_feature(feature_id="fId")]}
    )
    onshape_client.post = AsyncMock(
        return_value={
            "feature": {"featureId": "fId", "name": "Boss extrude", "featureType": "extrude"},
            "featureState": {"featureStatus": "OK"},
        }
    )

    result = await rename_feature_and_check(
        onshape_client, "d", "w", "e", "fId", "Boss extrude",
    )

    assert isinstance(result, FeatureApplyResult)
    assert result.ok is True
    assert result.feature_name == "Boss extrude"

    posted_path = onshape_client.post.await_args[0][0]
    assert posted_path.endswith("/features/featureid/fId")

    sent_payload = onshape_client.post.await_args[1]["data"]
    assert sent_payload["feature"]["name"] == "Boss extrude"
    # Parameters must be untouched by a rename.
    assert sent_payload["feature"]["parameters"] == _extrude_feature(feature_id="fId")["parameters"]


@pytest.mark.asyncio
async def test_rename_feature_raises_for_unknown_feature(onshape_client):
    onshape_client.get = AsyncMock(return_value={"features": []})
    onshape_client.post = AsyncMock()
    with pytest.raises(ValueError) as exc:
        await rename_feature_and_check(onshape_client, "d", "w", "e", "missing", "New name")
    assert "not found" in str(exc.value)
    onshape_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_rename_feature_rejects_missing_feature_id(onshape_client):
    onshape_client.get = AsyncMock(return_value={"features": [_extrude_feature()]})
    onshape_client.post = AsyncMock()
    with pytest.raises(ValueError):
        await rename_feature_and_check(onshape_client, "d", "w", "e", "", "New name")
    onshape_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_rename_feature_reports_post_error_status(onshape_client):
    """A rename can still surface ERROR if the feature was already broken."""
    onshape_client.get = AsyncMock(
        return_value={"features": [_extrude_feature(feature_id="fId")]}
    )
    onshape_client.post = AsyncMock(
        return_value={
            "feature": {"featureId": "fId"},
            "featureState": {"featureStatus": "ERROR", "message": "Depth must be positive"},
        }
    )

    result = await rename_feature_and_check(onshape_client, "d", "w", "e", "fId", "New name")
    assert result.ok is False
    assert result.status == "ERROR"


class TestConcurrentWritesAreSerializedPerElement:
    """Regression coverage for a real incident: 20 `rename_feature` calls
    fired in parallel against one Part Studio raced on Onshape's server-side
    base-microversion regeneration and put 21/23 features into ERROR/WARNING,
    visibly collapsing the model (recovered via Onshape's version history).
    apply_feature_and_check now serializes its mutating POST per
    (document, workspace, element) so concurrent calls queue instead of
    racing Onshape's API directly.
    """

    @pytest.mark.asyncio
    async def test_same_element_writes_are_serialized(self, onshape_client):
        order = []

        async def fake_post(path, data=None, params=None):
            order.append("start")
            await asyncio.sleep(0.02)
            order.append("end")
            return {
                "feature": {"featureId": "f", "name": "x", "featureType": "extrude"},
                "featureState": {"featureStatus": "OK"},
            }

        onshape_client.post = fake_post

        await asyncio.gather(
            apply_feature_and_check(onshape_client, "d", "w", "e", {"feature": {}}),
            apply_feature_and_check(onshape_client, "d", "w", "e", {"feature": {}}),
        )

        # Serialized: the second POST can't start until the first fully ends.
        # A racy implementation would interleave as ["start", "start", "end", "end"].
        assert order == ["start", "end", "start", "end"]

    @pytest.mark.asyncio
    async def test_different_elements_are_not_serialized_against_each_other(
        self, onshape_client
    ):
        """The lock is per-element, not global -- unrelated Part Studios
        must not queue behind each other."""
        concurrent = 0
        max_concurrent = 0

        async def fake_post(path, data=None, params=None):
            nonlocal concurrent, max_concurrent
            concurrent += 1
            max_concurrent = max(max_concurrent, concurrent)
            await asyncio.sleep(0.02)
            concurrent -= 1
            return {
                "feature": {"featureId": "f", "name": "x", "featureType": "extrude"},
                "featureState": {"featureStatus": "OK"},
            }

        onshape_client.post = fake_post

        await asyncio.gather(
            apply_feature_and_check(onshape_client, "d", "w", "e1", {"feature": {}}),
            apply_feature_and_check(onshape_client, "d", "w", "e2", {"feature": {}}),
        )

        assert max_concurrent == 2

    @pytest.mark.asyncio
    async def test_assembly_writes_are_serialized_per_element_too(self, onshape_client):
        order = []

        async def fake_post(path, data=None, params=None):
            order.append("start")
            await asyncio.sleep(0.02)
            order.append("end")
            return {
                "feature": {"featureId": "f", "name": "x", "featureType": "mate"},
                "featureState": {"featureStatus": "OK"},
            }

        onshape_client.post = fake_post

        await asyncio.gather(
            apply_assembly_feature_and_check(onshape_client, "d", "w", "asm", {"feature": {}}),
            apply_assembly_feature_and_check(onshape_client, "d", "w", "asm", {"feature": {}}),
        )

        assert order == ["start", "end", "start", "end"]


def _risky_sketch_feature(feature_id: str = "riskyS") -> dict:
    """Shape lifted from knowledge_base/api/real_sketch_example.json: a
    non-default plane reference (would normally be a custom-feature-
    generated face) plus a constraint with an externalFirst ref."""
    return {
        "btType": "BTMSketch-151",
        "featureId": feature_id,
        "name": "Sketch 1",
        "parameters": [
            {
                "btType": "BTMParameterQueryList-148",
                "parameterId": "sketchPlane",
                "queries": [{"btType": "BTMIndividualQuery-138", "deterministicIds": ["KeKO"]}],
            }
        ],
        "entities": [],
        "constraints": [
            {
                "btType": "BTMSketchConstraint-2",
                "entityId": "c1",
                "constraintType": "DISTANCE",
                "parameters": [
                    {
                        "btType": "BTMParameterQueryList-148",
                        "parameterId": "externalFirst",
                        "queries": [{"btType": "BTMIndividualQuery-138", "deterministicIds": ["Kedg"]}],
                    },
                ],
            }
        ],
    }


def _safe_sketch_feature(feature_id: str = "safeS") -> dict:
    """Default plane, purely local constraints -- the Sketch 2 shape that
    renamed clean in the real incident."""
    return {
        "btType": "BTMSketch-151",
        "featureId": feature_id,
        "name": "Sketch 2",
        "parameters": [
            {
                "btType": "BTMParameterQueryList-148",
                "parameterId": "sketchPlane",
                "queries": [{"btType": "BTMIndividualQuery-138", "deterministicIds": ["JCC"]}],
            }
        ],
        "entities": [],
        "constraints": [
            {
                "btType": "BTMSketchConstraint-2",
                "entityId": "c1",
                "constraintType": "LENGTH",
                "parameters": [
                    {"btType": "BTMParameterString-149", "value": "e1.bottom", "parameterId": "localFirst"},
                ],
            }
        ],
    }


class TestRenameFeatureSafetyGate:
    """rename_feature_and_check must refuse a risky sketch by default,
    proceed with override_safety_check=True, and leave non-risky targets
    (safe sketches, non-sketch features) completely unaffected."""

    @pytest.mark.asyncio
    async def test_blocks_risky_sketch_without_override(self, onshape_client):
        onshape_client.get = AsyncMock(return_value={"features": [_risky_sketch_feature("s1")]})
        onshape_client.post = AsyncMock()

        result = await rename_feature_and_check(onshape_client, "d", "w", "e", "s1", "New name")

        assert result.ok is False
        assert result.status == "BLOCKED"
        assert "s1" in result.error_message or "New name" not in (result.error_message or "")
        onshape_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_proceeds_with_override_safety_check(self, onshape_client):
        onshape_client.get = AsyncMock(return_value={"features": [_risky_sketch_feature("s1")]})
        onshape_client.post = AsyncMock(return_value={
            "feature": {"featureId": "s1", "name": "New name", "featureType": "BTMSketch-151"},
            "featureState": {"featureStatus": "OK"},
        })

        result = await rename_feature_and_check(
            onshape_client, "d", "w", "e", "s1", "New name", override_safety_check=True,
        )

        assert result.ok is True
        assert result.status == "OK"
        onshape_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ignores_safe_sketch(self, onshape_client):
        onshape_client.get = AsyncMock(return_value={"features": [_safe_sketch_feature("s2")]})
        onshape_client.post = AsyncMock(return_value={
            "feature": {"featureId": "s2", "name": "New name", "featureType": "BTMSketch-151"},
            "featureState": {"featureStatus": "OK"},
        })

        result = await rename_feature_and_check(onshape_client, "d", "w", "e", "s2", "New name")

        assert result.ok is True
        onshape_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ignores_non_sketch_feature(self, onshape_client):
        """Regression check: a plain extrude must be unaffected by the gate."""
        onshape_client.get = AsyncMock(return_value={"features": [_extrude_feature(feature_id="fId")]})
        onshape_client.post = AsyncMock(return_value={
            "feature": {"featureId": "fId", "name": "New name", "featureType": "extrude"},
            "featureState": {"featureStatus": "OK"},
        })

        result = await rename_feature_and_check(onshape_client, "d", "w", "e", "fId", "New name")

        assert result.ok is True
        onshape_client.post.assert_awaited_once()


class TestUpdateFeatureSafetyGate:
    """Same gate, same contract, for update_feature_params_and_check."""

    @pytest.mark.asyncio
    async def test_blocks_risky_sketch_without_override(self, onshape_client):
        onshape_client.get = AsyncMock(return_value={"features": [_risky_sketch_feature("s1")]})
        onshape_client.post = AsyncMock()

        result = await update_feature_params_and_check(
            onshape_client, "d", "w", "e", "s1",
            [{"parameterId": "sketchPlane"}],
        )

        assert result.ok is False
        assert result.status == "BLOCKED"
        onshape_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_proceeds_with_override_safety_check(self, onshape_client):
        onshape_client.get = AsyncMock(return_value={"features": [_risky_sketch_feature("s1")]})
        onshape_client.post = AsyncMock(return_value={
            "feature": {"featureId": "s1", "name": "Sketch 1", "featureType": "BTMSketch-151"},
            "featureState": {"featureStatus": "OK"},
        })

        result = await update_feature_params_and_check(
            onshape_client, "d", "w", "e", "s1",
            [{"parameterId": "sketchPlane"}],
            override_safety_check=True,
        )

        assert result.ok is True
        onshape_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ignores_non_sketch_feature(self, onshape_client):
        """Regression check against the already-passing extrude-update tests."""
        onshape_client.get = AsyncMock(
            return_value={"features": [_extrude_feature(depth_expr="10 mm", depth_value=0.01)]}
        )
        onshape_client.post = AsyncMock(return_value={
            "feature": {"featureId": "fId", "name": "Extrude 10mm", "featureType": "extrude"},
            "featureState": {"featureStatus": "OK"},
        })

        result = await update_feature_params_and_check(
            onshape_client, "d", "w", "e", "fId",
            [{"parameterId": "depth", "expression": "15 mm"}],
        )

        assert result.ok is True
        onshape_client.post.assert_awaited_once()


class TestBatchRenameFeatures:
    @pytest.mark.asyncio
    async def test_sequential_order_not_parallel(self, onshape_client):
        """One shared GET up front, then each item's POST completes before
        the next begins (sequential, never overlapping)."""
        order = []

        async def fake_get(path, params=None):
            order.append("get-start")
            await asyncio.sleep(0.01)
            order.append("get-end")
            return {"features": [_safe_sketch_feature("s1"), _safe_sketch_feature("s2")]}

        async def fake_post(path, data=None, params=None):
            order.append("post-start")
            await asyncio.sleep(0.01)
            order.append("post-end")
            return {
                "feature": {"featureId": "x", "name": "x", "featureType": "BTMSketch-151"},
                "featureState": {"featureStatus": "OK"},
            }

        onshape_client.get = fake_get
        onshape_client.post = fake_post

        await batch_rename_features_and_check(
            onshape_client, "d", "w", "e",
            [{"featureId": "s1", "newName": "A"}, {"featureId": "s2", "newName": "B"}],
        )

        assert order == [
            "get-start", "get-end",
            "post-start", "post-end",
            "post-start", "post-end",
        ]

    @pytest.mark.asyncio
    async def test_fetches_features_only_once_for_whole_batch(self, onshape_client):
        """Regression guard for a real incident: per-item fetching sent ~8 MB
        through /partstudios/.../features for a 15-item batch and exhausted an
        Onshape-side quota (HTTP 429, throttled for hours). The batch must pay
        for exactly one GET no matter how many items it renames."""
        onshape_client.get = AsyncMock(return_value={
            "features": [_safe_sketch_feature(f"s{i}") for i in range(10)]
        })
        onshape_client.post = AsyncMock(return_value={
            "feature": {"featureId": "x", "name": "x", "featureType": "BTMSketch-151"},
            "featureState": {"featureStatus": "OK"},
        })

        results = await batch_rename_features_and_check(
            onshape_client, "d", "w", "e",
            [{"featureId": f"s{i}", "newName": f"N{i}"} for i in range(10)],
        )

        assert len(results) == 10
        assert all(r["ok"] for r in results)
        assert onshape_client.get.await_count == 1
        assert onshape_client.post.await_count == 10

    @pytest.mark.asyncio
    async def test_shared_features_doc_is_not_mutated_between_items(self, onshape_client):
        """Each item patches a COPY of its target, so a shared snapshot stays
        clean -- otherwise item N's rename would leak into the doc that items
        N+1.. are read from."""
        doc = {"features": [_safe_sketch_feature("s1"), _safe_sketch_feature("s2")]}
        original_names = [f["name"] for f in doc["features"]]

        onshape_client.get = AsyncMock(return_value=doc)
        posted_names = []

        async def fake_post(path, data=None, params=None):
            posted_names.append(data["feature"]["name"])
            return {
                "feature": {"featureId": "x", "name": "x", "featureType": "BTMSketch-151"},
                "featureState": {"featureStatus": "OK"},
            }

        onshape_client.post = fake_post

        await batch_rename_features_and_check(
            onshape_client, "d", "w", "e",
            [{"featureId": "s1", "newName": "Renamed A"}, {"featureId": "s2", "newName": "Renamed B"}],
        )

        # Each POST carried its own new name...
        assert posted_names == ["Renamed A", "Renamed B"]
        # ...and the shared snapshot still holds the pre-batch names.
        assert [f["name"] for f in doc["features"]] == original_names

    @pytest.mark.asyncio
    async def test_mixed_outcomes_reported_per_item(self, onshape_client):
        """One OK, one BLOCKED (risky sketch), one ERROR (Onshape-reported)."""
        onshape_client.get = AsyncMock(return_value={"features": [
            _safe_sketch_feature("ok1"),
            _risky_sketch_feature("blocked1"),
            _safe_sketch_feature("err1"),
        ]})
        # post is only called for ok1 and err1 -- blocked1 never reaches it.
        onshape_client.post = AsyncMock(side_effect=[
            {
                "feature": {"featureId": "ok1", "name": "x", "featureType": "BTMSketch-151"},
                "featureState": {"featureStatus": "OK"},
            },
            {
                "feature": {"featureId": "err1", "name": "x", "featureType": "BTMSketch-151"},
                "featureState": {"featureStatus": "ERROR", "message": "boom"},
            },
        ])

        results = await batch_rename_features_and_check(
            onshape_client, "d", "w", "e",
            [
                {"featureId": "ok1", "newName": "A"},
                {"featureId": "blocked1", "newName": "B"},
                {"featureId": "err1", "newName": "C"},
            ],
        )

        assert len(results) == 3
        assert results[0]["ok"] is True
        assert results[0]["status"] == "OK"
        assert results[1]["ok"] is False
        assert results[1]["status"] == "BLOCKED"
        assert results[2]["ok"] is False
        assert results[2]["status"] == "ERROR"

    @pytest.mark.asyncio
    async def test_bad_item_does_not_abort_the_batch(self, onshape_client):
        onshape_client.get = AsyncMock(return_value={"features": [_safe_sketch_feature("s1")]})
        onshape_client.post = AsyncMock(return_value={
            "feature": {"featureId": "s1", "name": "x", "featureType": "BTMSketch-151"},
            "featureState": {"featureStatus": "OK"},
        })

        results = await batch_rename_features_and_check(
            onshape_client, "d", "w", "e",
            [
                {"featureId": "", "newName": "A"},  # bad: empty featureId
                {"featureId": "s1", "newName": "B"},
            ],
        )

        assert len(results) == 2
        assert results[0]["ok"] is False
        assert results[0]["status"] == "ERROR"
        assert results[1]["ok"] is True

    @pytest.mark.asyncio
    async def test_override_safety_check_applies_to_whole_batch(self, onshape_client):
        onshape_client.get = AsyncMock(return_value={"features": [_risky_sketch_feature("s1")]})
        onshape_client.post = AsyncMock(return_value={
            "feature": {"featureId": "s1", "name": "x", "featureType": "BTMSketch-151"},
            "featureState": {"featureStatus": "OK"},
        })

        results = await batch_rename_features_and_check(
            onshape_client, "d", "w", "e",
            [{"featureId": "s1", "newName": "A"}],
            override_safety_check=True,
        )

        assert results[0]["ok"] is True
        onshape_client.post.assert_awaited_once()
