import pytest
import middleware.rate_limit_middleware as _rl
from tests.conftest import VALID_CV_PAYLOAD


async def test_single_request_passes(client, valid_sk_key, mock_ollama, mock_export):
    _rl._key_windows.clear()
    _rl._ip_windows.clear()
    resp = await client.post(
        "/v1/cv/generate",
        json=VALID_CV_PAYLOAD,
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 200


async def test_burst_within_limit_all_pass(client, valid_sk_key, mock_ollama, mock_export):
    _rl._key_windows.clear()
    _rl._ip_windows.clear()
    # Five requests well within 1000/min limit
    for _ in range(5):
        resp = await client.get("/v1/health")
        assert resp.status_code == 200


async def test_exceeding_ip_limit_returns_429(client, monkeypatch):
    """Directly saturate the IP window then assert the next request is 429."""
    import time
    from collections import deque

    _rl._key_windows.clear()
    _rl._ip_windows.clear()

    # Simulate the IP having already hit the limit
    now = time.time()
    ip = "testclient"  # httpx ASGI transport uses "testclient" as client host
    _rl._ip_windows[ip] = deque([now] * 1000, maxlen=2000)

    resp = await client.get("/v1/health")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
