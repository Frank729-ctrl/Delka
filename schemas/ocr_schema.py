from pydantic import BaseModel


class OCRRequest(BaseModel):
    image_url: str = ""
    image_base64: str = ""
    prompt: str = "Extract all text from this image accurately."


class OCRResponse(BaseModel):
    text: str
    provider: str = "nvidia"
