"""Unit tests for services/conversation_history_service.py."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_store_and_get_recent_history(test_db):
    from services.conversation_history_service import store_message, get_recent_history
    await store_message("u1", "plat", "sess1", "user", "Hello world", test_db)
    await store_message("u1", "plat", "sess1", "assistant", "Hi there!", test_db)
    await test_db.flush()

    history = await get_recent_history("u1", "plat", test_db)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello world"


@pytest.mark.asyncio
async def test_get_session_history_returns_messages_for_session(test_db):
    from services.conversation_history_service import store_message, get_session_history
    await store_message("u2", "plat", "sess-A", "user", "Msg for A", test_db)
    await store_message("u2", "plat", "sess-B", "user", "Msg for B", test_db)
    await test_db.flush()

    history = await get_session_history("u2", "sess-A", test_db)
    assert len(history) == 1
    assert history[0]["content"] == "Msg for A"


@pytest.mark.asyncio
async def test_get_session_history_empty_for_unknown(test_db):
    from services.conversation_history_service import get_session_history
    history = await get_session_history("nobody", "no-sess", test_db)
    assert history == []


@pytest.mark.asyncio
async def test_summarize_old_history_skips_when_under_50(test_db):
    from services.conversation_history_service import store_message, summarize_old_history
    for i in range(10):
        await store_message("sum_user", "plat", "s1", "user", f"Message {i}", test_db)
    await test_db.flush()

    result = await summarize_old_history("sum_user", "plat", test_db)
    assert result == ""


@pytest.mark.asyncio
async def test_summarize_old_history_calls_llm_when_over_50(test_db):
    from services.conversation_history_service import store_message, summarize_old_history

    for i in range(55):
        await store_message("heavy_user", "plat", f"s{i}", "user", f"Old message {i}", test_db)
    await test_db.flush()

    async def fake_generate(task, system_prompt, user_prompt, **kwargs):
        return ("Conversation summary here.", "groq", "llama")

    with patch("services.inference_service.generate_full_response", fake_generate):
        result = await summarize_old_history("heavy_user", "plat", test_db)

    assert result == "Conversation summary here."


@pytest.mark.asyncio
async def test_estimate_tokens():
    from services.conversation_history_service import estimate_tokens
    assert estimate_tokens("hello") >= 1
    assert estimate_tokens("a" * 400) == 100
