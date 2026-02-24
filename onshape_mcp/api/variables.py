"""Variable table management for Onshape Part Studios."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from .client import OnshapeClient


class Variable(BaseModel):
    """Represents a variable in an Onshape variable table."""

    name: str
    expression: str
    description: Optional[str] = None


class VariableManager:
    """Manager for Onshape variable tables."""

    def __init__(self, client: OnshapeClient):
        """Initialize the variable manager.

        Args:
            client: Onshape API client
        """
        self.client = client

    async def get_variables(
        self, document_id: str, workspace_id: str, element_id: str
    ) -> List[Variable]:
        """Get all variables from a Part Studio.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Part Studio element ID

        Returns:
            List of variables
        """
        path = f"/api/v6/variables/d/{document_id}/w/{workspace_id}/e/{element_id}/variables"
        response = await self.client.get(path)

        variables = []
        for var_data in response:
            variables.append(
                Variable(
                    name=var_data.get("name", ""),
                    expression=var_data.get("expression", ""),
                    description=var_data.get("description"),
                )
            )

        return variables

    async def set_variable(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        name: str,
        expression: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Set or update a variable in a Part Studio.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Part Studio element ID
            name: Variable name
            expression: Variable expression (e.g., "0.75 in")
            description: Optional variable description

        Returns:
            API response
        """
        path = f"/api/v6/variables/d/{document_id}/w/{workspace_id}/e/{element_id}/variables"

        data = [{"name": name, "expression": expression}]

        if description:
            data[0]["description"] = description

        return await self.client.post(path, data=data)

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
