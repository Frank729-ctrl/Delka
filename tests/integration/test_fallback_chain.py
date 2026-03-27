"""Integration tests for the provider fallback chain."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from tests.conftest import VALID_CV_PAYLOAD, VALID_LETTER_PAYLOAD, FIXTURE_CV_JSON


def _make_rate_limit_groq():
    """Mock GroqProvider that always raises a rate limit error."""
    import groq
    m = MagicMock()
    m.is_available.return_value = True
    m.is_rate_limit_error.return_value = True
    m.generate_full = AsyncMock(side_effect=groq.RateLimitError.__new__(groq.RateLimitError))
    return m


def _make_succeeding_ollama():
    """Mock OllamaProvider that succeeds."""
    m = MagicMock()
    m.is_available.return_value = True
    m.is_rate_limit_error.return_value = False
    m.generate_full = AsyncMock(return_value=FIXTURE_CV_JSON)
    return m


async def test_groq_rate_limit_falls_back_to_ollama(monkeypatch, mock_export):
    """When Groq returns rate limit, inference_service falls back to Ollama."""
    import services.inference_service as svc
    from fastapi import HTTPException

    ollama_m = _make_succeeding_ollama()
    groq_m = _make_rate_limit_groq()
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq_m, "ollama": ollama_m})

    text, provider, model = await svc.generate_full_response("cv", "sys", "user")
    assert provider == "ollama"
    assert text == FIXTURE_CV_JSON


async def test_both_providers_fail_raises_503(monkeypatch):
    """When all providers fail, generate_full_response raises 503."""
    import services.inference_service as svc
    from fastapi import HTTPException

    groq_m = MagicMock()
    groq_m.is_available.return_value = True
    groq_m.is_rate_limit_error.return_value = False
    groq_m.generate_full = AsyncMock(side_effect=RuntimeError("groq down"))

    ollama_m = MagicMock()
    ollama_m.is_available.return_value = True
    ollama_m.is_rate_limit_error.return_value = False
    ollama_m.generate_full = AsyncMock(side_effect=RuntimeError("ollama down"))

    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq_m, "ollama": ollama_m})

    with pytest.raises(HTTPException) as exc_info:
        await svc.generate_full_response("cv", "sys", "user")
    assert exc_info.value.status_code == 503


async def test_provider_used_header_shows_actual_provider(client, valid_sk_key, mock_export, monkeypatch):
    """X-Provider-Used header reflects which provider actually served the request."""
    import services.cv_service as cv_svc

    async def fake_inference(task, sys_prompt, user_prompt, **kwargs):
        return (FIXTURE_CV_JSON, "ollama", "llama3.1")

    monkeypatch.setattr(cv_svc, "_inference_full", fake_inference)
    from services import output_validator as ov
    monkeypatch.setattr(ov, "validate_and_parse_cv",
                        AsyncMock(return_value=__import__("json").loads(FIXTURE_CV_JSON)))

    resp = await client.post(
        "/v1/cv/generate",
        json=VALID_CV_PAYLOAD,
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 200
    assert resp.headers.get("x-provider-used") == "ollama"
    assert resp.headers.get("x-model-used") == "llama3.1"


async def test_security_event_logged_on_provider_failure(monkeypatch):
    """A security event is logged when a provider raises an error."""
    import services.inference_service as svc

    logged = []

    def fake_log(severity, event_type, details):
        logged.append(event_type)

    monkeypatch.setattr("services.inference_service.log_security_event", fake_log)

    groq_m = MagicMock()
    groq_m.is_available.return_value = True
    groq_m.is_rate_limit_error.return_value = False
    groq_m.generate_full = AsyncMock(side_effect=RuntimeError("timeout"))

    ollama_m = MagicMock()
    ollama_m.is_available.return_value = True
    ollama_m.is_rate_limit_error.return_value = False
    ollama_m.generate_full = AsyncMock(return_value=FIXTURE_CV_JSON)

    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq_m, "ollama": ollama_m})

    await svc.generate_full_response("cv", "sys", "user")
    assert "provider_error" in logged
