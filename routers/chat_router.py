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


# ── Export ────────────────────────────────────────────────────────────────────

@router.get("/export", summary="Export a conversation session as markdown, JSON, or plain text")
async def export_session(
    user_id: str,
    platform: str,
    session_id: str,
    format: str = "markdown",
    db: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response as FastResponse
    from services.conversation_export_service import export_session as _export, ExportFormat

    fmt: ExportFormat = format if format in ("markdown", "json", "plain") else "markdown"
    content, content_type = await _export(user_id, platform, session_id, fmt, db)

    filename = f"conversation-{session_id[:12]}.{{'markdown':'md','json':'json','plain':'txt'}[fmt]}"
    return FastResponse(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Response versioning ───────────────────────────────────────────────────────

class SelectVersionRequest(BaseModel):
    user_id: str


@router.get("/versions", summary="List response versions for a user message")
async def list_versions(
    user_id: str,
    platform: str,
    session_id: str,
    user_message: str,
    db: AsyncSession = Depends(get_db),
):
    from services.response_version_service import get_versions
    versions = await get_versions(user_id, session_id, user_message, db)
    return {"status": "ok", "data": versions, "count": len(versions)}


@router.get("/versions/all", summary="List all messages with multiple response versions")
async def list_all_versions(
    user_id: str,
    platform: str,
    session_id: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    from services.response_version_service import list_all_versions as _list
    versions = await _list(user_id, platform, db, session_id=session_id, limit=limit)
    return {"status": "ok", "data": versions, "count": len(versions)}


@router.post("/versions/{version_id}/select", summary="Mark a response version as preferred")
async def select_version(version_id: int, req: SelectVersionRequest, db: AsyncSession = Depends(get_db)):
    from services.response_version_service import select_version as _select
    ok = await _select(version_id, req.user_id, db)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Version {version_id} not found")
    return {"status": "ok", "selected": version_id}


# ── Budget status ─────────────────────────────────────────────────────────────

@router.get("/budget", summary="Get current monthly token budget status for a user")
async def get_budget(user_id: str, platform: str, db: AsyncSession = Depends(get_db)):
    from services.policy_limits_service import get_user_budget_status, load_platform_limits
    limits = await load_platform_limits(platform, db)
    status = get_user_budget_status(user_id, limits)
    return {"status": "ok", "data": status}
