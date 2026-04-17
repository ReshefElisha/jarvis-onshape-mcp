"""Export and translation management for Onshape."""
from typing import Any, Dict, Optional
from .client import OnshapeClient


class ExportManager:
    """Manager for exporting Onshape documents to various formats."""

    def __init__(self, client: OnshapeClient):
        self.client = client

    async def export_part_studio(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        format_name: str = "STL",
        part_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Export a Part Studio to a specified format.

        Uses the v11 direct translation endpoint.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Part Studio element ID
            format_name: Export format (STL, STEP, PARASOLID, GLTF, OBJ)
            part_id: Optional specific part ID to export

        Returns:
            Translation/export result with download URL or data
        """
        path = (
            f"/api/v11/partstudios/d/{document_id}/w/{workspace_id}"
            f"/e/{element_id}/translations"
        )
        data: Dict[str, Any] = {
            "formatName": format_name.upper(),
            "storeInDocument": False,
        }
        if part_id:
            data["partId"] = part_id

        return await self.client.post(path, data=data)

    async def export_assembly(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        format_name: str = "STL",
    ) -> Dict[str, Any]:
        """Export an Assembly to a specified format.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Assembly element ID
            format_name: Export format (STL, STEP, GLTF)

        Returns:
            Translation/export result
        """
        path = (
            f"/api/v11/assemblies/d/{document_id}/w/{workspace_id}"
            f"/e/{element_id}/translations"
        )
        data: Dict[str, Any] = {
            "formatName": format_name.upper(),
            "storeInDocument": False,
        }
        return await self.client.post(path, data=data)

    async def get_translation_status(
        self,
        translation_id: str,
    ) -> Dict[str, Any]:
        """Check the status of an export/translation.

        Args:
            translation_id: Translation ID from export request

        Returns:
            Translation status with state and result URL
        """
        path = f"/api/v6/translations/{translation_id}"
        return await self.client.get(path)
