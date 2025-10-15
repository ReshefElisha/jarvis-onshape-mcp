"""Extrude feature builder for Onshape."""

from typing import Any, Dict, Optional
from enum import Enum


class ExtrudeType(Enum):
    """Extrude operation type."""
    NEW = "NEW"
    ADD = "ADD"
    REMOVE = "REMOVE"
    INTERSECT = "INTERSECT"


class ExtrudeBuilder:
    """Builder for creating Onshape extrude features."""

    def __init__(
        self,
        name: str = "Extrude",
        sketch_feature_id: Optional[str] = None,
        depth: float = 1.0,
        operation_type: ExtrudeType = ExtrudeType.NEW
    ):
        """Initialize extrude builder.

        Args:
            name: Name of the extrude feature
            sketch_feature_id: ID of the sketch to extrude
            depth: Extrude depth in inches
            operation_type: Type of extrude operation
        """
        self.name = name
        self.sketch_feature_id = sketch_feature_id
        self.depth = depth
        self.operation_type = operation_type
        self.depth_variable: Optional[str] = None

    def set_depth(self, depth: float, variable_name: Optional[str] = None) -> 'ExtrudeBuilder':
        """Set extrude depth.

        Args:
            depth: Depth in inches
            variable_name: Optional variable name to reference

        Returns:
            Self for chaining
        """
        self.depth = depth
        self.depth_variable = variable_name
        return self

    def set_sketch(self, sketch_feature_id: str) -> 'ExtrudeBuilder':
        """Set the sketch to extrude.

        Args:
            sketch_feature_id: Feature ID of the sketch

        Returns:
            Self for chaining
        """
        self.sketch_feature_id = sketch_feature_id
        return self

    def build(self) -> Dict[str, Any]:
        """Build the extrude feature JSON.

        Returns:
            Feature definition for Onshape API
        """
        if not self.sketch_feature_id:
            raise ValueError("Sketch feature ID must be set before building extrude")

        depth_expression = (
            f"#{self.depth_variable}" if self.depth_variable
            else f"{self.depth} in"
        )

        return {
            "btType": "BTMFeature-134",
            "feature": {
                "btType": "BTMFeature-134",
                "featureType": "extrude",
                "name": self.name,
                "parameters": [
                    {
                        "btType": "BTMParameterQueryList-148",
                        "parameterId": "entities",
                        "queries": [{
                            "btType": "BTMIndividualQuery-138",
                            "queryStatement": f"query=qSketchRegion('{self.sketch_feature_id}')"
                        }]
                    },
                    {
                        "btType": "BTMParameterEnum-145",
                        "parameterId": "operationType",
                        "value": self.operation_type.value
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "parameterId": "depth",
                        "expression": depth_expression,
                        "value": self.depth,
                        "isInteger": False
                    },
                    {
                        "btType": "BTMParameterBoolean-144",
                        "parameterId": "oppositeDirection",
                        "value": False
                    }
                ]
            }
        }
