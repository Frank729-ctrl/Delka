"""Unit tests for services/console_service.py."""
import pytest
from services.console_service import (
    get_developer_overview,
    get_developer_keys,
    get_platform_list,
    register_platform,
)


async def test_get_developer_overview_no_keys(test_db):
    """Overview returns zeros when developer has no keys."""
    overview = await get_developer_overview("nobody@example.com", test_db)
    assert overview["total_keys"] == 0
    assert overview["active_keys"] == 0
    assert overview["total_requests"] == 0
    assert "avg_response_ms" in overview
    assert "error_rate" in overview


async def test_get_developer_keys_returns_empty_for_unknown_owner(test_db):
    """get_developer_keys returns empty list for unknown email."""
    keys = await get_developer_keys("ghost@example.com", test_db)
    assert keys == []


async def test_get_platform_list_returns_empty_initially(test_db):
    """get_platform_list returns empty list when no platforms registered."""
    platforms = await get_platform_list(test_db)
    assert platforms == []


async def test_register_platform_creates_entry(test_db):
    """register_platform creates a new platform record."""
    result = await register_platform(
        "myapp", "owner@example.com", "My App", "https://example.com/wh", False, test_db
    )
    assert result["success"] is True
    assert result["platform_name"] == "myapp"


async def test_register_platform_duplicate_returns_error(test_db):
    """Registering the same platform name twice returns platform_exists error."""
    await register_platform("dupe", "a@b.com", None, None, False, test_db)
    result = await register_platform("dupe", "c@d.com", None, None, False, test_db)
    assert result["success"] is False
    assert result["error"] == "platform_exists"


async def test_get_platform_list_returns_registered_platforms(test_db):
    """get_platform_list returns all registered platforms."""
    await register_platform("plat1", "a@b.com", "Platform 1", None, False, test_db)
    await register_platform("plat2", "c@d.com", "Platform 2", "https://hook.example.com", True, test_db)
    platforms = await get_platform_list(test_db)
    names = [p["platform_name"] for p in platforms]
    assert "plat1" in names
    assert "plat2" in names


async def test_platform_with_webhook_has_correct_fields(test_db):
    """Registered platform with webhook returns correct webhook_url and requires_hmac."""
    await register_platform(
        "webhookplat", "owner@test.com", "Desc", "https://myapp.com/hook", True, test_db
    )
    platforms = await get_platform_list(test_db)
    p = next(x for x in platforms if x["platform_name"] == "webhookplat")
    assert p["webhook_url"] == "https://myapp.com/hook"
    assert p["requires_hmac"] is True
    assert p["is_active"] is True
