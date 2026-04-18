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
    _make_box_step(ref_path, 0.040, 0.030, 0.020)
    _make_box_step(agent_path, 0.040, 0.030, 0.020)
    r = score_step_pair(agent_path, ref_path)
    print(f"\n[identity] composite={r.composite:.4f}  (expect 1.0)")
    for name, layer in r.layers.items():
        print(f"  {name}: pass={layer.passed} measurement={layer.measurement:.6g} ({layer.tolerance})")
    assert r.composite > 0.999, f"identity failed: {r.to_dict()}"

    # Test 2: translated box. Same size, same topology, non-overlapping volume
    # → L1 pass (volume matches), L2 pass (bbox diag matches), L3 pass
    # (topology matches), L4 fail (IoU = 0, no overlap), L5 skipped.
    # Composite = 0.15 + 0.15 + 0.15 = 0.45.
    agent_moved = tmp / "agent_translated.step"
    _make_translated_box_step(agent_moved, 0.040, 0.030, 0.020,
                              tx=1.0, ty=0.0, tz=0.0)  # moved 1 meter in x
    r2 = score_step_pair(agent_moved, ref_path)
    print(f"\n[translated] composite={r2.composite:.4f}  (expect ~0.45)")
    for name, layer in r2.layers.items():
        print(f"  {name}: pass={layer.passed} measurement={layer.measurement:.6g}")
    assert 0.40 < r2.composite < 0.50, f"translated failed: {r2.to_dict()}"
    assert r2.layers["L1"].passed
    assert r2.layers["L2"].passed
    assert r2.layers["L3"].passed
    assert not r2.layers["L4"].passed
    assert not r2.layers["L5"].passed

    # Test 3: smaller box. Volume ratio off by 50% → L1 fails, L4 skipped by
    # the volume-diff guard. Composite = 0.0 (L2 fails too since diagonal
    # changes by > 5%).
    agent_small = tmp / "agent_small.step"
    _make_box_step(agent_small, 0.020, 0.015, 0.010)  # half-size in each axis
    r3 = score_step_pair(agent_small, ref_path)
    print(f"\n[smaller] composite={r3.composite:.4f}  (expect 0.15; topology still OK)")
    # L3 passes: same box topology (6 faces, 12 edges, 8 verts, 1 solid).
    assert r3.layers["L3"].passed
    assert not r3.layers["L1"].passed
    assert not r3.layers["L2"].passed

    print("\n✅ Grader self-test PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
