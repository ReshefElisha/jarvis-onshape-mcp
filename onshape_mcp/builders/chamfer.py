"""Chamfer feature builder for Onshape."""

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ._units import parse_length


class ChamferType(Enum):
    """Chamfer geometry type."""

    EQUAL_OFFSETS = "EQUAL_OFFSETS"
    TWO_OFFSETS = "TWO_OFFSETS"
    OFFSET_ANGLE = "OFFSET_ANGLE"


class ChamferBuilder:
    """Builder for creating Onshape chamfer features."""

    def __init__(
        self,
        name: str = "Chamfer",
        distance: Union[float, int, str] = 0.1,
        chamfer_type: ChamferType = ChamferType.EQUAL_OFFSETS,
    ):
        """Initialize chamfer builder.

        Args:
            name: Name of the chamfer feature
            distance: Chamfer distance. Bare numbers default to mm.
            chamfer_type: Type of chamfer geometry
        """
        self.name = name
        self.distance: Union[float, int, str] = distance
        self.distance_variable: Optional[str] = None
        self.chamfer_type = chamfer_type
        self.edge_queries: List[str] = []

    def set_distance(
        self,
        distance: Union[float, int, str],
        variable_name: Optional[str] = None,
    ) -> "ChamferBuilder":
        """Set chamfer distance.

        Args:
            distance: Distance. Bare numbers are mm; pass `"0.125 in"` etc.
                for explicit units.
            variable_name: Optional variable name to reference

        Returns:
            Self for chaining
        """
        self.distance = distance
        self.distance_variable = variable_name
        return self

    def add_edge(self, edge_id: str) -> "ChamferBuilder":
        """Add an edge to chamfer by its deterministic ID.

        Args:
            edge_id: Deterministic ID of the edge

        Returns:
            Self for chaining
        """
        self.edge_queries.append(edge_id)
        return self

    def build(self) -> Dict[str, Any]:
        """Build the chamfer feature JSON.

        Returns:
            Feature definition for Onshape API

        Raises:
            ValueError: If no edges have been added
        """
        if not self.edge_queries:
            raise ValueError("At least one edge must be added")

        if self.distance_variable:
            distance_expression = f"#{self.distance_variable}"
            distance_value_m = 0.0
        else:
            parsed = parse_length(self.distance)
            distance_expression = parsed.expression
            distance_value_m = parsed.meters

        return {
            "btType": "BTFeatureDefinitionCall-1406",
            "feature": {
                "btType": "BTMFeature-134",
                "featureType": "chamfer",
                "name": self.name,
                "suppressed": False,
                "namespace": "",
                "parameters": [
                    {
                        "btType": "BTMParameterQueryList-148",
                        "queries": [
                            {
                                "btType": "BTMIndividualQuery-138",
                                "deterministicIds": self.edge_queries,
                            }
                        ],
                        "parameterId": "entities",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    {
                        "btType": "BTMParameterEnum-145",
                        "namespace": "",
                        "enumName": "ChamferType",
                        "value": self.chamfer_type.value,
                        "parameterId": "chamferType",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "isInteger": False,
                        "value": distance_value_m,
                        "units": "",
                        "expression": distance_expression,
                        "parameterId": "width",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                ],
            },
        }
