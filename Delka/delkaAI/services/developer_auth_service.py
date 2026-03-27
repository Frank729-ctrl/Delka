"""Developer account registration, login, and session management."""
import secrets
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.developer_account_model import DeveloperAccount
from models.developer_session_model import DeveloperSession
from utils.logger import request_logger

_ph = PasswordHasher()
_SESSION_TTL_HOURS = 24


async def register_developer(
    email: str,
    password: str,
    full_name: str,
    company: str | None,
    db: AsyncSession,
) -> dict:
    existing = await db.execute(
        select(DeveloperAccount).where(DeveloperAccount.email == email.lower())
    )
    if existing.scalar_one_or_none() is not None:
        return {"success": False, "error": "email_taken"}

    pw_hash = _ph.hash(password)
    account = DeveloperAccount(
        email=email.lower(),
        password_hash=pw_hash,
        full_name=full_name,
        company=company,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    request_logger.info(f"developer_auth: registered email={email}")
    return {"success": True, "developer_id": account.id}


async def login_developer(
    email: str,
    password: str,
    ip_address: str | None,
    user_agent: str | None,
    db: AsyncSession,
) -> dict:
    result = await db.execute(
        select(DeveloperAccount).where(DeveloperAccount.email == email.lower())
    )
    account = result.scalar_one_or_none()
    if account is None:
        return {"success": False, "error": "invalid_credentials"}

    try:
        _ph.verify(account.password_hash, password)
    except VerifyMismatchError:
        return {"success": False, "error": "invalid_credentials"}

    if not account.is_active:
        return {"success": False, "error": "account_disabled"}

    token = secrets.token_hex(64)
    expires_at = datetime.utcnow() + timedelta(hours=_SESSION_TTL_HOURS)
    session = DeveloperSession(
        session_token=token,
        developer_id=account.id,
        ip_address=ip_address,
        user_agent=user_agent,
        expires_at=expires_at,
    )
    db.add(session)
    account.last_login_at = datetime.utcnow()
    await db.commit()

    request_logger.info(f"developer_auth: login email={email}")
    return {"success": True, "session_token": token, "expires_at": expires_at.isoformat()}


async def get_session(token: str, db: AsyncSession) -> DeveloperAccount | None:
    """Return the DeveloperAccount for a valid, unexpired session token, or None."""
    result = await db.execute(
        select(DeveloperSession).where(
            DeveloperSession.session_token == token,
            DeveloperSession.is_active == True,  # noqa: E712
        )
    )
    session = result.scalar_one_or_none()
    if session is None or session.expires_at < datetime.utcnow():
        return None

    acc_result = await db.execute(
        select(DeveloperAccount).where(DeveloperAccount.id == session.developer_id)
    )
    return acc_result.scalar_one_or_none()


async def logout_developer(token: str, db: AsyncSession) -> bool:
    result = await db.execute(
        select(DeveloperSession).where(DeveloperSession.session_token == token)
    )
    session = result.scalar_one_or_none()
    if session is None:
        return False
    session.is_active = False
    await db.commit()
    return True
