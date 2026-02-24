"""Assembly management for Onshape."""

from typing import Any, Dict, List
from .client import OnshapeClient


class AssemblyManager:
    """Manager for Onshape Assemblies."""

    def __init__(self, client: OnshapeClient):
        """Initialize the Assembly manager.

        Args:
            client: Onshape API client
        """
        self.client = client

    async def get_assembly_definition(
        self, document_id: str, workspace_id: str, element_id: str
    ) -> Dict[str, Any]:
        """Get the definition of an assembly.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Assembly element ID

        Returns:
            Assembly definition data
        """
        path = f"/api/v9/assemblies/d/{document_id}/w/{workspace_id}/e/{element_id}"
        return await self.client.get(path)

    async def create_assembly(
        self, document_id: str, workspace_id: str, name: str
    ) -> Dict[str, Any]:
        """Create a new Assembly in a document.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            name: Name for the new Assembly

        Returns:
            API response with new Assembly info
        """
        path = f"/api/v9/assemblies/d/{document_id}/w/{workspace_id}"
        data = {"name": name}
        return await self.client.post(path, data=data)

    async def add_instance(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        part_studio_element_id: str,
        part_id: str | None = None,
        is_assembly: bool = False,
    ) -> Dict[str, Any]:
        """Add an instance to an assembly.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Assembly element ID
            part_studio_element_id: Element ID of the Part Studio or Assembly to insert
            part_id: Part ID to insert (None for whole Part Studio)
            is_assembly: Whether the instance is an assembly

        Returns:
            API response
        """
        path = (
            f"/api/v9/assemblies/d/{document_id}/w/{workspace_id}/e/{element_id}"
            f"/instances"
        )
        if is_assembly:
            data: Dict[str, Any] = {
                "documentId": document_id,
                "elementId": part_studio_element_id,
                "isAssembly": True,
            }
        else:
            data = {
                "documentId": document_id,
                "elementId": part_studio_element_id,
                "partId": part_id,
                "isAssembly": False,
                "isWholePartStudio": part_id is None,
            }
        return await self.client.post(path, data=data)

    async def delete_instance(
        self, document_id: str, workspace_id: str, element_id: str, node_id: str
    ) -> Dict[str, Any]:
        """Delete an instance from an assembly.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Assembly element ID
            node_id: Node ID of the instance to delete

        Returns:
            API response
        """
        path = (
            f"/api/v9/assemblies/d/{document_id}/w/{workspace_id}/e/{element_id}"
            f"/instance/nodeid/{node_id}"
        )
        return await self.client.delete(path)

    async def transform_occurrences(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        occurrences: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Apply transforms to assembly occurrences.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Assembly element ID
            occurrences: List of occurrence transforms, each with "path"
                (list of instance IDs) and "transform" (16-element 4x4 matrix)

        Returns:
            API response
        """
        path = (
            f"/api/v9/assemblies/d/{document_id}/w/{workspace_id}/e/{element_id}"
            f"/occurrencetransforms"
        )
        data = {
            "isRelative": True,
            "occurrences": [{"path": occ["path"]} for occ in occurrences],
            "transform": occurrences[0]["transform"],
        }
        return await self.client.post(path, data=data)

    async def add_feature(
        self, document_id: str, workspace_id: str, element_id: str, feature_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Add a feature to an assembly (mates, mate connectors, etc.).

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Assembly element ID
            feature_data: Feature definition JSON

        Returns:
            API response
        """
        path = f"/api/v9/assemblies/d/{document_id}/w/{workspace_id}/e/{element_id}/features"
        return await self.client.post(path, data=feature_data)
