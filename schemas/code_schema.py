from pydantic import BaseModel
from typing import Optional


class CodeRequest(BaseModel):
    prompt: str
    language: str = ""
    context: str = ""
    max_tokens: int = 2048
    user_id: str = ""
    platform: str = "web"


class CodeResponse(BaseModel):
    code: str
    language: str
    explanation: str = ""
    provider: str
    model: str
