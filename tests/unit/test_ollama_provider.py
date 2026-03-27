import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from services.providers.ollama_provider import OllamaProvider


@pytest.fixture
def provider():
    return OllamaProvider()


def test_is_available_true_when_base_url_set(provider, monkeypatch):
    monkeypatch.setattr("config.settings.OLLAMA_BASE_URL", "http://localhost:11434")
    assert provider.is_available() is True


def test_is_rate_limit_error_always_false(provider):
    assert provider.is_rate_limit_error(Exception("429")) is False
    assert provider.is_rate_limit_error(RuntimeError("rate limit")) is False
    assert provider.is_rate_limit_error(Exception()) is False


async def test_generate_full_raises_503_when_unreachable(provider, monkeypatch):
    import httpx
    monkeypatch.setattr("config.settings.OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr("config.settings.OLLAMA_TIMEOUT_SECONDS", 5)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client_cls.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await provider.generate_full("sys", "user", "llama3.1")
        assert exc_info.value.status_code == 503


async def test_generate_full_raises_503_on_http_status_error(provider, monkeypatch):
    """generate_full raises HTTPException 503 on HTTPStatusError (e.g. 404)."""
    import httpx
    monkeypatch.setattr("config.settings.OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr("config.settings.OLLAMA_TIMEOUT_SECONDS", 5)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError("not found", request=MagicMock(), response=mock_resp)
        )
        mock_client_cls.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await provider.generate_full("sys", "user", "llama3.1")
        assert exc_info.value.status_code == 503


async def test_generate_full_raises_500_on_malformed_response(provider, monkeypatch):
    """generate_full raises HTTPException 500 when response JSON is missing message key."""
    import httpx
    monkeypatch.setattr("config.settings.OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr("config.settings.OLLAMA_TIMEOUT_SECONDS", 5)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"unexpected_key": "value"}  # No "message" key

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        with pytest.raises(HTTPException) as exc_info:
            await provider.generate_full("sys", "user", "llama3.1")
        assert exc_info.value.status_code == 500


async def test_generate_stream_yields_tokens(provider, monkeypatch):
    """generate_stream yields token strings from Ollama's streaming response."""
    import json as _json
    monkeypatch.setattr("config.settings.OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr("config.settings.OLLAMA_STREAM_TIMEOUT_SECONDS", 5)

    stream_lines = [
        _json.dumps({"message": {"content": "Hello"}, "done": False}),
        _json.dumps({"message": {"content": " World"}, "done": False}),
        _json.dumps({"message": {"content": ""}, "done": True}),
    ]

    class _FakeStreamCtx:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def aiter_lines(self):
            for line in stream_lines:
                yield line

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        def stream(self, *a, **kw):
            return _FakeStreamCtx()

    with patch("services.providers.ollama_provider.httpx.AsyncClient",
               return_value=_FakeClient()):
        tokens = []
        async for token in provider.generate_stream(
            [{"role": "user", "content": "hi"}], "llama3.1"
        ):
            tokens.append(token)

    assert "Hello" in tokens
    assert " World" in tokens


async def test_generate_stream_raises_503_on_connect_error(provider, monkeypatch):
    """generate_stream raises HTTPException 503 on ConnectError."""
    import httpx
    monkeypatch.setattr("config.settings.OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr("config.settings.OLLAMA_STREAM_TIMEOUT_SECONDS", 5)

    class _FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        def stream(self, *a, **kw):
            raise httpx.ConnectError("refused")

    with patch("services.providers.ollama_provider.httpx.AsyncClient",
               return_value=_FailingClient()):
        with pytest.raises(HTTPException) as exc_info:
            async for _ in provider.generate_stream(
                [{"role": "user", "content": "hi"}], "llama3.1"
            ):
                pass
        assert exc_info.value.status_code == 503


async def test_generate_full_returns_string_on_success(provider, monkeypatch):
    import httpx
    monkeypatch.setattr("config.settings.OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr("config.settings.OLLAMA_TIMEOUT_SECONDS", 5)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"message": {"content": "Generated text"}}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await provider.generate_full("sys", "user", "llama3.1")
        assert result == "Generated text"
        assert isinstance(result, str)
