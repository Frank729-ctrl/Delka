"""Unit tests for services/correction_service.py."""
import pytest
from unittest.mock import AsyncMock, patch
from services.correction_service import is_correction


def test_is_correction_detects_dont_say():
    assert is_correction("don't say 'certainly' please") is True


def test_is_correction_detects_i_prefer():
    assert is_correction("I prefer shorter responses") is True


def test_is_correction_detects_stop_saying():
    assert is_correction("stop saying 'Great question!'") is True


def test_is_correction_detects_too_formal():
    assert is_correction("you're being too formal") is True


def test_is_correction_returns_false_for_normal_message():
    assert is_correction("How do I update my CV?") is False


def test_is_correction_returns_false_for_question():
    assert is_correction("What templates do you support?") is False


@pytest.mark.asyncio
async def test_extract_and_store_correction_returns_acknowledgment(test_db):
    from services.correction_service import extract_and_store_correction

    async def fake_generate(task, system_prompt, user_prompt, **kwargs):
        return ("Never use bullet points", "groq", "llama")

    with patch("services.inference_service.generate_full_response", fake_generate):
        result = await extract_and_store_correction(
            "stop using bullet points",
            "user_001",
            "test",
            test_db,
        )
    assert result is not None
    assert "got it" in result.lower() or "remember" in result.lower()


@pytest.mark.asyncio
async def test_extract_and_store_correction_calls_add_correction_rule(test_db):
    from services.correction_service import extract_and_store_correction

    async def fake_generate(task, system_prompt, user_prompt, **kwargs):
        return ("Never use bullet points", "groq", "llama")

    with patch("services.inference_service.generate_full_response", fake_generate):
        await extract_and_store_correction(
            "don't say certainly",
            "user_002",
            "test",
            test_db,
        )

    from services.memory_service import get_or_create_profile
    profile = await get_or_create_profile("user_002", "test", test_db)
    assert len(profile.correction_rules) >= 1


@pytest.mark.asyncio
async def test_extract_and_store_correction_returns_none_for_normal_message(test_db):
    from services.correction_service import extract_and_store_correction
    result = await extract_and_store_correction(
        "What is the weather like?",
        "user_003",
        "test",
        test_db,
    )
    assert result is None
