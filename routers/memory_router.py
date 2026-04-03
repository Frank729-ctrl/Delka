"""
Memory management API — browse, search, and delete stored memories.

GET    /v1/memory                        — list all memories (optional ?type=)
GET    /v1/memory/manifest               — full structured manifest (MEMORY.md equivalent)
GET    /v1/memory/stats                  — counts by type + staleness
GET    /v1/memory/search?q=&platform=   — keyword search
DELETE /v1/memory/{id}                  — delete a specific memory
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.memory_manifest_service import (
    list_memories, search_memories, delete_memory,
    manifest_for_prompt, get_memory_stats,
)

router = APIRouter(prefix="/v1/memory")

_VALID_TYPES = {"user", "feedback", "project", "reference"}


@router.get("", summary="List stored memories for a user")
async def api_list(
    user_id: str,
    platform: str,
    type: Optional[str] = Query(None, description="Filter by type: user|feedback|project|reference"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    if type and type not in _VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of: {', '.join(_VALID_TYPES)}")
    memories = await list_memories(user_id, platform, db, mem_type=type, limit=limit)
    return {"status": "ok", "data": memories, "count": len(memories)}


@router.get("/manifest", summary="Get structured memory manifest (MEMORY.md equivalent)")
async def api_manifest(
    user_id: str,
    platform: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns a structured, truncation-aware memory index — Delka's equivalent
    of Claude Code's MEMORY.md file. Grouped by type, sorted newest-first,
    capped at 200 lines / 25KB with a warning if truncated.
    """
    manifest = await manifest_for_prompt(user_id, platform, db)
    if not manifest:
        return {"status": "ok", "manifest": "", "message": "No memories stored yet"}
    return {"status": "ok", "manifest": manifest}


@router.get("/stats", summary="Memory counts by type and staleness")
async def api_stats(
    user_id: str,
    platform: str,
    db: AsyncSession = Depends(get_db),
):
    stats = await get_memory_stats(user_id, platform, db)
    return {"status": "ok", "data": stats}


@router.get("/search", summary="Search memories by keyword")
async def api_search(
    user_id: str,
    platform: str,
    q: str = Query(..., description="Keyword to search in title and content"),
    type: Optional[str] = Query(None, description="Filter by type"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    if type and type not in _VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of: {', '.join(_VALID_TYPES)}")
    results = await search_memories(user_id, platform, q, db, mem_type=type, limit=limit)
    return {"status": "ok", "query": q, "data": results, "count": len(results)}


@router.delete("/{memory_id}", summary="Delete a specific memory")
async def api_delete(
    memory_id: int,
    user_id: str,
    platform: str,
    db: AsyncSession = Depends(get_db),
):
    deleted = await delete_memory(memory_id, user_id, platform, db)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Memory {memory_id} not found for this user/platform"
        )
    return {"status": "ok", "message": f"Memory {memory_id} deleted"}
