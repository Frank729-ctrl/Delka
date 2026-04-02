"""
NVIDIA NIM safety layer — uses llama-3.1-nemoguard-8b-content-safety to
evaluate content. Falls back to local content_moderator if NVIDIA unavailable.
Returns (is_safe: bool, category: str).
"""
from config import settings


async def nvidia_safety_check(text: str) -> tuple[bool, str]:
    """
    Returns (is_safe, category).
    category is empty string when safe.
    """
    if not settings.NVIDIA_API_KEY or not text.strip():
        return True, ""

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.NVIDIA_API_KEY,
            base_url=settings.NVIDIA_BASE_URL,
        )
        response = await client.chat.completions.create(
            model=settings.NVIDIA_SAFETY_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Classify this content. Reply with ONLY ONE of: "
                        "SAFE, VIOLENCE, HATE, SEXUAL, SELF_HARM, ILLEGAL\n\n"
                        f"Content: {text[:1000]}"
                    ),
                }
            ],
            max_tokens=10,
            temperature=0.0,
        )
        verdict = (response.choices[0].message.content or "").strip().upper()
        if verdict == "SAFE" or not verdict:
            return True, ""
        return False, verdict.lower()
    except Exception:
        # NVIDIA unavailable — fail open (local moderator still runs separately)
        return True, ""
