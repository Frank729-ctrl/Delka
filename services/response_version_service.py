"""
Response versioning — store multiple AI responses for the same user message.

When a user says "try again", "regenerate", "give me another answer", or
explicitly calls POST /v1/chat/regenerate, this service:
  1. Saves the new response as version N+1 for the same user message
  2. Returns all versions so the client can let the user pick

Versions are grouped by MD5 hash of the user message within a session.
The selected version can be marked via POST /v1/chat/versions/{id}/select.

This is a fundamental UX improvement over Claude Code — src has no
multi-version response tracking at all.
"""
from __future__ import annotations

import hashlib
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


def _message_hash(message: str) -> str:
    return hashlib.md5(message.strip().encode()).hexdigest()


async def save_response_version(
    user_id: str,
    platform: str,
    session_id: str,
    user_message: str,
    response: str,
    db: AsyncSession,
    provider: str = "",
    model_name: str = "",
    effort_tier: str = "",
    output_style: str = "",
    tokens: int = 0,
    cost_usd: float = 0.0,
) -> dict:
    """
    Save a response as a versioned entry. Auto-increments version number.
    Returns the saved version dict.
    """
    from models.response_version_model import ResponseVersion

    msg_hash = _message_hash(user_message)

    # Get current max version for this message
    result = await db.execute(
        select(ResponseVersion.version)
        .where(
            ResponseVersion.user_id == user_id,
            ResponseVersion.session_id == session_id,
            ResponseVersion.message_hash == msg_hash,
        )
        .order_by(ResponseVersion.version.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    next_version = (row or 0) + 1

    entry = ResponseVersion(
        user_id=user_id,
        platform=platform,
        session_id=session_id,
        message_hash=msg_hash,
        user_message=user_message[:2000],
        version=next_version,
        response=response,
        provider=provider or None,
        model_name=model_name or None,
        effort_tier=effort_tier or None,
        output_style=output_style or None,
        tokens=tokens or None,
        cost_usd=cost_usd or None,
        selected=1 if next_version == 1 else 0,  # v1 selected by default
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _to_dict(entry)


async def get_versions(
    user_id: str,
    session_id: str,
    user_message: str,
    db: AsyncSession,
) -> list[dict]:
    """Get all versions for a specific user message."""
    from models.response_version_model import ResponseVersion

    msg_hash = _message_hash(user_message)
    result = await db.execute(
        select(ResponseVersion)
        .where(
            ResponseVersion.user_id == user_id,
            ResponseVersion.session_id == session_id,
            ResponseVersion.message_hash == msg_hash,
        )
        .order_by(ResponseVersion.version.asc())
    )
    return [_to_dict(r) for r in result.scalars().all()]


async def select_version(
    version_id: int,
    user_id: str,
    db: AsyncSession,
) -> bool:
    """Mark a specific version as the user's preferred one."""
    from models.response_version_model import ResponseVersion
    from sqlalchemy import update

    # Get the version to find its message hash + session
    result = await db.execute(
        select(ResponseVersion).where(
            ResponseVersion.id == version_id,
            ResponseVersion.user_id == user_id,
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        return False

    # Deselect all versions for this message
    await db.execute(
        update(ResponseVersion)
        .where(
            ResponseVersion.user_id == user_id,
            ResponseVersion.session_id == target.session_id,
            ResponseVersion.message_hash == target.message_hash,
        )
        .values(selected=0)
    )
    # Select the target
    await db.execute(
        update(ResponseVersion)
        .where(ResponseVersion.id == version_id)
        .values(selected=1)
    )
    await db.commit()
    return True


async def list_all_versions(
    user_id: str,
    platform: str,
    db: AsyncSession,
    session_id: Optional[str] = None,
    only_multiple: bool = True,
    limit: int = 50,
) -> list[dict]:
    """List messages that have multiple versions (for the versions browser)."""
    from models.response_version_model import ResponseVersion
    from sqlalchemy import func

    conditions = [
        ResponseVersion.user_id == user_id,
        ResponseVersion.platform == platform,
    ]
    if session_id:
        conditions.append(ResponseVersion.session_id == session_id)

    if only_multiple:
        # Subquery: message hashes with >1 version
        subq = (
            select(ResponseVersion.message_hash)
            .where(*conditions)
            .group_by(ResponseVersion.message_hash)
            .having(func.count(ResponseVersion.id) > 1)
        ).scalar_subquery()
        conditions.append(ResponseVersion.message_hash.in_(subq))

    result = await db.execute(
        select(ResponseVersion)
        .where(*conditions)
        .order_by(ResponseVersion.created_at.desc())
        .limit(limit)
    )
    return [_to_dict(r) for r in result.scalars().all()]


def _to_dict(r) -> dict:
    return {
        "id": r.id,
        "session_id": r.session_id,
        "version": r.version,
        "user_message": r.user_message[:200],
        "response": r.response,
        "provider": r.provider,
        "model_name": r.model_name,
        "effort_tier": r.effort_tier,
        "output_style": r.output_style,
        "tokens": r.tokens,
        "cost_usd": r.cost_usd,
        "selected": bool(r.selected),
        "created_at": str(r.created_at),
    }
