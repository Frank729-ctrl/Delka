import pytest
from security.ip_blocker import is_ip_blocked
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession


async def test_unknown_path_returns_404(client):
    resp = await client.get("/this/path/does/not/exist")
    assert resp.status_code == 404


async def test_honeypot_post_returns_404(client):
    resp = await client.post("/admin/secret", json={"x": 1})
    assert resp.status_code == 404


async def test_honeypot_blocks_ip(client, test_engine):
    await client.get("/unknown/path/xyz")
    # The IP "testclient" should now be blocked
    SM = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    async with SM() as db:
        blocked = await is_ip_blocked("testclient", db)
    assert blocked is True


async def test_multiple_methods_all_return_404(client):
    for method in ("get", "post", "put", "delete"):
        resp = await getattr(client, method)("/not/a/real/route")
        assert resp.status_code == 404
