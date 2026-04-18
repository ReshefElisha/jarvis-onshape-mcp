"""Pull Shef's downloaded SolidWorks Model Mania parts into the manifest.

Each Model Mania STEP becomes a brief with `render_plus_envelope` modality:
iso render + short spec with bbox envelope. No drawings (drawing PDFs
not bundled with the competition STEP downloads).

Run:
    PYTHONPATH=. eval/.venv/bin/python eval/bootstrap_modelmania.py
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

import math

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf

from eval.bootstrap_seed import render_iso_png, text_hash
from eval.bootstrap_nist import rasterize_pdf
from eval.grader.compare_step import bbox, load_step


def _rotate_shape(shape, axis: str, degrees: float):
    """Rotate a shape about a world-axis-aligned line THROUGH ITS BBOX CENTER.

    Rotating about the origin when the part is offset from origin mixes
    rotation with translation — visually the part swings to a new
    position, which isn't what we want. We want in-place reorientation,
    so anchor the rotation axis at the part's centroid.
    """
    dir_map = {"X": (1.0, 0.0, 0.0),
               "Y": (0.0, 1.0, 0.0),
               "Z": (0.0, 0.0, 1.0)}
    if axis not in dir_map:
        raise ValueError(f"rotate_axis must be X|Y|Z, got {axis!r}")
    b = bbox(shape)
    cx = (b.xmin + b.xmax) / 2
    cy = (b.ymin + b.ymax) / 2
    cz = (b.zmin + b.zmax) / 2
    trsf = gp_Trsf()
    trsf.SetRotation(gp_Ax1(gp_Pnt(cx, cy, cz), gp_Dir(*dir_map[axis])),
                     math.radians(degrees))
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def _write_step(shape, path):
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    status = writer.Write(str(path))
    if status != IFSelect_RetDone:
        raise IOError(f"STEP write failed: {path} status={status}")


MM_DIR = Path(__file__).parent / "datasets" / "modelmania"
RAW_DIR = MM_DIR / "step_raw"
DRAWING_RAW_DIR = MM_DIR / "drawing_raw"
OUT_STEP = MM_DIR / "step"
OUT_ISO = MM_DIR / "iso"
OUT_DRAWING = MM_DIR / "drawing"
MANIFEST_PATH = Path(__file__).parent / "datasets" / "MANIFEST.json"


@dataclass
class MMPart:
    slug: str
    step_file: str
    display_name: str
    drawing_source: Optional[str]  # filename in drawing_raw/, or None if missing
    views: tuple = ("iso", "front", "top", "right")
    # Optional pre-render orientation fix. `rotate_axis` is 'X' | 'Y' | 'Z'
    # (world); `rotate_deg` is the rotation magnitude. Applied before
    # writing the normalized STEP + rendering.
    rotate_axis: Optional[str] = None
    rotate_deg: float = 0.0


PARTS = [
    # 2009, 2019, 2022: default iso angle hides the more-interesting face.
    # Use iso_flip (back-side isometric) as the hero view.
    MMPart("mm_2009_phase1", "Model Mania 2009 (Phase 1).stp",
           "SolidWorks Model Mania 2009 – Phase 1",
           "mm_2009_phase1.jpg",
           views=("iso_flip", "front", "top", "right")),
    MMPart("mm_2019_phase1", "Model Mania 2019 (Phase 1).stp",
           "SolidWorks Model Mania 2019 – Phase 1",
           "mm_2019_phase1.png",
           views=("iso_flip", "front", "top", "right")),
    # ⚠ The zip "model-mania-2022-phase-1" actually contains the 2021 Phase 1
    # part (mislabeled by SolidWorks' snapshot export). Slug + drawing
    # corrected to 2021.
    MMPart("mm_2021_phase1", "Model Mania 2022 (Phase 1).stp",
           "SolidWorks Model Mania 2021 – Phase 1",
           "mm_2021_phase1.jpg",
           views=("iso_flip", "front", "top", "right"),
           rotate_axis="Y", rotate_deg=180.0),
    MMPart("mm_2025_phase1", "Model Mania 2025 (Phase 1).stp",
           "SolidWorks Model Mania 2025 – Phase 1",
           "mm_2025_phase1.pdf"),
    # 2026 geometry benefits from seeing both sides — substitute BACK for TOP.
    MMPart("mm_2026_jan", "Model Mania January 2026.stp",
           "SolidWorks Model Mania January 2026",
           None,
           views=("iso", "front", "back", "right")),
]


def drawing_brief(part_name: str) -> str:
    return (
        f"Build the mechanical part specified by the attached SolidWorks "
        f"Model Mania drawing sheet. Read the orthographic views, "
        f"dimensions, and any tolerances carefully; the drawing is the "
        f"ground truth for geometry. Model Mania competition parts are "
        f"designed to be non-obvious under time pressure — watch for "
        f"compound features whose dimensional interactions matter. "
        f"({part_name})"
    )


def copy_or_rasterize_drawing(src: Path, out_png: Path) -> None:
    """Normalize drawing input (PDF / PNG / JPG) to a single PNG target."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower()
    if ext == ".pdf":
        rasterize_pdf(src, out_png, scale=2.5)
    elif ext in (".png", ".jpg", ".jpeg"):
        # Re-encode as PNG for uniform downstream handling.
        Image.open(src).convert("RGB").save(out_png)
    else:
        raise ValueError(f"unsupported drawing extension {ext} for {src}")


