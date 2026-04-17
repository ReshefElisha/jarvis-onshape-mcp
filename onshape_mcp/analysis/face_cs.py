"""Face coordinate system query using temporary mate connectors."""

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from loguru import logger


METERS_TO_INCHES = 1.0 / 0.0254


@dataclass
class FaceCoordinateSystem:
    """Resolved coordinate system for a face on an assembly instance.

    All axis vectors are unit vectors in world space.
    Z-axis is the guaranteed outward-facing normal.
    """

    origin_meters: Tuple[float, float, float]
    origin_inches: Tuple[float, float, float]
    x_axis: Tuple[float, float, float]
    y_axis: Tuple[float, float, float]
    z_axis: Tuple[float, float, float]  # outward face normal


def extract_mc_coordinate_system(
    assembly_data: Dict[str, Any],
    feature_id: str,
) -> FaceCoordinateSystem | None:
    """Extract the resolved coordinate system for a mate connector.

    Searches rootAssembly.features for a mate connector matching feature_id
    and extracts its matedCS (coordinate system).

    Args:
        assembly_data: Assembly definition with includeMateFeatures=true
        feature_id: The feature ID of the mate connector

    Returns:
        FaceCoordinateSystem if found, None otherwise
    """
    root = assembly_data.get("rootAssembly", {})
    features = root.get("features", [])

    for feat in features:
        fid = feat.get("featureId") or feat.get("id")
        if fid != feature_id:
            continue

        # Try multiple paths where the coordinate system might live
        mated_cs = feat.get("matedCS")
        if not mated_cs:
            fd = feat.get("featureData", {})
            mated_cs = fd.get("matedCS") or fd.get("mateConnectorCS")

        if mated_cs:
            return _parse_mated_cs(mated_cs)

    # Also check rootAssembly.mateConnectors
    mate_connectors = root.get("mateConnectors", [])
    for mc in mate_connectors:
        fid = mc.get("featureId") or mc.get("id")
        if fid != feature_id:
            continue
        mated_cs = mc.get("matedCS")
        if mated_cs:
            return _parse_mated_cs(mated_cs)

    return None


def _parse_mated_cs(mated_cs: Dict[str, Any]) -> FaceCoordinateSystem:
    """Parse a matedCS dict into a FaceCoordinateSystem."""
    origin = mated_cs.get("origin", [0, 0, 0])
    x_axis = mated_cs.get("xAxis", [1, 0, 0])
    y_axis = mated_cs.get("yAxis", [0, 1, 0])
    z_axis = mated_cs.get("zAxis", [0, 0, 1])

    ox, oy, oz = float(origin[0]), float(origin[1]), float(origin[2])

    return FaceCoordinateSystem(
        origin_meters=(ox, oy, oz),
        origin_inches=(
            ox * METERS_TO_INCHES,
            oy * METERS_TO_INCHES,
            oz * METERS_TO_INCHES,
        ),
        x_axis=(float(x_axis[0]), float(x_axis[1]), float(x_axis[2])),
        y_axis=(float(y_axis[0]), float(y_axis[1]), float(y_axis[2])),
        z_axis=(float(z_axis[0]), float(z_axis[1]), float(z_axis[2])),
    )


async def query_face_coordinate_system(
    assembly_manager: Any,
    document_id: str,
    workspace_id: str,
    element_id: str,
    instance_id: str,
    face_id: str,
) -> FaceCoordinateSystem:
    """Query the true coordinate system for a face on an assembly instance.

    Creates a temporary mate connector on the face, reads its resolved
    coordinate system from the assembly definition, then deletes it.
    The Z-axis of the returned CS is the guaranteed outward face normal.

    Args:
        assembly_manager: AssemblyManager instance
        document_id: Document ID
        workspace_id: Workspace ID
        element_id: Assembly element ID
        instance_id: Instance ID containing the face
        face_id: Face deterministic ID

    Returns:
        FaceCoordinateSystem with origin and axes

    Raises:
        RuntimeError: If the coordinate system could not be resolved
    """
    from ..builders.mate import MateConnectorBuilder

    mc = MateConnectorBuilder(
        name="__temp_cs_query__",
        face_id=face_id,
        occurrence_path=[instance_id],
    )
    result = await assembly_manager.add_feature(
        document_id=document_id,
        workspace_id=workspace_id,
        element_id=element_id,
        feature_data=mc.build(),
    )
    mc_feature_id = result.get("feature", {}).get("featureId")
    if not mc_feature_id:
        raise RuntimeError("Failed to create temporary mate connector")

    try:
        assembly_data = await assembly_manager.get_assembly_definition(
            document_id,
            workspace_id,
            element_id,
            params={
                "includeMateFeatures": True,
                "includeMateConnectors": True,
            },
        )

        cs = extract_mc_coordinate_system(assembly_data, mc_feature_id)
        if cs is None:
            raise RuntimeError(
                f"Could not find resolved coordinate system for MC {mc_feature_id}. "
                "The assembly definition may not include mate feature data in the expected format."
            )

        return cs
    finally:
        try:
            await assembly_manager.delete_feature(
                document_id, workspace_id, element_id, mc_feature_id
            )
        except Exception as e:
            logger.warning(
                f"Failed to delete temporary MC {mc_feature_id}: {e}. "
                "You may need to manually delete '__temp_cs_query__' from the assembly."
            )
