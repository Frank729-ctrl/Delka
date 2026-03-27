import pytest
from tests.conftest import VALID_CV_PAYLOAD


async def test_missing_key_returns_401(client):
    resp = await client.post("/v1/cv/generate", json=VALID_CV_PAYLOAD)
    assert resp.status_code == 401
    assert resp.json()["status"] == "error"


async def test_wrong_key_returns_401(client):
    resp = await client.post(
        "/v1/cv/generate",
        json=VALID_CV_PAYLOAD,
        headers={"X-DelkaAI-Key": "fd-delka-sk-ffffffffffffffffffffffffffffffff"},
    )
    assert resp.status_code == 401


async def test_revoked_key_returns_403(client, valid_sk_key, master_key):
    prefix = valid_sk_key[:20]
    await client.post(
        "/v1/admin/keys/revoke",
        json={"key_prefix": prefix},
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    resp = await client.post(
        "/v1/cv/generate",
        json=VALID_CV_PAYLOAD,
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 403


async def test_flagged_key_returns_403(client, valid_sk_key, test_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    from security.key_store import flag_key

    prefix = valid_sk_key[:20]
    SM = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    async with SM() as db:
        await flag_key(prefix, db)

    resp = await client.post(
        "/v1/cv/generate",
        json=VALID_CV_PAYLOAD,
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 403


async def test_valid_sk_key_passes_auth(client, valid_sk_key, mock_ollama, mock_export):
    resp = await client.post(
        "/v1/cv/generate",
        json=VALID_CV_PAYLOAD,
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    # Auth passes; might fail at service layer if mock not active but not 401/403
    assert resp.status_code not in (401, 403)


async def test_valid_pk_key_passes_auth_on_allowed_endpoint(client, valid_pk_key, mock_ollama):
    resp = await client.post(
        "/v1/support/chat",
        json={"message": "Hello", "platform": "generic"},
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code not in (401, 403)


async def test_malformed_key_header_returns_401(client):
    resp = await client.post(
        "/v1/cv/generate",
        json=VALID_CV_PAYLOAD,
        headers={"X-DelkaAI-Key": "not-a-valid-key-format"},
    )
    assert resp.status_code == 401
