from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.chat_schema import ChatRequest
from services.chat_service import chat
from services.personality_service import analyze_user_tone

router = APIRouter(prefix="/v1/chat", tags=["Chat"])


@router.post("")
async def chat_endpoint(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    tone = analyze_user_tone(request.message)
    tone_detected = tone.get("formality", "neutral")

    async def stream_gen():
        async for chunk in chat(request, db):
            yield chunk

    return StreamingResponse(
        stream_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Tone-Detected": tone_detected,
            "X-Memory-Updated": "true",
            "X-Corrections-Detected": "false",
            "X-Provider-Used": "groq",
        },
    )
