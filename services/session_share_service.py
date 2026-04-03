"""
Session Sharing — share a conversation with other users via a link/code.

Generates a short share code. Anyone with the code can:
  - Read the shared conversation (read-only view)
  - Fork it into their own session to continue from that point

Share settings:
  - expires_hours: how long the link stays valid (default 72h, max 720h)
  - include_meta: whether to include provider/cost metadata in the shared view

POST /v1/share              — create a share link
GET  /v1/share/{code}       — read a shared conversation (public)
POST /v1/share/{code}/fork  — fork into caller's own session

This gives Delka a feature src entirely lacks — Claude Code sessions are
completely local and not shareable.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


_CODE_LENGTH = 8   # e.g. "a3f7b2e1"


async def create_share(
    user_id: str,
    platform: str,
    session_id: str,
    db: AsyncSession,
    expires_hours: int = 72,
    include_meta: bool = False,
) -> dict:
    """
    Snapshot the current session and generate a share code.
    Returns {code, url_path, expires_at, message_count}.
    """
    from services.conversation_history_service import get_session_history

    history = await get_session_history(user_id, session_id, db)
    messages = [
        {
            "role": m["role"],
            "content": m["content"],
            **({"meta": m["meta"]} if include_meta and m.get("meta") else {}),
        }
        for m in history
        if m["role"] in ("user", "assistant")
    ]

    if not messages:
        return {"error": "No messages to share"}

    code = secrets.token_hex(4)  # 8 hex chars
    expires_at = int(time.time()) + expires_hours * 3600

    await db.execute(
        text(
            "INSERT INTO session_shares "
            "(code, owner_id, platform, session_id, snapshot, expires_at, include_meta) "
            "VALUES (:code, :uid, :pl, :sid, :snap::jsonb, :exp, :im)"
        ),
        {
            "code": code,
            "uid": user_id,
            "pl": platform,
            "sid": session_id,
            "snap": __import__("json").dumps(messages),
            "exp": expires_at,
            "im": include_meta,
        },
    )
    await db.commit()

    return {
        "code": code,
        "url_path": f"/v1/share/{code}",
        "message_count": len(messages),
        "expires_at": expires_at,
        "expires_in_hours": expires_hours,
    }


async def get_share(code: str, db: AsyncSession) -> Optional[dict]:
    """Fetch a shared conversation by code. Returns None if expired/not found."""
    import json as _json

    result = await db.execute(
        text(
            "SELECT code, platform, session_id, snapshot, expires_at, include_meta "
            "FROM session_shares WHERE code = :code"
        ),
        {"code": code},
    )
    row = result.fetchone()
    if not row:
        return None

    code_, platform, session_id, snapshot, expires_at, include_meta = row
    if expires_at and int(time.time()) > expires_at:
        return None  # expired

    messages = _json.loads(snapshot) if isinstance(snapshot, str) else snapshot
    return {
        "code": code_,
        "platform": platform,
        "session_id": session_id,
        "message_count": len(messages),
        "messages": messages,
        "expires_at": expires_at,
    }


async def fork_share(
    code: str,
    new_user_id: str,
    new_session_id: str,
    new_platform: str,
    db: AsyncSession,
) -> Optional[dict]:
    """
    Fork a shared session into the caller's own session.
    Replays the snapshot messages as if they were the user's own history.
    Returns the new session info or None if code not found/expired.
    """
    shared = await get_share(code, db)
    if not shared:
        return None

    from models.conversation_log_model import ConversationLog
    from services.conversation_history_service import estimate_tokens

    for msg in shared["messages"]:
        entry = ConversationLog(
            user_id=new_user_id,
            platform=new_platform,
            session_id=new_session_id,
            role=msg["role"],
            content=msg["content"],
            tokens_estimate=estimate_tokens(msg["content"]),
        )
        db.add(entry)
    await db.commit()

    return {
        "session_id": new_session_id,
        "message_count": len(shared["messages"]),
        "forked_from": code,
    }


async def _ensure_shares_table(db: AsyncSession) -> None:
    """Create session_shares table if it doesn't exist (called at startup)."""
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS session_shares (
            id SERIAL PRIMARY KEY,
            code VARCHAR(16) UNIQUE NOT NULL,
            owner_id VARCHAR(100) NOT NULL,
            platform VARCHAR(50) NOT NULL,
            session_id VARCHAR(100) NOT NULL,
            snapshot JSONB NOT NULL,
            expires_at BIGINT,
            include_meta BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    await db.commit()
