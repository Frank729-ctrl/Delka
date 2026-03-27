from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from database import AsyncSessionLocal
from security.ip_blocker import is_ip_blocked

_SKIP_PATHS = {"/v1/health"}
_SKIP_PREFIXES = ("/admin/", "/console/", "/static/")


class IPBlockMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in _SKIP_PATHS or any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"

        async with AsyncSessionLocal() as db:
            blocked = await is_ip_blocked(ip, db)

        if blocked:
            return JSONResponse(
                status_code=404,
                content={"detail": "Not Found"},
            )

        return await call_next(request)
