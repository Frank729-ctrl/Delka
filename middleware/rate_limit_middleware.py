import asyncio
import time
from collections import defaultdict, deque
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from config import settings

_PREFIX_LEN = 20

# Sliding window: store deque of timestamps per identity
_key_windows: dict[str, deque] = defaultdict(deque)
_ip_windows: dict[str, deque] = defaultdict(deque)
_lock = asyncio.Lock()

_KEY_WINDOW = 60   # seconds
_IP_WINDOW = 60    # seconds


def _count_window(window: deque, now: float, duration: int) -> int:
    cutoff = now - duration
    while window and window[0] < cutoff:
        window.popleft()
    return len(window)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        now = time.time()
        ip = request.client.host if request.client else "unknown"

        raw_key = request.headers.get("X-DelkaAI-Key", "")
        key_prefix = raw_key[:_PREFIX_LEN] if raw_key else None

        async with _lock:
            # Per-IP limit
            ip_window = _ip_windows[ip]
            ip_count = _count_window(ip_window, now, _IP_WINDOW)
            if ip_count >= settings.RATE_LIMIT_PER_IP_MINUTE:
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": "60"},
                    content={
                        "status": "error",
                        "message": "Too many requests from this IP. Try again later.",
                        "data": None,
                    },
                )
            ip_window.append(now)

            # Per-key limit
            if key_prefix:
                key_window = _key_windows[key_prefix]
                key_count = _count_window(key_window, now, _KEY_WINDOW)
                if key_count >= settings.RATE_LIMIT_PER_MINUTE:
                    return JSONResponse(
                        status_code=429,
                        headers={"Retry-After": "60"},
                        content={
                            "status": "error",
                            "message": "Rate limit exceeded for this API key. Try again later.",
                            "data": None,
                        },
                    )
                key_window.append(now)

        return await call_next(request)
