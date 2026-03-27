from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from security.key_permission import check_permission

_SKIP_PATHS = {"/v1/health", "/docs", "/openapi.json", "/redoc"}
_ADMIN_PREFIX = "/v1/admin"

_403 = JSONResponse(
    status_code=403,
    content={
        "status": "error",
        "message": "This key type cannot access this endpoint.",
        "data": None,
    },
)


class KeyPermissionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if path in _SKIP_PATHS or path.startswith(_ADMIN_PREFIX):
            return await call_next(request)

        api_key = getattr(request.state, "api_key", None)
        if api_key is None:
            return await call_next(request)

        if not check_permission(api_key.key_type, path):
            return _403

        return await call_next(request)
