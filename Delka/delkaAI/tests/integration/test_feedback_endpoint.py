"""Integration tests for /v1/feedback and /v1/admin/feedback/* endpoints."""
import pytest
from config import settings


@pytest.mark.asyncio
async def test_feedback_submission_with_valid_data(client, valid_pk_key):
    """POST /v1/feedback with valid data returns 200."""
    resp = await client.post(
        "/v1/feedback",
        json={
            "session_id": "test-sess-001",
            "service": "support",
            "rating": 5,
            "comment": "Great response",
        },
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "correction_stored" in data


@pytest.mark.asyncio
async def test_feedback_with_correction_stores_it(client, valid_pk_key):
    """POST /v1/feedback with correction → correction_stored: true."""
    resp = await client.post(
        "/v1/feedback",
        json={
            "session_id": "test-sess-002",
            "service": "chat",
            "rating": 3,
            "correction": "Don't use bullet points",
        },
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code == 200
    assert resp.json()["correction_stored"] is True


@pytest.mark.asyncio
async def test_feedback_no_key_returns_401(client):
    """POST /v1/feedback without key returns 401."""
    resp = await client.post(
        "/v1/feedback",
        json={"session_id": "s", "service": "support", "rating": 4},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_feedback_summary_with_master_key(client, master_key):
    """GET /v1/admin/feedback/summary with master key returns 200."""
    resp = await client.get(
        "/v1/admin/feedback/summary?platform=test",
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "data" in data


@pytest.mark.asyncio
async def test_feedback_export_returns_jsonl(client, master_key):
    """GET /v1/admin/feedback/export returns downloadable file."""
    resp = await client.get(
        "/v1/admin/feedback/export?platform=test&min_rating=4",
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    assert resp.status_code == 200
