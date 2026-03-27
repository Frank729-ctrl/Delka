"""Integration tests for /v1/developer/* JSON API endpoints."""
import pytest


_EMAIL = "devapi@test.com"
_PASSWORD = "devpassword123"
_NAME = "Dev User"


@pytest.fixture
async def dev_session(client) -> str:
    """Register a developer and return a valid session token."""
    await client.post(
        "/v1/developer/register",
        json={"email": _EMAIL, "password": _PASSWORD, "full_name": _NAME},
    )
    resp = await client.post(
        "/v1/developer/login",
        json={"email": _EMAIL, "password": _PASSWORD},
    )
    return resp.json()["session_token"]


async def test_register_success(client):
    resp = await client.post(
        "/v1/developer/register",
        json={"email": "new_dev@test.com", "password": "pass123", "full_name": "New Dev"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


async def test_register_duplicate_returns_409(client):
    await client.post(
        "/v1/developer/register",
        json={"email": "dup@test.com", "password": "pass123", "full_name": "Dup"},
    )
    resp = await client.post(
        "/v1/developer/register",
        json={"email": "dup@test.com", "password": "pass123", "full_name": "Dup"},
    )
    assert resp.status_code == 409


async def test_login_success(client):
    await client.post(
        "/v1/developer/register",
        json={"email": "login_dev@test.com", "password": "pass123", "full_name": "Login Dev"},
    )
    resp = await client.post(
        "/v1/developer/login",
        json={"email": "login_dev@test.com", "password": "pass123"},
    )
    assert resp.status_code == 200
    assert "session_token" in resp.json()


async def test_login_wrong_password_returns_401(client):
    await client.post(
        "/v1/developer/register",
        json={"email": "wrongpass@test.com", "password": "correct", "full_name": "X"},
    )
    resp = await client.post(
        "/v1/developer/login",
        json={"email": "wrongpass@test.com", "password": "wrong"},
    )
    assert resp.status_code == 401


async def test_me_returns_account_info(client, dev_session):
    resp = await client.get(
        "/v1/developer/me",
        headers={"x-delkai-session": dev_session},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == _EMAIL
    assert data["full_name"] == _NAME


async def test_me_without_token_returns_401(client):
    resp = await client.get("/v1/developer/me")
    assert resp.status_code == 401


async def test_me_with_invalid_token_returns_401(client):
    resp = await client.get(
        "/v1/developer/me",
        headers={"x-delkai-session": "invalid-token-xyz"},
    )
    assert resp.status_code == 401


async def test_overview_returns_stats(client, dev_session):
    resp = await client.get(
        "/v1/developer/overview",
        headers={"x-delkai-session": dev_session},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_keys" in data
    assert "active_keys" in data


async def test_keys_returns_list(client, dev_session):
    resp = await client.get(
        "/v1/developer/keys",
        headers={"x-delkai-session": dev_session},
    )
    assert resp.status_code == 200
    assert "keys" in resp.json()


async def test_logout_success(client, dev_session):
    resp = await client.post(
        "/v1/developer/logout",
        headers={"x-delkai-session": dev_session},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


async def test_logout_invalidates_session(client, dev_session):
    await client.post(
        "/v1/developer/logout",
        headers={"x-delkai-session": dev_session},
    )
    resp = await client.get(
        "/v1/developer/me",
        headers={"x-delkai-session": dev_session},
    )
    assert resp.status_code == 401


async def test_register_with_company(client):
    resp = await client.post(
        "/v1/developer/register",
        json={
            "email": "company_dev@test.com",
            "password": "pass123",
            "full_name": "Company Dev",
            "company": "Acme Corp",
        },
    )
    assert resp.status_code == 200
