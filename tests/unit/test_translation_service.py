import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_translate_returns_text_from_gemini():
    from unittest.mock import MagicMock
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "Bonjour le monde"

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("openai.AsyncOpenAI", return_value=mock_client), \
         patch("config.settings.GOOGLE_API_KEY", "fake-key"):
        from services.translation_service import translate
        translated, source, provider = await translate(
            text="Hello world", target_lang="fr"
        )
    assert translated == "Bonjour le monde"
    assert provider == "gemini"


@pytest.mark.asyncio
async def test_translate_returns_unavailable_when_no_keys(monkeypatch):
    monkeypatch.setattr("config.settings.GOOGLE_API_KEY", "")
    monkeypatch.setattr("config.settings.GROQ_API_KEY", "")
    from services.translation_service import translate
    translated, source, provider = await translate(text="Hello", target_lang="fr")
    assert provider == "unavailable"
    assert translated == ""
