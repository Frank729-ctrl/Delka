"""Integration tests for /v1/admin/* endpoints — error cases and happy paths."""
import pytest
from tests.conftest import VALID_CV_PAYLOAD


async def test_admin_invalid_master_key_returns_401(client):
    """Admin endpoint with wrong master key returns 401."""
    resp = await client.post(
        "/v1/admin/keys/create",
        json={"platform": "test", "owner": "frank"},
        headers={"X-DelkaAI-Master-Key": "wrong-key"},
    )
    assert resp.status_code == 401


async def test_admin_create_keys_returns_201(client, master_key):
    """Creating a key pair with correct master key returns 201."""
    resp = await client.post(
        "/v1/admin/keys/create",
        json={"platform": "test", "owner": "frank"},
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "success"
    assert "publishable_key" in data["data"]
    assert "secret_key" in data["data"]


async def test_admin_list_keys_returns_200(client, master_key, valid_sk_key):
    """Listing keys with correct master key returns 200."""
    resp = await client.get(
        "/v1/admin/keys/list",
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    assert resp.status_code == 200


async def test_admin_revoke_nonexistent_key_returns_404(client, master_key):
    """Revoking a non-existent key prefix returns 404."""
    resp = await client.post(
        "/v1/admin/keys/revoke",
        json={"key_prefix": "fd-delka-sk-doesnotexist00"},
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    assert resp.status_code == 404


async def test_admin_revoke_key_returns_200(client, master_key, valid_sk_key):
    """Revoking a real key prefix returns 200."""
    prefix = valid_sk_key[:20]
    resp = await client.post(
        "/v1/admin/keys/revoke",
        json={"key_prefix": prefix},
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    assert resp.status_code == 200


async def test_admin_metrics_returns_200(client, master_key):
    """Admin metrics endpoint returns 200 with metrics data."""
    resp = await client.get(
        "/v1/admin/metrics",
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    assert resp.status_code == 200


async def test_admin_blocked_ips_returns_200(client, master_key):
    """Admin blocked IPs endpoint returns 200."""
    resp = await client.get(
        "/v1/admin/blocked-ips",
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    assert resp.status_code == 200


async def test_admin_key_usage_known_prefix(client, master_key, valid_sk_key):
    """Key usage endpoint returns 200 for a known prefix."""
    prefix = valid_sk_key[:20]
    resp = await client.get(
        f"/v1/admin/keys/{prefix}/usage",
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    assert resp.status_code == 200


async def test_admin_key_usage_unknown_prefix_returns_404(client, master_key):
    """Key usage endpoint returns 404 for an unknown prefix."""
    resp = await client.get(
        "/v1/admin/keys/fd-delka-sk-doesnotexist0/usage",
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    assert resp.status_code == 404


async def test_admin_unblock_ip_returns_200(client, master_key, test_db):
    """Unblock IP endpoint returns 200 for a known IP."""
    from security.ip_blocker import block_ip
    await block_ip("192.168.0.99", "test", test_db)
    resp = await client.post(
        "/v1/admin/unblock-ip",
        json={"ip_address": "192.168.0.99"},
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    assert resp.status_code == 200


async def test_admin_job_status_not_found(client, master_key):
    """Job status for unknown job_id returns not_found."""
    resp = await client.get(
        "/v1/admin/jobs/nonexistent-job-id",
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "not_found"
