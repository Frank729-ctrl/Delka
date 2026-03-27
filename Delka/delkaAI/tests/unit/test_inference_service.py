import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_groq(available=True, response="ok", rate_limit=False, error=None):
    """Build a mock GroqProvider."""
    m = MagicMock()
    m.is_available.return_value = available
    if error:
        m.is_rate_limit_error.return_value = rate_limit
        m.generate_full = AsyncMock(side_effect=error)
        m.generate_stream = AsyncMock(side_effect=error)
    else:
        m.is_rate_limit_error.return_value = False
        m.generate_full = AsyncMock(return_value=response)
    return m


def _make_ollama(available=True, response="fallback_ok"):
    m = MagicMock()
    m.is_available.return_value = available
    m.is_rate_limit_error.return_value = False
    m.generate_full = AsyncMock(return_value=response)
    return m


# ── generate_full_response tests ─────────────────────────────────────────────

async def test_cv_task_uses_groq_when_key_set(monkeypatch):
    import services.inference_service as svc
    groq = _make_groq(response="cv_output")
    ollama = _make_ollama()
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": ollama})
    monkeypatch.setattr("config.settings.GROQ_API_KEY", "test-key")

    text, provider, model = await svc.generate_full_response("cv", "sys", "user")

    assert provider == "groq"
    assert model == svc.get_task_chain("cv")[0]["model"]
    assert text == "cv_output"
    groq.generate_full.assert_awaited_once()


async def test_cv_task_uses_correct_model(monkeypatch):
    import services.inference_service as svc
    from config import settings
    groq = _make_groq(response="out")
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": _make_ollama()})

    _, _, model = await svc.generate_full_response("cv", "s", "u")
    assert model == settings.CV_PRIMARY_MODEL


async def test_letter_task_uses_correct_model(monkeypatch):
    import services.inference_service as svc
    from config import settings
    groq = _make_groq(response="letter_out")
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": _make_ollama()})

    _, _, model = await svc.generate_full_response("letter", "s", "u")
    assert model == settings.LETTER_PRIMARY_MODEL


async def test_support_task_uses_correct_model(monkeypatch):
    import services.inference_service as svc
    from config import settings
    groq = _make_groq(response="chat")
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": _make_ollama()})

    _, _, model = await svc.generate_full_response("support", "s", "u")
    assert model == settings.SUPPORT_PRIMARY_MODEL


async def test_returns_tuple_of_text_provider_model(monkeypatch):
    import services.inference_service as svc
    groq = _make_groq(response="hello")
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": _make_ollama()})

    result = await svc.generate_full_response("cv", "s", "u")
    assert isinstance(result, tuple)
    assert len(result) == 3
    text, provider, model = result
    assert isinstance(text, str)
    assert isinstance(provider, str)
    assert isinstance(model, str)


async def test_falls_back_to_ollama_on_rate_limit(monkeypatch):
    import services.inference_service as svc
    exc = Exception("429 rate_limit exceeded")
    groq = _make_groq(error=exc, rate_limit=True)
    ollama = _make_ollama(response="fallback_text")
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": ollama})

    text, provider, model = await svc.generate_full_response("cv", "s", "u")
    assert provider == "ollama"
    assert text == "fallback_text"


async def test_falls_back_to_ollama_on_generic_error(monkeypatch):
    import services.inference_service as svc
    groq = _make_groq(error=RuntimeError("connection failed"), rate_limit=False)
    ollama = _make_ollama(response="fallback_text")
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": ollama})

    text, provider, _ = await svc.generate_full_response("cv", "s", "u")
    assert provider == "ollama"
    assert text == "fallback_text"


async def test_raises_503_when_all_providers_fail(monkeypatch):
    import services.inference_service as svc
    groq = _make_groq(error=RuntimeError("down"))
    ollama = _make_ollama()
    ollama.generate_full = AsyncMock(side_effect=RuntimeError("also down"))
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": ollama})

    with pytest.raises(HTTPException) as exc_info:
        await svc.generate_full_response("cv", "s", "u")
    assert exc_info.value.status_code == 503


async def test_skips_groq_when_api_key_empty(monkeypatch):
    import services.inference_service as svc
    groq = _make_groq(available=False)
    ollama = _make_ollama(response="ollama_result")
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": ollama})

    text, provider, _ = await svc.generate_full_response("cv", "s", "u")
    assert provider == "ollama"
    groq.generate_full.assert_not_awaited()


async def test_logs_warning_on_rate_limit(monkeypatch):
    import services.inference_service as svc
    logged = []

    def fake_log(severity, event_type, details):
        logged.append({"severity": severity, "event_type": event_type})

    monkeypatch.setattr("services.inference_service.log_security_event", fake_log)
    exc = Exception("429 rate_limit")
    groq = _make_groq(error=exc, rate_limit=True)
    ollama = _make_ollama()
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": ollama})

    await svc.generate_full_response("cv", "s", "u")
    assert any(e["event_type"] == "provider_rate_limited" for e in logged)
    assert any(e["severity"] == "WARNING" for e in logged)


