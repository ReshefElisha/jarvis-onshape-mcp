"""Build single-purpose fixture sketches to capture constraint-type wire
shapes that a reference sketch (e.g. the clevis) may not include.

Companion to probe_clevis_sketch_dump.py. Each fixture is ONE sketch
with ONE constraint (on the minimum geometry it needs) so a 400 is
always attributable to the specific shape under test, not to a
neighbor. Output is APPENDED to the same scratchpad md the clevis
probe writes.

Triage notes baked into the fixture list:

- `HORIZONTAL_DISTANCE` / `VERTICAL_DISTANCE` are NOT distinct
  constraintTypes — they are `DISTANCE` with a `direction`
  BTMParameterEnum-145 (`DimensionDirection`: `HORIZONTAL` |
  `VERTICAL`). Only the direction=VERTICAL variant is probed here
  since the clevis covers HORIZONTAL.
- `POINT_ON` is NOT distinct either — it's `COINCIDENT` where
  `localFirst` is a point sub-ref (`<entity>.start` / `.end` /
  `.center`) and `localSecond` is a curve id. Covered by clevis's
  COINCIDENT examples; no dedicated fixture here.
- `HORIZONTAL` on a POINT (e.g. circle `.center`) DOES need
  `externalSecond` (a QueryList targeting origin id `IB`). On a LINE,
  `externalSecond` is optional — the `fx_HORIZONTAL_no_external`
  fixture below proves that Onshape accepts and persists the 1-param
  form verbatim, without backfill.

Cleans up the auto-doc on exit.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import httpx
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import DocumentManager
from onshape_mcp.api.partstudio import PartStudioManager

OUT_MD = Path(__file__).parent.parent / "scratchpad" / "sketch-constraint-payloads.md"


# ---------- Minimal BTMSketch-151 builders -------------------------------


def _line(entity_id: str, p0: Tuple[float, float], p1: Tuple[float, float]) -> Dict[str, Any]:
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    length = math.hypot(dx, dy)
    return {
        "btType": "BTMSketchCurveSegment-155",
        "entityId": entity_id,
        "startPointId": f"{entity_id}.start",
        "endPointId": f"{entity_id}.end",
        "startParam": 0.0,
        "endParam": length,
        "geometry": {
            "btType": "BTCurveGeometryLine-117",
            "pntX": p0[0], "pntY": p0[1],
            "dirX": dx / length if length else 1.0,
            "dirY": dy / length if length else 0.0,
        },
        "isConstruction": False,
    }


def _circle(entity_id: str, center: Tuple[float, float], radius: float) -> Dict[str, Any]:
    return {
        "btType": "BTMSketchCurveSegment-155",
        "entityId": entity_id,
        "startPointId": f"{entity_id}.start",
        "endPointId": f"{entity_id}.end",
        "startParam": 0.0,
        "endParam": 2 * math.pi,
        "geometry": {
            "btType": "BTCurveGeometryCircle-115",
            "radius": radius,
            "xCenter": center[0], "yCenter": center[1],
            "xDir": 1.0, "yDir": 0.0, "clockwise": False,
        },
        "centerId": f"{entity_id}.center",
        "isConstruction": False,
    }


def _param_str(parameter_id: str, value: str) -> Dict[str, Any]:
    return {"btType": "BTMParameterString-149", "value": value, "parameterId": parameter_id}


def _param_qty(parameter_id: str, expression: str) -> Dict[str, Any]:
    return {
        "btType": "BTMParameterQuantity-147",
        "isInteger": False, "value": 0.0, "units": "",
        "expression": expression, "parameterId": parameter_id,
    }


def _param_enum(parameter_id: str, enum_name: str, value: str) -> Dict[str, Any]:
    return {
        "btType": "BTMParameterEnum-145", "namespace": "",
        "enumName": enum_name, "value": value, "parameterId": parameter_id,
    }


def _constraint(ctype: str, eid: str, params: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "btType": "BTMSketchConstraint-2",
        "constraintType": ctype,
        "entityId": eid,
        "parameters": params,
    }


def _sketch_feature(name: str, plane_id: str, entities: List[Dict[str, Any]],
                    constraints: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "feature": {
            "btType": "BTMSketch-151",
            "featureType": "newSketch",
            "name": name,
            "suppressed": False,
            "parameters": [{
                "btType": "BTMParameterQueryList-148",
                "queries": [{
                    "btType": "BTMIndividualQuery-138",
                    "deterministicIds": [plane_id],
                }],
                "parameterId": "sketchPlane",
            }],
            "entities": entities,
            "constraints": constraints,
        }
    }


# ---------- Fixtures -----------------------------------------------------


FIXTURES: List[Tuple[str, Callable[[], Tuple[List[Dict], List[Dict]]]]] = [
    ("fx_VERTICAL_line", lambda: (
        [_line("v_a", (0.05, 0.00), (0.05, 0.03))],
        [_constraint("VERTICAL", "v_c", [_param_str("localFirst", "v_a")])],
    )),
    ("fx_PARALLEL", lambda: (
        [
            _line("p_a", (0.00, 0.00), (0.04, 0.00)),
            _line("p_b", (0.00, 0.02), (0.04, 0.02)),
        ],
        [_constraint("PARALLEL", "p_c", [
            _param_str("localFirst", "p_a"),
            _param_str("localSecond", "p_b"),
        ])],
    )),
    ("fx_PERPENDICULAR", lambda: (
        [
            _line("pp_a", (0.00, 0.00), (0.04, 0.00)),
            _line("pp_b", (0.04, 0.00), (0.04, 0.03)),
        ],
        [_constraint("PERPENDICULAR", "pp_c", [
            _param_str("localFirst", "pp_a"),
            _param_str("localSecond", "pp_b"),
        ])],
    )),
    ("fx_EQUAL_lines", lambda: (
        [
            _line("eq_a", (0.00, 0.00), (0.03, 0.00)),
            _line("eq_b", (0.00, 0.02), (0.03, 0.02)),
        ],
        [_constraint("EQUAL", "eq_c", [
            _param_str("localFirst", "eq_a"),
            _param_str("localSecond", "eq_b"),
        ])],
    )),
    ("fx_EQUAL_circles", lambda: (
        [
            _circle("eqc_a", (0.00, 0.00), 0.005),
            _circle("eqc_b", (0.02, 0.00), 0.005),
        ],
        [_constraint("EQUAL", "eqc_c", [
            _param_str("localFirst", "eqc_a"),
            _param_str("localSecond", "eqc_b"),
        ])],
    )),
    ("fx_MIDPOINT", lambda: (
        # mp_b.start placed exactly at midpoint of mp_a so the solver is
        # happy. (Still returns WARNING if DOF is over-constrained, but
        # the constraint shape is persisted either way.)
        [
            _line("mp_a", (0.00, 0.00), (0.04, 0.00)),
            _line("mp_b", (0.02, 0.00), (0.02, 0.03)),
        ],
        [_constraint("MIDPOINT", "mp_c", [
            _param_str("localFirst", "mp_b.start"),
            _param_str("localSecond", "mp_a"),
        ])],
    )),
    ("fx_DISTANCE_vertical", lambda: (
        [
            _line("dv_a", (0.00, 0.00), (0.04, 0.00)),
            _line("dv_b", (0.00, 0.03), (0.04, 0.03)),
        ],
        [_constraint("DISTANCE", "dv_c", [
            _param_str("localFirst", "dv_a.start"),
            _param_str("localSecond", "dv_b.start"),
            _param_enum("direction", "DimensionDirection", "VERTICAL"),
            _param_qty("length", "30 mm"),
            _param_enum("alignment", "DimensionAlignment", "ALIGNED"),
        ])],
    )),
    ("fx_ANGLE", lambda: (
        [
            _line("ang_a", (0.00, 0.00), (0.04, 0.00)),
            _line("ang_b", (0.00, 0.00), (0.04, 0.04 * math.tan(math.radians(30)))),
        ],
        [_constraint("ANGLE", "ang_c", [
            _param_str("localFirst", "ang_a"),
            _param_str("localSecond", "ang_b"),
            _param_qty("angle", "30 deg"),
        ])],
    )),
    ("fx_HORIZONTAL_no_external", lambda: (
        [_line("hx_a", (0.00, 0.00), (0.04, 0.00))],
        [_constraint("HORIZONTAL", "hx_c", [_param_str("localFirst", "hx_a")])],
    )),
]


async def _apply_raw(client: OnshapeClient, doc_id: str, ws_id: str, elem: str,
                     feature_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a raw feature payload; return {ok, status, error, feature_id}.

    Captures the 400 response body so a malformed fixture surfaces a
    diagnosable Onshape message rather than a bare HTTPStatusError.
    """
    path = f"/api/v9/partstudios/d/{doc_id}/w/{ws_id}/e/{elem}/features"
    try:
        resp = await client.post(path, data=feature_payload)
        fs = (resp.get("featureState") or {}).get("featureStatus")
        feat = resp.get("feature") or {}
        return {
            "ok": fs == "OK",
            "status": fs or "UNKNOWN",
            "feature_id": feat.get("featureId"),
            "error": None,
        }
    except httpx.HTTPStatusError as e:
        try:
            body = e.response.json()
        except Exception:
            body = e.response.text
        return {
            "ok": False,
            "status": f"HTTP_{e.response.status_code}",
            "feature_id": None,
            "error": body,
        }


