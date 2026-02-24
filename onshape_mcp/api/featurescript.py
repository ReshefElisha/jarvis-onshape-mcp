"""FeatureScript evaluation for Onshape."""
from typing import Any, Dict
from .client import OnshapeClient


class FeatureScriptManager:
    """Manager for evaluating FeatureScript expressions in Onshape."""

    def __init__(self, client: OnshapeClient):
        self.client = client

    async def evaluate(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        script: str,
    ) -> Dict[str, Any]:
        """Evaluate a FeatureScript expression in a Part Studio.

        Only lambda expressions can be evaluated. This is read-only and
        cannot alter the model.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Part Studio element ID
            script: FeatureScript expression to evaluate

        Returns:
            Evaluation result
        """
        path = (
            f"/api/v8/partstudios/d/{document_id}/w/{workspace_id}"
            f"/e/{element_id}/featurescript"
        )
        data = {
            "script": script,
        }
        return await self.client.post(path, params={"rollbackBarIndex": -1}, data=data)

    async def get_bounding_box(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
    ) -> Dict[str, Any]:
        """Get tight bounding box for all parts in a Part Studio using FeatureScript.

        Returns bounding box with min/max coordinates in meters.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Part Studio element ID

        Returns:
            Bounding box data with minCorner and maxCorner
        """
        script = """
function(context is Context, queries) {
    var allParts = qAllModifiableSolidBodies();
    var bbox = evBox3d(context, {"topology": allParts});
    return bbox;
}"""
        return await self.evaluate(document_id, workspace_id, element_id, script.strip())
