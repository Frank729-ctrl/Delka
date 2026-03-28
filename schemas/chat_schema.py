from pydantic import BaseModel, ConfigDict


class ChatRequest(BaseModel):
    user_id: str
    platform: str = "generic"
    session_id: str = ""
    message: str
    context: dict = {}


class ChatMetadata(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    memory_updated: bool
    corrections_detected: bool
    tone_detected: str
    provider_used: str
    model_used: str
