"""Layered CAD grading rubric — LOCKED.

Composite score ∈ [0, 1]. Hard gate at L0 (body must exist). Upper layers
contribute their weights if they pass the tolerance.

Weights and tolerances are specified in CLAUDE.md § "The grader". Any
change invalidates prior scoreboard entries.

Layer | Check                                    | Tolerance                | Weight
------+------------------------------------------+--------------------------+--------
  L0  | At least one solid body exists           | —                        | gate
  L1  | Volume ratio within ±5%                  | |va-vb|/vb < 0.05        | 0.15
  L2  | BBox diagonal within ±5%                 | |da-db|/db < 0.05        | 0.15
  L3  | Topology signature ratio                 | >= 0.80                  | 0.15
  L4  | Boolean IoU                              | >= 0.90                  | 0.35
  L5  | Chamfer distance                         | <= 0.02 * diag(ref)      | 0.20
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
# Sums to 1.0; L0 is a hard gate not a weighted contributor.
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

TOL_VOLUME = 0.05          # ±5% volume
TOL_BBOX_DIAG = 0.05       # ±5% bbox diagonal
MIN_TOPOLOGY_RATIO = 0.80  # topology similarity
MIN_BOOL_IOU = 0.90
MAX_CHAMFER_FRACTION = 0.02  # of ref bbox diagonal


@dataclass
class LayerResult:
    name: str
    passed: bool
    measurement: float
    tolerance: str
    detail: str = ""


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
                    "passed": r.passed,
                    "measurement": r.measurement,
                    "tolerance": r.tolerance,
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
    l0_pass = va > 1e-15
    result.layers["L0"] = LayerResult(
        name="body_exists",
        passed=l0_pass,
        measurement=va,
        tolerance="> 1e-15 m^3",
        detail=f"agent volume={va:.6g} m^3",
    )
    if not l0_pass:
        result.notes.append("agent produced no solid body; composite=0")
        return result

    # L1 — volume ratio.
    if vr == 0:
        l1_measurement = float("inf") if va != 0 else 0.0
        l1_pass = False
    else:
        l1_measurement = abs(va - vr) / vr
        l1_pass = l1_measurement < TOL_VOLUME
    result.layers["L1"] = LayerResult(
        name="volume_ratio",
        passed=l1_pass,
        measurement=l1_measurement,
        tolerance=f"< {TOL_VOLUME}",
        detail=f"va={va:.6g} vr={vr:.6g}",
    )

    # L2 — bounding-box diagonal ratio.
    ba = bbox(a)
    br = bbox(r)
    diag_a = ba.diagonal
    diag_r = br.diagonal
    if diag_r == 0:
        l2_measurement = float("inf") if diag_a != 0 else 0.0
        l2_pass = False
    else:
        l2_measurement = abs(diag_a - diag_r) / diag_r
        l2_pass = l2_measurement < TOL_BBOX_DIAG
    result.layers["L2"] = LayerResult(
        name="bbox_diagonal",
        passed=l2_pass,
        measurement=l2_measurement,
        tolerance=f"< {TOL_BBOX_DIAG}",
        detail=f"diag_a={diag_a:.6g}m diag_r={diag_r:.6g}m",
    )

    # L3 — topology signature ratio.
    ta = topology_signature(a)
    tr = topology_signature(r)
    l3_ratio = ta.ratio(tr)
    l3_pass = l3_ratio >= MIN_TOPOLOGY_RATIO
    result.layers["L3"] = LayerResult(
        name="topology_ratio",
        passed=l3_pass,
        measurement=l3_ratio,
        tolerance=f">= {MIN_TOPOLOGY_RATIO}",
        detail=f"agent={ta} ref={tr}",
    )

    # L4 — boolean IoU. Expensive; only run if L1+L2 were roughly in ballpark
    # (big size/volume mismatch → IoU is guaranteed bad, skip the compute).
    if l1_measurement > 0.5 or l2_measurement > 0.5:
        l4_iou = 0.0
        result.notes.append("L4 skipped: volume or bbox off by >50%")
    else:
        # Align: we do NOT re-center or re-orient. If the agent built the
        # part at a different origin, IoU will flag it — which is a real
        # failure mode (the agent was asked to build at a specific pose).
        try:
            l4_iou = boolean_iou(a, r)
        except Exception as e:
            result.notes.append(f"L4 compute failed: {e}")
            l4_iou = 0.0
    l4_pass = l4_iou >= MIN_BOOL_IOU
    result.layers["L4"] = LayerResult(
        name="boolean_iou",
        passed=l4_pass,
        measurement=l4_iou,
        tolerance=f">= {MIN_BOOL_IOU}",
    )

    # L5 — Chamfer distance. Only run if L4 was in ballpark (if volumes
    # don't overlap, Chamfer will be huge and uninformative).
    if l4_iou < 0.5:
        l5_chamfer = float("inf")
        l5_pass = False
        result.notes.append("L5 skipped: L4 IoU too low")
    else:
        try:
            l5_chamfer = chamfer_distance(a, r)
        except Exception as e:
            result.notes.append(f"L5 compute failed: {e}")
            l5_chamfer = float("inf")
        threshold = MAX_CHAMFER_FRACTION * diag_r
        l5_pass = l5_chamfer <= threshold
    result.layers["L5"] = LayerResult(
        name="chamfer_distance",
        passed=l5_pass,
        measurement=l5_chamfer,
        tolerance=f"<= {MAX_CHAMFER_FRACTION} * diag_ref",
        detail=f"chamfer={l5_chamfer:.6g}m diag_ref={diag_r:.6g}m",
    )

    # Composite = weighted sum of passed upper layers (L1..L5).
    composite = 0.0
    for key, w in WEIGHTS.items():
        if result.layers[key].passed:
            composite += w
    result.composite = composite
    return result
