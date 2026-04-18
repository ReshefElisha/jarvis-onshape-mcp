"""Grader self-test. Builds a reference box, writes STEP, grades against itself.

Expected: composite == 1.0 (all layers pass). Run from the eval venv:

    source eval/.venv/bin/activate
    python -m eval.grader.selftest

Also tests the degenerate cases: empty shape → composite=0, shifted shape
→ L4/L5 should fail (correct behavior; we don't re-center).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.gp import gp_Pnt, gp_Trsf, gp_Vec
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

from eval.grader.rubric import score_step_pair


def _make_box_step(path: Path, dx: float, dy: float, dz: float,
                   dx0: float = 0.0, dy0: float = 0.0, dz0: float = 0.0) -> None:
    box = BRepPrimAPI_MakeBox(gp_Pnt(dx0, dy0, dz0), dx + dx0, dy + dy0, dz + dz0).Shape()
    writer = STEPControl_Writer()
    writer.Transfer(box, STEPControl_AsIs)
    status = writer.Write(str(path))
    if status != IFSelect_RetDone:
        raise IOError(f"STEPControl_Writer failed: {status}")


def _make_translated_box_step(path: Path, dx: float, dy: float, dz: float,
                              tx: float, ty: float, tz: float) -> None:
    box = BRepPrimAPI_MakeBox(dx, dy, dz).Shape()
    trsf = gp_Trsf()
    trsf.SetTranslation(gp_Vec(tx, ty, tz))
    moved = BRepBuilderAPI_Transform(box, trsf, True).Shape()
    writer = STEPControl_Writer()
    writer.Transfer(moved, STEPControl_AsIs)
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise IOError("STEPControl_Writer failed")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="grader-selftest-"))
    print(f"[tmp] {tmp}")

    # Test 1: identity. Same box vs same box → composite 1.0.
    ref_path = tmp / "reference.step"
    agent_path = tmp / "agent_identity.step"
    _make_box_step(ref_path, 40.0, 30.0, 20.0)
    _make_box_step(agent_path, 40.0, 30.0, 20.0)
    r = score_step_pair(agent_path, ref_path)
    print(f"\n[identity] composite={r.composite:.4f}  (expect 1.0)")
    for name, layer in r.layers.items():
        print(f"  {name}: frac={layer.fraction:.3f} measurement={layer.measurement:.6g} [{layer.band}]")
    assert r.composite > 0.999, f"identity failed: {r.to_dict()}"

    # Test 2: translated box. Same size, same topology, non-overlapping volume.
    # L1/L2/L3 at full fraction, L4 IoU=0 (below floor 0.30 → 0), L5 skipped.
    # Composite ≈ 0.15 + 0.15 + 0.15 = 0.45.
    agent_moved = tmp / "agent_translated.step"
    _make_translated_box_step(agent_moved, 40.0, 30.0, 20.0,
                              tx=1000.0, ty=0.0, tz=0.0)
    r2 = score_step_pair(agent_moved, ref_path)
    print(f"\n[translated] composite={r2.composite:.4f}  (expect ~0.45)")
    for name, layer in r2.layers.items():
        print(f"  {name}: frac={layer.fraction:.3f} measurement={layer.measurement:.6g}")
    assert 0.40 < r2.composite < 0.50, f"translated failed: {r2.to_dict()}"
    assert r2.layers["L1"].fraction > 0.99
    assert r2.layers["L2"].fraction > 0.99
    assert r2.layers["L3"].fraction > 0.99
    assert r2.layers["L4"].fraction == 0.0
    assert r2.layers["L5"].fraction == 0.0

    # Test 3: smaller box (halved each axis). Volume off by 87.5%, bbox diag
    # off by 50% — both saturate L1/L2 at floor (fraction 0). Topology
    # identical (6/12/8) → L3 full.
    agent_small = tmp / "agent_small.step"
    _make_box_step(agent_small, 20.0, 15.0, 10.0)
    r3 = score_step_pair(agent_small, ref_path)
    print(f"\n[smaller] composite={r3.composite:.4f}  (expect ~0.15; only L3 full)")
    assert r3.layers["L3"].fraction > 0.99
    assert r3.layers["L1"].fraction == 0.0
    assert r3.layers["L2"].fraction == 0.0

    # Test 4: slightly-off box — "skilled human simplified" case. 40×30×20
    # reference, agent builds 41×30×20 (2.5% bigger in one dim). Volume
    # error ~2.5%, bbox diag error < 1%. Both L1 and L2 should score high
    # but not full — tests the continuous-band scoring.
    agent_close = tmp / "agent_close.step"
    _make_box_step(agent_close, 41.0, 30.0, 20.0)
    r4 = score_step_pair(agent_close, ref_path)
    print(f"\n[near-match] composite={r4.composite:.4f}  (expect 0.7–0.95)")
    for name, layer in r4.layers.items():
        print(f"  {name}: frac={layer.fraction:.3f} measurement={layer.measurement:.6g}")
    assert 0.70 < r4.composite < 0.99, f"near-match composite unexpected: {r4.composite}"
    # L1 continuous: measurement ≈ 0.025, band (0.20→0.02); expect ~0.875
    assert 0.80 < r4.layers["L1"].fraction < 1.0

    print("\n✅ Grader self-test PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
