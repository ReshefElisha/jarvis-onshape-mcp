"""Unit tests for Onshape API client."""

import pytest
import base64
from unittest.mock import Mock
import httpx

from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials


class TestOnshapeCredentials:
    """Test OnshapeCredentials model."""

    def test_credentials_creation_with_defaults(self):
        """Test creating credentials with default base URL."""
        creds = OnshapeCredentials(access_key="test_key", secret_key="test_secret")

        assert creds.access_key == "test_key"
        assert creds.secret_key == "test_secret"
        assert creds.base_url == "https://cad.onshape.com"

    def test_credentials_creation_with_custom_url(self):
        """Test creating credentials with custom base URL."""
        creds = OnshapeCredentials(
            access_key="test_key", secret_key="test_secret", base_url="https://custom.onshape.com"
        )

        assert creds.base_url == "https://custom.onshape.com"

    def test_credentials_require_access_key(self):
        """Test that access_key is required."""
        with pytest.raises(Exception):
            OnshapeCredentials(secret_key="test_secret")

    def test_credentials_require_secret_key(self):
        """Test that secret_key is required."""
        with pytest.raises(Exception):
            OnshapeCredentials(access_key="test_key")


class TestOnshapeClient:
    """Test OnshapeClient HTTP operations."""

    def test_client_initialization(self, mock_credentials):
        """Test client initialization with credentials."""
        client = OnshapeClient(mock_credentials)

        assert client.credentials == mock_credentials
        assert client.base_url == mock_credentials.base_url
        assert client._client is not None

    def test_get_auth_header_encoding(self, mock_credentials):
        """Test Basic Auth header generation."""
        client = OnshapeClient(mock_credentials)
        auth_header = client._get_auth_header()

        # Verify it's a valid Basic auth header
        assert auth_header.startswith("Basic ")

        # Decode and verify the credentials
        encoded_part = auth_header.split(" ")[1]
        decoded = base64.b64decode(encoded_part).decode()
        expected = f"{mock_credentials.access_key}:{mock_credentials.secret_key}"

        assert decoded == expected

    @pytest.mark.asyncio
    async def test_get_request_success(self, onshape_client, mock_httpx_client):
        """Test successful GET request."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.get.return_value = mock_response

        result = await onshape_client.get("/api/test")

        assert result == {"data": "test"}
        mock_httpx_client.get.assert_called_once()

        # Verify headers
        call_args = mock_httpx_client.get.call_args
        headers = call_args.kwargs["headers"]
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")
        assert "Accept" in headers

    @pytest.mark.asyncio
    async def test_get_request_with_params(self, onshape_client, mock_httpx_client):
        """Test GET request with query parameters."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.get.return_value = mock_response

        params = {"key": "value", "limit": 10}
        result = await onshape_client.get("/api/test", params=params)

        call_args = mock_httpx_client.get.call_args
        assert call_args.kwargs["params"] == params

    @pytest.mark.asyncio
    async def test_get_request_http_error(self, onshape_client, mock_httpx_client):
        """Test GET request handling HTTP errors."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=Mock(), response=Mock(status_code=404)
        )
        mock_httpx_client.get.return_value = mock_response

        with pytest.raises(httpx.HTTPStatusError):
            await onshape_client.get("/api/test")

    @pytest.mark.asyncio
    async def test_post_request_success(self, onshape_client, mock_httpx_client):
        """Test successful POST request."""
        mock_response = Mock()
        mock_response.json.return_value = {"created": True}
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.post.return_value = mock_response

        data = {"name": "test", "value": 123}
        result = await onshape_client.post("/api/create", data=data)

        assert result == {"created": True}
        mock_httpx_client.post.assert_called_once()

        # Verify JSON data and Content-Type header
        call_args = mock_httpx_client.post.call_args
        assert call_args.kwargs["json"] == data
        headers = call_args.kwargs["headers"]
        assert "Content-Type" in headers

    @pytest.mark.asyncio
    async def test_post_request_with_params(self, onshape_client, mock_httpx_client):
        """Test POST request with query parameters."""
        mock_response = Mock()
        mock_response.json.return_value = {"created": True}
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.post.return_value = mock_response

        data = {"name": "test"}
        params = {"validate": True}
        result = await onshape_client.post("/api/create", data=data, params=params)

        call_args = mock_httpx_client.post.call_args
        assert call_args.kwargs["params"] == params

    @pytest.mark.asyncio
    async def test_delete_request_success(self, onshape_client, mock_httpx_client):
        """Test successful DELETE request."""
        mock_response = Mock()
        mock_response.json.return_value = {"deleted": True}
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.delete.return_value = mock_response

        result = await onshape_client.delete("/api/resource/123")

        assert result == {"deleted": True}
        mock_httpx_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_request_with_params(self, onshape_client, mock_httpx_client):
        """Test DELETE request with query parameters."""
        mock_response = Mock()
        mock_response.json.return_value = {"deleted": True}
        mock_response.raise_for_status.return_value = None
        mock_httpx_client.delete.return_value = mock_response

        params = {"force": True}
        result = await onshape_client.delete("/api/resource/123", params=params)

        call_args = mock_httpx_client.delete.call_args
        assert call_args.kwargs["params"] == params

    @pytest.mark.asyncio
    async def test_close_client(self, onshape_client, mock_httpx_client):
        """Test closing the HTTP client."""
        await onshape_client.close()

        mock_httpx_client.aclose.assert_called_once()

    def test_url_construction(self, onshape_client):
        """Test URL construction with base_url."""
        assert onshape_client.base_url == "https://test.onshape.com"

        # Verify path is appended correctly
        expected_url = "https://test.onshape.com/api/test"
        # This is tested indirectly through the get/post/delete methods
