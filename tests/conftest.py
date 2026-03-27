"""
Shared pytest fixtures for all test layers.
Environment variables are set BEFORE any app import so Settings and
module-level objects (Argon2 hasher, loggers) use test values.
"""
import asyncio
import json
import os
import time
import hmac as _hmac
from hashlib import sha256
from typing import AsyncGenerator

# ── Override settings before app imports ────────────────────────────────────
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SECRET_MASTER_KEY", "fd-delka-mk-testkey0000000000000000")
os.environ.setdefault("ADMIN_EMAIL", "admin@test.com")
os.environ.setdefault("ADMIN_PASSWORD", "testpassword123")
os.environ.setdefault("ARGON2_TIME_COST", "1")
os.environ.setdefault("ARGON2_MEMORY_COST", "8192")
os.environ.setdefault("ARGON2_PARALLELISM", "1")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "1000")
os.environ.setdefault("RATE_LIMIT_PER_IP_MINUTE", "1000")
os.environ.setdefault("OLLAMA_TIMEOUT_SECONDS", "5")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from config import settings
from database import Base, get_db

# ── Fixture data ─────────────────────────────────────────────────────────────

FIXTURE_CV_JSON = json.dumps({
    "full_name": "Jane Smith",
    "email": "jane@example.com",
    "phone": "+1234567890",
    "location": "London, UK",
    "summary": "Experienced software engineer with 8 years in Python development.",
    "experience": [
        {
            "company": "TechCorp",
            "title": "Senior Software Engineer",
            "start_date": "2019-01",
            "end_date": "Present",
            "bullets": [
                "Led migration to microservices architecture, reducing latency by 40%",
                "Mentored 5 junior engineers",
            ],
        }
    ],
    "education": [
        {
            "school": "University of Ghana",
            "degree": "BSc",
            "field": "Computer Science",
            "year": "2016",
        }
    ],
    "skills": ["Python", "FastAPI", "Docker"],
})

FIXTURE_LETTER_TEXT = (
    "With a decade of engineering leadership behind me, I am the candidate "
    "you are looking for at Acme Corp.\n\n"
    "Over the past five years at TechCorp I scaled the backend to ten million "
    "daily active users and reduced cloud spend by thirty percent.\n\n"
    "Acme's commitment to open-source infrastructure aligns directly with my "
    "own philosophy of building in public.\n\n"
    "I would welcome the opportunity to discuss how my background maps to "
    "your roadmap — please feel free to reach out at your earliest convenience."
)

FIXTURE_SSE_TOKENS = ["Hello", " from", " DelkaAI", "!"]

VALID_CV_PAYLOAD = {
    "full_name": "Jane Smith",
    "email": "jane@example.com",
    "phone": "+1234567890",
    "location": "London, UK",
    "summary": "Experienced software engineer.",
    "experience": [
        {
            "company": "TechCorp",
            "title": "Senior Engineer",
            "start_date": "2019-01",
            "end_date": "Present",
            "bullets": ["Built microservices", "Led team of 5"],
        }
    ],
    "education": [
        {"school": "MIT", "degree": "BSc", "field": "CS", "year": "2016"}
    ],
    "skills": ["Python", "Docker"],
}

VALID_LETTER_PAYLOAD = {
    "applicant_name": "Jane Smith",
    "company_name": "Acme Corp",
    "job_title": "Senior Engineer",
    "job_description": "Build scalable backend services in Python.",
    "applicant_background": "10 years Python, 5 years FastAPI, 3 years team lead.",
}


# ── Database fixtures ─────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_engine():
    """In-memory SQLite engine shared via StaticPool."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Register all models
    from models import (  # noqa
        api_key_model, usage_log_model, blocked_ip_model, webhook_model,
        developer_account_model, developer_session_model,
        platform_registry_model, settings_store_model, vision_index_model,
        user_memory_profile_model, conversation_log_model, feedback_log_model,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Single async session backed by the in-memory test engine."""
    SessionLocal = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with SessionLocal() as session:
        yield session


# ── HTTP client fixture ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(test_engine, monkeypatch):
    """AsyncClient wired to the test app with the in-memory DB."""
    TestSessionLocal = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with TestSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # Patch all modules that import AsyncSessionLocal at module level
    import database
    monkeypatch.setattr(database, "AsyncSessionLocal", TestSessionLocal)

    import middleware.api_key_middleware as _akm
    monkeypatch.setattr(_akm, "AsyncSessionLocal", TestSessionLocal)

    import middleware.ip_block_middleware as _ibm
    monkeypatch.setattr(_ibm, "AsyncSessionLocal", TestSessionLocal)

    import middleware.jailbreak_middleware as _jm
    monkeypatch.setattr(_jm, "AsyncSessionLocal", TestSessionLocal)

    import routers.honeypot_router as _hr
    monkeypatch.setattr(_hr, "AsyncSessionLocal", TestSessionLocal)

    import routers.dashboard_router as _dr
    monkeypatch.setattr(_dr, "AsyncSessionLocal", TestSessionLocal)

    import routers.admin_console_router as _acr
    monkeypatch.setattr(_acr, "AsyncSessionLocal", TestSessionLocal)

    import routers.console_router as _cr
    monkeypatch.setattr(_cr, "AsyncSessionLocal", TestSessionLocal)

    # Also clear rate-limit windows so prior tests don't bleed through
    import middleware.rate_limit_middleware as _rl
    _rl._key_windows.clear()
    _rl._ip_windows.clear()

    from main import app
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("testclient", 50000)),
        base_url="http://testserver",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Key fixtures ──────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def valid_sk_key(test_engine) -> str:
    """A live SK key committed to the test DB."""
    TestSessionLocal = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    from security.key_store import create_key_pair
    async with TestSessionLocal() as db:
        result = await create_key_pair("test_platform", "test_owner", False, db)
    return result["secret_key"]


