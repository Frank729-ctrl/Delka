"""Tests for all schema classes — covers 0% schema files by instantiation."""
import pytest
from schemas.common_schema import StandardResponse, ErrorResponse
from schemas.metrics_schema import MetricsSummary
from schemas.webhook_schema import WebhookJobRequest


# ── common_schema.py ──────────────────────────────────────────────────────────

def test_standard_response_success():
    """StandardResponse can be instantiated with success status."""
    r = StandardResponse(status="success", message="ok", data={"id": 1})
    assert r.status == "success"
    assert r.message == "ok"
    assert r.data == {"id": 1}


def test_standard_response_error():
    """StandardResponse can be instantiated with error status."""
    r = StandardResponse(status="error", message="bad request")
    assert r.status == "error"
    assert r.data is None


def test_error_response_default_status():
    """ErrorResponse always has status='error'."""
    r = ErrorResponse(message="Something failed")
    assert r.status == "error"
    assert r.message == "Something failed"


def test_error_response_with_data():
    """ErrorResponse accepts optional data field."""
    r = ErrorResponse(message="fail", data={"request_id": "abc"})
    assert r.data == {"request_id": "abc"}


# ── metrics_schema.py ─────────────────────────────────────────────────────────

def test_metrics_summary_instantiation():
    """MetricsSummary can be instantiated with all required fields."""
    m = MetricsSummary(
        total_requests=100,
        successful_requests=95,
        failed_requests=5,
        total_llm_calls=80,
        avg_llm_ms=1200.5,
        jailbreak_attempts=2,
        content_blocked=1,
        avg_response_ms=350.0,
        error_rate=0.05,
        endpoints={"/v1/cv/generate": 50},
        platforms={"swypply": 40},
        status_codes={"200": 95, "400": 5},
        started_at="2026-03-01T00:00:00",
    )
    assert m.total_requests == 100
    assert m.error_rate == 0.05


# ── webhook_schema.py ─────────────────────────────────────────────────────────

def test_webhook_job_request_instantiation():
    """WebhookJobRequest can be instantiated with all required fields."""
    req = WebhookJobRequest(
        job_id="job-abc-123",
        status="complete",
        event="cv.generated",
        data={"pdf_base64": "..."},
        timestamp="2026-03-01T12:00:00",
        signature="abc123def456",
    )
    assert req.job_id == "job-abc-123"
    assert req.event == "cv.generated"
