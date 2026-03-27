from datetime import datetime
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from utils.logger import request_logger


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        key_prefix = None
        api_key = getattr(request.state, "api_key", None)
        if api_key:
            key_prefix = getattr(api_key, "raw_prefix", None)

        response_ms = getattr(request.state, "response_ms", "-")
        request_id = getattr(request.state, "request_id", "-")

        request_logger.info(
            f'{datetime.utcnow().isoformat()} '
            f'method={request.method} '
            f'path={request.url.path} '
            f'key_prefix={key_prefix or "none"} '
            f'status={response.status_code} '
            f'ms={response_ms} '
            f'request_id={request_id}'
        )

        return response
