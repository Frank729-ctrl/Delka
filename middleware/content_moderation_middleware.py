import json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from security.content_moderator import screen_input
from security.nvidia_safety import nvidia_safety_check
from security.security_logger import log_security_event

_SKIP_PATHS = {"/v1/health", "/docs", "/openapi.json", "/redoc"}


def _extract_text(body_bytes: bytes) -> str:
    try:
        payload = json.loads(body_bytes)
        if isinstance(payload, dict):
            return " ".join(str(v) for v in payload.values() if isinstance(v, str))
        if isinstance(payload, str):
            return payload
    except Exception:
        pass
    return body_bytes.decode("utf-8", errors="replace")


class ContentModerationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        body_bytes = await request.body()
        if not body_bytes:
            return await call_next(request)

        text = _extract_text(body_bytes)
        is_safe, category = screen_input(text)

        # Augment with NVIDIA safety model for deeper content checking
        if is_safe:
            is_safe, category = await nvidia_safety_check(text)

        if is_safe:
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        api_key = getattr(request.state, "api_key", None)
        key_prefix = api_key.raw_prefix if api_key else None

        log_security_event(
            severity="WARNING",
            event_type="content_blocked",
            details={
                "category": category,
                "input_preview": text,
                "key_prefix": key_prefix,
                "ip": ip,
            },
        )

        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Request contains prohibited content.",
                "data": None,
            },
        )
