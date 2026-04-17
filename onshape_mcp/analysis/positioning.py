"""Assembly positioning tools for absolute placement and face alignment."""

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from loguru import logger

from .interference import BoundingBox, METERS_TO_INCHES, get_world_aabb

INCHES_TO_METERS = 0.0254

FACE_NAMES = {"front", "back", "left", "right", "top", "bottom"}


@dataclass
class InstancePositionInfo:
    """Position and extent information for a single assembly instance."""

    name: str
    instance_id: str
    position_x_inches: float
    position_y_inches: float
    position_z_inches: float
    size_x_inches: float
    size_y_inches: float
    size_z_inches: float
    world_low_x_inches: float
    world_low_y_inches: float
    world_low_z_inches: float
    world_high_x_inches: float
    world_high_y_inches: float
    world_high_z_inches: float


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
    x_inches: float, y_inches: float, z_inches: float
) -> List[float]:
    """Build a 4x4 identity-rotation matrix with given translation.

    Args:
        x_inches: X position in inches
        y_inches: Y position in inches
        z_inches: Z position in inches

    Returns:
        16-element row-major 4x4 matrix
    """
    return [
        1.0, 0.0, 0.0, x_inches * INCHES_TO_METERS,
        0.0, 1.0, 0.0, y_inches * INCHES_TO_METERS,
        0.0, 0.0, 1.0, z_inches * INCHES_TO_METERS,
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
            f'  Position: X={p.position_x_inches:.3f}", '
            f'Y={p.position_y_inches:.3f}", '
            f'Z={p.position_z_inches:.3f}"'
        )
        lines.append(
            f'  Size: {p.size_x_inches:.3f}" W x '
            f'{p.size_y_inches:.3f}" D x '
            f'{p.size_z_inches:.3f}" H'
        )
        lines.append(
            f"  World bounds: "
            f'X=[{p.world_low_x_inches:.3f}", {p.world_high_x_inches:.3f}"], '
            f'Y=[{p.world_low_y_inches:.3f}", {p.world_high_y_inches:.3f}"], '
            f'Z=[{p.world_low_z_inches:.3f}", {p.world_high_z_inches:.3f}"]'
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
                position_x_inches=pos_meters[0] * METERS_TO_INCHES,
                position_y_inches=pos_meters[1] * METERS_TO_INCHES,
                position_z_inches=pos_meters[2] * METERS_TO_INCHES,
                size_x_inches=(world_bbox.high_x - world_bbox.low_x) * METERS_TO_INCHES,
                size_y_inches=(world_bbox.high_y - world_bbox.low_y) * METERS_TO_INCHES,
                size_z_inches=(world_bbox.high_z - world_bbox.low_z) * METERS_TO_INCHES,
                world_low_x_inches=world_bbox.low_x * METERS_TO_INCHES,
                world_low_y_inches=world_bbox.low_y * METERS_TO_INCHES,
                world_low_z_inches=world_bbox.low_z * METERS_TO_INCHES,
                world_high_x_inches=world_bbox.high_x * METERS_TO_INCHES,
                world_high_y_inches=world_bbox.high_y * METERS_TO_INCHES,
                world_high_z_inches=world_bbox.high_z * METERS_TO_INCHES,
            )
        )

    return format_positions_report(positions)


async def set_absolute_position(
    assembly_manager,
    document_id: str,
    workspace_id: str,
    element_id: str,
    instance_id: str,
    x_inches: float,
    y_inches: float,
    z_inches: float,
) -> str:
    """Set an instance to an absolute position.

    Args:
        assembly_manager: AssemblyManager instance
        document_id: Document ID
        workspace_id: Workspace ID
        element_id: Assembly element ID
        instance_id: Instance to position
        x_inches: Absolute X position in inches
        y_inches: Absolute Y position in inches
        z_inches: Absolute Z position in inches

    Returns:
        Confirmation message string
    """
    transform = build_absolute_translation_matrix(x_inches, y_inches, z_inches)
    occurrences = [{"path": [instance_id], "transform": transform}]
    await assembly_manager.transform_occurrences(
        document_id, workspace_id, element_id, occurrences, is_relative=False
    )
    return (
        f"Set instance {instance_id} to absolute position: "
        f'X={x_inches:.3f}", Y={y_inches:.3f}", Z={z_inches:.3f}"'
    )


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

    new_x_in = new_pos_meters[0] * METERS_TO_INCHES
    new_y_in = new_pos_meters[1] * METERS_TO_INCHES
    new_z_in = new_pos_meters[2] * METERS_TO_INCHES

    # Apply absolute transform
    transform = build_absolute_translation_matrix(new_x_in, new_y_in, new_z_in)
    occurrences = [{"path": [source_instance_id], "transform": transform}]
    await assembly_manager.transform_occurrences(
        document_id, workspace_id, element_id, occurrences, is_relative=False
    )

    return (
        f"Aligned '{source_inst.get('name', source_instance_id)}' to "
        f"'{face}' face of '{target_inst.get('name', target_instance_id)}'.\n"
        f'New position: X={new_x_in:.3f}", Y={new_y_in:.3f}", Z={new_z_in:.3f}"'
    )
