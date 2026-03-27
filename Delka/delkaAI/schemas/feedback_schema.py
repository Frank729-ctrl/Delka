from pydantic import BaseModel, field_validator


class FeedbackRequest(BaseModel):
    session_id: str
    service: str
    rating: int
    comment: str = ""
    correction: str = ""

    @field_validator("rating")
    @classmethod
    def rating_range(cls, v):
        if not 1 <= v <= 5:
            raise ValueError("Rating must be between 1 and 5")
        return v


class FeedbackResponse(BaseModel):
    status: str
    message: str
    correction_stored: bool = False


class FeedbackSummary(BaseModel):
    service: str
    avg_rating: float
    total_ratings: int
    total_corrections: int
    period: str = "all"
