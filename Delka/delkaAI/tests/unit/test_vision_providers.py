"""Unit tests for vision provider base, groq, and ollama providers."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Base provider ────────────────────────────────────────────────────────────

def _make_base_instance():
    """Create a concrete subclass of VisionBaseProvider for testing base methods."""
    from services.providers.vision_base_provider import VisionBaseProvider
    T = type("_TestProvider", (VisionBaseProvider,), {
        "analyze_image": lambda *a, **kw: None,
        "is_available": lambda *a: True,
        "is_rate_limit_error": lambda *a: False,
    })
    return T()


def test_fallback_analysis_returns_dict():
    p = _make_base_instance()
    result = p._fallback_analysis()
    assert result["category"] == "Unknown"
    assert result["confidence"] == 0.0
    assert isinstance(result["colors"], list)


def test_parse_json_response_valid():
    p = _make_base_instance()
    raw = json.dumps({
        "category": "Electronics",
        "colors": ["black", "silver"],
        "material": "plastic",
        "shape": "rectangular",
        "brand_text": "Sony",
        "style": "modern",
        "attributes": ["wireless"],
        "description": "A headset",
        "confidence": 0.9,
    })
    result = p._parse_json_response(raw)
    assert result["category"] == "Electronics"
    assert result["confidence"] == 0.9


def test_parse_json_response_strips_markdown_fences():
    p = _make_base_instance()
    raw = '```json\n{"category": "Clothing", "colors": [], "material": "", "shape": "", "brand_text": "", "style": "", "attributes": [], "description": "A shirt", "confidence": 0.8}\n```'
    result = p._parse_json_response(raw)
    assert result["category"] == "Clothing"


def test_parse_json_response_returns_fallback_on_invalid():
    p = _make_base_instance()
    result = p._parse_json_response("this is not json at all")
    assert result["category"] == "Unknown"
    assert result["confidence"] == 0.0


# ── Groq provider ─────────────────────────────────────────────────────────────

def test_groq_provider_is_available_with_key():
    from services.providers.vision_groq_provider import VisionGroqProvider
    p = VisionGroqProvider()
    with patch("config.settings.GROQ_API_KEY", "test-key"):
        assert p.is_available() is True


def test_groq_provider_not_available_without_key():
    from services.providers.vision_groq_provider import VisionGroqProvider
    p = VisionGroqProvider()
    with patch("config.settings.GROQ_API_KEY", ""):
        assert p.is_available() is False


def test_groq_provider_rate_limit_detection():
    from services.providers.vision_groq_provider import VisionGroqProvider
    p = VisionGroqProvider()
    assert p.is_rate_limit_error(Exception("429 rate limit")) is True
    assert p.is_rate_limit_error(Exception("connection refused")) is False


@pytest.mark.asyncio
async def test_groq_provider_analyze_image_success():
    from services.providers.vision_groq_provider import VisionGroqProvider
    p = VisionGroqProvider()

    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "category": "Electronics", "colors": ["black"], "material": "plastic",
        "shape": "rect", "brand_text": "", "style": "modern",
        "attributes": [], "description": "A device", "confidence": 0.9,
    })
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("config.settings.GROQ_API_KEY", "test-key"), \
         patch("groq.AsyncGroq", return_value=mock_client):
        result = await p.analyze_image("base64data", "llama-4-scout")

    assert result["category"] == "Electronics"


@pytest.mark.asyncio
async def test_groq_provider_analyze_image_raises_on_api_error():
    from services.providers.vision_groq_provider import VisionGroqProvider
    p = VisionGroqProvider()
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

    with patch("config.settings.GROQ_API_KEY", "test-key"), \
         patch("groq.AsyncGroq", return_value=mock_client):
        with pytest.raises(Exception, match="API error"):
            await p.analyze_image("base64data", "llama-4-scout")


# ── Ollama provider ───────────────────────────────────────────────────────────

def test_ollama_provider_is_available_with_url():
    from services.providers.vision_ollama_provider import VisionOllamaProvider
    p = VisionOllamaProvider()
    with patch("config.settings.OLLAMA_BASE_URL", "http://localhost:11434"):
        assert p.is_available() is True


def test_ollama_provider_rate_limit_always_false():
    from services.providers.vision_ollama_provider import VisionOllamaProvider
    p = VisionOllamaProvider()
    assert p.is_rate_limit_error(Exception("anything")) is False


@pytest.mark.asyncio
async def test_ollama_provider_analyze_image_success():
    from services.providers.vision_ollama_provider import VisionOllamaProvider
    p = VisionOllamaProvider()

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "response": json.dumps({
            "category": "Clothing", "colors": ["red"], "material": "cotton",
            "shape": "flat", "brand_text": "", "style": "casual",
            "attributes": [], "description": "A t-shirt", "confidence": 0.85,
        })
    }
    mock_resp.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("config.settings.OLLAMA_BASE_URL", "http://localhost:11434"), \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        result = await p.analyze_image("base64data", "llava:13b")

    assert result["category"] == "Clothing"
