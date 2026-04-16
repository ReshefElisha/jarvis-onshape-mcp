"""Thicken feature builder for Onshape."""

from typing import Any, Dict, Optional, Union
from enum import Enum

from ._units import parse_length


class ThickenType(Enum):
    """Thicken operation types."""

    NEW = "NEW"
    ADD = "ADD"
    REMOVE = "REMOVE"
    INTERSECT = "INTERSECT"


class ThickenBuilder:
    """Builder for creating thicken features in Onshape Part Studios."""

    def __init__(
        self, name: str, sketch_feature_id: str, operation_type: ThickenType = ThickenType.NEW
    ):
        """Initialize thicken builder.

        Args:
            name: Name for the thicken feature
            sketch_feature_id: ID of the sketch feature to thicken
            operation_type: Type of boolean operation (NEW, ADD, REMOVE, INTERSECT)
        """
        self.name = name
        self.sketch_feature_id = sketch_feature_id
        self.operation_type = operation_type
        self.thickness_value: Optional[Union[float, int, str]] = None
        self.thickness_variable: Optional[str] = None
        self.midplane = False
        self.opposite_direction = False

    def set_thickness(
        self,
        thickness: Union[float, int, str],
        variable_name: Optional[str] = None,
    ) -> "ThickenBuilder":
        """Set the thickness for the thicken operation.

        Args:
            thickness: Thickness. Bare numbers default to mm; strings like
                "0.25 in" or "6 mm" carry explicit units.
            variable_name: Optional variable name to use for thickness

        Returns:
            Self for method chaining
        """
        self.thickness_value = thickness
        self.thickness_variable = variable_name
        return self

    def set_midplane(self, midplane: bool = True) -> "ThickenBuilder":
        """Set whether to thicken symmetrically from the sketch plane.

        Args:
            midplane: True to thicken symmetrically

        Returns:
            Self for method chaining
        """
        self.midplane = midplane
        return self

    def set_opposite_direction(self, opposite: bool = True) -> "ThickenBuilder":
        """Set whether to thicken in opposite direction.

        Args:
            opposite: True to thicken in opposite direction

        Returns:
            Self for method chaining
        """
        self.opposite_direction = opposite
        return self

    def build(self) -> Dict[str, Any]:
        """Build the thicken feature JSON for Onshape API.

        Returns:
            Feature definition as dictionary

        Raises:
            ValueError: If required parameters are missing
        """
        if self.thickness_value is None and self.thickness_variable is None:
            raise ValueError("Thickness must be set")

        # Determine thickness expression (and a matching numeric meter value
        # for the `value` field; Onshape prefers a stale-cleared 0 when the
        # expression is a variable reference so the solver re-evaluates).
        if self.thickness_variable:
            thickness_expr = f"#{self.thickness_variable}"
        else:
            thickness_expr = parse_length(self.thickness_value).expression

        # Build the feature data
        feature = {
            "btType": "BTMFeature-134",
            "name": self.name,
            "suppressed": False,
            "namespace": "",
            "featureType": "thicken",
            "parameters": [
                {
                    "btType": "BTMParameterEnum-145",
                    "enumName": "NewBodyOperationType",
                    "value": self.operation_type.value,
                    "parameterId": "operationType",
                },
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
                },
                {
                    "btType": "BTMParameterBoolean-144",
                    "value": self.midplane,
                    "parameterId": "midplane",
                },
                {
                    "btType": "BTMParameterQuantity-147",
                    "expression": thickness_expr,
                    "parameterId": "thickness1",
                },
                {
                    "btType": "BTMParameterBoolean-144",
                    "value": self.opposite_direction,
                    "parameterId": "oppositeDirection",
                },
                {
                    "btType": "BTMParameterQuantity-147",
                    "expression": "0 mm",
                    "parameterId": "thickness2",
                },
            ],
        }

        return feature
