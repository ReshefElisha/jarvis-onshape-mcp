"""Drawing-based section-view renderer — STUB / WIP.

STATUS 2026-04-16: BLOCKED by Onshape platform. `render_section` raises
NotImplementedError. Onshape's public REST API does not (as of rel-1.213,
2026-04-03) support creating Section / Detail / Auxiliary views via
`/drawings/.../modify`. Only `TopLevel` and `Projected` view types are
creatable today. Docs quote:

    "Currently, only `TopLevel` and `Projected` view types are supported for
    creating and editing via the Onshape API."
    -- https://onshape-public.github.io/docs/api-adv/drawings/

Live API returns either:
    Error processing view: Unsupported view type: <name>
    View type for view creation is not supported yet

for every Section-ish viewType we tried (Section, SectionView, CrossSection,
Cross Section, Aligned Section, Detail, Auxiliary).

## What this module DOES provide (working pieces)

- `DrawingSectionManager.create_drawing(...)` — creates a temp Drawing element
  in a workspace that references a Part Studio. Returns the drawing element id.
- `DrawingSectionManager.add_toplevel_view(...)` — posts an `onshapeCreateViews`
  TopLevel parent view via `/modify`, polls `/modify/status`, returns the
  view's `logicalId` + `viewId`.
- `DrawingSectionManager.translate_drawing_to_png(...)` — starts a translation
  to PNG/JPEG, polls via the existing `ExportManager.wait_for_translation`
  pipeline, returns PNG bytes.
- `DrawingSectionManager.delete_drawing(...)` — best-effort cleanup.
- `DrawingSectionManager.render_section(...)` — THE REQUESTED METHOD. Raises
  NotImplementedError with a pointer to the research doc. Do not silently fall
  back to cut-render-delete (per Shef).

The working pieces are here so that, the day Onshape ships API section-view
support, the only change needed is to add the section-view modify payload to
`_add_section_view(...)` (currently a NotImplementedError placeholder) and
chain the existing methods.

## Reference
- Onshape docs: https://onshape-public.github.io/docs/api-adv/drawings/
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from .client import OnshapeClient
from .export import ExportManager, TranslationResult


# ---- Known-working constants (confirmed live 2026-04-16) -------------------

# messageName discriminators supported by /drawings/.../modify.
# Source: https://onshape-public.github.io/docs/api-adv/drawings/
_MSG_CREATE_VIEWS = "onshapeCreateViews"
_MSG_EDIT_VIEWS = "onshapeEditViews"
_MSG_FORMAT_VERSION = "2021-01-01"

# Supported viewTypes for CREATE. Section / Detail / Auxiliary all return
# "View type for view creation is not supported yet".
_SUPPORTED_VIEW_TYPES = frozenset({"TopLevel", "Projected"})

# Valid orientation strings for TopLevel views (per docs + live probe).
_TOPLEVEL_ORIENTATIONS = frozenset({
    "front", "back", "top", "bottom", "left", "right",
    "isometric", "dimetric", "trimetric",
})

# Reasonable polling defaults for the /modify async pipeline.
_MODIFY_POLL_INTERVAL = 0.5  # seconds
_MODIFY_TIMEOUT = 60.0  # seconds


# ---- Result types ---------------------------------------------------------


@dataclass
class DrawingViewResult:
    """Outcome of an onshapeCreateViews modify call for a single view."""
    logical_id: str          # e.g. "h:100000FB" — used as parentView.logicalId
    view_id: str             # internal view id on the drawing
    status: str              # "OK" or "Failed"
    error_message: Optional[str] = None


@dataclass
class DrawingModifyResult:
    """Result of polling a /drawings/.../modify request to completion."""
    ok: bool
    request_id: str
    request_state: str       # "DONE" | "FAILED" | "ACTIVE" (on timeout)
    output_status_code: int
    results: List[DrawingViewResult]
    raw: Dict[str, Any]


# ---- Manager --------------------------------------------------------------


class DrawingSectionManager:
    """Orchestrates drawing creation, view creation, and PNG export.

    NOT FULLY IMPLEMENTED — `render_section` is the target deliverable and is
    blocked by an Onshape platform gap (see module docstring). The class still
    provides the four working primitives so callers / future maintainers have a
    tested base to build on.
    """

    def __init__(
        self,
        client: OnshapeClient,
        *,
        exporter: Optional[ExportManager] = None,
    ):
        self.client = client
        self.exporter = exporter or ExportManager(client)

    # ---- Drawing element lifecycle ---------------------------------------

    async def create_drawing(
        self,
        document_id: str,
        workspace_id: str,
        *,
        drawing_name: str,
        part_studio_element_id: str,
    ) -> str:
        """POST /drawings/d/{did}/w/{wid}/create — make a new Drawing element.

        Returns the new drawing element id. Confirmed live 2026-04-16.
        """
        path = f"/api/v9/drawings/d/{document_id}/w/{workspace_id}/create"
        body = {
            "drawingName": drawing_name,
            "elementId": part_studio_element_id,
        }
        resp = await self.client.post(path, data=body)
        drawing_eid = resp.get("id")
        if not drawing_eid:
            raise RuntimeError(
                f"drawing create returned no element id: {resp!r}"
            )
        return drawing_eid

    async def delete_drawing(
        self,
        document_id: str,
        workspace_id: str,
        drawing_element_id: str,
    ) -> None:
        """Best-effort delete of a drawing element. Swallows errors since
        callers should not lose the primary result (bytes) to a cleanup
        failure — they get logged instead."""
        path = (
            f"/api/v9/elements/d/{document_id}/w/{workspace_id}"
            f"/e/{drawing_element_id}"
        )
        try:
            await self.client.delete(path)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"delete_drawing({drawing_element_id}) failed: {e}")

    # ---- Modify + poll ---------------------------------------------------

    async def _post_modify(
        self,
        document_id: str,
        workspace_id: str,
        drawing_element_id: str,
        *,
        description: str,
        json_requests: List[Dict[str, Any]],
    ) -> str:
        """Start a /modify request. Returns the modify request id."""
        path = (
            f"/api/v9/drawings/d/{document_id}/w/{workspace_id}"
            f"/e/{drawing_element_id}/modify"
        )
        body = {"description": description, "jsonRequests": json_requests}
        resp = await self.client.post(path, data=body)
        mrid = resp.get("id")
        if not mrid:
            raise RuntimeError(f"/modify returned no request id: {resp!r}")
        return mrid

    async def _poll_modify(
        self,
        modify_request_id: str,
        *,
        timeout: float = _MODIFY_TIMEOUT,
        interval: float = _MODIFY_POLL_INTERVAL,
    ) -> DrawingModifyResult:
        """Poll `/drawings/modify/status/{mrid}` until DONE or FAILED.

        Response `output` is a JSON STRING (not an object), of shape
        `{"status": "OK|Failed", "statusCode": "200", "results": [{...}]}`.
        Each result in `results` has `logicalId` + `viewId` on success, or
        an `errorDescription` on failure.
        """
        path = f"/api/v6/drawings/modify/status/{modify_request_id}"
        deadline = asyncio.get_event_loop().time() + timeout
        last: Dict[str, Any] = {}
        while True:
            last = await self.client.get(path)
            state = last.get("requestState", "UNKNOWN")
            if state in ("DONE", "FAILED"):
                break
            if asyncio.get_event_loop().time() >= deadline:
                return DrawingModifyResult(
                    ok=False,
                    request_id=modify_request_id,
                    request_state=state,
                    output_status_code=0,
                    results=[],
                    raw=last,
                )
            await asyncio.sleep(interval)

        output_raw = last.get("output") or "{}"
        try:
            output = json.loads(output_raw) if isinstance(output_raw, str) else output_raw
        except json.JSONDecodeError:
            output = {}

        results: List[DrawingViewResult] = []
        for r in output.get("results") or []:
            results.append(
                DrawingViewResult(
                    logical_id=r.get("logicalId", ""),
                    view_id=r.get("viewId", ""),
                    status=r.get("status", ""),
                    error_message=r.get("errorDescription"),
                )
            )
        ok = (
            last.get("requestState") == "DONE"
            and output.get("status") == "OK"
        )
        return DrawingModifyResult(
            ok=ok,
            request_id=modify_request_id,
            request_state=last.get("requestState", "UNKNOWN"),
            output_status_code=int(last.get("outputStatusCode") or 0),
            results=results,
            raw=last,
        )

    # ---- Parent view creation (WORKING) ----------------------------------

    async def add_toplevel_view(
        self,
        document_id: str,
        workspace_id: str,
        drawing_element_id: str,
        *,
        part_studio_element_id: str,
        part_id: str,
        orientation: str = "front",
        position: Tuple[float, float] = (5.0, 5.0),
        scale_numerator: float = 1.0,
        scale_denominator: float = 1.0,
    ) -> DrawingViewResult:
        """Create a TopLevel parent view (Front/Top/Right/etc.) of a Part
        Studio. Confirmed live 2026-04-16.

        Returns the view's logicalId + viewId. The logicalId is the string
        another jsonRequest would use as `parentView.logicalId` once Onshape
        supports creating child section views (not today).
        """
        if orientation not in _TOPLEVEL_ORIENTATIONS:
            raise ValueError(
                f"orientation {orientation!r} not in {sorted(_TOPLEVEL_ORIENTATIONS)}"
            )
        view_obj = {
            "viewType": "TopLevel",
            "position": {"x": position[0], "y": position[1]},
            "scale": {
                "scaleSource": "Custom",
                "numerator": scale_numerator,
                "denumerator": scale_denominator,
            },
            "orientation": orientation,
            "reference": {
                "elementId": part_studio_element_id,
                "idTag": part_id,
            },
        }
        json_requests = [
            {
                "messageName": _MSG_CREATE_VIEWS,
                "formatVersion": _MSG_FORMAT_VERSION,
                "views": [view_obj],
            }
        ]
        mrid = await self._post_modify(
            document_id, workspace_id, drawing_element_id,
            description=f"Add {orientation} view",
            json_requests=json_requests,
        )
        result = await self._poll_modify(mrid)
        if not result.ok or not result.results:
            err = (
                result.results[0].error_message
                if result.results
                else f"modify request ended in state {result.request_state}"
            )
            raise RuntimeError(
                f"TopLevel view creation failed: {err} "
                f"(request_id={result.request_id})"
            )
        return result.results[0]

    # ---- Section view creation (BLOCKED — placeholder) -------------------

    async def _add_section_view(
        self,
        document_id: str,
        workspace_id: str,
        drawing_element_id: str,
        *,
        parent_view_logical_id: str,
        plane_origin: Tuple[float, float, float],
        plane_normal: Tuple[float, float, float],
        position: Tuple[float, float] = (11.0, 5.0),
    ) -> DrawingViewResult:
        """PLACEHOLDER — Onshape does not support this via public API today.

        When/if server support lands, the payload we'd send is (best guess
        based on the /views GET shape we observe on real documents):

            {
                "viewType": "Section",              # not accepted 2026-04-16
                "position": {"x": X, "y": Y},
                "parentView": {"logicalId": "<parent>"},
                "cuttingPlane": {
                    "origin": {"x": ox, "y": oy, "z": oz},
                    "normal": {"x": nx, "y": ny, "z": nz},
                },
                ...
            }

        See scratchpad/drawing-section-research.md for every variant tried
        and the exact server rejection each one produced.
        """
        raise NotImplementedError(
            "Onshape public REST API does not support section-view creation "
            "via /drawings/.../modify. Server returns "
            "\"View type for view creation is not supported yet\" for every "
            "Section/Detail/Auxiliary variant tested. See "
            "scratchpad/drawing-section-research.md for the full trail. "
            "Only TopLevel and Projected view types are creatable today."
        )

    # ---- PNG translation (WORKING building block) ------------------------

    async def translate_drawing_to_png(
        self,
        document_id: str,
        workspace_id: str,
        drawing_element_id: str,
        *,
        format_name: str = "PNG",
        timeout_seconds: float = 120.0,
        poll_interval_seconds: float = 1.0,
    ) -> TranslationResult:
        """Start a drawing translation (PNG / JPEG / PDF / etc.), poll to
        DONE, and download bytes via the existing ExportManager pipeline.

        Confirmed live 2026-04-16 that PNG + JPEG are in the
        /translationformats list. The translation start + poll + external-
        data download pipeline is the same shape as part-studio exports, so
        ExportManager.wait_for_translation is reused directly.
        """
        fmt = format_name.upper()
        path = (
            f"/api/v9/drawings/d/{document_id}/w/{workspace_id}"
            f"/e/{drawing_element_id}/translations"
        )
        start = await self.client.post(
            path, data={"formatName": fmt, "storeInDocument": False}
        )
        translation_id = start.get("id")
        if not translation_id:
            from .export import TranslationResult as _TR  # local alias
            return _TR(
                ok=False,
                state=start.get("requestState", "UNKNOWN"),
                translation_id="",
                format_name=fmt,
                error_message=(
                    f"drawing translation start returned no id; keys={list(start.keys())}"
                ),
                raw=start,
            )
        return await self.exporter.wait_for_translation(
            translation_id,
            source_document_id=document_id,
            format_name=fmt,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )

    # ---- The headline method — CURRENTLY BLOCKED -------------------------

    async def render_section(
        self,
        document_id: str,
        workspace_id: str,
        part_studio_element_id: str,
        *,
        plane_origin: Tuple[float, float, float],
        plane_normal: Tuple[float, float, float],
        base_view: str = "front",
        width: int = 1200,
        height: int = 800,
        sheet_size: str = "A",
    ) -> bytes:
        """NOT IMPLEMENTED — blocked by Onshape platform.

        Intended behavior (spec from Shef, 2026-04-16):
            1. Create a temp drawing element referencing the Part Studio.
            2. Add a `base_view` TopLevel parent view.
            3. Add a Section view referencing that parent + the cutting plane.
            4. Translate the drawing to PNG; return bytes.
            5. Delete the drawing element.

        Step 3 is impossible today. The public API only accepts `TopLevel`
        and `Projected` viewTypes; every Section variant is rejected
        server-side with the message:

            "View type for view creation is not supported yet"

        Do NOT silently fall back to the cut-render-delete FS path (that's
        what `onshape_mcp/api/section_view.py` already does — Shef
        explicitly said no to a quiet fallback here).

        See scratchpad/drawing-section-research.md for:
          - three independent confirmations of the platform gap,
          - the full list of viewType strings tested + exact server errors,
          - the probe doc id left for inspection,
          - the downstream options (keep FS path, wait for Onshape, etc.).
        """
        raise NotImplementedError(
            "render_section is not implementable via the Onshape public REST "
            "API today. The /drawings/.../modify endpoint only supports "
            "TopLevel and Projected view types (confirmed by docs + live "
            "probe on 2026-04-16). Section view creation returns "
            "\"View type for view creation is not supported yet\". See "
            "scratchpad/drawing-section-research.md for the full research "
            "trail. The working scaffolding (create_drawing, "
            "add_toplevel_view, translate_drawing_to_png) is present on this "
            "manager and will let this method go live the day Onshape ships "
            "server-side support — only _add_section_view needs a body."
        )
