"""Self-test: L-bracket with an inside-corner fillet.

Brief:
    "L-bracket: two perpendicular flat plates joined along one edge.
    Each plate 40x40 mm, 5 mm thick. Inside crease has a 5 mm fillet."

(Earlier revision of this file built a notched flat plate -- L in plan
view -- which was geometry-equivalent to the same fillet pick but isn't
what an L-bracket is. The corrected geometry is an L cross-section
extruded perpendicular to give two plates joined at a 90 deg crease,
matching the kind of part you'd actually call an L-bracket.)

Why this challenge:
    Exercises the failure-prone path: pick a body edge by deterministic
    id from list_entities and feed it to create_fillet. A wrong edge
    type (sketch curve, convex corner, edge in the wrong plane) silently
    makes the fillet no-op or hit ERROR -- the bug the smoke test
    originally caught. The driver's feature_apply truth helper catches
    the ERROR; this self-test additionally proves we can pick the *right*
    edge: the inside crease where the two plates meet.

Construction (Front plane sketches, extrude in +Y):
    Sketch the horizontal plate cross-section first: rectangle in Front
    coords (X, Z) from (0, 0) to (40, 5). Extrude 40 mm in +Y so the
    horizontal plate occupies x=0..40, y=0..40, z=0..5.

    Add the vertical plate: sketch in Front coords from (35, 0) to
    (40, 40), extrude 40 mm in +Y with ADD. Final solid:
        - horizontal arm: x=0..40, y=0..40, z=0..5  (40x40 plate, 5 thick)
        - vertical arm:   x=35..40, y=0..40, z=0..40 (40x40 plate, 5 thick)

    The two plates share the corner block (x=35..40, y=0..40, z=0..5).
    The inside crease edge runs along Y at (x=35, z=5) -- the concave
    line you'd round with an inside fillet.

Self-test criteria:
    1. Every feature returns OK.
    2. The inside crease picker finds exactly one Y-axis LINE edge with
       midpoint near (35, 20, 5) mm. 0 or >1 candidates is a hard error.
    3. After the fillet, exactly 1 cylindrical face of radius 5 mm
       exists (the fillet surface itself).
    4. Final volume within 0.5%% of:
           area_L_section * depth + fillet_addback
       where area_L_section = 40*5 + 35*5 = 375 mm^2 (two plates minus
       the corner block which we count once), depth = 40 mm, and
       fillet_addback = (R^2 - pi*R^2/4) * depth ~= 214.6 mm^3 for
       R=5 mm. Predicted ~= 15214.6 mm^3.

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
# as millimeters in builders/_units.py, so calling mm() (mm->in convert) on
# top of that re-shrinks every dimension by 25.4. All length args below are
# plain mm.
from test_pillow_block import (  # noqa: E402
    require_cylinder_count,
    require_volume_near,
)


# ---- Edge picker -----------------------------------------------------------


def _y_line_edge_at_xz(
    ctx, *, x_mm: float, z_mm: float, tol_mm: float = 0.5
) -> str:
    """Find the unique LINE edge parallel to Y with midpoint at (x, *, z).

    For the L-bracket built below, the inside crease runs along the Y axis
    at (x=35 mm, z=5 mm); this picker resolves to that edge. Reads
    ctx._snapshot_cache so callers must follow with an inspect/assert step
    that refreshes the snapshot. Raises if 0 or >1 candidates.
    """
    snap = ctx._snapshot_cache
    if snap is None:
        raise RuntimeError(
            "_y_line_edge_at_xz requires a preceding inspect/assert step "
            "to populate the snapshot cache"
        )
    bodies = snap["raw"]["entities"].get("bodies") or []
    if not bodies:
        raise RuntimeError("_y_line_edge_at_xz: no bodies in snapshot")
    edges = bodies[0].get("edges") or []

    candidates = []
    for e in edges:
        if e.get("type") != "LINE":
            continue
        if e.get("direction_axis") not in ("+Y", "-Y"):
            continue
        mid = e.get("midpoint")
        if not mid or len(mid) < 3:
            continue
        if abs(mid[0] * 1000 - x_mm) > tol_mm or abs(mid[2] * 1000 - z_mm) > tol_mm:
            continue
        candidates.append(e)

    if not candidates:
        all_y_lines = [
            (e.get("id"),
             tuple(round(c * 1000, 2) for c in (e.get("midpoint") or [0, 0, 0])))
            for e in edges
            if e.get("type") == "LINE" and e.get("direction_axis") in ("+Y", "-Y")
        ]
        raise RuntimeError(
            f"no Y-axis LINE edge near (x={x_mm}, z={z_mm}) mm; "
            f"available Y lines (id, midpoint mm): {all_y_lines}"
        )
    if len(candidates) > 1:
        ids = [(e.get("id"), e.get("midpoint")) for e in candidates]
        raise RuntimeError(
            f"ambiguous: {len(candidates)} Y-axis LINE edges near "
            f"(x={x_mm}, z={z_mm}) mm: {ids}"
        )
    return candidates[0]["id"]


# ---- Test ------------------------------------------------------------------


# L cross-section area = horizontal plate (40x5) + vertical plate above the
# corner block (5x35) = 200 + 175 = 375 mm^2. Depth = 40 mm. Inside fillet
# adds (R^2 - pi*R^2/4)*depth in the concave corner.
PREDICTED_FINAL_MM3 = (
    375 * 40
    + (5**2 - math.pi * 5**2 / 4) * 40
)


TEST = CadTest(
    name="l_bracket_inside_fillet",
    brief=(
        "L-bracket: two perpendicular 40x40 mm plates, 5 mm thick, joined "
        "along one edge to form an L cross-section extruded 40 mm deep. "
        "Round the inside crease with a 5 mm fillet."
    ),
    keep_doc=True,
    steps=[
        # 1. Horizontal plate. Sketch its cross-section on Front plane:
        #    a 40 wide x 5 tall rectangle in Front coords (X, Z).
        build("base_sketch", "create_sketch_rectangle", lambda ctx: {
            "name": "horizontal plate sketch", "plane": "Front",
            "corner1": [0, 0], "corner2": [40, 5],
        }),
        build("base_extrude", "create_extrude", lambda ctx: {
            "name": "horizontal plate",
            "sketchFeatureId": ctx.feature_ids["horizontal plate sketch"],
            "depth": 40, "operationType": "NEW",
        }),
        assert_state(
            "horizontal plate volume",
            require_volume_near(40 * 5 * 40, tol_pct=0.5),
        ),
        inspect("after_horizontal_plate"),

        # 2. Vertical plate. Sketch its cross-section on the same Front plane:
        #    a 5 wide x 40 tall rectangle from (35, 0) to (40, 40), so it
        #    overlaps the horizontal plate's corner block (x=35..40, z=0..5)
        #    and rises up to z=40. Extrude with ADD to fuse.
        build("riser_sketch", "create_sketch_rectangle", lambda ctx: {
            "name": "vertical plate sketch", "plane": "Front",
            "corner1": [35, 0], "corner2": [40, 40],
        }),
        build("riser_extrude", "create_extrude", lambda ctx: {
            "name": "vertical plate",
            "sketchFeatureId": ctx.feature_ids["vertical plate sketch"],
            "depth": 40, "operationType": "ADD",
        }),
        assert_state(
            "L-section volume",
            require_volume_near(375 * 40, tol_pct=0.5),
        ),
        inspect("after_l_join"),

        # 3. Inside fillet R=5 mm on the unique Y-axis LINE edge at the
        #    crease (x=35, z=5).
        build("inside_fillet", "create_fillet", lambda ctx: {
            "name": "inside fillet",
            "radius": 5,
            "edgeIds": [_y_line_edge_at_xz(ctx, x_mm=35.0, z_mm=5.0)],
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
