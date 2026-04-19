"""STEP comparison primitives — LOCKED.

The four measurements the rubric (rubric.py) layers on top of: volume,
bounding box, topology signature, Boolean IoU, Chamfer distance.
All built on cadquery-ocp (pip `cadquery-ocp`). Deterministic under
pinned versions.

Do NOT edit without a GRADER_HASH revision. See eval/README.md § Phase 1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np
import trimesh

from OCP.Bnd import Bnd_Box
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Fuse
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import (
    TopAbs_COMPOUND,
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_SHELL,
    TopAbs_SOLID,
    TopAbs_VERTEX,
)
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape, TopoDS_Face
from OCP.TopLoc import TopLoc_Location


# --- IO --------------------------------------------------------------


def load_step(path: str | Path) -> TopoDS_Shape:
    """Read a STEP file and normalize units to millimeters.

    The grader + renderers work in MILLIMETERS across the board. STEP
    files declare their own length unit; OCP's reader applies it
    literally, so STEPs from different sources come out at different
    scales (NIST AP242 → meters, SolidWorks Model Mania → mm, etc.).
    Heuristic: mechanical parts are ~10–500 mm in typical extent. If
    the loaded shape has a max bbox extent < 1.0 (impossible for a
    mm-scale mechanical part), the STEP was in meters → scale by 1000.
    """
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf

    reader = STEPControl_Reader()
    status = reader.ReadFile(str(path))
    if status != IFSelect_RetDone:
        raise IOError(f"STEPControl_Reader failed on {path}: status={status}")
    reader.TransferRoots()
    shape = reader.OneShape()

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    dims = [xmax - xmin, ymax - ymin, zmax - zmin]
    max_extent = max(dims) if dims else 0.0
    if 0 < max_extent < 1.0:
        # Shape is in meters; scale up to mm.
        trsf = gp_Trsf()
        trsf.SetScaleFactor(1000.0)
        shape = BRepBuilderAPI_Transform(shape, trsf, True).Shape()
    return shape


# --- Scalar measurements ---------------------------------------------


@dataclass(frozen=True)
class BBox:
    xmin: float
    ymin: float
    zmin: float
    xmax: float
    ymax: float
    zmax: float

    @property
    def dx(self) -> float:
        return self.xmax - self.xmin

    @property
    def dy(self) -> float:
        return self.ymax - self.ymin

    @property
    def dz(self) -> float:
        return self.zmax - self.zmin

    @property
    def diagonal(self) -> float:
        return math.sqrt(self.dx**2 + self.dy**2 + self.dz**2)


def volume(shape: TopoDS_Shape) -> float:
    """Volume in m^3 (OCC internal unit). Returns 0 for non-solid or empty shapes."""
    if shape is None or shape.IsNull():
        return 0.0
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return abs(props.Mass())


def bbox(shape: TopoDS_Shape) -> BBox:
    """Axis-aligned bounding box."""
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return BBox(xmin, ymin, zmin, xmax, ymax, zmax)


def _count_subshapes(shape: TopoDS_Shape, kind: int) -> int:
    """Count unique subshapes of a given topological type.

    TopExp_Explorer may revisit shared subshapes (e.g. an edge bordering
    two faces), so we dedupe using IsSame. cadquery-ocp 7.9 removed
    HashCode; IsSame compares TShape+Location canonically. O(n²) but
    acceptable for part-scale geometry (n < a few thousand).
    """
    explorer = TopExp_Explorer(shape, kind)
    unique: list[TopoDS_Shape] = []
    while explorer.More():
        s = explorer.Current()
        if not any(s.IsSame(u) for u in unique):
            unique.append(s)
        explorer.Next()
    return len(unique)


@dataclass(frozen=True)
class TopologySignature:
    n_solids: int
    n_faces: int
    n_edges: int
    n_vertices: int

    def ratio(self, other: "TopologySignature") -> float:
        """0..1 similarity score based on per-field min/max ratios.

        For each field: min(a,b)/max(a,b). Average across fields. If both
        zero in a field, that field scores 1. If one zero and the other
        nonzero, that field scores 0.
        """
        fields = ["n_solids", "n_faces", "n_edges", "n_vertices"]
        scores = []
        for f in fields:
            a = getattr(self, f)
            b = getattr(other, f)
            if a == 0 and b == 0:
                scores.append(1.0)
            elif a == 0 or b == 0:
                scores.append(0.0)
            else:
                scores.append(min(a, b) / max(a, b))
        return sum(scores) / len(scores)


def topology_signature(shape: TopoDS_Shape) -> TopologySignature:
    return TopologySignature(
        n_solids=_count_subshapes(shape, TopAbs_SOLID),
        n_faces=_count_subshapes(shape, TopAbs_FACE),
        n_edges=_count_subshapes(shape, TopAbs_EDGE),
        n_vertices=_count_subshapes(shape, TopAbs_VERTEX),
    )


# --- Boolean IoU -----------------------------------------------------


def _translate(shape: TopoDS_Shape, tx: float, ty: float, tz: float) -> TopoDS_Shape:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf, gp_Vec
    trsf = gp_Trsf()
    trsf.SetTranslation(gp_Vec(tx, ty, tz))
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def _bbox_center(shape: TopoDS_Shape) -> Tuple[float, float, float]:
    b = bbox(shape)
    return (0.5 * (b.xmin + b.xmax),
            0.5 * (b.ymin + b.ymax),
            0.5 * (b.zmin + b.zmax))


def align_bbox_centers(a: TopoDS_Shape, b: TopoDS_Shape) -> Tuple[TopoDS_Shape, TopoDS_Shape]:
    """Translate `a` so its bbox center sits on top of `b`'s.

    Position-invariance: the brief describes a shape, not its world-frame
    placement. Two agents that build the same part at different translations
    (e.g. corner-at-origin vs centered-on-origin) should score the same on
    geometric-similarity layers (L4 IoU, L5 Chamfer). Rotation is NOT canceled
    out — briefs specify orientation ("axis along Z") and a wrong-axis build
    is a real failure.
    """
    ax, ay, az = _bbox_center(a)
    bx, by, bz = _bbox_center(b)
    return _translate(a, bx - ax, by - ay, bz - az), b


def _rotate(shape: TopoDS_Shape, R33) -> TopoDS_Shape:
    """Apply a 3x3 rotation matrix to `shape`. Expects a proper rotation
    (det = +1). Uses OCC's Trsf.SetValues taking 12 coefficients (3x4)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf
    trsf = gp_Trsf()
    trsf.SetValues(
        R33[0][0], R33[0][1], R33[0][2], 0.0,
        R33[1][0], R33[1][1], R33[1][2], 0.0,
        R33[2][0], R33[2][1], R33[2][2], 0.0,
    )
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def _cubic_rotation_matrices():
    """Return the 24 proper rotations of the cube (axis permutations +
    sign flips with det = +1). Cached on first call."""
    if hasattr(_cubic_rotation_matrices, "_cache"):
        return _cubic_rotation_matrices._cache
    from itertools import permutations, product
    rots = []
    for perm in permutations([0, 1, 2]):
        P = [[0.0]*3 for _ in range(3)]
        for i, pi in enumerate(perm):
            P[i][pi] = 1.0
        for signs in product([1.0, -1.0], repeat=3):
            R = [[P[i][j] * signs[j] for j in range(3)] for i in range(3)]
            # determinant of a signed permutation: product of sign * sign(perm).
            det = signs[0] * signs[1] * signs[2]
            # Parity of permutation
            parity = 1
            for i in range(3):
                for j in range(i+1, 3):
                    if perm[i] > perm[j]:
                        parity *= -1
            if det * parity > 0:  # proper rotation
                rots.append(R)
    assert len(rots) == 24, f"expected 24, got {len(rots)}"
    _cubic_rotation_matrices._cache = rots
    return rots


