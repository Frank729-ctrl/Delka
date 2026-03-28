import httpx
from fastapi import APIRouter, Request, Header, HTTPException
from config import settings

router = APIRouter(tags=["health"])


# ── Developer key management (lazy imports — guaranteed to load) ──────────────

def _check_master(key: str | None) -> None:
    if not key or key != settings.SECRET_MASTER_KEY:
        raise HTTPException(status_code=401, detail="Invalid master key.")


@router.post("/v1/admin/dev-keys/create")
async def dev_keys_create(
    request: Request,
    x_delkaai_master_key: str | None = Header(default=None),
):
    _check_master(x_delkaai_master_key)
    body = await request.json()
    owner    = body.get("owner", "").strip().lower()
    key_name = body.get("key_name", "").strip()
    if not owner or not key_name:
        raise HTTPException(status_code=422, detail="owner and key_name required.")

    from database import AsyncSessionLocal
    from security.key_store import create_key_pair
    async with AsyncSessionLocal() as db:
        result = await create_key_pair(platform=key_name, owner=owner,
                                       requires_hmac=False, db=db)
    return result


@router.get("/v1/admin/dev-keys/list")
async def dev_keys_list(
    owner: str,
    x_delkaai_master_key: str | None = Header(default=None),
):
    _check_master(x_delkaai_master_key)
    from database import AsyncSessionLocal
    from sqlalchemy import select
    from models.api_key_model import APIKey
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(APIKey).where(APIKey.owner == owner.strip().lower())
        )
        keys = rows.scalars().all()
    return {"keys": [
        {
            "raw_prefix":   k.raw_prefix,
            "key_type":     k.key_type,
            "platform":     k.platform,
            "owner":        k.owner,
            "is_active":    k.is_active,
            "usage_count":  k.usage_count,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "created_at":   k.created_at.isoformat() if k.created_at else None,
        }
        for k in keys
    ]}


@router.post("/v1/admin/dev-keys/revoke")
async def dev_keys_revoke(
    request: Request,
    x_delkaai_master_key: str | None = Header(default=None),
):
    _check_master(x_delkaai_master_key)
    body = await request.json()
    prefix = body.get("key_prefix", "").strip()
    if not prefix:
        raise HTTPException(status_code=422, detail="key_prefix required.")

    from database import AsyncSessionLocal
    from security.key_store import revoke_key
    async with AsyncSessionLocal() as db:
        ok = await revoke_key(prefix, db)
    if not ok:
        raise HTTPException(status_code=404, detail="Key not found.")
    return {"success": True}


@router.post("/v1/admin/console-support")
async def console_support(
    request: Request,
    x_delkaai_master_key: str | None = Header(default=None),
):
    """Support chat for the developer console — master-key authenticated, returns full JSON response."""
    _check_master(x_delkaai_master_key)
    body = await request.json()
    message    = body.get("message", "").strip()
    session_id = body.get("session_id", "console-default")
    user_id    = body.get("user_id", "console-user")
    if not message:
        raise HTTPException(status_code=422, detail="message required.")

    from services.support_service import get_plain_reply
    from database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        reply, out_session = await get_plain_reply(
            message=message,
            session_id=session_id,
            user_id=user_id,
            platform="delkaai-console",
            db=db,
        )
    return {"reply": reply, "session_id": out_session}


@router.get("/v1/health")
async def health():
    # ── Groq status ──────────────────────────────────────────────
    groq_status = "available" if settings.GROQ_API_KEY else "not_configured"

    # ── Ollama status ────────────────────────────────────────────
    ollama_status = "unreachable"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                ollama_status = "ok"
    except Exception:
        pass

    # ── Overall status ───────────────────────────────────────────
    # Degraded only if ALL providers are unavailable
    all_down = groq_status == "not_configured" and ollama_status == "unreachable"
    overall = "degraded" if all_down else "ok"

    return {
        "status": overall,
        "version": "1.0.0",
        "providers": {
            "groq": groq_status,
            "ollama": ollama_status,
        },
        "models": {
            "cv": f"{settings.CV_PRIMARY_MODEL} via {settings.CV_PRIMARY_PROVIDER}",
            "letter": f"{settings.LETTER_PRIMARY_MODEL} via {settings.LETTER_PRIMARY_PROVIDER}",
            "support": f"{settings.SUPPORT_PRIMARY_MODEL} via {settings.SUPPORT_PRIMARY_PROVIDER}",
        },
        "fallbacks": {
            "cv": f"{settings.CV_FALLBACK_MODEL} via {settings.CV_FALLBACK_PROVIDER}",
            "letter": f"{settings.LETTER_FALLBACK_MODEL} via {settings.LETTER_FALLBACK_PROVIDER}",
            "support": f"{settings.SUPPORT_FALLBACK_MODEL} via {settings.SUPPORT_FALLBACK_PROVIDER}",
        },
    }
