from pydantic import BaseModel, field_validator


class IndexItem(BaseModel):
    item_id: str
    image_url: str = ""
    image_base64: str = ""
    metadata: dict = {}


class IndexRequest(BaseModel):
    platform: str
    items: list[IndexItem]
    webhook_url: str = ""

    @field_validator("items")
    @classmethod
    def max_100_items(cls, v):
        if len(v) > 100:
            raise ValueError("Maximum 100 items per request")
        return v


class IndexResponse(BaseModel):
    status: str
    indexed_count: int
    failed_count: int
    job_id: str = ""


class VisionSearchRequest(BaseModel):
    platform: str
    image: str = ""
    image_url: str = ""
    limit: int = 20
    min_similarity: float = 0.65

    @field_validator("limit")
    @classmethod
    def max_limit(cls, v):
        return min(v, 100)


class SearchResult(BaseModel):
    item_id: str
    similarity_score: float
    rank: int
    metadata: dict


class QueryAnalysis(BaseModel):
    detected_category: str
    detected_colors: list[str]
    detected_attributes: list[str]
    detected_text: str
    confidence: float


class VisionSearchResponse(BaseModel):
    status: str
    data: dict


class IndexStatusResponse(BaseModel):
    platform: str
    total_indexed: int
    last_indexed_at: str | None
    collection_size_mb: float
