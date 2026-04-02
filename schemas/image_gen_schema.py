from pydantic import BaseModel


class ImageGenRequest(BaseModel):
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 30
    seed: int = -1


class ImageGenResponse(BaseModel):
    image_base64: str
    content_type: str = "image/png"
    provider: str = "nvidia"
    seed: int = -1
