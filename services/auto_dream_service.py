"""
AutoDream — cross-session memory consolidation.

Inspired by Claude Code's autoDream service.

Claude Code fires this when enough sessions have accumulated since the last
consolidation AND enough hours have passed. We do the same but server-side:
- Runs in the background after any chat reply
- Triggers when: sessions since last dream >= MIN_SESSIONS and hours >= MIN_HOURS
- Consolidates scattered per-session memories into a unified user profile
- Much more powerful than Claude Code's version because we have all user
  data in the DB (not just local filesystem)

Delka improvements:
- Cross-device (server-side, not local file)
- Per-platform consolidation (delkaai-console vs swypply vs hakdel)
- Merges redundant memories, resolves contradictions
- Writes back to UserMemoryProfile (the structured profile) not just free text
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

MIN_SESSIONS_BEFORE_DREAM = 5    # consolidate every 5 new sessions
MIN_HOURS_BEFORE_DREAM = 6       # but not more often than every 6 hours

_CONSOLIDATION_SYSTEM = """You are Delka's memory consolidation agent.

You are given:
1. The user's current memory profile (structured facts)
2. New session memories collected since the last consolidation

Your job: produce an updated, unified user profile by:
- Merging new facts into the existing profile
- Resolving contradictions (newer info wins)
- Removing outdated or superseded facts
- Deduplicating similar entries
- Keeping it concise (max 500 words total)

Output format — JSON object:
{
  "name": "...",
  "role": "...",
  "location": "...",
  "preferences": ["...", "..."],
  "ongoing_projects": ["...", "..."],
  "communication_style": "...",
  "feedback_rules": ["...", "..."],
  "key_facts": ["...", "..."]
}

Only include fields where you have reliable information. Skip empty fields."""


async def maybe_dream(
    user_id: str,
    platform: str,
    db: AsyncSession,
) -> None:
    """
    Check if consolidation should run and fire it as a background task.
    Called after each chat reply — fast check, slow work happens async.
    """
    try:
        if not await _should_dream(user_id, platform, db):
            return
        asyncio.create_task(_run_dream(user_id, platform, db))
    except Exception:
        pass


async def _should_dream(user_id: str, platform: str, db: AsyncSession) -> bool:
    """Return True if enough sessions and time have passed."""
    try:
        from models.session_memory_model import SessionMemory
        from sqlalchemy import select, func

        # Count session memories created since last consolidation
        from services import memory_service
        profile = await memory_service.get_or_create_profile(user_id, platform, db)
        last_dream = getattr(profile, "last_dream_at", None)

        if last_dream:
            hours_since = (datetime.utcnow() - last_dream).total_seconds() / 3600
            if hours_since < MIN_HOURS_BEFORE_DREAM:
                return False

        since = last_dream or (datetime.utcnow() - timedelta(days=30))
        count_result = await db.execute(
            select(func.count(SessionMemory.id)).where(
                SessionMemory.user_id == user_id,
                SessionMemory.platform == platform,
                SessionMemory.created_at > since,
            )
        )
        new_memory_count = count_result.scalar() or 0
        return new_memory_count >= MIN_SESSIONS_BEFORE_DREAM
    except Exception:
        return False


async def _run_dream(user_id: str, platform: str, db: AsyncSession) -> None:
    """Consolidate all session memories into the user profile."""
    try:
        from services.session_memory_service import get_memories
        from services import memory_service
        from services.inference_service import generate_full_response
        import json

        # Load current profile + all session memories
        profile = await memory_service.get_or_create_profile(user_id, platform, db)
        memories_text = await get_memories(user_id, platform, db, limit=50)

        if not memories_text:
            return

        current_profile_text = (
            f"Name: {profile.name or 'unknown'}\n"
            f"Role: {profile.role or 'unknown'}\n"
            f"Location: {profile.location or 'unknown'}\n"
            f"Preferences: {profile.preferences or ''}\n"
            f"Notes: {profile.notes or ''}"
        )

        raw, _, _ = await generate_full_response(
            task="support",
            system_prompt=_CONSOLIDATION_SYSTEM,
            user_prompt=(
                f"CURRENT PROFILE:\n{current_profile_text}\n\n"
                f"NEW SESSION MEMORIES:\n{memories_text}"
            ),
            temperature=0.2,
            max_tokens=800,
        )

        # Parse and apply
        raw = raw.strip().lstrip("```json").rstrip("```").strip()
        consolidated = json.loads(raw)

        updates = {}
        if consolidated.get("name"):
            updates["name"] = consolidated["name"]
        if consolidated.get("role"):
            updates["role"] = consolidated["role"]
        if consolidated.get("location"):
            updates["location"] = consolidated["location"]
        if consolidated.get("preferences"):
            updates["preferences"] = ", ".join(consolidated["preferences"])
        extra_notes = []
        if consolidated.get("ongoing_projects"):
            extra_notes.append("Projects: " + "; ".join(consolidated["ongoing_projects"]))
        if consolidated.get("feedback_rules"):
            extra_notes.append("Style rules: " + "; ".join(consolidated["feedback_rules"]))
        if consolidated.get("key_facts"):
            extra_notes.append("Key facts: " + "; ".join(consolidated["key_facts"]))
        if extra_notes:
            updates["notes"] = "\n".join(extra_notes)
        updates["last_dream_at"] = datetime.utcnow()

        await memory_service.update_profile(user_id, platform, updates, db)

    except Exception:
        pass
