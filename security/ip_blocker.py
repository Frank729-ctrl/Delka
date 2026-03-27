from datetime import datetime, timedelta
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from models.blocked_ip_model import BlockedIP


async def is_ip_blocked(ip: str, db: AsyncSession) -> bool:
    result = await db.execute(
        select(BlockedIP).where(BlockedIP.ip_address == ip)
    )
    record = result.scalar_one_or_none()

    if record is None:
        return False

    if record.expires_at is not None and record.expires_at <= datetime.utcnow():
        await db.execute(delete(BlockedIP).where(BlockedIP.ip_address == ip))
        await db.commit()
        return False

    return True


async def block_ip(
    ip: str,
    reason: str,
    db: AsyncSession,
    duration_hours: float | None = None,
) -> None:
    expires_at = None
    if duration_hours is not None:
        expires_at = datetime.utcnow() + timedelta(hours=duration_hours)

    result = await db.execute(
        select(BlockedIP).where(BlockedIP.ip_address == ip)
    )
    record = result.scalar_one_or_none()

    if record:
        record.reason = reason
        record.blocked_at = datetime.utcnow()
        record.expires_at = expires_at
    else:
        db.add(BlockedIP(
            ip_address=ip,
            reason=reason,
            expires_at=expires_at,
        ))

    await db.commit()


async def list_blocked(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(BlockedIP).order_by(BlockedIP.blocked_at.desc()))
    rows = result.scalars().all()
    return [
        {
            "ip_address": r.ip_address,
            "reason": r.reason,
            "blocked_at": r.blocked_at.isoformat(),
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        }
        for r in rows
    ]


async def unblock_ip(ip: str, db: AsyncSession) -> bool:
    result = await db.execute(
        select(BlockedIP).where(BlockedIP.ip_address == ip)
    )
    record = result.scalar_one_or_none()

    if record is None:
        return False

    await db.delete(record)
    await db.commit()
    return True
