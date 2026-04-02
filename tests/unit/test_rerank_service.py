import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.rerank_service import rerank


@pytest.mark.asyncio
async def test_rerank_empty_documents():
    result = await rerank("query", [])
    assert result == []


@pytest.mark.asyncio
async def test_rerank_fallback_no_nvidia_key(monkeypatch):
    monkeypatch.setattr("config.settings.NVIDIA_API_KEY", "")
    docs = ["doc A", "doc B", "doc C"]
    result = await rerank("test query", docs, top_n=3)
    assert len(result) == 3
    assert result[0]["index"] == 0
    assert result[0]["text"] == "doc A"
    # Fallback assigns decreasing scores
    assert result[0]["score"] > result[1]["score"]


@pytest.mark.asyncio
async def test_rerank_nvidia_success(monkeypatch):
    monkeypatch.setattr("config.settings.NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.setattr("config.settings.NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setattr("config.settings.NVIDIA_RERANK_MODEL", "nvidia/nv-rerankqa-mistral-4b-v3")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "rankings": [
            {"index": 1, "logit": 0.95},
            {"index": 0, "logit": 0.70},
        ]
    }

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("services.rerank_service.httpx.AsyncClient", return_value=mock_client):
        docs = ["first doc", "second doc"]
        result = await rerank("query", docs, top_n=2)

    assert result[0]["index"] == 1
    assert result[0]["text"] == "second doc"
    assert result[0]["score"] == 0.95
