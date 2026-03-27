"""Integration tests for /v1/vision/* endpoints."""
import base64
import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image as PILImage


def _blank_b64() -> str:
    img = PILImage.new("RGB", (10, 10), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


_MOCK_ANALYSIS = {
    "category": "Electronics",
    "colors": ["black"],
    "material": "plastic",
    "shape": "rectangular",
    "brand_text": "Sony",
    "style": "modern",
    "attributes": ["wireless"],
    "description": "A wireless headset",
    "confidence": 0.95,
}

_MOCK_RESULTS = [
    {
        "item_id": "prod_001",
        "similarity_score": 0.92,
        "rank": 1,
        "metadata": {"name": "Headphones", "price": 50.0},
    }
]


@pytest.fixture(autouse=True)
def mock_vision_deps(monkeypatch):
    """Patch embedding service (no model download) and vision service (no API call)."""
    import numpy as np

    mock_vec = list(np.ones(512) / np.sqrt(512))

    monkeypatch.setattr(
        "services.embedding_service.generate_image_embedding",
        lambda img: mock_vec,
    )
    monkeypatch.setattr(
        "services.embedding_service.generate_text_embedding",
        lambda text: mock_vec,
    )
    monkeypatch.setattr(
        "services.embedding_service.combine_embeddings",
        lambda iv, tv, **kw: mock_vec,
    )
    monkeypatch.setattr(
        "services.embedding_service.image_from_base64",
        lambda b64: PILImage.new("RGB", (10, 10)),
    )

    async def fake_analyze(image_b64):
        return _MOCK_ANALYSIS

    monkeypatch.setattr("services.vision_service.analyze_image", fake_analyze)
    monkeypatch.setattr("services.visual_search_service.vision_service.analyze_image", fake_analyze)

    async def fake_search_similar(platform, query_embedding, limit, min_similarity):
        return _MOCK_RESULTS

    monkeypatch.setattr("services.index_service.search_similar", fake_search_similar)
    monkeypatch.setattr("services.visual_search_service.index_service.search_similar", fake_search_similar)

    async def fake_index_single(platform, item_id, embedding, metadata, image_url, db):
        return True

    monkeypatch.setattr("services.index_service.index_single_item", fake_index_single)
    monkeypatch.setattr("services.visual_search_service.index_service.index_single_item", fake_index_single)

    async def fake_remove(platform, item_id, db):
        return True

    monkeypatch.setattr("services.index_service.remove_item", fake_remove)

    async def fake_stats(platform, db):
        return {
            "platform": platform,
            "total_indexed": 5,
            "last_indexed_at": "2026-03-01T10:00:00",
            "collection_size_mb": 0.03,
        }

    monkeypatch.setattr("services.index_service.get_index_stats", fake_stats)


@pytest.mark.asyncio
async def test_vision_search_with_pk_key_returns_200(client, valid_pk_key):
    """POST /v1/vision/search with pk key returns 200."""
    resp = await client.post(
        "/v1/vision/search",
        json={"platform": "test_platform", "image": _blank_b64(), "limit": 5},
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "query_analysis" in data["data"]
    assert "results" in data["data"]


@pytest.mark.asyncio
async def test_vision_search_no_key_returns_401(client):
    """POST /v1/vision/search without key returns 401."""
    resp = await client.post(
        "/v1/vision/search",
        json={"platform": "test_platform", "image": _blank_b64()},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_vision_index_with_pk_key_returns_403(client, valid_pk_key):
    """POST /v1/vision/index with pk key returns 403 — sk only."""
    resp = await client.post(
        "/v1/vision/index",
        json={
            "platform": "test_platform",
            "items": [{"item_id": "p1", "image": _blank_b64(), "metadata": {}}],
        },
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_vision_index_with_sk_key_returns_200(client, valid_sk_key):
    """POST /v1/vision/index with sk key returns 200."""
    resp = await client.post(
        "/v1/vision/index",
        json={
            "platform": "test_platform",
            "items": [{"item_id": "p1", "image": _blank_b64(), "metadata": {"name": "Widget"}}],
        },
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


@pytest.mark.asyncio
async def test_vision_search_response_has_query_analysis_and_results(client, valid_pk_key):
    """Search response contains query_analysis with detected fields."""
    resp = await client.post(
        "/v1/vision/search",
        json={"platform": "test_platform", "image": _blank_b64(), "limit": 10},
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    qa = body["query_analysis"]
    assert "detected_category" in qa
    assert "detected_colors" in qa
    assert "detected_attributes" in qa
    assert isinstance(body["results"], list)


@pytest.mark.asyncio
async def test_vision_search_unknown_platform_returns_empty_results(client, valid_pk_key, monkeypatch):
    """Search on unknown platform returns empty results, not an error."""
    async def empty_search(platform, query_embedding, limit, min_similarity):
        return []

    monkeypatch.setattr("services.index_service.search_similar", empty_search)
    monkeypatch.setattr("services.visual_search_service.index_service.search_similar", empty_search)

    resp = await client.post(
        "/v1/vision/search",
        json={"platform": "nonexistent_platform", "image": _blank_b64()},
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["results"] == []
    assert resp.json()["data"]["total_found"] == 0


@pytest.mark.asyncio
async def test_vision_search_missing_image_returns_400(client, valid_pk_key, monkeypatch):
    """POST /v1/vision/search with no image or image_url returns 400."""
    from fastapi import HTTPException

    async def raise_400(item):
        raise HTTPException(status_code=400, detail="Provide either 'image' (base64) or 'image_url'")

    monkeypatch.setattr("services.vision_service.get_image_base64", raise_400)
    monkeypatch.setattr("services.visual_search_service.vision_service.get_image_base64", raise_400)

    resp = await client.post(
        "/v1/vision/search",
        json={"platform": "test_platform"},
        headers={"X-DelkaAI-Key": valid_pk_key},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_vision_delete_item_with_sk_returns_200(client, valid_sk_key):
    """DELETE /v1/vision/index/{item_id} with sk key returns 200."""
    resp = await client.delete(
        "/v1/vision/index/prod_001?platform=test_platform",
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["item_id"] == "prod_001"


@pytest.mark.asyncio
async def test_vision_index_status_with_sk_returns_200(client, valid_sk_key):
    """GET /v1/vision/index/status with sk key returns stats."""
    resp = await client.get(
        "/v1/vision/index/status?platform=test_platform",
        headers={"X-DelkaAI-Key": valid_sk_key},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["platform"] == "test_platform"
    assert "total_indexed" in data
    assert "collection_size_mb" in data
