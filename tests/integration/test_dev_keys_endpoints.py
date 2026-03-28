"""
Tests for /v1/admin/dev-keys/* endpoints in health_router.
"""
import pytest

MASTER = "fd-delka-mk-testkey0000000000000000"
HEADERS = {"X-DelkaAI-Master-Key": MASTER}


# ── /v1/admin/dev-keys/create ────────────────────────────────────────────────

async def test_dev_keys_create_success(client):
    resp = await client.post(
        "/v1/admin/dev-keys/create",
        json={"owner": "dev@example.com", "key_name": "MyApp"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "secret_key" in body
    assert "publishable_key" in body
    assert "sk_prefix" in body
    assert "pk_prefix" in body


async def test_dev_keys_create_missing_owner(client):
    resp = await client.post(
        "/v1/admin/dev-keys/create",
        json={"key_name": "NoOwner"},
        headers=HEADERS,
    )
    assert resp.status_code == 422


async def test_dev_keys_create_missing_key_name(client):
    resp = await client.post(
        "/v1/admin/dev-keys/create",
        json={"owner": "dev@example.com"},
        headers=HEADERS,
    )
    assert resp.status_code == 422


async def test_dev_keys_create_invalid_master_key(client):
    resp = await client.post(
        "/v1/admin/dev-keys/create",
        json={"owner": "dev@example.com", "key_name": "App"},
        headers={"X-DelkaAI-Master-Key": "wrong"},
    )
    assert resp.status_code == 401


async def test_dev_keys_create_no_master_key(client):
    resp = await client.post(
        "/v1/admin/dev-keys/create",
        json={"owner": "dev@example.com", "key_name": "App"},
    )
    assert resp.status_code == 401


# ── /v1/admin/dev-keys/list ──────────────────────────────────────────────────

async def test_dev_keys_list_empty(client):
    resp = await client.get(
        "/v1/admin/dev-keys/list",
        params={"owner": "nobody@example.com"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json() == {"keys": []}


async def test_dev_keys_list_returns_created_keys(client):
    owner = "listtest@example.com"
    await client.post(
        "/v1/admin/dev-keys/create",
        json={"owner": owner, "key_name": "ListApp"},
        headers=HEADERS,
    )
    resp = await client.get(
        "/v1/admin/dev-keys/list",
        params={"owner": owner},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    keys = resp.json()["keys"]
    assert len(keys) == 2  # PK + SK
    assert all(k["owner"] == owner for k in keys)


async def test_dev_keys_list_invalid_master_key(client):
    resp = await client.get(
        "/v1/admin/dev-keys/list",
        params={"owner": "x@x.com"},
        headers={"X-DelkaAI-Master-Key": "bad"},
    )
    assert resp.status_code == 401


# ── /v1/admin/dev-keys/revoke ────────────────────────────────────────────────

async def test_dev_keys_revoke_success(client):
    owner = "revoke@example.com"
    create_resp = await client.post(
        "/v1/admin/dev-keys/create",
        json={"owner": owner, "key_name": "RevokeApp"},
        headers=HEADERS,
    )
    sk_prefix = create_resp.json()["sk_prefix"]

    resp = await client.post(
        "/v1/admin/dev-keys/revoke",
        json={"key_prefix": sk_prefix},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


async def test_dev_keys_revoke_not_found(client):
    resp = await client.post(
        "/v1/admin/dev-keys/revoke",
        json={"key_prefix": "fd-delka-sk-nonexistent"},
        headers=HEADERS,
    )
    assert resp.status_code == 404


async def test_dev_keys_revoke_missing_prefix(client):
    resp = await client.post(
        "/v1/admin/dev-keys/revoke",
        json={},
        headers=HEADERS,
    )
    assert resp.status_code == 422


async def test_dev_keys_revoke_invalid_master_key(client):
    resp = await client.post(
        "/v1/admin/dev-keys/revoke",
        json={"key_prefix": "someprefix"},
        headers={"X-DelkaAI-Master-Key": "bad"},
    )
    assert resp.status_code == 401
