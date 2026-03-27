from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from database import AsyncSessionLocal
from security.ip_blocker import block_ip
from security.security_logger import log_security_event

router = APIRouter(tags=["honeypot"])


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def honeypot(path: str, request: Request):
    ip = request.client.host if request.client else "unknown"
    method = request.method
    full_path = str(request.url)

    log_security_event(
        severity="CRITICAL",
        event_type="honeypot_triggered",
        details={
            "path": f"/{path}",
            "method": method,
            "url": full_path,
            "ip": ip,
        },
    )

    try:
        async with AsyncSessionLocal() as db:
            await block_ip(
                ip=ip,
                reason=f"honeypot: {method} /{path}",
                db=db,
                duration_hours=None,  # permanent
            )
    except Exception:
        pass

    return JSONResponse(status_code=404, content={"detail": "Not Found"})
