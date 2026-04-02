from fastapi import APIRouter, HTTPException
from schemas.speech_schema import SpeechRequest, SpeechResponse
from services.speech_service import transcribe_simple as transcribe

router = APIRouter(prefix="/v1/speech")


@router.post("/transcribe", response_model=SpeechResponse)
async def speech_transcribe(request: SpeechRequest):
    if not request.audio_url and not request.audio_base64:
        raise HTTPException(status_code=400, detail="Provide audio_url or audio_base64.")

    transcript, provider = await transcribe(
        audio_url=request.audio_url,
        audio_base64=request.audio_base64,
        language=request.language,
    )
    if provider == "unavailable":
        raise HTTPException(status_code=503, detail="STT service unavailable. Check GROQ_API_KEY.")

    return SpeechResponse(transcript=transcript, language=request.language, provider=provider)
