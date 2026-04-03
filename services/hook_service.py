"""
Hook System — exceeds Claude Code's hooks/ system.

src: postSamplingHooks.ts, pre-compact hooks, post-compact hooks, stop hooks,
     session start hooks. Only TypeScript plugins can register hooks.
     Hooks are in-process function calls with no external delivery.

Delka: Two-tier hook system — better because:
  1. Internal hooks  — Python callables registered in-process (same as src)
  2. External hooks  — HTTP webhooks POST'd to any URL (src has zero of this)
  3. Any platform/service/language can subscribe, not just TS plugins
  4. HMAC-signed payloads for external webhook security
  5. Async fire-and-forget delivery (never blocks chat response)
  6. DB-persisted subscriptions survive restarts
  7. Retry on delivery failure (up to 2 attempts)

Hook event types (maps to src equivalents):
  pre_chat         Before any processing        (src: session start hook)
  post_chat        After full response sent      (src: postSamplingHook)
  post_compact     After context compaction      (src: post-compact hook)
  post_memory      After memory extraction       (src: post-memory hook)
  post_skill       After a /skill is executed    (src: no equivalent)
  post_tool        After MCP tool call           (src: tool hook)
  session_start    First message in session      (src: session start hook)
  session_end      Explicit session close        (src: stop hook)

Payload shape for all events:
  {
    "event":      "post_chat",
    "platform":   "my-app",
    "user_id":    "u123",
    "session_id": "s456",
    "timestamp":  1712345678.0,
    "data":       { ...event-specific fields }
  }
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from collections import defaultdict
from typing import Any, Callable, Awaitable, Optional

import httpx

# ── Valid events ───────────────────────────────────────────────────────────────

VALID_EVENTS = {
    "pre_chat",
    "post_chat",
    "post_compact",
    "post_memory",
    "post_skill",
    "post_tool",
    "session_start",
    "session_end",
}

# ── Internal hook registry ─────────────────────────────────────────────────────
# In-process async callables: event → list[async fn(payload) → None]

HookFn = Callable[[dict], Awaitable[None]]
_internal_registry: dict[str, list[HookFn]] = defaultdict(list)


def register(event: str, fn: HookFn) -> None:
    """Register an internal (in-process) hook for an event type."""
    if event not in VALID_EVENTS:
        raise ValueError(f"Unknown hook event '{event}'. Valid: {VALID_EVENTS}")
    _internal_registry[event].append(fn)


def unregister(event: str, fn: HookFn) -> None:
    """Remove a previously registered internal hook."""
    if event in _internal_registry:
        _internal_registry[event] = [f for f in _internal_registry[event] if f is not fn]


# ── Payload builder ────────────────────────────────────────────────────────────

def _build_payload(
    event: str,
    platform: str,
    user_id: str,
    session_id: str,
    data: dict,
) -> dict:
    return {
        "event": event,
        "platform": platform,
        "user_id": user_id,
        "session_id": session_id,
        "timestamp": time.time(),
        "data": data,
    }


# ── HMAC signing ───────────────────────────────────────────────────────────────

def _sign(payload_bytes: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


# ── External HTTP delivery ─────────────────────────────────────────────────────

_DELIVERY_TIMEOUT = 8    # seconds per attempt
_MAX_RETRIES = 2


async def _deliver_http(url: str, payload: dict, secret: Optional[str]) -> bool:
    """POST payload to a webhook URL. Returns True on success."""
    body = json.dumps(payload, default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Delka-Event": payload["event"],
        "X-Delka-Timestamp": str(int(payload["timestamp"])),
    }
    if secret:
        headers["X-Delka-Signature"] = _sign(body, secret)

    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=_DELIVERY_TIMEOUT) as client:
                resp = await client.post(url, content=body, headers=headers)
                if resp.status_code < 500:
                    return True
        except Exception:
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(1)
    return False


# ── DB subscription loader ─────────────────────────────────────────────────────

async def _load_subscriptions(event: str, platform: str, db) -> list[dict]:
    """Load active HTTP webhook subscriptions for this event + platform."""
    if db is None:
        return []
    try:
        from sqlalchemy import text
        result = await db.execute(
            text(
                "SELECT url, secret FROM hook_subscriptions "
                "WHERE event = :ev AND platform = :pl AND is_active = 1"
            ),
            {"ev": event, "pl": platform},
        )
        return [{"url": r[0], "secret": r[1]} for r in result.fetchall()]
    except Exception:
        return []


# ── Main fire function ─────────────────────────────────────────────────────────

async def fire(
    event: str,
    platform: str,
    user_id: str,
    session_id: str,
    data: dict,
    db=None,
) -> None:
    """
    Fire a hook event. Runs internal callables then delivers HTTP webhooks.
    Always fire-and-forget — never raises, never blocks caller.
    """
    if event not in VALID_EVENTS:
        return

    payload = _build_payload(event, platform, user_id, session_id, data)

    # ── Internal hooks (in-process) ───────────────────────────────────────────
    for fn in list(_internal_registry.get(event, [])):
        try:
            await fn(payload)
        except Exception:
            pass   # internal hook failure must never crash chat

    # ── External HTTP webhooks ────────────────────────────────────────────────
    subs = await _load_subscriptions(event, platform, db)
    if subs:
        async def _deliver_all():
            tasks = [_deliver_http(s["url"], payload, s["secret"]) for s in subs]
            await asyncio.gather(*tasks, return_exceptions=True)
        asyncio.create_task(_deliver_all())


def fire_background(
    event: str,
    platform: str,
    user_id: str,
    session_id: str,
    data: dict,
    db=None,
) -> None:
    """Synchronous wrapper — schedules fire() as asyncio task."""
    asyncio.create_task(fire(event, platform, user_id, session_id, data, db))


# ── DB CRUD helpers (used by hook_router) ─────────────────────────────────────

async def register_subscription(
    name: str,
    platform: str,
    event: str,
    url: str,
    secret: Optional[str],
    created_by: Optional[str],
    db,
) -> dict:
    if event not in VALID_EVENTS:
        return {"error": f"Unknown event '{event}'. Valid: {sorted(VALID_EVENTS)}"}
    try:
        from sqlalchemy import text
        await db.execute(
            text(
                "INSERT INTO hook_subscriptions "
                "(name, platform, event, url, secret, created_by, is_active) "
                "VALUES (:name, :pl, :ev, :url, :sec, :by, 1)"
            ),
            {"name": name[:128], "pl": platform, "ev": event,
             "url": url[:512], "sec": secret, "by": created_by},
        )
        await db.commit()
        return {"status": "ok"}
    except Exception as exc:
        return {"error": str(exc)[:200]}


async def list_subscriptions(platform: str, db) -> list[dict]:
    try:
        from sqlalchemy import text
        result = await db.execute(
            text(
                "SELECT id, name, event, url, is_active, created_at "
                "FROM hook_subscriptions WHERE platform = :pl ORDER BY event, name"
            ),
            {"pl": platform},
        )
        return [
            {"id": r[0], "name": r[1], "event": r[2],
             "url": r[3], "is_active": bool(r[4]), "created_at": str(r[5])}
            for r in result.fetchall()
        ]
    except Exception:
        return []


async def delete_subscription(sub_id: int, platform: str, db) -> bool:
    try:
        from sqlalchemy import text
        await db.execute(
            text("UPDATE hook_subscriptions SET is_active = 0 WHERE id = :id AND platform = :pl"),
            {"id": sub_id, "pl": platform},
        )
        await db.commit()
        return True
    except Exception:
        return False


async def test_subscription(sub_id: int, platform: str, db) -> dict:
    """Send a test payload to a registered webhook URL."""
    try:
        from sqlalchemy import text
        result = await db.execute(
            text("SELECT url, secret FROM hook_subscriptions WHERE id = :id AND platform = :pl"),
            {"id": sub_id, "pl": platform},
        )
        row = result.fetchone()
        if not row:
            return {"error": "Subscription not found"}
        test_payload = _build_payload(
            "test", platform, "test-user", "test-session",
            {"message": "This is a Delka hook test ping"}
        )
        success = await _deliver_http(row[0], test_payload, row[1])
        return {"delivered": success, "url": row[0]}
    except Exception as exc:
        return {"error": str(exc)[:200]}
