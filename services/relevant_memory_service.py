"""
Relevant memory retrieval — inspired by Claude Code's findRelevantMemories.ts

Instead of loading ALL memory every turn, this service:
1. Scans all memory entries (user profile, feedback, project notes)
2. Asks a fast LLM to pick which ones are relevant to the current query
3. Returns only those, keeping the system prompt lean

This means the more memories Delka accumulates over time, the smarter it
gets at choosing what to recall — just like Claude Code's memdir selector.
"""
import asyncio
import json
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

_SELECTOR_SYSTEM = """You select which memory entries are relevant to a user's query.

You will receive:
- The user's current message
- A list of memory entries with their type and a short description

Return a JSON array of the IDs of memory entries that are CLEARLY useful for answering this specific query.
Be selective — only include memories that genuinely matter for this query.
If no memories are relevant, return [].

Respond with ONLY a JSON array of integer IDs, nothing else. Example: [1, 4, 7]
"""


@dataclass
class MemoryEntry:
    id: int
    type: str       # user | feedback | project | reference
    key: str        # short label e.g. "user_role", "feedback_testing"
    value: str      # full content


async def get_relevant_memories(
    query: str,
    user_id: str,
    platform: str,
    db: AsyncSession,
    max_memories: int = 5,
) -> list[MemoryEntry]:
    """
    Returns at most `max_memories` memory entries that are relevant to `query`.
    Falls back to returning the most recent entries if the selector fails.
    """
    all_entries = await _load_all_memories(user_id, platform, db)
    if not all_entries:
        return []

    # If we have few entries, just return them all — no need for AI selection
    if len(all_entries) <= max_memories:
        return all_entries

    selected = await _select_relevant(query, all_entries)
    if selected:
        return selected[:max_memories]

    # Fallback: return the most recent entries
    return all_entries[-max_memories:]


async def _load_all_memories(
    user_id: str,
    platform: str,
    db: AsyncSession,
) -> list[MemoryEntry]:
    """Load all structured memories for this user from the DB."""
    entries: list[MemoryEntry] = []

    # Load from session_memory table (structured key-value memories)
    try:
        from sqlalchemy import text
        result = await db.execute(
            text(
                "SELECT id, memory_type, memory_key, memory_value "
                "FROM session_memories "
                "WHERE user_id = :uid AND platform = :pl "
                "ORDER BY updated_at DESC LIMIT 100"
            ),
            {"uid": user_id, "pl": platform},
        )
        for row in result.fetchall():
            entries.append(MemoryEntry(
                id=row[0],
                type=row[1],
                key=row[2],
                value=row[3][:300],  # truncate for selector prompt
            ))
    except Exception:
        pass

    # Also pull key facts from the memory profile (flat JSON blob)
    try:
        from services import memory_service
        profile = await memory_service.get_or_create_profile(user_id, platform, db)
        if profile:
            profile_dict = profile if isinstance(profile, dict) else (
                profile.__dict__ if hasattr(profile, "__dict__") else {}
            )
            for k, v in profile_dict.items():
                if k.startswith("_") or not v:
                    continue
                entries.append(MemoryEntry(
                    id=10000 + len(entries),
                    type="user",
                    key=k,
                    value=str(v)[:200],
                ))
    except Exception:
        pass

    return entries


async def _select_relevant(
    query: str,
    entries: list[MemoryEntry],
) -> list[MemoryEntry]:
    """Use a fast LLM to pick which memory entries are relevant."""
    try:
        # Build the selection prompt
        lines = [f"User query: {query[:300]}\n\nMemory entries:"]
        for e in entries:
            lines.append(f"ID {e.id} | type={e.type} | key={e.key} | {e.value[:120]}")
        selector_prompt = "\n".join(lines)

        from services.inference_service import generate_full_response
        response, _, _ = await generate_full_response(
            task="support",   # use the fast chat model
            system_prompt=_SELECTOR_SYSTEM,
            user_prompt=selector_prompt,
            temperature=0.0,
            max_tokens=64,
        )

        selected_ids = set(json.loads(response.strip()))
        id_map = {e.id: e for e in entries}
        return [id_map[i] for i in selected_ids if i in id_map]
    except Exception:
        return []


def format_memories_for_prompt(entries: list[MemoryEntry]) -> str:
    """Format selected memories into a system prompt section."""
    if not entries:
        return ""
    lines = ["RELEVANT MEMORY (recalled for this query):"]
    for e in entries:
        lines.append(f"[{e.type.upper()}] {e.key}: {e.value}")
    return "\n".join(lines)
