from fastapi import APIRouter, HTTPException
from schemas.ocr_schema import OCRRequest, OCRResponse
from services.ocr_service import extract_text

router = APIRouter(prefix="/v1/ocr")


@router.post("/extract", response_model=OCRResponse)
async def ocr_extract(request: OCRRequest):
    if not request.image_url and not request.image_base64:
        raise HTTPException(status_code=400, detail="Provide image_url or image_base64.")

    text, provider = await extract_text(
        image_url=request.image_url,
        image_base64=request.image_base64,
        prompt=request.prompt,
    )
    if provider == "unavailable":
        raise HTTPException(status_code=503, detail="OCR service unavailable. Check NVIDIA_API_KEY.")

    return OCRResponse(text=text, provider=provider)
