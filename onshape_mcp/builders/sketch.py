"""Sketch feature builder for Onshape."""

from typing import Any, Dict, List, Tuple, Optional
from enum import Enum


class SketchPlane(Enum):
    """Standard sketch planes."""
    FRONT = "Front"
    TOP = "Top"
    RIGHT = "Right"


class SketchBuilder:
    """Builder for creating Onshape sketch features."""

    def __init__(self, name: str = "Sketch", plane: SketchPlane = SketchPlane.FRONT):
        """Initialize sketch builder.

        Args:
            name: Name of the sketch feature
            plane: Sketch plane (Front, Top, or Right)
        """
        self.name = name
        self.plane = plane
        self.entities: List[Dict[str, Any]] = []
        self.constraints: List[Dict[str, Any]] = []

    def add_rectangle(
        self,
        corner1: Tuple[float, float],
        corner2: Tuple[float, float],
        variable_width: Optional[str] = None,
        variable_height: Optional[str] = None
    ) -> 'SketchBuilder':
        """Add a rectangle to the sketch.

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

        # Create four lines forming a rectangle
        lines = [
            {"start": [x1, y1], "end": [x2, y1]},  # Bottom
            {"start": [x2, y1], "end": [x2, y2]},  # Right
            {"start": [x2, y2], "end": [x1, y2]},  # Top
            {"start": [x1, y2], "end": [x1, y1]},  # Left
        ]

        for line in lines:
            self.entities.append({
                "type": "BTCurveGeometryLine",
                "startPoint": line["start"],
                "endPoint": line["end"],
                "isConstruction": False
            })

        # If variables specified, add dimensional constraints
        if variable_width:
            self._add_dimension_constraint("horizontal", abs(x2 - x1), variable_width)

        if variable_height:
            self._add_dimension_constraint("vertical", abs(y2 - y1), variable_height)

        return self

    def add_circle(
        self,
        center: Tuple[float, float],
        radius: float,
        variable_radius: Optional[str] = None
    ) -> 'SketchBuilder':
        """Add a circle to the sketch.

        Args:
            center: Center point (x, y) in inches
            radius: Circle radius in inches
            variable_radius: Optional variable name for radius

        Returns:
            Self for chaining
        """
        self.entities.append({
            "type": "BTCurveGeometryCircle",
            "center": list(center),
            "radius": radius,
            "isConstruction": False
        })

        if variable_radius:
            self._add_dimension_constraint("radius", radius, variable_radius)

        return self

    def add_line(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
        is_construction: bool = False
    ) -> 'SketchBuilder':
        """Add a line to the sketch.

        Args:
            start: Start point (x, y) in inches
            end: End point (x, y) in inches
            is_construction: Whether this is a construction line

        Returns:
            Self for chaining
        """
        self.entities.append({
            "type": "BTCurveGeometryLine",
            "startPoint": list(start),
            "endPoint": list(end),
            "isConstruction": is_construction
        })

        return self

    def _add_dimension_constraint(
        self,
        constraint_type: str,
        value: float,
        variable_name: str
    ):
        """Add a dimensional constraint.

        Args:
            constraint_type: Type of constraint (horizontal, vertical, radius, etc.)
            value: Dimension value
            variable_name: Variable name to reference
        """
        self.constraints.append({
            "type": constraint_type,
            "value": value,
            "expression": f"#{variable_name}"
        })

    def build(self) -> Dict[str, Any]:
        """Build the sketch feature JSON.

        Returns:
            Feature definition for Onshape API
        """
        # Get plane query based on selected plane
        plane_id = {
            SketchPlane.FRONT: "JHD",
            SketchPlane.TOP: "JHC",
            SketchPlane.RIGHT: "JHB"
        }.get(self.plane, "JHD")

        return {
            "btType": "BTMFeature-134",
            "feature": {
                "btType": "BTMSketch-151",
                "name": self.name,
                "parameters": [
                    {
                        "btType": "BTMParameterQueryList-148",
                        "parameterId": "sketchPlane",
                        "queries": [{
                            "btType": "BTMIndividualQuery-138",
                            "deterministicIds": [plane_id]
                        }]
                    }
                ],
                "constraints": self.constraints,
                "entities": self.entities
            }
        }
