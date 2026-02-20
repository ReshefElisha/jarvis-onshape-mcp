"""Document management for Onshape projects and documents."""

from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from .client import OnshapeClient


class DocumentInfo(BaseModel):
    """Represents an Onshape document."""

    id: str
    name: str
    created_at: datetime = Field(alias="createdAt")
    modified_at: datetime = Field(alias="modifiedAt")
    owner_id: str = Field(alias="ownerId")
    owner_name: Optional[str] = Field(default=None, alias="ownerName")
    public: bool = False
    description: Optional[str] = None
    thumbnail: Optional[str] = None

    class Config:
        populate_by_name = True


class WorkspaceInfo(BaseModel):
    """Represents a workspace within a document."""

    id: str
    name: str
    is_main: bool = Field(default=False, alias="isMain")
    created_at: Optional[datetime] = Field(default=None, alias="createdAt")
    modified_at: Optional[datetime] = Field(default=None, alias="modifiedAt")

    class Config:
        populate_by_name = True


class ElementInfo(BaseModel):
    """Represents an element (Part Studio, Assembly, etc.) in a document."""

    id: str
    name: str
    element_type: str = Field(alias="elementType")
    data_type: Optional[str] = Field(default=None, alias="dataType")
    thumbnail: Optional[str] = None

    class Config:
        populate_by_name = True


