"""
Session sharing API.

POST /v1/share                — create a shareable link for a session
GET  /v1/share/{code}         — read shared conversation (public, no auth)
POST /v1/share/{code}/fork    — fork into caller's own session
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.session_share_service import create_share, get_share, fork_share

router = APIRouter(prefix="/v1/share")


class CreateShareRequest(BaseModel):
    user_id: str
    platform: str
    session_id: str
    expires_hours: int = Field(72, ge=1, le=720, description="Link validity in hours (1–720)")
    include_meta: bool = Field(False, description="Include provider/cost metadata in shared view")


class ForkShareRequest(BaseModel):
    user_id: str
    platform: str
    session_id: str = Field(..., description="The new session_id to fork into")


@router.post("", summary="Create a shareable link for a conversation session")
async def api_create_share(req: CreateShareRequest, db: AsyncSession = Depends(get_db)):
    """
    Snapshot the session and generate a short share code.
    Anyone with the code can read or fork the conversation.
    """
    result = await create_share(
        user_id=req.user_id,
        platform=req.platform,
        session_id=req.session_id,
        db=db,
        expires_hours=req.expires_hours,
        include_meta=req.include_meta,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"status": "ok", **result}


@router.get("/{code}", summary="Read a shared conversation (public)")
async def api_read_share(code: str, db: AsyncSession = Depends(get_db)):
    """
    Public endpoint — no authentication required.
    Returns the conversation messages and metadata.
    Expired links return 404.
    """
    shared = await get_share(code, db)
    if not shared:
        raise HTTPException(status_code=404, detail="Share link not found or expired")
    return {"status": "ok", "data": shared}


@router.post("/{code}/fork", summary="Fork a shared conversation into your own session")
async def api_fork_share(code: str, req: ForkShareRequest, db: AsyncSession = Depends(get_db)):
    """
    Creates a copy of the shared conversation as the caller's own session.
    The caller can then continue the conversation from that point.
    """
    result = await fork_share(
        code=code,
        new_user_id=req.user_id,
        new_session_id=req.session_id,
        new_platform=req.platform,
        db=db,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Share link not found or expired")
    return {"status": "ok", **result}
