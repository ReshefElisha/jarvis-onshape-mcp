"""Layered CAD grading rubric — LOCKED.

Composite score ∈ [0, 1]. Hard gate at L0 (body must exist). Upper layers
contribute their weights proportionally — each layer's contribution
scales linearly between a FLOOR (scores 0) and a CEILING (scores full
weight). A "skilled human simplification" that gets the shape right but
misses fine details (e.g. sub-mm fillets) earns partial credit per
layer instead of falling off a cliff at a binary threshold.

Layer | Metric                                | Floor (0 pts)      | Ceiling (full pts) | Weight
------+---------------------------------------+--------------------+--------------------+--------
  L0  | Body exists                           | —                  | —                  | gate
  L1  | Volume relative error                 | ≥ 0.20             | ≤ 0.02             | 0.15
  L2  | BBox-diagonal relative error          | ≥ 0.20             | ≤ 0.02             | 0.15
  L3  | Topology signature ratio              | ≤ 0.40             | ≥ 0.90             | 0.15
  L4  | Boolean IoU                           | ≤ 0.30             | ≥ 0.95             | 0.35
  L5  | Chamfer / ref_diag                    | ≥ 0.05             | ≤ 0.005            | 0.20
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from .compare_step import (
    bbox,
    boolean_iou,
    chamfer_distance,
    load_step,
    topology_signature,
    volume,
)


WEIGHTS = {
    "L1": 0.15,
    "L2": 0.15,
    "L3": 0.15,
    "L4": 0.35,
    "L5": 0.20,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

# (floor, ceiling) per layer. `floor` = the worst measurement still worth
# any points; `ceiling` = the measurement at which the layer earns full
# weight. Scoring is linear in between. Direction per layer handled by
# the scorer below.
BANDS = {
    "L1": (0.20, 0.02),    # volume relative error — LOWER is better
    "L2": (0.20, 0.02),    # bbox-diagonal relative error — LOWER is better
    "L3": (0.40, 0.90),    # topology similarity ratio — HIGHER is better
    "L4": (0.30, 0.95),    # Boolean IoU — HIGHER is better
    "L5": (0.05, 0.005),   # Chamfer / ref_diag — LOWER is better
}


def _linear_fraction(measurement: float, floor: float, ceiling: float) -> float:
    """Linear interpolation [0, 1] between floor and ceiling.

    If floor > ceiling, "lower is better" (floor is worst, ceiling is best).
    If floor < ceiling, "higher is better". Measurement outside the band
    clamps to 0 or 1.
    """
    if floor == ceiling:
        return 1.0 if measurement == ceiling else 0.0
    if floor > ceiling:
        # Lower is better.
        if measurement >= floor:
            return 0.0
        if measurement <= ceiling:
            return 1.0
        return (floor - measurement) / (floor - ceiling)
    else:
        # Higher is better.
        if measurement <= floor:
            return 0.0
        if measurement >= ceiling:
            return 1.0
        return (measurement - floor) / (ceiling - floor)


@dataclass
class LayerResult:
    name: str
    measurement: float
    fraction: float          # in [0, 1]; weighted into the composite
    band: str                # human-readable floor→ceiling description
    detail: str = ""

    @property
    def passed(self) -> bool:
        """Back-compat flag: True iff the layer earned any credit."""
        return self.fraction > 0.0


@dataclass
class RubricResult:
    composite: float
    layers: Dict[str, LayerResult] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "composite": self.composite,
            "layers": {
                name: {
                    "measurement": r.measurement,
                    "fraction": r.fraction,
                    "band": r.band,
                    "detail": r.detail,
                }
                for name, r in self.layers.items()
            },
            "notes": self.notes,
        }


def score_step_pair(agent_step_path: str | Path,
                    reference_step_path: str | Path) -> RubricResult:
    """Grade an agent-produced STEP against a reference STEP.

    Returns RubricResult with composite ∈ [0, 1]. Hard fails (no solid,
    unreadable file, etc.) → composite = 0.0 with a note explaining why.
    """
    result = RubricResult(composite=0.0)
    try:
        a = load_step(agent_step_path)
        r = load_step(reference_step_path)
    except Exception as e:
        result.notes.append(f"load failed: {e}")
        return result

    va = volume(a)
    vr = volume(r)

    # L0 — body exists (agent must have produced a solid with volume).
    l0_exists = va > 1e-15
    result.layers["L0"] = LayerResult(
        name="body_exists",
        measurement=va,
        fraction=1.0 if l0_exists else 0.0,
        band="> 1e-15 mm^3",
        detail=f"agent volume={va:.6g} mm^3",
    )
    if not l0_exists:
        result.notes.append("agent produced no solid body; composite=0")
        return result

    # L1 — volume relative error (lower is better).
    if vr == 0:
        l1_err = float("inf") if va != 0 else 0.0
    else:
        l1_err = abs(va - vr) / vr
    floor1, ceil1 = BANDS["L1"]
    result.layers["L1"] = LayerResult(
        name="volume_relative_error",
        measurement=l1_err,
        fraction=_linear_fraction(l1_err, floor1, ceil1),
        band=f"floor={floor1}  ceiling={ceil1}",
        detail=f"va={va:.6g} vr={vr:.6g}",
    )

    # L2 — bounding-box diagonal relative error (lower is better).
    ba = bbox(a)
    br = bbox(r)
    diag_a = ba.diagonal
    diag_r = br.diagonal
    if diag_r == 0:
        l2_err = float("inf") if diag_a != 0 else 0.0
    else:
        l2_err = abs(diag_a - diag_r) / diag_r
    floor2, ceil2 = BANDS["L2"]
    result.layers["L2"] = LayerResult(
        name="bbox_diag_relative_error",
        measurement=l2_err,
        fraction=_linear_fraction(l2_err, floor2, ceil2),
        band=f"floor={floor2}  ceiling={ceil2}",
        detail=f"diag_a={diag_a:.6g}mm diag_r={diag_r:.6g}mm",
    )

    # L3 — topology signature ratio (higher is better).
    ta = topology_signature(a)
    tr = topology_signature(r)
    l3_ratio = ta.ratio(tr)
    floor3, ceil3 = BANDS["L3"]
    result.layers["L3"] = LayerResult(
        name="topology_ratio",
        measurement=l3_ratio,
        fraction=_linear_fraction(l3_ratio, floor3, ceil3),
        band=f"floor={floor3}  ceiling={ceil3}",
        detail=f"agent={ta} ref={tr}",
    )

    # L4 — Boolean IoU (higher is better).
    # Skip the expensive Boolean ops if L1/L2 say the sizes are wildly off.
    if l1_err > 0.5 or l2_err > 0.5:
        l4_iou = 0.0
        result.notes.append("L4 skipped: volume or bbox off by >50%")
    else:
        try:
            l4_iou = boolean_iou(a, r)
        except Exception as e:
            result.notes.append(f"L4 compute failed: {e}")
            l4_iou = 0.0
    floor4, ceil4 = BANDS["L4"]
    result.layers["L4"] = LayerResult(
        name="boolean_iou",
        measurement=l4_iou,
        fraction=_linear_fraction(l4_iou, floor4, ceil4),
        band=f"floor={floor4}  ceiling={ceil4}",
    )

    # L5 — Chamfer distance, normalized by ref bbox diagonal (lower is better).
    if l4_iou < 0.30:
        l5_norm = float("inf")
        result.notes.append("L5 skipped: L4 IoU below floor, Chamfer uninformative")
    else:
        try:
            chamfer_raw = chamfer_distance(a, r)
            l5_norm = chamfer_raw / diag_r if diag_r else float("inf")
        except Exception as e:
            result.notes.append(f"L5 compute failed: {e}")
            l5_norm = float("inf")
    floor5, ceil5 = BANDS["L5"]
    result.layers["L5"] = LayerResult(
        name="chamfer_over_diag",
        measurement=l5_norm,
        fraction=_linear_fraction(l5_norm, floor5, ceil5),
        band=f"floor={floor5}  ceiling={ceil5}",
        detail=f"chamfer/diag_ref={l5_norm:.6g}",
    )

    # Composite = Σ (layer_weight × layer_fraction).
    composite = 0.0
    for key, w in WEIGHTS.items():
        composite += w * result.layers[key].fraction
    result.composite = composite
    return result
