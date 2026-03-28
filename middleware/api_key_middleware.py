from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from database import AsyncSessionLocal
from security.key_store import get_key_by_prefix
from security.key_hasher import verify_key
from config import settings

_PREFIX_LEN = 20

_SKIP_PATHS = {"/v1/health", "/v1/routes", "/docs", "/openapi.json", "/redoc", "/admin/dashboard"}

_ADMIN_PREFIX = "/v1/admin"
_DEVELOPER_PREFIX = "/v1/developer"

# Paths that must pass through unauthenticated so the honeypot route can catch
# them, log the probe, block the IP, and return 404.
_KNOWN_PREFIXES = ("/v1/", "/docs", "/redoc", "/openapi.json")

_401 = JSONResponse(
    status_code=401,
    content={"status": "error", "message": "Invalid or missing API key.", "data": None},
)
_403 = JSONResponse(
    status_code=403,
    content={"status": "error", "message": "This key has been suspended.", "data": None},
)


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if path in _SKIP_PATHS:
            return await call_next(request)

        # Developer API routes — session-based auth handled in the router itself
        if path.startswith(_DEVELOPER_PREFIX):
            return await call_next(request)

        # Unknown paths → let honeypot router handle them
        if not any(path.startswith(p) for p in _KNOWN_PREFIXES):
            return await call_next(request)

        # Admin routes — master key auth
        if path.startswith(_ADMIN_PREFIX):
            master = request.headers.get("X-DelkaAI-Master-Key", "")
            if master != settings.SECRET_MASTER_KEY:
                return JSONResponse(
                    status_code=401,
                    content={"status": "error", "message": "Invalid master key.", "data": None},
                )
            return await call_next(request)

        raw_key = request.headers.get("X-DelkaAI-Key", "")
        if not raw_key:
            return _401

        prefix = raw_key[:_PREFIX_LEN]

        async with AsyncSessionLocal() as db:
            record = await get_key_by_prefix(prefix, db)

            # Same generic message whether not found or wrong hash — never reveal existence
            if record is None:
                return _401

            if not verify_key(raw_key, record.key_hash):
                return _401

            if not record.is_active:
                return _403

            if record.is_flagged:
                return _403

            # Detach record from session before attaching to state
            await db.refresh(record)
            request.state.api_key = record
            # Expose raw HMAC secret for hmac_middleware (stored in hmac_secret_hash field)
            request.state.hmac_secret_raw = record.hmac_secret_hash

        return await call_next(request)
