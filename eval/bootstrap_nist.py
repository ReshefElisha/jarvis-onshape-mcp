"""Pull NIST MBE PMI Test Cases into the eval manifest.

Each NIST part yields TWO briefs in the manifest:

  1. `engineering_drawing` modality — the drawing PDF rendered to PNG.
     Hard: agent must read GD&T, dimensions, tolerances from the sheet.
  2. `render_plus_envelope` modality — an iso render of the reference
     STEP + a short text spec with only the bounding-box envelope.
     Soft: "replicate this shape roughly at these dimensions." No GD&T.

11 CTC/FTC parts → 22 briefs. Skips STC (STEP-only, no drawings).

Run:
    source eval/.venv/bin/activate
    PYTHONPATH=. python eval/bootstrap_nist.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Tuple

import pypdfium2 as pdfium

from eval.bootstrap_seed import render_iso_png, text_hash
from eval.grader.compare_step import bbox, load_step, volume


NIST_DIR = Path(__file__).parent / "datasets" / "nist_pmi"
STEP_SRC = NIST_DIR / "NIST-PMI-STEP-Files"
PDF_SRC = STEP_SRC / "PDF"

OUT_STEP = NIST_DIR / "step"
OUT_ISO = NIST_DIR / "iso"
OUT_DRAWING = NIST_DIR / "drawing"
MANIFEST_PATH = Path(__file__).parent / "datasets" / "MANIFEST.json"


# (brief_slug, step_filename, pdf_filename, human_part_name)
NIST_PARTS: list[Tuple[str, str, str, str]] = [
    ("nist_ctc_01", "nist_ctc_01_asme1_ap242-e1.stp", "nist_ctc_01_asme1_rd.pdf",
     "CTC 01 – complex plate with through-holes, counterbore, and hex pocket"),
    ("nist_ctc_02", "nist_ctc_02_asme1_ap242-e2.stp", "nist_ctc_02_asme1_rc.pdf",
     "CTC 02 – complex part with line-profile tolerance"),
    ("nist_ctc_03", "nist_ctc_03_asme1_ap242-e2.stp", "nist_ctc_03_asme1_rc.pdf",
     "CTC 03 – complex mechanical part with interacting features"),
    ("nist_ctc_04", "nist_ctc_04_asme1_ap242-e1.stp", "nist_ctc_04_asme1_rd.pdf",
     "CTC 04 – complex part with basic dimensions"),
    ("nist_ctc_05", "nist_ctc_05_asme1_ap242-e1.stp", "nist_ctc_05_asme1_rd.pdf",
     "CTC 05 – complex part, basic dimensions (no surface or position tols)"),
    ("nist_ftc_06", "nist_ftc_06_asme1_ap242-e2.stp", "nist_ftc_06_asme1_rd.pdf",
     "FTC 06 – fully-toleranced test part"),
    ("nist_ftc_07", "nist_ftc_07_asme1_ap242-e2.stp", "nist_ftc_07_asme1_rd.pdf",
     "FTC 07 – fully-toleranced test part"),
    ("nist_ftc_08", "nist_ftc_08_asme1_ap242-e2.stp", "nist_ftc_08_asme1_rc.pdf",
     "FTC 08 – fully-toleranced test part with parallelism tolerances"),
    ("nist_ftc_09", "nist_ftc_09_asme1_ap242-e1.stp", "nist_ftc_09_asme1_rd.pdf",
     "FTC 09 – fully-toleranced test part"),
    ("nist_ftc_10", "nist_ftc_10_asme1_ap242-e2.stp", "nist_ftc_10_asme1_rb.pdf",
     "FTC 10 – fully-toleranced test part"),
    ("nist_ftc_11", "nist_ftc_11_asme1_ap242-e2.stp", "nist_ftc_11_asme1_rb.pdf",
     "FTC 11 – fully-toleranced test part"),
]


def rasterize_pdf(pdf_path: Path, out_path: Path, scale: float = 2.5) -> None:
    """PDF → PNG at a scale that keeps annotation text legible."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    bm = pdf[0].render(scale=scale)
    img = bm.to_pil()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def envelope_brief(part_name: str, b) -> str:
    """Brief that gives ONLY the envelope + iso — no GD&T, no tolerances.

    Dimensions are the STEP's bounding box in mm, rounded. The agent's
    job is to match the geometry shape; exact dimensions are open.
    """
    dx, dy, dz = b.dx, b.dy, b.dz  # bbox is already in mm
    return (
        f"Build the mechanical part shown in the reference isometric render. "
        f"The part fits inside an approximately {dx:.0f} × {dy:.0f} × {dz:.0f} mm "
        f"axis-aligned bounding box. Match the shape and feature layout as "
        f"closely as possible — exact dimensions are at your discretion, "
        f"but proportions and feature placement should match the render. "
        f"({part_name})"
    )


