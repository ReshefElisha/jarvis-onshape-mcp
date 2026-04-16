"""Self-test: linear pattern of through-holes.

STATUS 2026-04-16: **currently FAILING against real Onshape.** The seed
hole builds cleanly; `create_linear_pattern` then returns
`featureStatus: ERROR` from Onshape. Root cause traced to
`builders/pattern.py:_build_direction_query`, which emits
`qCreatedBy(makeId("RIGHT"), EntityType.EDGE)` — Onshape's default
feature ids in a Part Studio are capital-initial ("Origin", "Top",
"Front", "Right"), and even with the right casing a datum plane has
no EDGE entities to pattern along. The existing `tests/builders/test_pattern.py`
mock-tests assert this same wrong shape, so the bug never surfaced
until a real-API call hit it.

This test stays committed as a regression marker — it will start
passing once `_build_direction_query` references one of the Origin
feature's axes (e.g. `qNthElement(qCreatedBy(makeId("Origin"),
EntityType.EDGE), 0)` for X) or accepts a caller-supplied edge id.
No code changes here when that lands.

Brief:
    "80x40x5 mm plate. Cut one ø6 mm through-hole near one short edge,
    then linear-pattern it 4x along the long edge with 20 mm spacing so
    the plate has 4 holes evenly spaced down its length."

Why this challenge:
    `create_linear_pattern` is wired but never end-to-end-tested against
    the live API alongside the rest of the new stack. This catches:
        - whether `featureIds` of a REMOVE extrude correctly patterns the
          *operation* (4 holes), not 4 new cylinder bodies
        - whether the post-pattern entity surface exposes 4 cylindrical
          faces of the seed radius (the contract list_entities promises)
        - whether default direction X + distance "20 mm" lays the holes
          along the expected axis

Geometry:
    Base extrude: rect (-40, -20) -> (40, 20) on Top, depth 5 mm.
    Seed cut:     ø6 mm circle at (-30, 0) on the +Z top face,
                  REMOVE depth 5, oppositeDirection=True.
    Pattern:      featureIds=[seed_cut], distance=20 mm, count=4, direction=X.
                  Resulting hole centers: x = -30, -10, 10, 30; y = 0.

Self-test criteria:
    1. All features OK.
    2. After the seed cut: exactly 1 cylinder of radius 3 mm.
    3. After the pattern: exactly 4 cylinders of radius 3 mm.
    4. Final volume within 1% of 80*40*5 - 4 * pi * 3^2 * 5 ~= 15435 mm^3.

Run:
    uv run python tools/cad_challenges/test_linear_pattern_holes.py
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
from test_pillow_block import (  # noqa: E402  -- units convention: bare numbers = mm
    _top_face,
    require_cylinder_count,
    require_volume_near,
)


PREDICTED_FINAL_MM3 = 80 * 40 * 5 - 4 * math.pi * 3**2 * 5


TEST = CadTest(
    name="linear_pattern_holes",
    brief=(
        "80x40x5 mm plate with 4 ø6 mm through-holes evenly spaced 20 mm "
        "apart along the long axis (X), centered on the short axis."
    ),
    keep_doc=True,
    steps=[
        # 1. Base plate
        build("base_sketch", "create_sketch_rectangle", lambda ctx: {
            "name": "base sketch", "plane": "Top",
            "corner1": [-40, -20], "corner2": [40, 20],
        }),
        build("base_extrude", "create_extrude", lambda ctx: {
            "name": "base extrude",
            "sketchFeatureId": ctx.feature_ids["base sketch"],
            "depth": 5, "operationType": "NEW",
        }),
        assert_state("base volume", require_volume_near(80 * 40 * 5, tol_pct=0.5)),
        inspect("after_base"),

        # 2. Seed hole at (-30, 0) — far enough from the +X edge that the
        #    final pattern lands cleanly inside the plate.
        build("hole_sketch", "create_sketch_circle", lambda ctx: {
            "name": "seed hole sketch",
            "faceId": _top_face(ctx, z_mm=5.0),
            "center": [-30, 0], "radius": 3,
        }),
        build("hole_cut", "create_extrude", lambda ctx: {
            "name": "seed hole cut",
            "sketchFeatureId": ctx.feature_ids["seed hole sketch"],
            "depth": 5, "operationType": "REMOVE",
            "oppositeDirection": True,
        }),
        assert_state("seed hole present", require_cylinder_count(1, 3.0, "seed hole")),
        inspect("after_seed_cut"),

        # 3. Linear pattern x4 along +X with 20 mm spacing.
        build("pattern", "create_linear_pattern", lambda ctx: {
            "name": "hole pattern",
            "featureIds": [ctx.feature_ids["seed hole cut"]],
            "distance": 20,
            "count": 4,
            "direction": "X",
        }),
        assert_state(
            "four-hole row",
            require_cylinder_count(4, 3.0, "patterned holes"),
        ),
        assert_state(
            "final volume",
            require_volume_near(PREDICTED_FINAL_MM3, tol_pct=1.0),
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
