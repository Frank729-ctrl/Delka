from pydantic import BaseModel


class SupportChatRequest(BaseModel):
    message: str
    platform: str = "generic"
    session_id: str = ""


class SupportChatResponse(BaseModel):
    status: str
    message: str
    data: dict | None = None
