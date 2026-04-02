import pytest
from services.providers.gemini_provider import GeminiProvider


@pytest.fixture
def provider():
    return GeminiProvider()


def test_is_available_false_when_key_empty(provider, monkeypatch):
    monkeypatch.setattr("config.settings.GOOGLE_API_KEY", "")
    assert provider.is_available() is False


def test_is_available_true_when_key_set(provider, monkeypatch):
    monkeypatch.setattr("config.settings.GOOGLE_API_KEY", "AIzaSy-test-key")
    assert provider.is_available() is True


def test_is_rate_limit_error_quota(provider):
    err = Exception("quota exceeded 429")
    assert provider.is_rate_limit_error(err) is True


def test_is_rate_limit_error_false(provider):
    err = Exception("Internal server error")
    assert provider.is_rate_limit_error(err) is False


def test_client_uses_gemini_base_url(provider, monkeypatch):
    monkeypatch.setattr("config.settings.GOOGLE_API_KEY", "AIzaSy-test-key")
    client = provider._client()
    assert "generativelanguage" in str(client.base_url)
