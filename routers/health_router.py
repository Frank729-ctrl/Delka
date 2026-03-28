import httpx
from fastapi import APIRouter
from config import settings

router = APIRouter(tags=["health"])


@router.get("/v1/ping")
async def ping():
    return {"pong": True}


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
