"""Export and translation management for Onshape."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger

from .client import OnshapeClient


# File extensions by Onshape format name. Used when the translation response
# does not include a result filename.
FORMAT_EXTENSIONS = {
    "STL": "stl",
    "STEP": "step",
    "PARASOLID": "x_t",
    "GLTF": "gltf",
    "OBJ": "obj",
    "IGES": "igs",
    "ACIS": "sat",
    "SOLIDWORKS": "sldprt",
    "COLLADA": "dae",
    "JT": "jt",
    "3MF": "3mf",
    "DWG": "dwg",
    "DXF": "dxf",
    "PDF": "pdf",
}


@dataclass
class TranslationResult:
    """Result of polling a translation job to completion and downloading bytes.

    Attributes:
        ok: True only if the translation reached DONE and bytes were downloaded.
        state: Final Onshape request state ("DONE", "FAILED", or the last seen
            state if the caller timed out, e.g. "ACTIVE").
        translation_id: The translation ID that was polled.
        format_name: Uppercase format name passed to the export (e.g., "STEP").
        data: Raw bytes of the exported file. None on failure/timeout.
        filename: A reasonable filename for the payload (format-based extension
            if Onshape did not return one). None on failure/timeout.
        error_message: Human-readable error explanation on failure/timeout.
        raw: The final /translations/{id} response, preserved for debugging.
    """

    ok: bool
    state: str
    translation_id: str
    format_name: str
    data: Optional[bytes] = None
    filename: Optional[str] = None
    error_message: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


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
        """Start a Part Studio translation in a specified format.

        Uses the v11 direct translation endpoint. This only *starts* the job;
        use `wait_for_translation` or `export_part_studio_and_download` to get
        the actual bytes.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Part Studio element ID
            format_name: Export format (STL, STEP, PARASOLID, GLTF, OBJ)
            part_id: Optional specific part ID to export

        Returns:
            Raw translation start response (contains `id` and `requestState`).
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
        """Start an Assembly translation in a specified format.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Assembly element ID
            format_name: Export format (STL, STEP, GLTF)

        Returns:
            Raw translation start response (contains `id` and `requestState`).
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
            Translation status with state, result doc id, and result external
            data IDs (once DONE).
        """
        path = f"/api/v6/translations/{translation_id}"
        return await self.client.get(path)

    async def download_external_data(
        self,
        document_id: str,
        external_data_id: str,
    ) -> bytes:
        """Download external data bytes attached to a document.

        Translation results with `storeInDocument=False` land as external data
        on the source document, fetched via this endpoint.

        Args:
            document_id: Document that owns the external data (usually the
                `resultDocumentId` from the finished translation, which equals
                the source document when the translation did not fork).
            external_data_id: One of the IDs in
                `resultExternalDataIds` on a DONE translation.

        Returns:
            Raw file bytes.
        """
        path = (
            f"/api/v6/documents/d/{document_id}/externaldata/{external_data_id}"
        )
        return await self.client.get_raw(path)

    async def wait_for_translation(
        self,
        translation_id: str,
        source_document_id: str,
        format_name: str,
        timeout_seconds: float = 120.0,
        poll_interval_seconds: float = 1.0,
    ) -> TranslationResult:
        """Poll a translation to completion, then download the resulting bytes.

        Polls `GET /api/v6/translations/{id}` at `poll_interval_seconds` until
        `requestState` is DONE or FAILED, or `timeout_seconds` elapses. On DONE
        with external-data results, downloads the first external data payload
        and returns it.

        Args:
            translation_id: Translation ID returned from `export_*`.
            source_document_id: Document the export originated from. Used as a
                fallback when the translation response omits `resultDocumentId`.
            format_name: Format name (uppercase) used for the export. Used to
                pick a filename extension when Onshape does not return one.
            timeout_seconds: Give up after this many seconds of polling.
            poll_interval_seconds: Seconds between poll requests.

        Returns:
            `TranslationResult` — `ok=True` only when the translation reached
            DONE and bytes were successfully downloaded.
        """
        fmt = format_name.upper()
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        status: Dict[str, Any] = {}
        state = "UNKNOWN"

        while True:
            status = await self.get_translation_status(translation_id)
            state = status.get("requestState", "UNKNOWN")

            if state == "DONE":
                break
            if state == "FAILED":
                return TranslationResult(
                    ok=False,
                    state=state,
                    translation_id=translation_id,
                    format_name=fmt,
                    error_message=(
                        status.get("failureReason")
                        or "Onshape reported translation FAILED with no reason"
                    ),
                    raw=status,
                )

            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return TranslationResult(
                    ok=False,
                    state=state,
                    translation_id=translation_id,
                    format_name=fmt,
                    error_message=(
                        f"Translation did not complete within {timeout_seconds:.0f}s "
                        f"(last state: {state})"
                    ),
                    raw=status,
                )
            await asyncio.sleep(min(poll_interval_seconds, remaining))

        external_ids: List[str] = list(status.get("resultExternalDataIds") or [])
        if not external_ids:
            return TranslationResult(
                ok=False,
                state=state,
                translation_id=translation_id,
                format_name=fmt,
                error_message=(
                    "Translation DONE but response had no resultExternalDataIds. "
                    "Export may have been stored in the document instead."
                ),
                raw=status,
            )

        result_doc_id = status.get("resultDocumentId") or source_document_id
        external_id = external_ids[0]

        try:
            data = await self.download_external_data(result_doc_id, external_id)
        except Exception as e:  # noqa: BLE001
            logger.exception("External data download failed")
            return TranslationResult(
                ok=False,
                state=state,
                translation_id=translation_id,
                format_name=fmt,
                error_message=f"Download of external data failed: {e}",
                raw=status,
            )

        filename = (
            status.get("resultFilename")
            or status.get("name")
            or f"{translation_id}.{FORMAT_EXTENSIONS.get(fmt, fmt.lower())}"
        )

        return TranslationResult(
            ok=True,
            state=state,
            translation_id=translation_id,
            format_name=fmt,
            data=data,
            filename=filename,
            raw=status,
        )

    async def export_part_studio_and_download(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        format_name: str = "STL",
        part_id: Optional[str] = None,
        timeout_seconds: float = 120.0,
        poll_interval_seconds: float = 1.0,
    ) -> TranslationResult:
        """Start a Part Studio export, poll to DONE, and download the bytes.

        Args:
            document_id: Document ID
            workspace_id: Workspace ID
            element_id: Part Studio element ID
            format_name: Export format
            part_id: Optional specific part ID
            timeout_seconds: Polling budget
            poll_interval_seconds: Poll cadence

        Returns:
            TranslationResult with either bytes or an error.
        """
        start = await self.export_part_studio(
            document_id, workspace_id, element_id, format_name, part_id
        )
        translation_id = start.get("id")
        if not translation_id:
            return TranslationResult(
                ok=False,
                state=start.get("requestState", "UNKNOWN"),
                translation_id="",
                format_name=format_name.upper(),
                error_message=(
                    "Onshape did not return a translation id from export start; "
                    f"response keys: {list(start.keys())}"
                ),
                raw=start,
            )
        return await self.wait_for_translation(
            translation_id,
            source_document_id=document_id,
            format_name=format_name,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )

    async def export_assembly_and_download(
        self,
        document_id: str,
        workspace_id: str,
        element_id: str,
        format_name: str = "STL",
        timeout_seconds: float = 120.0,
        poll_interval_seconds: float = 1.0,
    ) -> TranslationResult:
        """Start an Assembly export, poll to DONE, and download the bytes."""
        start = await self.export_assembly(
            document_id, workspace_id, element_id, format_name
        )
        translation_id = start.get("id")
        if not translation_id:
            return TranslationResult(
                ok=False,
                state=start.get("requestState", "UNKNOWN"),
                translation_id="",
                format_name=format_name.upper(),
                error_message=(
                    "Onshape did not return a translation id from export start; "
                    f"response keys: {list(start.keys())}"
                ),
                raw=start,
            )
        return await self.wait_for_translation(
            translation_id,
            source_document_id=document_id,
            format_name=format_name,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
