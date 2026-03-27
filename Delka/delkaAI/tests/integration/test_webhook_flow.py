"""Integration tests for the webhook job lifecycle."""
import pytest
from tests.conftest import VALID_CV_PAYLOAD, VALID_LETTER_PAYLOAD


async def test_cv_request_with_webhook_returns_202(client, valid_sk_key, mock_inference, mock_export):
    """CV request with webhook_url returns 202 Accepted with a job_id."""
    payload = dict(VALID_CV_PAYLOAD)
    payload["webhook_url"] = "https://example.com/webhook"
    resp = await client.post(
        "/v1/cv/generate",
        json=payload,
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "success"
    assert "job_id" in data["data"]


async def test_letter_request_with_webhook_returns_202(client, valid_sk_key, mock_inference, mock_export):
    """Cover letter request with webhook_url returns 202 Accepted."""
    payload = dict(VALID_LETTER_PAYLOAD)
    payload["webhook_url"] = "https://example.com/webhook"
    resp = await client.post(
        "/v1/letter/generate",
        json=payload,
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "success"
    assert "job_id" in data["data"]


async def test_job_status_endpoint_returns_queued(client, valid_sk_key, mock_inference, mock_export, master_key):
    """After enqueuing, the job status endpoint returns 'queued'."""
    payload = dict(VALID_CV_PAYLOAD)
    payload["webhook_url"] = "https://example.com/webhook"
    create_resp = await client.post(
        "/v1/cv/generate",
        json=payload,
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    job_id = create_resp.json()["data"]["job_id"]

    status_resp = await client.get(
        f"/v1/admin/jobs/{job_id}",
        headers={"X-DelkaAI-Master-Key": master_key},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["data"]["job_id"] == job_id


async def test_cv_without_webhook_returns_pdf_synchronously(client, valid_sk_key, mock_inference, mock_export):
    """CV request without webhook_url returns PDF immediately (200)."""
    resp = await client.post(
        "/v1/cv/generate",
        json=VALID_CV_PAYLOAD,
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
