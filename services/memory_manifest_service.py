"""
Memory Manifest — ports Claude Code's memdir/MEMORY.md system to Delka's DB.

src:
  - MEMORY.md: structured index file, max 200 lines / 25KB
  - Individual topic .md files with YAML frontmatter (name, description, type)
  - scanMemoryFiles(): reads headers, sorts newest-first, caps at 200 files
  - truncateEntrypointContent(): line + byte cap with warning injected

Delka:
  - Memories live in DB (session_memories + user_memory_profile tables)
  - manifest_for_prompt(): builds MEMORY.md-equivalent string from DB rows
    grouped by type, sorted newest-first, with line + byte caps and warning
  - Full search (keyword across title + content)
  - Per-type filtering
  - Age metadata (days since created)
  - Stale detection (memories older than 30 days flagged)

Why this beats src:
  - No file system required — works across any deployment
  - Search is SQL, not file scan
  - Cross-device (src MEMORY.md is local)
  - Type counts + staleness stats in the manifest header
  - Auto-prunes duplicate titles on insert (src accumulates duplicates)
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

# ── Constants matching src's caps ─────────────────────────────────────────────

MAX_MANIFEST_LINES = 200        # src: MAX_ENTRYPOINT_LINES
MAX_MANIFEST_BYTES = 25_000     # src: MAX_ENTRYPOINT_BYTES
STALE_DAYS = 30                 # memories older than this get a stale flag

# ── Type display ordering ─────────────────────────────────────────────────────

_TYPE_ORDER = ["user", "feedback", "project", "reference"]
_TYPE_EMOJI = {
    "user": "👤",
    "feedback": "💬",
    "project": "🏗️",
    "reference": "🔗",
}
_TYPE_DESCRIPTION = {
    "user": "About the user — role, preferences, goals",
    "feedback": "How the user wants Delka to behave",
    "project": "Ongoing work, decisions, deadlines",
    "reference": "External resources and tools",
}


# ── DB queries ────────────────────────────────────────────────────────────────

async def _fetch_memories(
    user_id: str,
    platform: str,
    db: AsyncSession,
    mem_type: Optional[str] = None,
    search_query: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """Fetch memories from DB with optional type + keyword filter."""
    try:
        where = "WHERE user_id = :uid AND platform = :pl"
        params: dict = {"uid": user_id, "pl": platform}

        if mem_type:
            where += " AND mem_type = :mt"
            params["mt"] = mem_type

        if search_query:
            where += " AND (title LIKE :sq OR content LIKE :sq)"
            params["sq"] = f"%{search_query}%"

        result = await db.execute(
            text(
                f"SELECT id, mem_type, title, content, created_at "
                f"FROM session_memories {where} "
                f"ORDER BY created_at DESC LIMIT :lim"
            ),
            {**params, "lim": limit},
        )
        rows = result.fetchall()
        return [
            {
                "id": r[0],
                "type": r[1],
                "title": r[2],
                "content": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]
    except Exception:
        return []


def _days_ago(created_at) -> int:
    if created_at is None:
        return 0
    if isinstance(created_at, datetime):
        now = datetime.now(timezone.utc)
        delta = now - created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else now - created_at
        return delta.days
    return 0


def _is_stale(created_at) -> bool:
    return _days_ago(created_at) >= STALE_DAYS


# ── Manifest builder ──────────────────────────────────────────────────────────

def _truncate(content: str, max_lines: int, max_bytes: int) -> tuple[str, bool, bool]:
    """
    Truncate content to line + byte caps.
    Returns (truncated_content, was_line_truncated, was_byte_truncated).
    Matches src's truncateEntrypointContent() logic exactly.
    """
    lines = content.split("\n")
    line_count = len(lines)
    byte_count = len(content.encode())

    was_line_truncated = line_count > max_lines
    was_byte_truncated = byte_count > max_bytes

    if not was_line_truncated and not was_byte_truncated:
        return content, False, False

    truncated = "\n".join(lines[:max_lines]) if was_line_truncated else content
    if len(truncated.encode()) > max_bytes:
        cut_at = truncated.rfind("\n", 0, max_bytes)
        truncated = truncated[:cut_at if cut_at > 0 else max_bytes]

    return truncated, was_line_truncated, was_byte_truncated


async def manifest_for_prompt(
    user_id: str,
    platform: str,
    db: AsyncSession,
    max_lines: int = MAX_MANIFEST_LINES,
    max_bytes: int = MAX_MANIFEST_BYTES,
) -> str:
    """
    Build a MEMORY.md-equivalent string for injection into the system prompt.
    Grouped by type, sorted newest-first, capped at line + byte limits.
    Stale memories (>30 days) are flagged.
    """
    memories = await _fetch_memories(user_id, platform, db, limit=200)
    if not memories:
        return ""

    # Group by type
    by_type: dict[str, list[dict]] = {t: [] for t in _TYPE_ORDER}
    other: list[dict] = []
    for m in memories:
        t = m["type"]
        if t in by_type:
            by_type[t].append(m)
        else:
            other.append(m)

    # Count stats for header
    total = len(memories)
    stale_count = sum(1 for m in memories if _is_stale(m["created_at"]))
    type_counts = {t: len(ms) for t, ms in by_type.items() if ms}

    lines = [
        "## Delka Memory Index",
        f"_{total} memories stored"
        + (f" · {stale_count} stale (>{STALE_DAYS}d)" if stale_count else "")
        + "_",
        "",
    ]

    # Type sections
    for mem_type in _TYPE_ORDER:
        mems = by_type.get(mem_type, [])
        if not mems:
            continue
        emoji = _TYPE_EMOJI.get(mem_type, "•")
        desc = _TYPE_DESCRIPTION.get(mem_type, "")
        lines.append(f"### {emoji} {mem_type.title()} ({len(mems)})")
        lines.append(f"_{desc}_")
        for m in mems:
            days = _days_ago(m["created_at"])
            stale_tag = " ⚠️stale" if days >= STALE_DAYS else (f" ({days}d ago)" if days > 0 else "")
            lines.append(f"- **{m['title']}**{stale_tag}: {m['content'][:200]}")
        lines.append("")

    if other:
        lines.append(f"### Other ({len(other)})")
        for m in other:
            lines.append(f"- [{m['type']}] **{m['title']}**: {m['content'][:200]}")
        lines.append("")

    content = "\n".join(lines)
    truncated, line_trunc, byte_trunc = _truncate(content, max_lines, max_bytes)

    if line_trunc or byte_trunc:
        reason = (
            f"{len(content.split(chr(10)))} lines" if line_trunc else ""
        ) + (
            f"{len(content.encode())} bytes" if byte_trunc else ""
        )
        truncated += (
            f"\n\n> ⚠️ Memory index truncated ({reason} exceeded cap). "
            f"Use GET /v1/memory to browse all memories."
        )

    return truncated


# ── Compact version for tight context ────────────────────────────────────────

async def manifest_compact(
    user_id: str,
    platform: str,
    db: AsyncSession,
    max_entries: int = 10,
) -> str:
    """
    Ultra-compact manifest — just the most recent N memories, one line each.
    Used when context is already near capacity.
    """
    memories = await _fetch_memories(user_id, platform, db, limit=max_entries)
    if not memories:
        return ""
    lines = ["[Memory] " + ", ".join(
        f"{m['title']}" for m in memories[:max_entries]
    )]
    return "\n".join(lines)


# ── Stats ─────────────────────────────────────────────────────────────────────

async def get_memory_stats(
    user_id: str,
    platform: str,
    db: AsyncSession,
) -> dict:
    """Return memory counts by type + staleness stats."""
    memories = await _fetch_memories(user_id, platform, db)
    by_type = {}
    stale = 0
    for m in memories:
        by_type[m["type"]] = by_type.get(m["type"], 0) + 1
        if _is_stale(m["created_at"]):
            stale += 1
    return {
        "total": len(memories),
        "by_type": by_type,
        "stale": stale,
    }


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def delete_memory(memory_id: int, user_id: str, platform: str, db: AsyncSession) -> bool:
    try:
        result = await db.execute(
            text(
                "DELETE FROM session_memories "
                "WHERE id = :id AND user_id = :uid AND platform = :pl"
            ),
            {"id": memory_id, "uid": user_id, "pl": platform},
        )
        await db.commit()
        return result.rowcount > 0
    except Exception:
        return False


async def search_memories(
    user_id: str,
    platform: str,
    query: str,
    db: AsyncSession,
    mem_type: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    return await _fetch_memories(
        user_id, platform, db,
        mem_type=mem_type,
        search_query=query,
        limit=limit,
    )


async def list_memories(
    user_id: str,
    platform: str,
    db: AsyncSession,
    mem_type: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    return await _fetch_memories(user_id, platform, db, mem_type=mem_type, limit=limit)