class DocumentManager:
    """Manager for Onshape documents and projects."""

    def __init__(self, client: OnshapeClient):
        """Initialize the document manager.

        Args:
            client: Onshape API client
        """
        self.client = client

    async def list_documents(
        self,
        filter_type: Optional[str] = None,
        sort_by: str = "modifiedAt",
        sort_order: str = "desc",
        limit: int = 20,
        offset: int = 0,
    ) -> List[DocumentInfo]:
        """List documents in the user's account.

        Args:
            filter_type: Filter by document type (0=all, 1=owned, 4=created, 5=shared)
            sort_by: Sort field (name, modifiedAt, createdAt)
            sort_order: Sort order (asc, desc)
            limit: Maximum number of documents to return
            offset: Offset for pagination

        Returns:
            List of document information
        """
        params = {"sortColumn": sort_by, "sortOrder": sort_order, "limit": limit, "offset": offset}

        if filter_type is not None:
            params["filter"] = filter_type

        response = await self.client.get("/api/v6/documents", params=params)

        documents = []
        for doc_data in response.get("items", []):
            try:
                # Handle thumbnail - can be dict with 'href' or None
                thumbnail_data = doc_data.get("thumbnail")
                thumbnail_url = None
                if thumbnail_data and isinstance(thumbnail_data, dict):
                    thumbnail_url = thumbnail_data.get("href")

                doc = DocumentInfo(
                    id=doc_data.get("id"),
                    name=doc_data.get("name"),
                    createdAt=doc_data.get("createdAt"),
                    modifiedAt=doc_data.get("modifiedAt"),
                    ownerId=doc_data.get("owner", {}).get("id", ""),
                    ownerName=doc_data.get("owner", {}).get("name"),
                    public=doc_data.get("public", False),
                    description=doc_data.get("description"),
                    thumbnail=thumbnail_url,
                )
                documents.append(doc)
            except Exception as e:
                # Skip documents with invalid data - but log for debugging
                import sys

                print(f"Warning: Failed to parse document: {e}", file=sys.stderr)
                continue

        return documents

    async def get_document(self, document_id: str) -> DocumentInfo:
        """Get detailed information about a specific document.

        Args:
            document_id: Document ID

        Returns:
            Document information
        """
        response = await self.client.get(f"/api/v6/documents/{document_id}")

        # Handle thumbnail - can be dict with 'href' or None
        thumbnail_data = response.get("thumbnail")
        thumbnail_url = None
        if thumbnail_data and isinstance(thumbnail_data, dict):
            thumbnail_url = thumbnail_data.get("href")

        return DocumentInfo(
            id=response.get("id"),
            name=response.get("name"),
            createdAt=response.get("createdAt"),
            modifiedAt=response.get("modifiedAt"),
            ownerId=response.get("owner", {}).get("id", ""),
            ownerName=response.get("owner", {}).get("name"),
            public=response.get("public", False),
            description=response.get("description"),
            thumbnail=thumbnail_url,
        )

    async def search_documents(
        self, query: str, limit: int = 20, document_filter: int = 0
    ) -> List[DocumentInfo]:
        """Search for documents by name or description.

        Args:
            query: Search query string
            limit: Maximum number of results
            document_filter: Filter type (0=all, 1=owned, 4=created, 5=shared)

        Returns:
            List of matching documents
        """
        params = {"q": query, "limit": limit, "documentFilter": document_filter}

        response = await self.client.get("/api/v5/globaltreenodes/search", params=params)

        documents = []
        for item in response.get("items", []):
            if item.get("resourceType") == "document":
                try:
                    # Handle thumbnail - can be dict with 'href' or None
                    thumbnail_data = item.get("thumbnail")
                    thumbnail_url = None
                    if thumbnail_data and isinstance(thumbnail_data, dict):
                        thumbnail_url = thumbnail_data.get("href")

                    doc = DocumentInfo(
                        id=item.get("id"),
                        name=item.get("name"),
                        createdAt=item.get("createdAt"),
                        modifiedAt=item.get("modifiedAt"),
                        ownerId=item.get("owner", {}).get("id", ""),
                        ownerName=item.get("owner", {}).get("name"),
                        public=item.get("public", False),
                        description=item.get("description"),
                        thumbnail=thumbnail_url,
                    )
                    documents.append(doc)
                except Exception:
                    continue

        return documents

    async def get_workspaces(self, document_id: str) -> List[WorkspaceInfo]:
        """Get all workspaces in a document.

        Args:
            document_id: Document ID

        Returns:
            List of workspace information
        """
        response = await self.client.get(f"/api/v6/documents/d/{document_id}/workspaces")

        workspaces = []
        for ws_data in response:
            workspace = WorkspaceInfo(
                id=ws_data.get("id"),
                name=ws_data.get("name"),
                isMain=ws_data.get("isMain", False),
                createdAt=ws_data.get("createdAt"),
                modifiedAt=ws_data.get("modifiedAt"),
            )
            workspaces.append(workspace)

        return workspaces

    async def get_elements(
        self, document_id: str, workspace_id: str, element_type: Optional[str] = None
    ) -> List[ElementInfo]:
        """Get all elements in a workspace.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_type: Optional filter by element type (e.g., 'PARTSTUDIO', 'ASSEMBLY')

        Returns:
            List of element information
        """
        response = await self.client.get(
            f"/api/v6/documents/d/{document_id}/w/{workspace_id}/elements"
        )

        elements = []
        for elem_data in response:
            elem_type = elem_data.get("type", "")

            # Filter by type if specified (case-insensitive, handle both "PARTSTUDIO" and "Part Studio")
            if element_type:
                # Normalize both values for comparison (remove spaces, uppercase)
                normalized_elem_type = elem_type.replace(" ", "").upper()
                normalized_filter = element_type.replace(" ", "").upper()
                if normalized_elem_type != normalized_filter:
                    continue

            element = ElementInfo(
                id=elem_data.get("id"),
                name=elem_data.get("name"),
                elementType=elem_data.get("type", "UNKNOWN"),
                dataType=elem_data.get("dataType"),
                thumbnail=elem_data.get("thumbnail"),
            )
            elements.append(element)

        return elements

    async def find_part_studios(
        self, document_id: str, workspace_id: str, name_pattern: Optional[str] = None
    ) -> List[ElementInfo]:
        """Find Part Studio elements in a workspace.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            name_pattern: Optional name pattern to filter by (case-insensitive)

        Returns:
            List of Part Studio elements
        """
        elements = await self.get_elements(document_id, workspace_id, element_type="PARTSTUDIO")

        if name_pattern:
            pattern_lower = name_pattern.lower()
            elements = [elem for elem in elements if pattern_lower in elem.name.lower()]

        return elements

    async def create_document(
        self, name: str, description: Optional[str] = None, is_public: bool = False
    ) -> DocumentInfo:
        """Create a new Onshape document.

        Args:
            name: Name for the new document
            description: Optional description
            is_public: Whether the document should be public

        Returns:
            DocumentInfo for the created document
        """
        data: Dict[str, Any] = {"name": name}
        if description is not None:
            data["description"] = description
        data["isPublic"] = is_public

        response = await self.client.post("/api/v10/documents", data=data)

        # Handle thumbnail - can be dict with 'href' or None
        thumbnail_data = response.get("thumbnail")
        thumbnail_url = None
        if thumbnail_data and isinstance(thumbnail_data, dict):
            thumbnail_url = thumbnail_data.get("href")

        return DocumentInfo(
            id=response.get("id"),
            name=response.get("name"),
            createdAt=response.get("createdAt"),
            modifiedAt=response.get("modifiedAt"),
            ownerId=response.get("owner", {}).get("id", ""),
            ownerName=response.get("owner", {}).get("name"),
            public=response.get("public", False),
            description=response.get("description"),
            thumbnail=thumbnail_url,
        )

    async def get_document_summary(self, document_id: str) -> Dict[str, Any]:
        """Get a comprehensive summary of a document including workspaces and elements.

        Args:
            document_id: Document ID

        Returns:
            Dictionary with document info, workspaces, and elements
        """
        # Get document info
        doc_info = await self.get_document(document_id)

        # Get workspaces
        workspaces = await self.get_workspaces(document_id)

        # Get elements for each workspace
        workspace_details = []
        for workspace in workspaces:
            elements = await self.get_elements(document_id, workspace.id)
            workspace_details.append({"workspace": workspace, "elements": elements})

        return {
            "document": doc_info,
            "workspaces": workspaces,
            "workspace_details": workspace_details,
        }
