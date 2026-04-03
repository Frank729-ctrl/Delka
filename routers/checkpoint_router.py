"""
Session checkpoint API.

POST   /v1/checkpoints              — create a named snapshot of current session
GET    /v1/checkpoints              — list checkpoints (filter by session_id)
POST   /v1/checkpoints/{id}/restore — restore session to checkpoint state
DELETE /v1/checkpoints/{id}         — delete a checkpoint
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.checkpoint_service import (
    create_checkpoint, list_checkpoints, restore_checkpoint, delete_checkpoint,
)

router = APIRouter(prefix="/v1/checkpoints")


class CreateCheckpointRequest(BaseModel):
    user_id: str
    platform: str
    session_id: str
    name: str = Field(..., description="Human-readable label for this checkpoint")
    description: Optional[str] = Field(None, description="Why this checkpoint was created")


class RestoreCheckpointRequest(BaseModel):
    user_id: str
    platform: str
    new_session_id: Optional[str] = Field(
        None,
        description="If provided, forks into a new session instead of overwriting the original"
    )


@router.post("", summary="Save current session state as a named checkpoint")
async def api_create(req: CreateCheckpointRequest, db: AsyncSession = Depends(get_db)):
    """
    Snapshot the session's full message history at this moment.
    Use before risky operations (refactoring, experiments) so you can restore if needed.
    """
    checkpoint = await create_checkpoint(
        user_id=req.user_id,
        platform=req.platform,
        session_id=req.session_id,
        name=req.name,
        db=db,
        description=req.description or "",
    )
    return {"status": "ok", "checkpoint": checkpoint}


@router.get("", summary="List checkpoints for a user or session")
async def api_list(
    user_id: str,
    platform: str,
    session_id: Optional[str] = Query(None, description="Filter to one session"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    checkpoints = await list_checkpoints(user_id, platform, db, session_id=session_id, limit=limit)
    return {"status": "ok", "data": checkpoints, "count": len(checkpoints)}


@router.post("/{checkpoint_id}/restore", summary="Restore session to a checkpoint state")
async def api_restore(
    checkpoint_id: int,
    req: RestoreCheckpointRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Replays the checkpoint's message history into the session.

    - Without new_session_id: overwrites the original session (in-place restore)
    - With new_session_id: forks into a new session — original session is untouched
      (useful for exploring alternative paths from the same starting point)
    """
    result = await restore_checkpoint(
        checkpoint_id=checkpoint_id,
        user_id=req.user_id,
        platform=req.platform,
        db=db,
        new_session_id=req.new_session_id,
    )
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint {checkpoint_id} not found for this user/platform"
        )
    return {"status": "ok", **result}


@router.delete("/{checkpoint_id}", summary="Delete a checkpoint")
async def api_delete(
    checkpoint_id: int,
    user_id: str,
    platform: str,
    db: AsyncSession = Depends(get_db),
):
    deleted = await delete_checkpoint(checkpoint_id, user_id, platform, db)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint {checkpoint_id} not found for this user/platform"
        )
    return {"status": "ok", "message": f"Checkpoint {checkpoint_id} deleted"}
