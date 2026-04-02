"""
Text-to-Speech service.
Primary: edge-tts (Microsoft, free, no key, Ghana English voice).
Fallback: Groq (if they add TTS) or base message.
"""
import asyncio
import base64
import io
from config import settings


async def synthesize(text: str, voice: str = "", speed: float = 1.0) -> tuple[bytes, str, str]:
    """
    Returns (audio_bytes, content_type, provider_name).
    Uses edge-tts — Ghana English voice by default.
    """
    if not voice:
        voice = "en-GH-AmaNewscast"

    try:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice, rate=f"{int((speed - 1) * 100):+d}%")
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])

        audio_bytes = buf.getvalue()
        if audio_bytes:
            return audio_bytes, "audio/mpeg", "edge-tts"
    except ImportError:
        pass
    except Exception:
        pass

    return b"", "audio/mpeg", "unavailable"
