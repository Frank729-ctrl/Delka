from fastapi import APIRouter, HTTPException
from schemas.detection_schema import DetectionRequest, DetectionResponse, DetectedObject
from services.object_detection_service import detect_objects

router = APIRouter(prefix="/v1/detect")


@router.post("/objects", response_model=DetectionResponse)
async def detect(request: DetectionRequest):
    if not request.image_url and not request.image_base64:
        raise HTTPException(status_code=400, detail="Provide image_url or image_base64.")

    objects, raw, provider = await detect_objects(
        image_url=request.image_url,
        image_base64=request.image_base64,
        confidence_threshold=request.confidence_threshold,
    )
    if provider == "unavailable":
        raise HTTPException(status_code=503, detail="Object detection unavailable.")

    return DetectionResponse(
        objects=[DetectedObject(**o) for o in objects],
        raw_description=raw,
        provider=provider,
    )
