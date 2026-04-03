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
        raw = (response.choices[0].message.content or "").strip()

        # NIM models sometimes return JSON instead of a bare label.
        # e.g. '{"user safety": "safe", "safety categories": {...}}'
        # Parse JSON and extract the verdict from known fields.
        import json as _json
        try:
            data = _json.loads(raw)
            if isinstance(data, dict):
                # Primary field used by nemoguard
                user_safety = str(data.get("user safety", "")).lower()
                if user_safety == "safe":
                    return True, ""
                if user_safety in ("unsafe", "blocked"):
                    cats = data.get("safety categories", {})
                    category = next(
                        (k for k, v in cats.items() if str(v).lower() == "true"),
                        "unsafe",
                    ) if isinstance(cats, dict) else "unsafe"
                    return False, category
        except (_json.JSONDecodeError, TypeError):
            pass

        verdict = raw.upper()
        if not verdict or verdict == "SAFE" or "safe" in verdict.lower():
            return True, ""
        return False, raw.lower()
    except Exception:
        # NVIDIA unavailable — fail open (local moderator still runs separately)
        return True, ""
