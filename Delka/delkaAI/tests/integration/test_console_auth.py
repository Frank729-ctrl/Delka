"""Integration tests for /console/* — register, login, session auth."""
import pytest


async def _create_session(client, email="console@test.com", password="pass1234", name="Console User"):
    """Helper: register + login, return session token."""
    await client.post(
        "/console/register",
        data={"email": email, "password": password, "full_name": name, "company": ""},
        follow_redirects=False,
    )
    resp = await client.post(
        "/console/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    return resp.cookies.get("delka_console_session")


async def test_register_page_returns_200(client):
    """Register page loads successfully."""
    resp = await client.get("/console/register")
    assert resp.status_code == 200
    assert b"Create Account" in resp.content


async def test_login_page_returns_200(client):
    """Login page loads successfully."""
    resp = await client.get("/console/login")
    assert resp.status_code == 200
    assert b"Developer Console" in resp.content


async def test_register_post_creates_account_and_redirects(client):
    """POST /console/register with valid data redirects to login."""
    resp = await client.post(
        "/console/register",
        data={
            "email": "test@delkaai.com",
            "password": "securepass123",
            "full_name": "Test User",
            "company": "TestCo",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/console/login" in resp.headers.get("location", "")


async def test_register_duplicate_email_returns_400(client):
    """Registering with a taken email returns 400."""
    await client.post(
        "/console/register",
        data={"email": "dup@test.com", "password": "pass1234", "full_name": "Dup", "company": ""},
        follow_redirects=False,
    )
    resp = await client.post(
        "/console/register",
        data={"email": "dup@test.com", "password": "pass5678", "full_name": "Dup2", "company": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 400


async def test_login_post_valid_credentials_redirects(client):
    """POST /console/login with valid creds sets cookie and redirects to overview."""
    await client.post(
        "/console/register",
        data={"email": "login@test.com", "password": "pass1234", "full_name": "Login User", "company": ""},
        follow_redirects=False,
    )
    resp = await client.post(
        "/console/login",
        data={"email": "login@test.com", "password": "pass1234"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "delka_console_session" in resp.cookies


async def test_login_invalid_credentials_returns_401(client):
    """POST /console/login with wrong password returns 401."""
    resp = await client.post(
        "/console/login",
        data={"email": "nobody@example.com", "password": "wrongpass"},
        follow_redirects=False,
    )
    assert resp.status_code == 401


async def test_overview_without_session_redirects_to_login(client):
    """GET /console/overview without cookie redirects to /console/login."""
    resp = await client.get("/console/overview", follow_redirects=False)
    assert resp.status_code == 302
    assert "/console/login" in resp.headers.get("location", "")


async def test_overview_with_valid_session_returns_200(client):
    """GET /console/overview with valid session cookie returns 200."""
    await client.post(
        "/console/register",
        data={"email": "view@test.com", "password": "pass1234", "full_name": "Viewer", "company": ""},
        follow_redirects=False,
    )
    login_resp = await client.post(
        "/console/login",
        data={"email": "view@test.com", "password": "pass1234"},
        follow_redirects=False,
    )
    token = login_resp.cookies.get("delka_console_session")
    resp = await client.get(
        "/console/overview",
        cookies={"delka_console_session": token},
    )
    assert resp.status_code == 200
    assert b"Welcome" in resp.content


async def test_keys_page_requires_auth(client):
    """GET /console/keys without session redirects to login."""
    resp = await client.get("/console/keys", follow_redirects=False)
    assert resp.status_code == 302


async def test_usage_page_requires_auth(client):
    """GET /console/usage without session redirects to login."""
    resp = await client.get("/console/usage", follow_redirects=False)
    assert resp.status_code == 302


async def test_docs_page_requires_auth(client):
    """GET /console/docs without session redirects to login."""
    resp = await client.get("/console/docs", follow_redirects=False)
    assert resp.status_code == 302


async def test_playground_page_requires_auth(client):
    """GET /console/playground without session redirects to login."""
    resp = await client.get("/console/playground", follow_redirects=False)
    assert resp.status_code == 302


async def test_support_page_requires_auth(client):
    """GET /console/support without session redirects to login."""
    resp = await client.get("/console/support", follow_redirects=False)
    assert resp.status_code == 302


async def test_keys_page_with_session_returns_200(client):
    """GET /console/keys with valid session returns 200."""
    token = await _create_session(client, "keys@test.com")
    resp = await client.get("/console/keys", cookies={"delka_console_session": token})
    assert resp.status_code == 200
    assert b"API Keys" in resp.content


async def test_usage_page_with_session_returns_200(client):
    """GET /console/usage with valid session returns 200."""
    token = await _create_session(client, "usage@test.com")
    resp = await client.get("/console/usage", cookies={"delka_console_session": token})
    assert resp.status_code == 200
    assert b"Usage" in resp.content


async def test_docs_page_with_session_returns_200(client):
    """GET /console/docs with valid session returns 200."""
    token = await _create_session(client, "docs@test.com")
    resp = await client.get("/console/docs", cookies={"delka_console_session": token})
    assert resp.status_code == 200
    assert b"API Reference" in resp.content or b"Docs" in resp.content


async def test_playground_page_with_session_returns_200(client):
    """GET /console/playground with valid session returns 200."""
    token = await _create_session(client, "playground@test.com")
    resp = await client.get("/console/playground", cookies={"delka_console_session": token})
    assert resp.status_code == 200
    assert b"Playground" in resp.content


async def test_support_page_with_session_returns_200(client):
    """GET /console/support with valid session returns 200."""
    token = await _create_session(client, "support@test.com")
    resp = await client.get("/console/support", cookies={"delka_console_session": token})
    assert resp.status_code == 200
    assert b"Support" in resp.content


async def test_logout_clears_session(client):
    """GET /console/logout clears session cookie and redirects to login."""
    await client.post(
        "/console/register",
        data={"email": "logoutme@test.com", "password": "pass1234", "full_name": "Logout", "company": ""},
        follow_redirects=False,
    )
    login_resp = await client.post(
        "/console/login",
        data={"email": "logoutme@test.com", "password": "pass1234"},
        follow_redirects=False,
    )
    token = login_resp.cookies.get("delka_console_session")

    logout_resp = await client.get(
        "/console/logout",
        cookies={"delka_console_session": token},
        follow_redirects=False,
    )
    assert logout_resp.status_code == 302
    assert "/console/login" in logout_resp.headers.get("location", "")
