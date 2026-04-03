"""
Permission mode API — get and set permission modes per platform.

GET  /v1/permissions/{platform}           — get current platform mode
POST /v1/permissions/{platform}           — set platform mode
GET  /v1/permissions/modes                — list all valid modes and their capabilities
POST /v1/permissions/resolve              — resolve effective mode for a request (dry-run)
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.permission_service import (
    VALID_MODES, _MODE_CAPABILITIES,
    resolve_permission, check_capability, permission_instruction,
    get_platform_permission_mode, set_platform_permission_mode,
)

router = APIRouter(prefix="/v1/permissions")


@router.get("/modes", summary="List all permission modes and their capability matrix")
async def list_modes():
    """Return all valid permission modes and what each allows/blocks."""
    modes = []
    for mode in sorted(VALID_MODES):
        caps = _MODE_CAPABILITIES[mode]
        modes.append({
            "mode": mode,
            "capabilities": caps,
            "description": _MODE_DESCRIPTIONS.get(mode, ""),
        })
    return {"status": "ok", "modes": modes}


@router.get("/{platform}", summary="Get the current permission mode for a platform")
async def get_mode(platform: str, db: AsyncSession = Depends(get_db)):
    mode = await get_platform_permission_mode(platform, db)
    return {
        "status": "ok",
        "platform": platform,
        "mode": mode or "auto",
        "source": "platform" if mode else "default",
    }


class SetModeRequest(BaseModel):
    mode: str = Field(..., description=f"One of: {', '.join(sorted(VALID_MODES))}")


@router.post("/{platform}", summary="Set the permission mode for a platform")
async def set_mode(platform: str, req: SetModeRequest, db: AsyncSession = Depends(get_db)):
    if req.mode not in VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{req.mode}'. Valid modes: {', '.join(sorted(VALID_MODES))}"
        )
    ok = await set_platform_permission_mode(platform, req.mode, db)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save permission mode")
    return {
        "status": "ok",
        "platform": platform,
        "mode": req.mode,
        "message": f"Platform '{platform}' permission mode set to '{req.mode}'",
    }


class ResolveRequest(BaseModel):
    request_mode: Optional[str] = Field(None, description="Mode from the request")
    platform_mode: Optional[str] = Field(None, description="Mode from the platform")
    api_key_mode: Optional[str] = Field(None, description="Mode from the API key")


@router.post("/resolve", summary="Dry-run permission resolution for a given request")
async def resolve_mode(req: ResolveRequest):
    """
    Show how permission modes would be resolved for a given combination.
    Useful for debugging or pre-flight checks before making requests.
    """
    profile = resolve_permission(
        request_mode=req.request_mode,
        platform_mode=req.platform_mode,
        api_key_mode=req.api_key_mode,
    )
    return {
        "status": "ok",
        "resolved_mode": profile.mode,
        "source": profile.source,
        "capabilities": {
            "can_execute_code": profile.can_execute_code,
            "can_fetch_urls": profile.can_fetch_urls,
            "can_use_tools": profile.can_use_tools,
            "can_write_memory": profile.can_write_memory,
            "requires_approval": profile.requires_approval,
            "sandbox_network": profile.sandbox_network,
        },
        "system_prompt_injection": permission_instruction(profile) or None,
    }


_MODE_DESCRIPTIONS = {
    "auto": "All capabilities enabled, no confirmation required (default)",
    "manual": "All capabilities enabled but client must confirm each tool call before execution",
    "readonly": "Read-only — no code execution, no memory writes. URL fetching and read-only tools allowed",
    "sandbox": "Code runs isolated in /tmp with no network access. Other capabilities unrestricted",
    "restricted": "Chat only — no code execution, no URL fetching, no tools, no memory writes",
}
