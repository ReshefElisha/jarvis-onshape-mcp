"""Unit tests for Export manager."""

import pytest
from unittest.mock import AsyncMock, patch

from onshape_mcp.api.export import ExportManager, TranslationResult


class TestExportManager:
    """Test ExportManager operations."""

    @pytest.fixture
    def export_manager(self, onshape_client):
        """Provide an ExportManager instance."""
        return ExportManager(onshape_client)

    @pytest.mark.asyncio
    async def test_export_part_studio_stl(
        self, export_manager, onshape_client, sample_document_ids
    ):
        """Test exporting a Part Studio to STL format."""
        expected_response = {
            "id": "translation_123",
            "requestState": "ACTIVE",
        }

        onshape_client.post = AsyncMock(return_value=expected_response)

        result = await export_manager.export_part_studio(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            format_name="STL",
        )

        assert result == expected_response
        onshape_client.post.assert_called_once()

        call_args = onshape_client.post.call_args
        body = call_args[1]["data"]
        assert body["formatName"] == "STL"

        path = call_args[0][0]
        assert sample_document_ids["document_id"] in path
        assert sample_document_ids["workspace_id"] in path
        assert sample_document_ids["element_id"] in path

    @pytest.mark.asyncio
    async def test_export_part_studio_with_part_id(
        self, export_manager, onshape_client, sample_document_ids
    ):
        """Test exporting a specific part by part ID."""
        part_id = "JHD"
        expected_response = {"id": "translation_456", "requestState": "ACTIVE"}

        onshape_client.post = AsyncMock(return_value=expected_response)

        result = await export_manager.export_part_studio(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            format_name="STEP",
            part_id=part_id,
        )

        assert result == expected_response
        onshape_client.post.assert_called_once()

        call_args = onshape_client.post.call_args
        body = call_args[1]["data"]
        assert body["partId"] == part_id
        assert body["formatName"] == "STEP"

    @pytest.mark.asyncio
    async def test_export_assembly_success(
        self, export_manager, onshape_client, sample_document_ids
    ):
        """Test exporting an assembly POSTs to the assemblies path."""
        expected_response = {"id": "translation_789", "requestState": "ACTIVE"}

        onshape_client.post = AsyncMock(return_value=expected_response)

        result = await export_manager.export_assembly(
            sample_document_ids["document_id"],
            sample_document_ids["workspace_id"],
            sample_document_ids["element_id"],
            format_name="STL",
        )

        assert result == expected_response
        onshape_client.post.assert_called_once()

        call_args = onshape_client.post.call_args
        path = call_args[0][0]
        assert "assemblies" in path
        assert sample_document_ids["document_id"] in path
        assert sample_document_ids["workspace_id"] in path
        assert sample_document_ids["element_id"] in path

        body = call_args[1]["data"]
        assert body["formatName"] == "STL"

    @pytest.mark.asyncio
    async def test_get_translation_status(
        self, export_manager, onshape_client
    ):
        """Test checking the status of a translation by ID."""
        translation_id = "trans_id_abc123"
        expected_response = {
            "id": translation_id,
            "requestState": "DONE",
            "resultExternalDataIds": ["file_data_id_xyz"],
        }

        onshape_client.get = AsyncMock(return_value=expected_response)

        result = await export_manager.get_translation_status(translation_id)

        assert result == expected_response
        onshape_client.get.assert_called_once()

        call_args = onshape_client.get.call_args
        path = call_args[0][0]
        assert translation_id in path


