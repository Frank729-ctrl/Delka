from pydantic import BaseModel


class TTSRequest(BaseModel):
    text: str
    voice: str = "en-GH-AmaNewscast"
    speed: float = 1.0


class TTSResponse(BaseModel):
    audio_base64: str
    content_type: str = "audio/mpeg"
    provider: str = "edge-tts"
