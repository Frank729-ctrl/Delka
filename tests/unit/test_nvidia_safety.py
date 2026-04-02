import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_nvidia_safety_no_key_returns_safe(monkeypatch):
    monkeypatch.setattr("config.settings.NVIDIA_API_KEY", "")
    from security.nvidia_safety import nvidia_safety_check
    is_safe, category = await nvidia_safety_check("some text")
    assert is_safe is True
    assert category == ""


@pytest.mark.asyncio
async def test_nvidia_safety_safe_verdict(monkeypatch):
    monkeypatch.setattr("config.settings.NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setattr("config.settings.NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setattr("config.settings.NVIDIA_SAFETY_MODEL", "nvidia/llama-3.1-nemoguard-8b-content-safety")

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "SAFE"

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        from security.nvidia_safety import nvidia_safety_check
        is_safe, category = await nvidia_safety_check("Help me write a CV")

    assert is_safe is True
    assert category == ""


@pytest.mark.asyncio
async def test_nvidia_safety_unsafe_verdict(monkeypatch):
    monkeypatch.setattr("config.settings.NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setattr("config.settings.NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setattr("config.settings.NVIDIA_SAFETY_MODEL", "nvidia/llama-3.1-nemoguard-8b-content-safety")

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "VIOLENCE"

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        from security.nvidia_safety import nvidia_safety_check
        is_safe, category = await nvidia_safety_check("violent content here")

    assert is_safe is False
    assert category == "violence"


@pytest.mark.asyncio
async def test_nvidia_safety_fails_open_on_exception(monkeypatch):
    monkeypatch.setattr("config.settings.NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setattr("config.settings.NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setattr("config.settings.NVIDIA_SAFETY_MODEL", "test-model")

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("timeout"))

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        from security.nvidia_safety import nvidia_safety_check
        is_safe, category = await nvidia_safety_check("some text")

    # Fail open — never block on provider error
    assert is_safe is True
