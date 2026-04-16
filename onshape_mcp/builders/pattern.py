"""Pattern feature builders for Onshape."""

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ._units import parse_length


class PatternType(Enum):
    """Pattern entity type."""

    PART = "PART"
    FEATURE = "FEATURE"
    FACE = "FACE"


class LinearPatternBuilder:
    """Builder for creating Onshape linear pattern features."""

    def __init__(
        self,
        name: str = "Linear pattern",
        distance: Union[float, int, str] = 1.0,
        count: int = 2,
        direction_edge_id: Optional[str] = None,
    ):
        """Initialize linear pattern builder.

        Args:
            name: Name of the pattern feature
            distance: Spacing between instances. Bare numbers default to mm.
            count: Total number of instances including the original
            direction_edge_id: Deterministic id of an edge whose direction
                defines the pattern axis. Get from list_entities(kinds=["edges"])
                or from a sketch line you drew specifically as a direction
                reference. REQUIRED for the pattern to build: Onshape has no
                implicit "world X" axis usable via qCreatedBy() on a datum
                plane, so the caller MUST pick an edge.
        """
        self.name = name
        self.distance: Union[float, int, str] = distance
        self.count = count
        self.distance_variable: Optional[str] = None
        self.feature_queries: List[str] = []
        self.direction_axis = "X"  # legacy field kept for caller-compat
        self.direction_edge_id: Optional[str] = direction_edge_id

    def set_distance(
        self,
        distance: Union[float, int, str],
        variable_name: Optional[str] = None,
    ) -> "LinearPatternBuilder":
        """Set the distance between pattern instances.

        Args:
            distance: Distance. Bare numbers are mm; pass "<value> <unit>" for
                explicit units.
            variable_name: Optional variable name to reference

        Returns:
            Self for chaining
        """
        self.distance = distance
        self.distance_variable = variable_name
        return self

    def set_count(self, count: int) -> "LinearPatternBuilder":
        """Set the number of pattern instances.

        Args:
            count: Total number of instances including the original

        Returns:
            Self for chaining
        """
        self.count = count
        return self

    def add_feature(self, feature_id: str) -> "LinearPatternBuilder":
        """Add a feature to pattern by its deterministic ID.

        Args:
            feature_id: Deterministic ID of the feature to pattern

        Returns:
            Self for chaining
        """
        self.feature_queries.append(feature_id)
        return self

    def set_direction(self, axis: str) -> "LinearPatternBuilder":
        """LEGACY: axis name. Prefer set_direction_edge with a real edge id.

        Kept for callers that still pass axis=X/Y/Z. On its own, axis=X/Y/Z
        will produce an ERROR-state pattern feature because Onshape's
        datum planes (Right/Top/Front) don't carry EDGE entities. Pair it
        with set_direction_edge() or pass `direction_edge_id` in __init__.
        """
        self.direction_axis = axis
        return self

    def set_direction_edge(self, edge_id: str) -> "LinearPatternBuilder":
        """Set the pattern direction via an edge's deterministic ID.

        Get the edge id from list_entities(kinds=["edges"]) — pick any line
        edge pointing the direction you want the pattern to propagate in.
        """
        self.direction_edge_id = edge_id
        return self

    def _build_direction_query(self) -> Dict[str, Any]:
        """Build the direction-edge query parameter.

        The pattern won't regenerate without a real edge to follow. Callers
        MUST have set a direction_edge_id (either via __init__ or
        set_direction_edge()). We intentionally do NOT fall back to the old
        axis=X/Y/Z datum-plane path — it always failed silently in the
        builder's mock tests and loud-ERRORed at the API layer. See
        tools/cad_challenges/test_linear_pattern_holes.py regression marker.
        """
        if not self.direction_edge_id:
            raise ValueError(
                "LinearPatternBuilder needs a direction_edge_id. Call "
                "list_entities(kinds=['edges']) and pick an edge pointing "
                "the direction you want the pattern to propagate; pass its "
                "id as direction_edge_id."
            )

        return {
            "btType": "BTMParameterQueryList-148",
            "queries": [
                {
                    "btType": "BTMIndividualQuery-138",
                    "deterministicIds": [self.direction_edge_id],
                    "queryStatement": None,
                    "queryString": "",
                }
            ],
            "parameterId": "directionQuery",
            "parameterName": "",
            "libraryRelationType": "NONE",
        }

    def build(self) -> Dict[str, Any]:
        """Build the linear pattern feature JSON.

        Returns:
            Feature definition for Onshape API

        Raises:
            ValueError: If no features have been added
        """
        if not self.feature_queries:
            raise ValueError("At least one feature must be added")

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
                "featureType": "linearPattern",
                "name": self.name,
                "suppressed": False,
                "namespace": "",
                "parameters": [
                    {
                        "btType": "BTMParameterQueryList-148",
                        "queries": [
                            {
                                "btType": "BTMIndividualQuery-138",
                                "deterministicIds": self.feature_queries,
                            }
                        ],
                        "parameterId": "entities",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    self._build_direction_query(),
                    {
                        "btType": "BTMParameterEnum-145",
                        "namespace": "",
                        "enumName": "PatternType",
                        "value": PatternType.FEATURE.value,
                        "parameterId": "patternType",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "isInteger": False,
                        "value": distance_value_m,
                        "units": "",
                        "expression": distance_expression,
                        "parameterId": "distance",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "isInteger": True,
                        "value": self.count,
                        "units": "",
                        "expression": str(self.count),
                        "parameterId": "instanceCount",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                ],
            },
        }


