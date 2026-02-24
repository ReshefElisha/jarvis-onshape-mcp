"""Boolean operation builder for Onshape."""

from enum import Enum
from typing import Any, Dict, List


class BooleanType(Enum):
    """Boolean operation type."""

    UNION = "UNION"
    SUBTRACT = "SUBTRACT"
    INTERSECT = "INTERSECT"


class BooleanBuilder:
    """Builder for creating Onshape boolean features."""

    def __init__(
        self,
        name: str = "Boolean",
        boolean_type: BooleanType = BooleanType.UNION,
    ):
        """Initialize boolean builder.

        Args:
            name: Name of the boolean feature
            boolean_type: Type of boolean operation
        """
        self.name = name
        self.boolean_type = boolean_type
        self.tool_body_queries: List[str] = []
        self.target_body_queries: List[str] = []

    def add_tool_body(self, body_id: str) -> "BooleanBuilder":
        """Add a tool body by its deterministic ID.

        Tool bodies are the bodies being combined into/subtracted from/
        intersected with the target.

        Args:
            body_id: Deterministic ID of the tool body

        Returns:
            Self for chaining
        """
        self.tool_body_queries.append(body_id)
        return self

    def add_target_body(self, body_id: str) -> "BooleanBuilder":
        """Add a target body by its deterministic ID.

        Target bodies are the bodies that receive the boolean operation.
        Required for SUBTRACT and INTERSECT operations.

        Args:
            body_id: Deterministic ID of the target body

        Returns:
            Self for chaining
        """
        self.target_body_queries.append(body_id)
        return self

    def build(self) -> Dict[str, Any]:
        """Build the boolean feature JSON.

        Returns:
            Feature definition for Onshape API

        Raises:
            ValueError: If required bodies are missing
        """
        if not self.tool_body_queries:
            raise ValueError("At least one tool body must be added")

        if self.boolean_type in (BooleanType.SUBTRACT, BooleanType.INTERSECT):
            if not self.target_body_queries:
                raise ValueError(
                    f"At least one target body must be added for {self.boolean_type.value} "
                    "operations"
                )

        parameters: List[Dict[str, Any]] = [
            {
                "btType": "BTMParameterEnum-145",
                "namespace": "",
                "enumName": "BooleanOperationType",
                "value": self.boolean_type.value,
                "parameterId": "booleanOperationType",
                "parameterName": "",
                "libraryRelationType": "NONE",
            },
            {
                "btType": "BTMParameterQueryList-148",
                "queries": [
                    {
                        "btType": "BTMIndividualQuery-138",
                        "deterministicIds": self.tool_body_queries,
                    }
                ],
                "parameterId": "tools",
                "parameterName": "",
                "libraryRelationType": "NONE",
            },
        ]

        if self.target_body_queries:
            parameters.append(
                {
                    "btType": "BTMParameterQueryList-148",
                    "queries": [
                        {
                            "btType": "BTMIndividualQuery-138",
                            "deterministicIds": self.target_body_queries,
                        }
                    ],
                    "parameterId": "targets",
                    "parameterName": "",
                    "libraryRelationType": "NONE",
                }
            )

        return {
            "btType": "BTFeatureDefinitionCall-1406",
            "feature": {
                "btType": "BTMFeature-134",
                "featureType": "boolean",
                "name": self.name,
                "suppressed": False,
                "namespace": "",
                "parameters": parameters,
            },
        }
