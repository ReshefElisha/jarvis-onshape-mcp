"""Fillet feature builder for Onshape."""

from typing import Any, Dict, List, Optional


class FilletBuilder:
    """Builder for creating Onshape fillet features."""

    def __init__(
        self,
        name: str = "Fillet",
        radius: float = 0.1,
    ):
        """Initialize fillet builder.

        Args:
            name: Name of the fillet feature
            radius: Fillet radius in inches
        """
        self.name = name
        self.radius = radius
        self.radius_variable: Optional[str] = None
        self.edge_queries: List[str] = []

    def set_radius(self, radius: float, variable_name: Optional[str] = None) -> "FilletBuilder":
        """Set fillet radius.

        Args:
            radius: Radius in inches
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

        radius_expression = (
            f"#{self.radius_variable}" if self.radius_variable else f"{self.radius} in"
        )

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
                        "value": self.radius,
                        "units": "",
                        "expression": radius_expression,
                        "parameterId": "radius",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                ],
            },
        }
