"""Assembly interference detection using AABB overlap checks."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

METERS_TO_INCHES = 1.0 / 0.0254


@dataclass
class BoundingBox:
    """Axis-aligned bounding box in meters."""

    low_x: float
    low_y: float
    low_z: float
    high_x: float
    high_y: float
    high_z: float

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "BoundingBox":
        """Create from Onshape API response dict."""
        return cls(
            low_x=data["lowX"],
            low_y=data["lowY"],
            low_z=data["lowZ"],
            high_x=data["highX"],
            high_y=data["highY"],
            high_z=data["highZ"],
        )


@dataclass
class OverlapInfo:
    """Details about an overlap between two instances."""

    instance_a_name: str
    instance_a_id: str
    instance_b_name: str
    instance_b_id: str
    overlap_x_inches: float
    overlap_y_inches: float
    overlap_z_inches: float
    overlap_volume_cubic_inches: float


@dataclass
class InterferenceResult:
    """Complete result of an interference check."""

    total_instances: int
    total_pairs_checked: int
    overlaps: List[OverlapInfo] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def transform_point(
    matrix: List[float], point: Tuple[float, float, float]
) -> Tuple[float, float, float]:
    """Apply a 4x4 row-major transformation matrix to a 3D point.

    Args:
        matrix: 16-element row-major 4x4 transform matrix
        point: (x, y, z) coordinates

    Returns:
        Transformed (x, y, z) coordinates
    """
    x, y, z = point
    new_x = matrix[0] * x + matrix[1] * y + matrix[2] * z + matrix[3]
    new_y = matrix[4] * x + matrix[5] * y + matrix[6] * z + matrix[7]
    new_z = matrix[8] * x + matrix[9] * y + matrix[10] * z + matrix[11]
    return (new_x, new_y, new_z)


def get_world_aabb(local_bbox: BoundingBox, transform: List[float]) -> BoundingBox:
    """Compute world-space AABB by transforming all 8 corners of the local bbox.

    Correctly handles rotation: the resulting AABB encloses the rotated local
    box. For axis-aligned parts (no rotation), this produces exact results.
    For rotated parts, the result is conservative (may be slightly larger).

    Args:
        local_bbox: Bounding box in local/part coordinates (meters)
        transform: 16-element row-major 4x4 transform matrix

    Returns:
        World-space axis-aligned bounding box (meters)
    """
    corners = [
        (local_bbox.low_x, local_bbox.low_y, local_bbox.low_z),
        (local_bbox.low_x, local_bbox.low_y, local_bbox.high_z),
        (local_bbox.low_x, local_bbox.high_y, local_bbox.low_z),
        (local_bbox.low_x, local_bbox.high_y, local_bbox.high_z),
        (local_bbox.high_x, local_bbox.low_y, local_bbox.low_z),
        (local_bbox.high_x, local_bbox.low_y, local_bbox.high_z),
        (local_bbox.high_x, local_bbox.high_y, local_bbox.low_z),
        (local_bbox.high_x, local_bbox.high_y, local_bbox.high_z),
    ]

    transformed = [transform_point(transform, c) for c in corners]

    xs = [p[0] for p in transformed]
    ys = [p[1] for p in transformed]
    zs = [p[2] for p in transformed]

    return BoundingBox(
        low_x=min(xs), low_y=min(ys), low_z=min(zs),
        high_x=max(xs), high_y=max(ys), high_z=max(zs),
    )


def check_overlap(
    box_a: BoundingBox, box_b: BoundingBox, tolerance: float = 1e-8
) -> Optional[Tuple[float, float, float]]:
    """Check if two AABBs overlap in all three axes simultaneously.

    Args:
        box_a: First bounding box (meters)
        box_b: Second bounding box (meters)
        tolerance: Minimum overlap in meters to count as real (filters
            floating-point noise at touching boundaries). Default 1e-8m
            (~0.0000004 inches).

    Returns:
        (overlap_x, overlap_y, overlap_z) in meters if overlapping, else None.
    """
    overlap_x = min(box_a.high_x, box_b.high_x) - max(box_a.low_x, box_b.low_x)
    overlap_y = min(box_a.high_y, box_b.high_y) - max(box_a.low_y, box_b.low_y)
    overlap_z = min(box_a.high_z, box_b.high_z) - max(box_a.low_z, box_b.low_z)

    if overlap_x > tolerance and overlap_y > tolerance and overlap_z > tolerance:
        return (overlap_x, overlap_y, overlap_z)
    return None


async def check_assembly_interference(
    assembly_manager,
    partstudio_manager,
    document_id: str,
    workspace_id: str,
    element_id: str,
) -> InterferenceResult:
    """Run AABB interference check on an assembly.

    Fetches assembly definition and per-part bounding boxes, computes
    world-space AABBs, and checks all pairs for overlap.

    Args:
        assembly_manager: AssemblyManager instance
        partstudio_manager: PartStudioManager instance
        document_id: Assembly document ID
        workspace_id: Assembly workspace ID
        element_id: Assembly element ID

    Returns:
        InterferenceResult with overlap details
    """
    assembly_data = await assembly_manager.get_assembly_definition(
        document_id, workspace_id, element_id
    )
    root_assembly = assembly_data.get("rootAssembly", {})
    instances = root_assembly.get("instances", [])
    occurrences = root_assembly.get("occurrences", [])

    if len(instances) < 2:
        return InterferenceResult(
            total_instances=len(instances),
            total_pairs_checked=0,
            warnings=["Need at least 2 instances for interference check."],
        )

    # Build occurrence transform map (instance_id -> transform matrix)
    occurrence_transforms: Dict[str, List[float]] = {}
    for occ in occurrences:
        path = occ.get("path", [])
        if len(path) == 1:
            occurrence_transforms[path[0]] = occ.get("transform")

    # Fetch bounding boxes, cached by (doc_id, elem_id, part_id)
    bbox_cache: Dict[Tuple[str, str, str], BoundingBox] = {}

    for inst in instances:
        if inst.get("type") != "Part" or inst.get("suppressed", False):
            continue

        inst_doc_id = inst.get("documentId", document_id)
        inst_elem_id = inst.get("elementId")
        inst_part_id = inst.get("partId")

        if not inst_elem_id or not inst_part_id:
            continue

        cache_key = (inst_doc_id, inst_elem_id, inst_part_id)
        if cache_key not in bbox_cache:
            try:
                bbox_data = await partstudio_manager.get_part_bounding_box(
                    inst_doc_id, workspace_id, inst_elem_id, inst_part_id
                )
                bbox_cache[cache_key] = BoundingBox.from_api_response(bbox_data)
            except Exception as e:
                logger.warning(f"Could not get bbox for part {inst_part_id}: {e}")

    # Compute world-space AABBs
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    world_bboxes: List[Tuple[Dict[str, Any], BoundingBox]] = []

    for inst in instances:
        if inst.get("type") != "Part" or inst.get("suppressed", False):
            continue

        inst_doc_id = inst.get("documentId", document_id)
        inst_elem_id = inst.get("elementId")
        inst_part_id = inst.get("partId")
        cache_key = (inst_doc_id, inst_elem_id, inst_part_id)

        if cache_key not in bbox_cache:
            continue

        local_bbox = bbox_cache[cache_key]
        transform = occurrence_transforms.get(inst["id"], identity)
        world_bbox = get_world_aabb(local_bbox, transform)
        world_bboxes.append((inst, world_bbox))

    # Check all pairs
    result = InterferenceResult(
        total_instances=len(world_bboxes),
        total_pairs_checked=0,
    )

    for i in range(len(world_bboxes)):
        for j in range(i + 1, len(world_bboxes)):
            result.total_pairs_checked += 1
            inst_a, bbox_a = world_bboxes[i]
            inst_b, bbox_b = world_bboxes[j]

            overlap = check_overlap(bbox_a, bbox_b)
            if overlap is not None:
                ox, oy, oz = overlap
                result.overlaps.append(
                    OverlapInfo(
                        instance_a_name=inst_a.get("name", "Unknown"),
                        instance_a_id=inst_a["id"],
                        instance_b_name=inst_b.get("name", "Unknown"),
                        instance_b_id=inst_b["id"],
                        overlap_x_inches=ox * METERS_TO_INCHES,
                        overlap_y_inches=oy * METERS_TO_INCHES,
                        overlap_z_inches=oz * METERS_TO_INCHES,
                        overlap_volume_cubic_inches=(
                            (ox * METERS_TO_INCHES)
                            * (oy * METERS_TO_INCHES)
                            * (oz * METERS_TO_INCHES)
                        ),
                    )
                )

    return result


def format_interference_result(result: InterferenceResult) -> str:
    """Format an InterferenceResult into human-readable text.

    Args:
        result: The interference check result

    Returns:
        Formatted string for MCP tool response
    """
    lines = ["Assembly Interference Check Results", "=" * 40]

    if result.warnings:
        for w in result.warnings:
            lines.append(f"Warning: {w}")
        lines.append("")

    lines.append(
        f"Checked {result.total_instances} instances "
        f"({result.total_pairs_checked} pairs)"
    )
    lines.append("")

    if not result.overlaps:
        lines.append("No overlaps detected. All parts are properly spaced.")
    else:
        lines.append(f"FOUND {len(result.overlaps)} OVERLAP(S):")
        lines.append("")
        for i, ov in enumerate(result.overlaps, 1):
            lines.append(
                f'Overlap {i}: "{ov.instance_a_name}" and "{ov.instance_b_name}"'
            )
            lines.append(
                f"  Penetration: X={ov.overlap_x_inches:.3f}\", "
                f"Y={ov.overlap_y_inches:.3f}\", "
                f"Z={ov.overlap_z_inches:.3f}\""
            )
            lines.append(
                f"  Overlap volume: {ov.overlap_volume_cubic_inches:.3f} cubic inches"
            )

            # Suggest fix along axis with smallest overlap
            min_val = min(
                ov.overlap_x_inches, ov.overlap_y_inches, ov.overlap_z_inches
            )
            if min_val == ov.overlap_x_inches:
                axis = "X"
            elif min_val == ov.overlap_y_inches:
                axis = "Y"
            else:
                axis = "Z"
            lines.append(
                f"  Suggestion: Move one part {min_val:.3f}\" along {axis} to resolve"
            )
            lines.append("")

    lines.append("")
    lines.append(
        "Note: Uses AABB (axis-aligned bounding box) detection. "
        "Exact for axis-aligned rectangular parts. "
        "For rotated parts, may report false positives."
    )
    return "\n".join(lines)
