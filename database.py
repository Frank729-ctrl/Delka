from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator
from config import settings


class Base(DeclarativeBase):
    pass


def _build_database_url() -> str:
    if settings.DATABASE_URL:
        return settings.DATABASE_URL
    return (
        f"mysql+aiomysql://{settings.DB_USER}:{settings.DB_PASSWORD}"
        f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )


def _engine_kwargs() -> dict:
    kwargs: dict = {"echo": not settings.is_production, "pool_pre_ping": True}
    url = _build_database_url()
    if "supabase.com" in url or "supabase.co" in url:
        import ssl as _ssl
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        kwargs["connect_args"] = {"ssl": ctx}
    return kwargs


engine = create_async_engine(_build_database_url(), **_engine_kwargs())

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all_tables() -> None:
    from models import (  # noqa: F401
        api_key_model,
        usage_log_model,
        blocked_ip_model,
        webhook_model,
        developer_account_model,
        developer_session_model,
        platform_registry_model,
        settings_store_model,
        vision_index_model,
        user_memory_profile_model,
        conversation_log_model,
        feedback_log_model,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