@pytest_asyncio.fixture
async def valid_pk_key(test_engine) -> str:
    """A live PK key committed to the test DB."""
    TestSessionLocal = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    from security.key_store import create_key_pair
    async with TestSessionLocal() as db:
        result = await create_key_pair("test_platform", "test_owner", False, db)
    return result["publishable_key"]


@pytest_asyncio.fixture
async def valid_hmac_key(test_engine):
    """An SK key with HMAC required; returns (raw_key, hmac_secret)."""
    TestSessionLocal = async_sessionmaker(
        bind=test_engine, class_=AsyncSession, expire_on_commit=False
    )
    from security.key_store import create_key_pair
    async with TestSessionLocal() as db:
        result = await create_key_pair("test_platform", "test_owner", True, db)
    return result["secret_key"], result["hmac_secret"]


@pytest.fixture
def master_key() -> str:
    return settings.SECRET_MASTER_KEY


# ── Ollama mock ───────────────────────────────────────────────────────────────

@pytest.fixture
def mock_inference(monkeypatch):
    """Patches inference_service so no real API calls are made.
    generate_full_response returns (text, provider, model) tuple.
    generate_stream_response yields fixture tokens.
    """

    async def fake_full(task, system_prompt, user_prompt, **kwargs):
        return (FIXTURE_CV_JSON, "groq", "llama-3.3-70b-versatile")

    async def fake_stream(task, messages, **kwargs):
        for token in FIXTURE_SSE_TOKENS:
            yield token

    monkeypatch.setattr("services.inference_service.generate_full_response", fake_full)
    monkeypatch.setattr("services.inference_service.generate_stream_response", fake_stream)
    monkeypatch.setattr("services.cv_service._inference_full", fake_full)
    monkeypatch.setattr("services.cover_letter_service._inference_full", fake_full)
    monkeypatch.setattr("services.support_service._inference_stream", fake_stream)

    return {"full": fake_full, "stream": fake_stream}


@pytest.fixture
def mock_inference_stream(monkeypatch):
    """Patches inference_service.generate_stream_response only."""

    async def fake_stream(task, messages, **kwargs):
        for token in FIXTURE_SSE_TOKENS:
            yield token

    monkeypatch.setattr("services.inference_service.generate_stream_response", fake_stream)
    monkeypatch.setattr("services.support_service._inference_stream", fake_stream)
    return fake_stream


@pytest.fixture
def mock_ollama(monkeypatch):
    """Backward-compat fixture: patches inference_service (the entry point all
    services call) so no real LLM calls are made. Points at ollama_provider
    for backward compatibility but patches at the inference_service level
    so all consumers are covered.
    """

    async def fake_full(task, system_prompt, user_prompt, **kwargs):
        return (FIXTURE_CV_JSON, "ollama", "llama3.1")

    async def fake_stream(task, messages, **kwargs):
        for token in FIXTURE_SSE_TOKENS:
            yield token

    monkeypatch.setattr("services.inference_service.generate_full_response", fake_full)
    monkeypatch.setattr("services.inference_service.generate_stream_response", fake_stream)
    monkeypatch.setattr("services.cv_service._inference_full", fake_full)
    monkeypatch.setattr("services.cover_letter_service._inference_full", fake_full)
    monkeypatch.setattr("services.support_service._inference_stream", fake_stream)

    # Also patch ollama_provider for any tests that call it directly
    monkeypatch.setattr(
        "services.providers.ollama_provider.OllamaProvider.generate_full",
        fake_full,
    )

    return {"full": fake_full, "stream": fake_stream}


@pytest.fixture
def mock_export(monkeypatch):
    """Patches WeasyPrint so PDF rendering returns fake bytes.

    Both the export_service module AND each consumer module are patched
    because consumers import the functions directly (from ... import f).
    """
    _fake_cv_pdf = b"%PDF-1.4 fake-cv-pdf"
    _fake_lt_pdf = b"%PDF-1.4 fake-letter-pdf"

    monkeypatch.setattr("services.export_service.render_cv_to_pdf",
                        lambda *a, **kw: _fake_cv_pdf)
    monkeypatch.setattr("services.export_service.render_letter_to_pdf",
                        lambda *a, **kw: _fake_lt_pdf)
    monkeypatch.setattr("services.cv_service.render_cv_to_pdf",
                        lambda *a, **kw: _fake_cv_pdf)
    monkeypatch.setattr("services.cover_letter_service.render_letter_to_pdf",
                        lambda *a, **kw: _fake_lt_pdf)


def make_hmac_headers(raw_key: str, body: bytes, hmac_secret: str) -> dict:
    """Helper: build the three HMAC request headers."""
    ts = str(int(time.time()))
    body_str = body.decode("utf-8", errors="replace")
    message = f"{ts}.{body_str}"
    sig = _hmac.new(hmac_secret.encode(), message.encode(), sha256).hexdigest()
    return {
        "X-DelkaAI-Key": raw_key,
        "X-DelkaAI-Timestamp": ts,
        "X-DelkaAI-Signature": sig,
    }
