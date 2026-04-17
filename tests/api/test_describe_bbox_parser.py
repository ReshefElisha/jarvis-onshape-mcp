"""Unit tests for the FS evBox3d response parser in describe.py.

Pure-shape tests: no Onshape required. Live response shape captured via
probe (see scratchpad/fs-failure-evidence.md / probe_bbox.py) and pinned
here so a future drift in Onshape's BTFSValueMap encoding fails loudly
in CI rather than silently rendering "bbox: unknown" in describe output.
"""

from __future__ import annotations

from onshape_mcp.api.describe import _parse_bbox_response


# Live response captured 2026-04-17 from FS get_bounding_box() against a
# 20x10x5 mm extruded plate. Trimmed to just the fields the parser reads.
LIVE_BBOX_RESPONSE = {
    "btType": "BTFeatureScriptEvalResponse-1859",
    "result": {
        "btType": "com.belmonttech.serialize.fsvalue.BTFSValueMap",
        "typeTag": "Box3d",
        "value": [
            {
                "btType": "BTFSValueMapEntry-2077",
                "key": {
                    "btType": "com.belmonttech.serialize.fsvalue.BTFSValueString",
                    "typeTag": "",
                    "value": "maxCorner",
                },
                "value": {
                    "btType": "com.belmonttech.serialize.fsvalue.BTFSValueArray",
                    "typeTag": "Vector",
                    "value": [
                        {"btType": "com.belmonttech.serialize.fsvalue.BTFSValueWithUnits",
                         "value": 0.02, "unitToPower": {"METER": 1}},
                        {"btType": "com.belmonttech.serialize.fsvalue.BTFSValueWithUnits",
                         "value": 0.01, "unitToPower": {"METER": 1}},
                        {"btType": "com.belmonttech.serialize.fsvalue.BTFSValueWithUnits",
                         "value": 0.005, "unitToPower": {"METER": 1}},
                    ],
                },
            },
            {
                "btType": "BTFSValueMapEntry-2077",
                "key": {
                    "btType": "com.belmonttech.serialize.fsvalue.BTFSValueString",
                    "typeTag": "",
                    "value": "minCorner",
                },
                "value": {
                    "btType": "com.belmonttech.serialize.fsvalue.BTFSValueArray",
                    "typeTag": "Vector",
                    "value": [
                        {"btType": "com.belmonttech.serialize.fsvalue.BTFSValueWithUnits",
                         "value": 0.0, "unitToPower": {"METER": 1}},
                        {"btType": "com.belmonttech.serialize.fsvalue.BTFSValueWithUnits",
                         "value": 0.0, "unitToPower": {"METER": 1}},
                        {"btType": "com.belmonttech.serialize.fsvalue.BTFSValueWithUnits",
                         "value": 0.0, "unitToPower": {"METER": 1}},
                    ],
                },
            },
        ],
    },
    "notices": [],
}


def test_parse_live_bbox_response_returns_meters():
    """The headline regression: the actual FS shape must round-trip to
    {minCorner: {x,y,z}, maxCorner: {x,y,z}} in meters. Before the fix
    the parser walked `result.message.value` and treated `value` as a
    dict, returning None on every healthy body."""
    out = _parse_bbox_response(LIVE_BBOX_RESPONSE)
    assert out is not None, (
        "parser returned None on the live response shape -- this is the "
        "exact regression that caused 'bbox: unknown' on healthy bodies"
    )
    assert out["minCorner"] == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert out["maxCorner"] == {"x": 0.02, "y": 0.01, "z": 0.005}


def test_parse_bbox_corner_order_doesnt_matter():
    """Onshape doesn't guarantee corner ordering in the entry list. Build a
    response with min before max and confirm the parser still finds both."""
    swapped = {
        "result": {
            "btType": "com.belmonttech.serialize.fsvalue.BTFSValueMap",
            "value": [
                LIVE_BBOX_RESPONSE["result"]["value"][1],  # minCorner first
                LIVE_BBOX_RESPONSE["result"]["value"][0],  # maxCorner second
            ],
        },
    }
    out = _parse_bbox_response(swapped)
    assert out is not None
    assert out["minCorner"] == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert out["maxCorner"] == {"x": 0.02, "y": 0.01, "z": 0.005}


def test_parse_bbox_returns_none_on_empty_response():
    assert _parse_bbox_response(None) is None
    assert _parse_bbox_response({}) is None
    assert _parse_bbox_response({"result": {}}) is None
    assert _parse_bbox_response({"result": {"value": []}}) is None


def test_parse_bbox_returns_none_when_only_one_corner_present():
    """Empty PartStudio path: evBox3d may return a single zero-corner or
    an unrecognized entry. Don't fabricate a bbox in that case."""
    only_max = {
        "result": {
            "value": [LIVE_BBOX_RESPONSE["result"]["value"][0]],  # maxCorner only
        },
    }
    assert _parse_bbox_response(only_max) is None


def test_parse_bbox_tolerates_unknown_extra_entries():
    """Future-proofing: if Onshape adds more keys to the Box3d map (e.g. a
    'centroid'), the parser should ignore unknowns and still return min/max."""
    with_extra = {
        "result": {
            "value": list(LIVE_BBOX_RESPONSE["result"]["value"]) + [
                {
                    "btType": "BTFSValueMapEntry-2077",
                    "key": {"value": "centroid"},
                    "value": {
                        "btType": "com.belmonttech.serialize.fsvalue.BTFSValueArray",
                        "value": [{"value": 0.01}, {"value": 0.005}, {"value": 0.0025}],
                    },
                },
            ],
        },
    }
    out = _parse_bbox_response(with_extra)
    assert out is not None
    assert out["maxCorner"] == {"x": 0.02, "y": 0.01, "z": 0.005}
