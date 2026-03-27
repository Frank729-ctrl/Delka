import pytest


async def test_create_key_pair_returns_201(client, master_key):
    resp = await client.post(
        "/v1/admin/keys/create",
        json={"platform": "myapp", "owner": "admin@myapp.com"},
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["publishable_key"].startswith("fd-delka-pk-")
    assert data["secret_key"].startswith("fd-delka-sk-")
    assert "warning" in data


async def test_list_keys_requires_master_key(client):
    resp = await client.get("/v1/admin/keys/list")
    assert resp.status_code == 401


async def test_revoke_key_marks_inactive(client, master_key, valid_sk_key):
    # Extract prefix from the key
    prefix = valid_sk_key[:20]
    resp = await client.post(
        "/v1/admin/keys/revoke",
        json={"key_prefix": prefix},
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    assert resp.status_code == 200

    # Confirm the key is now rejected
    cv_resp = await client.post(
        "/v1/cv/generate",
        json={"full_name": "Test"},
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert cv_resp.status_code == 403


async def test_wrong_master_key_returns_401(client):
    resp = await client.post(
        "/v1/admin/keys/create",
        json={"platform": "x", "owner": "y"},
        headers={"X-DelkaAI-Master-Key": "fd-delka-mk-wrong0000000000000000000"},
    )
    assert resp.status_code == 401
