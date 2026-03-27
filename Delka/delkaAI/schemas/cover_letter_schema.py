from pydantic import BaseModel


class CoverLetterRequest(BaseModel):
    applicant_name: str
    company_name: str
    job_title: str
    job_description: str
    applicant_background: str
    tone: str = "professional"
    webhook_url: str = ""


class CoverLetterResponse(BaseModel):
    status: str
    message: str
    data: dict | None = None
