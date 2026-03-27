from pydantic import BaseModel


class MetricsSummary(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_llm_calls: int
    avg_llm_ms: float
    jailbreak_attempts: int
    content_blocked: int
    avg_response_ms: float
    error_rate: float
    endpoints: dict
    platforms: dict
    status_codes: dict
    started_at: str
