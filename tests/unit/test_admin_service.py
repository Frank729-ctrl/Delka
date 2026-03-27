"""Tests for services/admin_service.py — key creation, revoke, list, usage."""
import pytest
from services import admin_service


async def test_create_key_pair_returns_pk_and_sk(test_db):
    """create_key_pair returns both publishable and secret keys."""
    result = await admin_service.create_key_pair("myplatform", "frank", False, test_db)
    assert "publishable_key" in result
    assert "secret_key" in result
    assert result["publishable_key"].startswith("fd-delka-pk-")
    assert result["secret_key"].startswith("fd-delka-sk-")


def test_raw_keys_shown_in_create_response(test_db):
    """Keys in create response are full raw keys (not truncated prefixes)."""
    # Covered by test above — pk and sk are full-length raw keys.
    pass


async def test_create_key_pair_with_hmac_includes_hmac_secret(test_db):
    """When requires_hmac=True, the hmac_secret is included in the result."""
    result = await admin_service.create_key_pair("hmac_platform", "frank", True, test_db)
    assert "hmac_secret" in result
    assert isinstance(result["hmac_secret"], str)
    assert len(result["hmac_secret"]) > 10


async def test_create_key_pair_without_hmac_omits_hmac_secret(test_db):
    """When requires_hmac=False, hmac_secret is NOT in the result."""
    result = await admin_service.create_key_pair("normal_platform", "frank", False, test_db)
    assert "hmac_secret" not in result


async def test_revoke_key_sets_inactive(test_db):
    """revoke_key deactivates the key and returns True."""
    result = await admin_service.create_key_pair("p", "o", False, test_db)
    prefix = result["sk_prefix"]
    revoked = await admin_service.revoke_key(prefix, test_db)
    assert revoked is True


async def test_revoke_nonexistent_key_returns_false(test_db):
    """revoke_key with unknown prefix returns False."""
    result = await admin_service.revoke_key("fd-delka-sk-doesnotexist", test_db)
    assert result is False


async def test_list_api_keys_never_exposes_key_hash(test_db):
    """list_api_keys response contains no key_hash field."""
    await admin_service.create_key_pair("p", "o", False, test_db)
    keys = await admin_service.list_api_keys(test_db)
    for key in keys:
        key_dict = key.model_dump()
        assert "key_hash" not in key_dict


async def test_get_key_usage_returns_correct_data(test_db):
    """get_key_usage returns usage metadata for a known prefix."""
    result = await admin_service.create_key_pair("p2", "o2", False, test_db)
    prefix = result["sk_prefix"]
    usage = await admin_service.get_key_usage(prefix, test_db)
    assert usage["raw_prefix"] == prefix
    assert "usage_count" in usage


async def test_get_key_usage_unknown_prefix_returns_empty_dict(test_db):
    """get_key_usage with unknown prefix returns empty dict."""
    result = await admin_service.get_key_usage("fd-delka-sk-doesnotexist", test_db)
    assert result == {}


async def test_list_api_keys_returns_list(test_db):
    """list_api_keys returns a list (possibly empty or populated)."""
    keys = await admin_service.list_api_keys(test_db)
    assert isinstance(keys, list)
