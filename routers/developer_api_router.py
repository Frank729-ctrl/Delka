"""JSON API endpoints for the external developer console."""
from fastapi import APIRouter, Header, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

from database import AsyncSessionLocal
from config import settings
from services.developer_auth_service import (
    register_developer, login_developer, get_session, logout_developer,
    clerk_provision_developer,
)
from services.console_service import get_developer_overview, get_developer_keys

router = APIRouter(prefix="/v1/developer", tags=["Developer API"])


@router.get("/ping")
async def developer_ping():
    return {"developer_router": "ok"}


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    company: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


async def _require_session(token: str | None):
    if not token:
        raise HTTPException(status_code=401, detail="Session token required.")
    async with AsyncSessionLocal() as db:
        account = await get_session(token, db)
    if not account:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return account


@router.post("/register")
async def developer_register(body: RegisterRequest):
    async with AsyncSessionLocal() as db:
        result = await register_developer(body.email, body.password, body.full_name, body.company, db)
    if not result["success"]:
        raise HTTPException(status_code=409, detail="Email already in use.")
    return {"success": True}


@router.post("/login")
async def developer_login(body: LoginRequest, request: Request):
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    async with AsyncSessionLocal() as db:
        result = await login_developer(body.email, body.password, ip, ua, db)
    if not result["success"]:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return {"success": True, "session_token": result["session_token"], "expires_at": result["expires_at"]}


@router.post("/logout")
async def developer_logout(x_delkai_session: str | None = Header(default=None)):
    if x_delkai_session:
        async with AsyncSessionLocal() as db:
            await logout_developer(x_delkai_session, db)
    return {"success": True}


@router.get("/me")
async def developer_me(x_delkai_session: str | None = Header(default=None)):
    account = await _require_session(x_delkai_session)
    return {
        "email": account.email,
        "full_name": account.full_name,
        "company": account.company,
        "is_active": account.is_active,
        "created_at": account.created_at.isoformat(),
    }


@router.get("/overview")
async def developer_overview(x_delkai_session: str | None = Header(default=None)):
    account = await _require_session(x_delkai_session)
    async with AsyncSessionLocal() as db:
        overview = await get_developer_overview(account.email, db)
    return overview


class CreateKeyRequest(BaseModel):
    key_name: str


class RevokeKeyRequest(BaseModel):
    key_prefix: str


@router.post("/keys/create")
async def developer_create_key(
    body: CreateKeyRequest,
    x_delkai_session: str | None = Header(default=None),
):
    account = await _require_session(x_delkai_session)
    # Limit to 10 keys per developer
    async with AsyncSessionLocal() as db:
        existing = await get_developer_keys(account.email, db)
    if len(existing) >= 10:
        raise HTTPException(status_code=429, detail="Key limit reached (max 10 per account).")
    async with AsyncSessionLocal() as db:
        from security.key_store import create_key_pair
        result = await create_key_pair(
            platform=body.key_name,
            owner=account.email,
            requires_hmac=False,
            db=db,
        )
    return result


@router.post("/keys/revoke")
async def developer_revoke_key(
    body: RevokeKeyRequest,
    x_delkai_session: str | None = Header(default=None),
):
    account = await _require_session(x_delkai_session)
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from models.api_key_model import APIKey
        result = await db.execute(
            select(APIKey).where(
                APIKey.raw_prefix == body.key_prefix,
                APIKey.owner == account.email,
            )
        )
        key = result.scalar_one_or_none()
        if not key:
            raise HTTPException(status_code=404, detail="Key not found.")
        key.is_active = False
        await db.commit()
    return {"success": True}


class ClerkProvisionRequest(BaseModel):
    email: str
    full_name: str
    clerk_id: str


@router.post("/clerk-provision", include_in_schema=False)
async def developer_clerk_provision(
    body: ClerkProvisionRequest,
    x_delkaai_master_key: str | None = Header(default=None),
):
    if not x_delkaai_master_key or x_delkaai_master_key != settings.SECRET_MASTER_KEY:
        raise HTTPException(status_code=403, detail="Forbidden.")
    async with AsyncSessionLocal() as db:
        result = await clerk_provision_developer(body.email, body.full_name, body.clerk_id, db)
    return result


@router.get("/keys")
async def developer_keys_list(x_delkai_session: str | None = Header(default=None)):
    account = await _require_session(x_delkai_session)
    async with AsyncSessionLocal() as db:
        keys = await get_developer_keys(account.email, db)
    return {"keys": keys}
