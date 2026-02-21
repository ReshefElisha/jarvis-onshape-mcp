"""Revolve feature builder for Onshape."""

from enum import Enum
from typing import Any, Dict, Optional


class RevolveType(Enum):
    """Revolve operation type."""

    NEW = "NEW"
    ADD = "ADD"
    REMOVE = "REMOVE"
    INTERSECT = "INTERSECT"


class RevolveBuilder:
    """Builder for creating Onshape revolve features."""

    def __init__(
        self,
        name: str = "Revolve",
        sketch_feature_id: Optional[str] = None,
        axis: str = "Y",
        angle: float = 360.0,
        operation_type: RevolveType = RevolveType.NEW,
    ):
        """Initialize revolve builder.

        Args:
            name: Name of the revolve feature
            sketch_feature_id: ID of the sketch to revolve
            axis: Axis of revolution ("X", "Y", or "Z")
            angle: Revolve angle in degrees
            operation_type: Type of revolve operation
        """
        self.name = name
        self.sketch_feature_id = sketch_feature_id
        self.axis = axis
        self.angle = angle
        self.angle_variable: Optional[str] = None
        self.operation_type = operation_type
        self.opposite_direction = False

    def set_sketch(self, sketch_feature_id: str) -> "RevolveBuilder":
        """Set the sketch to revolve.

        Args:
            sketch_feature_id: Feature ID of the sketch

        Returns:
            Self for chaining
        """
        self.sketch_feature_id = sketch_feature_id
        return self

    def set_angle(self, angle: float, variable_name: Optional[str] = None) -> "RevolveBuilder":
        """Set revolve angle.

        Args:
            angle: Angle in degrees
            variable_name: Optional variable name to reference

        Returns:
            Self for chaining
        """
        self.angle = angle
        self.angle_variable = variable_name
        return self

    def set_axis(self, axis: str) -> "RevolveBuilder":
        """Set the axis of revolution.

        Args:
            axis: Axis string ("X", "Y", or "Z")

        Returns:
            Self for chaining
        """
        self.axis = axis
        return self

    def set_opposite_direction(self, opposite: bool = True) -> "RevolveBuilder":
        """Set whether to revolve in opposite direction.

        Args:
            opposite: True to revolve in opposite direction

        Returns:
            Self for chaining
        """
        self.opposite_direction = opposite
        return self

    def _build_axis_query(self) -> Dict[str, Any]:
        """Build the axis query parameter based on the selected axis.

        Returns:
            Axis query parameter dictionary
        """
        axis_map = {
            "X": "RIGHT",
            "Y": "TOP",
            "Z": "FRONT",
        }
        axis_value = axis_map.get(self.axis, "TOP")

        return {
            "btType": "BTMParameterQueryList-148",
            "queries": [
                {
                    "btType": "BTMIndividualQuery-138",
                    "deterministicIds": [],
                    "queryStatement": None,
                    "queryString": f'query = qCreatedBy(makeId("{axis_value}"), EntityType.EDGE);',
                }
            ],
            "parameterId": "axis",
            "parameterName": "",
            "libraryRelationType": "NONE",
        }

    def build(self) -> Dict[str, Any]:
        """Build the revolve feature JSON.

        Returns:
            Feature definition for Onshape API

        Raises:
            ValueError: If sketch feature ID is not set
        """
        if not self.sketch_feature_id:
            raise ValueError("Sketch feature ID must be set before building revolve")

        angle_expression = (
            f"#{self.angle_variable}" if self.angle_variable else f"{self.angle} deg"
        )

        return {
            "btType": "BTFeatureDefinitionCall-1406",
            "feature": {
                "btType": "BTMFeature-134",
                "featureType": "revolve",
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
                                "queryString": (
                                    f'query = qSketchRegion(id + "{self.sketch_feature_id}"'
                                    ', true);'
                                ),
                                "featureId": self.sketch_feature_id,
                                "deterministicIds": [],
                            }
                        ],
                        "parameterId": "entities",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    self._build_axis_query(),
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
                        "value": self.angle,
                        "units": "",
                        "expression": angle_expression,
                        "parameterId": "revolveAngle",
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
