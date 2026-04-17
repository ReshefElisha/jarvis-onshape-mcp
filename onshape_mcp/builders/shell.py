"""Shell feature builder for Onshape.

Native `featureType="shell"` accepts three parameters: `entities` (the
faces to remove so the remaining body becomes a thin-walled hollow),
`thickness` (positive length), and `oppositeDirection` (false = inward
shell, true = outward offset). Inward is the common enclosure case and
is the default here. Confirmed live against `cad.onshape.com`
(rel-1.213, 2026-04-17).
"""

from typing import Any, Dict, List, Optional, Union

from ._units import parse_length


class ShellBuilder:
    """Builder for creating Onshape shell features."""

    def __init__(
        self,
        name: str = "Shell",
        thickness: Union[float, int, str] = 1.0,
        outward: bool = False,
    ):
        """Initialize shell builder.

        Args:
            name: Feature name.
            thickness: Wall thickness. Bare numbers are mm; strings like
                "0.0625 in" or "2 mm" carry explicit units.
            outward: If False (default), shell inward — the remaining body
                keeps the original bounding box and gets hollowed on the
                inside. If True, the shell thickness is added outside the
                original surface (rare; grows the bbox).
        """
        self.name = name
        self.thickness: Union[float, int, str] = thickness
        self.thickness_variable: Optional[str] = None
        self.outward = outward
        self.face_queries: List[str] = []

    def add_face(self, face_id: str) -> "ShellBuilder":
        """Add a face to remove (the wall is built from every face EXCEPT
        the ones added here).

        Args:
            face_id: Deterministic ID of the face (from `list_entities`).

        Returns:
            Self for chaining.
        """
        self.face_queries.append(face_id)
        return self

    def set_thickness(
        self,
        thickness: Union[float, int, str],
        variable_name: Optional[str] = None,
    ) -> "ShellBuilder":
        """Set the shell thickness.

        Args:
            thickness: Wall thickness (bare number = mm; string for units).
            variable_name: Optional variable name to reference.

        Returns:
            Self for chaining.
        """
        self.thickness = thickness
        self.thickness_variable = variable_name
        return self

    def build(self) -> Dict[str, Any]:
        if not self.face_queries:
            raise ValueError("At least one face must be added to remove")

        if self.thickness_variable:
            thickness_expression = f"#{self.thickness_variable}"
            thickness_value_m = 0.0
        else:
            parsed = parse_length(self.thickness)
            thickness_expression = parsed.expression
            thickness_value_m = parsed.meters

        return {
            "btType": "BTFeatureDefinitionCall-1406",
            "feature": {
                "btType": "BTMFeature-134",
                "featureType": "shell",
                "name": self.name,
                "suppressed": False,
                "namespace": "",
                "parameters": [
                    {
                        "btType": "BTMParameterQueryList-148",
                        "queries": [
                            {
                                "btType": "BTMIndividualQuery-138",
                                "deterministicIds": self.face_queries,
                            }
                        ],
                        "parameterId": "entities",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    {
                        "btType": "BTMParameterQuantity-147",
                        "isInteger": False,
                        "value": thickness_value_m,
                        "units": "",
                        "expression": thickness_expression,
                        "parameterId": "thickness",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                    {
                        "btType": "BTMParameterBoolean-144",
                        "value": self.outward,
                        "parameterId": "oppositeDirection",
                        "parameterName": "",
                        "libraryRelationType": "NONE",
                    },
                ],
            },
        }
