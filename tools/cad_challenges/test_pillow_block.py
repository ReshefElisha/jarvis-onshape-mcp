"""Self-test: motor pillow block with bearing seat.

Brief:
    "Motor pillow block. Rectangular base flange 60x40x8 mm with four 4mm
    mounting holes at the corners, 6mm inset from each edge. Centered on top
    of the flange, a cylindrical housing 30mm OD x 20mm tall. Top of the
    housing has a blind 22mm-diameter x 8mm-deep bearing bore. A through
    8mm shaft hole runs coaxially through housing and flange."

Target geometry and checks:
    - Base flange: 60 x 40 x 8 mm rectangular solid, volume 14400 mm^3 before cuts.
    - Housing: ø30 x 20 mm cylinder added on top, volume 14137 mm^3.
    - Bearing bore: ø22 x 8 mm deep, subtracts 3040 mm^3.
    - Shaft hole: ø8 mm through-hole (28 mm long), subtracts 1407 mm^3.
    - 4 mounting holes: ø4 x 8 mm (through the base), each subtracts 100.5 mm^3.
    Predicted final volume: 14400 + 14137 - 3040 - 1407 - 402 = 23688 mm^3.

Self-test criteria (objective, not visual):
    1. Every feature returns status OK or INFO (none ERROR).
    2. Final body topology has:
         - exactly 1 cylindrical face of radius 15.0 mm (housing wall)
         - exactly 1 cylindrical face of radius 11.0 mm (bearing bore)
         - exactly 1 cylindrical face of radius 4.0 mm (shaft hole)
         - exactly 4 cylindrical faces of radius 2.0 mm (mounting holes)
    3. Bearing bore depth = 8.0 mm (measure floor of bore vs top of housing).
    4. Housing top is at z = 28 mm (base 8 + housing 20). measured against z=0 base bottom.
    5. Total volume within 1% of predicted 23688 mm^3.

Run:
    uv run python tools/cad_challenges/test_pillow_block.py
"""

from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from cad_driver import CadTest, Step, build, assert_state, inspect, run_cad_test  # noqa: E402


# Starter still interprets bare numbers as INCHES (pending peer's [units] fix).
# For now, convert mm -> inches inline.
def mm(x: float) -> float:
    return x / 25.4


# --- Helper predicates -------------------------------------------------------


def _cylinders_with_radius(faces: list, target_mm: float, tol_mm: float = 0.01) -> list:
    target_m = target_mm / 1000.0
    return [
        f for f in faces
        if f.get("type") == "CYLINDER"
        and f.get("radius") is not None
        and abs(f["radius"] - target_m) < tol_mm / 1000.0
    ]


def require_cylinder_count(expected_count: int, target_mm: float, label: str):
    """Return a predicate that asserts N cylinders at the given radius."""

    def check(snap: dict) -> str | None:
        bodies = snap["raw"]["entities"].get("bodies") or []
        if not bodies:
            return f"{label}: no bodies yet"
        faces = bodies[0].get("faces") or []
        found = _cylinders_with_radius(faces, target_mm)
        if len(found) != expected_count:
            descs = [f["description"] for f in found]
            all_cyls = [
                f"{f['id']}: r={f.get('radius')*1000:.2f}mm"
                for f in faces if f.get("type") == "CYLINDER"
            ]
            return (
                f"{label}: expected {expected_count} cylinders of radius "
                f"{target_mm}mm, found {len(found)}. Matching: {descs}. "
                f"All cylinders: {all_cyls}"
            )
        return None

    return check


def require_volume_near(expected_mm3: float, tol_pct: float = 1.0):
    def check(snap: dict) -> str | None:
        mp = snap["raw"]["mass_properties"]
        bodies = mp.get("bodies") or {}
        if not bodies:
            return "mass_properties returned no bodies"
        first = next(iter(bodies.values()))
        vol = first.get("volume") or [0, 0, 0]
        vol_mm3 = vol[1] * 1e9 if len(vol) >= 2 else 0
        pct = 100 * abs(vol_mm3 - expected_mm3) / expected_mm3
        if pct > tol_pct:
            return f"volume {vol_mm3:.1f} mm^3 differs from expected {expected_mm3:.1f} by {pct:.2f}% (>{tol_pct}%)"
        return None

    return check


def pick_top_face_at_z(z_mm: float, tol_mm: float = 0.5):
    """Return the deterministic id of the highest +Z face at (~z_mm)."""

    def _find(snap: dict) -> str | None:
        bodies = snap["raw"]["entities"].get("bodies") or []
        if not bodies:
            return None
        top_faces = [
            f for f in bodies[0]["faces"]
            if f.get("type") == "PLANE" and f.get("normal_axis") == "+Z"
            and f.get("origin") and abs(f["origin"][2] * 1000 - z_mm) < tol_mm
        ]
        if not top_faces:
            return None
        return top_faces[0]["id"]

    return _find


# --- Test definition --------------------------------------------------------


