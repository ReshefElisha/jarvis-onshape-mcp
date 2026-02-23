"""Sketch feature builder for Onshape."""

import math
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

    def add_circle(
        self,
        center: Tuple[float, float],
        radius: float,
        is_construction: bool = False,
    ) -> "SketchBuilder":
        """Add a circle to the sketch.

        Args:
            center: Center point (x, y) in inches
            radius: Radius in inches
            is_construction: Whether this is construction geometry

        Returns:
            Self for chaining
        """
        cx, cy = center

        def to_meters(inches: float) -> float:
            return inches * 0.0254

        cx_m, cy_m = to_meters(cx), to_meters(cy)
        radius_m = to_meters(radius)

        circle_id = self._generate_entity_id("circle")

        # Full circles require two semicircular arcs to form a closed region.
        # A single BTMSketchCurveSegment with startParam=0 and endParam=2π
        # is accepted by Onshape but doesn't render or create a sketch region.
        arc1_id = f"{circle_id}.arc1"
        arc2_id = f"{circle_id}.arc2"

        # First semicircle: 0 to π
        self.entities.append(
            {
                "btType": "BTMSketchCurveSegment-155",
                "entityId": arc1_id,
                "startPointId": f"{circle_id}.start",
                "endPointId": f"{circle_id}.mid",
                "startParam": 0.0,
                "endParam": math.pi,
                "geometry": {
                    "btType": "BTCurveGeometryCircle-115",
                    "radius": radius_m,
                    "xCenter": cx_m,
                    "yCenter": cy_m,
                    "xDir": 1.0,
                    "yDir": 0.0,
                    "clockwise": False,
                },
                "centerId": f"{circle_id}.center",
                "isConstruction": is_construction,
            }
        )

        # Second semicircle: π to 2π
        self.entities.append(
            {
                "btType": "BTMSketchCurveSegment-155",
                "entityId": arc2_id,
                "startPointId": f"{circle_id}.mid",
                "endPointId": f"{circle_id}.start",
                "startParam": math.pi,
                "endParam": 2.0 * math.pi,
                "geometry": {
                    "btType": "BTCurveGeometryCircle-115",
                    "radius": radius_m,
                    "xCenter": cx_m,
                    "yCenter": cy_m,
                    "xDir": 1.0,
                    "yDir": 0.0,
                    "clockwise": False,
                },
                "centerId": f"{circle_id}.center",
                "isConstruction": is_construction,
            }
        )

        # Coincident constraints to close the circle
        self.constraints.append(
            {
                "btType": "BTMSketchConstraint-2",
                "constraintType": "COINCIDENT",
                "entityId": f"{circle_id}.close1",
                "parameters": [
                    {
                        "btType": "BTMParameterString-149",
                        "value": f"{arc1_id}.end",
                        "parameterId": "localFirst",
                    },
                    {
                        "btType": "BTMParameterString-149",
                        "value": f"{arc2_id}.start",
                        "parameterId": "localSecond",
                    },
                ],
            }
        )
        self.constraints.append(
            {
                "btType": "BTMSketchConstraint-2",
                "constraintType": "COINCIDENT",
                "entityId": f"{circle_id}.close2",
                "parameters": [
                    {
                        "btType": "BTMParameterString-149",
                        "value": f"{arc2_id}.end",
                        "parameterId": "localFirst",
                    },
                    {
                        "btType": "BTMParameterString-149",
                        "value": f"{arc1_id}.start",
                        "parameterId": "localSecond",
                    },
                ],
            }
        )

        return self

    def add_arc(
        self,
        center: Tuple[float, float],
        radius: float,
        start_angle: float = 0.0,
        end_angle: float = 180.0,
        is_construction: bool = False,
    ) -> "SketchBuilder":
        """Add an arc to the sketch.

        Args:
            center: Center point (x, y) in inches
            radius: Radius in inches
            start_angle: Start angle in degrees (0 = positive X direction)
            end_angle: End angle in degrees
            is_construction: Whether this is construction geometry

        Returns:
            Self for chaining
        """
        cx, cy = center

        def to_meters(inches: float) -> float:
            return inches * 0.0254

        cx_m, cy_m = to_meters(cx), to_meters(cy)
        radius_m = to_meters(radius)

        start_rad = math.radians(start_angle)
        end_rad = math.radians(end_angle)

        arc_id = self._generate_entity_id("arc")

        self.entities.append(
            {
                "btType": "BTMSketchCurveSegment-155",
                "entityId": arc_id,
                "startPointId": f"{arc_id}.start",
                "endPointId": f"{arc_id}.end",
                "startParam": start_rad,
                "endParam": end_rad,
                "geometry": {
                    "btType": "BTCurveGeometryCircle-115",
                    "radius": radius_m,
                    "xCenter": cx_m,
                    "yCenter": cy_m,
                    "xDir": 1.0,
                    "yDir": 0.0,
                    "clockwise": False,
                },
                "centerId": f"{arc_id}.center",
                "isConstruction": is_construction,
            }
        )

        return self

    def add_line(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
        is_construction: bool = False,
    ) -> "SketchBuilder":
        """Add a line segment to the sketch.

        Args:
            start: Start point (x, y) in inches
            end: End point (x, y) in inches
            is_construction: Whether this is construction geometry

        Returns:
            Self for chaining
        """
        sx, sy = start
        ex, ey = end

        def to_meters(inches: float) -> float:
            return inches * 0.0254

        sx_m, sy_m = to_meters(sx), to_meters(sy)
        ex_m, ey_m = to_meters(ex), to_meters(ey)

        length = math.sqrt((ex_m - sx_m) ** 2 + (ey_m - sy_m) ** 2)
        if length == 0:
            raise ValueError("Line start and end points must be different")

        dir_x = (ex_m - sx_m) / length
        dir_y = (ey_m - sy_m) / length

        line_id = self._generate_entity_id("line")

        self.entities.append(
            {
                "btType": "BTMSketchCurveSegment-155",
                "entityId": line_id,
                "startPointId": f"{line_id}.start",
                "endPointId": f"{line_id}.end",
                "startParam": 0.0,
                "endParam": length,
                "geometry": {
                    "btType": "BTCurveGeometryLine-117",
                    "pntX": sx_m,
                    "pntY": sy_m,
                    "dirX": dir_x,
                    "dirY": dir_y,
                },
                "isConstruction": is_construction,
            }
        )

        return self

    def add_polygon(
        self,
        center: Tuple[float, float],
        sides: int,
        radius: float,
        is_construction: bool = False,
    ) -> "SketchBuilder":
        """Add a regular polygon to the sketch.

        Creates a polygon inscribed in a circle of the given radius.

        Args:
            center: Center point (x, y) in inches
            sides: Number of sides (3 for triangle, 6 for hexagon, etc.)
            radius: Circumscribed radius in inches
            is_construction: Whether this is construction geometry

        Returns:
            Self for chaining

        Raises:
            ValueError: If sides < 3
        """
        if sides < 3:
            raise ValueError("Polygon must have at least 3 sides")

        cx, cy = center

        # Calculate vertices
        vertices = []
        for i in range(sides):
            angle = 2.0 * math.pi * i / sides - math.pi / 2  # Start from top
            vx = cx + radius * math.cos(angle)
            vy = cy + radius * math.sin(angle)
            vertices.append((vx, vy))

        # Add line segments between consecutive vertices
        for i in range(sides):
            start = vertices[i]
            end = vertices[(i + 1) % sides]
            self.add_line(start, end, is_construction=is_construction)

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
