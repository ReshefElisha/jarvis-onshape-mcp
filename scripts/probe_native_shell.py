"""Probe the exact shape of Onshape's native shell feature.

Reuses an existing throwaway doc/box. Posts a native BTMFeature-134 with
featureType="shell", varying the parameter shape until Onshape accepts it.
Dumps what went in, what came back, and the persisted feature shape.

Usage:
    DID=<docId> WID=<wsId> EID=<psId> FID=<faceId> \\
        uv run python scripts/probe_native_shell.py
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


def shell_payload(face_id: str, thickness_m: float, thickness_expr: str,
                  opposite: bool, name: str = "Probe Shell") -> dict:
    return {
        "feature": {
            "btType": "BTMFeature-134",
            "featureType": "shell",
            "name": name,
            "suppressed": False,
            "namespace": "",
            "parameters": [
                {
                    "btType": "BTMParameterQueryList-148",
                    "queries": [
                        {
                            "btType": "BTMIndividualQuery-138",
                            "deterministicIds": [face_id],
                        }
                    ],
                    "parameterId": "entities",
                    "parameterName": "",
                    "libraryRelationType": "NONE",
                },
                {
                    "btType": "BTMParameterQuantity-147",
                    "isInteger": False,
                    "value": thickness_m,
                    "units": "",
                    "expression": thickness_expr,
                    "parameterId": "thickness",
                    "parameterName": "",
                    "libraryRelationType": "NONE",
                },
                {
                    "btType": "BTMParameterBoolean-144",
                    "value": opposite,
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
    fid = os.environ["FID"]

    ak = os.getenv("ONSHAPE_API_KEY") or os.getenv("ONSHAPE_ACCESS_KEY", "")
    sk = os.getenv("ONSHAPE_API_SECRET") or os.getenv("ONSHAPE_SECRET_KEY", "")
    client = OnshapeClient(OnshapeCredentials(access_key=ak, secret_key=sk))

    try:
        for label, thickness_m, thickness_expr, opposite in [
            ("inward-natural", 0.0015, "1.5 mm", False),
        ]:
            print(f"\n--- trial {label} ---")
            payload = shell_payload(fid, thickness_m, thickness_expr, opposite, name=f"Shell {label}")
            print("payload:")
            print(json.dumps(payload, indent=2)[:800])
            r = await apply_feature_and_check(
                client, did, wid, eid, payload, track_changes=True,
            )
            print(f"\nstatus={r.status} id={r.feature_id}")
            print(f"error_message={r.error_message}")
            if r.changes:
                print(f"changes={json.dumps(r.changes, indent=2, default=str)[:400]}")
            if r.ok:
                feats = await client.get(
                    f"/api/v9/partstudios/d/{did}/w/{wid}/e/{eid}/features"
                )
                for f in feats.get("features", []):
                    if f.get("featureId") == r.feature_id:
                        print("\npersisted feature shape:")
                        print(json.dumps(f, indent=2, default=str))
                        break
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
