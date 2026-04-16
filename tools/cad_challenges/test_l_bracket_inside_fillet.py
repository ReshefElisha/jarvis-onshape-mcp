"""Self-test: L-bracket with an inside-corner fillet.

Brief:
    "L-shaped bracket. Start from a 60x40x10 mm plate. Cut away a 30x20 mm
    block from one corner so the result is L-shaped in plan view. Round the
    inside (concave) vertical edge with a 5 mm fillet."

Why this challenge:
    Exercises the failure-prone path: pick a body edge by deterministic id
    from list_entities and feed it to create_fillet. A wrong edge type
    (sketch curve, convex corner, horizontal edge) silently makes the fillet
    no-op or hit ERROR -- this is exactly the bug the smoke test originally
    found. The driver's feature_apply truth helper catches the ERROR; this
    self-test additionally proves we can pick the *right* edge.

Geometry:
    Base extrude (centered on Top plane): rect (-30,-20) -> (30,20), depth 10mm.
    Corner cut (sketched on top face at z=10): rect (-30,-20) -> (0,0),
        REMOVE through, oppositeDirection=True so it cuts DOWN into material.
    Inside vertical edge: a LINE running parallel to Z with midpoint
        approximately (0, 0, 5 mm). Fillet R=5mm on that edge.

Self-test criteria:
    1. Every feature returns OK.
    2. After the corner cut, exactly 1 vertical-axis LINE edge sits at
       midpoint ~ (0, 0, 5 mm) -- the concave inside corner. Picker resolves
       it deterministically (we abort the run if 0 or >1 candidates).
    3. After the fillet, exactly 1 cylindrical face of radius 5 mm exists
       (the fillet surface itself).
    4. Final body volume = base box - cut block + fillet add-back, within 1%.
       Predicted: 60*40*10 - 30*20*10 + (25 - pi*25/4)*10 mm^3 ~= 18054 mm^3.

Run:
    uv run python tools/cad_challenges/test_l_bracket_inside_fillet.py
"""

from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cad_driver import (  # noqa: E402
    CadTest,
    assert_state,
    build,
    inspect,
    run_cad_test,
)

# Reuse helpers from the first self-test. NB: deliberately NOT importing
# pillow_block's `mm()` converter -- the [units] WIP now treats bare numbers
# as millimeters (see onshape_mcp/builders/_units.py), so converting mm->in
# would *re-break* every dimension. All length args below are plain mm.
# (test_pillow_block.py still uses `mm()` and will fail volume asserts under
# the post-WIP units; flagged separately in the peer report.)
from test_pillow_block import (  # noqa: E402
    _top_face,
    require_cylinder_count,
    require_volume_near,
)


# ---- Edge picker -----------------------------------------------------------


def _vertical_line_edge_at_xy(
    ctx, *, x_mm: float, y_mm: float, tol_mm: float = 0.5
) -> str:
    """Find the unique LINE edge parallel to Z with midpoint at (x, y, *).

    Reads ctx._snapshot_cache so callers must follow it with an inspect/assert
    step. Raises if 0 or >1 candidates are found -- both are bugs we want loud.
    """
    snap = ctx._snapshot_cache
    if snap is None:
        raise RuntimeError(
            "_vertical_line_edge_at_xy requires a preceding inspect/assert step "
            "to populate the snapshot cache"
        )
    bodies = snap["raw"]["entities"].get("bodies") or []
    if not bodies:
        raise RuntimeError("_vertical_line_edge_at_xy: no bodies in snapshot")
    edges = bodies[0].get("edges") or []

    candidates = []
    for e in edges:
        if e.get("type") != "LINE":
            continue
        if e.get("direction_axis") not in ("+Z", "-Z"):
            continue
        mid = e.get("midpoint")
        if not mid or len(mid) < 3:
            continue
        if abs(mid[0] * 1000 - x_mm) > tol_mm or abs(mid[1] * 1000 - y_mm) > tol_mm:
            continue
        candidates.append(e)

    if not candidates:
        all_z_lines = [
            (e.get("id"),
             tuple(round(c * 1000, 2) for c in (e.get("midpoint") or [0, 0, 0])))
            for e in edges
            if e.get("type") == "LINE" and e.get("direction_axis") in ("+Z", "-Z")
        ]
        raise RuntimeError(
            f"no vertical LINE edge near (x={x_mm}, y={y_mm}) mm; "
            f"available vertical lines (id, midpoint mm): {all_z_lines}"
        )
    if len(candidates) > 1:
        ids = [(e.get("id"), e.get("midpoint")) for e in candidates]
        raise RuntimeError(
            f"ambiguous: {len(candidates)} vertical LINE edges near "
            f"(x={x_mm}, y={y_mm}) mm: {ids}"
        )
    return candidates[0]["id"]


