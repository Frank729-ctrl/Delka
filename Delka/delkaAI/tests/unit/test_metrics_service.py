"""Tests for services/metrics_service.py — all record/get functions."""
import pytest
import services.metrics_service as metrics


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metrics state before each test."""
    from datetime import datetime
    metrics._metrics.update({
        "total_requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "total_response_ms": 0,
        "request_count_for_avg": 0,
        "total_llm_calls": 0,
        "total_llm_ms": 0,
        "llm_call_count": 0,
        "jailbreak_attempts": 0,
        "content_blocked": 0,
        "endpoints": {},
        "platforms": {},
        "status_codes": {},
        "started_at": datetime.utcnow().isoformat(),
    })
    yield


async def test_record_request_increments_total(monkeypatch):
    """record_request increments total_requests counter."""
    await metrics.record_request("/v1/cv/generate", "test", 200, 150)
    assert metrics._metrics["total_requests"] == 1


async def test_record_request_success_counter(monkeypatch):
    """200 response increments successful_requests."""
    await metrics.record_request("/v1/cv/generate", "test", 200, 100)
    assert metrics._metrics["successful_requests"] == 1
    assert metrics._metrics["failed_requests"] == 0


async def test_record_request_failure_counter(monkeypatch):
    """400 response increments failed_requests."""
    await metrics.record_request("/v1/cv/generate", "test", 400, 50)
    assert metrics._metrics["failed_requests"] == 1
    assert metrics._metrics["successful_requests"] == 0


async def test_record_request_tracks_endpoint():
    """record_request increments endpoint count."""
    await metrics.record_request("/v1/cv/generate", "test", 200, 100)
    await metrics.record_request("/v1/cv/generate", "test", 200, 100)
    assert metrics._metrics["endpoints"].get("/v1/cv/generate") == 2


async def test_record_request_tracks_platform():
    """record_request increments platform count when platform is provided."""
    await metrics.record_request("/v1/support/chat", "swypply", 200, 100)
    assert metrics._metrics["platforms"].get("swypply") == 1


async def test_record_request_no_platform_skipped():
    """record_request with platform=None does not crash and skips platform tracking."""
    await metrics.record_request("/v1/health", None, 200, 5)
    assert metrics._metrics["platforms"] == {}


async def test_record_llm_call_increments():
    """record_llm_call increments LLM counters."""
    await metrics.record_llm_call(1500)
    assert metrics._metrics["total_llm_calls"] == 1
    assert metrics._metrics["total_llm_ms"] == 1500


async def test_record_jailbreak_increments():
    """record_jailbreak increments jailbreak_attempts."""
    await metrics.record_jailbreak()
    assert metrics._metrics["jailbreak_attempts"] == 1


async def test_record_content_blocked_increments():
    """record_content_blocked increments content_blocked counter."""
    await metrics.record_content_blocked()
    assert metrics._metrics["content_blocked"] == 1


def test_get_avg_response_time_no_requests():
    """get_avg_response_time returns 0.0 when no requests recorded."""
    assert metrics.get_avg_response_time() == 0.0


async def test_get_avg_response_time_with_requests():
    """get_avg_response_time computes correct average."""
    await metrics.record_request("/v1/health", None, 200, 100)
    await metrics.record_request("/v1/health", None, 200, 300)
    avg = metrics.get_avg_response_time()
    assert avg == 200.0


def test_get_error_rate_no_requests():
    """get_error_rate returns 0.0 when no requests recorded."""
    assert metrics.get_error_rate() == 0.0


async def test_get_error_rate_with_mixed_requests():
    """get_error_rate computes correct ratio of failures to total."""
    await metrics.record_request("/", None, 200, 10)
    await metrics.record_request("/", None, 400, 10)
    rate = metrics.get_error_rate()
    assert rate == 0.5


async def test_get_summary_returns_all_fields():
    """get_summary returns a dict with all expected keys."""
    summary = await metrics.get_summary()
    for key in ["total_requests", "successful_requests", "failed_requests",
                "total_llm_calls", "avg_llm_ms", "jailbreak_attempts",
                "content_blocked", "avg_response_ms", "error_rate",
                "endpoints", "platforms", "status_codes", "started_at"]:
        assert key in summary, f"Missing key: {key}"


async def test_get_summary_avg_llm_zero_when_no_calls():
    """get_summary shows avg_llm_ms=0.0 when no LLM calls recorded."""
    summary = await metrics.get_summary()
    assert summary["avg_llm_ms"] == 0.0


async def test_get_summary_avg_llm_computed_when_calls_exist():
    """get_summary computes avg_llm_ms from recorded LLM calls."""
    await metrics.record_llm_call(2000)
    await metrics.record_llm_call(1000)
    summary = await metrics.get_summary()
    assert summary["avg_llm_ms"] == 1500.0
