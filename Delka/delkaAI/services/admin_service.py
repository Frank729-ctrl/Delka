from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.api_key_model import APIKey
from schemas.admin_schema import KeyInfo
from security.key_store import create_key_pair as _create_pair, revoke_key as _revoke


async def create_key_pair(
    platform: str,
    owner: str,
    requires_hmac: bool,
    db: AsyncSession,
) -> dict:
    raw = await _create_pair(platform, owner, requires_hmac, db)
    return {
        "publishable_key": raw["publishable_key"],
        "secret_key": raw["secret_key"],
        "pk_prefix": raw["pk_prefix"],
        "sk_prefix": raw["sk_prefix"],
        **({"hmac_secret": raw["hmac_secret"]} if requires_hmac else {}),
        "platform": platform,
        "owner": owner,
        "warning": "Save these keys now. They will not be shown again.",
    }


async def revoke_key(prefix: str, db: AsyncSession) -> bool:
    return await _revoke(prefix, db)


async def list_api_keys(db: AsyncSession) -> list[KeyInfo]:
    result = await db.execute(
        select(APIKey).order_by(APIKey.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        KeyInfo(
            raw_prefix=r.raw_prefix,
            key_type=r.key_type,
            platform=r.platform,
            owner=r.owner,
            is_active=r.is_active,
            is_flagged=r.is_flagged,
            violation_count=r.violation_count,
            usage_count=r.usage_count,
            created_at=r.created_at,
            last_used_at=r.last_used_at,
        )
        for r in rows
    ]


async def get_key_usage(prefix: str, db: AsyncSession) -> dict:
    result = await db.execute(
        select(APIKey).where(APIKey.raw_prefix == prefix)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return {}
    return {
        "raw_prefix": record.raw_prefix,
        "usage_count": record.usage_count,
        "last_used_at": record.last_used_at.isoformat() if record.last_used_at else None,
        "ip_history": record.ip_history or [],
        "last_ip": record.last_ip,
        "violation_count": record.violation_count,
        "is_flagged": record.is_flagged,
        "is_active": record.is_active,
    }
