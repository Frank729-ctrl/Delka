"""Unit tests for services/memory_service.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_profile(**kwargs):
    p = MagicMock()
    p.user_id = kwargs.get("user_id", "user_001")
    p.platform = kwargs.get("platform", "test")
    p.name = kwargs.get("name", None)
    p.language_preference = kwargs.get("language_preference", "en")
    p.tone_preference = kwargs.get("tone_preference", "adaptive")
    p.correction_rules = kwargs.get("correction_rules", [])
    p.preferences = kwargs.get("preferences", {})
    p.cv_profile = kwargs.get("cv_profile", {})
    p.topics_discussed = kwargs.get("topics_discussed", [])
    p.total_interactions = kwargs.get("total_interactions", 0)
    p.avg_rating_given = kwargs.get("avg_rating_given", 0.0)
    p.last_seen = None
    return p


@pytest.mark.asyncio
async def test_get_or_create_profile_creates_blank_for_new_user(test_db):
    from services.memory_service import get_or_create_profile
    profile = await get_or_create_profile("new_user_001", "test_platform", test_db)
    assert profile is not None
    assert profile.user_id == "new_user_001"
    assert profile.platform == "test_platform"


@pytest.mark.asyncio
async def test_get_or_create_profile_returns_existing(test_db):
    from services.memory_service import get_or_create_profile
    p1 = await get_or_create_profile("existing_user", "plat", test_db)
    p1.name = "Kofi"
    await test_db.flush()
    p2 = await get_or_create_profile("existing_user", "plat", test_db)
    assert p2.name == "Kofi"


@pytest.mark.asyncio
async def test_update_profile_merges_correctly(test_db):
    from services.memory_service import get_or_create_profile, update_profile
    await get_or_create_profile("upd_user", "plat", test_db)
    await update_profile("upd_user", "plat", {"name": "Ama"}, test_db)
    profile = await get_or_create_profile("upd_user", "plat", test_db)
    assert profile.name == "Ama"
    assert profile.total_interactions >= 1


@pytest.mark.asyncio
async def test_add_correction_rule_appends(test_db):
    from services.memory_service import add_correction_rule, get_or_create_profile
    await get_or_create_profile("rule_user", "plat", test_db)
    await add_correction_rule("rule_user", "plat", "Never use jargon", test_db)
    profile = await get_or_create_profile("rule_user", "plat", test_db)
    assert "Never use jargon" in profile.correction_rules


@pytest.mark.asyncio
async def test_add_correction_rule_deduplicates(test_db):
    from services.memory_service import add_correction_rule, get_or_create_profile
    await get_or_create_profile("dup_user", "plat", test_db)
    await add_correction_rule("dup_user", "plat", "Keep it short", test_db)
    await add_correction_rule("dup_user", "plat", "Keep it short", test_db)
    profile = await get_or_create_profile("dup_user", "plat", test_db)
    assert profile.correction_rules.count("Keep it short") == 1


@pytest.mark.asyncio
async def test_add_correction_rule_enforces_max_20(test_db):
    from services.memory_service import add_correction_rule, get_or_create_profile
    await get_or_create_profile("max_user", "plat", test_db)
    for i in range(25):
        await add_correction_rule("max_user", "plat", f"Rule number {i}", test_db)
    profile = await get_or_create_profile("max_user", "plat", test_db)
    assert len(profile.correction_rules) <= 20


@pytest.mark.asyncio
async def test_extract_profile_updates_finds_name():
    from services.memory_service import extract_profile_updates
    profile = _make_profile()
    updates = await extract_profile_updates(
        "Hi, my name is Kofi and I need help", "", profile
    )
    assert updates.get("name") == "Kofi"


@pytest.mark.asyncio
async def test_extract_profile_updates_finds_job_title():
    from services.memory_service import extract_profile_updates
    profile = _make_profile()
    updates = await extract_profile_updates(
        "I work as a software engineer at a startup.", "", profile
    )
    assert "cv_profile" in updates


@pytest.mark.asyncio
async def test_build_memory_context_string_returns_string():
    from services.memory_service import build_memory_context_string
    profile = _make_profile(name="Kofi", total_interactions=10)
    result = await build_memory_context_string(profile, [], [])
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_build_memory_context_string_handles_empty_profile():
    from services.memory_service import build_memory_context_string
    profile = _make_profile()
    result = await build_memory_context_string(profile, [], [])
    # New user with nothing stored should return empty or minimal
    assert isinstance(result, str)
