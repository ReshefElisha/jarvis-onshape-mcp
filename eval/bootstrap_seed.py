"""Phase-0 seed eval set — 10 procedurally-generated briefs + STEPs + PNGs.

Ships the eval harness with a working end-to-end pipeline on simple parts
so the AutoResearch loop has something to score against from iteration 1.
DeepCAD / CADPrompt conversion can expand the set later.

Each brief is:
  - a natural-language instruction the agent will receive
  - a reference STEP produced procedurally via OCP
  - a PNG render so Shef can eyeball before running the loop

Run:
    source eval/.venv/bin/activate
    python eval/bootstrap_seed.py

Output:
    eval/datasets/seed/
      step/<brief_id>.step
      png/<brief_id>.png
    eval/datasets/MANIFEST.json
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from OCP.BRep import BRep_Tool
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
)
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Shape
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform


SEED_DIR = Path(__file__).parent / "datasets" / "seed"
STEP_DIR = SEED_DIR / "step"
PNG_DIR = SEED_DIR / "png"
MANIFEST_PATH = Path(__file__).parent / "datasets" / "MANIFEST.json"


# ---------- part builders (OCP) ----------


def box(dx: float, dy: float, dz: float) -> TopoDS_Shape:
    return BRepPrimAPI_MakeBox(dx, dy, dz).Shape()


def cylinder(r: float, h: float, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> TopoDS_Shape:
    axis = gp_Ax2(gp_Pnt(x, y, z), gp_Dir(0, 0, 1))
    return BRepPrimAPI_MakeCylinder(axis, r, h).Shape()


def translate(shape: TopoDS_Shape, tx: float, ty: float, tz: float) -> TopoDS_Shape:
    trsf = gp_Trsf()
    trsf.SetTranslation(gp_Vec(tx, ty, tz))
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def subtract(a: TopoDS_Shape, b: TopoDS_Shape) -> TopoDS_Shape:
    return BRepAlgoAPI_Cut(a, b).Shape()


def union(a: TopoDS_Shape, b: TopoDS_Shape) -> TopoDS_Shape:
    return BRepAlgoAPI_Fuse(a, b).Shape()


def plate_with_hole(plate_dx: float, plate_dy: float, plate_dz: float,
                    hole_r: float, hole_x: float, hole_y: float) -> TopoDS_Shape:
    p = box(plate_dx, plate_dy, plate_dz)
    h = cylinder(hole_r, plate_dz + 0.002, hole_x, hole_y, -0.001)
    return subtract(p, h)


def plate_with_four_holes(dx: float, dy: float, dz: float,
                           hole_r: float, margin: float) -> TopoDS_Shape:
    p = box(dx, dy, dz)
    for hx, hy in [(margin, margin), (dx - margin, margin),
                   (margin, dy - margin), (dx - margin, dy - margin)]:
        h = cylinder(hole_r, dz + 0.002, hx, hy, -0.001)
        p = subtract(p, h)
    return p


def l_bracket(leg_length: float, leg_width: float, thickness: float) -> TopoDS_Shape:
    horiz = box(leg_length, leg_width, thickness)
    vert = box(thickness, leg_width, leg_length)
    return union(horiz, vert)


def standoff(od: float, id_: float, h: float) -> TopoDS_Shape:
    outer = cylinder(od / 2, h)
    inner = cylinder(id_ / 2, h + 0.002, z=-0.001)
    return subtract(outer, inner)


def washer(od: float, id_: float, h: float) -> TopoDS_Shape:
    return standoff(od, id_, h)


def slotted_strap(length: float, width: float, thickness: float,
                  slot_length: float, slot_width: float) -> TopoDS_Shape:
    strap = box(length, width, thickness)
    # Slot: two half-cylinders + rectangle. Simpler: use capped rectangle.
    slot_rect = box(slot_length - slot_width, slot_width, thickness + 0.002)
    slot_rect = translate(slot_rect, (length - (slot_length - slot_width)) / 2,
                          (width - slot_width) / 2, -0.001)
    cap_a = cylinder(slot_width / 2, thickness + 0.002,
                     (length - (slot_length - slot_width)) / 2, width / 2, -0.001)
    cap_b = cylinder(slot_width / 2, thickness + 0.002,
                     (length - (slot_length - slot_width)) / 2 + (slot_length - slot_width),
                     width / 2, -0.001)
    slot = union(slot_rect, cap_a)
    slot = union(slot, cap_b)
    return subtract(strap, slot)


# ---------- STEP writer ----------


def write_step(shape: TopoDS_Shape, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(str(path))
    if status != IFSelect_RetDone:
        raise IOError(f"STEP write failed: {path} status={status}")


# ---------- PNG render (matplotlib 3D) ----------


def _tessellate_triangles(shape: TopoDS_Shape, deflection: float) -> list:
    BRepMesh_IncrementalMesh(shape, deflection, False, 0.5, True).Perform()
    tris = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None:
            trsf = loc.Transformation()
            nodes = [tri.Node(i + 1).Transformed(trsf)
                     for i in range(tri.NbNodes())]
            for i in range(tri.NbTriangles()):
                t = tri.Triangle(i + 1)
                a, b, c = t.Get()
                tris.append([
                    (nodes[a - 1].X(), nodes[a - 1].Y(), nodes[a - 1].Z()),
                    (nodes[b - 1].X(), nodes[b - 1].Y(), nodes[b - 1].Z()),
                    (nodes[c - 1].X(), nodes[c - 1].Y(), nodes[c - 1].Z()),
                ])
        explorer.Next()
    return tris


def _tessellate_edges(shape: TopoDS_Shape, deflection: float) -> list:
    """Return a list of polylines (each a list of (x,y,z) tuples) tracing
    every TopoDS_EDGE in the shape. Uses BRep_Tool.PolygonOnTriangulation
    where available (edges lying on meshed faces), falling back to the
    edge's own 3D polygon for free-standing edges.

    This gives geometrically-correct feature lines: box edges, cylinder
    silhouettes where they meet flat faces, circular hole boundaries.
    The tessellation-triangle diagonals never appear because we only
    walk real B-rep edges.
    """
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_UniformDeflection
    polylines: list[list[tuple[float, float, float]]] = []
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    seen = []
    while explorer.More():
        raw = explorer.Current()
        if any(raw.IsSame(u) for u in seen):
            explorer.Next()
            continue
        seen.append(raw)
        pts: list[tuple[float, float, float]] = []
        try:
            edge = TopoDS.Edge_s(raw)
            curve = BRepAdaptor_Curve(edge)
            sampler = GCPnts_UniformDeflection(curve, deflection)
            if sampler.IsDone():
                for i in range(1, sampler.NbPoints() + 1):
                    p = sampler.Value(i)
                    pts.append((p.X(), p.Y(), p.Z()))
        except Exception:
            pass
        if len(pts) >= 2:
            polylines.append(pts)
        explorer.Next()
    return polylines


def render_iso_png(shape: TopoDS_Shape, path: Path, size: int = 800) -> None:
    """Render shape to a PNG via VTK.

    Uses VTK's offscreen rendering (no display required) with proper
    z-buffered hidden-surface removal, flat shading, and edge-only
    feature-line overlay. Avoids matplotlib Poly3DCollection's painter
    algorithm which produces tessellation artifacts.
    """
    import vtk
    path.parent.mkdir(parents=True, exist_ok=True)
    from eval.grader.compare_step import bbox
    b = bbox(shape)
    diag = max(b.diagonal, 1e-6)
    tris = _tessellate_triangles(shape, diag * 0.002)  # denser tessellation for smoother curves
    if not tris:
        return

    # Build a vtkPolyData from the triangle list.
    points = vtk.vtkPoints()
    cells = vtk.vtkCellArray()
    for tri in tris:
        ids = [points.InsertNextPoint(*v) for v in tri]
        cells.InsertNextCell(3)
        for i in ids:
            cells.InsertCellPoint(i)
    polydata = vtk.vtkPolyData()
    polydata.SetPoints(points)
    polydata.SetPolys(cells)

    # Merge coincident vertices (the triangle list creates duplicates at
    # every shared corner). Without this, normal smoothing can't recognize
    # adjacent triangles as belonging to the same surface, and cylinders
    # render as faceted polygons.
    cleaner = vtk.vtkCleanPolyData()
    cleaner.SetInputData(polydata)
    cleaner.SetTolerance(1e-6)  # 1 micron — tight enough for mm-scale parts
    cleaner.Update()

    # Smooth normals with a high feature angle so flat faces stay flat and
    # only real CAD corners get a normal split. SplittingOn + feature angle
    # of 45° gives round cylinders + sharp box edges.
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputConnection(cleaner.GetOutputPort())
    normals.SetFeatureAngle(45.0)
    normals.ConsistencyOn()
    normals.AutoOrientNormalsOn()
    normals.SplittingOn()
    normals.ComputePointNormalsOn()
    normals.Update()

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(normals.GetOutputPort())

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(0.70, 0.75, 0.85)
    prop.SetAmbient(0.25)
    prop.SetDiffuse(0.80)
    prop.SetSpecular(0.08)
    prop.SetSpecularPower(15)

    # Feature edges drawn from B-rep TopoDS_EDGE curves, NOT from tessellation
    # diagonals. 10× finer deflection than the face mesh — edges are 1D and
    # cheap to sample densely; the payoff is smooth circle / arc outlines
    # (hole boundaries were reading as hexagons at coarser deflection).
    edge_polylines = _tessellate_edges(shape, diag * 0.0005)
    edge_points = vtk.vtkPoints()
    edge_cells = vtk.vtkCellArray()
    for poly in edge_polylines:
        ids = [edge_points.InsertNextPoint(*p) for p in poly]
        edge_cells.InsertNextCell(len(ids))
        for i in ids:
            edge_cells.InsertCellPoint(i)
    edge_polydata = vtk.vtkPolyData()
    edge_polydata.SetPoints(edge_points)
    edge_polydata.SetLines(edge_cells)
    edge_mapper = vtk.vtkPolyDataMapper()
    edge_mapper.SetInputData(edge_polydata)
    edge_mapper.SetResolveCoincidentTopologyToPolygonOffset()
    edge_actor = vtk.vtkActor()
    edge_actor.SetMapper(edge_mapper)
    edge_actor.GetProperty().SetColor(0.10, 0.10, 0.15)
    edge_actor.GetProperty().SetLineWidth(1.3)

    renderer = vtk.vtkRenderer()
    renderer.AddActor(actor)
    renderer.AddActor(edge_actor)
    renderer.SetBackground(1.0, 1.0, 1.0)

    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.AddRenderer(renderer)
    window.SetSize(size, size)

    # Isometric camera aimed at the body center.
    cx, cy, cz = (b.xmin + b.xmax) / 2, (b.ymin + b.ymax) / 2, (b.zmin + b.zmax) / 2
    d = diag * 2.2
    cam = renderer.GetActiveCamera()
    cam.SetFocalPoint(cx, cy, cz)
    cam.SetPosition(cx + d * 0.8, cy - d * 0.8, cz + d * 0.6)
    cam.SetViewUp(0.0, 0.0, 1.0)
    renderer.ResetCameraClippingRange()
    renderer.ResetCamera()

    window.Render()

    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(window)
    w2i.SetInputBufferTypeToRGB()
    w2i.ReadFrontBufferOff()
    w2i.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(path))
    writer.SetInputConnection(w2i.GetOutputPort())
    writer.Write()


# ---------- brief specs ----------


@dataclass
class BriefSpec:
    brief_id: str
    brief_text: str
    difficulty_tier: str  # "trivial" | "easy" | "medium"
    build_fn: Any
    build_kwargs: dict


SPECS: list[BriefSpec] = [
    BriefSpec(
        brief_id="seed_01_box_40_30_20",
        brief_text=(
            "Build a rectangular plate 40 mm long × 30 mm wide × 20 mm thick. "
            "Place the corner at the origin with the long side along X."
        ),
        difficulty_tier="trivial",
        build_fn=box, build_kwargs={"dx": 0.040, "dy": 0.030, "dz": 0.020},
    ),
    BriefSpec(
        brief_id="seed_02_cube_25",
        brief_text=(
            "Build a 25 mm cube with one corner at the origin."
        ),
        difficulty_tier="trivial",
        build_fn=box, build_kwargs={"dx": 0.025, "dy": 0.025, "dz": 0.025},
    ),
    BriefSpec(
        brief_id="seed_03_cylinder_d20_h30",
        brief_text=(
            "Build a cylinder 20 mm in diameter and 30 mm tall. "
            "Axis along the world Z, base on the XY plane centered on the origin."
        ),
        difficulty_tier="trivial",
        build_fn=cylinder, build_kwargs={"r": 0.010, "h": 0.030},
    ),
    BriefSpec(
        brief_id="seed_04_plate_one_hole",
        brief_text=(
            "Mounting plate 60 mm × 40 mm × 5 mm thick, with a single 8 mm "
            "diameter through-hole in the center. Plate corner at the origin, "
            "long side along X, hole axis along Z."
        ),
        difficulty_tier="easy",
        build_fn=plate_with_hole,
        build_kwargs={"plate_dx": 0.060, "plate_dy": 0.040, "plate_dz": 0.005,
                      "hole_r": 0.004, "hole_x": 0.030, "hole_y": 0.020},
    ),
    BriefSpec(
        brief_id="seed_05_plate_four_holes",
        brief_text=(
            "Mounting plate 80 mm × 60 mm × 6 mm thick, with four 4 mm "
            "diameter through-holes, one near each corner, 10 mm in from "
            "each edge. Plate corner at the origin."
        ),
        difficulty_tier="easy",
        build_fn=plate_with_four_holes,
        build_kwargs={"dx": 0.080, "dy": 0.060, "dz": 0.006,
                      "hole_r": 0.002, "margin": 0.010},
    ),
    BriefSpec(
        brief_id="seed_06_washer",
        brief_text=(
            "Washer: outer diameter 30 mm, inner diameter 15 mm, thickness 3 mm. "
            "Axis along world Z, centered on origin."
        ),
        difficulty_tier="easy",
        build_fn=washer, build_kwargs={"od": 0.030, "id_": 0.015, "h": 0.003},
    ),
    BriefSpec(
        brief_id="seed_07_standoff",
        brief_text=(
            "Threaded-style standoff cylinder: outer diameter 10 mm, inner bore "
            "4 mm through, total height 25 mm. Axis along world Z, base on the "
            "XY plane centered on origin."
        ),
        difficulty_tier="easy",
        build_fn=standoff, build_kwargs={"od": 0.010, "id_": 0.004, "h": 0.025},
    ),
    BriefSpec(
        brief_id="seed_08_l_bracket",
        brief_text=(
            "L-bracket: two legs, each 50 mm long and 30 mm wide, joined at a "
            "right angle. Leg thickness 5 mm. One leg lies flat on the XY "
            "plane; the other rises along Z."
        ),
        difficulty_tier="medium",
        build_fn=l_bracket,
        build_kwargs={"leg_length": 0.050, "leg_width": 0.030, "thickness": 0.005},
    ),
    BriefSpec(
        brief_id="seed_09_slotted_strap",
        brief_text=(
            "Flat strap 60 mm long × 20 mm wide × 4 mm thick with a single "
            "centered slot along the length: slot is 40 mm long × 8 mm wide "
            "with fully-rounded ends (slot is a rectangle capped with two "
            "semicircles). Strap corner at the origin."
        ),
        difficulty_tier="medium",
        build_fn=slotted_strap,
        build_kwargs={"length": 0.060, "width": 0.020, "thickness": 0.004,
                      "slot_length": 0.040, "slot_width": 0.008},
    ),
    BriefSpec(
        brief_id="seed_10_plate_with_hole_offset",
        brief_text=(
            "Rectangular plate 50 mm × 50 mm × 10 mm thick with a 12 mm "
            "diameter through-hole positioned 15 mm in from the +X edge and "
            "15 mm in from the +Y edge (i.e., not centered). Plate corner at "
            "the origin."
        ),
        difficulty_tier="medium",
        build_fn=plate_with_hole,
        build_kwargs={"plate_dx": 0.050, "plate_dy": 0.050, "plate_dz": 0.010,
                      "hole_r": 0.006,
                      "hole_x": 0.050 - 0.015, "hole_y": 0.050 - 0.015},
    ),
]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def main() -> int:
    STEP_DIR.mkdir(parents=True, exist_ok=True)
    PNG_DIR.mkdir(parents=True, exist_ok=True)

    briefs = []
    for spec in SPECS:
        print(f"[build] {spec.brief_id}")
        shape = spec.build_fn(**spec.build_kwargs)
        step_path = STEP_DIR / f"{spec.brief_id}.step"
        png_path = PNG_DIR / f"{spec.brief_id}.png"
        write_step(shape, step_path)
        render_iso_png(shape, png_path)
        briefs.append({
            "brief_id": spec.brief_id,
            "brief_text": spec.brief_text,
            "brief_text_hash": text_hash(spec.brief_text),
            "brief_image_path": None,
            "reference_step_path": str(step_path.relative_to(MANIFEST_PATH.parent)),
            "reference_png_path": str(png_path.relative_to(MANIFEST_PATH.parent)),
            "source_dataset": "seed",
            "difficulty_tier": spec.difficulty_tier,
        })

    manifest = {
        "manifest_version": 1,
        "n_briefs": len(briefs),
        "source_sets": ["seed"],
        "note": (
            "Phase-0 seed set. 10 procedurally-generated simple parts. "
            "Expand with DeepCAD / CADPrompt conversions in later phases; "
            "bump manifest_version when you do."
        ),
        "briefs": briefs,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"\n[manifest] {MANIFEST_PATH}  ({len(briefs)} briefs)")
    print(f"[steps]    {STEP_DIR}")
    print(f"[renders]  {PNG_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
