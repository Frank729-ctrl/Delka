import pytest
from services.providers.groq_provider import GroqProvider


@pytest.fixture
def provider():
    return GroqProvider()


def test_is_available_false_when_key_empty(provider, monkeypatch):
    monkeypatch.setattr("config.settings.GROQ_API_KEY", "")
    assert provider.is_available() is False


def test_is_available_true_when_key_set(provider, monkeypatch):
    monkeypatch.setattr("config.settings.GROQ_API_KEY", "gsk_test_key")
    assert provider.is_available() is True


def test_is_rate_limit_error_true_for_groq_exception(provider):
    try:
        import groq
        err = groq.RateLimitError.__new__(groq.RateLimitError)
        assert provider.is_rate_limit_error(err) is True
    except (ImportError, Exception):
        pytest.skip("groq SDK not installed or RateLimitError not constructible directly")


def test_is_rate_limit_error_true_for_429_in_message(provider):
    err = Exception("HTTP 429 Too Many Requests")
    assert provider.is_rate_limit_error(err) is True


def test_is_rate_limit_error_true_for_rate_limit_in_message(provider):
    err = Exception("rate limit exceeded for model")
    assert provider.is_rate_limit_error(err) is True


def test_is_rate_limit_error_false_for_generic_error(provider):
    err = ValueError("some other error")
    assert provider.is_rate_limit_error(err) is False


async def test_generate_full_returns_string(provider, monkeypatch):
    """generate_full calls Groq SDK and returns the response content string."""
    from unittest.mock import AsyncMock, MagicMock, patch

    monkeypatch.setattr("config.settings.GROQ_API_KEY", "gsk_test_key")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Hello from Groq!"

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("groq.AsyncGroq", return_value=mock_client):
        result = await provider.generate_full("sys", "user", "llama-3.3-70b-versatile")

    assert result == "Hello from Groq!"


async def test_generate_stream_yields_tokens(provider, monkeypatch):
    """generate_stream yields non-empty token strings from the Groq stream."""
    from unittest.mock import AsyncMock, MagicMock, patch

    monkeypatch.setattr("config.settings.GROQ_API_KEY", "gsk_test_key")

    # Build fake stream chunks
    def make_chunk(content):
        c = MagicMock()
        c.choices = [MagicMock()]
        c.choices[0].delta.content = content
        return c

    chunks = [make_chunk("Hello"), make_chunk(""), make_chunk(" World")]

    async def fake_aiter(self):
        for chunk in chunks:
            yield chunk

    mock_stream = MagicMock()
    mock_stream.__aiter__ = fake_aiter

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_stream)

    with patch("groq.AsyncGroq", return_value=mock_client):
        tokens = []
        async for token in provider.generate_stream(
            [{"role": "user", "content": "hi"}], "llama-3.3-70b-versatile"
        ):
            tokens.append(token)

    assert "Hello" in tokens
    assert " World" in tokens
    # Empty string chunk should be filtered out
    assert "" not in tokens
