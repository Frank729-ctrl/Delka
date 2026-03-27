from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        try:
            from services.metrics_service import record_request  # lazy import — built in Phase 3

            api_key = getattr(request.state, "api_key", None)
            platform = getattr(api_key, "platform", None) if api_key else None
            response_ms = getattr(request.state, "response_ms", 0)

            await record_request(
                endpoint=request.url.path,
                platform=platform,
                status_code=response.status_code,
                response_ms=response_ms,
            )
        except Exception:
            pass  # metrics must never break the request path

        return response
