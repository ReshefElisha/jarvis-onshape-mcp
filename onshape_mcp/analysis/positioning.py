"""Assembly positioning tools for absolute placement and face alignment."""

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Union

from loguru import logger

from .interference import BoundingBox, get_world_aabb
from ..builders._units import parse_length

METERS_TO_MM = 1000.0

FACE_NAMES = {"front", "back", "left", "right", "top", "bottom"}

LengthLike = Union[float, int, str]


@dataclass
class InstancePositionInfo:
    """Position and extent information for a single assembly instance.

    All fields in millimeters (the post-[units-asm] convention).
    """

    name: str
    instance_id: str
    position_x_mm: float
    position_y_mm: float
    position_z_mm: float
    size_x_mm: float
    size_y_mm: float
    size_z_mm: float
    world_low_x_mm: float
    world_low_y_mm: float
    world_low_z_mm: float
    world_high_x_mm: float
    world_high_y_mm: float
    world_high_z_mm: float


def extract_occurrence_transforms(
    assembly_data: Dict[str, Any],
) -> Dict[str, List[float]]:
    """Extract instance_id -> transform matrix mapping from assembly data.

    Handles only top-level instances (path length == 1).

    Args:
        assembly_data: Raw assembly definition from API

    Returns:
        Dict mapping instance ID to 16-element row-major transform
    """
    occurrence_transforms: Dict[str, List[float]] = {}
    root = assembly_data.get("rootAssembly", {})
    for occ in root.get("occurrences", []):
        path = occ.get("path", [])
        if len(path) == 1:
            occurrence_transforms[path[0]] = occ.get(
                "transform",
                [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
            )
    return occurrence_transforms


def get_position_from_transform(
    transform: List[float],
) -> Tuple[float, float, float]:
    """Extract translation (meters) from a 4x4 row-major transform.

    Args:
        transform: 16-element row-major matrix

    Returns:
        (tx, ty, tz) in meters
    """
    return (transform[3], transform[7], transform[11])


def build_absolute_translation_matrix(
    x: LengthLike, y: LengthLike, z: LengthLike
) -> List[float]:
    """Build a 4x4 identity-rotation matrix with given translation.

    Args:
        x: X position. Bare numbers = mm; strings like "20 mm" / "0.5 in"
            carry explicit units.
        y: Y position, same convention.
        z: Z position, same convention.

    Returns:
        16-element row-major 4x4 matrix (in meters, as Onshape expects).
    """
    x_m = parse_length(x).meters
    y_m = parse_length(y).meters
    z_m = parse_length(z).meters
    return [
        1.0, 0.0, 0.0, x_m,
        0.0, 1.0, 0.0, y_m,
        0.0, 0.0, 1.0, z_m,
        0.0, 0.0, 0.0, 1.0,
    ]


def compute_aligned_position(
    source_local_bbox: BoundingBox,
    source_current_pos_meters: Tuple[float, float, float],
    target_world_aabb: BoundingBox,
    face: str,
) -> Tuple[float, float, float]:
    """Compute new absolute position (meters) for source to be flush against target face.

    The source is placed OUTSIDE the target, touching the specified face.
    Only the axis perpendicular to the face changes; other axes are preserved.

    Args:
        source_local_bbox: Source part's local bounding box (meters)
        source_current_pos_meters: Source's current (tx, ty, tz) in meters
        target_world_aabb: Target's world-space AABB (meters)
        face: One of "front", "back", "left", "right", "top", "bottom"

    Returns:
        (new_x, new_y, new_z) in meters

    Raises:
        ValueError: If face is not a valid face name
    """
    if face not in FACE_NAMES:
        raise ValueError(
            f"Invalid face '{face}'. Must be one of: {sorted(FACE_NAMES)}"
        )

    cur_x, cur_y, cur_z = source_current_pos_meters

    if face == "front":
        new_y = target_world_aabb.low_y - source_local_bbox.high_y
        return (cur_x, new_y, cur_z)
    elif face == "back":
        new_y = target_world_aabb.high_y - source_local_bbox.low_y
        return (cur_x, new_y, cur_z)
    elif face == "left":
        new_x = target_world_aabb.low_x - source_local_bbox.high_x
        return (new_x, cur_y, cur_z)
    elif face == "right":
        new_x = target_world_aabb.high_x - source_local_bbox.low_x
        return (new_x, cur_y, cur_z)
    elif face == "bottom":
        new_z = target_world_aabb.low_z - source_local_bbox.high_z
        return (cur_x, cur_y, new_z)
    else:  # top
        new_z = target_world_aabb.high_z - source_local_bbox.low_z
        return (cur_x, cur_y, new_z)


def format_positions_report(positions: List[InstancePositionInfo]) -> str:
    """Format instance positions into human-readable text.

    Args:
        positions: List of position info for each instance

    Returns:
        Formatted string for MCP tool response
    """
    lines = ["Assembly Instance Positions", "=" * 40, ""]

    if not positions:
        lines.append("No instances found in assembly.")
        return "\n".join(lines)

    lines.append(f"Found {len(positions)} instance(s):\n")

    for p in positions:
        lines.append(f"**{p.name}** (ID: {p.instance_id})")
        lines.append(
            f"  Position: X={p.position_x_mm:.2f} mm, "
            f"Y={p.position_y_mm:.2f} mm, "
            f"Z={p.position_z_mm:.2f} mm"
        )
        lines.append(
            f"  Size: {p.size_x_mm:.2f} mm W x "
            f"{p.size_y_mm:.2f} mm D x "
            f"{p.size_z_mm:.2f} mm H"
        )
        lines.append(
            f"  World bounds: "
            f"X=[{p.world_low_x_mm:.2f}, {p.world_high_x_mm:.2f}] mm, "
            f"Y=[{p.world_low_y_mm:.2f}, {p.world_high_y_mm:.2f}] mm, "
            f"Z=[{p.world_low_z_mm:.2f}, {p.world_high_z_mm:.2f}] mm"
        )
        lines.append("")

    return "\n".join(lines)


async def get_assembly_positions(
    assembly_manager,
    partstudio_manager,
    document_id: str,
    workspace_id: str,
    element_id: str,
) -> str:
    """Fetch and format all instance positions in an assembly.

    Args:
        assembly_manager: AssemblyManager instance
        partstudio_manager: PartStudioManager instance
        document_id: Document ID
        workspace_id: Workspace ID
        element_id: Assembly element ID

    Returns:
        Formatted position report string
    """
    assembly_data = await assembly_manager.get_assembly_definition(
        document_id, workspace_id, element_id
    )
    root = assembly_data.get("rootAssembly", {})
    instances = root.get("instances", [])
    occ_transforms = extract_occurrence_transforms(assembly_data)
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

    # Fetch bounding boxes, cached by unique part
    bbox_cache: Dict[tuple, BoundingBox] = {}
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

    # Build position info for each instance
    positions: List[InstancePositionInfo] = []
    for inst in instances:
        if inst.get("type") != "Part" or inst.get("suppressed", False):
            continue
        inst_doc_id = inst.get("documentId", document_id)
        inst_elem_id = inst.get("elementId")
        inst_part_id = inst.get("partId")
        cache_key = (inst_doc_id, inst_elem_id, inst_part_id)
        if cache_key not in bbox_cache:
            continue

        transform = occ_transforms.get(inst["id"], identity)
        pos_meters = get_position_from_transform(transform)
        local_bbox = bbox_cache[cache_key]
        world_bbox = get_world_aabb(local_bbox, transform)

        positions.append(
            InstancePositionInfo(
                name=inst.get("name", "Unnamed"),
                instance_id=inst["id"],
                position_x_mm=pos_meters[0] * METERS_TO_MM,
                position_y_mm=pos_meters[1] * METERS_TO_MM,
                position_z_mm=pos_meters[2] * METERS_TO_MM,
                size_x_mm=(world_bbox.high_x - world_bbox.low_x) * METERS_TO_MM,
                size_y_mm=(world_bbox.high_y - world_bbox.low_y) * METERS_TO_MM,
                size_z_mm=(world_bbox.high_z - world_bbox.low_z) * METERS_TO_MM,
                world_low_x_mm=world_bbox.low_x * METERS_TO_MM,
                world_low_y_mm=world_bbox.low_y * METERS_TO_MM,
                world_low_z_mm=world_bbox.low_z * METERS_TO_MM,
                world_high_x_mm=world_bbox.high_x * METERS_TO_MM,
                world_high_y_mm=world_bbox.high_y * METERS_TO_MM,
                world_high_z_mm=world_bbox.high_z * METERS_TO_MM,
            )
        )

    return format_positions_report(positions)


async def set_absolute_position(
    assembly_manager,
    document_id: str,
    workspace_id: str,
    element_id: str,
    instance_id: str,
    x: LengthLike,
    y: LengthLike,
    z: LengthLike,
) -> Tuple[str, Tuple[float, float, float]]:
    """Set an instance to an absolute position.

    Args:
        assembly_manager: AssemblyManager instance
        document_id, workspace_id, element_id: Assembly triple.
        instance_id: Instance to position.
        x: Absolute X. Bare numbers = mm; strings like "20 mm" / "0.5 in"
            carry explicit units.
        y: Absolute Y, same convention.
        z: Absolute Z, same convention.

    Returns:
        (confirmation_message, (x_mm, y_mm, z_mm)) — the second element lets
        the caller put resolved-mm values in a structured response without
        re-parsing.
    """
    transform = build_absolute_translation_matrix(x, y, z)
    occurrences = [{"path": [instance_id], "transform": transform}]
    await assembly_manager.transform_occurrences(
        document_id, workspace_id, element_id, occurrences, is_relative=False
    )
    x_mm = parse_length(x).meters * METERS_TO_MM
    y_mm = parse_length(y).meters * METERS_TO_MM
    z_mm = parse_length(z).meters * METERS_TO_MM
    msg = (
        f"Set instance {instance_id} to absolute position: "
        f"X={x_mm:.2f} mm, Y={y_mm:.2f} mm, Z={z_mm:.2f} mm"
    )
    return msg, (x_mm, y_mm, z_mm)


async def align_to_face(
    assembly_manager,
    partstudio_manager,
    document_id: str,
    workspace_id: str,
    element_id: str,
    source_instance_id: str,
    target_instance_id: str,
    face: str,
) -> str:
    """Align source instance flush against a face of the target instance.

    Args:
        assembly_manager: AssemblyManager instance
        partstudio_manager: PartStudioManager instance
        document_id: Document ID
        workspace_id: Workspace ID
        element_id: Assembly element ID
        source_instance_id: Instance ID to move
        target_instance_id: Instance ID to align against
        face: Face of target ("front"/"back"/"left"/"right"/"top"/"bottom")

    Returns:
        Confirmation message with new position

    Raises:
        ValueError: If face is invalid or instances not found
    """
    face = face.lower().strip()
    if face not in FACE_NAMES:
        raise ValueError(
            f"Invalid face '{face}'. Must be one of: {sorted(FACE_NAMES)}"
        )

    assembly_data = await assembly_manager.get_assembly_definition(
        document_id, workspace_id, element_id
    )
    root = assembly_data.get("rootAssembly", {})
    instances = root.get("instances", [])
    occ_transforms = extract_occurrence_transforms(assembly_data)
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]

    # Find source and target instances
    source_inst = None
    target_inst = None
    for inst in instances:
        if inst["id"] == source_instance_id:
            source_inst = inst
        if inst["id"] == target_instance_id:
            target_inst = inst

    if source_inst is None:
        raise ValueError(
            f"Source instance '{source_instance_id}' not found in assembly"
        )
    if target_inst is None:
        raise ValueError(
            f"Target instance '{target_instance_id}' not found in assembly"
        )

    # Get bounding boxes
    def _bbox_params(inst):
        return (
            inst.get("documentId", document_id),
            inst.get("elementId"),
            inst.get("partId"),
        )

    s_doc, s_elem, s_part = _bbox_params(source_inst)
    t_doc, t_elem, t_part = _bbox_params(target_inst)

    source_bbox_data = await partstudio_manager.get_part_bounding_box(
        s_doc, workspace_id, s_elem, s_part
    )
    source_local_bbox = BoundingBox.from_api_response(source_bbox_data)

    target_bbox_data = await partstudio_manager.get_part_bounding_box(
        t_doc, workspace_id, t_elem, t_part
    )
    target_local_bbox = BoundingBox.from_api_response(target_bbox_data)

    # Compute target world AABB and source current position
    target_transform = occ_transforms.get(target_instance_id, identity)
    target_world_aabb = get_world_aabb(target_local_bbox, target_transform)

    source_transform = occ_transforms.get(source_instance_id, identity)
    source_current_pos = get_position_from_transform(source_transform)

    # Compute new position
    new_pos_meters = compute_aligned_position(
        source_local_bbox, source_current_pos, target_world_aabb, face
    )

    new_x_mm = new_pos_meters[0] * METERS_TO_MM
    new_y_mm = new_pos_meters[1] * METERS_TO_MM
    new_z_mm = new_pos_meters[2] * METERS_TO_MM

    # Apply absolute transform (pass mm strings so build_absolute_translation_matrix
    # parses them via the units helper like any other caller).
    transform = build_absolute_translation_matrix(
        f"{new_x_mm} mm", f"{new_y_mm} mm", f"{new_z_mm} mm"
    )
    occurrences = [{"path": [source_instance_id], "transform": transform}]
    await assembly_manager.transform_occurrences(
        document_id, workspace_id, element_id, occurrences, is_relative=False
    )

    return (
        f"Aligned '{source_inst.get('name', source_instance_id)}' to "
        f"'{face}' face of '{target_inst.get('name', target_instance_id)}'.\n"
        f"New position: X={new_x_mm:.2f} mm, Y={new_y_mm:.2f} mm, Z={new_z_mm:.2f} mm"
    )
