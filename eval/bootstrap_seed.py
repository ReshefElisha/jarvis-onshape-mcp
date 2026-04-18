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
    h = cylinder(hole_r, plate_dz + 2.0, hole_x, hole_y, -1.0)
    return subtract(p, h)


def plate_with_four_holes(dx: float, dy: float, dz: float,
                           hole_r: float, margin: float) -> TopoDS_Shape:
    p = box(dx, dy, dz)
    for hx, hy in [(margin, margin), (dx - margin, margin),
                   (margin, dy - margin), (dx - margin, dy - margin)]:
        h = cylinder(hole_r, dz + 2.0, hx, hy, -1.0)
        p = subtract(p, h)
    return p


def l_bracket(leg_length: float, leg_width: float, thickness: float) -> TopoDS_Shape:
    horiz = box(leg_length, leg_width, thickness)
    vert = box(thickness, leg_width, leg_length)
    return union(horiz, vert)


def standoff(od: float, id_: float, h: float) -> TopoDS_Shape:
    outer = cylinder(od / 2, h)
    inner = cylinder(id_ / 2, h + 2.0, z=-1.0)
    return subtract(outer, inner)


def washer(od: float, id_: float, h: float) -> TopoDS_Shape:
    return standoff(od, id_, h)


def slotted_strap(length: float, width: float, thickness: float,
                  slot_length: float, slot_width: float) -> TopoDS_Shape:
    strap = box(length, width, thickness)
    # Slot: two half-cylinders + rectangle. Simpler: use capped rectangle.
    slot_rect = box(slot_length - slot_width, slot_width, thickness + 2.0)
    slot_rect = translate(slot_rect, (length - (slot_length - slot_width)) / 2,
                          (width - slot_width) / 2, -1.0)
    cap_a = cylinder(slot_width / 2, thickness + 2.0,
                     (length - (slot_length - slot_width)) / 2, width / 2, -1.0)
    cap_b = cylinder(slot_width / 2, thickness + 2.0,
                     (length - (slot_length - slot_width)) / 2 + (slot_length - slot_width),
                     width / 2, -1.0)
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


_VIEW_CAMERAS = {
    # (position_vec_normalized, up_vec)  — all in world axes
    "iso":   ((0.8, -0.8, 0.6), (0.0, 0.0, 1.0)),
    "front": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    "top":   ((0.0, 0.0, 1.0),  (0.0, 1.0, 0.0)),
    "right": ((1.0, 0.0, 0.0),  (0.0, 0.0, 1.0)),
}


