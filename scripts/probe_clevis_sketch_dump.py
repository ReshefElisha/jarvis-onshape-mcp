"""Dump the raw BTMSketch-151 JSON shape of every constraint type in a
live reference sketch (Shef's clevis by default).

Output: scratchpad/sketch-constraint-payloads.md beside this repo's
scratchpad — one canonical JSON example per constraintType, plus a
TL;DR of wire-format patterns. Used once to hydrate the constraint
serializer design; keep it in scripts/ so the same probe can be
re-run against any other sketch by swapping DOC_ID / ELEM_ID /
SKETCH_NAME.

Complement: probe_sketch_constraint_fixtures.py, which builds a part
studio exercising the constraint types a reference sketch happens not
to use.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials
from onshape_mcp.api.documents import DocumentManager

# Shef's clevis reference sketch — constraint-rich, hand-built in the UI.
DOC_ID = os.environ.get("PROBE_DOC_ID", "31cc3095d494cf79317a0075")
ELEM_ID = os.environ.get("PROBE_ELEM_ID", "321fc180d13c1dfe6b98d601")
SKETCH_NAME = os.environ.get("PROBE_SKETCH_NAME", "Sketch 1")

OUT_MD = Path(__file__).parent.parent / "scratchpad" / "sketch-constraint-payloads.md"


async def main() -> None:
    ak = os.environ.get("ONSHAPE_ACCESS_KEY") or os.environ["ONSHAPE_API_KEY"]
    sk = os.environ.get("ONSHAPE_SECRET_KEY") or os.environ["ONSHAPE_API_SECRET"]
    async with OnshapeClient(OnshapeCredentials(access_key=ak, secret_key=sk)) as c:
        dm = DocumentManager(c)
        summary = await dm.get_document_summary(DOC_ID)
        ws = summary["workspaces"][0]
        ws_id = ws.id
        print(f"ws={ws_id}")

        # Raw GET /features — constraints come back as flat dicts
        # (no {btType, message} envelope) under features[].constraints.
        path = f"/api/v9/partstudios/d/{DOC_ID}/w/{ws_id}/e/{ELEM_ID}/features"
        resp = await c.get(path)
        features = resp.get("features", [])
        print(f"features={len(features)}")

        def _msg(f: dict) -> dict:
            return f.get("message", f)

        target = None
        for f in features:
            if _msg(f).get("name") == SKETCH_NAME:
                target = f
                break
        if target is None:
            for f in features:
                m = _msg(f)
                if m.get("btType") == "BTMSketch-151" or m.get("featureType") == "newSketch":
                    target = f
                    print(f"FALLBACK: using sketch {m.get('name')!r}")
                    break
        if target is None:
            raise SystemExit(f"no sketch found; saw {[_msg(f).get('name') for f in features]}")

        sketch_msg = _msg(target)
        entities = sketch_msg.get("entities", [])
        constraints = sketch_msg.get("constraints", [])
        print(f"entities={len(entities)} constraints={len(constraints)}")

        # Group by constraintType, first-seen-wins canonical example.
        by_type: "OrderedDict[str, list[dict]]" = OrderedDict()
        for con in constraints:
            cmsg = con.get("message", con)
            ctype = cmsg.get("constraintType", "UNKNOWN")
            by_type.setdefault(ctype, []).append(con)

        # One sample entity per unique geometry btType — the constraint
        # params reference entityIds; readers often want the entity shape
        # too (especially for sub-point refs like "<id>.start").
        sample_entities: "OrderedDict[str, dict]" = OrderedDict()
        for e in entities:
            emsg = e.get("message", e)
            geom = emsg.get("geometry") or {}
            gmsg = geom.get("message", geom)
            key = gmsg.get("btType", "BTMSketchCurveSegment-155")
            sample_entities.setdefault(key, e)

        entity_ref_types = [
            "HORIZONTAL", "VERTICAL", "COINCIDENT", "TANGENT", "CONCENTRIC",
            "PARALLEL", "PERPENDICULAR", "EQUAL", "POINT_ON", "MIDPOINT",
        ]
        dimension_types = [
            "DIAMETER", "RADIUS", "DISTANCE",
            "HORIZONTAL_DISTANCE", "VERTICAL_DISTANCE", "ANGLE",
        ]
        binary_pair_types = ["OFFSET"]

        lines: list[str] = []
        lines.append("# BTMSketch-151 raw constraint payloads — sketch probe")
        lines.append("")
        lines.append(
            f"Source: doc `{DOC_ID}` / ws `{ws_id}` / partstudio `{ELEM_ID}` / "
            f"sketch `{sketch_msg.get('name')}` "
            f"({len(entities)} entities, {len(constraints)} constraints).\n"
        )
        lines.append(
            "Probed via raw `GET /api/v9/partstudios/.../features`. "
            "**Constraints are FLAT objects** at this endpoint (just "
            "`{btType: \"BTMSketchConstraint-2\", constraintType: ..., "
            "parameters: [...], ...}`) — no outer `{btType, message}` "
            "envelope. Entity IDs referenced in parameters are the same "
            "deterministic strings Onshape assigns at sketch creation.\n"
        )

        lines.append(f"## Constraint types present: {len(by_type)}")
        lines.append("")
        for t, lst in by_type.items():
            lines.append(f"- **{t}** ×{len(lst)}")
        lines.append("")

        def dump(name: str, bucket: list[str]) -> None:
            lines.append(f"## {name}")
            lines.append("")
            for ct in bucket:
                lines.append(f"### {ct}")
                lines.append("")
                if ct not in by_type:
                    lines.append(
                        "_Not present in this sketch — **need separate probe "
                        "(see probe_sketch_constraint_fixtures.py)**._"
                    )
                    lines.append("")
                    continue
                ex = by_type[ct][0]
                lines.append(f"Count in sketch: {len(by_type[ct])}")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(ex, indent=2))
                lines.append("```")
                lines.append("")

        dump("Entity-ref constraints", entity_ref_types)
        dump("Dimensioned constraints", dimension_types)
        dump("Binary-pair constraints", binary_pair_types)

        known = set(entity_ref_types + dimension_types + binary_pair_types)
        extras = [t for t in by_type if t not in known]
        if extras:
            lines.append("## Extras present in sketch but not on standard list")
            lines.append("")
            for ct in extras:
                lines.append(f"### {ct}")
                lines.append("")
                lines.append(f"Count: {len(by_type[ct])}")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(by_type[ct][0], indent=2))
                lines.append("```")
                lines.append("")

        lines.append("## Sample entities (for sub-point id reference)")
        lines.append("")
        for key, e in sample_entities.items():
            lines.append(f"### {key}")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(e, indent=2))
            lines.append("```")
            lines.append("")

        OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        OUT_MD.write_text("\n".join(lines))
        print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    asyncio.run(main())
