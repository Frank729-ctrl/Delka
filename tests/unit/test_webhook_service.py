"""Tests for services/webhook_service.py — delivery, retries, HMAC signature."""
import hmac
import json
import pytest
from hashlib import sha256
from unittest.mock import AsyncMock, MagicMock, patch
from services.webhook_service import deliver


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeClient:
    """Context manager that wraps a post callable."""
    def __init__(self, post_fn):
        self._post_fn = post_fn

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def post(self, *args, **kwargs):
        return await self._post_fn(*args, **kwargs)


async def test_successful_delivery_returns_true(monkeypatch):
    """deliver() returns True when webhook endpoint responds with 200."""
    async def fake_post(*args, **kwargs):
        return _FakeResponse(200)

    with patch("services.webhook_service.httpx.AsyncClient",
               return_value=_FakeClient(fake_post)):
        result = await deliver("http://example.com/hook", {"key": "value"}, "secret123")
    assert result is True


async def test_4xx_response_retries_and_returns_false(monkeypatch):
    """deliver() retries on 4xx and ultimately returns False after exhausting retries."""
    call_count = []

    async def fake_post(*args, **kwargs):
        call_count.append(1)
        return _FakeResponse(422)

    with patch("services.webhook_service.httpx.AsyncClient",
               return_value=_FakeClient(fake_post)):
        with patch("config.settings.WEBHOOK_MAX_RETRIES", 2):
            result = await deliver("http://example.com/hook", {}, "secret")

    assert result is False
    assert len(call_count) == 2  # retried WEBHOOK_MAX_RETRIES times


async def test_connection_error_retries_and_returns_false(monkeypatch):
    """deliver() catches exceptions and retries, returning False on exhaustion."""
    import httpx
    call_count = []

    async def fake_post(*args, **kwargs):
        call_count.append(1)
        raise httpx.ConnectError("unreachable")

    with patch("services.webhook_service.httpx.AsyncClient",
               return_value=_FakeClient(fake_post)):
        with patch("config.settings.WEBHOOK_MAX_RETRIES", 2):
            result = await deliver("http://example.com/hook", {}, "secret")

    assert result is False
    assert len(call_count) == 2


async def test_payload_is_hmac_signed(monkeypatch):
    """deliver() computes correct HMAC-SHA256 signature and includes it in headers."""
    captured_headers = {}

    async def fake_post(url, content, headers):
        captured_headers.update(headers)
        return _FakeResponse(200)

    payload = {"event": "cv.generated", "data": {"pdf": "base64..."}}
    secret = "my_secret_key"
    body = json.dumps(payload, default=str)
    expected_sig = hmac.new(secret.encode(), body.encode(), sha256).hexdigest()

    with patch("services.webhook_service.httpx.AsyncClient",
               return_value=_FakeClient(fake_post)):
        await deliver("http://example.com/hook", payload, secret)

    assert captured_headers.get("X-DelkaAI-Signature") == expected_sig


async def test_first_attempt_success_does_not_retry(monkeypatch):
    """deliver() stops after first successful delivery — no extra retries."""
    call_count = []

    async def fake_post(*args, **kwargs):
        call_count.append(1)
        return _FakeResponse(201)

    with patch("services.webhook_service.httpx.AsyncClient",
               return_value=_FakeClient(fake_post)):
        result = await deliver("http://example.com/hook", {}, "secret")

    assert result is True
    assert len(call_count) == 1


async def test_5xx_response_retries(monkeypatch):
    """deliver() treats 5xx responses as failures and retries."""
    responses = [_FakeResponse(500), _FakeResponse(200)]
    idx = [0]

    async def fake_post(*args, **kwargs):
        r = responses[idx[0]]
        idx[0] += 1
        return r

    with patch("services.webhook_service.httpx.AsyncClient",
               return_value=_FakeClient(fake_post)):
        result = await deliver("http://example.com/hook", {}, "secret")

    assert result is True