def envelope_brief(part_name: str, b) -> str:
    dx, dy, dz = b.dx, b.dy, b.dz  # bbox is already in mm
    return (
        f"Build the mechanical part shown in the reference isometric render. "
        f"The part fits inside an approximately {dx:.0f} × {dy:.0f} × {dz:.0f} mm "
        f"axis-aligned bounding box. This is a SolidWorks Model Mania "
        f"competition part — expect compound features, thoughtful dimensional "
        f"relationships, and non-obvious interactions between geometry. "
        f"Match the shape and feature layout as closely as possible. "
        f"({part_name})"
    )


def main() -> int:
    OUT_STEP.mkdir(parents=True, exist_ok=True)
    OUT_ISO.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(MANIFEST_PATH.read_text())
    existing = manifest.get("briefs", [])
    existing_ids = {b["brief_id"] for b in existing}

    new_briefs = []
    for part in PARTS:
        slug = part.slug
        src = RAW_DIR / part.step_file
        if not src.exists():
            print(f"[skip] {slug}: missing {src}")
            continue
        step_out = OUT_STEP / f"{slug}.step"
        shutil.copy(src, step_out)
        shape = load_step(step_out)
        if part.rotate_axis is not None:
            shape = _rotate_shape(shape, part.rotate_axis, part.rotate_deg)
            # Overwrite step_out so the rotated shape becomes the canonical
            # reference — agent output will be graded against this orientation.
            _write_step(shape, step_out)
        b = bbox(shape)
        iso_out = OUT_ISO / f"{slug}.png"
        print(f"[{slug}] {part.display_name}  "
              f"bbox=({b.dx:.1f},{b.dy:.1f},{b.dz:.1f}) mm  "
              f"views={part.views}")
        render_iso_png(shape, iso_out, size=800, views=part.views)

        # If a source drawing (PDF/PNG/JPG) was downloaded, convert to a
        # single PNG and emit a second brief with drawing modality.
        drawing_png: Optional[Path] = None
        if part.drawing_source:
            src_drawing = DRAWING_RAW_DIR / part.drawing_source
            if src_drawing.exists():
                drawing_png = OUT_DRAWING / f"{slug}.png"
                copy_or_rasterize_drawing(src_drawing, drawing_png)
            else:
                print(f"  [warn] drawing source {src_drawing} missing, skipping drawing brief")

        # Envelope brief (render + bbox only).
        env_id = f"{slug}_envelope"
        if env_id not in existing_ids:
            env_txt = envelope_brief(part.display_name, b)
            new_briefs.append({
                "brief_id": env_id,
                "brief_modality": "render_plus_envelope",
                "brief_text": env_txt,
                "brief_text_hash": text_hash(env_txt),
                "brief_image_path": str(iso_out.relative_to(MANIFEST_PATH.parent)),
                "reference_step_path": str(step_out.relative_to(MANIFEST_PATH.parent)),
                "reference_png_path": str(iso_out.relative_to(MANIFEST_PATH.parent)),
                "source_dataset": "modelmania",
                "difficulty_tier": "hard",
                "notes": (
                    "SolidWorks Model Mania competition part. Non-obvious "
                    "compound geometry intended to challenge skilled human CAD "
                    "users under time pressure. Render+envelope tier: evaluate "
                    "via shape replication against the STEP."
                ),
            })

        # Drawing brief (GD&T / orthographic problem sheet).
        if drawing_png is not None:
            dr_id = f"{slug}_drawing"
            if dr_id not in existing_ids:
                dr_txt = drawing_brief(part.display_name)
                new_briefs.append({
                    "brief_id": dr_id,
                    "brief_modality": "engineering_drawing",
                    "brief_text": dr_txt,
                    "brief_text_hash": text_hash(dr_txt),
                    "brief_image_path": str(drawing_png.relative_to(MANIFEST_PATH.parent)),
                    "reference_step_path": str(step_out.relative_to(MANIFEST_PATH.parent)),
                    "reference_png_path": str(iso_out.relative_to(MANIFEST_PATH.parent)),
                    "source_dataset": "modelmania",
                    "difficulty_tier": "hard",
                    "notes": (
                        "SolidWorks Model Mania problem drawing sourced from "
                        "the official archive. Dimensional rigor expected — "
                        "match the drawing, not just the overall shape."
                    ),
                })

    merged = existing + new_briefs
    manifest["manifest_version"] = 3
    manifest["n_briefs"] = len(merged)
    manifest["source_sets"] = sorted(set(b["source_dataset"] for b in merged))
    manifest["note"] = (
        "v3 — added 4 SolidWorks Model Mania parts on top of v2 (22 NIST + "
        "10 seed). Model Mania parts are envelope-only briefs (no drawings) "
        "at hard difficulty. Seed tier is for plumbing/baseline and should "
        "NOT be averaged into scoreboard composite."
    )
    manifest["briefs"] = merged
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"\n[manifest] v3 — {manifest['n_briefs']} briefs "
          f"(sources: {manifest['source_sets']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
