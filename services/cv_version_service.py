"""
CV / Cover Letter version history — save a snapshot before every regeneration.

Inspired by Claude Code's fileHistory utility.

On each CV or letter generation:
1. Check if a previous version exists for this user+platform
2. If yes, save it as version N before overwriting
3. Keep last 5 versions per document type per user

Versions are stored as blobs in the DB alongside their metadata.
"""
import json
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

MAX_VERSIONS = 5


async def save_version(
    user_id: str,
    platform: str,
    doc_type: str,          # "cv" | "letter"
    content_bytes: bytes,   # the PDF bytes
    metadata: dict,         # e.g. {"full_name": "...", "model": "..."}
    db: AsyncSession,
) -> bool:
    """
    Save a new version of a generated document.
    Prunes old versions so we keep at most MAX_VERSIONS.
    """
    try:
        import base64
        content_b64 = base64.b64encode(content_bytes).decode()

        await db.execute(
            text(
                "INSERT INTO document_versions "
                "(user_id, platform, doc_type, content_b64, metadata_json, created_at) "
                "VALUES (:uid, :pl, :dt, :content, :meta, NOW())"
            ),
            {
                "uid": user_id,
                "pl": platform,
                "dt": doc_type,
                "content": content_b64,
                "meta": json.dumps(metadata),
            },
        )
        await db.commit()

        # Prune old versions beyond MAX_VERSIONS
        await _prune_versions(user_id, platform, doc_type, db)
        return True
    except Exception:
        return False


async def _prune_versions(
    user_id: str,
    platform: str,
    doc_type: str,
    db: AsyncSession,
) -> None:
    """Delete oldest versions beyond MAX_VERSIONS."""
    try:
        result = await db.execute(
            text(
                "SELECT id FROM document_versions "
                "WHERE user_id = :uid AND platform = :pl AND doc_type = :dt "
                "ORDER BY created_at DESC"
            ),
            {"uid": user_id, "pl": platform, "dt": doc_type},
        )
        ids = [row[0] for row in result.fetchall()]
        if len(ids) > MAX_VERSIONS:
            to_delete = ids[MAX_VERSIONS:]
            await db.execute(
                text("DELETE FROM document_versions WHERE id IN :ids"),
                {"ids": tuple(to_delete)},
            )
            await db.commit()
    except Exception:
        pass


async def list_versions(
    user_id: str,
    platform: str,
    doc_type: str,
    db: AsyncSession,
) -> list[dict]:
    """List available versions for a user (without content — metadata only)."""
    try:
        result = await db.execute(
            text(
                "SELECT id, metadata_json, created_at FROM document_versions "
                "WHERE user_id = :uid AND platform = :pl AND doc_type = :dt "
                "ORDER BY created_at DESC LIMIT :limit"
            ),
            {"uid": user_id, "pl": platform, "dt": doc_type, "limit": MAX_VERSIONS},
        )
        rows = []
        for row in result.fetchall():
            meta = {}
            try:
                meta = json.loads(row[1]) if row[1] else {}
            except Exception:
                pass
            rows.append({"id": row[0], "created_at": str(row[2]), **meta})
        return rows
    except Exception:
        return []


async def get_version(
    version_id: int,
    user_id: str,
    db: AsyncSession,
) -> bytes | None:
    """Retrieve the PDF bytes for a specific version."""
    try:
        import base64
        result = await db.execute(
            text(
                "SELECT content_b64 FROM document_versions "
                "WHERE id = :id AND user_id = :uid"
            ),
            {"id": version_id, "uid": user_id},
        )
        row = result.fetchone()
        if not row:
            return None
        return base64.b64decode(row[0])
    except Exception:
        return None
