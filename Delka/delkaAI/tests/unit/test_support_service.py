"""Unit tests for services/support_service.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


_TOKENS = ["Hello", " there", "!"]


@pytest.fixture(autouse=True)
def mock_stream(monkeypatch):
    async def fake_stream(task, messages, **kwargs):
        for t in _TOKENS:
            yield t
    monkeypatch.setattr("services.support_service._inference_stream", fake_stream)


@pytest.mark.asyncio
async def test_handle_chat_returns_streaming_response():
    from fastapi.responses import StreamingResponse
    from services.support_service import handle_chat
    from schemas.support_schema import SupportChatRequest

    data = SupportChatRequest(session_id="s1", message="Hi", platform="generic")
    resp = await handle_chat(data)
    assert isinstance(resp, StreamingResponse)


@pytest.mark.asyncio
async def test_handle_chat_uses_fallback_when_validator_rejects(monkeypatch):
    """validate_support_response returns False → fallback text used."""
    from fastapi.responses import StreamingResponse
    from services.support_service import handle_chat
    from schemas.support_schema import SupportChatRequest

    monkeypatch.setattr("services.support_service.validate_support_response", lambda x: False)

    data = SupportChatRequest(session_id="s2", message="Hi", platform="generic")
    resp = await handle_chat(data)
    assert isinstance(resp, StreamingResponse)

    # Collect SSE body
    chunks = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk)
    body = "".join(chunks)
    assert "rephrase" in body.lower() or "help" in body.lower()


@pytest.mark.asyncio
async def test_handle_chat_with_user_id_and_db_triggers_memory_hooks(test_db, monkeypatch):
    """When db and user_id are provided the memory hooks execute without error."""
    from services.support_service import handle_chat
    from schemas.support_schema import SupportChatRequest

    async def fake_generate(task, system_prompt, user_prompt, **kwargs):
        return ("summary text", "groq", "llama")

    monkeypatch.setattr("services.inference_service.generate_full_response", fake_generate)

    data = SupportChatRequest(
        session_id="mem-sess",
        message="Hello, my name is Kwame",
        platform="generic",
        user_id="support_mem_user",
    )
    resp = await handle_chat(data, db=test_db)
    # Just verify it returns successfully; memory hooks run silently
    from fastapi.responses import StreamingResponse
    assert isinstance(resp, StreamingResponse)
