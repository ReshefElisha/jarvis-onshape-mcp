"""Offset construction-plane builder for Onshape.

Native `featureType="cPlane"` with `cplaneType=OFFSET` creates a datum
plane offset by a signed distance from a reference plane or face. The
reference is passed as a deterministic ID — either a standard datum
plane id (from `PartStudioManager.get_plane_id`) or a face id (from
`list_entities`). Confirmed live against `cad.onshape.com` for both
reference kinds (rel-1.213, 2026-04-17).
"""

from typing import Any, Dict, Optional, Union

from ._units import parse_length


class OffsetPlaneBuilder:
    """Builder for offset construction planes."""

    def __init__(
        self,
        name: str = "Offset Plane",
        reference_id: Optional[str] = None,
        offset: Union[float, int, str] = 10.0,
        flip: bool = False,
    ):
        """Initialize offset-plane builder.

        Args:
            name: Feature name shown in the tree.
            reference_id: Deterministic ID of the reference plane or face to
                offset from. Use `PartStudioManager.get_plane_id(... "Front"|
                "Top"|"Right")` for standard datums, or a face ID from
                `list_entities` to offset from existing geometry.
            offset: Signed offset distance. Bare numbers are mm; strings
                like "0.25 in" or "5 mm" carry explicit units. Sign follows
                the reference plane's outward normal (or use `flip`).
            flip: If True, invert the offset direction.
        """
        self.name = name
        self.reference_id = reference_id
        self.offset: Union[float, int, str] = offset
        self.offset_variable: Optional[str] = None
        self.flip = flip

    def set_reference(self, reference_id: str) -> "OffsetPlaneBuilder":
        self.reference_id = reference_id
        return self

    def set_offset(
        self,
        offset: Union[float, int, str],
        variable_name: Optional[str] = None,
    ) -> "OffsetPlaneBuilder":
        self.offset = offset
        self.offset_variable = variable_name
        return self

    def build(self) -> Dict[str, Any]:
        if not self.reference_id:
            raise ValueError("reference_id is required")

        if self.offset_variable:
            offset_expression = f"#{self.offset_variable}"
            offset_value_m = 0.0
        else:
            parsed = parse_length(self.offset)
            offset_expression = parsed.expression
            offset_value_m = parsed.meters

        return {
            "btType": "BTFeatureDefinitionCall-1406",
            "feature": {
                "btType": "BTMFeature-134",
                "featureType": "cPlane",
                "name": self.name,
                "suppressed": False,
                "namespace": "",
                "parameters": [
                    {
                        "btType": "BTMParameterEnum-145",
                        "namespace": "",
                        "enumName": "CPlaneType",
                        "value": "OFFSET",
                        "parameterId": "cplaneType",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    {
                        "btType": "BTMParameterQueryList-148",
                        "queries": [
                            {
                                "btType": "BTMIndividualQuery-138",
                                "deterministicIds": [self.reference_id],
                            }
                        ],
                        "parameterId": "entities",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "isInteger": False,
                        "value": offset_value_m,
                        "units": "",
                        "expression": offset_expression,
                        "parameterId": "offset",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    {
                        "btType": "BTMParameterBoolean-144",
                        "value": self.flip,
                        "parameterId": "oppositeDirection",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                ],
            },
        }
