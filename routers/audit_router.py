"""
Tool audit trail API.

GET /v1/audit/tools          — list tool invocations
GET /v1/audit/tools/stats    — aggregate stats by tool type
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.tool_audit_service import query_audit_log, get_audit_stats

router = APIRouter(prefix="/v1/audit")

_VALID_TOOL_TYPES = {"search", "sandbox", "fetch", "mcp", "skill", "memory"}


@router.get("/tools", summary="List tool invocations in the audit log")
async def api_list_tools(
    user_id: str,
    platform: str,
    session_id: Optional[str] = Query(None),
    tool_type: Optional[str] = Query(None, description=f"Filter by type: {', '.join(sorted(_VALID_TOOL_TYPES))}"),
    tool_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    logs = await query_audit_log(
        user_id=user_id,
        platform=platform,
        db=db,
        session_id=session_id,
        tool_type=tool_type,
        tool_name=tool_name,
        limit=limit,
        offset=offset,
    )
    return {"status": "ok", "data": logs, "count": len(logs)}


@router.get("/tools/stats", summary="Aggregate tool usage stats")
async def api_tool_stats(
    user_id: str,
    platform: str,
    session_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stats = await get_audit_stats(user_id, platform, db, session_id=session_id)
    return {"status": "ok", "data": stats}
