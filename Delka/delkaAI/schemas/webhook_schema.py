from pydantic import BaseModel


class WebhookJobRequest(BaseModel):
    job_id: str
    status: str
    event: str
    data: dict
    timestamp: str
    signature: str
