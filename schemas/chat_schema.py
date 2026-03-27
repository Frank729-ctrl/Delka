from pydantic import BaseModel


class ChatRequest(BaseModel):
    user_id: str
    platform: str = "generic"
    session_id: str = ""
    message: str
    context: dict = {}


class ChatMetadata(BaseModel):
    memory_updated: bool
    corrections_detected: bool
    tone_detected: str
    provider_used: str
    model_used: str
