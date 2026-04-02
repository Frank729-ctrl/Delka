from pydantic import BaseModel


class SpeechRequest(BaseModel):
    audio_url: str = ""
    audio_base64: str = ""
    language: str = "en"


class SpeechResponse(BaseModel):
    transcript: str
    language: str
    provider: str = "groq"
