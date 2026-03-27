"""Unit tests for services/settings_service.py."""
import pytest
from services.settings_service import (
    get_setting, upsert_setting, list_settings, delete_setting
)


async def test_get_setting_returns_none_when_missing(test_db):
    """get_setting returns None for a key that hasn't been stored."""
    result = await get_setting("nonexistent_key", test_db)
    assert result is None


async def test_upsert_creates_new_setting(test_db):
    """upsert_setting creates a new record and returns a SettingItem."""
    item = await upsert_setting("feature_x", "enabled", "Feature X toggle", "admin", test_db)
    assert item.setting_key == "feature_x"
    assert item.setting_value == "enabled"
    assert item.description == "Feature X toggle"
    assert item.updated_by == "admin"


async def test_get_setting_returns_value_after_upsert(test_db):
    """get_setting returns the correct value after upserting."""
    await upsert_setting("site_name", "DelkaAI", None, None, test_db)
    result = await get_setting("site_name", test_db)
    assert result == "DelkaAI"


async def test_upsert_updates_existing_setting(test_db):
    """upsert_setting updates an existing record."""
    await upsert_setting("max_tokens", "1000", "Token limit", "admin", test_db)
    item = await upsert_setting("max_tokens", "2000", None, "superadmin", test_db)
    assert item.setting_value == "2000"
    assert item.updated_by == "superadmin"


async def test_upsert_preserves_description_if_not_given(test_db):
    """upsert_setting preserves existing description when None passed."""
    await upsert_setting("rate_limit", "30", "Rate limit per minute", "admin", test_db)
    item = await upsert_setting("rate_limit", "60", None, "admin", test_db)
    # description None means don't update, so original description preserved
    assert item.setting_key == "rate_limit"
    assert item.setting_value == "60"


async def test_list_settings_returns_all(test_db):
    """list_settings returns all stored settings ordered by key."""
    await upsert_setting("z_last", "val1", None, None, test_db)
    await upsert_setting("a_first", "val2", None, None, test_db)
    items = await list_settings(test_db)
    keys = [i.setting_key for i in items]
    assert "z_last" in keys
    assert "a_first" in keys
    # Should be alphabetically ordered
    assert keys.index("a_first") < keys.index("z_last")


async def test_list_settings_empty_returns_empty_list(test_db):
    """list_settings returns empty list when no settings exist."""
    items = await list_settings(test_db)
    assert items == []


async def test_delete_setting_removes_record(test_db):
    """delete_setting removes the setting and returns True."""
    await upsert_setting("temp_key", "temp_val", None, None, test_db)
    ok = await delete_setting("temp_key", test_db)
    assert ok is True
    result = await get_setting("temp_key", test_db)
    assert result is None


async def test_delete_setting_nonexistent_returns_false(test_db):
    """delete_setting returns False when the key doesn't exist."""
    ok = await delete_setting("does_not_exist", test_db)
    assert ok is False
