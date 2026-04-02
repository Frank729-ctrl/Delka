from pydantic import BaseModel


class TranslationRequest(BaseModel):
    text: str
    source_lang: str = "auto"
    target_lang: str = "en"


class TranslationResponse(BaseModel):
    translated_text: str
    source_lang: str
    target_lang: str
    provider: str = "nvidia"
