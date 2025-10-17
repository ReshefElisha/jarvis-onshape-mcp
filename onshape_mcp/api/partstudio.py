"""Part Studio management for Onshape."""

from typing import Any, Dict, List
from .client import OnshapeClient


class PartStudioManager:
    """Manager for Onshape Part Studios."""

    def __init__(self, client: OnshapeClient):
        """Initialize the Part Studio manager.

        Args:
            client: Onshape API client
        """
        self.client = client
        self._plane_id_cache: Dict[str, str] = {}

    async def get_features(
        self, document_id: str, workspace_id: str, element_id: str
    ) -> Dict[str, Any]:
        """Get all features from a Part Studio.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Part Studio element ID

        Returns:
            Features data
        """
        path = f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/features"
        return await self.client.get(path)

    async def add_feature(
        self, document_id: str, workspace_id: str, element_id: str, feature_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Add a feature to a Part Studio.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Part Studio element ID
            feature_data: Feature definition JSON

        Returns:
            API response
        """
        path = f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}/features"
        return await self.client.post(path, data=feature_data)

    async def update_feature(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        feature_id: str,
        feature_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update an existing feature in a Part Studio.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Part Studio element ID
            feature_id: Feature ID to update
            feature_data: Updated feature definition JSON

        Returns:
            API response
        """
        path = (
            f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}"
            f"/features/featureid/{feature_id}"
        )
        return await self.client.post(path, data=feature_data)

    async def delete_feature(
        self, document_id: str, workspace_id: str, element_id: str, feature_id: str
    ) -> Dict[str, Any]:
        """Delete a feature from a Part Studio.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Part Studio element ID
            feature_id: Feature ID to delete

        Returns:
            API response
        """
        path = (
            f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}/e/{element_id}"
            f"/features/featureid/{feature_id}"
        )
        return await self.client.delete(path)

    async def get_parts(
        self, document_id: str, workspace_id: str, element_id: str
    ) -> List[Dict[str, Any]]:
        """Get all parts in a Part Studio.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Part Studio element ID

        Returns:
            List of parts
        """
        path = f"/api/v9/parts/d/{document_id}/w/{workspace_id}/e/{element_id}"
        response = await self.client.get(path)
        return response

    async def create_part_studio(
        self, document_id: str, workspace_id: str, name: str
    ) -> Dict[str, Any]:
        """Create a new Part Studio in a document.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            name: Name for the new Part Studio

        Returns:
            API response with new Part Studio info
        """
        path = f"/api/v9/partstudios/d/{document_id}/w/{workspace_id}"
        data = {"name": name}
        return await self.client.post(path, data=data)

    async def get_plane_id(
        self, document_id: str, workspace_id: str, element_id: str, plane_name: str
    ) -> str:
        """Get the deterministic ID for a standard plane (Front, Top, Right).

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Part Studio element ID
            plane_name: Name of the plane ("Front", "Top", or "Right")

        Returns:
            Deterministic ID of the plane (e.g., "JCC" for Front)

        Raises:
            ValueError: If plane name is invalid or ID cannot be retrieved
        """
        # Check cache first
        cache_key = f"{document_id}_{workspace_id}_{element_id}_{plane_name}"
        if cache_key in self._plane_id_cache:
            return self._plane_id_cache[cache_key]

        # Validate plane name
        valid_planes = {"Front", "Top", "Right"}
        if plane_name not in valid_planes:
            raise ValueError(f"Invalid plane name: {plane_name}. Must be one of {valid_planes}")

        # Standard plane IDs are consistent across Onshape Part Studios
        # These are the deterministic IDs for the default planes
        standard_plane_ids = {"Front": "JCC", "Top": "JDC", "Right": "JEC"}

        plane_id = standard_plane_ids[plane_name]
        self._plane_id_cache[cache_key] = plane_id
        return plane_id
