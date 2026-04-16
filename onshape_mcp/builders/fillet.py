"""Fillet feature builder for Onshape."""

from typing import Any, Dict, List, Optional, Union

from ._units import parse_length


class FilletBuilder:
    """Builder for creating Onshape fillet features."""

    def __init__(
        self,
        name: str = "Fillet",
        radius: Union[float, int, str] = 0.1,
    ):
        """Initialize fillet builder.

        Args:
            name: Name of the fillet feature
            radius: Fillet radius. Bare numbers default to mm; strings like
                "0.125 in" or "2 mm" carry explicit units.
        """
        self.name = name
        self.radius: Union[float, int, str] = radius
        self.radius_variable: Optional[str] = None
        self.edge_queries: List[str] = []

    def set_radius(
        self,
        radius: Union[float, int, str],
        variable_name: Optional[str] = None,
    ) -> "FilletBuilder":
        """Set fillet radius.

        Args:
            radius: Radius. Bare numbers are mm; pass a "<value> <unit>" string
                for explicit units.
            variable_name: Optional variable name to reference

        Returns:
            Self for chaining
        """
        self.radius = radius
        self.radius_variable = variable_name
        return self

    def add_edge(self, edge_id: str) -> "FilletBuilder":
        """Add an edge to fillet by its deterministic ID.

        Args:
            edge_id: Deterministic ID of the edge

        Returns:
            Self for chaining
        """
        self.edge_queries.append(edge_id)
        return self

    def build(self) -> Dict[str, Any]:
        """Build the fillet feature JSON.

        Returns:
            Feature definition for Onshape API

        Raises:
            ValueError: If no edges have been added
        """
        if not self.edge_queries:
            raise ValueError("At least one edge must be added")

        if self.radius_variable:
            radius_expression = f"#{self.radius_variable}"
            radius_value_m = 0.0
        else:
            parsed = parse_length(self.radius)
            radius_expression = parsed.expression
            radius_value_m = parsed.meters

        return {
            "btType": "BTFeatureDefinitionCall-1406",
            "feature": {
                "btType": "BTMFeature-134",
                "featureType": "fillet",
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
                        "btType": "BTMParameterQuantity-147",
                        "isInteger": False,
                        "value": radius_value_m,
                        "units": "",
                        "expression": radius_expression,
                        "parameterId": "radius",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                ],
            },
        }
