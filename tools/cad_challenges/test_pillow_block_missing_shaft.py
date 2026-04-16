"""NEGATIVE self-test: pillow block with the shaft hole step deliberately omitted.

This is a **harness** test, not a CAD test. It exists to answer: "if a future
driver regression made assertion failures invisible, would we notice?"
We reuse `test_pillow_block.py`'s brief + helpers verbatim but skip the two
build steps that cut the ø8 shaft. The shaft-hole assertion stays in place,
so the driver should halt **at** that assertion with an error that names the
missing cylinder.

Pass condition for this file's `__main__`:
    - report.ok is False (driver did NOT silently claim success)
    - the first failing step is the shaft-hole assertion
    - the error message mentions "radius 4.0mm" and "found 0"

Run:
    uv run python tools/cad_challenges/test_pillow_block_missing_shaft.py
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

# Reuse everything from the passing self-test so the two tests can't drift
# apart on unit conventions or helper behavior. If test_pillow_block.py moves,
# update both in the same commit.
from test_pillow_block import (  # noqa: E402
    mm,
    _top_face,
    require_cylinder_count,
    require_volume_near,
)


NEGATIVE_TEST = CadTest(
    name="pillow_block_missing_shaft",
    brief=(
        "Motor pillow block (negative test). Same as pillow_block but the "
        "driver DOES NOT cut the shaft hole; the shaft assertion must fire."
    ),
    keep_doc=False,  # we expect to fail — don't leave garbage docs behind
    steps=[
        # 1. Base flange
        build("base_sketch", "create_sketch_rectangle", lambda ctx: {
            "name": "base sketch", "plane": "Top",
            "corner1": [mm(-30), mm(-20)], "corner2": [mm(30), mm(20)],
        }),
        build("base_extrude", "create_extrude", lambda ctx: {
            "name": "base extrude",
            "sketchFeatureId": ctx.feature_ids["base sketch"],
            "depth": 8, "operationType": "NEW",
        }),
        assert_state("base volume", require_volume_near(60 * 40 * 8, tol_pct=0.5)),
        inspect("after_base"),

        # 2. Housing on top of the base
        build("housing_sketch", "create_sketch_circle", lambda ctx: {
            "name": "housing sketch",
            "faceId": _top_face(ctx, z_mm=8.0),
            "center": [0.0, 0.0], "radius": mm(15),
        }),
        build("housing_extrude", "create_extrude", lambda ctx: {
            "name": "housing extrude",
            "sketchFeatureId": ctx.feature_ids["housing sketch"],
            "depth": 20, "operationType": "ADD",
        }),
        assert_state("housing radius", require_cylinder_count(1, 15.0, "housing wall")),
        assert_state(
            "total volume after housing",
            require_volume_near(60 * 40 * 8 + math.pi * 15**2 * 20, tol_pct=0.5),
        ),
        inspect("after_housing"),

        # 3. Bearing bore
        build("bearing_sketch", "create_sketch_circle", lambda ctx: {
            "name": "bearing sketch",
            "faceId": _top_face(ctx, z_mm=28.0),
            "center": [0.0, 0.0], "radius": mm(11),
        }),
        build("bearing_cut", "create_extrude", lambda ctx: {
            "name": "bearing cut",
            "sketchFeatureId": ctx.feature_ids["bearing sketch"],
            "depth": 8, "operationType": "REMOVE",
            "oppositeDirection": True,
        }),
        assert_state("bearing bore radius", require_cylinder_count(1, 11.0, "bearing bore")),
        inspect("after_bearing"),

        # 4. SHAFT HOLE STEPS INTENTIONALLY OMITTED.
        #    The next assertion expects exactly 1 cylinder of radius 4.0 mm;
        #    since we never cut it, this must fail and halt the driver.

        assert_state("shaft hole radius", require_cylinder_count(1, 4.0, "shaft hole")),

        # Never reached unless the harness is broken; kept so that a silent-
        # failure regression would still show us diverging state.
        inspect("unreachable_after_shaft"),
    ],
)


def _negative_harness_ok(report) -> tuple[bool, str]:
    """Verify the driver caught the missing-shaft scenario correctly.

    Returns (ok, message). Pass condition:
        1. report.ok is False
        2. exactly one step failed (the first assertion that hit the gap)
        3. that step is the shaft-hole assertion
        4. the error string names the missing radius AND the found=0 count
    """
    if report.ok:
        return False, (
            "FAIL: report.ok is True — driver silently approved a build "
            "missing the shaft hole. Harness regression."
        )

    failing = [s for s in report.steps if not s.ok]
    if not failing:
        return False, "FAIL: report.ok is False but no failing step — inconsistent report."

    first = failing[0]
    if first.step != "shaft hole radius":
        return False, (
            f"FAIL: first failing step is {first.step!r}, expected 'shaft hole radius'. "
            f"Upstream step failed before the shaft assertion could fire; check the "
            f"report for the underlying cause."
        )

    err = first.error or ""
    if "radius 4.0mm" not in err or "found 0" not in err:
        return False, (
            f"FAIL: shaft-hole assertion error doesn't name the missing cylinder. "
            f"error={err!r}"
        )

    return True, (
        f"PASS: driver halted at 'shaft hole radius' as expected. "
        f"error substring confirmed: 'expected 1 cylinders of radius 4.0mm, found 0'."
    )


if __name__ == "__main__":
    out_root = (
        Path(__file__).resolve().parents[2] / ".." / "scratchpad" / "cad-tests"
    ).resolve()
    report = asyncio.run(run_cad_test(NEGATIVE_TEST, out_root))
    print(report.summary())
    print()

    ok, msg = _negative_harness_ok(report)
    print(msg)
    sys.exit(0 if ok else 1)
