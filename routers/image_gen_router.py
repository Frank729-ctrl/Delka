import base64
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from schemas.image_gen_schema import ImageGenRequest, ImageGenResponse
from services.image_gen_service import generate_image

router = APIRouter(prefix="/v1/image")


@router.post("/generate", response_model=ImageGenResponse)
async def image_generate(request: ImageGenRequest):
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required.")

    image_bytes, provider, seed_used = await generate_image(
        prompt=request.prompt,
        negative_prompt=request.negative_prompt,
        width=request.width,
        height=request.height,
        steps=request.steps,
        seed=request.seed,
    )
    if provider == "unavailable" or not image_bytes:
        raise HTTPException(
            status_code=503,
            detail="Image generation unavailable. Check NVIDIA_API_KEY."
        )

    return ImageGenResponse(
        image_base64=base64.b64encode(image_bytes).decode(),
        content_type="image/png",
        provider=provider,
        seed=seed_used,
    )


@router.post("/generate/stream")
async def image_generate_stream(request: ImageGenRequest):
    """Returns image bytes directly."""
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required.")

    image_bytes, provider, _ = await generate_image(
        prompt=request.prompt,
        negative_prompt=request.negative_prompt,
        width=request.width,
        height=request.height,
        steps=request.steps,
        seed=request.seed,
    )
    if provider == "unavailable" or not image_bytes:
        raise HTTPException(status_code=503, detail="Image generation unavailable.")

    return Response(content=image_bytes, media_type="image/png")
