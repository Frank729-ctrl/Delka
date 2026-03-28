import pytest


async def test_health_no_auth_required(client):
    resp = await client.get("/v1/health")
    assert resp.status_code == 200


async def test_health_returns_version(client):
    resp = await client.get("/v1/health")
    body = resp.json()
    assert body["version"] == "1.0.0"
    # Phase 8: response includes providers, models, fallbacks
    assert "providers" in body
    assert "models" in body
    assert "fallbacks" in body


async def test_health_ollama_unreachable_returns_degraded(client, monkeypatch):
    import httpx

    async def fail_get(*a, **kw):
        raise httpx.ConnectError("unreachable")

    monkeypatch.setattr("routers.health_router.httpx.AsyncClient", lambda **kw: _FakeCtx(fail_get))
    # Also ensure Groq key is empty so both providers are down → degraded
    monkeypatch.setattr("config.settings.GROQ_API_KEY", "")
    resp = await client.get("/v1/health")
    body = resp.json()
    assert body["providers"]["ollama"] == "unreachable"
    assert body["providers"]["groq"] == "not_configured"
    assert body["status"] == "degraded"


async def test_health_ollama_ok_when_reachable(client, monkeypatch):
    import httpx

    class _OkResp:
        status_code = 200

    async def ok_get(*a, **kw):
        return _OkResp()

    monkeypatch.setattr("routers.health_router.httpx.AsyncClient", lambda **kw: _OkCtx(ok_get))
    resp = await client.get("/v1/health")
    body = resp.json()
    assert body["providers"]["ollama"] == "ok"
    assert body["status"] == "ok"


class _OkCtx:
    def __init__(self, fn):
        self._fn = fn

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get(self, *a, **kw):
        return await self._fn()


class _FakeCtx:
    def __init__(self, raiser):
        self._raiser = raiser

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def get(self, *a, **kw):
        await self._raiser()
