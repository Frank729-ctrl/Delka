"""
OCR service — uses NVIDIA neva-22b (multimodal) via the OpenAI-compatible API.
Accepts image URL or base64-encoded image.
"""
import base64
import httpx
from config import settings


async def extract_text(image_url: str = "", image_base64: str = "", prompt: str = "") -> tuple[str, str]:
    """
    Returns (extracted_text, provider_name).
    Tries NVIDIA neva → falls back to Groq llama4-scout vision.
    """
    if not prompt:
        prompt = "Extract all text from this image accurately. Return only the text, no commentary."

    # Build image content block
    if image_url:
        image_content = {"type": "image_url", "image_url": {"url": image_url}}
    elif image_base64:
        image_content = {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
        }
    else:
        return "", "none"

    messages = [
        {
            "role": "user",
            "content": [
                image_content,
                {"type": "text", "text": prompt},
            ],
        }
    ]

    # Try NVIDIA neva first
    if settings.NVIDIA_API_KEY:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=settings.NVIDIA_API_KEY,
                base_url=settings.NVIDIA_BASE_URL,
            )
            response = await client.chat.completions.create(
                model=settings.NVIDIA_OCR_MODEL,
                messages=messages,
                max_tokens=2048,
                temperature=0.1,
            )
            return response.choices[0].message.content or "", "nvidia"
        except Exception:
            pass

    # Fallback: Groq llama4-scout (vision-capable)
    if settings.GROQ_API_KEY:
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=settings.GROQ_API_KEY)
            response = await client.chat.completions.create(
                model=settings.VISION_PRIMARY_MODEL,
                messages=messages,
                max_tokens=2048,
                temperature=0.1,
            )
            return response.choices[0].message.content or "", "groq"
        except Exception:
            pass

    return "", "unavailable"
