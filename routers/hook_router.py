"""
Hook Subscription API — register HTTP webhooks for lifecycle events.

POST   /v1/hooks               — register a webhook subscription
GET    /v1/hooks?platform=…    — list subscriptions for a platform
DELETE /v1/hooks/{id}          — deactivate a subscription
POST   /v1/hooks/{id}/test     — send a test ping to the URL
GET    /v1/hooks/events        — list all valid event types
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.hook_service import (
    register_subscription, list_subscriptions,
    delete_subscription, test_subscription, VALID_EVENTS,
)

router = APIRouter(prefix="/v1/hooks")


class RegisterHookRequest(BaseModel):
    name: str = Field(..., description="Human label for this subscription")
    platform: str
    event: str = Field(..., description="Hook event type, e.g. 'post_chat'")
    url: str = Field(..., description="URL to POST the event payload to")
    secret: Optional[str] = Field(None, description="HMAC secret for X-Delka-Signature header")
    created_by: Optional[str] = None


@router.get("/events", summary="List all valid hook event types")
async def api_list_events():
    descriptions = {
        "pre_chat":      "Before any processing — payload includes message + user context",
        "post_chat":     "After full response sent — payload includes response + provider used",
        "post_compact":  "After context compaction — payload includes summary + token savings",
        "post_memory":   "After session memory extraction — payload includes extracted facts",
        "post_skill":    "After a /skill is executed — payload includes skill name + result",
        "post_tool":     "After an MCP tool call — payload includes tool name + result",
        "session_start": "First message in a session",
        "session_end":   "Explicit session close or TTL expiry",
    }
    return {
        "status": "ok",
        "events": [{"event": e, "description": descriptions.get(e, "")} for e in sorted(VALID_EVENTS)],
    }


@router.post("", summary="Register a webhook subscription")
async def api_register(req: RegisterHookRequest, db: AsyncSession = Depends(get_db)):
    result = await register_subscription(
        name=req.name,
        platform=req.platform,
        event=req.event,
        url=req.url,
        secret=req.secret,
        created_by=req.created_by,
        db=db,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"status": "ok", "message": f"Webhook registered for '{req.event}' on platform '{req.platform}'"}


@router.get("", summary="List webhook subscriptions for a platform")
async def api_list(platform: str, db: AsyncSession = Depends(get_db)):
    subs = await list_subscriptions(platform, db)
    return {"status": "ok", "data": subs, "count": len(subs)}


@router.delete("/{sub_id}", summary="Deactivate a webhook subscription")
async def api_delete(sub_id: int, platform: str, db: AsyncSession = Depends(get_db)):
    ok = await delete_subscription(sub_id, platform, db)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Subscription {sub_id} not found")
    return {"status": "ok", "message": f"Subscription {sub_id} deactivated"}


@router.post("/{sub_id}/test", summary="Send a test ping to a webhook URL")
async def api_test(sub_id: int, platform: str, db: AsyncSession = Depends(get_db)):
    result = await test_subscription(sub_id, platform, db)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return {"status": "ok", **result}
