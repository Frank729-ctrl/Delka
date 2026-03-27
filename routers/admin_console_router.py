"""Admin Console — server-rendered UI at /admin/* (email + password auth)."""
from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from config import settings
from database import AsyncSessionLocal
from services.admin_service import create_key_pair, list_api_keys, revoke_key
from services.metrics_service import get_summary
from services.settings_service import list_settings, upsert_setting
from security.ip_blocker import list_blocked, unblock_ip
from security.security_logger import get_recent_events
from services.console_service import get_platform_list, register_platform
from utils.logger import request_logger

router = APIRouter(tags=["Admin Console"])

_env = Environment(
    loader=FileSystemLoader("templates/"),
    autoescape=select_autoescape(["html"]),
)

_COOKIE_NAME = "delka_admin_session"
_SESSION_TOKEN = "delka_admin_authenticated"


def _check_auth(session_key: str | None) -> bool:
    return session_key == _SESSION_TOKEN


def _login_redirect() -> RedirectResponse:
    return RedirectResponse(url="/admin/login", status_code=302)


# ── LOGIN ────────────────────────────────────────────────────────────────────

@router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(error: str = ""):
    tpl = _env.get_template("admin/login.html")
    return HTMLResponse(tpl.render(error=error))


@router.post("/admin/login")
async def admin_login_post(
    email: str = Form(...),
    password: str = Form(...),
):
    if email != settings.ADMIN_EMAIL or password != settings.ADMIN_PASSWORD:
        tpl = _env.get_template("admin/login.html")
        return HTMLResponse(tpl.render(error="Invalid email or password."), status_code=401)

    response = RedirectResponse(url="/admin/keys", status_code=302)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=_SESSION_TOKEN,
        httponly=True,
        samesite="lax",
        max_age=3600 * 8,
    )
    return response


@router.get("/admin/logout")
async def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie(_COOKIE_NAME)
    return response


# ── KEYS ─────────────────────────────────────────────────────────────────────

@router.get("/admin/keys", response_class=HTMLResponse)
async def admin_keys(
    delka_admin_session: str | None = Cookie(default=None),
    message: str = "",
):
    if not _check_auth(delka_admin_session):
        return _login_redirect()

    async with AsyncSessionLocal() as db:
        keys = await list_api_keys(db)

    tpl = _env.get_template("admin/keys.html")
    return HTMLResponse(tpl.render(keys=[k.model_dump() for k in keys], message=message))


@router.post("/admin/keys/create")
async def admin_keys_create(
    platform: str = Form(...),
    owner: str = Form(...),
    requires_hmac: bool = Form(False),
    delka_admin_session: str | None = Cookie(default=None),
):
    if not _check_auth(delka_admin_session):
        return _login_redirect()

    async with AsyncSessionLocal() as db:
        result = await create_key_pair(platform, owner, requires_hmac, db)

    tpl = _env.get_template("admin/keys.html")
    async with AsyncSessionLocal() as db:
        keys = await list_api_keys(db)

    msg = (
        f"Created: PK={result['publishable_key']} | SK={result['secret_key']}"
        + (f" | HMAC={result.get('hmac_secret', '')}" if requires_hmac else "")
    )
    return HTMLResponse(tpl.render(keys=[k.model_dump() for k in keys], message=msg, new_key=result))


@router.post("/admin/keys/revoke")
async def admin_keys_revoke(
    key_prefix: str = Form(...),
    delka_admin_session: str | None = Cookie(default=None),
):
    if not _check_auth(delka_admin_session):
        return _login_redirect()

    async with AsyncSessionLocal() as db:
        ok = await revoke_key(key_prefix, db)

    msg = f"Revoked {key_prefix}." if ok else f"Prefix '{key_prefix}' not found."
    return RedirectResponse(url=f"/admin/keys?message={msg}", status_code=302)


# ── SECURITY ─────────────────────────────────────────────────────────────────

@router.get("/admin/security", response_class=HTMLResponse)
async def admin_security(
    delka_admin_session: str | None = Cookie(default=None),
):
    if not _check_auth(delka_admin_session):
        return _login_redirect()

    async with AsyncSessionLocal() as db:
        blocked = await list_blocked(db)

    events = get_recent_events(50)
    tpl = _env.get_template("admin/security.html")
    return HTMLResponse(tpl.render(blocked_ips=blocked, events=events))


