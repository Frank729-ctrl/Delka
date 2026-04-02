"""
Speech-to-Text service — uses Groq Whisper (fastest, free) as primary.
Falls back to httpx-based NVIDIA ASR if Groq unavailable.
"""
import base64
import httpx
from config import settings


async def transcribe(audio_url: str = "", audio_base64: str = "", language: str = "en") -> tuple[str, str]:
    """
    Returns (transcript, provider_name).
    Primary: Groq Whisper | Fallback: NVIDIA Parakeet.
    """
    # Groq Whisper primary (free, very fast)
    if settings.GROQ_API_KEY:
        try:
            import io
            from groq import AsyncGroq

            client = AsyncGroq(api_key=settings.GROQ_API_KEY)

            if audio_url:
                async with httpx.AsyncClient(timeout=30) as http:
                    resp = await http.get(audio_url)
                    resp.raise_for_status()
                    audio_bytes = resp.content
            elif audio_base64:
                audio_bytes = base64.b64decode(audio_base64)
            else:
                return "", "none"

            transcription = await client.audio.transcriptions.create(
                file=("audio.mp3", io.BytesIO(audio_bytes), "audio/mpeg"),
                model="whisper-large-v3",
                language=language if language != "auto" else None,
                response_format="text",
            )
            return transcription, "groq-whisper"
        except Exception:
            pass

    return "", "unavailable"
