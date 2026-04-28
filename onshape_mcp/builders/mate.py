"""Mate and mate connector builders for Onshape assemblies."""

import math
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ._units import parse_length


LengthLike = Union[float, int, str]


class MateType(Enum):
    """Assembly mate type."""

    FASTENED = "FASTENED"
    REVOLUTE = "REVOLUTE"
    SLIDER = "SLIDER"
    CYLINDRICAL = "CYLINDRICAL"


class MateConnectorBuilder:
    """Builder for creating Onshape assembly mate connector features (BTMMateConnector-66).

    Creates mate connectors that reference specific faces on assembly instances
    using BTMInferenceQueryWithOccurrence-1083 with CENTROID inference type.
    The connector is placed at the center of the specified face with its primary
    axis (Z-axis) aligned to the face normal.

    Requires both a face deterministic ID and an occurrence path (instance ID)
    to properly resolve geometry in the assembly context.
    """

    def __init__(
        self,
        name: str = "Mate connector",
        face_id: Optional[str] = None,
        occurrence_path: Optional[List[str]] = None,
        inference_type: str = "CENTROID",
    ):
        """Initialize mate connector builder.

        Args:
            name: Name of the mate connector feature
            face_id: Deterministic ID of the face to place the connector on
            occurrence_path: List of instance IDs defining the occurrence
            inference_type: How to derive a coordinate system from the face.
                "CENTROID" works for planar faces (the default — connector
                placed at face centroid, Z along normal). For CYLINDER, CONE,
                TORUS, or SPHERE faces, pass "MID_AXIS_POINT" — the
                connector lands on the face's axis with Z along the axis
                direction. CENTROID on a cylinder produces a featureStatus
                ERROR with no actionable diagnostic from Onshape.
        """
        self.name = name
        self.face_id = face_id
        self.occurrence_path = occurrence_path
        self.inference_type = inference_type
        self._flip_primary = False
        self._secondary_axis_type = "PLUS_X"
        self._transform_enabled = False
        self._translation_x = 0.0
        self._translation_y = 0.0
        self._translation_z = 0.0
        self._rotation_type = "ABOUT_Z"
        self._rotation_angle = 0.0

    def set_face(self, face_id: str) -> "MateConnectorBuilder":
        """Set the face deterministic ID for the connector origin.

        Args:
            face_id: Deterministic ID of the face (from Part Studio body details)

        Returns:
            Self for chaining
        """
        self.face_id = face_id
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

    def set_flip_primary(self, flip: bool = True) -> "MateConnectorBuilder":
        """Flip the primary (Z) axis direction.

        Args:
            flip: Whether to flip the primary axis

        Returns:
            Self for chaining
        """
        self._flip_primary = flip
        return self

    def set_secondary_axis(self, axis_type: str) -> "MateConnectorBuilder":
        """Reorient the secondary axis around the primary axis.

        Args:
            axis_type: One of "PLUS_X", "PLUS_Y", "MINUS_X", "MINUS_Y"

        Returns:
            Self for chaining

        Raises:
            ValueError: If axis_type is not valid
        """
        valid = {"PLUS_X", "PLUS_Y", "MINUS_X", "MINUS_Y"}
        if axis_type not in valid:
            raise ValueError(f"axis_type must be one of {valid}, got '{axis_type}'")
        self._secondary_axis_type = axis_type
        return self

    def set_translation(
        self,
        x: LengthLike,
        y: LengthLike,
        z: LengthLike,
    ) -> "MateConnectorBuilder":
        """Set offset from face center.

        Enables the transform parameters on the mate connector.

        Args:
            x: X offset. Bare number = mm; strings like "10 mm" / "0.5 in"
                carry explicit units.
            y: Y offset, same convention.
            z: Z offset, same convention.

        Returns:
            Self for chaining
        """
        self._transform_enabled = True
        # Store in meters so build() can skip re-parsing.
        self._translation_x = parse_length(x).meters
        self._translation_y = parse_length(y).meters
        self._translation_z = parse_length(z).meters
        return self

    def set_rotation(
        self, axis: str = "ABOUT_Z", angle: float = 0.0
    ) -> "MateConnectorBuilder":
        """Set rotation around an axis.

        Enables the transform parameters on the mate connector.

        Args:
            axis: Rotation axis - "ABOUT_X", "ABOUT_Y", or "ABOUT_Z"
            angle: Rotation angle in degrees

        Returns:
            Self for chaining

        Raises:
            ValueError: If axis is not valid
        """
        valid = {"ABOUT_X", "ABOUT_Y", "ABOUT_Z"}
        if axis not in valid:
            raise ValueError(f"axis must be one of {valid}, got '{axis}'")
        self._transform_enabled = True
        self._rotation_type = axis
        self._rotation_angle = angle
        return self

    def build(self) -> Dict[str, Any]:
        """Build the mate connector feature JSON.

        Returns:
            Feature definition for Onshape API
        """
        parameters: List[Dict[str, Any]] = [
            {
                "btType": "BTMParameterEnum-145",
                "parameterId": "originType",
                "enumName": "Origin type",
                "value": "ON_ENTITY",
            },
            {
                "btType": "BTMParameterQueryWithOccurrenceList-67",
                "parameterId": "originQuery",
                "queries": [
                    {
                        "btType": "BTMInferenceQueryWithOccurrence-1083",
                        "inferenceType": self.inference_type,
                        "path": self.occurrence_path or [],
                        "deterministicIds": [self.face_id] if self.face_id else [],
                    }
                ],
            },
        ]

        if self._flip_primary:
            parameters.append({
                "btType": "BTMParameterBoolean-144",
                "parameterId": "flipPrimary",
                "value": True,
            })

        if self._secondary_axis_type != "PLUS_X":
            parameters.append({
                "btType": "BTMParameterEnum-145",
                "parameterId": "secondaryAxisType",
                "enumName": "Reorient secondary axis",
                "value": self._secondary_axis_type,
            })

        if self._transform_enabled:
            # set_translation stored these in meters already.
            tx_m = self._translation_x
            ty_m = self._translation_y
            tz_m = self._translation_z
            parameters.append({
                "btType": "BTMParameterBoolean-144",
                "parameterId": "transform",
                "value": True,
            })
            parameters.extend([
                {
                    "btType": "BTMParameterQuantity-147",
                    "parameterId": "translationX",
                    "expression": f"{tx_m} m",
                    "isInteger": False,
                },
                {
                    "btType": "BTMParameterQuantity-147",
                    "parameterId": "translationY",
                    "expression": f"{ty_m} m",
                    "isInteger": False,
                },
                {
                    "btType": "BTMParameterQuantity-147",
                    "parameterId": "translationZ",
                    "expression": f"{tz_m} m",
                    "isInteger": False,
                },
                {
                    "btType": "BTMParameterEnum-145",
                    "parameterId": "rotationType",
                    "enumName": "Rotation axis",
                    "value": self._rotation_type,
                },
                {
                    "btType": "BTMParameterQuantity-147",
                    "parameterId": "rotation",
                    "expression": f"{math.radians(self._rotation_angle)} rad",
                    "isInteger": False,
                },
            ])

        return {
            "feature": {
                "btType": "BTMMateConnector-66",
                "featureType": "mateConnector",
                "name": self.name,
                "suppressed": False,
                "parameters": parameters,
            }
        }


