import pytest
from services.providers.nvidia_provider import NvidiaProvider


@pytest.fixture
def provider():
    return NvidiaProvider()


def test_is_available_false_when_key_empty(provider, monkeypatch):
    monkeypatch.setattr("config.settings.NVIDIA_API_KEY", "")
    assert provider.is_available() is False


def test_is_available_true_when_key_set(provider, monkeypatch):
    monkeypatch.setattr("config.settings.NVIDIA_API_KEY", "nvapi-test-key")
    assert provider.is_available() is True


def test_is_rate_limit_error_429(provider):
    err = Exception("HTTP 429 Too Many Requests")
    assert provider.is_rate_limit_error(err) is True


def test_is_rate_limit_error_false(provider):
    err = Exception("Connection refused")
    assert provider.is_rate_limit_error(err) is False


def test_client_uses_nvidia_base_url(provider, monkeypatch):
    monkeypatch.setattr("config.settings.NVIDIA_API_KEY", "nvapi-test-key")
    monkeypatch.setattr("config.settings.NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    client = provider._client()
    assert "nvidia" in str(client.base_url)