def drawing_brief(part_name: str) -> str:
    return (
        f"Build the mechanical part specified by the attached engineering "
        f"drawing sheet. The drawing uses ASME Y14 conventions: read the "
        f"orthographic views, dimensions, tolerances, and any GD&T "
        f"feature-control frames carefully. Match every dimension and "
        f"feature placement. ({part_name})"
    )


def main() -> int:
    OUT_STEP.mkdir(parents=True, exist_ok=True)
    OUT_ISO.mkdir(parents=True, exist_ok=True)
    OUT_DRAWING.mkdir(parents=True, exist_ok=True)

    # Load existing manifest (seed tier) and append NIST entries.
    manifest = json.loads(MANIFEST_PATH.read_text())
    existing_briefs = manifest.get("briefs", [])

    new_briefs = []
    for slug, step_name, pdf_name, part_name in NIST_PARTS:
        src_step = STEP_SRC / step_name
        src_pdf = PDF_SRC / pdf_name
        print(f"[{slug}] {part_name}")

        # Copy STEP to our canonical location.
        step_out = OUT_STEP / f"{slug}.step"
        step_out.write_bytes(src_step.read_bytes())

        # Iso render from the STEP.
        shape = load_step(step_out)
        b = bbox(shape)
        iso_out = OUT_ISO / f"{slug}.png"
        render_iso_png(shape, iso_out, size=800)

        # Drawing PDF → PNG.
        drawing_out = OUT_DRAWING / f"{slug}.png"
        rasterize_pdf(src_pdf, drawing_out, scale=2.5)

        # Brief #1: engineering drawing modality.
        drawing_text = drawing_brief(part_name)
        new_briefs.append({
            "brief_id": f"{slug}_drawing",
            "brief_modality": "engineering_drawing",
            "brief_text": drawing_text,
            "brief_text_hash": text_hash(drawing_text),
            "brief_image_path": str(drawing_out.relative_to(MANIFEST_PATH.parent)),
            "reference_step_path": str(step_out.relative_to(MANIFEST_PATH.parent)),
            "reference_png_path": str(iso_out.relative_to(MANIFEST_PATH.parent)),
            "source_dataset": "nist_pmi",
            "difficulty_tier": "hard",
            "notes": (
                "Engineering drawing with GD&T, tolerances, feature-control "
                "frames. Volume L4/L5 grading should tolerate ±5% since the "
                "agent may interpret nominal dimensions within tolerance."
            ),
        })

        # Brief #2: render + envelope modality (easier, no GD&T).
        env_text = envelope_brief(part_name, b)
        new_briefs.append({
            "brief_id": f"{slug}_envelope",
            "brief_modality": "render_plus_envelope",
            "brief_text": env_text,
            "brief_text_hash": text_hash(env_text),
            "brief_image_path": str(iso_out.relative_to(MANIFEST_PATH.parent)),
            "reference_step_path": str(step_out.relative_to(MANIFEST_PATH.parent)),
            "reference_png_path": str(iso_out.relative_to(MANIFEST_PATH.parent)),
            "source_dataset": "nist_pmi",
            "difficulty_tier": "medium",
            "notes": (
                "Same NIST part as the _drawing variant, but the brief only "
                "gives the iso render + bbox envelope. Tests shape replication "
                "without dimensional rigor. L4/L5 thresholds should be relaxed "
                "since 'match the shape' invites proportional scaling."
            ),
        })

    merged = existing_briefs + new_briefs
    manifest["manifest_version"] = 2
    manifest["n_briefs"] = len(merged)
    manifest["source_sets"] = sorted(set(b["source_dataset"] for b in merged))
    manifest["note"] = (
        "v2 — added 22 NIST PMI briefs on top of the v1 seed. Each of "
        "11 NIST parts yields 2 briefs: one engineering-drawing tier "
        "(hard, GD&T) and one render+envelope tier (medium). Seed tier "
        "kept for plumbing/baseline but should NOT be averaged into "
        "scoreboard composite — agents will ceiling-score it."
    )
    manifest["briefs"] = merged
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))

    print(f"\n[manifest] v{manifest['manifest_version']}  "
          f"{manifest['n_briefs']} briefs "
          f"(sources: {manifest['source_sets']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
