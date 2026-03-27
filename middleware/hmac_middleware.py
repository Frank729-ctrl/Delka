from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from security.hmac_verifier import verify_request_signature

_401 = JSONResponse(
    status_code=401,
    content={"status": "error", "message": "Request signature verification failed.", "data": None},
)


class HMACMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        api_key = getattr(request.state, "api_key", None)
        if api_key is None or not api_key.requires_hmac:
            return await call_next(request)

        timestamp = request.headers.get("X-DelkaAI-Timestamp", "")
        signature = request.headers.get("X-DelkaAI-Signature", "")

        if not timestamp or not signature:
            return _401

        body_bytes = await request.body()

        # hmac_secret_hash holds the raw HMAC secret (stored hashed, but we need
        # the raw secret for verification — resolved via key_store during auth).
        # The raw secret is attached to request.state by api_key_middleware.
        hmac_secret = getattr(request.state, "hmac_secret_raw", None)
        if not hmac_secret:
            return _401

        if not verify_request_signature(hmac_secret, body_bytes, timestamp, signature):
            return _401

        return await call_next(request)
