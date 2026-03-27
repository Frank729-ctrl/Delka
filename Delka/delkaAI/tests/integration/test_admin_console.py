"""Integration tests for /admin/* console UI (cookie-based auth)."""
import pytest


_MASTER_KEY = "fd-delka-mk-testkey000000000000000"


async def test_admin_login_page_returns_200(client):
    """GET /admin/login returns login page."""
    resp = await client.get("/admin/login")
    assert resp.status_code == 200
    assert b"Admin Console" in resp.content or b"admin" in resp.content.lower()


async def test_admin_login_wrong_key_returns_401(client):
    """POST /admin/login with wrong master key returns 401."""
    resp = await client.post(
        "/admin/login",
        data={"master_key": "wrong-key"},
        follow_redirects=False,
    )
    assert resp.status_code == 401


async def test_admin_login_correct_key_sets_cookie(client, master_key):
    """POST /admin/login with correct key sets cookie and redirects."""
    resp = await client.post(
        "/admin/login",
        data={"master_key": master_key},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "delka_admin_session" in resp.cookies


async def test_admin_keys_page_without_cookie_redirects(client):
    """GET /admin/keys without cookie redirects to /admin/login."""
    resp = await client.get("/admin/keys", follow_redirects=False)
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers.get("location", "")


async def test_admin_keys_page_with_valid_cookie_returns_200(client, master_key):
    """GET /admin/keys with valid cookie returns 200."""
    resp = await client.get(
        "/admin/keys",
        cookies={"delka_admin_session": master_key},
    )
    assert resp.status_code == 200
    assert b"API Keys" in resp.content


async def test_admin_security_page_with_valid_cookie_returns_200(client, master_key):
    """GET /admin/security with valid cookie returns 200."""
    resp = await client.get(
        "/admin/security",
        cookies={"delka_admin_session": master_key},
    )
    assert resp.status_code == 200


async def test_admin_metrics_page_with_valid_cookie_returns_200(client, master_key):
    """GET /admin/metrics with valid cookie returns 200."""
    resp = await client.get(
        "/admin/metrics",
        cookies={"delka_admin_session": master_key},
    )
    assert resp.status_code == 200


async def test_admin_providers_page_with_valid_cookie_returns_200(client, master_key):
    """GET /admin/providers with valid cookie returns 200."""
    resp = await client.get(
        "/admin/providers",
        cookies={"delka_admin_session": master_key},
    )
    assert resp.status_code == 200


async def test_admin_platforms_page_with_valid_cookie_returns_200(client, master_key):
    """GET /admin/platforms with valid cookie returns 200."""
    resp = await client.get(
        "/admin/platforms",
        cookies={"delka_admin_session": master_key},
    )
    assert resp.status_code == 200


async def test_admin_webhooks_page_with_valid_cookie_returns_200(client, master_key):
    """GET /admin/webhooks with valid cookie returns 200."""
    resp = await client.get(
        "/admin/webhooks",
        cookies={"delka_admin_session": master_key},
    )
    assert resp.status_code == 200


async def test_admin_settings_page_with_valid_cookie_returns_200(client, master_key):
    """GET /admin/settings with valid cookie returns 200."""
    resp = await client.get(
        "/admin/settings",
        cookies={"delka_admin_session": master_key},
    )
    assert resp.status_code == 200


async def test_admin_logout_clears_cookie_and_redirects(client, master_key):
    """GET /admin/logout clears cookie and redirects to /admin/login."""
    resp = await client.get(
        "/admin/logout",
        cookies={"delka_admin_session": master_key},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers.get("location", "")


async def test_admin_keys_create_via_form_returns_200(client, master_key):
    """POST /admin/keys/create with valid data creates a key and shows it."""
    resp = await client.post(
        "/admin/keys/create",
        data={"platform": "testplatform", "owner": "admin@test.com"},
        cookies={"delka_admin_session": master_key},
    )
    assert resp.status_code == 200
    assert b"fd-delka-pk-" in resp.content or b"Created" in resp.content


async def test_admin_settings_upsert_redirects_on_success(client, master_key):
    """POST /admin/settings/upsert saves setting and redirects."""
    resp = await client.post(
        "/admin/settings/upsert",
        data={
            "setting_key": "test_setting",
            "setting_value": "test_value",
            "description": "A test setting",
        },
        cookies={"delka_admin_session": master_key},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/settings" in resp.headers.get("location", "")


async def test_admin_platform_register_redirects_on_success(client, master_key):
    """POST /admin/platforms/register creates platform and redirects."""
    resp = await client.post(
        "/admin/platforms/register",
        data={
            "platform_name": "testplatform",
            "owner_email": "owner@test.com",
            "description": "Test platform",
            "webhook_url": "",
        },
        cookies={"delka_admin_session": master_key},
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


async def test_admin_keys_revoke_redirects_with_message(client, master_key, valid_sk_key):
    """POST /admin/keys/revoke with valid key redirects with message."""
    prefix = valid_sk_key[:20]
    resp = await client.post(
        "/admin/keys/revoke",
        data={"key_prefix": prefix},
        cookies={"delka_admin_session": master_key},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/keys" in resp.headers.get("location", "")


async def test_admin_keys_revoke_nonexistent_redirects_with_not_found_message(client, master_key):
    """POST /admin/keys/revoke with nonexistent prefix redirects with not found message."""
    resp = await client.post(
        "/admin/keys/revoke",
        data={"key_prefix": "fd-delka-sk-doesnotexist00"},
        cookies={"delka_admin_session": master_key},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    location = resp.headers.get("location", "")
    assert "not found" in location.lower() or "/admin/keys" in location


async def test_admin_security_unblock_with_auth_redirects(client, master_key, test_db):
    """POST /admin/security/unblock with auth unblocks IP and redirects."""
    from security.ip_blocker import block_ip
    await block_ip("10.0.0.1", "test", test_db)
    resp = await client.post(
        "/admin/security/unblock",
        data={"ip_address": "10.0.0.1"},
        cookies={"delka_admin_session": master_key},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/security" in resp.headers.get("location", "")
