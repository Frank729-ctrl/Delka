from pydantic import BaseModel, EmailStr, field_validator


class ExperienceItem(BaseModel):
    company: str
    title: str
    start_date: str
    end_date: str = "Present"
    bullets: list[str]

    @field_validator("bullets")
    @classmethod
    def bullets_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("bullets must be a non-empty list")
        return v


class EducationItem(BaseModel):
    school: str
    degree: str
    field: str = ""
    year: str


class CVRequest(BaseModel):
    # Free-text intake — when provided, structured fields are inferred by AI
    raw_text: str = ""

    # Structured fields (required when raw_text is absent)
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    summary: str = ""
    experience: list[ExperienceItem] = []
    education: list[EducationItem] = []
    skills: list[str] = []
    linkedin: str = ""
    website: str = ""
    webhook_url: str = ""


class CVResponse(BaseModel):
    status: str
    message: str
    data: dict | None = None
