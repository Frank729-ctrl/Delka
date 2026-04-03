"""
Session Checkpoints — save and restore conversation state at named points.

Equivalent of Claude Code's git-worktree session isolation, but:
  - DB-backed (cross-device, no filesystem required)
  - Named checkpoints with optional description
  - Restore replays history so user continues from that exact state
  - List all checkpoints for a session
  - Delete individual checkpoints

Use cases:
  - "Checkpoint before refactoring" — then restore if the refactor goes wrong
  - "Save this conversation state" — share a named starting point
  - Fork exploration: checkpoint, explore one approach, restore, explore another

Endpoints (via checkpoint_router):
  POST   /v1/checkpoints              — create checkpoint
  GET    /v1/checkpoints?session_id=  — list checkpoints for a session
  POST   /v1/checkpoints/{id}/restore — restore session to this checkpoint
  DELETE /v1/checkpoints/{id}         — delete a checkpoint
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete


async def create_checkpoint(
    user_id: str,
    platform: str,
    session_id: str,
    name: str,
    db: AsyncSession,
    description: str = "",
) -> dict:
    """
    Snapshot the current session history into a named checkpoint.
    Returns the checkpoint record.
    """
    from services.conversation_history_service import get_session_history
    from models.session_checkpoint_model import SessionCheckpoint

    history = await get_session_history(user_id, session_id, db)

    # Strip internal fields that shouldn't be in snapshot (e.g. db id)
    snapshot = [
        {"role": m["role"], "content": m["content"], "meta": m.get("meta")}
        for m in history
        if m["role"] in ("user", "assistant")
    ]

    meta = {
        "message_count": len(snapshot),
        "created_at": datetime.utcnow().isoformat(),
        "platform": platform,
    }

    checkpoint = SessionCheckpoint(
        user_id=user_id,
        platform=platform,
        session_id=session_id,
        name=name[:200],
        description=description[:500] if description else None,
        history_snapshot=snapshot,
        meta=meta,
    )
    db.add(checkpoint)
    await db.commit()
    await db.refresh(checkpoint)

    return _checkpoint_to_dict(checkpoint)


async def list_checkpoints(
    user_id: str,
    platform: str,
    db: AsyncSession,
    session_id: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """List checkpoints for a user, optionally filtered to one session."""
    from models.session_checkpoint_model import SessionCheckpoint

    conditions = [
        SessionCheckpoint.user_id == user_id,
        SessionCheckpoint.platform == platform,
    ]
    if session_id:
        conditions.append(SessionCheckpoint.session_id == session_id)

    result = await db.execute(
        select(SessionCheckpoint)
        .where(*conditions)
        .order_by(SessionCheckpoint.created_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [_checkpoint_to_dict(r) for r in rows]


async def restore_checkpoint(
    checkpoint_id: int,
    user_id: str,
    platform: str,
    db: AsyncSession,
    new_session_id: Optional[str] = None,
) -> dict:
    """
    Restore a session to the state saved in a checkpoint.

    By default, restores into the same session_id (replaces history).
    If new_session_id is provided, forks into a new session — original is untouched.

    Returns: {checkpoint, restored_to_session_id, message_count}
    """
    from models.session_checkpoint_model import SessionCheckpoint
    from models.conversation_log_model import ConversationLog

    result = await db.execute(
        select(SessionCheckpoint).where(
            SessionCheckpoint.id == checkpoint_id,
            SessionCheckpoint.user_id == user_id,
            SessionCheckpoint.platform == platform,
        )
    )
    checkpoint = result.scalar_one_or_none()
    if not checkpoint:
        return {}

    target_session = new_session_id or checkpoint.session_id

    # Clear existing messages for target session
    await db.execute(
        delete(ConversationLog).where(
            ConversationLog.user_id == user_id,
            ConversationLog.platform == platform,
            ConversationLog.session_id == target_session,
        )
    )

    # Replay snapshot messages
    from services.conversation_history_service import estimate_tokens
    for msg in (checkpoint.history_snapshot or []):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        meta = msg.get("meta") or {}
        entry = ConversationLog(
            user_id=user_id,
            platform=platform,
            session_id=target_session,
            role=role,
            content=content,
            tokens_estimate=estimate_tokens(content),
            provider=meta.get("provider"),
            model_name=meta.get("model"),
            input_tokens=meta.get("input_tokens"),
            output_tokens=meta.get("output_tokens"),
            cost_usd=meta.get("cost_usd"),
            effort_tier=meta.get("effort_tier"),
        )
        db.add(entry)

    await db.commit()

    return {
        "checkpoint": _checkpoint_to_dict(checkpoint),
        "restored_to_session_id": target_session,
        "message_count": len(checkpoint.history_snapshot or []),
        "forked": new_session_id is not None,
    }


async def delete_checkpoint(
    checkpoint_id: int,
    user_id: str,
    platform: str,
    db: AsyncSession,
) -> bool:
    """Delete a checkpoint. Returns True if found and deleted."""
    from models.session_checkpoint_model import SessionCheckpoint

    result = await db.execute(
        delete(SessionCheckpoint).where(
            SessionCheckpoint.id == checkpoint_id,
            SessionCheckpoint.user_id == user_id,
            SessionCheckpoint.platform == platform,
        )
    )
    await db.commit()
    return result.rowcount > 0


def _checkpoint_to_dict(cp) -> dict:
    return {
        "id": cp.id,
        "session_id": cp.session_id,
        "name": cp.name,
        "description": cp.description,
        "message_count": (cp.meta or {}).get("message_count", len(cp.history_snapshot or [])),
        "meta": cp.meta,
        "created_at": str(cp.created_at),
    }
