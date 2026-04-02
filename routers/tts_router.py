import base64
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from schemas.tts_schema import TTSRequest, TTSResponse
from services.tts_service import synthesize

router = APIRouter(prefix="/v1/tts")


@router.post("/synthesize", response_model=TTSResponse)
async def tts_synthesize(request: TTSRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="text is required.")

    audio_bytes, content_type, provider = await synthesize(
        text=request.text,
        voice=request.voice,
        speed=request.speed,
    )
    if provider == "unavailable" or not audio_bytes:
        raise HTTPException(
            status_code=503,
            detail="TTS unavailable. Install edge-tts: pip install edge-tts"
        )

    return TTSResponse(
        audio_base64=base64.b64encode(audio_bytes).decode(),
        content_type=content_type,
        provider=provider,
    )


@router.post("/synthesize/stream")
async def tts_stream(request: TTSRequest):
    """Returns audio bytes directly (Content-Type: audio/mpeg)."""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="text is required.")

    audio_bytes, content_type, provider = await synthesize(
        text=request.text,
        voice=request.voice,
        speed=request.speed,
    )
    if provider == "unavailable" or not audio_bytes:
        raise HTTPException(status_code=503, detail="TTS unavailable.")

    return Response(content=audio_bytes, media_type=content_type)
