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
from pathlib import Path

from eval.bootstrap_seed import render_iso_png, text_hash
from eval.grader.compare_step import bbox, load_step


MM_DIR = Path(__file__).parent / "datasets" / "modelmania"
RAW_DIR = MM_DIR / "step_raw"
OUT_STEP = MM_DIR / "step"
OUT_ISO = MM_DIR / "iso"
MANIFEST_PATH = Path(__file__).parent / "datasets" / "MANIFEST.json"


PARTS = [
    ("mm_2009_phase1", "Model Mania 2009 (Phase 1).stp",
     "SolidWorks Model Mania 2009 – Phase 1"),
    ("mm_2019_phase1", "Model Mania 2019 (Phase 1).stp",
     "SolidWorks Model Mania 2019 – Phase 1"),
    ("mm_2022_phase1", "Model Mania 2022 (Phase 1).stp",
     "SolidWorks Model Mania 2022 – Phase 1"),
    ("mm_2025_phase1", "Model Mania 2025 (Phase 1).stp",
     "SolidWorks Model Mania 2025 – Phase 1"),
    ("mm_2026_jan", "Model Mania January 2026.stp",
     "SolidWorks Model Mania January 2026"),
]


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
    for slug, raw_name, part_name in PARTS:
        src = RAW_DIR / raw_name
        if not src.exists():
            print(f"[skip] {slug}: missing {src}")
            continue
        step_out = OUT_STEP / f"{slug}.step"
        shutil.copy(src, step_out)
        shape = load_step(step_out)
        b = bbox(shape)
        iso_out = OUT_ISO / f"{slug}.png"
        print(f"[{slug}] {part_name}  bbox=({b.dx:.1f},{b.dy:.1f},{b.dz:.1f}) mm")
        render_iso_png(shape, iso_out, size=800)

        brief_id = f"{slug}_envelope"
        if brief_id in existing_ids:
            continue
        txt = envelope_brief(part_name, b)
        new_briefs.append({
            "brief_id": brief_id,
            "brief_modality": "render_plus_envelope",
            "brief_text": txt,
            "brief_text_hash": text_hash(txt),
            "brief_image_path": str(iso_out.relative_to(MANIFEST_PATH.parent)),
            "reference_step_path": str(step_out.relative_to(MANIFEST_PATH.parent)),
            "reference_png_path": str(iso_out.relative_to(MANIFEST_PATH.parent)),
            "source_dataset": "modelmania",
            "difficulty_tier": "hard",
            "notes": (
                "SolidWorks Model Mania competition Phase 1 part. Non-obvious "
                "compound geometry intended to challenge skilled human CAD users "
                "under time pressure. No accompanying drawing — evaluate via "
                "shape replication against the STEP ground truth."
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
