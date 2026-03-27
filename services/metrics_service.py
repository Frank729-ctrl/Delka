import asyncio
from datetime import datetime

_lock = asyncio.Lock()

_metrics: dict = {
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
}


async def record_request(
    endpoint: str,
    platform: str | None,
    status_code: int,
    response_ms: int,
) -> None:
    async with _lock:
        _metrics["total_requests"] += 1
        _metrics["total_response_ms"] += response_ms
        _metrics["request_count_for_avg"] += 1

        if status_code < 400:
            _metrics["successful_requests"] += 1
        else:
            _metrics["failed_requests"] += 1

        ep = endpoint or "unknown"
        _metrics["endpoints"][ep] = _metrics["endpoints"].get(ep, 0) + 1

        if platform:
            _metrics["platforms"][platform] = _metrics["platforms"].get(platform, 0) + 1

        code_key = str(status_code)
        _metrics["status_codes"][code_key] = _metrics["status_codes"].get(code_key, 0) + 1


async def record_llm_call(ms: int) -> None:
    async with _lock:
        _metrics["total_llm_calls"] += 1
        _metrics["total_llm_ms"] += ms
        _metrics["llm_call_count"] += 1


async def record_jailbreak() -> None:
    async with _lock:
        _metrics["jailbreak_attempts"] += 1


async def record_content_blocked() -> None:
    async with _lock:
        _metrics["content_blocked"] += 1


def get_avg_response_time() -> float:
    count = _metrics["request_count_for_avg"]
    if count == 0:
        return 0.0
    return round(_metrics["total_response_ms"] / count, 2)


def get_error_rate() -> float:
    total = _metrics["total_requests"]
    if total == 0:
        return 0.0
    return round(_metrics["failed_requests"] / total, 4)


async def get_summary() -> dict:
    async with _lock:
        llm_count = _metrics["llm_call_count"]
        avg_llm = (
            round(_metrics["total_llm_ms"] / llm_count, 2) if llm_count > 0 else 0.0
        )
        return {
            "total_requests": _metrics["total_requests"],
            "successful_requests": _metrics["successful_requests"],
            "failed_requests": _metrics["failed_requests"],
            "total_llm_calls": _metrics["total_llm_calls"],
            "avg_llm_ms": avg_llm,
            "jailbreak_attempts": _metrics["jailbreak_attempts"],
            "content_blocked": _metrics["content_blocked"],
            "avg_response_ms": get_avg_response_time(),
            "error_rate": get_error_rate(),
            "endpoints": dict(_metrics["endpoints"]),
            "platforms": dict(_metrics["platforms"]),
            "status_codes": dict(_metrics["status_codes"]),
            "started_at": _metrics["started_at"],
        }
