from pydantic import BaseModel, ConfigDict
from typing import Optional


class ChatRequest(BaseModel):
    user_id: str
    platform: str = "generic"
    session_id: str = ""
    message: str
    context: dict = {}
    output_style: Optional[str] = None  # auto|brief|detailed|bullets|numbered|narrative|
                                        # code_only|table|json|plain|academic|slack|executive
    permission_mode: Optional[str] = None  # auto|manual|readonly|sandbox|restricted
    json_schema: Optional[dict] = None    # if set, response is validated against this JSON Schema


class ChatMetadata(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    memory_updated: bool
    corrections_detected: bool
    tone_detected: str
    provider_used: str
    model_used: str
