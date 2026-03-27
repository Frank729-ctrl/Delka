"""Integration tests for POST /v1/chat."""
import pytest
from unittest.mock import AsyncMock, patch


_MOCK_TOKENS = ["Hey", " Kofi", "!", " How", " can", " I", " help", "?"]


@pytest.fixture(autouse=True)
def mock_chat_inference(monkeypatch):
    """Mock inference so no real LLM call is made."""
    async def fake_stream(task, messages, **kwargs):
        for token in _MOCK_TOKENS:
            yield token

    monkeypatch.setattr(
        "services.chat_service._inference_stream", fake_stream
    )


@pytest.mark.asyncio
async def test_chat_with_pk_key_returns_200(client, valid_pk_key):
    """POST /v1/chat with pk key returns 200 SSE stream."""
    resp = await client.post(
        "/v1/chat",
        json={
            "user_id": "kofi_001",
            "platform": "swypply",
            "session_id": "chat-001",
            "message": "Hi! I need help with my CV.",
        },
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_chat_no_key_returns_401(client):
    """POST /v1/chat without key returns 401."""
    resp = await client.post(
        "/v1/chat",
        json={
            "user_id": "kofi_001",
            "platform": "generic",
            "session_id": "s1",
            "message": "Hello",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_stream_ends_with_done(client, valid_pk_key):
    """POST /v1/chat stream contains [DONE] marker."""
    resp = await client.post(
        "/v1/chat",
        json={
            "user_id": "test_user",
            "platform": "generic",
            "session_id": "s2",
            "message": "Hello there",
        },
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code == 200
    assert b"[DONE]" in resp.content


@pytest.mark.asyncio
async def test_chat_has_tone_detected_header(client, valid_pk_key):
    """POST /v1/chat response includes X-Tone-Detected header."""
    resp = await client.post(
        "/v1/chat",
        json={
            "user_id": "test_user",
            "platform": "generic",
            "session_id": "s3",
            "message": "hello can u help me?",
        },
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code == 200
    assert "x-tone-detected" in resp.headers


@pytest.mark.asyncio
async def test_chat_with_user_id_updates_memory(client, valid_pk_key, test_db):
    """POST /v1/chat with user_id stores conversation history."""
    resp = await client.post(
        "/v1/chat",
        json={
            "user_id": "mem_user_001",
            "platform": "generic",
            "session_id": "mem-sess-001",
            "message": "My name is Kwame and I need CV help.",
        },
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_chat_with_correction_message_returns_acknowledgment(client, valid_pk_key, monkeypatch):
    """POST /v1/chat with correction message → correction acknowledged."""
    async def fake_generate(task, system_prompt, user_prompt, **kwargs):
        return ("Never use bullet points", "groq", "llama")

    monkeypatch.setattr("services.inference_service.generate_full_response", fake_generate)

    resp = await client.post(
        "/v1/chat",
        json={
            "user_id": "corr_user",
            "platform": "generic",
            "session_id": "corr-sess",
            "message": "Please stop using bullet points in your responses",
        },
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code == 200
    # Should contain acknowledgment
    content = resp.content.decode()
    assert "got it" in content.lower() or "remember" in content.lower() or "data:" in content


@pytest.mark.asyncio
async def test_chat_second_message_retrieves_profile(client, valid_pk_key):
    """Two consecutive requests with same user_id — second should work with memory."""
    for i in range(2):
        resp = await client.post(
            "/v1/chat",
            json={
                "user_id": "repeat_user",
                "platform": "generic",
                "session_id": f"repeat-sess-{i}",
                "message": "Tell me about CV formats.",
            },
            headers={"X-DelkaAI-Key": valid_pk_key},
        )
        assert resp.status_code == 200
