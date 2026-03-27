"""Developer Console — server-rendered UI at /console/* (session cookie auth)."""
from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from database import AsyncSessionLocal
from services.developer_auth_service import (
    register_developer, login_developer, get_session, logout_developer
)
from services.console_service import get_developer_overview, get_developer_keys, get_platform_list
from services.metrics_service import get_summary
from utils.logger import request_logger

router = APIRouter(tags=["Developer Console"])

_env = Environment(
    loader=FileSystemLoader("templates/"),
    autoescape=select_autoescape(["html"]),
)

_COOKIE_NAME = "delka_console_session"


async def _get_account(token: str | None):
    if not token:
        return None
    async with AsyncSessionLocal() as db:
        return await get_session(token, db)


def _login_redirect() -> RedirectResponse:
    return RedirectResponse(url="/console/login", status_code=302)


# ── REGISTER ─────────────────────────────────────────────────────────────────

@router.get("/console/register", response_class=HTMLResponse)
async def console_register_page():
    tpl = _env.get_template("console/register.html")
    return HTMLResponse(tpl.render(error=""))


@router.post("/console/register")
async def console_register_post(
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    company: str = Form(""),
):
    async with AsyncSessionLocal() as db:
        result = await register_developer(email, password, full_name, company or None, db)

    if not result["success"]:
        tpl = _env.get_template("console/register.html")
        return HTMLResponse(tpl.render(error="Email already in use."), status_code=400)

    return RedirectResponse(url="/console/login?registered=1", status_code=302)


# ── LOGIN ─────────────────────────────────────────────────────────────────────

@router.get("/console/login", response_class=HTMLResponse)
async def console_login_page(registered: str = "", error: str = ""):
    tpl = _env.get_template("console/login.html")
    return HTMLResponse(tpl.render(registered=registered, error=error))


@router.post("/console/login")
async def console_login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    async with AsyncSessionLocal() as db:
        result = await login_developer(email, password, ip, ua, db)

    if not result["success"]:
        tpl = _env.get_template("console/login.html")
        return HTMLResponse(tpl.render(registered="", error="Invalid email or password."), status_code=401)

    response = RedirectResponse(url="/console/overview", status_code=302)
    response.set_cookie(
        key=_COOKIE_NAME,
        value=result["session_token"],
        httponly=True,
        samesite="lax",
        max_age=3600 * 24,
    )
    return response


@router.get("/console/logout")
async def console_logout(
    delka_console_session: str | None = Cookie(default=None),
):
    if delka_console_session:
        async with AsyncSessionLocal() as db:
            await logout_developer(delka_console_session, db)

    response = RedirectResponse(url="/console/login", status_code=302)
    response.delete_cookie(_COOKIE_NAME)
    return response


# ── OVERVIEW ─────────────────────────────────────────────────────────────────

@router.get("/console/overview", response_class=HTMLResponse)
async def console_overview(
    delka_console_session: str | None = Cookie(default=None),
):
    account = await _get_account(delka_console_session)
    if not account:
        return _login_redirect()

    async with AsyncSessionLocal() as db:
        overview = await get_developer_overview(account.email, db)

    tpl = _env.get_template("console/overview.html")
    return HTMLResponse(tpl.render(account=account, overview=overview))


# ── KEYS ─────────────────────────────────────────────────────────────────────

@router.get("/console/keys", response_class=HTMLResponse)
async def console_keys(
    delka_console_session: str | None = Cookie(default=None),
):
    account = await _get_account(delka_console_session)
    if not account:
        return _login_redirect()

    async with AsyncSessionLocal() as db:
        keys = await get_developer_keys(account.email, db)

    tpl = _env.get_template("console/keys.html")
    return HTMLResponse(tpl.render(account=account, keys=keys))


# ── USAGE ─────────────────────────────────────────────────────────────────────

@router.get("/console/usage", response_class=HTMLResponse)
async def console_usage(
    delka_console_session: str | None = Cookie(default=None),
):
    account = await _get_account(delka_console_session)
    if not account:
        return _login_redirect()

    async with AsyncSessionLocal() as db:
        keys = await get_developer_keys(account.email, db)

    total_usage = sum(k.get("usage_count", 0) for k in keys)
    tpl = _env.get_template("console/usage.html")
    return HTMLResponse(tpl.render(account=account, keys=keys, total_usage=total_usage))


# ── DOCS ─────────────────────────────────────────────────────────────────────

@router.get("/console/docs", response_class=HTMLResponse)
async def console_docs(
    delka_console_session: str | None = Cookie(default=None),
):
    account = await _get_account(delka_console_session)
    if not account:
        return _login_redirect()

    tpl = _env.get_template("console/docs.html")
    return HTMLResponse(tpl.render(account=account))


# ── PLAYGROUND ───────────────────────────────────────────────────────────────

@router.get("/console/playground", response_class=HTMLResponse)
async def console_playground(
    delka_console_session: str | None = Cookie(default=None),
):
    account = await _get_account(delka_console_session)
    if not account:
        return _login_redirect()

    async with AsyncSessionLocal() as db:
        keys = await get_developer_keys(account.email, db)

    sk_keys = [k for k in keys if k["key_type"] == "sk" and k["is_active"]]
    tpl = _env.get_template("console/playground.html")
    return HTMLResponse(tpl.render(account=account, sk_keys=sk_keys))


# ── SUPPORT ───────────────────────────────────────────────────────────────────

@router.get("/console/support", response_class=HTMLResponse)
async def console_support(
    delka_console_session: str | None = Cookie(default=None),
):
    account = await _get_account(delka_console_session)
    if not account:
        return _login_redirect()

    tpl = _env.get_template("console/support.html")
    return HTMLResponse(tpl.render(account=account))
