"""
PII Middleware — scans request bodies and adds a redacted copy to request.state.
Does NOT block requests (PII in a CV is legitimate). Just makes redacted text
available so services can log safely without leaking user data.
"""
import json
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from security.pii_detector import detect_pii

_SKIP_PATHS = {"/v1/health", "/docs", "/openapi.json", "/redoc", "/static"}

# Endpoints where PII is expected (CV, cover letter) — skip noisy logging
_PII_EXPECTED_PATHS = {"/v1/cv", "/v1/letter"}


class PIIMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if any(path.startswith(p) for p in _SKIP_PATHS):
            return await call_next(request)

        body_bytes = await request.body()
        if body_bytes:
            try:
                payload = json.loads(body_bytes)
                text = " ".join(str(v) for v in payload.values() if isinstance(v, str))
                result = detect_pii(text)
                request.state.pii_found = result.found
                request.state.pii_types = result.types
                # Only attach redacted text for logging on non-CV paths
                if result.found and not any(path.startswith(p) for p in _PII_EXPECTED_PATHS):
                    request.state.pii_redacted = result.redacted
            except Exception:
                pass

        return await call_next(request)
