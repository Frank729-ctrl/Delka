import asyncio
import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from database import AsyncSessionLocal, create_all_tables
from middleware.cors_middleware import get_cors_config
from middleware.security_headers_middleware import SecurityHeadersMiddleware
from middleware.ip_block_middleware import IPBlockMiddleware
from middleware.request_id_middleware import RequestIDMiddleware
from middleware.response_time_middleware import ResponseTimeMiddleware
from middleware.logging_middleware import LoggingMiddleware
from middleware.metrics_middleware import MetricsMiddleware
from middleware.rate_limit_middleware import RateLimitMiddleware
from middleware.sanitize_middleware import SanitizeMiddleware
from middleware.hmac_middleware import HMACMiddleware
from middleware.api_key_middleware import APIKeyMiddleware
from middleware.key_permission_middleware import KeyPermissionMiddleware
from middleware.jailbreak_middleware import JailbreakMiddleware
from middleware.content_moderation_middleware import ContentModerationMiddleware
from job_queue.job_queue import process_jobs
from fastapi.staticfiles import StaticFiles
from routers import (
    health_router,
    cv_router,
    cover_letter_router,
    support_router,
    admin_router,
    dashboard_router,
    honeypot_router,
)
from routers.admin_console_router import router as admin_console_router
from routers.vision_router import router as vision_router
from routers.chat_router import router as chat_router
from routers.feedback_router import router as feedback_router
from utils.logger import request_logger

_logger = logging.getLogger("delkaai.main")


# ── LIFESPAN ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_all_tables()
    asyncio.create_task(process_jobs(AsyncSessionLocal))
    request_logger.info(
        f"DelkaAI v1 started | ENV:{settings.APP_ENV} | Model:{settings.OLLAMA_MODEL}"
    )
    yield
    request_logger.info("DelkaAI shutting down")


# ── APP ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="DelkaAI API",
    description="AI services by Frank Dela Nutsukpuie",
    version="1.0.0",
    docs_url=settings.docs_url,
    redoc_url=settings.redoc_url,
    lifespan=lifespan,
)


# ── MIDDLEWARE ───────────────────────────────────────────────────────────────
# add_middleware wraps the existing stack — last added = outermost.
# Spec order: outermost=CORS → ... → innermost=SecurityHeaders.
# So we register innermost first, outermost last.

app.add_middleware(SecurityHeadersMiddleware)          # 14 — innermost
app.add_middleware(IPBlockMiddleware)                  # 13
app.add_middleware(RequestIDMiddleware)                # 12
app.add_middleware(ResponseTimeMiddleware)             # 11
app.add_middleware(LoggingMiddleware)                  # 10
app.add_middleware(MetricsMiddleware)                  # 9
app.add_middleware(RateLimitMiddleware)                # 8
app.add_middleware(SanitizeMiddleware)                 # 7
app.add_middleware(HMACMiddleware)                     # 6
app.add_middleware(KeyPermissionMiddleware)            # 5 — inner: reads api_key set by APIKey
app.add_middleware(APIKeyMiddleware)                   # 4 — outer: authenticates first, sets api_key
app.add_middleware(JailbreakMiddleware)                # 3
app.add_middleware(ContentModerationMiddleware)        # 2
app.add_middleware(CORSMiddleware, **get_cors_config())  # 1 — outermost


# ── EXCEPTION HANDLERS ───────────────────────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "message": "Request validation failed.",
            "data": {"errors": exc.errors(), "request_id": request_id},
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": exc.detail,
            "data": {"request_id": request_id},
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    _logger.error(
        f"Unhandled exception | request_id={request_id} | "
        f"path={request.url.path}\n{traceback.format_exc()}"
    )
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "An internal error occurred.",
            "data": {"request_id": request_id},
        },
    )


# ── ROOT ─────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"name": "DelkaAI API", "version": "1.0.0", "docs": "/v1/health"}


# ── STATIC FILES ────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── ROUTERS ─────────────────────────────────────────────────────────────────
# Honeypot MUST be last — it catches all unmatched paths.
app.include_router(health_router.router,       tags=["Health"])
app.include_router(cv_router.router,           tags=["CV Generation"])
app.include_router(cover_letter_router.router, tags=["Cover Letter"])
app.include_router(support_router.router,      tags=["Support Chat"])
app.include_router(admin_router.router,        tags=["Administration"])
app.include_router(dashboard_router.router,    tags=["Dashboard"])
app.include_router(admin_console_router,       tags=["Admin Console"])
app.include_router(vision_router,              tags=["Visual Search"])
app.include_router(chat_router,                tags=["Chat"])
app.include_router(feedback_router,            tags=["Feedback"])
app.include_router(honeypot_router.router,     tags=["*"])   # ← MUST BE LAST