def _top_face(ctx, z_mm: float, tol: float = 0.5):
    """Pick a +Z face at a given z using the cached snapshot.

    Relies on a preceding inspect/assert step to have populated ctx._snapshot_cache.
    This is deliberate: it means every "sketch-on-face" step must come after a
    look-at-current-state step, matching the verify-before-pick protocol.
    """
    snap = ctx._snapshot_cache
    if snap is None:
        raise RuntimeError(
            f"_top_face({z_mm}mm) requires a preceding inspect/assert step to "
            "populate the snapshot cache"
        )
    bodies = snap["raw"]["entities"].get("bodies") or []
    if not bodies:
        raise RuntimeError(f"_top_face({z_mm}mm): no bodies in snapshot")
    top_faces = [
        f for f in bodies[0]["faces"]
        if f.get("type") == "PLANE" and f.get("normal_axis") == "+Z"
        and f.get("origin") and abs(f["origin"][2] * 1000 - z_mm) < tol
    ]
    if not top_faces:
        available = [
            (f["id"], f"z={(f.get('origin') or [0,0,0])[2]*1000:.2f}mm")
            for f in bodies[0]["faces"]
            if f.get("type") == "PLANE" and f.get("normal_axis") == "+Z"
        ]
        raise RuntimeError(f"_top_face: no +Z face at z={z_mm}mm. Available: {available}")
    return top_faces[0]["id"]


def _mounting_hole_steps(corner: tuple) -> list[Step]:
    ix, iy = corner
    tag = f"mh_{ix:+d}_{iy:+d}".replace("+", "p").replace("-", "m")
    sketch_name = f"{tag} sketch"
    cut_name = f"{tag} cut"
    return [
        # Refresh snapshot so _top_face can find the base top via cache.
        inspect(f"before_{tag}"),
        build(sketch_name, "create_sketch_circle", lambda ctx, ix=ix, iy=iy, n=sketch_name: {
            "name": n,
            "faceId": _top_face(ctx, z_mm=8.0),
            "center": [mm(ix), mm(iy)], "radius": mm(2),
        }),
        build(cut_name, "create_extrude", lambda ctx, s=sketch_name, n=cut_name: {
            "name": n,
            "sketchFeatureId": ctx.feature_ids[s],
            "depth": 10, "operationType": "REMOVE",
            "oppositeDirection": True,
        }),
    ]


TEST = CadTest(
    name="pillow_block",
    brief="Motor pillow block: 60x40x8 base flange with 4 corner M4 mounting holes, "
          "ø30x20 mm housing centered on top, ø22x8 mm blind bearing bore, "
          "ø8 mm through shaft.",
    steps=[
        # 1. Base sketch on Top plane, extrude 8mm.
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

        # 2. Housing on top of the base: find top face, sketch ø30 circle, extrude +20.
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

        # 3. Bearing bore: ø22, cut 8mm down from housing top (z=28).
        build("bearing_sketch", "create_sketch_circle", lambda ctx: {
            "name": "bearing sketch",
            "faceId": _top_face(ctx, z_mm=28.0),
            "center": [0.0, 0.0], "radius": mm(11),
        }),
        build("bearing_cut", "create_extrude", lambda ctx: {
            "name": "bearing cut",
            "sketchFeatureId": ctx.feature_ids["bearing sketch"],
            "depth": 8, "operationType": "REMOVE",
            "oppositeDirection": True,   # cut INTO the housing, not up into air
        }),
        assert_state("bearing bore radius", require_cylinder_count(1, 11.0, "bearing bore")),
        inspect("after_bearing"),

        # 4. Shaft hole: ø8, cut all the way through (30 mm to be safe).
        build("shaft_sketch", "create_sketch_circle", lambda ctx: {
            "name": "shaft sketch",
            "faceId": _top_face_at_z(ctx, z_mm=20.0),  # bearing bore floor at z=28-8=20
            "center": [0.0, 0.0], "radius": mm(4),
        }),
        build("shaft_cut", "create_extrude", lambda ctx: {
            "name": "shaft cut",
            "sketchFeatureId": ctx.feature_ids["shaft sketch"],
            "depth": 25, "operationType": "REMOVE",
            "oppositeDirection": True,
        }),
        assert_state("shaft hole radius", require_cylinder_count(1, 4.0, "shaft hole")),
        inspect("after_shaft"),

        # 5. Four mounting holes: ø4, on the base top face (z=8), cut through 8mm.
        *[
            s for corner in [(+24, +14), (-24, +14), (-24, -14), (+24, -14)]
            for s in _mounting_hole_steps(corner)
        ],
        assert_state("mounting holes count", require_cylinder_count(4, 2.0, "mounting holes")),
        inspect("final"),
        assert_state(
            "final volume",
            # shaft length is 20 mm (total height 28 mm minus bearing-bore 8 mm
            # that's already removed), not 28 mm.
            require_volume_near(
                60 * 40 * 8 + math.pi * 15**2 * 20 - math.pi * 11**2 * 8
                - math.pi * 4**2 * 20 - 4 * math.pi * 2**2 * 8,
                tol_pct=0.5,
            ),
        ),
    ],
)


_top_face_at_z = _top_face  # alias for readability at the bearing-floor call site


if __name__ == "__main__":
    out_root = Path(__file__).resolve().parents[2] / ".." / "scratchpad" / "cad-tests"
    report = asyncio.run(run_cad_test(TEST, out_root.resolve()))
    print(report.summary())
    sys.exit(0 if report.ok else 1)
