"""Tests for job_queue/job_queue.py — enqueue, get_status, _process_one."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from job_queue.job_queue import enqueue_job, get_job_status, _process_one


async def test_enqueue_job_creates_record(test_db):
    """enqueue_job creates a WebhookJob record in the database."""
    await enqueue_job(
        job_id="job-001",
        job_type="cv",
        payload={"full_name": "Jane"},
        webhook_url="https://example.com/hook",
        key_prefix="fd-delka-sk-test1234",
        db=test_db,
    )
    result = await get_job_status("job-001", test_db)
    assert result["job_id"] == "job-001"
    assert result["status"] == "queued"


async def test_get_job_status_not_found(test_db):
    """get_job_status returns not_found for unknown job_id."""
    result = await get_job_status("nonexistent-job", test_db)
    assert result["status"] == "not_found"
    assert result["job_id"] == "nonexistent-job"


async def test_get_job_status_returns_expected_fields(test_db):
    """get_job_status returns all expected keys for a known job."""
    await enqueue_job(
        job_id="job-002",
        job_type="cover_letter",
        payload={"applicant_name": "Jane"},
        webhook_url="https://example.com/hook2",
        key_prefix=None,
        db=test_db,
    )
    result = await get_job_status("job-002", test_db)
    for field in ["job_id", "job_type", "status", "attempts", "created_at", "completed_at"]:
        assert field in result, f"Missing field: {field}"


async def test_process_one_cv_job_marks_complete(test_db):
    """_process_one processes a CV job, marks it complete, and calls webhook deliver."""
    await enqueue_job(
        job_id="job-cv-1",
        job_type="cv",
        payload={
            "full_name": "Frank Dela",
            "email": "frank@example.com",
            "summary": "Engineer.",
            "experience": [{"company": "Delka", "title": "Lead", "start_date": "2024-01",
                             "end_date": "present", "bullets": ["Built APIs"]}],
            "education": [{"school": "UG", "degree": "BSc", "year": "2022"}],
            "skills": ["Python"],
        },
        webhook_url="https://example.com/hook",
        key_prefix=None,
        db=test_db,
    )

    fake_pdf = b"%PDF-1.4 fake"

    async def fake_pipeline(payload):
        return (fake_pdf, "bold_header", "professional_blue", "groq", "llama-3.3-70b-versatile")

    async def fake_deliver(url, payload, secret):
        return True

    with patch("services.cv_service._run_cv_pipeline", fake_pipeline), \
         patch("services.webhook_service.deliver", fake_deliver):
        await _process_one("job-cv-1", test_db)

    result = await get_job_status("job-cv-1", test_db)
    assert result["status"] == "complete"
    assert result["completed_at"] is not None


async def test_process_one_unknown_job_type_marks_failed(test_db):
    """_process_one marks a job with unknown job_type as failed."""
    await enqueue_job(
        job_id="job-bad-1",
        job_type="unknown_type",
        payload={},
        webhook_url="https://example.com/hook",
        key_prefix=None,
        db=test_db,
    )

    async def fake_deliver(url, payload, secret):
        return True

    with patch("services.webhook_service.deliver", fake_deliver):
        await _process_one("job-bad-1", test_db)

    result = await get_job_status("job-bad-1", test_db)
    assert result["status"] == "failed"


async def test_process_one_nonexistent_job_does_nothing(test_db):
    """_process_one with unknown job_id silently does nothing."""
    # Should not raise
    await _process_one("does-not-exist", test_db)


async def test_process_one_pipeline_failure_marks_failed(test_db):
    """When CV pipeline raises an exception, job is marked failed."""
    await enqueue_job(
        job_id="job-fail-1",
        job_type="cv",
        payload={"full_name": "Jane"},
        webhook_url="https://example.com/hook",
        key_prefix=None,
        db=test_db,
    )

    async def exploding_pipeline(payload):
        raise RuntimeError("pipeline exploded")

    async def fake_deliver(url, payload, secret):
        return True

    with patch("services.cv_service._run_cv_pipeline", exploding_pipeline), \
         patch("services.webhook_service.deliver", fake_deliver):
        await _process_one("job-fail-1", test_db)

    result = await get_job_status("job-fail-1", test_db)
    assert result["status"] == "failed"
