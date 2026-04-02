"""
Away Summary — "while you were away" session recap.

Inspired by Claude Code's awaySummary.ts.

When a user returns to a chat session after being away (> 30 min gap),
Delka generates a 1-3 sentence recap: what was being worked on and the
next concrete step. Shown as the first message in the restored session.

Delka improvements over Claude Code:
- Uses session memories (persistent) not just in-memory transcript
- Detects the gap from DB timestamps (works across page refreshes)
- Returns structured JSON so the frontend can render it as a special card
- Includes the platform context so the recap is role-appropriate
"""
from __future__ import annotations

from datetime import datetime, timedelta

AWAY_THRESHOLD_MINUTES = 30

_AWAY_SYSTEM = """You are summarizing a conversation for a user who stepped away and is returning.

Write exactly 1-3 short sentences:
1. What the user was working on (be specific — name the thing, not just "a project")
2. The concrete next step or where things were left

Be direct. No greetings. No "Welcome back". No filler.
Bad: "You were working on your CV and we discussed some options."
Good: "Building your CV for a software engineer role at Acme Corp. Next: add the National Service section."""


async def get_away_summary(
    user_id: str,
    platform: str,
    session_id: str,
    db,
) -> str | None:
    """
    Returns a recap string if the user has been away > AWAY_THRESHOLD_MINUTES,
    otherwise returns None.
    """
    try:
        from services.conversation_history_service import get_recent_history
        from services.session_memory_service import get_memories
        from services.inference_service import generate_full_response
        from models.conversation_log_model import ConversationLog
        from sqlalchemy import select

        # Check last message timestamp
        result = await db.execute(
            select(ConversationLog)
            .where(
                ConversationLog.user_id == user_id,
                ConversationLog.platform == platform,
                ConversationLog.session_id == session_id,
            )
            .order_by(ConversationLog.created_at.desc())
            .limit(1)
        )
        last_msg = result.scalar_one_or_none()
        if not last_msg:
            return None

        gap = datetime.utcnow() - last_msg.created_at
        if gap < timedelta(minutes=AWAY_THRESHOLD_MINUTES):
            return None  # user wasn't away long enough

        # Build recap from recent history + session memories
        recent = await get_recent_history(user_id, platform, db, limit=10, session_id=session_id)
        memories = await get_memories(user_id, platform, db, limit=5)

        if not recent:
            return None

        history_text = "\n".join(
            f"{m['role'].upper()}: {m['content'][:300]}"
            for m in recent[-8:]
        )
        context = f"{memories}\n\n---\nRecent conversation:\n{history_text}" if memories else history_text

        recap, _, _ = await generate_full_response(
            task="support",
            system_prompt=_AWAY_SYSTEM,
            user_prompt=context,
            temperature=0.3,
            max_tokens=120,
        )
        return recap.strip() if recap else None

    except Exception:
        return None
