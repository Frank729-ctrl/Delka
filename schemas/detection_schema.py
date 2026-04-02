from pydantic import BaseModel
from typing import List


class DetectionRequest(BaseModel):
    image_url: str = ""
    image_base64: str = ""
    confidence_threshold: float = 0.5


class DetectedObject(BaseModel):
    label: str
    confidence: float
    description: str = ""


class DetectionResponse(BaseModel):
    objects: List[DetectedObject]
    raw_description: str
    provider: str = "nvidia"
