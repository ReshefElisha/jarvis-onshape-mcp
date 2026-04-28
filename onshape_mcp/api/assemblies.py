"""Assembly management for Onshape."""

from typing import Any, Dict, List
from urllib.parse import quote
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
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        params: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Get the definition of an assembly.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Assembly element ID
            params: Optional query parameters (e.g. includeMateFeatures)

        Returns:
            Assembly definition data
        """
        path = f"/api/v9/assemblies/d/{document_id}/w/{workspace_id}/e/{element_id}"
        return await self.client.get(path, params=params)

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
        source_document_id: str | None = None,
        source_workspace_id: str | None = None,
        source_version_id: str | None = None,
    ) -> Dict[str, Any]:
        """Add an instance to an assembly.

        Args:
            document_id: Document ID containing the assembly
            workspace_id: Workspace ID containing the assembly
            element_id: Assembly element ID
            part_studio_element_id: Element ID of the Part Studio or Assembly to insert
            part_id: Part ID to insert (None for whole Part Studio)
            is_assembly: Whether the instance is an assembly
            source_document_id: Document ID containing the part to insert. Defaults
                to document_id (same-doc insert). Set this for cross-document inserts
                (e.g. inserting from a public catalog).
            source_workspace_id: Workspace ID of the source document. Used only as
                a hint for resolving the latest published version when
                source_version_id is not given. Onshape requires linked-document
                references to be locked to a versionId, not a workspaceId.
            source_version_id: Version ID of the source document. Required for
                cross-document inserts because Onshape rejects workspace-only
                references with "Linked document references require a version
                identifier". If omitted on a cross-doc insert, this method
                auto-resolves the latest non-"Start" published version of
                source_document_id.

        Returns:
            API response
        """
        path = (
            f"/api/v9/assemblies/d/{document_id}/w/{workspace_id}/e/{element_id}"
            f"/instances"
        )
        src_doc = source_document_id or document_id
        is_cross_doc = src_doc != document_id

        if is_cross_doc and not source_version_id:
            # Onshape requires versionId for cross-doc inserts. Auto-resolve the
            # latest published version (Onshape returns versions in chronological
            # order; the implicit "Start" version sits at index 0 with no real
            # geometry, so pick the newest non-"Start" entry).
            versions = await self.client.get(
                f"/api/v9/documents/d/{src_doc}/versions"
            )
            published = [
                v for v in versions
                if v.get("name") and v["name"] != "Start"
            ]
            if not published:
                raise RuntimeError(
                    f"Cannot insert from document {src_doc}: no published "
                    f"versions found. Ask the source document's owner to "
                    f"create a version (right-click document → Create version)."
                )
            source_version_id = published[-1]["id"]

        if is_assembly:
            data: Dict[str, Any] = {
                "documentId": src_doc,
                "elementId": part_studio_element_id,
                "isAssembly": True,
            }
        else:
            data = {
                "documentId": src_doc,
                "elementId": part_studio_element_id,
                "partId": part_id,
                "isAssembly": False,
                "isWholePartStudio": part_id is None,
            }
        if is_cross_doc:
            data["versionId"] = source_version_id
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
        is_relative: bool = True,
    ) -> Dict[str, Any]:
        """Apply transforms to assembly occurrences.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Assembly element ID
            occurrences: List of occurrence transforms, each with "path"
                (list of instance IDs) and "transform" (16-element 4x4 matrix)
            is_relative: If True (default), transform is applied relative to
                current position. If False, transform sets absolute position.

        Returns:
            API response
        """
        path = (
            f"/api/v9/assemblies/d/{document_id}/w/{workspace_id}/e/{element_id}"
            f"/occurrencetransforms"
        )
        data = {
            "isRelative": is_relative,
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

    async def delete_feature(
        self, document_id: str, workspace_id: str, element_id: str, feature_id: str
    ) -> Dict[str, Any]:
        """Delete a feature from an assembly (mates, mate connectors, etc.).

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Assembly element ID
            feature_id: Feature ID to delete

        Returns:
            API response
        """
        encoded_fid = quote(feature_id, safe="")
        path = (
            f"/api/v9/assemblies/d/{document_id}/w/{workspace_id}/e/{element_id}"
            f"/features/featureid/{encoded_fid}"
        )
        return await self.client.delete(path)

    async def get_features(
        self, document_id: str, workspace_id: str, element_id: str
    ) -> Dict[str, Any]:
        """Get all features from an assembly (mates, mate connectors, etc.).

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Assembly element ID

        Returns:
            Features data including feature list with states
        """
        path = f"/api/v9/assemblies/d/{document_id}/w/{workspace_id}/e/{element_id}/features"
        return await self.client.get(path)
