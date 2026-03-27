import json
import re
from typing import Any
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
import bleach

_SQL_PATTERN = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|--|;--)\b",
    re.IGNORECASE,
)

_SUPPORT_MESSAGE_MAX = 800
_DEFAULT_MAX = 5000


def _sanitize_string(value: str, max_len: int = _DEFAULT_MAX) -> str:
    cleaned = bleach.clean(value, tags=[], strip=True)
    cleaned = cleaned.replace("\x00", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_len]


def _sanitize_value(value: Any, key: str = "") -> Any:
    if isinstance(value, str):
        max_len = _SUPPORT_MESSAGE_MAX if key == "message" else _DEFAULT_MAX
        return _sanitize_string(value, max_len)
    if isinstance(value, dict):
        return {k: _sanitize_value(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item, key) for item in value]
    return value


def _check_sql_injection(obj: Any) -> bool:
    """Returns True if SQL injection pattern detected."""
    if isinstance(obj, str):
        return bool(_SQL_PATTERN.search(obj))
    if isinstance(obj, dict):
        return any(_check_sql_injection(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_check_sql_injection(item) for item in obj)
    return False


class SanitizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type:
            return await call_next(request)

        body_bytes = await request.body()
        if not body_bytes:
            return await call_next(request)

        try:
            payload = json.loads(body_bytes)
        except json.JSONDecodeError:
            return await call_next(request)

        if _check_sql_injection(payload):
            return JSONResponse(
                status_code=400,
                content={
                    "status": "error",
                    "message": "Invalid input detected.",
                    "data": None,
                },
            )

        sanitized = _sanitize_value(payload)
        sanitized_bytes = json.dumps(sanitized).encode("utf-8")

        # Overwrite the cached body so downstream handlers see sanitized content.
        # request.body() checks _body first — no need to touch _receive.
        request._body = sanitized_bytes

        return await call_next(request)
