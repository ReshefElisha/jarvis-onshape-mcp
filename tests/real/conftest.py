"""Shared fixtures for real-API tests.

The module-level `client` singleton in `onshape_mcp.server` lazily creates
its underlying httpx client on first use, binding it to whichever event
loop fires first. pytest-asyncio recycles the loop between tests, leaving
the cached httpx client dead -- the next test that calls
`server.call_tool(...)` raises `RuntimeError: Event loop is closed`.

The autouse fixture below nulls `server.client._client` at the start of
every real-API test so the singleton lazy-rebuilds in the current loop.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_server_singleton_per_test():
    """Reset the server-level OnshapeClient's underlying httpx client so each
    async test gets a fresh connection bound to its own event loop."""
    import onshape_mcp.server as srv  # noqa: PLC0415
    srv.client._client = None
    yield
    # No teardown needed -- next test's autouse will reset again before use.
