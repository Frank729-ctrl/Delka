"""Unit tests for services/vision_service.py."""
import base64
import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from PIL import Image as PILImage


def _blank_b64() -> str:
    img = PILImage.new("RGB", (10, 10), color=(100, 100, 100))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


_GOOD_ANALYSIS = {
    "category": "Electronics",
    "colors": ["black"],
    "material": "plastic",
    "shape": "rectangular",
    "brand_text": "Sony",
    "style": "modern",
    "attributes": ["wireless"],
    "description": "A wireless headset",
    "confidence": 0.95,
}


@pytest.mark.asyncio
async def test_analyze_image_calls_primary_provider():
    from services import vision_service
    mock_provider = MagicMock()
    mock_provider.is_available.return_value = True
    mock_provider.analyze_image = AsyncMock(return_value=_GOOD_ANALYSIS)

    with patch.dict(vision_service.VISION_PROVIDERS, {"groq": mock_provider}), \
         patch("config.settings.VISION_PRIMARY_PROVIDER", "groq"), \
         patch("config.settings.VISION_PRIMARY_MODEL", "llama-4-scout"), \
         patch("config.settings.VISION_FALLBACK_PROVIDER", "ollama"), \
         patch("config.settings.VISION_FALLBACK_MODEL", "llava:13b"):
        result = await vision_service.analyze_image(_blank_b64())
    assert result["category"] == "Electronics"
    mock_provider.analyze_image.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_image_falls_back_on_rate_limit():
    from services import vision_service
    primary = MagicMock()
    primary.is_available.return_value = True
    primary.is_rate_limit_error.return_value = True
    primary.analyze_image = AsyncMock(side_effect=Exception("429 rate limit"))

    fallback = MagicMock()
    fallback.is_available.return_value = True
    fallback.is_rate_limit_error.return_value = False
    fallback.analyze_image = AsyncMock(return_value=_GOOD_ANALYSIS)

    with patch.dict(vision_service.VISION_PROVIDERS, {"groq": primary, "ollama": fallback}), \
         patch("config.settings.VISION_PRIMARY_PROVIDER", "groq"), \
         patch("config.settings.VISION_PRIMARY_MODEL", "llama-4-scout"), \
         patch("config.settings.VISION_FALLBACK_PROVIDER", "ollama"), \
         patch("config.settings.VISION_FALLBACK_MODEL", "llava:13b"):
        result = await vision_service.analyze_image(_blank_b64())
    assert result["category"] == "Electronics"
    fallback.analyze_image.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_image_falls_back_on_generic_error():
    from services import vision_service
    primary = MagicMock()
    primary.is_available.return_value = True
    primary.is_rate_limit_error.return_value = False
    primary.analyze_image = AsyncMock(side_effect=Exception("connection error"))

    fallback = MagicMock()
    fallback.is_available.return_value = True
    fallback.is_rate_limit_error.return_value = False
    fallback.analyze_image = AsyncMock(return_value=_GOOD_ANALYSIS)

    with patch.dict(vision_service.VISION_PROVIDERS, {"groq": primary, "ollama": fallback}), \
         patch("config.settings.VISION_PRIMARY_PROVIDER", "groq"), \
         patch("config.settings.VISION_PRIMARY_MODEL", "llama-4-scout"), \
         patch("config.settings.VISION_FALLBACK_PROVIDER", "ollama"), \
         patch("config.settings.VISION_FALLBACK_MODEL", "llava:13b"):
        result = await vision_service.analyze_image(_blank_b64())
    assert result == _GOOD_ANALYSIS


@pytest.mark.asyncio
async def test_analyze_image_raises_503_when_all_fail():
    from services import vision_service
    bad = MagicMock()
    bad.is_available.return_value = True
    bad.is_rate_limit_error.return_value = False
    bad.analyze_image = AsyncMock(side_effect=Exception("down"))

    with patch.dict(vision_service.VISION_PROVIDERS, {"groq": bad, "ollama": bad}), \
         patch("config.settings.VISION_PRIMARY_PROVIDER", "groq"), \
         patch("config.settings.VISION_PRIMARY_MODEL", "llama-4-scout"), \
         patch("config.settings.VISION_FALLBACK_PROVIDER", "ollama"), \
         patch("config.settings.VISION_FALLBACK_MODEL", "llava:13b"):
        with pytest.raises(HTTPException) as exc_info:
            await vision_service.analyze_image(_blank_b64())
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_fetch_image_as_base64_rejects_oversized(respx_mock=None):
    from services import vision_service
    big_bytes = b"x" * (11 * 1024 * 1024)  # 11MB

    mock_resp = MagicMock()
    mock_resp.headers = {"content-type": "image/jpeg"}
    mock_resp.content = big_bytes
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch("config.settings.VISION_MAX_IMAGE_SIZE_MB", 10):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_ctx
        with pytest.raises(HTTPException) as exc_info:
            await vision_service.fetch_image_as_base64("http://example.com/big.jpg")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_get_image_base64_accepts_base64_field():
    from services import vision_service
    b64 = _blank_b64()
    item = MagicMock()
    item.image = b64
    item.image_base64 = ""
    item.image_url = ""
    result = await vision_service.get_image_base64(item)
    assert result == b64


@pytest.mark.asyncio
async def test_get_image_base64_fetches_url():
    from services import vision_service
    b64 = _blank_b64()
    item = MagicMock()
    item.image = ""
    item.image_base64 = ""
    item.image_url = "http://example.com/img.jpg"
    with patch.object(vision_service, "fetch_image_as_base64", AsyncMock(return_value=b64)):
        result = await vision_service.get_image_base64(item)
    assert result == b64


@pytest.mark.asyncio
async def test_get_image_base64_raises_400_when_neither_provided():
    from services import vision_service
    item = MagicMock()
    item.image = ""
    item.image_base64 = ""
    item.image_url = ""
    with pytest.raises(HTTPException) as exc_info:
        await vision_service.get_image_base64(item)
    assert exc_info.value.status_code == 400
