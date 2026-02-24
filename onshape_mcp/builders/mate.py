"""Mate and mate connector builders for Onshape assemblies."""

import math
from enum import Enum
from typing import Any, Dict, List, Optional


class MateType(Enum):
    """Assembly mate type."""

    FASTENED = "FASTENED"
    REVOLUTE = "REVOLUTE"
    SLIDER = "SLIDER"
    CYLINDRICAL = "CYLINDRICAL"


class MateConnectorBuilder:
    """Builder for creating Onshape mate connector features (BTMMateConnector-66)."""

    # Rotation angles (degrees) that align the connector's Z-axis with a world axis.
    # Assumes Onshape's ZYZ Euler convention for mate connector rotation parameters.
    AXIS_ROTATIONS = {
        "Z": (0.0, 0.0, 0.0),
        "Y": (-90.0, 90.0, 0.0),
        "X": (180.0, 90.0, 0.0),
    }

    def __init__(
        self,
        name: str = "Mate connector",
        origin_x: float = 0.0,
        origin_y: float = 0.0,
        origin_z: float = 0.0,
        axis: str = "Z",
    ):
        """Initialize mate connector builder.

        Args:
            name: Name of the mate connector feature
            origin_x: X origin in inches
            origin_y: Y origin in inches
            origin_z: Z origin in inches
            axis: Primary axis direction ("X", "Y", or "Z"). The connector's
                  Z-axis will be aligned with this world axis. Controls the
                  slide direction for slider mates. Default is "Z".
        """
        self.name = name
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.origin_z = origin_z
        self.occurrence_path: Optional[List[str]] = None
        self._rotation0 = 0.0
        self._rotation1 = 0.0
        self._rotation2 = 0.0
        if axis.upper() != "Z":
            self.set_axis(axis)

    def set_origin(self, x: float, y: float, z: float) -> "MateConnectorBuilder":
        """Set the connector origin in inches.

        Args:
            x: X coordinate in inches
            y: Y coordinate in inches
            z: Z coordinate in inches

        Returns:
            Self for chaining
        """
        self.origin_x = x
        self.origin_y = y
        self.origin_z = z
        return self

    def set_occurrence(self, path: List[str]) -> "MateConnectorBuilder":
        """Set the occurrence path (list of instance IDs).

        Args:
            path: List of instance IDs defining the occurrence

        Returns:
            Self for chaining
        """
        self.occurrence_path = path
        return self

    def set_axis(self, axis: str) -> "MateConnectorBuilder":
        """Set the connector's primary axis direction.

        The mate connector's Z-axis will be aligned with the specified world axis.
        For slider mates, this controls the slide direction.

        Args:
            axis: "X", "Y", or "Z"

        Returns:
            Self for chaining

        Raises:
            ValueError: If axis is not X, Y, or Z
        """
        axis = axis.upper()
        if axis not in self.AXIS_ROTATIONS:
            raise ValueError(f"axis must be 'X', 'Y', or 'Z', got '{axis}'")
        self._rotation0, self._rotation1, self._rotation2 = self.AXIS_ROTATIONS[axis]
        return self

    def set_rotation(
        self, rotation0: float = 0.0, rotation1: float = 0.0, rotation2: float = 0.0
    ) -> "MateConnectorBuilder":
        """Set explicit rotation angles for the connector orientation.

        Args:
            rotation0: First rotation angle in degrees
            rotation1: Second rotation angle in degrees
            rotation2: Third rotation angle in degrees

        Returns:
            Self for chaining
        """
        self._rotation0 = rotation0
        self._rotation1 = rotation1
        self._rotation2 = rotation2
        return self

    def build(self) -> Dict[str, Any]:
        """Build the mate connector feature JSON.

        Returns:
            Feature definition for Onshape API
        """
        origin_x_meters = self.origin_x * 0.0254
        origin_y_meters = self.origin_y * 0.0254
        origin_z_meters = self.origin_z * 0.0254

        return {
            "feature": {
                "btType": "BTMFeature-134",
                "featureType": "mateConnector",
                "name": self.name,
                "suppressed": False,
                "parameters": [
                    {
                        "btType": "BTMParameterEnum-145",
                        "parameterId": "originType",
                        "enumName": "MateConnectorOriginType",
                        "value": "ON_ENTITY",
                    },
                    {
                        "btType": "BTMParameterQueryList-148",
                        "parameterId": "originQuery",
                        "queries": [
                            {
                                "btType": "BTMIndividualOccurrenceQuery-626",
                                "path": self.occurrence_path or [],
                            }
                        ],
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "parameterId": "flipPrimary",
                        "expression": "false",
                        "isInteger": False,
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "parameterId": "translationX",
                        "expression": f"{origin_x_meters} m",
                        "isInteger": False,
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "parameterId": "translationY",
                        "expression": f"{origin_y_meters} m",
                        "isInteger": False,
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "parameterId": "translationZ",
                        "expression": f"{origin_z_meters} m",
                        "isInteger": False,
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "parameterId": "rotation0",
                        "expression": f"{math.radians(self._rotation0)} rad",
                        "isInteger": False,
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "parameterId": "rotation1",
                        "expression": f"{math.radians(self._rotation1)} rad",
                        "isInteger": False,
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "parameterId": "rotation2",
                        "expression": f"{math.radians(self._rotation2)} rad",
                        "isInteger": False,
                    },
                ],
            }
        }


