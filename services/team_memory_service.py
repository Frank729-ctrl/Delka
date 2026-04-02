"""
Team/shared memory — inspired by Claude Code's teamMemorySync service.

Platform-level context shared across ALL users of a platform.
Useful for:
- Business-specific info (company name, products, policies)
- Shared FAQs and answers
- Platform-wide corrections and guidelines
- Common user patterns on a specific platform

Per-user memory takes precedence over team memory.
Team memory is platform-scoped, not user-scoped.
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

_CACHE: dict[str, dict] = {}  # platform → {key: value}
_CACHE_TTL_SECONDS = 300
import time
_CACHE_TS: dict[str, float] = {}


async def get_team_context(platform: str, db: AsyncSession) -> str:
    """
    Returns a formatted string of team-level context for injection
    into the system prompt. Cached per platform for 5 minutes.
    """
    now = time.time()
    if platform in _CACHE and now - _CACHE_TS.get(platform, 0) < _CACHE_TTL_SECONDS:
        entries = _CACHE[platform]
    else:
        entries = await _load_team_memory(platform, db)
        _CACHE[platform] = entries
        _CACHE_TS[platform] = now

    if not entries:
        return ""

    lines = ["PLATFORM CONTEXT (applies to all users on this platform):"]
    for key, value in entries.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


async def _load_team_memory(platform: str, db: AsyncSession) -> dict:
    """Load team memory entries from DB."""
    try:
        result = await db.execute(
            text(
                "SELECT memory_key, memory_value FROM team_memories "
                "WHERE platform = :pl ORDER BY updated_at DESC LIMIT 50"
            ),
            {"pl": platform},
        )
        return {row[0]: row[1] for row in result.fetchall()}
    except Exception:
        return {}


async def set_team_memory(
    platform: str,
    key: str,
    value: str,
    set_by: str,
    db: AsyncSession,
) -> bool:
    """
    Set or update a platform-level memory entry.
    Called by admins or via the admin API.
    """
    try:
        await db.execute(
            text(
                "INSERT INTO team_memories (platform, memory_key, memory_value, set_by, updated_at) "
                "VALUES (:pl, :k, :v, :by, NOW()) "
                "ON DUPLICATE KEY UPDATE memory_value = :v, set_by = :by, updated_at = NOW()"
            ),
            {"pl": platform, "k": key, "v": value, "by": set_by},
        )
        await db.commit()
        # Bust cache
        _CACHE.pop(platform, None)
        return True
    except Exception:
        return False


async def delete_team_memory(
    platform: str,
    key: str,
    db: AsyncSession,
) -> bool:
    """Delete a platform-level memory entry."""
    try:
        await db.execute(
            text("DELETE FROM team_memories WHERE platform = :pl AND memory_key = :k"),
            {"pl": platform, "k": key},
        )
        await db.commit()
        _CACHE.pop(platform, None)
        return True
    except Exception:
        return False


async def list_team_memory(platform: str, db: AsyncSession) -> list[dict]:
    """List all team memory entries for a platform (for admin UI)."""
    try:
        result = await db.execute(
            text(
                "SELECT memory_key, memory_value, set_by, updated_at "
                "FROM team_memories WHERE platform = :pl ORDER BY updated_at DESC"
            ),
            {"pl": platform},
        )
        return [
            {"key": r[0], "value": r[1], "set_by": r[2], "updated_at": str(r[3])}
            for r in result.fetchall()
        ]
    except Exception:
        return []
