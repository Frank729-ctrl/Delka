"""
Document Workspace — exceeds Claude Code's file system tools (Read/Write/Edit/Glob/Grep).

src: Read, Write, Edit, Glob, Grep tools let the AI work with the user's local files.
Delka: Cloud workspace — users upload files to their personal workspace, the AI
       can read them, search across them, and edit them. Persists across sessions.
       No local file system access needed.

Workspace operations:
- upload(user_id, filename, content)   — store a file
- read(user_id, filename)              — read a file's content
- search(user_id, query)               — keyword search across all user files
- edit(user_id, filename, old, new)    — targeted string replacement
- list_files(user_id)                  — list all user's files with metadata
- delete(user_id, filename)            — remove a file

Files stored in DB as compressed text blobs (base64 for binary, utf-8 for text).
Max file size: 500KB. Max files per user: 50.

Used by: chat_service (AI reads user files on request),
         doc_qa_service (workspace files as document sources),
         cv_service (auto-saves generated CVs to workspace).
"""
import re
import time
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


_MAX_FILE_SIZE = 500_000   # 500KB
_MAX_FILES_PER_USER = 50


# ── Core operations ───────────────────────────────────────────────────────────

async def upload_file(
    user_id: str,
    platform: str,
    filename: str,
    content: str,
    file_type: str = "text",
    db: AsyncSession = None,
) -> dict:
    """Store or overwrite a file in the user's workspace."""
    if len(content) > _MAX_FILE_SIZE:
        return {"error": f"File too large (max {_MAX_FILE_SIZE // 1000}KB)"}

    # Check file count limit
    count_result = await db.execute(
        text("SELECT COUNT(*) FROM workspace_files WHERE user_id = :uid AND platform = :pl"),
        {"uid": user_id, "pl": platform},
    )
    count = count_result.scalar() or 0
    if count >= _MAX_FILES_PER_USER:
        return {"error": f"Workspace full (max {_MAX_FILES_PER_USER} files). Delete some files first."}

    try:
        await db.execute(
            text(
                "INSERT INTO workspace_files "
                "(user_id, platform, filename, content, file_type, size_bytes, updated_at) "
                "VALUES (:uid, :pl, :fn, :ct, :ft, :sz, NOW()) "
                "ON DUPLICATE KEY UPDATE content = :ct, file_type = :ft, size_bytes = :sz, updated_at = NOW()"
            ),
            {
                "uid": user_id, "pl": platform,
                "fn": filename[:255], "ct": content,
                "ft": file_type, "sz": len(content.encode("utf-8")),
            },
        )
        await db.commit()
        return {"status": "ok", "filename": filename, "size": len(content)}
    except Exception as e:
        return {"error": str(e)[:200]}


async def read_file(
    user_id: str,
    platform: str,
    filename: str,
    db: AsyncSession,
) -> Optional[str]:
    """Read a file from the workspace. Returns None if not found."""
    try:
        result = await db.execute(
            text(
                "SELECT content FROM workspace_files "
                "WHERE user_id = :uid AND platform = :pl AND filename = :fn"
            ),
            {"uid": user_id, "pl": platform, "fn": filename},
        )
        row = result.fetchone()
        return row[0] if row else None
    except Exception:
        return None


async def search_workspace(
    user_id: str,
    platform: str,
    query: str,
    db: AsyncSession,
    max_results: int = 5,
) -> list[dict]:
    """
    Search all user files for a keyword/phrase.
    Returns list of {filename, snippet, match_count}.
    """
    try:
        result = await db.execute(
            text(
                "SELECT filename, content FROM workspace_files "
                "WHERE user_id = :uid AND platform = :pl"
            ),
            {"uid": user_id, "pl": platform},
        )
        rows = result.fetchall()
    except Exception:
        return []

    results = []
    query_lower = query.lower()
    query_words = query_lower.split()

    for filename, content in rows:
        content_lower = content.lower()
        match_count = sum(content_lower.count(w) for w in query_words)
        if match_count == 0:
            continue

        # Find a good snippet around the first match
        idx = content_lower.find(query_words[0])
        start = max(0, idx - 100)
        end = min(len(content), idx + 200)
        snippet = content[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet += "..."

        results.append({
            "filename": filename,
            "snippet": snippet,
            "match_count": match_count,
        })

    results.sort(key=lambda x: x["match_count"], reverse=True)
    return results[:max_results]


async def edit_file(
    user_id: str,
    platform: str,
    filename: str,
    old_string: str,
    new_string: str,
    db: AsyncSession,
) -> dict:
    """
    Replace old_string with new_string in a workspace file.
    Fails if old_string not found or appears multiple times (ambiguous).
    """
    content = await read_file(user_id, platform, filename, db)
    if content is None:
        return {"error": f"File '{filename}' not found in workspace"}

    occurrences = content.count(old_string)
    if occurrences == 0:
        return {"error": f"String not found in '{filename}'"}
    if occurrences > 1:
        return {"error": f"String appears {occurrences} times in '{filename}' — provide more context to make it unique"}

    new_content = content.replace(old_string, new_string, 1)
    result = await upload_file(user_id, platform, filename, new_content, db=db)
    if "error" in result:
        return result
    return {"status": "ok", "filename": filename, "chars_changed": abs(len(new_string) - len(old_string))}


async def list_files(
    user_id: str,
    platform: str,
    db: AsyncSession,
) -> list[dict]:
    """List all files in the user's workspace with metadata."""
    try:
        result = await db.execute(
            text(
                "SELECT filename, file_type, size_bytes, updated_at "
                "FROM workspace_files WHERE user_id = :uid AND platform = :pl "
                "ORDER BY updated_at DESC"
            ),
            {"uid": user_id, "pl": platform},
        )
        return [
            {
                "filename": row[0],
                "type": row[1],
                "size_kb": round(row[2] / 1024, 1),
                "updated_at": str(row[3]),
            }
            for row in result.fetchall()
        ]
    except Exception:
        return []


async def delete_file(
    user_id: str,
    platform: str,
    filename: str,
    db: AsyncSession,
) -> bool:
    """Delete a file from the workspace."""
    try:
        await db.execute(
            text(
                "DELETE FROM workspace_files "
                "WHERE user_id = :uid AND platform = :pl AND filename = :fn"
            ),
            {"uid": user_id, "pl": platform, "fn": filename},
        )
        await db.commit()
        return True
    except Exception:
        return False


# ── Context builder ───────────────────────────────────────────────────────────

def build_workspace_context(files: list[dict], search_results: list[dict] = None) -> str:
    """Format workspace info as system prompt context."""
    if not files and not search_results:
        return ""

    lines = ["[User Workspace]"]
    if files:
        lines.append(f"Files ({len(files)}): " + ", ".join(f['filename'] for f in files[:10]))

    if search_results:
        lines.append("\nRelevant file excerpts:")
        for r in search_results:
            lines.append(f"\n— {r['filename']}:\n{r['snippet']}")

    return "\n".join(lines)


# ── Intent detection ──────────────────────────────────────────────────────────

_WORKSPACE_RE = re.compile(
    r"\b(my (files?|documents?|workspace|cv|resume|letter)|"
    r"(read|open|show|find|search|edit|update|change) (my|the) (file|document|cv|resume)|"
    r"(in|from|across) my (files?|workspace|documents?))\b",
    re.IGNORECASE,
)


def needs_workspace(message: str) -> bool:
    return bool(_WORKSPACE_RE.search(message))