class MateBuilder:
    """Builder for creating Onshape assembly mates (BTMMate-64)."""

    def __init__(
        self,
        name: str = "Mate",
        mate_type: MateType = MateType.FASTENED,
    ):
        """Initialize mate builder.

        Args:
            name: Name of the mate feature
            mate_type: Type of mate to create
        """
        self.name = name
        self.mate_type = mate_type
        self.first_path: List[str] = []
        self.second_path: List[str] = []
        self.min_limit: Optional[float] = None
        self.max_limit: Optional[float] = None

    def set_first_occurrence(self, path: List[str]) -> "MateBuilder":
        """Set the first occurrence path.

        Args:
            path: List of instance IDs for the first occurrence

        Returns:
            Self for chaining
        """
        self.first_path = path
        return self

    def set_second_occurrence(self, path: List[str]) -> "MateBuilder":
        """Set the second occurrence path.

        Args:
            path: List of instance IDs for the second occurrence

        Returns:
            Self for chaining
        """
        self.second_path = path
        return self

    def set_limits(self, min_value: float, max_value: float) -> "MateBuilder":
        """Set motion limits for the mate.

        For SLIDER/CYLINDRICAL mates: values are in inches (converted to meters).
        For REVOLUTE mates: values are in degrees (converted to radians).

        Args:
            min_value: Minimum travel (inches for slider, degrees for revolute)
            max_value: Maximum travel (inches for slider, degrees for revolute)

        Returns:
            Self for chaining
        """
        self.min_limit = min_value
        self.max_limit = max_value
        return self

    def build(self) -> Dict[str, Any]:
        """Build the mate feature JSON.

        Returns:
            Feature definition for Onshape API
        """
        feature_data = {
            "feature": {
                "btType": "BTMFeature-134",
                "featureType": "mate",
                "name": self.name,
                "suppressed": False,
                "parameters": [
                    {
                        "btType": "BTMParameterEnum-145",
                        "parameterId": "mateType",
                        "enumName": "MateType",
                        "value": self.mate_type.value,
                    },
                    {
                        "btType": "BTMParameterMateConnectorList-2020",
                        "parameterId": "mateConnectorsQuery",
                        "mateConnectors": [
                            {
                                "btType": "BTMMateConnectorQuery-564",
                                "implicitQuery": {
                                    "btType": "BTMIndividualOccurrenceQuery-626",
                                    "path": self.first_path,
                                },
                            },
                            {
                                "btType": "BTMMateConnectorQuery-564",
                                "implicitQuery": {
                                    "btType": "BTMIndividualOccurrenceQuery-626",
                                    "path": self.second_path,
                                },
                            },
                        ],
                    },
                ],
            }
        }

        if self.min_limit is not None and self.max_limit is not None:
            params = feature_data["feature"]["parameters"]
            params.append({
                "btType": "BTMParameterBoolean-144",
                "parameterId": "limitsEnabled",
                "value": True,
            })
            if self.mate_type in (MateType.SLIDER, MateType.CYLINDRICAL):
                min_m = self.min_limit * 0.0254
                max_m = self.max_limit * 0.0254
                params.append({
                    "btType": "BTMParameterQuantity-147",
                    "parameterId": "limitAxialZMin",
                    "expression": f"{min_m} m",
                    "isInteger": False,
                })
                params.append({
                    "btType": "BTMParameterQuantity-147",
                    "parameterId": "limitAxialZMax",
                    "expression": f"{max_m} m",
                    "isInteger": False,
                })
            elif self.mate_type == MateType.REVOLUTE:
                min_rad = math.radians(self.min_limit)
                max_rad = math.radians(self.max_limit)
                params.append({
                    "btType": "BTMParameterQuantity-147",
                    "parameterId": "limitRotationMin",
                    "expression": f"{min_rad} rad",
                    "isInteger": False,
                })
                params.append({
                    "btType": "BTMParameterQuantity-147",
                    "parameterId": "limitRotationMax",
                    "expression": f"{max_rad} rad",
                    "isInteger": False,
                })

        return feature_data


def build_transform_matrix(
    tx: float = 0.0,
    ty: float = 0.0,
    tz: float = 0.0,
    rx: float = 0.0,
    ry: float = 0.0,
    rz: float = 0.0,
) -> List[float]:
    """Build a 4x4 transformation matrix (row-major, 16 elements).

    Translation values are in inches (converted to meters).
    Rotation values are in degrees (converted to radians).
    Rotation order is Rz * Ry * Rx.

    Args:
        tx: X translation in inches
        ty: Y translation in inches
        tz: Z translation in inches
        rx: X rotation in degrees
        ry: Y rotation in degrees
        rz: Z rotation in degrees

    Returns:
        16-element list representing the 4x4 transformation matrix
    """
    # Convert inches to meters
    tx_m = tx * 0.0254
    ty_m = ty * 0.0254
    tz_m = tz * 0.0254

    # Convert degrees to radians
    rx_r = math.radians(rx)
    ry_r = math.radians(ry)
    rz_r = math.radians(rz)

    # Precompute trig values
    cx, sx = math.cos(rx_r), math.sin(rx_r)
    cy, sy = math.cos(ry_r), math.sin(ry_r)
    cz, sz = math.cos(rz_r), math.sin(rz_r)

    # Rotation matrix R = Rz * Ry * Rx (row-major)
    r00 = cz * cy
    r01 = cz * sy * sx - sz * cx
    r02 = cz * sy * cx + sz * sx

    r10 = sz * cy
    r11 = sz * sy * sx + cz * cx
    r12 = sz * sy * cx - cz * sx

    r20 = -sy
    r21 = cy * sx
    r22 = cy * cx

    # 4x4 matrix in row-major order
    return [
        r00, r01, r02, tx_m,
        r10, r11, r12, ty_m,
        r20, r21, r22, tz_m,
        0.0, 0.0, 0.0, 1.0,
    ]