class TestTranslationPipeline:
    """Tests for the poll-and-download translation pipeline."""

    @pytest.fixture
    def export_manager(self, onshape_client):
        return ExportManager(onshape_client)

    @pytest.mark.asyncio
    async def test_download_external_data_hits_correct_path(
        self, export_manager, onshape_client
    ):
        """download_external_data should call the documents/externaldata path."""
        onshape_client.get_raw = AsyncMock(return_value=b"ISO-10303-21;\nHEADER;")

        data = await export_manager.download_external_data(
            document_id="docABC", external_data_id="fid123"
        )

        assert data.startswith(b"ISO-10303-21")
        path = onshape_client.get_raw.call_args[0][0]
        assert "/documents/d/docABC/externaldata/fid123" in path

    @pytest.mark.asyncio
    async def test_wait_for_translation_polls_until_done_then_downloads(
        self, export_manager, onshape_client
    ):
        """Poll ACTIVE -> ACTIVE -> DONE, then download bytes for the result."""
        responses = [
            {"id": "t1", "requestState": "ACTIVE"},
            {"id": "t1", "requestState": "ACTIVE"},
            {
                "id": "t1",
                "requestState": "DONE",
                "resultExternalDataIds": ["ext1"],
                "resultDocumentId": "docABC",
            },
        ]
        onshape_client.get = AsyncMock(side_effect=responses)
        onshape_client.get_raw = AsyncMock(return_value=b"ISO-10303-21;\nHEADER;\nENDSEC;")

        # Patch asyncio.sleep so the test doesn't actually wait.
        with patch("onshape_mcp.api.export.asyncio.sleep", new=AsyncMock()):
            result = await export_manager.wait_for_translation(
                translation_id="t1",
                source_document_id="docSRC",
                format_name="STEP",
                timeout_seconds=30.0,
                poll_interval_seconds=0.01,
            )

        assert isinstance(result, TranslationResult)
        assert result.ok is True
        assert result.state == "DONE"
        assert result.format_name == "STEP"
        assert result.data is not None and result.data.startswith(b"ISO-10303-21")
        assert result.filename and result.filename.endswith(".step")
        # Polled three times and downloaded once.
        assert onshape_client.get.await_count == 3
        assert onshape_client.get_raw.await_count == 1
        # Downloaded from the result document id (not the source).
        raw_path = onshape_client.get_raw.call_args[0][0]
        assert "/documents/d/docABC/externaldata/ext1" in raw_path

    @pytest.mark.asyncio
    async def test_wait_for_translation_falls_back_to_source_doc_id(
        self, export_manager, onshape_client
    ):
        """When resultDocumentId is absent, download from the source document."""
        onshape_client.get = AsyncMock(
            return_value={
                "id": "t1",
                "requestState": "DONE",
                "resultExternalDataIds": ["ext1"],
                # resultDocumentId intentionally missing
            }
        )
        onshape_client.get_raw = AsyncMock(return_value=b"solid\n")

        result = await export_manager.wait_for_translation(
            translation_id="t1",
            source_document_id="docSRC",
            format_name="STL",
        )

        assert result.ok is True
        raw_path = onshape_client.get_raw.call_args[0][0]
        assert "/documents/d/docSRC/externaldata/ext1" in raw_path

    @pytest.mark.asyncio
    async def test_wait_for_translation_reports_failed_state(
        self, export_manager, onshape_client
    ):
        """FAILED state should short-circuit with an error message."""
        onshape_client.get = AsyncMock(
            return_value={
                "id": "t1",
                "requestState": "FAILED",
                "failureReason": "Tessellation failed",
            }
        )
        onshape_client.get_raw = AsyncMock()

        result = await export_manager.wait_for_translation(
            translation_id="t1",
            source_document_id="docSRC",
            format_name="STEP",
        )

        assert result.ok is False
        assert result.state == "FAILED"
        assert result.data is None
        assert "Tessellation failed" in (result.error_message or "")
        # Never downloaded anything on FAILED.
        onshape_client.get_raw.assert_not_called()

    @pytest.mark.asyncio
    async def test_wait_for_translation_times_out(
        self, export_manager, onshape_client, monkeypatch
    ):
        """Return ok=False with last state if timeout expires before DONE."""
        onshape_client.get = AsyncMock(
            return_value={"id": "t1", "requestState": "ACTIVE"}
        )

        # Drive the deadline clock: start=0, next tick past the 1.0s budget.
        times = iter([0.0, 2.0, 2.0, 2.0])

        class FakeLoop:
            def time(self):
                return next(times)

        monkeypatch.setattr(
            "onshape_mcp.api.export.asyncio.get_event_loop",
            lambda: FakeLoop(),
        )
        monkeypatch.setattr(
            "onshape_mcp.api.export.asyncio.sleep", AsyncMock()
        )

        result = await export_manager.wait_for_translation(
            translation_id="t1",
            source_document_id="docSRC",
            format_name="STEP",
            timeout_seconds=1.0,
            poll_interval_seconds=0.01,
        )

        assert result.ok is False
        assert result.state == "ACTIVE"
        assert result.data is None
        assert "did not complete" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_wait_for_translation_done_but_no_external_data(
        self, export_manager, onshape_client
    ):
        """DONE with no resultExternalDataIds should surface a clear error."""
        onshape_client.get = AsyncMock(
            return_value={
                "id": "t1",
                "requestState": "DONE",
                "resultExternalDataIds": [],
            }
        )
        onshape_client.get_raw = AsyncMock()

        result = await export_manager.wait_for_translation(
            translation_id="t1",
            source_document_id="docSRC",
            format_name="STEP",
        )

        assert result.ok is False
        assert result.state == "DONE"
        assert "no resultExternalDataIds" in (result.error_message or "")
        onshape_client.get_raw.assert_not_called()

    @pytest.mark.asyncio
    async def test_export_part_studio_and_download_wires_through(
        self, export_manager, onshape_client
    ):
        """export_part_studio_and_download: start + wait + download."""
        onshape_client.post = AsyncMock(
            return_value={"id": "t42", "requestState": "ACTIVE"}
        )
        onshape_client.get = AsyncMock(
            return_value={
                "id": "t42",
                "requestState": "DONE",
                "resultExternalDataIds": ["ext42"],
                "resultDocumentId": "docX",
            }
        )
        onshape_client.get_raw = AsyncMock(return_value=b"ISO-10303-21;")

        result = await export_manager.export_part_studio_and_download(
            document_id="docSRC",
            workspace_id="wsSRC",
            element_id="elSRC",
            format_name="step",
            poll_interval_seconds=0.01,
        )

        assert result.ok is True
        assert result.translation_id == "t42"
        assert result.format_name == "STEP"

    @pytest.mark.asyncio
    async def test_export_assembly_and_download_wires_through(
        self, export_manager, onshape_client
    ):
        onshape_client.post = AsyncMock(
            return_value={"id": "tA", "requestState": "ACTIVE"}
        )
        onshape_client.get = AsyncMock(
            return_value={
                "id": "tA",
                "requestState": "DONE",
                "resultExternalDataIds": ["extA"],
            }
        )
        onshape_client.get_raw = AsyncMock(return_value=b"solid\n")

        result = await export_manager.export_assembly_and_download(
            document_id="docSRC",
            workspace_id="wsSRC",
            element_id="elSRC",
            format_name="STL",
            poll_interval_seconds=0.01,
        )

        assert result.ok is True
        assert result.format_name == "STL"
        assert result.data == b"solid\n"
        # Assembly path was hit (not part studio).
        post_path = onshape_client.post.call_args[0][0]
        assert "/assemblies/" in post_path

    @pytest.mark.asyncio
    async def test_export_start_without_translation_id(
        self, export_manager, onshape_client
    ):
        """If Onshape doesn't return a translation id, return an error result."""
        onshape_client.post = AsyncMock(return_value={"requestState": "UNKNOWN"})

        result = await export_manager.export_part_studio_and_download(
            document_id="docSRC",
            workspace_id="wsSRC",
            element_id="elSRC",
            format_name="STEP",
        )

        assert result.ok is False
        assert result.translation_id == ""
        assert "did not return a translation id" in (result.error_message or "")
