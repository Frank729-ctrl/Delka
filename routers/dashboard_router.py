from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from config import settings
from database import AsyncSessionLocal
from services.admin_service import list_api_keys
from services.metrics_service import get_summary
from security.ip_blocker import list_blocked
from security.security_logger import get_recent_events

router = APIRouter(tags=["dashboard"])

_env = Environment(
    loader=FileSystemLoader("templates/"),
    autoescape=select_autoescape(["html"]),
)


@router.get("/admin/dashboard", response_class=HTMLResponse)
async def dashboard(master_key: str = Query(...)):
    if master_key != settings.SECRET_MASTER_KEY:
        raise HTTPException(status_code=401, detail="Invalid master key.")

    async with AsyncSessionLocal() as db:
        keys = await list_api_keys(db)
        blocked = await list_blocked(db)

    metrics = await get_summary()
    events = get_recent_events(20)

    template = _env.get_template("admin/dashboard.html")
    rendered = template.render(
        metrics=metrics,
        keys=[k.model_dump() for k in keys],
        events=events,
        blocked_ips=blocked,
        master_key=master_key,
    )
    return HTMLResponse(content=rendered)
