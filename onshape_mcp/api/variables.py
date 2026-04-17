"""Variable Studio management for Onshape.

Modern Onshape stores user variables in a dedicated Variable Studio element
(parallel to Part Studio / Assembly / Feature Studio). The Part Studio's
`/variables` GET endpoint is read-only on modern docs and POSTing to it 404s
-- which is the dogfooder bug #1 z5rz5fhl reported. The fix is to write to a
Variable Studio's variables endpoint instead, and let Onshape's expression
resolver pull `#name` references from VS elements in the same workspace.

Endpoints (all under the `variables` resource family, NOT `variablestudios`):
    POST /api/v6/variables/d/{did}/w/{wid}/variablestudio
        body: {"name": "<vs name>"}
        -> creates a VARIABLESTUDIO element, returns BTDocumentElementInfo
    POST /api/v6/variables/d/{did}/w/{wid}/e/{vs_eid}/variables
        body: [{"name", "type", "expression", "description"?}, ...]
        -> writes/replaces variables in the VS
    GET  /api/v6/variables/d/{did}/w/{wid}/e/{vs_eid}/variables
        -> returns [{"variableStudioReference": null, "variables": [...]}]

Probe details: scratchpad/variables-probe-2.md.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel
from .client import OnshapeClient


VariableType = Literal["LENGTH", "ANGLE", "NUMBER", "ANY"]


class Variable(BaseModel):
    """A variable in an Onshape Variable Studio."""

    name: str
    expression: str
    type: Optional[str] = None
    description: Optional[str] = None
    value: Optional[Any] = None  # populated by GET responses; not settable


class VariableManager:
    """Manager for Onshape Variable Studios + the variables they contain."""

    def __init__(self, client: OnshapeClient):
        self.client = client

    async def create_variable_studio(
        self, document_id: str, workspace_id: str, name: str
    ) -> str:
        """Create a new Variable Studio element in a workspace.

        Returns the new element's id (use it for set_variables / get_variables).
        """
        path = f"/api/v6/variables/d/{document_id}/w/{workspace_id}/variablestudio"
        response = await self.client.post(path, data={"name": name})
        vs_id = response.get("id")
        if not vs_id:
            raise RuntimeError(
                f"Variable Studio creation returned no id: {response!r}"
            )
        return vs_id

    async def get_variables(
        self, document_id: str, workspace_id: str, element_id: str
    ) -> List[Variable]:
        """Get all variables from a Variable Studio (or PS, for backwards compat).

        The endpoint returns `[{variableStudioReference, variables: [...]}]` --
        a list of one wrapper. Earlier code iterated the wrapper as if it were
        a variable, yielding empty rows; this flattens correctly.

        For Part Studio element ids, returns variables owned by that PS only
        (typically empty on modern docs; VS variables don't propagate to the
        PS variables endpoint even though `#name` references resolve fine).
        """
        path = f"/api/v6/variables/d/{document_id}/w/{workspace_id}/e/{element_id}/variables"
        response = await self.client.get(path)

        variables: List[Variable] = []
        for wrapper in response or []:
            if not isinstance(wrapper, dict):
                continue
            for var_data in wrapper.get("variables") or []:
                variables.append(
                    Variable(
                        name=var_data.get("name", ""),
                        expression=var_data.get("expression", ""),
                        type=var_data.get("type"),
                        description=var_data.get("description") or None,
                        value=var_data.get("value"),
                    )
                )
        return variables

    async def set_variables(
        self,
        document_id: str,
        workspace_id: str,
        variable_studio_element_id: str,
        variables: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Write a batch of variables to a Variable Studio. Replaces any
        existing variables with the same name.

        Each entry: `{"name", "type", "expression", "description"?}`. `type`
        defaults to "LENGTH" if absent (most common in CAD).
        """
        if not variables:
            raise ValueError("variables list must not be empty")

        path = (
            f"/api/v6/variables/d/{document_id}/w/{workspace_id}"
            f"/e/{variable_studio_element_id}/variables"
        )
        body: List[Dict[str, Any]] = []
        for v in variables:
            name = v.get("name")
            expression = v.get("expression")
            if not name or not expression:
                raise ValueError(f"variable missing name or expression: {v!r}")
            entry: Dict[str, Any] = {
                "name": name,
                "expression": expression,
                "type": v.get("type", "LENGTH"),
            }
            description = v.get("description")
            if description:
                entry["description"] = description
            body.append(entry)

        return await self.client.post(path, data=body)

    async def set_variable(
        self,
        document_id: str,
        workspace_id: str,
        variable_studio_element_id: str,
        name: str,
        expression: str,
        description: Optional[str] = None,
        type: VariableType = "LENGTH",
    ) -> Dict[str, Any]:
        """Convenience wrapper for the single-variable case.

        Targets a VARIABLE STUDIO element id (NOT a Part Studio id -- the PS
        path is read-only on modern docs). Use `create_variable_studio` if the
        workspace doesn't have one yet.

        `description` is positional after `expression` for backwards-compat
        with callers that predate the type-aware Variable Studio surface.
        """
        return await self.set_variables(
            document_id,
            workspace_id,
            variable_studio_element_id,
            [
                {
                    "name": name,
                    "expression": expression,
                    "type": type,
                    "description": description,
                }
            ],
        )

    async def get_configuration_definition(
        self, document_id: str, workspace_id: str, element_id: str
    ) -> Dict[str, Any]:
        """Get configuration definition for an element.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Element ID

        Returns:
            Configuration definition
        """
        path = f"/api/v6/elements/d/{document_id}/w/{workspace_id}/e/{element_id}/configuration"
        return await self.client.get(path)
