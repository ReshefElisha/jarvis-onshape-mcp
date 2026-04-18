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
    """Read a STEP file. Returns a single compound shape (may contain many solids)."""
    reader = STEPControl_Reader()
    status = reader.ReadFile(str(path))
    if status != IFSelect_RetDone:
        raise IOError(f"STEPControl_Reader failed on {path}: status={status}")
    reader.TransferRoots()
    return reader.OneShape()


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


def boolean_iou(a: TopoDS_Shape, b: TopoDS_Shape) -> float:
    """vol(A ∩ B) / vol(A ∪ B). Returns 0 on degenerate cases."""
    va = volume(a)
    vb = volume(b)
    if va == 0.0 or vb == 0.0:
        return 0.0
    try:
        inter = BRepAlgoAPI_Common(a, b).Shape()
        union = BRepAlgoAPI_Fuse(a, b).Shape()
    except Exception:
        return 0.0
    v_inter = volume(inter)
    v_union = volume(union)
    if v_union == 0.0:
        return 0.0
    return v_inter / v_union


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
) -> float:
    """Symmetric Chamfer distance between tessellations of a and b, in meters.

    Down-samples each point cloud to `n_samples` for KDTree cost. Returns
    the mean of mean-forward-distance and mean-backward-distance.
    """
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
