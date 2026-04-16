"""Extrude feature builder for Onshape."""

from typing import Any, Dict, Optional, Union
from enum import Enum

from ._units import parse_length


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
        depth: Union[float, int, str] = 1.0,
        operation_type: ExtrudeType = ExtrudeType.NEW,
        opposite_direction: bool = False,
    ):
        """Initialize extrude builder.

        Args:
            name: Name of the extrude feature
            sketch_feature_id: ID of the sketch to extrude
            depth: Extrude depth. Bare numbers default to millimeters; pass a
                string like "1.5 in" for explicit units.
            operation_type: Type of extrude operation
            opposite_direction: If True, extrude against the sketch normal.
                Essential for REMOVE on a +Z face (cut into material, not air).
        """
        self.name = name
        self.sketch_feature_id = sketch_feature_id
        self.depth: Union[float, int, str] = depth
        self.operation_type = operation_type
        self.depth_variable: Optional[str] = None
        self.opposite_direction = opposite_direction

    def set_depth(
        self,
        depth: Union[float, int, str],
        variable_name: Optional[str] = None,
    ) -> "ExtrudeBuilder":
        """Set extrude depth.

        Args:
            depth: Depth. Bare numbers are mm; pass "0.5 in" / "15 mm" etc.
                for explicit units.
            variable_name: Optional variable name to reference

        Returns:
            Self for chaining
        """
        self.depth = depth
        self.depth_variable = variable_name
        return self

    def set_sketch(self, sketch_feature_id: str) -> "ExtrudeBuilder":
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

        if self.depth_variable:
            depth_expression = f"#{self.depth_variable}"
            depth_value_m = 0.0  # Onshape re-evaluates when variable resolves
        else:
            parsed = parse_length(self.depth)
            depth_expression = parsed.expression
            depth_value_m = parsed.meters

        return {
            "btType": "BTFeatureDefinitionCall-1406",
            "feature": {
                "btType": "BTMFeature-134",
                "featureType": "extrude",
                "name": self.name,
                "suppressed": False,
                "namespace": "",
                "parameters": [
                    {
                        "btType": "BTMParameterQueryList-148",
                        "queries": [
                            {
                                "btType": "BTMIndividualSketchRegionQuery-140",
                                "queryStatement": None,
                                "filterInnerLoops": True,
                                "queryString": f'query = qSketchRegion(id + "{self.sketch_feature_id}", true);',
                                "featureId": self.sketch_feature_id,
                                "deterministicIds": [],
                            }
                        ],
                        "parameterId": "entities",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    {
                        "btType": "BTMParameterEnum-145",
                        "namespace": "",
                        "enumName": "NewBodyOperationType",
                        "value": self.operation_type.value,
                        "parameterId": "operationType",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "isInteger": False,
                        "value": depth_value_m,
                        "units": "",
                        "expression": depth_expression,
                        "parameterId": "depth",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    {
                        "btType": "BTMParameterBoolean-144",
                        "value": self.opposite_direction,
                        "parameterId": "oppositeDirection",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                ],
            },
        }
