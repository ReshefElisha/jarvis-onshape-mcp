"""Onshape API client for REST API communication."""

import base64
import httpx
from typing import Any, Dict, Optional
from pydantic import BaseModel


class OnshapeCredentials(BaseModel):
    """Onshape API credentials."""
    access_key: str
    secret_key: str
    base_url: str = "https://cad.onshape.com"


class OnshapeClient:
    """Client for interacting with Onshape REST API."""

    def __init__(self, credentials: OnshapeCredentials):
        """Initialize the Onshape client.

        Args:
            credentials: Onshape API credentials (access key and secret key)
        """
        self.credentials = credentials
        self.base_url = credentials.base_url
        self._client = httpx.AsyncClient(timeout=30.0)

    def _get_auth_header(self) -> str:
        """Generate Basic Auth header from credentials.

        Returns:
            Authorization header value
        """
        auth_string = f"{self.credentials.access_key}:{self.credentials.secret_key}"
        encoded = base64.b64encode(auth_string.encode()).decode()
        return f"Basic {encoded}"

    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a GET request to Onshape API.

        Args:
            path: API endpoint path (e.g., "/api/v9/documents")
            params: Query parameters

        Returns:
            JSON response data
        """
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": self._get_auth_header(),
            "Accept": "application/json;charset=UTF-8; qs=0.09"
        }

        response = await self._client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()

    async def post(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a POST request to Onshape API.

        Args:
            path: API endpoint path
            data: JSON body data
            params: Query parameters

        Returns:
            JSON response data
        """
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": self._get_auth_header(),
            "Accept": "application/json;charset=UTF-8; qs=0.09",
            "Content-Type": "application/json;charset=UTF-8; qs=0.09"
        }

        response = await self._client.post(url, json=data, params=params, headers=headers)
        response.raise_for_status()
        return response.json()

    async def delete(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a DELETE request to Onshape API.

        Args:
            path: API endpoint path
            params: Query parameters

        Returns:
            JSON response data
        """
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": self._get_auth_header(),
            "Accept": "application/json;charset=UTF-8; qs=0.09"
        }

        response = await self._client.delete(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
