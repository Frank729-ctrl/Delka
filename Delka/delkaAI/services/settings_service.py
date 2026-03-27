"""Persistent key-value settings store backed by the database."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.settings_store_model import SettingsStore
from schemas.settings_schema import SettingItem


async def get_setting(key: str, db: AsyncSession) -> str | None:
    result = await db.execute(
        select(SettingsStore).where(SettingsStore.setting_key == key)
    )
    row = result.scalar_one_or_none()
    return row.setting_value if row else None


async def upsert_setting(
    key: str,
    value: str,
    description: str | None,
    updated_by: str | None,
    db: AsyncSession,
) -> SettingItem:
    result = await db.execute(
        select(SettingsStore).where(SettingsStore.setting_key == key)
    )
    row = result.scalar_one_or_none()
    now = datetime.utcnow()

    if row is None:
        row = SettingsStore(
            setting_key=key,
            setting_value=value,
            description=description,
            updated_at=now,
            updated_by=updated_by,
        )
        db.add(row)
    else:
        row.setting_value = value
        if description is not None:
            row.description = description
        row.updated_at = now
        row.updated_by = updated_by

    await db.commit()
    await db.refresh(row)
    return SettingItem(
        setting_key=row.setting_key,
        setting_value=row.setting_value,
        description=row.description,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
    )


async def list_settings(db: AsyncSession) -> list[SettingItem]:
    result = await db.execute(
        select(SettingsStore).order_by(SettingsStore.setting_key)
    )
    rows = result.scalars().all()
    return [
        SettingItem(
            setting_key=r.setting_key,
            setting_value=r.setting_value,
            description=r.description,
            updated_at=r.updated_at,
            updated_by=r.updated_by,
        )
        for r in rows
    ]


async def delete_setting(key: str, db: AsyncSession) -> bool:
    result = await db.execute(
        select(SettingsStore).where(SettingsStore.setting_key == key)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True
