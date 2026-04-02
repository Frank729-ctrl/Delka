"""
Background session memory extractor.

Inspired by Claude Code's SessionMemory + extractMemories services.

After every chat reply, this runs as a background asyncio task — it never
blocks the streamed response. It:
1. Looks at the last N messages
2. Asks a small/fast model to extract anything worth remembering
3. Appends structured memory entries to a per-user markdown file in the DB

Delka improvements over Claude Code src:
- Stores memories in the DB (not just local files) so they're available
  across devices and deployments
- Uses 4-type taxonomy: user, feedback, project, reference
- Deduplicates against existing memories before writing
- Runs on every reply (not just every N tool calls) because our sessions
  are shorter and cheaper than desktop IDE sessions
"""
from __future__ import annotations

import asyncio
import json
from sqlalchemy.ext.asyncio import AsyncSession

_EXTRACT_SYSTEM = """You are a memory extraction agent for Delka AI.

Analyze the conversation excerpt and extract only facts worth remembering long-term.
Use this 4-type taxonomy:

TYPE: user
- User's role, job, skills, goals, location, preferences
- Example: "user is a frontend developer in Accra"

TYPE: feedback
- How the user wants Delka to behave (corrections, style preferences, things to avoid)
- Example: "user prefers bullet points over paragraphs"

TYPE: project
- Ongoing work the user is doing, deadlines, decisions made
- Example: "user is building a job board for Ghanaian companies"

TYPE: reference
- External resources, links, tools the user mentioned
- Example: "user's company is Acme at acme.com.gh"

Output JSON array. Each item: {"type": "...", "title": "...", "content": "..."}
If nothing is worth remembering, output: []

Rules:
- Only extract facts explicitly stated (never infer or guess)
- Skip small talk, greetings, and one-off questions
- Skip things already obvious from the conversation flow
- Max 3 memories per extraction run"""

_MIN_MESSAGES_TO_EXTRACT = 4  # don't run on very short exchanges


async def extract_and_store(
    user_id: str,
    platform: str,
    session_id: str,
    recent_messages: list[dict],
    db: AsyncSession,
) -> None:
    """
    Fire-and-forget: extract memories from recent messages and store them.
    Called as asyncio.create_task() so it never blocks the chat stream.
    """
    if len(recent_messages) < _MIN_MESSAGES_TO_EXTRACT:
        return

    # Only use the last 10 messages for extraction (efficiency)
    excerpt = recent_messages[-10:]
    conversation_text = "\n".join(
        f"{m['role'].upper()}: {m['content'][:400]}"
        for m in excerpt
        if m.get("role") in ("user", "assistant") and m.get("content")
    )

    try:
        from services.inference_service import generate_full_response
        raw, _, _ = await generate_full_response(
            task="support",
            system_prompt=_EXTRACT_SYSTEM,
            user_prompt=conversation_text,
            temperature=0.2,
            max_tokens=512,
        )

        # Parse JSON
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        memories: list[dict] = json.loads(raw)
        if not isinstance(memories, list):
            return

        for mem in memories[:3]:
            if not isinstance(mem, dict):
                continue
            mem_type = mem.get("type", "user")
            title = mem.get("title", "")[:100]
            content = mem.get("content", "")[:500]
            if title and content:
                await _store_memory(user_id, platform, mem_type, title, content, db)

    except Exception:
        pass  # extraction is best-effort, never surface errors to user


async def _store_memory(
    user_id: str,
    platform: str,
    mem_type: str,
    title: str,
    content: str,
    db: AsyncSession,
) -> None:
    """Write a memory entry to the session_memories table."""
    try:
        from models.session_memory_model import SessionMemory
        from sqlalchemy import select

        # Dedup: skip if a memory with same title already exists
        existing = await db.execute(
            select(SessionMemory).where(
                SessionMemory.user_id == user_id,
                SessionMemory.platform == platform,
                SessionMemory.title == title,
            )
        )
        if existing.scalar_one_or_none():
            return

        entry = SessionMemory(
            user_id=user_id,
            platform=platform,
            mem_type=mem_type,
            title=title,
            content=content,
        )
        db.add(entry)
        await db.commit()
    except Exception:
        pass


async def get_memories(
    user_id: str,
    platform: str,
    db: AsyncSession,
    limit: int = 20,
) -> str:
    """
    Return stored memories as a formatted string for system prompt injection.
    Returns empty string if no memories exist.
    """
    try:
        from models.session_memory_model import SessionMemory
        from sqlalchemy import select

        result = await db.execute(
            select(SessionMemory)
            .where(
                SessionMemory.user_id == user_id,
                SessionMemory.platform == platform,
            )
            .order_by(SessionMemory.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        if not rows:
            return ""

        lines = ["## What Delka remembers about you"]
        for r in reversed(rows):
            lines.append(f"- [{r.mem_type.upper()}] **{r.title}**: {r.content}")
        return "\n".join(lines)
    except Exception:
        return ""
