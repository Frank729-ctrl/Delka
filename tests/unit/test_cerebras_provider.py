import pytest
from services.providers.cerebras_provider import CerebrasProvider


@pytest.fixture
def provider():
    return CerebrasProvider()


def test_is_available_false_when_key_empty(provider, monkeypatch):
    monkeypatch.setattr("config.settings.CEREBRAS_API_KEY", "")
    assert provider.is_available() is False


def test_is_available_true_when_key_set(provider, monkeypatch):
    monkeypatch.setattr("config.settings.CEREBRAS_API_KEY", "csk-test-key")
    assert provider.is_available() is True


def test_is_rate_limit_error_429(provider):
    err = Exception("rate limit exceeded 429")
    assert provider.is_rate_limit_error(err) is True


def test_client_uses_cerebras_base_url(provider, monkeypatch):
    monkeypatch.setattr("config.settings.CEREBRAS_API_KEY", "csk-test-key")
    client = provider._client()
    assert "cerebras" in str(client.base_url)