async def test_logs_warning_on_provider_error(monkeypatch):
    import services.inference_service as svc
    logged = []

    def fake_log(severity, event_type, details):
        logged.append({"severity": severity, "event_type": event_type})

    monkeypatch.setattr("services.inference_service.log_security_event", fake_log)
    groq = _make_groq(error=RuntimeError("boom"), rate_limit=False)
    ollama = _make_ollama()
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": ollama})

    await svc.generate_full_response("cv", "s", "u")
    assert any(e["event_type"] == "provider_error" for e in logged)


async def test_unknown_provider_name_skips_and_logs_warning(monkeypatch):
    """Provider name not in PROVIDER_INSTANCES logs provider_unknown and continues."""
    import services.inference_service as svc
    logged = []

    def fake_log(severity, event_type, details):
        logged.append(event_type)

    monkeypatch.setattr("services.inference_service.log_security_event", fake_log)
    # Override task chain to use a non-existent provider name
    monkeypatch.setattr(svc, "get_task_chain",
                        lambda task: [{"provider": "nonexistent", "model": "x"},
                                      {"provider": "ollama", "model": "llama3.1"}])
    ollama = _make_ollama(response="from_ollama")
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"ollama": ollama})

    text, provider, _ = await svc.generate_full_response("cv", "s", "u")
    assert provider == "ollama"
    assert "provider_unknown" in logged


async def test_provider_is_available_false_skips(monkeypatch):
    """Provider with is_available()=False is skipped without calling generate."""
    import services.inference_service as svc
    groq = _make_groq(available=False)
    ollama = _make_ollama(response="from_ollama")
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": ollama})

    text, provider, _ = await svc.generate_full_response("cv", "s", "u")
    assert provider == "ollama"
    groq.generate_full.assert_not_awaited()


async def test_unknown_task_falls_back_to_support_chain(monkeypatch):
    """Unknown task name falls back to support chain."""
    import services.inference_service as svc
    groq = _make_groq(response="support_output")
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": _make_ollama()})

    chain = svc.get_task_chain("unknown_task_xyz")
    # Should return support chain (the default)
    from config import settings
    assert chain[0]["model"] == settings.SUPPORT_PRIMARY_MODEL


# ── generate_stream_response tests ───────────────────────────────────────────

async def test_generate_stream_yields_tokens(monkeypatch):
    """generate_stream_response yields tokens from a successful provider."""
    import services.inference_service as svc

    async def fake_stream(messages, model, temperature=0.8):
        for token in ["Hello", " World"]:
            yield token

    groq = MagicMock()
    groq.is_available.return_value = True
    groq.is_rate_limit_error.return_value = False
    groq.generate_stream = fake_stream
    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": _make_ollama()})

    tokens = []
    async for token in svc.generate_stream_response("support", [{"role": "user", "content": "hi"}]):
        tokens.append(token)

    assert "Hello" in tokens
    assert " World" in tokens


async def test_generate_stream_falls_back_on_rate_limit(monkeypatch):
    """generate_stream_response falls back when first provider is rate limited."""
    import services.inference_service as svc

    async def fail_stream(messages, model, temperature=0.8):
        raise Exception("429 rate_limit")
        yield  # make it a generator

    groq = MagicMock()
    groq.is_available.return_value = True
    groq.is_rate_limit_error.return_value = True
    groq.generate_stream = fail_stream

    async def ok_stream(messages, model, temperature=0.8):
        yield "fallback_token"

    ollama = MagicMock()
    ollama.is_available.return_value = True
    ollama.is_rate_limit_error.return_value = False
    ollama.generate_stream = ok_stream

    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": ollama})

    tokens = []
    async for token in svc.generate_stream_response("support", [{"role": "user", "content": "hi"}]):
        tokens.append(token)

    assert "fallback_token" in tokens


async def test_generate_stream_yields_error_when_all_fail(monkeypatch):
    """generate_stream_response yields 'data: [ERROR]' when all providers fail."""
    import services.inference_service as svc

    async def fail_stream(messages, model, temperature=0.8):
        raise RuntimeError("down")
        yield

    groq = MagicMock()
    groq.is_available.return_value = True
    groq.is_rate_limit_error.return_value = False
    groq.generate_stream = fail_stream

    ollama = MagicMock()
    ollama.is_available.return_value = True
    ollama.is_rate_limit_error.return_value = False
    ollama.generate_stream = fail_stream

    monkeypatch.setattr(svc, "PROVIDER_INSTANCES", {"groq": groq, "ollama": ollama})

    tokens = []
    async for token in svc.generate_stream_response("support", [{"role": "user", "content": "hi"}]):
        tokens.append(token)

    assert any("[ERROR]" in t for t in tokens)
