from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.chat_schema import ChatRequest
from services.chat_service import chat
from services.personality_service import analyze_user_tone
from services.output_style_service import list_styles, VALID_STYLES
from services.hook_service import fire

router = APIRouter(prefix="/v1/chat", tags=["Chat"])


@router.get("/styles", summary="List available output styles")
async def get_styles():
    """Return all valid output_style values and their descriptions."""
    return {"status": "ok", "styles": list_styles(), "valid_values": sorted(VALID_STYLES)}


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


class SessionEndRequest(BaseModel):
    user_id: str
    platform: str
    session_id: str
    reason: Optional[str] = Field(None, description="Why the session ended: user_closed|timeout|error")


class AnalyzeRequest(BaseModel):
    user_id: str
    platform: str
    session_id: str
    store_as_memory: bool = Field(False, description="Save key findings as a project memory for future recall")
    format: str = Field("json", description="Response format: json | markdown")


@router.post("/session/end", summary="Explicitly close a session and fire session_end hook")
async def session_end(req: SessionEndRequest, db: AsyncSession = Depends(get_db)):
    """
    Call this when the user closes the chat window or logs out.
    Fires the session_end hook so subscribers (analytics, CRM, etc.) are notified.
    """
    await fire("session_end", req.platform, req.user_id, req.session_id, {
        "reason": req.reason or "user_closed",
    }, db)
    return {"status": "ok", "message": "session_end hook fired"}


@router.post("/analyze", summary="Deep analysis of a past conversation session (Thinkback)")
async def analyze_session(req: AnalyzeRequest, db: AsyncSession = Depends(get_db)):
    """
    Analyze a conversation session to extract structured intelligence:
    key decisions, AI errors, intent evolution, action items, user patterns,
    and confidence calibration issues.

    Exceeds Claude Code's compactConversation — this is insight extraction,
    not just summarization.
    """
    from services.thinkback_service import analyze_session as _analyze, format_insight_markdown
    from dataclasses import asdict

    insight = await _analyze(
        session_id=req.session_id,
        user_id=req.user_id,
        platform=req.platform,
        db=db,
        store_as_memory=req.store_as_memory,
    )

    if req.format == "markdown":
        return {"status": "ok", "markdown": format_insight_markdown(insight)}

    return {"status": "ok", "data": asdict(insight)}
