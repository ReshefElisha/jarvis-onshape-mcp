"""Sketch feature builder for Onshape."""

import math
from typing import Any, Dict, List, Tuple, Optional, Union
from enum import Enum

from ._units import parse_length


# A sketch-space length: raw number (interpreted as mm, the new default), or a
# string with an explicit unit ("10 mm", "0.5 in"). All sketch geometry
# coordinates and radii accept this type.
LengthLike = Union[float, int, str]


def _to_meters(v: LengthLike) -> float:
    """Parse a user-facing length value to meters."""
    return parse_length(v).meters


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
        corner1: Tuple[LengthLike, LengthLike],
        corner2: Tuple[LengthLike, LengthLike],
        variable_width: Optional[str] = None,
        variable_height: Optional[str] = None,
    ) -> "SketchBuilder":
        """Add a rectangle to the sketch with proper Onshape format.

        Creates 4 line entities with appropriate constraints (perpendicular,
        parallel, coincident, horizontal, and optional dimensional constraints).

        Args:
            corner1: First corner `(x, y)`. Each component is a number (mm
                default) or a string with an explicit unit ("10 mm", "0.5 in").
            corner2: Opposite corner `(x, y)`, same convention.
            variable_width: Optional variable name for width
            variable_height: Optional variable name for height

        Returns:
            Self for chaining
        """
        x1, y1 = corner1
        x2, y2 = corner2

        x1_m, y1_m = _to_meters(x1), _to_meters(y1)
        x2_m, y2_m = _to_meters(x2), _to_meters(y2)

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

    def add_rounded_rectangle(
        self,
        corner1: Tuple[LengthLike, LengthLike],
        corner2: Tuple[LengthLike, LengthLike],
        corner_radius: LengthLike,
    ) -> "SketchBuilder":
        """Add a rounded rectangle: 4 straight sides + 4 tangent corner arcs.

        The bounding box is defined by the two opposite corners; `corner_radius`
        is the fillet radius at each of the four corners. Straight segments
        connect consecutive arcs end-to-end, so the closed profile is a valid
        sketch region ready for extrude / cut-extrude.

        Minimum viable constraint set:
            - HORIZONTAL on the bottom straight segment (pins orientation)
            - COINCIDENT at each of the 8 line/arc junction points

        That's enough for a clean regen; Onshape treats the geometry as exact
        and doesn't need tangency constraints when the initial placement is
        geometrically tangent. Add-feature-and-check gives OK on the regen.

        Args:
            corner1: First corner `(x, y)` of the bounding rectangle; each
                component is a number (mm default) or a string with explicit
                units ("10 mm", "0.5 in").
            corner2: Opposite corner `(x, y)`, same convention.
            corner_radius: Fillet radius at each corner, same convention.

        Returns:
            Self for chaining.
        """
        x1, y1 = corner1
        x2, y2 = corner2
        x1_m, y1_m = _to_meters(x1), _to_meters(y1)
        x2_m, y2_m = _to_meters(x2), _to_meters(y2)
        r_m = _to_meters(corner_radius)

        # Normalize so (xlo, ylo) is lower-left regardless of caller ordering.
        xlo, xhi = (x1_m, x2_m) if x2_m > x1_m else (x2_m, x1_m)
        ylo, yhi = (y1_m, y2_m) if y2_m > y1_m else (y2_m, y1_m)

        # Sanity check the radius -- a corner radius larger than half the
        # short edge would make the "straight" sides zero-length or negative.
        short_side = min(xhi - xlo, yhi - ylo)
        if r_m <= 0:
            raise ValueError(
                f"corner_radius must be > 0, got {corner_radius!r} -> {r_m}m"
            )
        if r_m * 2 > short_side:
            raise ValueError(
                f"corner_radius ({r_m*1000:.2f} mm) exceeds half the short side "
                f"({short_side*1000/2:.2f} mm); would leave negative straight "
                f"segments. Either shrink the radius or use a plain rectangle."
            )

        rrect_id = self._generate_entity_id("rrect")
        bottom_id = f"{rrect_id}.bottom"
        right_id = f"{rrect_id}.right"
        top_id = f"{rrect_id}.top"
        left_id = f"{rrect_id}.left"
        arc_br = f"{rrect_id}.arc_br"
        arc_tr = f"{rrect_id}.arc_tr"
        arc_tl = f"{rrect_id}.arc_tl"
        arc_bl = f"{rrect_id}.arc_bl"

        # Four straight segments, each shortened by r on both ends.
        # Point-id convention matches add_rectangle for familiarity:
        #   <segment>.start, <segment>.end
        self.entities.append({
            "btType": "BTMSketchCurveSegment-155",
            "entityId": bottom_id,
            "startPointId": f"{bottom_id}.start",
            "endPointId": f"{bottom_id}.end",
            "startParam": 0.0,
            "endParam": (xhi - xlo) - 2 * r_m,
            "geometry": {
                "btType": "BTCurveGeometryLine-117",
                "pntX": xlo + r_m, "pntY": ylo,
                "dirX": 1.0, "dirY": 0.0,
            },
            "isConstruction": False,
        })
        self.entities.append({
            "btType": "BTMSketchCurveSegment-155",
            "entityId": right_id,
            "startPointId": f"{right_id}.start",
            "endPointId": f"{right_id}.end",
            "startParam": 0.0,
            "endParam": (yhi - ylo) - 2 * r_m,
            "geometry": {
                "btType": "BTCurveGeometryLine-117",
                "pntX": xhi, "pntY": ylo + r_m,
                "dirX": 0.0, "dirY": 1.0,
            },
            "isConstruction": False,
        })
        self.entities.append({
            "btType": "BTMSketchCurveSegment-155",
            "entityId": top_id,
            "startPointId": f"{top_id}.start",
            "endPointId": f"{top_id}.end",
            "startParam": 0.0,
            "endParam": (xhi - xlo) - 2 * r_m,
            "geometry": {
                "btType": "BTCurveGeometryLine-117",
                "pntX": xhi - r_m, "pntY": yhi,
                "dirX": -1.0, "dirY": 0.0,
            },
            "isConstruction": False,
        })
        self.entities.append({
            "btType": "BTMSketchCurveSegment-155",
            "entityId": left_id,
            "startPointId": f"{left_id}.start",
            "endPointId": f"{left_id}.end",
            "startParam": 0.0,
            "endParam": (yhi - ylo) - 2 * r_m,
            "geometry": {
                "btType": "BTCurveGeometryLine-117",
                "pntX": xlo, "pntY": yhi - r_m,
                "dirX": 0.0, "dirY": -1.0,
            },
            "isConstruction": False,
        })

        # Four corner arcs, each 90 degrees CCW, reference angle from +X.
        #   bottom-right: 270 -> 360 deg (3pi/2 .. 2pi)
        #   top-right:      0 ->  90 deg (0     .. pi/2)
        #   top-left:      90 -> 180 deg (pi/2  .. pi)
        #   bottom-left:  180 -> 270 deg (pi    .. 3pi/2)
        arcs = [
            (arc_br, xhi - r_m, ylo + r_m, 3 * math.pi / 2, 2 * math.pi),
            (arc_tr, xhi - r_m, yhi - r_m, 0.0,             math.pi / 2),
            (arc_tl, xlo + r_m, yhi - r_m, math.pi / 2,     math.pi),
            (arc_bl, xlo + r_m, ylo + r_m, math.pi,         3 * math.pi / 2),
        ]
        for arc_eid, cx, cy, t0, t1 in arcs:
            self.entities.append({
                "btType": "BTMSketchCurveSegment-155",
                "entityId": arc_eid,
                "startPointId": f"{arc_eid}.start",
                "endPointId": f"{arc_eid}.end",
                "centerId": f"{arc_eid}.center",
                "startParam": t0,
                "endParam": t1,
                "geometry": {
                    "btType": "BTCurveGeometryCircle-115",
                    "radius": r_m,
                    "xCenter": cx, "yCenter": cy,
                    "xDir": 1.0, "yDir": 0.0,
                    "clockwise": False,
                },
                "isConstruction": False,
            })

        # Join the 8 endpoints with COINCIDENT constraints, walking the closed
        # profile CCW: bottom -> arc_br -> right -> arc_tr -> top -> arc_tl ->
        # left -> arc_bl -> back to bottom.
        pairs = [
            (f"{bottom_id}.end",   f"{arc_br}.start"),
            (f"{arc_br}.end",      f"{right_id}.start"),
            (f"{right_id}.end",    f"{arc_tr}.start"),
            (f"{arc_tr}.end",      f"{top_id}.start"),
            (f"{top_id}.end",      f"{arc_tl}.start"),
            (f"{arc_tl}.end",      f"{left_id}.start"),
            (f"{left_id}.end",     f"{arc_bl}.start"),
            (f"{arc_bl}.end",      f"{bottom_id}.start"),
        ]
        for i, (pt_a, pt_b) in enumerate(pairs):
            self.constraints.append({
                "btType": "BTMSketchConstraint-2",
                "constraintType": "COINCIDENT",
                "entityId": f"{rrect_id}.join{i}",
                "parameters": [
                    {"btType": "BTMParameterString-149", "value": pt_a, "parameterId": "localFirst"},
                    {"btType": "BTMParameterString-149", "value": pt_b, "parameterId": "localSecond"},
                ],
            })

        # HORIZONTAL on the bottom edge pins the orientation so the solver
        # doesn't rotate the whole profile.
        self.constraints.append({
            "btType": "BTMSketchConstraint-2",
            "constraintType": "HORIZONTAL",
            "entityId": f"{rrect_id}.horizontal",
            "parameters": [
                {"btType": "BTMParameterString-149", "value": bottom_id, "parameterId": "localFirst"},
            ],
        })

        return self

    def add_circle(
        self,
        center: Tuple[LengthLike, LengthLike],
        radius: LengthLike,
        is_construction: bool = False,
        variable_radius: Optional[str] = None,
        variable_center: Optional[Tuple[str, str]] = None,
    ) -> "SketchBuilder":
        """Add a circle to the sketch.

        Args:
            center: Center point `(x, y)` (number = mm, or "10 mm" / "0.5 in").
                Used for the initial position; if `variable_center` is also
                given, those dimension constraints override the seeded position.
            radius: Radius (number = mm, or string with explicit unit). Same
                seeding role as `center` when `variable_radius` is given.
            is_construction: Whether this is construction geometry
            variable_radius: Optional variable name. When set, a DIAMETER
                constraint emitted with expression `#<var>*2` drives the
                circle radius from a variable table entry instead of a
                literal, so the caller can parametrically resize by
                `set_variable`.
            variable_center: Optional `(x_var, y_var)` pair of variable names.
                When set, DISTANCE constraints from the sketch origin (the
                `Origin` implicit entity) to the circle's centerId drive
                the center position parametrically.

        Returns:
            Self for chaining
        """
        cx, cy = center
        cx_m, cy_m = _to_meters(cx), _to_meters(cy)
        radius_m = _to_meters(radius)

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

        # Optional dimensional constraints that reference a variable. Variables
        # are prefixed with "#" in Onshape's expression parser, matching the
        # rectangle LENGTH constraint pattern.
        if variable_radius:
            self.constraints.append(
                {
                    "btType": "BTMSketchConstraint-2",
                    "constraintType": "RADIUS",
                    "entityId": f"{circle_id}.radius",
                    "parameters": [
                        {
                            "btType": "BTMParameterString-149",
                            "value": arc1_id,
                            "parameterId": "localFirst",
                        },
                        {
                            "btType": "BTMParameterQuantity-147",
                            "expression": f"#{variable_radius}",
                            "parameterId": "length",
                            "isInteger": False,
                        },
                    ],
                }
            )
        if variable_center:
            vx, vy = variable_center
            self.constraints.extend(
                self._variable_center_constraints(
                    entity_id=f"{circle_id}.center",
                    prefix=f"{circle_id}.pos",
                    variable_x=vx,
                    variable_y=vy,
                )
            )

        return self

    def _variable_center_constraints(
        self,
        entity_id: str,
        prefix: str,
        variable_x: str,
        variable_y: str,
    ) -> List[Dict[str, Any]]:
        """Build HORIZONTAL + VERTICAL DISTANCE constraints from the sketch origin.

        Distances are relative to Onshape's implicit sketch `origin` point,
        with the x/y variable expressions driving them. Extracted as a helper
        because add_arc will use the same pattern.
        """
        return [
            {
                "btType": "BTMSketchConstraint-2",
                "constraintType": "DISTANCE",
                "entityId": f"{prefix}.x",
                "parameters": [
                    {
                        "btType": "BTMParameterString-149",
                        "value": "origin",
                        "parameterId": "localFirst",
                    },
                    {
                        "btType": "BTMParameterString-149",
                        "value": entity_id,
                        "parameterId": "localSecond",
                    },
                    {
                        "btType": "BTMParameterEnum-145",
                        "value": "HORIZONTAL",
                        "enumName": "DimensionDirection",
                        "parameterId": "direction",
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "expression": f"#{variable_x}",
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
            },
            {
                "btType": "BTMSketchConstraint-2",
                "constraintType": "DISTANCE",
                "entityId": f"{prefix}.y",
                "parameters": [
                    {
                        "btType": "BTMParameterString-149",
                        "value": "origin",
                        "parameterId": "localFirst",
                    },
                    {
                        "btType": "BTMParameterString-149",
                        "value": entity_id,
                        "parameterId": "localSecond",
                    },
                    {
                        "btType": "BTMParameterEnum-145",
                        "value": "VERTICAL",
                        "enumName": "DimensionDirection",
                        "parameterId": "direction",
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "expression": f"#{variable_y}",
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
            },
        ]

    def add_arc(
        self,
        center: Tuple[LengthLike, LengthLike],
        radius: LengthLike,
        start_angle: float = 0.0,
        end_angle: float = 180.0,
        is_construction: bool = False,
        variable_radius: Optional[str] = None,
        variable_center: Optional[Tuple[str, str]] = None,
    ) -> "SketchBuilder":
        """Add an arc to the sketch.

        Args:
            center: Center point `(x, y)` (number = mm, or string with unit)
            radius: Radius (number = mm, or string with unit)
            start_angle: Start angle in degrees (0 = positive X direction)
            end_angle: End angle in degrees
            is_construction: Whether this is construction geometry
            variable_radius: Optional variable name. When set, a RADIUS
                constraint with expression `#<var>` drives the arc radius
                from the variable table.
            variable_center: Optional `(x_var, y_var)` variable names.
                DISTANCE constraints from the sketch origin to the arc's
                center drive the center position parametrically.

        Returns:
            Self for chaining
        """
        cx, cy = center
        cx_m, cy_m = _to_meters(cx), _to_meters(cy)
        radius_m = _to_meters(radius)

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

        if variable_radius:
            self.constraints.append(
                {
                    "btType": "BTMSketchConstraint-2",
                    "constraintType": "RADIUS",
                    "entityId": f"{arc_id}.radius",
                    "parameters": [
                        {
                            "btType": "BTMParameterString-149",
                            "value": arc_id,
                            "parameterId": "localFirst",
                        },
                        {
                            "btType": "BTMParameterQuantity-147",
                            "expression": f"#{variable_radius}",
                            "parameterId": "length",
                            "isInteger": False,
                        },
                    ],
                }
            )
        if variable_center:
            vx, vy = variable_center
            self.constraints.extend(
                self._variable_center_constraints(
                    entity_id=f"{arc_id}.center",
                    prefix=f"{arc_id}.pos",
                    variable_x=vx,
                    variable_y=vy,
                )
            )

        return self

    def add_line(
        self,
        start: Tuple[LengthLike, LengthLike],
        end: Tuple[LengthLike, LengthLike],
        is_construction: bool = False,
    ) -> "SketchBuilder":
        """Add a line segment to the sketch.

        Args:
            start: Start point `(x, y)` (number = mm, or string with unit)
            end: End point `(x, y)` (number = mm, or string with unit)
            is_construction: Whether this is construction geometry

        Returns:
            Self for chaining
        """
        sx, sy = start
        ex, ey = end

        sx_m, sy_m = _to_meters(sx), _to_meters(sy)
        ex_m, ey_m = _to_meters(ex), _to_meters(ey)

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
        center: Tuple[LengthLike, LengthLike],
        sides: int,
        radius: LengthLike,
        is_construction: bool = False,
    ) -> "SketchBuilder":
        """Add a regular polygon to the sketch.

        Creates a polygon inscribed in a circle of the given radius.

        Args:
            center: Center point `(x, y)` (number = mm, or string with unit)
            sides: Number of sides (3 for triangle, 6 for hexagon, etc.)
            radius: Circumscribed radius (number = mm, or string with unit)
            is_construction: Whether this is construction geometry

        Returns:
            Self for chaining

        Raises:
            ValueError: If sides < 3
        """
        if sides < 3:
            raise ValueError("Polygon must have at least 3 sides")

        # Parse once, in meters, then compute vertices in meters. Pass the
        # already-meter vertices to add_line as numeric (treated as mm by
        # add_line's parser -> convert back to meters). To avoid the mm
        # re-parse, we bypass add_line's coordinate parsing by constructing
        # geometry with meters directly -- simplest is to pass explicit "m"
        # strings so parse_length recognizes them.
        cx_m, cy_m = _to_meters(center[0]), _to_meters(center[1])
        radius_m = _to_meters(radius)

        vertices: List[Tuple[float, float]] = []
        for i in range(sides):
            angle = 2.0 * math.pi * i / sides - math.pi / 2  # Start from top
            vx = cx_m + radius_m * math.cos(angle)
            vy = cy_m + radius_m * math.sin(angle)
            vertices.append((vx, vy))

        for i in range(sides):
            sx, sy = vertices[i]
            ex, ey = vertices[(i + 1) % sides]
            # add_line treats bare numbers as mm; we already have meters, so
            # pass explicit-meter strings.
            self.add_line(
                (f"{sx} m", f"{sy} m"),
                (f"{ex} m", f"{ey} m"),
                is_construction=is_construction,
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
