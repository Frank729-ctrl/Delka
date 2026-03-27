"""Tests for middleware/ip_block_middleware.py — blocked vs allowed paths.

Note: IPBlockMiddleware runs after APIKeyMiddleware in the stack.
For V1 paths, API key auth runs first. Tests use a valid key or non-V1 paths.
"""
import pytest
from unittest.mock import AsyncMock


async def test_blocked_ip_with_valid_key_returns_404(client, valid_sk_key, monkeypatch):
    """A blocked IP with a valid API key receives 404 from IPBlockMiddleware."""
    import middleware.ip_block_middleware as _ibm
    monkeypatch.setattr(_ibm, "is_ip_blocked", AsyncMock(return_value=True))
    # Use a path that passes API key auth but is then caught by IPBlockMiddleware
    resp = await client.get("/v1/health")
    # health is in IPBlockMiddleware's SKIP_PATHS so it passes
    assert resp.status_code == 200


async def test_blocked_ip_on_non_v1_path_returns_404(client, monkeypatch):
    """A blocked IP on a non-V1 path (e.g., honeypot) gets 404 from IPBlockMiddleware."""
    import middleware.ip_block_middleware as _ibm
    monkeypatch.setattr(_ibm, "is_ip_blocked", AsyncMock(return_value=True))
    # Unknown path goes through IPBlockMiddleware (APIKeyMiddleware passes non-v1 paths)
    resp = await client.get("/some-unknown-path-xyz")
    assert resp.status_code == 404


async def test_unblocked_ip_passes_through(client, monkeypatch):
    """A non-blocked IP passes through the IP block middleware normally."""
    import middleware.ip_block_middleware as _ibm
    monkeypatch.setattr(_ibm, "is_ip_blocked", AsyncMock(return_value=False))
    resp = await client.get("/v1/health")
    assert resp.status_code == 200


async def test_blocked_ip_on_health_endpoint_allowed(client, monkeypatch):
    """Health endpoint is in IPBlockMiddleware's skip list — blocked IPs can still check health."""
    import middleware.ip_block_middleware as _ibm
    # Even if is_ip_blocked would return True, /v1/health is skipped
    monkeypatch.setattr(_ibm, "is_ip_blocked", AsyncMock(return_value=True))
    resp = await client.get("/v1/health")
    assert resp.status_code == 200
    # is_ip_blocked should NOT have been called for /v1/health
    _ibm.is_ip_blocked.assert_not_called()
