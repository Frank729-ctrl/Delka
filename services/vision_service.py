import httpx
from fastapi import HTTPException
from security.security_logger import log_security_event
from services.providers.vision_groq_provider import VisionGroqProvider
from services.providers.vision_ollama_provider import VisionOllamaProvider

VISION_PROVIDERS = {
    "groq": VisionGroqProvider(),
    "ollama": VisionOllamaProvider(),
}


async def analyze_image(image_base64: str) -> dict:
    from config import settings

    chain = [
        {"provider": settings.VISION_PRIMARY_PROVIDER,
         "model": settings.VISION_PRIMARY_MODEL},
        {"provider": settings.VISION_FALLBACK_PROVIDER,
         "model": settings.VISION_FALLBACK_MODEL},
    ]

    for entry in chain:
        provider_name = entry["provider"]
        model = entry["model"]
        provider = VISION_PROVIDERS.get(provider_name)
        if provider is None or not provider.is_available():
            continue
        try:
            return await provider.analyze_image(image_base64, model)
        except Exception as e:
            event = "provider_rate_limited" if provider.is_rate_limit_error(e) \
                else "provider_error"
            log_security_event(
                severity="WARNING",
                event_type=event,
                details={"task": "vision", "provider": provider_name,
                         "error": str(e)[:200]},
            )
            continue

    raise HTTPException(
        status_code=503,
        detail="All vision providers unavailable. Try again later.",
    )


async def fetch_image_as_base64(url: str) -> str:
    import base64
    from config import settings

    max_bytes = settings.VISION_MAX_IMAGE_SIZE_MB * 1024 * 1024
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                raise HTTPException(
                    status_code=400,
                    detail=f"URL did not return an image (got {content_type})",
                )
            raw = resp.content
            if len(raw) > max_bytes:
                raise HTTPException(
                    status_code=400,
                    detail=f"Image exceeds {settings.VISION_MAX_IMAGE_SIZE_MB}MB limit",
                )
            return base64.b64encode(raw).decode("utf-8")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch image: {e}")


def prepare_image_input(item) -> str:
    """
    Returns base64 string from either image_base64 or image_url field.
    Raises HTTPException 400 if neither is provided.
    """
    import asyncio

    if hasattr(item, "image") and item.image:
        return item.image
    if hasattr(item, "image_base64") and item.image_base64:
        return item.image_base64

    image_url = getattr(item, "image_url", "")
    if image_url:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're already in an async context — caller should await fetch directly
            raise _NeedsAsyncFetch(image_url)
        return loop.run_until_complete(fetch_image_as_base64(image_url))

    raise HTTPException(
        status_code=400,
        detail="Provide either 'image' (base64) or 'image_url'",
    )


class _NeedsAsyncFetch(Exception):
    def __init__(self, url: str):
        self.url = url


async def get_image_base64(item) -> str:
    """Async version — always use this inside async endpoints/services."""
    if hasattr(item, "image") and item.image:
        return item.image
    if hasattr(item, "image_base64") and item.image_base64:
        return item.image_base64
    image_url = getattr(item, "image_url", "")
    if image_url:
        return await fetch_image_as_base64(image_url)
    raise HTTPException(
        status_code=400,
        detail="Provide either 'image' (base64) or 'image_url'",
    )