def _iou_aligned(a: TopoDS_Shape, b: TopoDS_Shape, align: bool = True) -> float:
    if align:
        a, b = align_bbox_centers(a, b)
    try:
        inter = BRepAlgoAPI_Common(a, b).Shape()
        union = BRepAlgoAPI_Fuse(a, b).Shape()
    except Exception:
        return 0.0
    v_union = volume(union)
    if v_union == 0.0:
        return 0.0
    return volume(inter) / v_union


def find_best_rotation(a: TopoDS_Shape, b: TopoDS_Shape) -> Tuple[TopoDS_Shape, float]:
    """Find the axis-aligned rotation of `a` that maximizes IoU with `b`.
    Returns (rotated_a, iou). Skips rotation search if bbox sorted dims
    don't match within 25% — in that case the shapes aren't the same
    solid at any rotation.
    """
    va = volume(a)
    vb = volume(b)
    if va == 0.0 or vb == 0.0:
        return a, 0.0
    a_bbox = bbox(a)
    b_bbox = bbox(b)
    a_sorted = sorted([a_bbox.dx, a_bbox.dy, a_bbox.dz], reverse=True)
    b_sorted = sorted([b_bbox.dx, b_bbox.dy, b_bbox.dz], reverse=True)
    if not all(abs(x - y) / max(y, 1e-9) < 0.25 for x, y in zip(a_sorted, b_sorted)):
        return a, _iou_aligned(a, b)
    best_shape = a
    best_iou = 0.0
    for R in _cubic_rotation_matrices():
        rotated = _rotate(a, R)
        iou = _iou_aligned(rotated, b)
        if iou > best_iou:
            best_iou = iou
            best_shape = rotated
            if best_iou > 0.99:
                break
    return best_shape, best_iou


