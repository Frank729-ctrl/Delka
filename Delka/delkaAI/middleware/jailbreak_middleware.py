import json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from security.jailbreak_detector import detect_jailbreak
from security.security_logger import log_security_event
from database import AsyncSessionLocal
from security.key_store import increment_violation, flag_key, auto_revoke_key

_SKIP_PATHS = {"/v1/health", "/docs", "/openapi.json", "/redoc"}
_PREFIX_LEN = 20


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


class JailbreakMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        body_bytes = await request.body()
        if not body_bytes:
            return await call_next(request)

        text = _extract_text(body_bytes)
        detected, pattern = detect_jailbreak(text)

        if not detected:
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        api_key = getattr(request.state, "api_key", None)
        if api_key:
            key_prefix = api_key.raw_prefix
        else:
            raw_key = request.headers.get("X-DelkaAI-Key", "")
            key_prefix = raw_key[:_PREFIX_LEN] if raw_key else None

        log_security_event(
            severity="CRITICAL",
            event_type="jailbreak_attempt",
            details={
                "pattern": pattern,
                "input_preview": text,
                "key_prefix": key_prefix,
                "ip": ip,
            },
        )

        if key_prefix:
            async with AsyncSessionLocal() as db:
                new_count = await increment_violation(key_prefix, db)
                if new_count >= 3:
                    await flag_key(key_prefix, db)
                if new_count >= 5:
                    await auto_revoke_key(key_prefix, db)

        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Request contains prohibited content.",
                "data": None,
            },
        )