# ---- Test ------------------------------------------------------------------


# Predicted final volume = base - cut + fillet correction.
# Fillet on a concave 90 inside corner adds material:
#   add = (R^2 - pi*R^2/4) * L
# For R = 5 mm, L = 10 mm: 25 * (1 - pi/4) * 10 ~= 53.65 mm^3.
PREDICTED_FINAL_MM3 = (
    60 * 40 * 10
    - 30 * 20 * 10
    + (5**2 - math.pi * 5**2 / 4) * 10
)


TEST = CadTest(
    name="l_bracket_inside_fillet",
    brief=(
        "L-shaped bracket: 60x40x10 mm plate, with a 30x20 mm corner removed "
        "from one corner; round the inside vertical edge with a 5 mm fillet."
    ),
    keep_doc=True,  # leave the doc so we can eyeball the inside fillet later
    steps=[
        # 1. Base 60x40x10 plate (all dims in mm, per new units convention)
        build("base_sketch", "create_sketch_rectangle", lambda ctx: {
            "name": "base sketch", "plane": "Top",
            "corner1": [-30, -20], "corner2": [30, 20],
        }),
        build("base_extrude", "create_extrude", lambda ctx: {
            "name": "base extrude",
            "sketchFeatureId": ctx.feature_ids["base sketch"],
            "depth": 10, "operationType": "NEW",
        }),
        assert_state("base volume", require_volume_near(60 * 40 * 10, tol_pct=0.5)),
        inspect("after_base"),

        # 2. Corner cut: rectangle (-30,-20) -> (0,0) on the +Z top face,
        #    REMOVE through with oppositeDirection so the cut goes DOWN.
        build("cut_sketch", "create_sketch_rectangle", lambda ctx: {
            "name": "corner cut sketch",
            "faceId": _top_face(ctx, z_mm=10.0),
            "corner1": [-30, -20], "corner2": [0, 0],
        }),
        build("cut_extrude", "create_extrude", lambda ctx: {
            "name": "corner cut",
            "sketchFeatureId": ctx.feature_ids["corner cut sketch"],
            "depth": 10, "operationType": "REMOVE",
            "oppositeDirection": True,
        }),
        assert_state(
            "L-shape volume",
            require_volume_near(60 * 40 * 10 - 30 * 20 * 10, tol_pct=0.5),
        ),
        inspect("after_cut"),

        # 3. Inside-corner fillet R=5 mm on the unique vertical edge at x=y=0.
        build("inside_fillet", "create_fillet", lambda ctx: {
            "name": "inside fillet",
            "radius": 5,
            "edgeIds": [_vertical_line_edge_at_xy(ctx, x_mm=0.0, y_mm=0.0)],
        }),
        assert_state("fillet radius", require_cylinder_count(1, 5.0, "inside fillet")),
        assert_state(
            "final volume",
            require_volume_near(PREDICTED_FINAL_MM3, tol_pct=0.5),
        ),
        inspect("final"),
    ],
)


if __name__ == "__main__":
    out_root = (
        Path(__file__).resolve().parents[2] / ".." / "scratchpad" / "cad-tests"
    ).resolve()
    report = asyncio.run(run_cad_test(TEST, out_root))
    print(report.summary())
    sys.exit(0 if report.ok else 1)
