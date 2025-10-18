"""Pytest configuration and shared fixtures."""

import pytest
from unittest.mock import Mock, AsyncMock
from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials


@pytest.fixture
def mock_credentials():
    """Provide mock Onshape credentials."""
    return OnshapeCredentials(
        access_key="test_access_key",
        secret_key="test_secret_key",
        base_url="https://test.onshape.com",
    )


@pytest.fixture
def mock_httpx_client():
    """Provide a mock httpx AsyncClient."""
    mock_client = AsyncMock()

    # Default success response
    mock_response = Mock()
    mock_response.json.return_value = {"success": True}
    mock_response.raise_for_status.return_value = None
    mock_response.status_code = 200  # Add status_code for POST/DELETE error logging
    mock_response.text = ""  # Add text attribute for error logging

    mock_client.get.return_value = mock_response
    mock_client.post.return_value = mock_response
    mock_client.delete.return_value = mock_response

    return mock_client


@pytest.fixture
def onshape_client(mock_credentials, mock_httpx_client, monkeypatch):
    """Provide a fully configured OnshapeClient with mocked HTTP client."""
    client = OnshapeClient(mock_credentials)
    client._client = mock_httpx_client
    return client


@pytest.fixture
def sample_document_ids():
    """Provide sample document, workspace, and element IDs."""
    return {
        "document_id": "test_doc_123",
        "workspace_id": "test_ws_456",
        "element_id": "test_elem_789",
    }


@pytest.fixture
def sample_feature_response():
    """Provide sample feature API response."""
    return {
        "featureId": "test_feature_id",
        "name": "Test Feature",
        "type": "sketch",
        "suppressed": False,
    }


@pytest.fixture
def sample_variables():
    """Provide sample variable data."""
    return [
        {"name": "width", "expression": "10 in", "description": "Width of the part"},
        {"name": "height", "expression": "5 in", "description": "Height of the part"},
    ]