async def main() -> None:
    ak = os.environ.get("ONSHAPE_ACCESS_KEY") or os.environ["ONSHAPE_API_KEY"]
    sk = os.environ.get("ONSHAPE_SECRET_KEY") or os.environ["ONSHAPE_API_SECRET"]
    async with OnshapeClient(OnshapeCredentials(access_key=ak, secret_key=sk)) as c:
        dm = DocumentManager(c)
        ps = PartStudioManager(c)

        doc = await dm.create_document(name="mcp-sketch-constraint-fixture (auto)")
        print(f"doc={doc.id}")
        outcome: List[Dict[str, Any]] = []
        try:
            summary = await dm.get_document_summary(doc.id)
            ws = summary["workspaces"][0]
            elem = (await ps.create_part_studio(doc.id, ws.id, "fixtures"))["id"]
            top = await ps.get_plane_id(doc.id, ws.id, elem, "Top")

            for fname, builder in FIXTURES:
                entities, constraints = builder()
                feature = _sketch_feature(fname, top, entities, constraints)
                res = await _apply_raw(c, doc.id, ws.id, elem, feature)
                res["name"] = fname
                outcome.append(res)
                err_tail = f" err={str(res['error'])[:120]}" if res["error"] else ""
                print(f"  {fname}: status={res['status']} ok={res['ok']}{err_tail}")

            # Pull back the persisted sketches so we see the on-wire JSON
            # Onshape actually stored (incl. any backfill).
            path = f"/api/v9/partstudios/d/{doc.id}/w/{ws.id}/e/{elem}/features"
            resp = await c.get(path)
            sketches_by_name: Dict[str, Dict[str, Any]] = {}
            for f in resp.get("features", []):
                m = f.get("message", f)
                if m.get("btType") == "BTMSketch-151":
                    sketches_by_name[m.get("name") or ""] = m

            lines = [
                "",
                "---",
                "",
                "## Fixture probe — previously-missing constraint types",
                "",
                f"Source: fresh auto-doc `{doc.id}` (deleted after probe). "
                "Each constraint in its own sketch feature for isolation.",
                "",
                "**Key findings from fixture triage:**",
                "",
                "- `HORIZONTAL_DISTANCE` and `VERTICAL_DISTANCE` are **NOT** "
                "distinct constraintTypes. Both are `DISTANCE` with a "
                "`direction` BTMParameterEnum-145 (`DimensionDirection`: "
                "`HORIZONTAL` | `VERTICAL`).",
                "- `POINT_ON` is **NOT** a distinct constraintType either. "
                "It's `COINCIDENT` where `localFirst` is a point sub-ref "
                "(`<entity>.start` / `.end` / `.center`) and `localSecond` "
                "is a curve entity id.",
                "- `HORIZONTAL` / `VERTICAL` on a LINE do NOT require "
                "`externalSecond`. On a POINT sub-ref they DO (see clevis "
                "example referencing origin id `IB`).",
                "",
                "Per-fixture apply status:",
                "",
            ]
            for r in outcome:
                err_note = ""
                if r.get("error"):
                    body = r["error"]
                    if isinstance(body, dict):
                        msg = body.get("message") or body.get("error") or str(body)[:200]
                    else:
                        msg = str(body)[:200]
                    err_note = f" — `{msg}`"
                lines.append(
                    f"- **{r['name']}** — status `{r['status']}`, ok={r['ok']}{err_note}"
                )
            lines.append("")

            order = [
                ("fx_VERTICAL_line", "VERTICAL"),
                ("fx_PARALLEL", "PARALLEL"),
                ("fx_PERPENDICULAR", "PERPENDICULAR"),
                ("fx_EQUAL_lines", "EQUAL (on lines)"),
                ("fx_EQUAL_circles", "EQUAL (on circles)"),
                ("fx_MIDPOINT", "MIDPOINT"),
                ("fx_DISTANCE_vertical", "DISTANCE (direction=VERTICAL)"),
                ("fx_ANGLE", "ANGLE"),
            ]
            for fname, title in order:
                lines.append(f"### {title}")
                lines.append("")
                sk = sketches_by_name.get(fname)
                if sk is None:
                    lines.append(
                        f"_Sketch never created — fixture `{fname}` failed to apply; "
                        "see status table above for the Onshape error body._"
                    )
                    lines.append("")
                    continue
                target_ctype = title.split()[0].split("(")[0].strip()
                candidates = [
                    c for c in (sk.get("constraints") or [])
                    if c.get("constraintType") == target_ctype
                ]
                if not candidates:
                    lines.append(
                        f"_Sketch was applied but the `{target_ctype}` constraint was "
                        "not persisted — Onshape may have dropped or rewrote it._"
                    )
                    lines.append("")
                    continue
                lines.append("```json")
                lines.append(json.dumps(candidates[0], indent=2))
                lines.append("```")
                lines.append("")

            lines.append("### HORIZONTAL without externalSecond — backfill test")
            lines.append("")
            fh = next((r for r in outcome if r["name"] == "fx_HORIZONTAL_no_external"), None)
            lines.append(f"Apply status: `{fh['status']}` (ok={fh['ok']})")
            lines.append("")
            sk_fh = sketches_by_name.get("fx_HORIZONTAL_no_external")
            if sk_fh is None:
                lines.append("_Sketch was rejected outright; externalSecond IS required._")
            else:
                horiz = next(
                    (c for c in (sk_fh.get("constraints") or [])
                     if c.get("constraintType") == "HORIZONTAL"),
                    None,
                )
                if horiz is None:
                    lines.append("_Sketch applied but Onshape dropped the HORIZONTAL._")
                else:
                    param_ids = [p.get("parameterId") for p in horiz.get("parameters", [])]
                    lines.append(f"Stored parameterIds: `{param_ids}`")
                    lines.append("")
                    if "externalSecond" in param_ids:
                        lines.append(
                            "**externalSecond was BACKFILLED** — Onshape inserted it "
                            "despite our omission. Safe to omit at author time."
                        )
                    else:
                        lines.append(
                            "**externalSecond NOT present** — Onshape accepted the "
                            "1-param HORIZONTAL on a line as-is. `externalSecond` "
                            "is therefore **not required** when HORIZONTAL targets "
                            "a line entity."
                        )
                    lines.append("")
                    lines.append("Stored constraint JSON:")
                    lines.append("")
                    lines.append("```json")
                    lines.append(json.dumps(horiz, indent=2))
                    lines.append("```")

            OUT_MD.parent.mkdir(parents=True, exist_ok=True)
            with OUT_MD.open("a") as f:
                f.write("\n".join(lines) + "\n")
            print(f"appended to {OUT_MD}")

        finally:
            try:
                await dm.delete_document(doc.id)
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 403:
                    raise


if __name__ == "__main__":
    asyncio.run(main())
