"""
Remote Session router — webhook-triggered agent runs.

POST   /v1/remote/trigger          — queue a prompt, get session_id back (202)
GET    /v1/remote/sessions/{id}    — poll session status + result
GET    /v1/remote/sessions         — list recent sessions
POST   /v1/remote/purge            — clean up old completed sessions
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

from services.remote_session_service import trigger, get_session, list_sessions, purge_old

router = APIRouter(prefix="/v1/remote")


class TriggerRequest(BaseModel):
    prompt: str = Field(..., description="The task or question for the AI to handle")
    callback_url: Optional[str] = Field(None, description="URL to POST the result to when done")
    system_prompt: str = Field("", description="Optional system/persona instructions")
    session_id: Optional[str] = Field(None, description="Custom session ID (auto-generated if omitted)")
    metadata: Optional[dict] = Field(None, description="Arbitrary key-value data echoed in callback")


@router.post("/trigger", status_code=202, summary="Trigger a remote agent session")
async def api_trigger(req: TriggerRequest):
    """
    Queue a prompt for async inference. Returns 202 immediately.
    Result is POSTed to callback_url when ready (if provided).
    Poll GET /v1/remote/sessions/{session_id} for status.
    """
    if len(req.prompt) > 8_000:
        raise HTTPException(status_code=400, detail="Prompt too long (max 8,000 chars)")
    session = trigger(
        prompt=req.prompt,
        callback_url=req.callback_url,
        system_prompt=req.system_prompt,
        session_id=req.session_id,
        metadata=req.metadata,
    )
    return JSONResponse(
        status_code=202,
        content={
            "status": "queued",
            "session_id": session.session_id,
            "message": "Session queued. Poll /v1/remote/sessions/{session_id} or await callback.",
        },
    )


@router.get("/sessions/{session_id}", summary="Get session status and result")
async def api_get_session(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"status": "ok", "data": session.to_dict()}


@router.get("/sessions", summary="List recent remote sessions")
async def api_list_sessions(limit: int = 50):
    sessions = list_sessions(limit=limit)
    return {
        "status": "ok",
        "data": {
            "sessions": [s.to_dict() for s in sessions],
            "count": len(sessions),
        },
    }


@router.post("/purge", summary="Remove old completed/failed sessions")
async def api_purge(max_age_seconds: int = 3600):
    removed = purge_old(max_age_seconds)
    return {"status": "ok", "message": f"Removed {removed} old sessions"}
