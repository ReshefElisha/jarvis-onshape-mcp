"""Probe the exact shape of Onshape's native plane feature.

Offsets from Front / Top / Right datum planes and from a picked face.

Usage:
    DID=<docId> WID=<wsId> EID=<psId> FID=<faceIdOptional> \\
        uv run python scripts/probe_offset_plane.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.feature_apply import apply_feature_and_check
from onshape_mcp.api.partstudio import PartStudioManager


def offset_plane_payload(ref_query: dict, offset_m: float, offset_expr: str,
                         flip: bool, name: str) -> dict:
    return {
        "feature": {
            "btType": "BTMFeature-134",
            "featureType": "cPlane",
            "name": name,
            "suppressed": False,
            "namespace": "",
            "parameters": [
                {
                    "btType": "BTMParameterEnum-145",
                    "namespace": "",
                    "enumName": "CPlaneType",
                    "value": "OFFSET",
                    "parameterId": "cplaneType",
                    "parameterName": "",
                    "libraryRelationType": "NONE",
                },
                {
                    "btType": "BTMParameterQueryList-148",
                    "queries": [ref_query],
                    "parameterId": "entities",
                    "parameterName": "",
                    "libraryRelationType": "NONE",
                },
                {
                    "btType": "BTMParameterQuantity-147",
                    "isInteger": False,
                    "value": offset_m,
                    "units": "",
                    "expression": offset_expr,
                    "parameterId": "offset",
                    "parameterName": "",
                    "libraryRelationType": "NONE",
                },
                {
                    "btType": "BTMParameterBoolean-144",
                    "value": flip,
                    "parameterId": "oppositeDirection",
                    "parameterName": "",
                    "libraryRelationType": "NONE",
                },
            ],
        },
    }


async def main() -> None:
    did = os.environ["DID"]
    wid = os.environ["WID"]
    eid = os.environ["EID"]
    fid = os.environ.get("FID")

    ak = os.getenv("ONSHAPE_API_KEY") or os.getenv("ONSHAPE_ACCESS_KEY", "")
    sk = os.getenv("ONSHAPE_API_SECRET") or os.getenv("ONSHAPE_SECRET_KEY", "")
    client = OnshapeClient(OnshapeCredentials(access_key=ak, secret_key=sk))

    ps = PartStudioManager(client)

    try:
        # Trial 1: offset from the Top datum plane by 2.5 mm
        top_plane_id = await ps.get_plane_id(did, wid, eid, "Top")
        print(f"Top plane id: {top_plane_id}")

        ref_q = {
            "btType": "BTMIndividualQuery-138",
            "deterministicIds": [top_plane_id],
        }
        payload = offset_plane_payload(
            ref_q, 0.0025, "2.5 mm", flip=False, name="OffsetFromTop"
        )
        print("\npayload:")
        print(json.dumps(payload, indent=2)[:1000])
        r = await apply_feature_and_check(
            client, did, wid, eid, payload,
        )
        print(f"\nstatus={r.status} id={r.feature_id} err={r.error_message}")
        if r.ok:
            feats = await client.get(
                f"/api/v9/partstudios/d/{did}/w/{wid}/e/{eid}/features"
            )
            for f in feats.get("features", []):
                if f.get("featureId") == r.feature_id:
                    print("\npersisted shape:")
                    print(json.dumps(f, indent=2, default=str)[:2500])
                    break

        # Trial 2: offset from a face
        if fid:
            print("\n\n--- trial 2: offset from face ---")
            ref_q2 = {
                "btType": "BTMIndividualQuery-138",
                "deterministicIds": [fid],
            }
            payload2 = offset_plane_payload(
                ref_q2, 0.005, "5 mm", flip=False, name="OffsetFromFace"
            )
            r2 = await apply_feature_and_check(
                client, did, wid, eid, payload2,
            )
            print(f"status={r2.status} id={r2.feature_id} err={r2.error_message}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
