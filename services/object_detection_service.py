"""
Object detection service — uses NVIDIA neva (multimodal) to describe and
identify objects in images. Returns structured detection results.
"""
import re
from config import settings


async def detect_objects(
    image_url: str = "",
    image_base64: str = "",
    confidence_threshold: float = 0.5,
) -> tuple[list[dict], str, str]:
    """
    Returns (objects_list, raw_description, provider_name).
    objects_list: [{"label": str, "confidence": float, "description": str}]
    """
    if not image_url and not image_base64:
        return [], "", "none"

    # Build image content
    if image_url:
        image_content = {"type": "image_url", "image_url": {"url": image_url}}
    else:
        image_content = {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
        }

    detect_prompt = (
        "List all objects, people, and elements visible in this image. "
        "For each item, format as: OBJECT: <name> | CONFIDENCE: <high/medium/low> | DESCRIPTION: <brief>\n"
        "List every distinct object on a separate line."
    )

    messages = [
        {
            "role": "user",
            "content": [
                image_content,
                {"type": "text", "text": detect_prompt},
            ],
        }
    ]

    raw = ""
    provider = "unavailable"

    # Try NVIDIA neva
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
                max_tokens=1024,
                temperature=0.1,
            )
            raw = response.choices[0].message.content or ""
            provider = "nvidia"
        except Exception:
            pass

    # Fallback: Groq vision
    if not raw and settings.GROQ_API_KEY:
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=settings.GROQ_API_KEY)
            response = await client.chat.completions.create(
                model=settings.VISION_PRIMARY_MODEL,
                messages=messages,
                max_tokens=1024,
                temperature=0.1,
            )
            raw = response.choices[0].message.content or ""
            provider = "groq"
        except Exception:
            pass

    # Parse the structured output
    objects = []
    conf_map = {"high": 0.9, "medium": 0.65, "low": 0.4}
    for line in raw.splitlines():
        m = re.match(
            r"OBJECT:\s*(.+?)\s*\|\s*CONFIDENCE:\s*(\w+)\s*\|\s*DESCRIPTION:\s*(.+)",
            line, re.IGNORECASE
        )
        if m:
            label, conf_str, description = m.group(1), m.group(2).lower(), m.group(3)
            score = conf_map.get(conf_str, 0.5)
            if score >= confidence_threshold:
                objects.append({"label": label, "confidence": score, "description": description})

    return objects, raw, provider