class CircularPatternBuilder:
    """Builder for creating Onshape circular pattern features."""

    def __init__(
        self,
        name: str = "Circular pattern",
        count: int = 4,
    ):
        """Initialize circular pattern builder.

        Args:
            name: Name of the pattern feature
            count: Total number of instances including the original
        """
        self.name = name
        self.count = count
        self.angle = 360.0
        self.angle_variable: Optional[str] = None
        self.feature_queries: List[str] = []
        self.axis = "Z"

    def set_count(self, count: int) -> "CircularPatternBuilder":
        """Set the number of pattern instances.

        Args:
            count: Total number of instances including the original

        Returns:
            Self for chaining
        """
        self.count = count
        return self

    def set_angle(self, angle: float, variable_name: Optional[str] = None) -> "CircularPatternBuilder":
        """Set the total angle spread for the pattern.

        Args:
            angle: Total angle in degrees
            variable_name: Optional variable name to reference

        Returns:
            Self for chaining
        """
        self.angle = angle
        self.angle_variable = variable_name
        return self

    def add_feature(self, feature_id: str) -> "CircularPatternBuilder":
        """Add a feature to pattern by its deterministic ID.

        Args:
            feature_id: Deterministic ID of the feature to pattern

        Returns:
            Self for chaining
        """
        self.feature_queries.append(feature_id)
        return self

    def set_axis(self, axis: str) -> "CircularPatternBuilder":
        """Set the pattern rotation axis.

        Args:
            axis: Rotation axis ("X", "Y", or "Z")

        Returns:
            Self for chaining
        """
        self.axis = axis
        return self

    def _build_axis_query(self) -> Dict[str, Any]:
        """Build the rotation axis query parameter.

        Returns:
            Axis query parameter dictionary
        """
        axis_map = {
            "X": "RIGHT",
            "Y": "TOP",
            "Z": "FRONT",
        }
        axis_value = axis_map.get(self.axis, "FRONT")

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
            "parameterId": "axisQuery",
            "parameterName": "",
            "libraryRelationType": "NONE",
        }

    def build(self) -> Dict[str, Any]:
        """Build the circular pattern feature JSON.

        Returns:
            Feature definition for Onshape API

        Raises:
            ValueError: If no features have been added
        """
        if not self.feature_queries:
            raise ValueError("At least one feature must be added")

        angle_expression = (
            f"#{self.angle_variable}" if self.angle_variable else f"{self.angle} deg"
        )

        return {
            "btType": "BTFeatureDefinitionCall-1406",
            "feature": {
                "btType": "BTMFeature-134",
                "featureType": "circularPattern",
                "name": self.name,
                "suppressed": False,
                "namespace": "",
                "parameters": [
                    {
                        "btType": "BTMParameterQueryList-148",
                        "queries": [
                            {
                                "btType": "BTMIndividualQuery-138",
                                "deterministicIds": self.feature_queries,
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
                        "enumName": "PatternType",
                        "value": PatternType.FEATURE.value,
                        "parameterId": "patternType",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "isInteger": False,
                        "value": self.angle,
                        "units": "",
                        "expression": angle_expression,
                        "parameterId": "angle",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "isInteger": True,
                        "value": self.count,
                        "units": "",
                        "expression": str(self.count),
                        "parameterId": "instanceCount",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                ],
            },
        }