@router.post("/admin/security/unblock")
async def admin_security_unblock(
    ip_address: str = Form(...),
    delka_admin_session: str | None = Cookie(default=None),
):
    if not _check_auth(delka_admin_session):
        return _login_redirect()

    async with AsyncSessionLocal() as db:
        await unblock_ip(ip_address, db)

    return RedirectResponse(url="/admin/security", status_code=302)


# ── METRICS ──────────────────────────────────────────────────────────────────

@router.get("/admin/metrics", response_class=HTMLResponse)
async def admin_metrics_page(
    delka_admin_session: str | None = Cookie(default=None),
):
    if not _check_auth(delka_admin_session):
        return _login_redirect()

    metrics = await get_summary()
    tpl = _env.get_template("admin/metrics.html")
    return HTMLResponse(tpl.render(metrics=metrics))


# ── PROVIDERS ────────────────────────────────────────────────────────────────

@router.get("/admin/providers", response_class=HTMLResponse)
async def admin_providers(
    delka_admin_session: str | None = Cookie(default=None),
):
    if not _check_auth(delka_admin_session):
        return _login_redirect()

    providers = [
        {"name": "Groq", "model": settings.CV_PRIMARY_MODEL, "status": "active", "task": "cv, cover_letter"},
        {"name": "Ollama", "model": settings.OLLAMA_MODEL, "status": "active", "task": "fallback"},
    ]
    tpl = _env.get_template("admin/providers.html")
    return HTMLResponse(tpl.render(providers=providers))


# ── PLATFORMS ────────────────────────────────────────────────────────────────

@router.get("/admin/platforms", response_class=HTMLResponse)
async def admin_platforms(
    delka_admin_session: str | None = Cookie(default=None),
    message: str = "",
):
    if not _check_auth(delka_admin_session):
        return _login_redirect()

    async with AsyncSessionLocal() as db:
        platforms = await get_platform_list(db)

    tpl = _env.get_template("admin/platforms.html")
    return HTMLResponse(tpl.render(platforms=platforms, message=message))


@router.post("/admin/platforms/register")
async def admin_platforms_register(
    platform_name: str = Form(...),
    owner_email: str = Form(...),
    description: str = Form(""),
    webhook_url: str = Form(""),
    requires_hmac: bool = Form(False),
    delka_admin_session: str | None = Cookie(default=None),
):
    if not _check_auth(delka_admin_session):
        return _login_redirect()

    async with AsyncSessionLocal() as db:
        result = await register_platform(
            platform_name, owner_email,
            description or None, webhook_url or None, requires_hmac, db
        )

    msg = result.get("error", f"Registered platform: {platform_name}")
    return RedirectResponse(url=f"/admin/platforms?message={msg}", status_code=302)


# ── WEBHOOKS ─────────────────────────────────────────────────────────────────

@router.get("/admin/webhooks", response_class=HTMLResponse)
async def admin_webhooks(
    delka_admin_session: str | None = Cookie(default=None),
):
    if not _check_auth(delka_admin_session):
        return _login_redirect()

    async with AsyncSessionLocal() as db:
        platforms = await get_platform_list(db)

    webhook_platforms = [p for p in platforms if p.get("webhook_url")]
    tpl = _env.get_template("admin/webhooks.html")
    return HTMLResponse(tpl.render(webhook_platforms=webhook_platforms))


# ── SETTINGS ─────────────────────────────────────────────────────────────────

@router.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings(
    delka_admin_session: str | None = Cookie(default=None),
    message: str = "",
):
    if not _check_auth(delka_admin_session):
        return _login_redirect()

    async with AsyncSessionLocal() as db:
        all_settings = await list_settings(db)

    tpl = _env.get_template("admin/settings.html")
    return HTMLResponse(tpl.render(settings_list=[s.model_dump() for s in all_settings], message=message))


@router.post("/admin/settings/upsert")
async def admin_settings_upsert(
    setting_key: str = Form(...),
    setting_value: str = Form(...),
    description: str = Form(""),
    delka_admin_session: str | None = Cookie(default=None),
):
    if not _check_auth(delka_admin_session):
        return _login_redirect()

    async with AsyncSessionLocal() as db:
        await upsert_setting(setting_key, setting_value, description or None, "admin", db)

    return RedirectResponse(url=f"/admin/settings?message=Saved+{setting_key}", status_code=302)