def boolean_iou(
    a: TopoDS_Shape,
    b: TopoDS_Shape,
    align: bool = True,
    rotation_invariant: bool = True,
) -> float:
    """vol(A ∩ B) / vol(A ∪ B). Returns 0 on degenerate cases.

    Translates A so its bbox center aligns with B's before computing the
    boolean. If `rotation_invariant` (default), also tries the 24 proper
    rotations of the cube (±90°/±180° per axis) and returns the best IoU.
    This captures the case where the agent built the correct shape but
    in a different world-frame orientation. Non-axis-aligned rotations
    are NOT tested — orientation beyond ±90° is treated as a real error.

    Pass `align=False` to skip translation alignment; pass
    `rotation_invariant=False` to require orientation agreement.
    """
    if volume(a) == 0.0 or volume(b) == 0.0:
        return 0.0
    if not rotation_invariant:
        return _iou_aligned(a, b, align=align)
    _, iou = find_best_rotation(a, b)
    return iou


# --- Tessellation + Chamfer ------------------------------------------


def _tessellate(shape: TopoDS_Shape, linear_deflection: float = 0.5) -> np.ndarray:
    """Mesh the shape and return an (N,3) vertex array in meters.

    `linear_deflection` is in the shape's units (OCC uses mm in many
    imports; our grader treats it as meters consistently — callers pass
    a fraction of the bbox diagonal for a density-adaptive tessellation).
    """
    meshed = BRepMesh_IncrementalMesh(shape, linear_deflection, False, 0.5, True)
    meshed.Perform()
    points: list[list[float]] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        # explorer.Current() returns a TopoDS_Shape; cast to Face via TopoDS.Face_s.
        face = TopoDS.Face_s(explorer.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None:
            trsf = loc.Transformation()
            n_nodes = tri.NbNodes()
            for i in range(1, n_nodes + 1):
                p = tri.Node(i).Transformed(trsf)
                points.append([p.X(), p.Y(), p.Z()])
        explorer.Next()
    if not points:
        return np.zeros((0, 3), dtype=np.float64)
    return np.asarray(points, dtype=np.float64)


def chamfer_distance(
    a: TopoDS_Shape,
    b: TopoDS_Shape,
    n_samples: int = 10000,
    align: bool = True,
    rotation_invariant: bool = True,
) -> float:
    """Symmetric Chamfer distance between tessellations of a and b, in meters.

    Down-samples each point cloud to `n_samples` for KDTree cost. Returns
    the mean of mean-forward-distance and mean-backward-distance.

    When `align=True` (default) the two shapes' bbox centers are aligned
    before tessellation. When `rotation_invariant`, tries the 24 cubic
    rotations of A and returns the MIN distance — matches boolean_iou's
    rotation handling so both layers agree about whether two shapes are
    equivalent up to ±90° world-axis rotation.
    """
    if rotation_invariant:
        # Pick the rotation found best by boolean-IoU and use that for Chamfer.
        a, _ = find_best_rotation(a, b)
    if align:
        a, b = align_bbox_centers(a, b)
    # Use a bbox-diag-fraction deflection so large + small shapes both tess well.
    try:
        diag = max(bbox(a).diagonal, bbox(b).diagonal, 1e-6)
    except Exception:
        diag = 1e-3
    defl = max(diag * 0.01, 1e-5)
    pa = _tessellate(a, linear_deflection=defl)
    pb = _tessellate(b, linear_deflection=defl)
    if len(pa) == 0 or len(pb) == 0:
        return float("inf")
    if len(pa) > n_samples:
        pa = pa[np.random.default_rng(0).choice(len(pa), n_samples, replace=False)]
    if len(pb) > n_samples:
        pb = pb[np.random.default_rng(1).choice(len(pb), n_samples, replace=False)]
    # KDTree via trimesh for convenience.
    try:
        from scipy.spatial import cKDTree
        tree_a = cKDTree(pa)
        tree_b = cKDTree(pb)
        d_ab = tree_b.query(pa)[0].mean()
        d_ba = tree_a.query(pb)[0].mean()
    except ImportError:
        # Fall back to trimesh's proximity (slower but available).
        mesh_a = trimesh.Trimesh(vertices=pa, process=False)
        mesh_b = trimesh.Trimesh(vertices=pb, process=False)
        d_ab = float(np.mean(np.linalg.norm(
            pa[:, None, :] - pb[None, :, :], axis=-1).min(axis=1)))
        d_ba = float(np.mean(np.linalg.norm(
            pb[:, None, :] - pa[None, :, :], axis=-1).min(axis=1)))
    return float((d_ab + d_ba) / 2)
