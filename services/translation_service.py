"""
Translation service — uses Groq/Gemini LLM for translation.
NVIDIA nllb-200 as secondary if available.
"""
from config import settings


_SYSTEM_PROMPT = (
    "You are a professional translator. Translate the user's text accurately. "
    "Return ONLY the translated text — no explanations, no labels, no commentary."
)


async def translate(text: str, source_lang: str = "auto", target_lang: str = "en") -> tuple[str, str, str]:
    """
    Returns (translated_text, detected_source_lang, provider_name).
    """
    user_prompt = (
        f"Translate the following text to {target_lang}."
        + (f" The source language is {source_lang}." if source_lang != "auto" else "")
        + f"\n\nText:\n{text}"
    )

    # Try Gemini first (quality)
    if settings.GOOGLE_API_KEY:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=settings.GOOGLE_API_KEY,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
            response = await client.chat.completions.create(
                model="gemini-2.5-pro",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=4096,
            )
            translated = response.choices[0].message.content or ""
            return translated.strip(), source_lang, "gemini"
        except Exception:
            pass

    # Groq fallback
    if settings.GROQ_API_KEY:
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=settings.GROQ_API_KEY)
            response = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=4096,
            )
            translated = response.choices[0].message.content or ""
            return translated.strip(), source_lang, "groq"
        except Exception:
            pass

    return "", source_lang, "unavailable"
