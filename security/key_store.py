from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.api_key_model import APIKey
from security.key_generator import generate_key_pair
from security.key_hasher import hash_key

_PREFIX_LEN = 20  # "fd-delka-pk-" (12) + 8 hex chars


async def get_key_by_prefix(prefix: str, db: AsyncSession) -> APIKey | None:
    result = await db.execute(
        select(APIKey).where(APIKey.raw_prefix == prefix)
    )
    return result.scalar_one_or_none()


async def create_key_pair(
    platform: str,
    owner: str,
    requires_hmac: bool,
    db: AsyncSession,
) -> dict:
    pair = generate_key_pair()
    pk_raw = pair["publishable_key"]
    sk_raw = pair["secret_key"]
    hmac_raw = pair["hmac_secret"]

    pk_record = APIKey(
        raw_prefix=pk_raw[:_PREFIX_LEN],
        key_hash=hash_key(pk_raw),
        key_type="pk",
        platform=platform,
        owner=owner,
        requires_hmac=requires_hmac,
        # Store raw HMAC secret (not hashed) so middleware can retrieve it for verification.
        # Field name is legacy; the value is the raw secret, access-controlled by key auth.
        hmac_secret_hash=hmac_raw if requires_hmac else None,
        ip_history=[],
    )
    sk_record = APIKey(
        raw_prefix=sk_raw[:_PREFIX_LEN],
        key_hash=hash_key(sk_raw),
        key_type="sk",
        platform=platform,
        owner=owner,
        requires_hmac=requires_hmac,
        hmac_secret_hash=hmac_raw if requires_hmac else None,
        ip_history=[],
    )

    db.add(pk_record)
    db.add(sk_record)
    await db.commit()

    result = {
        "publishable_key": pk_raw,
        "secret_key": sk_raw,
        "pk_prefix": pk_raw[:_PREFIX_LEN],
        "sk_prefix": sk_raw[:_PREFIX_LEN],
    }
    if requires_hmac:
        result["hmac_secret"] = hmac_raw

    return result


async def revoke_key(prefix: str, db: AsyncSession) -> bool:
    record = await get_key_by_prefix(prefix, db)
    if record is None:
        return False
    record.is_active = False
    await db.commit()
    return True


async def increment_violation(prefix: str, db: AsyncSession) -> int:
    record = await get_key_by_prefix(prefix, db)
    if record is None:
        return 0
    record.violation_count += 1
    await db.commit()
    return record.violation_count


async def flag_key(prefix: str, db: AsyncSession) -> None:
    record = await get_key_by_prefix(prefix, db)
    if record is None:
        return
    record.is_flagged = True
    await db.commit()


async def auto_revoke_key(prefix: str, db: AsyncSession) -> None:
    record = await get_key_by_prefix(prefix, db)
    if record is None:
        return
    record.is_active = False
    record.is_flagged = True
    await db.commit()


async def update_usage(prefix: str, ip: str, db: AsyncSession) -> None:
    record = await get_key_by_prefix(prefix, db)
    if record is None:
        return
    record.usage_count += 1
    record.last_used_at = datetime.utcnow()
    record.last_ip = ip

    history: list = list(record.ip_history or [])
    if ip not in history:
        history.append(ip)
    if len(history) > 10:
        history = history[-10:]
    record.ip_history = history

    await db.commit()
