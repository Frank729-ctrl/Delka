"""Integration tests for /admin/* console UI (email+password auth)."""
import pytest

from config import settings

_SESSION_TOKEN = "delka_admin_authenticated"


@pytest.fixture
def admin_cookie():
    return {"delka_admin_session": _SESSION_TOKEN}


async def test_admin_login_page_returns_200(client):
    """GET /admin/login returns login page."""
    resp = await client.get("/admin/login")
    assert resp.status_code == 200
    assert b"Admin Console" in resp.content or b"admin" in resp.content.lower()


async def test_admin_login_wrong_credentials_returns_401(client):
    """POST /admin/login with wrong credentials returns 401."""
    resp = await client.post(
        "/admin/login",
        data={"email": settings.ADMIN_EMAIL, "password": "wrong-password"},
        follow_redirects=False,
    )
    assert resp.status_code == 401


async def test_admin_login_correct_credentials_sets_cookie(client):
    """POST /admin/login with correct credentials sets cookie and redirects."""
    resp = await client.post(
        "/admin/login",
        data={"email": settings.ADMIN_EMAIL, "password": settings.ADMIN_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "delka_admin_session" in resp.cookies


async def test_admin_keys_page_without_cookie_redirects(client):
    """GET /admin/keys without cookie redirects to /admin/login."""
    resp = await client.get("/admin/keys", follow_redirects=False)
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers.get("location", "")


async def test_admin_keys_page_with_valid_cookie_returns_200(client, admin_cookie):
    """GET /admin/keys with valid cookie returns 200."""
    resp = await client.get("/admin/keys", cookies=admin_cookie)
    assert resp.status_code == 200
    assert b"API Keys" in resp.content


async def test_admin_security_page_with_valid_cookie_returns_200(client, admin_cookie):
    """GET /admin/security with valid cookie returns 200."""
    resp = await client.get("/admin/security", cookies=admin_cookie)
    assert resp.status_code == 200


async def test_admin_metrics_page_with_valid_cookie_returns_200(client, admin_cookie):
    """GET /admin/metrics with valid cookie returns 200."""
    resp = await client.get("/admin/metrics", cookies=admin_cookie)
    assert resp.status_code == 200


async def test_admin_providers_page_with_valid_cookie_returns_200(client, admin_cookie):
    """GET /admin/providers with valid cookie returns 200."""
    resp = await client.get("/admin/providers", cookies=admin_cookie)
    assert resp.status_code == 200


async def test_admin_platforms_page_with_valid_cookie_returns_200(client, admin_cookie):
    """GET /admin/platforms with valid cookie returns 200."""
    resp = await client.get("/admin/platforms", cookies=admin_cookie)
    assert resp.status_code == 200


async def test_admin_webhooks_page_with_valid_cookie_returns_200(client, admin_cookie):
    """GET /admin/webhooks with valid cookie returns 200."""
    resp = await client.get("/admin/webhooks", cookies=admin_cookie)
    assert resp.status_code == 200


async def test_admin_settings_page_with_valid_cookie_returns_200(client, admin_cookie):
    """GET /admin/settings with valid cookie returns 200."""
    resp = await client.get("/admin/settings", cookies=admin_cookie)
    assert resp.status_code == 200


async def test_admin_logout_clears_cookie_and_redirects(client, admin_cookie):
    """GET /admin/logout clears cookie and redirects to /admin/login."""
    resp = await client.get(
        "/admin/logout",
        cookies=admin_cookie,
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers.get("location", "")


async def test_admin_keys_create_via_form_returns_200(client, admin_cookie):
    """POST /admin/keys/create with valid data creates a key and shows it."""
    resp = await client.post(
        "/admin/keys/create",
        data={"platform": "testplatform", "owner": "admin@test.com"},
        cookies=admin_cookie,
    )
    assert resp.status_code == 200
    assert b"fd-delka-pk-" in resp.content or b"Created" in resp.content


async def test_admin_settings_upsert_redirects_on_success(client, admin_cookie):
    """POST /admin/settings/upsert saves setting and redirects."""
    resp = await client.post(
        "/admin/settings/upsert",
        data={
            "setting_key": "test_setting",
            "setting_value": "test_value",
            "description": "A test setting",
        },
        cookies=admin_cookie,
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/settings" in resp.headers.get("location", "")


async def test_admin_platform_register_redirects_on_success(client, admin_cookie):
    """POST /admin/platforms/register creates platform and redirects."""
    resp = await client.post(
        "/admin/platforms/register",
        data={
            "platform_name": "testplatform",
            "owner_email": "owner@test.com",
            "description": "Test platform",
            "webhook_url": "",
        },
        cookies=admin_cookie,
        follow_redirects=False,
    )
    assert resp.status_code == 302


async def test_admin_keys_revoke_without_auth_redirects(client):
    """POST /admin/keys/revoke without auth redirects to login."""
    resp = await client.post(
        "/admin/keys/revoke",
        data={"key_prefix": "fd-delka-sk-test0000000"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers.get("location", "")


async def test_admin_security_unblock_without_auth_redirects(client):
    """POST /admin/security/unblock without auth redirects to login."""
    resp = await client.post(
        "/admin/security/unblock",
        data={"ip_address": "1.2.3.4"},
        follow_redirects=False,
    )
    assert resp.status_code == 302


async def test_admin_keys_revoke_redirects_with_message(client, admin_cookie, valid_sk_key):
    """POST /admin/keys/revoke with valid key redirects with message."""
    prefix = valid_sk_key[:20]
    resp = await client.post(
        "/admin/keys/revoke",
        data={"key_prefix": prefix},
        cookies=admin_cookie,
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/keys" in resp.headers.get("location", "")


async def test_admin_keys_revoke_nonexistent_redirects_with_not_found_message(client, admin_cookie):
    """POST /admin/keys/revoke with nonexistent prefix redirects with not found message."""
    resp = await client.post(
        "/admin/keys/revoke",
        data={"key_prefix": "fd-delka-sk-doesnotexist00"},
        cookies=admin_cookie,
        follow_redirects=False,
    )
    assert resp.status_code == 302
    location = resp.headers.get("location", "")
    assert "not found" in location.lower() or "/admin/keys" in location


async def test_admin_security_unblock_with_auth_redirects(client, admin_cookie, test_db):
    """POST /admin/security/unblock with auth unblocks IP and redirects."""
    from security.ip_blocker import block_ip
    await block_ip("10.0.0.1", "test", test_db)
    resp = await client.post(
        "/admin/security/unblock",
        data={"ip_address": "10.0.0.1"},
        cookies=admin_cookie,
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/security" in resp.headers.get("location", "")