class MateBuilder:
    """Builder for creating Onshape assembly mates (BTMMate-64).

    Mates reference explicit mate connector features by their feature IDs
    using BTMFeatureQueryWithOccurrence-157.
    """

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
        self.first_mc_id: Optional[str] = None
        self.second_mc_id: Optional[str] = None
        self.min_limit: Optional[float] = None
        self.max_limit: Optional[float] = None

    def set_first_connector(self, feature_id: str) -> "MateBuilder":
        """Set the first mate connector by feature ID.

        Args:
            feature_id: Feature ID of the mate connector

        Returns:
            Self for chaining
        """
        self.first_mc_id = feature_id
        return self

    def set_second_connector(self, feature_id: str) -> "MateBuilder":
        """Set the second mate connector by feature ID.

        Args:
            feature_id: Feature ID of the mate connector

        Returns:
            Self for chaining
        """
        self.second_mc_id = feature_id
        return self

    def set_limits(
        self,
        min_value: "LengthLike | float",
        max_value: "LengthLike | float",
    ) -> "MateBuilder":
        """Set motion limits for the mate.

        For SLIDER / CYLINDRICAL mates: values are LENGTHS. Bare numbers are
            mm (matches the new-forward units convention); strings like
            "10 mm" / "0.5 in" carry explicit units.
        For REVOLUTE mates: values are ANGLES in degrees (float only; no
            length parsing — "deg" strings are rejected by the build step).

        Args:
            min_value: Minimum travel (length for slider/cylindrical; degrees
                for revolute).
            max_value: Maximum travel.

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
                "btType": "BTMMate-64",
                "featureType": "mate",
                "name": self.name,
                "suppressed": False,
                "parameters": [
                    {
                        "btType": "BTMParameterEnum-145",
                        "parameterId": "mateType",
                        "enumName": "Mate type",
                        "value": self.mate_type.value,
                    },
                    {
                        "btType": "BTMParameterQueryWithOccurrenceList-67",
                        "parameterId": "mateConnectorsQuery",
                        "queries": [
                            {
                                "btType": "BTMFeatureQueryWithOccurrence-157",
                                "featureId": self.first_mc_id or "",
                                "path": [],
                                "queryData": "",
                            },
                            {
                                "btType": "BTMFeatureQueryWithOccurrence-157",
                                "featureId": self.second_mc_id or "",
                                "path": [],
                                "queryData": "",
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
                min_m = parse_length(self.min_limit).meters
                max_m = parse_length(self.max_limit).meters
                params.append({
                    "btType": "BTMParameterNullableQuantity-807",
                    "parameterId": "limitZMin",
                    "expression": f"{min_m} m",
                    "isInteger": False,
                    "isNull": False,
                })
                params.append({
                    "btType": "BTMParameterNullableQuantity-807",
                    "parameterId": "limitZMax",
                    "expression": f"{max_m} m",
                    "isInteger": False,
                    "isNull": False,
                })
            elif self.mate_type == MateType.REVOLUTE:
                min_rad = math.radians(self.min_limit)
                max_rad = math.radians(self.max_limit)
                params.append({
                    "btType": "BTMParameterNullableQuantity-807",
                    "parameterId": "limitAxialZMin",
                    "expression": f"{min_rad} rad",
                    "isInteger": False,
                    "isNull": False,
                })
                params.append({
                    "btType": "BTMParameterNullableQuantity-807",
                    "parameterId": "limitAxialZMax",
                    "expression": f"{max_rad} rad",
                    "isInteger": False,
                    "isNull": False,
                })

        return feature_data


def build_transform_matrix(
    tx: LengthLike = 0.0,
    ty: LengthLike = 0.0,
    tz: LengthLike = 0.0,
    rx: float = 0.0,
    ry: float = 0.0,
    rz: float = 0.0,
) -> List[float]:
    """Build a 4x4 transformation matrix (row-major, 16 elements).

    Translations are lengths: bare numbers are mm (CAD default); strings like
    "10 mm" / "0.5 in" / "0.03 m" carry explicit units. Rotations are degrees
    (float). Rotation order is Rz * Ry * Rx.

    Args:
        tx: X translation. Bare = mm; strings with unit suffix respected.
        ty: Y translation, same convention.
        tz: Z translation, same convention.
        rx: X rotation in degrees
        ry: Y rotation in degrees
        rz: Z rotation in degrees

    Returns:
        16-element list representing the 4x4 transformation matrix
    """
    tx_m = parse_length(tx).meters
    ty_m = parse_length(ty).meters
    tz_m = parse_length(tz).meters

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
