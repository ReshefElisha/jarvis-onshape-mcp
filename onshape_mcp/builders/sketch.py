"""Sketch feature builder for Onshape."""

from typing import Any, Dict, List, Tuple, Optional
from enum import Enum


class SketchPlane(Enum):
    """Standard sketch planes."""

    FRONT = "Front"
    TOP = "Top"
    RIGHT = "Right"


class SketchBuilder:
    """Builder for creating Onshape sketch features in BTMSketch-151 format."""

    def __init__(
        self,
        name: str = "Sketch",
        plane: SketchPlane = SketchPlane.FRONT,
        plane_id: Optional[str] = None,
    ):
        """Initialize sketch builder.

        Args:
            name: Name of the sketch feature
            plane: Sketch plane (Front, Top, or Right)
            plane_id: Optional deterministic plane ID (obtained via get_plane_id)
        """
        self.name = name
        self.plane = plane
        self.plane_id = plane_id
        self.entities: List[Dict[str, Any]] = []
        self.constraints: List[Dict[str, Any]] = []
        self._entity_counter = 0

    def _generate_entity_id(self, prefix: str = "entity") -> str:
        """Generate a unique entity ID.

        Args:
            prefix: Prefix for the entity ID

        Returns:
            Unique entity ID
        """
        self._entity_counter += 1
        return f"{prefix}.{self._entity_counter}"

    def add_rectangle(
        self,
        corner1: Tuple[float, float],
        corner2: Tuple[float, float],
        variable_width: Optional[str] = None,
        variable_height: Optional[str] = None,
    ) -> "SketchBuilder":
        """Add a rectangle to the sketch with proper Onshape format.

        Creates 4 line entities with appropriate constraints (perpendicular,
        parallel, coincident, horizontal, and optional dimensional constraints).

        Args:
            corner1: First corner (x, y) in inches
            corner2: Opposite corner (x, y) in inches
            variable_width: Optional variable name for width
            variable_height: Optional variable name for height

        Returns:
            Self for chaining
        """
        x1, y1 = corner1
        x2, y2 = corner2

        # Convert inches to meters for Onshape API
        def to_meters(inches: float) -> float:
            return inches * 0.0254

        x1_m, y1_m = to_meters(x1), to_meters(y1)
        x2_m, y2_m = to_meters(x2), to_meters(y2)

        # Generate unique IDs for all components
        rect_id = self._generate_entity_id("rect")
        bottom_id = f"{rect_id}.bottom"
        right_id = f"{rect_id}.right"
        top_id = f"{rect_id}.top"
        left_id = f"{rect_id}.left"

        # Create point IDs
        point_ids = {
            "bottom_start": f"{bottom_id}.start",
            "bottom_end": f"{bottom_id}.end",
            "right_start": f"{right_id}.start",
            "right_end": f"{right_id}.end",
            "top_start": f"{top_id}.start",
            "top_end": f"{top_id}.end",
            "left_start": f"{left_id}.start",
            "left_end": f"{left_id}.end",
        }

        # Create four line entities (BTMSketchCurve-4 is for curves, but we use BTMSketchCurveSegment-155)
        # Bottom line (x1, y1) to (x2, y1)
        self.entities.append(
            {
                "btType": "BTMSketchCurveSegment-155",
                "entityId": bottom_id,
                "startPointId": point_ids["bottom_start"],
                "endPointId": point_ids["bottom_end"],
                "startParam": 0.0,
                "endParam": abs(x2_m - x1_m),
                "geometry": {
                    "btType": "BTCurveGeometryLine-117",
                    "pntX": x1_m,
                    "pntY": y1_m,
                    "dirX": 1.0 if x2_m > x1_m else -1.0,
                    "dirY": 0.0,
                },
                "isConstruction": False,
            }
        )

        # Right line (x2, y1) to (x2, y2)
        self.entities.append(
            {
                "btType": "BTMSketchCurveSegment-155",
                "entityId": right_id,
                "startPointId": point_ids["right_start"],
                "endPointId": point_ids["right_end"],
                "startParam": 0.0,
                "endParam": abs(y2_m - y1_m),
                "geometry": {
                    "btType": "BTCurveGeometryLine-117",
                    "pntX": x2_m,
                    "pntY": y1_m,
                    "dirX": 0.0,
                    "dirY": 1.0 if y2_m > y1_m else -1.0,
                },
                "isConstruction": False,
            }
        )

        # Top line (x2, y2) to (x1, y2)
        self.entities.append(
            {
                "btType": "BTMSketchCurveSegment-155",
                "entityId": top_id,
                "startPointId": point_ids["top_start"],
                "endPointId": point_ids["top_end"],
                "startParam": 0.0,
                "endParam": abs(x2_m - x1_m),
                "geometry": {
                    "btType": "BTCurveGeometryLine-117",
                    "pntX": x2_m,
                    "pntY": y2_m,
                    "dirX": -1.0 if x2_m > x1_m else 1.0,
                    "dirY": 0.0,
                },
                "isConstruction": False,
            }
        )

        # Left line (x1, y2) to (x1, y1)
        self.entities.append(
            {
                "btType": "BTMSketchCurveSegment-155",
                "entityId": left_id,
                "startPointId": point_ids["left_start"],
                "endPointId": point_ids["left_end"],
                "startParam": 0.0,
                "endParam": abs(y2_m - y1_m),
                "geometry": {
                    "btType": "BTCurveGeometryLine-117",
                    "pntX": x1_m,
                    "pntY": y2_m,
                    "dirX": 0.0,
                    "dirY": -1.0 if y2_m > y1_m else 1.0,
                },
                "isConstruction": False,
            }
        )

        # Add constraints to make it a proper rectangle

        # 1. Perpendicular constraints
        self.constraints.append(
            {
                "btType": "BTMSketchConstraint-2",
                "constraintType": "PERPENDICULAR",
                "entityId": f"{rect_id}.perpendicular",
                "parameters": [
                    {
                        "btType": "BTMParameterString-149",
                        "value": bottom_id,
                        "parameterId": "localFirst",
                    },
                    {
                        "btType": "BTMParameterString-149",
                        "value": left_id,
                        "parameterId": "localSecond",
                    },
                ],
            }
        )

        # 2. Parallel constraints
        self.constraints.append(
            {
                "btType": "BTMSketchConstraint-2",
                "constraintType": "PARALLEL",
                "entityId": f"{rect_id}.parallel.1",
                "parameters": [
                    {
                        "btType": "BTMParameterString-149",
                        "value": bottom_id,
                        "parameterId": "localFirst",
                    },
                    {
                        "btType": "BTMParameterString-149",
                        "value": top_id,
                        "parameterId": "localSecond",
                    },
                ],
            }
        )

        self.constraints.append(
            {
                "btType": "BTMSketchConstraint-2",
                "constraintType": "PARALLEL",
                "entityId": f"{rect_id}.parallel.2",
                "parameters": [
                    {
                        "btType": "BTMParameterString-149",
                        "value": left_id,
                        "parameterId": "localFirst",
                    },
                    {
                        "btType": "BTMParameterString-149",
                        "value": right_id,
                        "parameterId": "localSecond",
                    },
                ],
            }
        )

        # 3. Horizontal constraint for bottom line
        self.constraints.append(
            {
                "btType": "BTMSketchConstraint-2",
                "constraintType": "HORIZONTAL",
                "entityId": f"{rect_id}.horizontal",
                "parameters": [
                    {
                        "btType": "BTMParameterString-149",
                        "value": bottom_id,
                        "parameterId": "localFirst",
                    }
                ],
            }
        )

        # 4. Coincident constraints at corners
        corners = [
            (point_ids["bottom_start"], point_ids["left_end"], "corner0"),
            (point_ids["bottom_end"], point_ids["right_start"], "corner1"),
            (point_ids["top_start"], point_ids["right_end"], "corner2"),
            (point_ids["top_end"], point_ids["left_start"], "corner3"),
        ]

        for pt1, pt2, corner_name in corners:
            self.constraints.append(
                {
                    "btType": "BTMSketchConstraint-2",
                    "constraintType": "COINCIDENT",
                    "entityId": f"{rect_id}.{corner_name}",
                    "parameters": [
                        {
                            "btType": "BTMParameterString-149",
                            "value": pt1,
                            "parameterId": "localFirst",
                        },
                        {
                            "btType": "BTMParameterString-149",
                            "value": pt2,
                            "parameterId": "localSecond",
                        },
                    ],
                }
            )

        # 5. Dimensional constraints with variable references
        if variable_width:
            self.constraints.append(
                {
                    "btType": "BTMSketchConstraint-2",
                    "constraintType": "LENGTH",
                    "entityId": f"{rect_id}.width",
                    "parameters": [
                        {
                            "btType": "BTMParameterString-149",
                            "value": bottom_id,
                            "parameterId": "localFirst",
                        },
                        {
                            "btType": "BTMParameterEnum-145",
                            "value": "MINIMUM",
                            "enumName": "DimensionDirection",
                            "parameterId": "direction",
                        },
                        {
                            "btType": "BTMParameterQuantity-147",
                            "expression": f"#{variable_width}",
                            "parameterId": "length",
                            "isInteger": False,
                        },
                        {
                            "btType": "BTMParameterEnum-145",
                            "value": "ALIGNED",
                            "enumName": "DimensionAlignment",
                            "parameterId": "alignment",
                        },
                    ],
                }
            )

        if variable_height:
            self.constraints.append(
                {
                    "btType": "BTMSketchConstraint-2",
                    "constraintType": "LENGTH",
                    "entityId": f"{rect_id}.height",
                    "parameters": [
                        {
                            "btType": "BTMParameterString-149",
                            "value": right_id,
                            "parameterId": "localFirst",
                        },
                        {
                            "btType": "BTMParameterEnum-145",
                            "value": "MINIMUM",
                            "enumName": "DimensionDirection",
                            "parameterId": "direction",
                        },
                        {
                            "btType": "BTMParameterQuantity-147",
                            "expression": f"#{variable_height}",
                            "parameterId": "length",
                            "isInteger": False,
                        },
                        {
                            "btType": "BTMParameterEnum-145",
                            "value": "ALIGNED",
                            "enumName": "DimensionAlignment",
                            "parameterId": "alignment",
                        },
                    ],
                }
            )

        return self

    def build(self, plane_id: Optional[str] = None) -> Dict[str, Any]:
        """Build the sketch feature JSON in BTMSketch-151 format.

        Args:
            plane_id: Optional deterministic plane ID. If not provided, uses
                     the plane_id from the constructor or raises an error.

        Returns:
            Feature definition for Onshape API in proper BTMSketch-151 format

        Raises:
            ValueError: If plane_id is not provided and was not set in constructor
        """
        final_plane_id = plane_id or self.plane_id

        if not final_plane_id:
            raise ValueError(
                "plane_id must be provided either in constructor or build() method. "
                "Use PartStudioManager.get_plane_id() to obtain the correct plane ID."
            )

        # Build the feature in proper BTMSketch-151 format
        return {
            "feature": {
                "btType": "BTMSketch-151",
                "featureType": "newSketch",
                "name": self.name,
                "suppressed": False,
                "parameters": [
                    {
                        "btType": "BTMParameterQueryList-148",
                        "queries": [
                            {
                                "btType": "BTMIndividualQuery-138",
                                "deterministicIds": [final_plane_id],
                            }
                        ],
                        "parameterId": "sketchPlane",
                    }
                ],
                "entities": self.entities,
                "constraints": self.constraints,
            }
        }
