"""Data aggregation helpers for the developer console."""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.api_key_model import APIKey
from models.usage_log_model import UsageLog
from models.platform_registry_model import PlatformRegistry
from services.metrics_service import get_summary


async def get_developer_overview(developer_email: str, db: AsyncSession) -> dict:
    """Aggregate stats for a developer's console overview page."""
    keys_result = await db.execute(
        select(APIKey).where(APIKey.owner == developer_email)
    )
    keys = keys_result.scalars().all()

    active_count = sum(1 for k in keys if k.is_active)
    total_usage = sum(k.usage_count for k in keys)

    metrics = await get_summary()

    return {
        "total_keys": len(keys),
        "active_keys": active_count,
        "total_requests": total_usage,
        "avg_response_ms": metrics.get("avg_response_ms", 0),
        "error_rate": metrics.get("error_rate", 0.0),
    }


async def get_developer_keys(developer_email: str, db: AsyncSession) -> list[dict]:
    """Return all API keys owned by this developer."""
    result = await db.execute(
        select(APIKey)
        .where(APIKey.owner == developer_email)
        .order_by(APIKey.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "raw_prefix": r.raw_prefix,
            "key_type": r.key_type,
            "platform": r.platform,
            "is_active": r.is_active,
            "usage_count": r.usage_count,
            "created_at": r.created_at.isoformat(),
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
        }
        for r in rows
    ]


async def get_platform_list(db: AsyncSession) -> list[dict]:
    """Return registered platforms."""
    result = await db.execute(
        select(PlatformRegistry).order_by(PlatformRegistry.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "platform_name": r.platform_name,
            "owner_email": r.owner_email,
            "description": r.description,
            "webhook_url": r.webhook_url,
            "is_active": r.is_active,
            "requires_hmac": r.requires_hmac,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


async def register_platform(
    platform_name: str,
    owner_email: str,
    description: str | None,
    webhook_url: str | None,
    requires_hmac: bool,
    db: AsyncSession,
) -> dict:
    existing = await db.execute(
        select(PlatformRegistry).where(PlatformRegistry.platform_name == platform_name)
    )
    if existing.scalar_one_or_none():
        return {"success": False, "error": "platform_exists"}

    platform = PlatformRegistry(
        platform_name=platform_name,
        owner_email=owner_email,
        description=description,
        webhook_url=webhook_url,
        requires_hmac=requires_hmac,
    )
    db.add(platform)
    await db.commit()
    return {"success": True, "platform_name": platform_name}