def _render_view(shape: TopoDS_Shape, view_name: str, size: int,
                 tris, edge_polylines) -> "vtk.vtkImageData":
    import vtk
    from eval.grader.compare_step import bbox as _bbox
    b = _bbox(shape)

    # Build scene.
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

    cleaner = vtk.vtkCleanPolyData()
    cleaner.SetInputData(polydata)
    cleaner.SetTolerance(1e-6)
    cleaner.Update()
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

    # View label as an overlay text in the top-left.
    label = vtk.vtkTextActor()
    label.SetInput(view_name.upper())
    tp = label.GetTextProperty()
    tp.SetFontSize(max(size // 24, 16))
    tp.SetColor(0.15, 0.15, 0.20)
    tp.SetBold(True)
    label.SetDisplayPosition(10, size - max(size // 22, 18) - 10)
    renderer.AddActor2D(label)

    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.AddRenderer(renderer)
    window.SetSize(size, size)

    cx, cy, cz = (b.xmin + b.xmax) / 2, (b.ymin + b.ymax) / 2, (b.zmin + b.zmax) / 2
    diag = max(b.diagonal, 1e-6)
    d = diag * 2.2
    dir_vec, up_vec = _VIEW_CAMERAS[view_name]
    cam = renderer.GetActiveCamera()
    cam.SetFocalPoint(cx, cy, cz)
    cam.SetPosition(cx + d * dir_vec[0], cy + d * dir_vec[1], cz + d * dir_vec[2])
    cam.SetViewUp(*up_vec)
    if view_name in ("front", "top", "right"):
        cam.ParallelProjectionOn()
    renderer.ResetCameraClippingRange()
    renderer.ResetCamera()
    window.Render()

    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(window)
    w2i.SetInputBufferTypeToRGB()
    w2i.ReadFrontBufferOff()
    w2i.Update()
    return w2i.GetOutput()


def render_iso_png(shape: TopoDS_Shape, path: Path, size: int = 800) -> None:
    """Render shape as a 2×2 multi-view composite (iso + front + top + right).

    Orthographic projections for front/top/right so dimensions can be
    read off the image. Perspective (iso) for the hero view.
    Composite is written to `path`. The filename keeps `_iso` for
    backward-compat with the manifest, but the content is a 4-panel
    montage.
    """
    from PIL import Image
    import numpy as np
    path.parent.mkdir(parents=True, exist_ok=True)
    from eval.grader.compare_step import bbox
    b = bbox(shape)
    diag = max(b.diagonal, 1e-6)
    tris = _tessellate_triangles(shape, diag * 0.002)
    if not tris:
        return
    edge_polylines = _tessellate_edges(shape, diag * 0.0005)

    panel = size // 2
    panels: dict[str, Image.Image] = {}
    for view in ("iso", "front", "top", "right"):
        img_data = _render_view(shape, view, panel, tris, edge_polylines)
        dims = img_data.GetDimensions()
        arr = np.frombuffer(
            img_data.GetPointData().GetScalars(), dtype=np.uint8
        ).reshape(dims[1], dims[0], -1)
        # VTK writes (0,0) at bottom-left; flip to image convention.
        arr = np.flipud(arr).copy()
        panels[view] = Image.fromarray(arr[:, :, :3])

    composite = Image.new("RGB", (size, size), (255, 255, 255))
    composite.paste(panels["iso"],   (0, 0))
    composite.paste(panels["front"], (panel, 0))
    composite.paste(panels["top"],   (0, panel))
    composite.paste(panels["right"], (panel, panel))
    composite.save(path)


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
        build_fn=box, build_kwargs={"dx": 40.0, "dy": 30.0, "dz": 20.0},
    ),
    BriefSpec(
        brief_id="seed_02_cube_25",
        brief_text=(
            "Build a 25 mm cube with one corner at the origin."
        ),
        difficulty_tier="trivial",
        build_fn=box, build_kwargs={"dx": 25.0, "dy": 25.0, "dz": 25.0},
    ),
    BriefSpec(
        brief_id="seed_03_cylinder_d20_h30",
        brief_text=(
            "Build a cylinder 20 mm in diameter and 30 mm tall. "
            "Axis along the world Z, base on the XY plane centered on the origin."
        ),
        difficulty_tier="trivial",
        build_fn=cylinder, build_kwargs={"r": 10.0, "h": 30.0},
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
        build_kwargs={"plate_dx": 60.0, "plate_dy": 40.0, "plate_dz": 5.0,
                      "hole_r": 4.0, "hole_x": 30.0, "hole_y": 20.0},
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
        build_kwargs={"dx": 80.0, "dy": 60.0, "dz": 6.0,
                      "hole_r": 2.0, "margin": 10.0},
    ),
    BriefSpec(
        brief_id="seed_06_washer",
        brief_text=(
            "Washer: outer diameter 30 mm, inner diameter 15 mm, thickness 3 mm. "
            "Axis along world Z, centered on origin."
        ),
        difficulty_tier="easy",
        build_fn=washer, build_kwargs={"od": 30.0, "id_": 15.0, "h": 0.003},
    ),
    BriefSpec(
        brief_id="seed_07_standoff",
        brief_text=(
            "Threaded-style standoff cylinder: outer diameter 10 mm, inner bore "
            "4 mm through, total height 25 mm. Axis along world Z, base on the "
            "XY plane centered on origin."
        ),
        difficulty_tier="easy",
        build_fn=standoff, build_kwargs={"od": 10.0, "id_": 4.0, "h": 25.0},
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
        build_kwargs={"leg_length": 50.0, "leg_width": 30.0, "thickness": 5.0},
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
        build_kwargs={"length": 60.0, "width": 20.0, "thickness": 4.0,
                      "slot_length": 40.0, "slot_width": 8.0},
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
        build_kwargs={"plate_dx": 50.0, "plate_dy": 50.0, "plate_dz": 10.0,
                      "hole_r": 6.0,
                      "hole_x": 50.0 - 15.0, "hole_y": 50.0 - 15.0},
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
